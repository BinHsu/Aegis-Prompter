#!/usr/bin/env python3
"""Re-listen to any audio or video file, not only a session this application retained.

The re-listening pass (`src/relisten.py`) was reachable only from Archive Mode, for a session with
a live transcript beside it. A recording made elsewhere -- a screen capture of a call, a phone
memo -- needed a hand-written placeholder session, a manual `ffmpeg` conversion and a Python call.
This is that, as one command:

1. `ffmpeg` converts the first audio stream into a temporary 16 kHz mono 16-bit WAV, the one
   shape `relisten.read_wav_mono_int16` accepts. Channels are down-mixed. A file with more than
   one audio stream is refused, and so is a file whose stream list cannot be read: this command
   is for one mixed track, and keeping one stream of several would describe a call it only half
   heard.
2. The existing pass runs over that one track, with **no live transcript**, so the output header
   describes a single external file instead of two tracks and a missing timebase.
3. `--vocab` primes the recogniser with the operator's own domain terms through the same
   `initial_prompt` the archived path uses. The terms are printed in the output header, because
   they are text the decoder may copy (**V74**).

**Offline only.** The storage root from the app's settings decides where weights live (**R48**),
and `HF_HUB_OFFLINE` is set before anything can import `huggingface_hub`. If the model is not
already in that cache the command stops and says so; it never downloads. Run the app and press
Start once to fetch it.

Usage:
    .venv/bin/python tools/relisten_file.py call.mov --vocab "Datadog, JSON, TrueWatch, pipeline"
    .venv/bin/python tools/relisten_file.py memo.m4a --out ~/notes --model mlx-community/whisper-large-v3-turbo
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

TARGET_RATE = 16000


def output_path(input_path, out_dir):
    """`<stem>_relistened.md` in `out_dir`, numbered rather than overwriting an earlier run.

    A re-run with a better vocabulary is the normal next step, and the previous reading is worth
    comparing against rather than losing.
    """
    import relisten
    stem = os.path.splitext(os.path.basename(input_path))[0]
    candidate = os.path.join(out_dir, f"{stem}{relisten.RELISTEN_SUFFIX}.md")
    number = 2
    while os.path.exists(candidate):
        candidate = os.path.join(out_dir, f"{stem}{relisten.RELISTEN_SUFFIX}-{number}.md")
        number += 1
    return candidate


_AUDIO_STREAM = re.compile(r"^\s*Stream #\d+:\d+.*:\s*Audio:", re.MULTILINE)


def audio_stream_count(ffmpeg, input_path):
    """How many audio streams `ffmpeg` lists, or None when that listing cannot be read.

    `ffmpeg -i` writes the input's streams to stderr and exits non-zero because no output file
    was asked for. A missing or failed `ffprobe` must not be treated as "one stream": the header
    would then describe a single mixed recording that was only the stream ffmpeg happened to keep.
    """
    if not ffmpeg:
        return None
    completed = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-i", input_path],
        capture_output=True, text=True)
    if "Input #" not in completed.stderr:
        return None
    return len(_AUDIO_STREAM.findall(completed.stderr))


def convert(ffmpeg, input_path, wav_path):
    """Decode the first audio stream into 16 kHz mono 16-bit PCM. Returns an error string or ""."""
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", input_path, "-vn", "-ac", "1", "-ar", str(TARGET_RATE),
               "-c:a", "pcm_s16le", wav_path]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        return f"ffmpeg exit {completed.returncode}: {completed.stderr.strip()[-400:]}"
    if not os.path.exists(wav_path) or os.path.getsize(wav_path) <= 44:
        return "ffmpeg produced no audio -- does the input have an audio stream?"
    return ""


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Re-transcribe an audio or video file with Aegis Prompter's offline model.")
    parser.add_argument("input", help="any file ffmpeg can decode (.mov, .mp4, .m4a, .wav, ...)")
    parser.add_argument("--vocab", default="",
                        help="comma-separated domain terms to prime recognition with")
    parser.add_argument("--out", default="",
                        help="directory for the markdown (default: next to the input)")
    parser.add_argument("--model", default="",
                        help="ASR model id (default: ASR_MODEL from settings, else the shipped one)")
    parser.add_argument("--label", default="Recording", help="role label on every line")
    parser.add_argument("--diarize", action="store_true",
                        help="separate voices (optional, installed on demand; see src/diarize.py)")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    input_path = os.path.abspath(os.path.expanduser(args.input))
    if not os.path.isfile(input_path):
        print(f"❌ not a file: {input_path}", file=sys.stderr)
        return 2
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("❌ ffmpeg is not on PATH (brew install ffmpeg)", file=sys.stderr)
        return 2
    streams = audio_stream_count(ffmpeg, input_path)
    if streams is None:
        print(f"❌ could not tell how many audio streams "
              f"{os.path.basename(input_path)} has, so it was not transcribed.",
              file=sys.stderr)
        return 2
    if streams == 0:
        print(f"❌ no audio stream in {os.path.basename(input_path)}", file=sys.stderr)
        return 1
    if streams is not None and streams > 1:
        print(f"❌ {streams} audio streams in {os.path.basename(input_path)}. This command "
              f"transcribes one mixed stream — a screen recording with both sides already in "
              f"one track. It will not pick a stream and call that the whole recording.",
              file=sys.stderr)
        return 2
    out_dir = os.path.abspath(os.path.expanduser(args.out)) if args.out else \
        os.path.dirname(input_path)
    if os.path.isfile(out_dir):
        print(f"❌ --out is a file, not a directory: {out_dir}", file=sys.stderr)
        return 2
    os.makedirs(out_dir, exist_ok=True)

    import bootstrap
    settings = bootstrap.read_settings()
    if not bootstrap.is_configured(settings):
        print("❌ no storage root is configured, so there is no model cache to read from. Open "
              "the app once and set it (R48).", file=sys.stderr)
        return 2
    # Order matters (V19): the cache path and the offline flag must be in the environment before
    # anything imports `huggingface_hub`, which reads both at import time.
    paths = bootstrap.apply_environment(settings)
    bootstrap.enforce_offline()

    import relisten
    model = args.model.strip() or (settings.get("ASR_MODEL") or "").strip() or \
        relisten.default_model()
    if not bootstrap.weights_present(model):
        print(f"❌ {model} is not in the local cache ({paths['models']}). This command does not "
              f"download; start a capture in the app once to fetch it, or pass --model with one "
              f"that is cached.", file=sys.stderr)
        return 2

    target = output_path(input_path, out_dir)
    with tempfile.TemporaryDirectory(prefix="aegis-relisten-") as scratch:
        wav = os.path.join(scratch, "input.wav")
        error = convert(ffmpeg, input_path, wav)
        if error:
            print(f"❌ {error}", file=sys.stderr)
            return 1
        outcome = relisten.run(
            None, {args.label: wav},
            model_path=model,
            vocabulary=args.vocab,
            out_path=target,
            source=input_path,
            diarize=args.diarize,
            hf_token=(settings.get("HF_TOKEN") or "").strip(),
            diarize_model=(settings.get("DIARIZE_MODEL") or "").strip(),
            speaker_track=args.label,
            on_progress=lambda label: print(f"🎧 {label}", file=sys.stderr),
        )

    if outcome.get("diarize_error"):
        print(f"⚠️ voices not separated: {outcome['diarize_error']}", file=sys.stderr)
    if outcome["error"]:
        print(f"❌ {outcome['error']}", file=sys.stderr)
    if not outcome["output"]:
        return 1
    print(f"{outcome['output']}  ({outcome['segments']} lines, vocabulary: "
          f"{outcome['vocabulary'] or 'off'})")
    return 1 if outcome["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
