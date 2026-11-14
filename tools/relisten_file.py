#!/usr/bin/env python3
"""Re-listen to any audio or video file, not only a session this application retained.

The re-listening pass (`src/relisten.py`) was reachable only from Archive Mode, for a session with
a live transcript beside it. A recording made elsewhere -- a screen capture of a call, a phone
memo -- needed a hand-written placeholder session, a manual `ffmpeg` conversion and a Python call.
This is that, as one command:

1. `ffmpeg` converts each audio stream into its own temporary 16 kHz mono 16-bit WAV, the shape
   `relisten.read_wav_mono_int16` accepts. Channels within a stream are down-mixed. One stream is
   one track. A screen recording that kept the microphone and the system audio apart therefore
   stays two tracks, labelled `Stream 1` and `Stream 2` unless `--labels` names them. They share
   a timebase because they are one container. A file whose stream list cannot be read is refused.
2. The existing pass runs over those tracks, with **no live transcript**. One stream is described
   as a mixed recording. Several streams are described as separate tracks of one file.
3. `--vocab` primes the recogniser with the operator's own domain terms through the same
   `initial_prompt` the archived path uses. The terms are printed in the output header, because
   they are text the decoder may copy (**V74**).

**Offline only.** The storage root from the app's settings decides where weights live (**R48**),
and `HF_HUB_OFFLINE` is set before anything can import `huggingface_hub`. If the model is not
already in that cache the command stops and says so; it never downloads. Run the app and press
Start once to fetch it.

Usage:
    .venv/bin/python tools/relisten_file.py call.mov --vocab "Datadog, JSON, TrueWatch, pipeline"
    .venv/bin/python tools/relisten_file.py memo.m4a --out ~/notes/memo.transcript.txt
    .venv/bin/python tools/relisten_file.py memo.m4a --out ~/notes/ --model mlx-community/whisper-large-v3-turbo

`--out` is the file to write, and missing parent directories are created. It is a directory
only when that path already is one, or when it ends with `/`; the file is then
`<stem>_relistened.md` inside it. An existing file is never overwritten (the run numbers a new
one beside it), and `--out` cannot name the input.
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


def destination(input_path, out_arg):
    """The markdown file this run writes. Returns `(path, error)`.

    No `--out` writes `<stem>_relistened.md` beside the input. `--out` is a directory when that
    path already is one, or when the argument ends with a slash, and the file is then named
    inside it. Any other `--out` is the file itself: a path like `name.transcript.txt` is not
    created as a directory, and missing parents are created so the file can be written there.

    A named file that already exists is not overwritten: the run writes `name-2.txt` (then `-3`…)
    beside it, as the directory form does, so an earlier reading survives a re-run. `--out` naming
    the input itself is refused, since writing there would replace the recording with its text.
    """
    if not out_arg:
        return output_path(input_path, os.path.dirname(input_path)), ""

    raw = os.path.expanduser(out_arg)
    as_directory = raw.endswith("/") or raw.endswith(os.sep)
    resolved = os.path.abspath(raw)
    if as_directory or os.path.isdir(resolved):
        try:
            os.makedirs(resolved, exist_ok=True)
        except OSError as exc:
            return "", f"--out is not a directory that can be created: {resolved} ({exc})"
        return output_path(input_path, resolved), ""

    if _same_file(resolved, input_path):
        return "", f"--out is the input file; writing there would replace the recording: {resolved}"

    parent = os.path.dirname(resolved)
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
    except OSError as exc:
        return "", f"--out's directory could not be created: {parent} ({exc})"
    return _unused(resolved), ""


def _same_file(path, input_path):
    if os.path.abspath(path) == os.path.abspath(input_path):
        return True
    try:
        return os.path.samefile(path, input_path)
    except OSError:
        return False


def _unused(path):
    """`path` if nothing is there yet, else the first free `<base>-N<ext>` beside it."""
    base, ext = os.path.splitext(path)
    candidate = path
    number = 2
    while os.path.exists(candidate):
        candidate = f"{base}-{number}{ext}"
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


def track_labels(count, labels_arg, single_label):
    """Names for each audio stream, in stream order.

    Several streams default to `Stream 1`, `Stream 2`, …. One stream keeps `single_label`
    (`--label`, default `Recording`) unless `--labels` names it. Returns `(names, error)`.
    """
    if labels_arg:
        names = [" ".join(part.split()) for part in labels_arg.split(",")]
        if len(names) != count or any(not name for name in names):
            return [], (f"--labels needs {count} names for {count} audio streams, "
                        f"in stream order")
        if len(set(names)) != len(names):
            return [], "--labels names must be distinct, because each stream is its own track"
        if any("`" in name for name in names):
            return [], "a track label cannot contain a backtick"
        return names, ""
    if count == 1:
        return [single_label], ""
    return [f"Stream {index}" for index in range(1, count + 1)], ""


def convert(ffmpeg, input_path, wav_path, stream_index=0):
    """Decode audio stream `stream_index` into 16 kHz mono 16-bit PCM. Returns an error or ""."""
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
               "-i", input_path, "-vn", "-map", f"0:a:{stream_index}",
               "-ac", "1", "-ar", str(TARGET_RATE), "-c:a", "pcm_s16le", wav_path]
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
                        help="comma-separated domain terms to prime recognition with. "
                             "A term cannot contain a backtick")
    parser.add_argument("--out", default="",
                        help="file to write. A path that already is a directory, or that ends "
                             "with /, receives <stem>_relistened.md instead. An existing file is "
                             "kept and the run writes <name>-2 beside it; the input cannot be "
                             "named (default: <stem>_relistened.md next to the input)")
    parser.add_argument("--model", default="",
                        help="ASR model id (default: ASR_MODEL from settings, else the shipped one)")
    parser.add_argument("--label", default="Recording",
                        help="role label when the file has one audio stream (default: Recording)")
    parser.add_argument("--labels", default="",
                        help="comma-separated names for each audio stream, in stream order "
                             "(default: Stream 1, Stream 2, ...)")
    parser.add_argument("--diarize", action="store_true",
                        help="separate voices on a single mixed stream. This command does not "
                             "install the diarizer; see src/diarize.py. Not applied when the "
                             "file has more than one audio stream")
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
    labels, label_error = track_labels(streams, args.labels, args.label)
    if label_error:
        print(f"❌ {label_error}", file=sys.stderr)
        return 2
    if "`" in args.vocab:
        print("❌ a vocabulary term cannot contain a backtick", file=sys.stderr)
        return 2
    target, out_error = destination(input_path, args.out)
    if out_error:
        print(f"❌ {out_error}", file=sys.stderr)
        return 2

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

    # One mixed stream can still be split by voice. Several streams are already one side each;
    # diarizing them would invent a second split the container already made.
    diarize = args.diarize and len(labels) == 1
    if args.diarize and not diarize:
        print("⚠️ --diarize applies to one mixed stream. These streams are already separate "
              "tracks, so voices were not separated further.", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="aegis-relisten-") as scratch:
        tracks = {}
        for index, label in enumerate(labels):
            wav = os.path.join(scratch, f"stream-{index}.wav")
            # One stream keeps the 3-argument call the single-file tests replace.
            error = convert(ffmpeg, input_path, wav) if len(labels) == 1 else \
                convert(ffmpeg, input_path, wav, index)
            if error:
                print(f"❌ {error}", file=sys.stderr)
                return 1
            tracks[label] = wav
        outcome = relisten.run(
            None, tracks,
            model_path=model,
            vocabulary=args.vocab,
            out_path=target,
            source=input_path,
            diarize=diarize,
            hf_token=(settings.get("HF_TOKEN") or "").strip(),
            diarize_model=(settings.get("DIARIZE_MODEL") or "").strip(),
            speaker_track=labels[0],
            same_container=len(labels) > 1,
            track_order=labels,
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
