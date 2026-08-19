#!/usr/bin/env python3
"""Build a reusable V52 / 7.3 prompt audio fixture.

Default path is TTS (macOS `say`) — preferred for repeatable verification. Optional
`--teleprompter` records your mic while showing timed captions (natural speech).

Why TTS is enough for closing 7.3: V52 measures UI contention against live inference
latency, not WER. The audio only has to enter the running Transcriber (play while
capture is Started). Natural reading is optional.

Output (gitignored WAV): fixtures/asr/speech/en/v52_ten_line_en.wav
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from asr_eval import (  # noqa: E402
    TARGET_SR,
    assert_fixture_path_allowed,
    load_wav_mono_float32,
    write_wav_mono_int16,
)

DEFAULT_OUT = os.path.join(
    REPO_ROOT, "fixtures", "asr", "speech", "en", "v52_ten_line_en.wav",
)

# Same shape as the V52 write-up: ten lines, long pauses → one segment each.
LINES = [
    "Good morning everyone, thank you for joining today's briefing.",
    "Quarterly revenue grew twelve percent year over year.",
    "Operating margin improved by two points versus last quarter.",
    "We launched three products in the Asia Pacific region.",
    "Customer retention remains above ninety four percent.",
    "The support backlog is down to under two days on average.",
    "Next we will review the hiring plan for engineering.",
    "Please hold questions until the prepared remarks are finished.",
    "Finance will circulate the detailed slides after this call.",
    "That concludes the overview; we will now take questions.",
]

GAP_S = 4.0
# Three passes → ~30 segments (closes 7.3 n≥30 without a second live arm).
PASSES = 3
VOICE = "Samantha"


def _silence(duration_s, sr=TARGET_SR):
    return [0.0] * int(duration_s * sr)


def _say_line_to_samples(text, voice, sr=TARGET_SR):
    if shutil.which("say") is None or shutil.which("afconvert") is None:
        raise RuntimeError("macOS say + afconvert required for TTS mode")
    with tempfile.TemporaryDirectory() as tmp:
        aiff = os.path.join(tmp, "line.aiff")
        wav = os.path.join(tmp, "line.wav")
        cmd = ["say", "-o", aiff, "-v", voice, text]
        subprocess.run(cmd, check=True, timeout=120, capture_output=True)
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", f"LEI16@{sr}", aiff, wav],
            check=True, timeout=60, capture_output=True,
        )
        samples, _ = load_wav_mono_float32(wav, target_sr=sr)
        return samples


def build_tts(out_path, voice=VOICE, gap_s=GAP_S, passes=PASSES):
    assert_fixture_path_allowed(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    combined = []
    print(f"TTS voice={voice!r} gap={gap_s}s passes={passes} → {out_path}")
    for p in range(passes):
        print(f"  pass {p + 1}/{passes}")
        for i, line in enumerate(LINES, 1):
            print(f"    [{i:02d}] {line}")
            combined.extend(_say_line_to_samples(line, voice))
            combined.extend(_silence(gap_s))
    write_wav_mono_int16(out_path, combined)
    dur = len(combined) / float(TARGET_SR)
    print(f"Wrote {out_path} ({dur:.1f}s, {TARGET_SR} Hz mono)")
    return out_path


def teleprompter_record(out_path, gap_s=GAP_S, passes=PASSES, sample_rate=TARGET_SR):
    """Show captions with timing; record default input to out_path."""
    import numpy as np
    import sounddevice as sd

    assert_fixture_path_allowed(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    print("Teleprompter record — speak each line when it appears.")
    print("Recording starts in 3 seconds…")
    time.sleep(3)

    chunks = []

    def _callback(indata, frames, time_info, status):
        if status:
            print(status, file=sys.stderr)
        chunks.append(indata.copy())

    stream = sd.InputStream(
        channels=1, samplerate=sample_rate, dtype="float32", callback=_callback,
    )
    with stream:
        for p in range(passes):
            print(f"\n===== PASS {p + 1}/{passes} =====\n")
            for i, line in enumerate(LINES, 1):
                print("\033[2J\033[H", end="")  # clear
                print(f"PASS {p + 1}/{passes}   LINE {i}/{len(LINES)}\n")
                print("=" * 60)
                print(line)
                print("=" * 60)
                print("\n(speak now)")
                # Rough speak window from word count, then enforced gap.
                speak_s = max(3.0, 0.35 * len(line.split()))
                time.sleep(speak_s)
                print(f"\n… pause {gap_s:.0f}s …")
                time.sleep(gap_s)
    if not chunks:
        raise RuntimeError("no audio captured")
    audio = np.concatenate(chunks, axis=0).reshape(-1)
    write_wav_mono_int16(out_path, audio.tolist(), sample_rate=sample_rate)
    print(f"Wrote {out_path} ({len(audio) / sample_rate:.1f}s)")
    return out_path


def play(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    print(f"Playing {path} (use while the app has Start'd capture)")
    if shutil.which("afplay"):
        subprocess.run(["afplay", path], check=True)
        return
    import numpy as np
    import sounddevice as sd

    samples, sr = load_wav_mono_float32(path, target_sr=TARGET_SR)
    sd.play(np.asarray(samples, dtype=np.float32), sr)
    sd.wait()


def print_script():
    print("V52 ten-line script (4s silence between lines, two passes in the WAV):\n")
    for i, line in enumerate(LINES, 1):
        print(f"{i:02d}. {line}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output WAV path")
    parser.add_argument("--voice", default=VOICE, help="macOS say voice for TTS")
    parser.add_argument("--gap", type=float, default=GAP_S, help="Silence between lines (s)")
    parser.add_argument("--passes", type=int, default=PASSES, help="How many full script passes")
    parser.add_argument(
        "--teleprompter", action="store_true",
        help="Record mic with on-screen captions instead of TTS",
    )
    parser.add_argument(
        "--play", action="store_true",
        help="Play an existing (or just-built) WAV and exit",
    )
    parser.add_argument("--print-script", action="store_true", help="Print lines and exit")
    parser.add_argument("--force", action="store_true", help="Overwrite existing WAV")
    args = parser.parse_args()

    if args.print_script:
        print_script()
        return 0

    out = os.path.abspath(args.out)
    if args.play and os.path.isfile(out) and not args.teleprompter:
        play(out)
        return 0

    if os.path.isfile(out) and not args.force and not args.teleprompter:
        print(f"Exists (use --force to rebuild): {out}")
    elif args.teleprompter:
        teleprompter_record(out, gap_s=args.gap, passes=args.passes)
    else:
        build_tts(out, voice=args.voice, gap_s=args.gap, passes=args.passes)

    if args.play:
        play(out)
    else:
        print("\nNext: Start capture in the app, then play this file into the mic path:")
        print(f"  .venv/bin/python tools/gen_v52_prompt_audio.py --play --out {out}")
        print("  # or: afplay", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
