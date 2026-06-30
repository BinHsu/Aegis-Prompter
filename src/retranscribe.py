"""Offline re-transcribe engine. Runs the SAME model as the live pipeline but with no realtime
gate and no lossy ring, so it never drops audio and maximizes quality. This is the "complete
record" deliverable that recovers anything the live path lost under load.

Two modes:

  Single file : python src/retranscribe.py -at <audio> -o <out.txt>
                Transcribes one arbitrary audio file to plain text. A mono file yields a single
                transcript. A multichannel WAV (e.g. L=Speaker, R=Participant) is transcribed per
                channel and merged by segment start time into a channel-labeled transcript.

  Session dir : python src/retranscribe.py recordings/<session_id>/
                Transcribes every per-track WAV, tags each segment with its track role, merges all
                tracks sorted by start time, and writes a speaker-labeled, time-ordered
                transcript.md (+ transcript.txt) into the session directory.

Constants and the model id come from transcriber.py — no duplicated magic strings.

Channel-split is supported for 16kHz int16 WAV files without extra dependencies. Other formats are
decoded mono via mlx_whisper (ffmpeg) and produce a single transcript; this limit is by design to
avoid new pip dependencies.
"""
import os
import sys
import glob
import wave
import argparse
import datetime

import numpy as np
import mlx_whisper

from transcriber import Transcriber, DEFAULT_MODEL, DEFAULT_BILINGUAL_PROMPT, NPU_LOCK

SAMPLE_RATE = 16000


def should_run_batch(argv):
    """True when batch (file->text) mode is requested via -at/--audio anywhere in argv.

    Used by app.py to decide between batch mode and the live Streamlit app BEFORE importing
    streamlit. `streamlit run src/app.py` carries no such flag, so it always returns False and the
    live path is untouched; argparse never runs against streamlit's own argv."""
    return any(arg in ("-at", "--audio") for arg in argv)


def load_wav_channels(path):
    """Load a 16kHz int16 WAV as a list of mono float32 channel arrays. Returns (channels, sr).
    Raises ValueError on unsupported sample width."""
    with wave.open(path, "rb") as w:
        nch = w.getnchannels()
        sampwidth = w.getsampwidth()
        sr = w.getframerate()
        nframes = w.getnframes()
        raw = w.readframes(nframes)

    if sampwidth != 2:
        raise ValueError(f"Unsupported sample width {sampwidth * 8}-bit; only 16-bit PCM is supported.")

    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        data = data.reshape(-1, nch)
        channels = [np.ascontiguousarray(data[:, c]) for c in range(nch)]
    else:
        channels = [data]
    return channels, sr


def transcribe_audio(audio_or_path, label):
    """One full, ungated decode over a complete recording (mlx chunks long audio internally).
    Returns a list of {start, text, label}, ghost-phrase-filtered with the live pipeline's rule."""
    with NPU_LOCK:
        result = mlx_whisper.transcribe(
            audio_or_path,
            path_or_hf_repo=DEFAULT_MODEL,
            language=None,
            initial_prompt=DEFAULT_BILINGUAL_PROMPT,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
            fp16=True,
        )
    segments = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if Transcriber._acceptable(text):
            segments.append({"start": float(seg.get("start", 0.0)), "text": text, "label": label})
    return segments


def _fmt_ts(seconds):
    """Whole-second HH:MM:SS for transcript readability."""
    total = int(seconds)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def write_markdown(path, title_id, tracks, segments):
    """Write a speaker-labeled, time-ordered markdown transcript."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Complete Meeting Transcript",
        "",
        f"- Source: {title_id}",
        f"- Generated: {now}",
        f"- Tracks: {', '.join(tracks)}",
        "",
        "---",
        "",
    ]
    for seg in segments:
        lines.append(f"**[{_fmt_ts(seg['start'])}] {seg['label']}**: {seg['text']}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_text(path, segments, labeled):
    """Write a plain-text transcript. Labeled=True prefixes each line with [ts] label."""
    lines = []
    for seg in segments:
        if labeled:
            lines.append(f"[{_fmt_ts(seg['start'])}] {seg['label']}: {seg['text']}")
        else:
            lines.append(seg["text"])
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


def _write_summary(transcript_text, summary_path):
    """Summarize transcript_text with the local LLM and write it to summary_path.

    summarizer (and thus mlx-lm) is imported here so the no-summary path never pulls in the
    dependency. A summary failure is swallowed and reported: the transcript is already on disk and
    must not be jeopardized by the optional summary step."""
    try:
        import summarizer  # lazy: keeps mlx-lm out of the default transcribe path
        summary = summarizer.summarize(transcript_text)
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary.rstrip() + "\n")
        print(f"[retranscribe] Wrote summary to {summary_path}")
    except Exception as e:
        # Never fail the transcript step on a summary error.
        print(f"[retranscribe] Summary step failed (transcript is unaffected): {e}")


def run_single_file(audio_path, out_path, summarize=False):
    """Batch mode: transcribe one audio file to a plain-text transcript. Multichannel WAV is split
    per channel and merged time-ordered; everything else is a single track.

    summarize=True additionally writes a local-LLM summary to <output_stem>.summary.md."""
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    is_wav = audio_path.lower().endswith(".wav")
    segments = []
    labeled = False

    if is_wav:
        channels, sr = load_wav_channels(audio_path)
        if sr == SAMPLE_RATE and len(channels) >= 2:
            # True multichannel WAV: transcribe each channel separately, then merge by start time.
            labeled = True
            for idx, chan in enumerate(channels, start=1):
                segments.extend(transcribe_audio(chan, f"Channel {idx}"))
            segments.sort(key=lambda s: s["start"])
        elif sr == SAMPLE_RATE:
            segments = transcribe_audio(channels[0], "Track")
        else:
            # Non-16kHz WAV: let mlx/ffmpeg resample via the path (mono).
            segments = transcribe_audio(audio_path, "Track")
    else:
        # Arbitrary format: mlx decodes mono via ffmpeg. No channel split (no extra deps).
        segments = transcribe_audio(audio_path, "Track")

    write_text(out_path, segments, labeled=labeled)
    print(f"[retranscribe] Wrote {len(segments)} segments to {out_path}")

    if summarize:
        transcript_text = "\n".join(
            (f"{s['label']}: {s['text']}" if labeled else s["text"]) for s in segments
        )
        summary_path = os.path.splitext(out_path)[0] + ".summary.md"
        _write_summary(transcript_text, summary_path)

    return out_path


def run_session_dir(session_dir, summarize=False):
    """Session mode: transcribe every per-track WAV and merge into a complete time-ordered,
    speaker-labeled transcript.md (+ transcript.txt) inside the session directory.

    summarize=True additionally writes a local-LLM summary.md into the session directory."""
    session_dir = session_dir.rstrip("/")
    if not os.path.isdir(session_dir):
        raise NotADirectoryError(f"Session directory not found: {session_dir}")

    wavs = sorted(glob.glob(os.path.join(session_dir, "*.wav")))
    if not wavs:
        raise FileNotFoundError(f"No .wav track files in {session_dir}")

    segments = []
    tracks = []
    for wav_path in wavs:
        role = os.path.splitext(os.path.basename(wav_path))[0]
        tracks.append(role)
        print(f"[retranscribe] Transcribing track '{role}' from {wav_path} ...")
        try:
            channels, sr = load_wav_channels(wav_path)
            audio_input = channels[0] if sr == SAMPLE_RATE else wav_path
        except Exception as e:
            print(f"[retranscribe] WAV load failed ({e}); falling back to path decode.")
            audio_input = wav_path
        segments.extend(transcribe_audio(audio_input, role))

    segments.sort(key=lambda s: s["start"])

    session_id = os.path.basename(session_dir)
    md_path = os.path.join(session_dir, "transcript.md")
    txt_path = os.path.join(session_dir, "transcript.txt")
    write_markdown(md_path, session_id, tracks, segments)
    write_text(txt_path, segments, labeled=True)
    print(f"[retranscribe] Wrote {len(segments)} merged segments to {md_path} and {txt_path}")

    if summarize:
        transcript_text = "\n".join(f"[{_fmt_ts(s['start'])}] {s['label']}: {s['text']}" for s in segments)
        summary_path = os.path.join(session_dir, "summary.md")
        _write_summary(transcript_text, summary_path)

    return md_path


def build_arg_parser():
    """Build the CLI argument parser. Factored out so tests can assert flag parsing without
    invoking main() against a real session."""
    parser = argparse.ArgumentParser(
        description="Offline re-transcribe: single audio file (-at/-o) or a session directory.")
    parser.add_argument("session_dir", nargs="?", default=None,
                        help="recordings/<session_id>/ directory to merge into transcript.md")
    parser.add_argument("-at", "--audio", dest="audio", default=None,
                        help="single audio file to transcribe to plain text")
    parser.add_argument("-o", "--output", dest="output", default=None,
                        help="output text file for single-file mode")
    parser.add_argument("--summarize", dest="summarize", action="store_true", default=False,
                        help="also write a local-LLM summary (mlx-lm) next to the transcript")
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.audio:
        out_path = args.output or (os.path.splitext(args.audio)[0] + ".txt")
        run_single_file(args.audio, out_path, summarize=args.summarize)
    elif args.session_dir:
        run_session_dir(args.session_dir, summarize=args.summarize)
    else:
        parser.error("Provide either -at <audio> [-o <out>] or a session directory path.")


if __name__ == "__main__":
    main()
