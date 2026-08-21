"""Run the capture pipeline for real, once, and report what came out.

This exists because of a line that stood in `STATE.md` for weeks: **capture itself has never been
executed** — not on this machine, not on any. Warm-up, weight download and pre-flight were all
verified; everything below the point where a stream opens was not. Every latency and accuracy
number the project has was measured by feeding WAV files to the transcriber, which says nothing
about whether a device opens, whether the two tracks stay apart, or whether a session stops
cleanly.

What it does:

1. Warms the model through `GlobalState`, exactly as the app does.
2. Presses Start — which opens the microphone and, on a machine that can run it, publishes and
   opens the system-audio tap.
3. Plays synthesized speech through the **system output**, so the Participant track has something
   real to transcribe. `say` is macOS's offline TTS; nothing here reaches the network.
4. Reads the dialogue buffer and reports what each track produced.
5. Stops, and checks the tap's device is gone afterwards.

It writes a session file under `history/` the way a real meeting does, because it *is* a real
session — that directory is the operator's and this tool does not read it back.

Run:  PYTHONPATH="$PWD" .venv/bin/python tools/verify_capture_end_to_end.py [--seconds 20]

Expect the microphone track to pick the speech up acoustically from the speakers. That is not a
fault: it is the room, and it is the condition R2 exists for — one merged track could not tell the
two apart, and V60 measured what overlapping speech does to the transcript.
"""

import argparse
import json
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

SENTENCES = [
    "The committee will now hear testimony on the budget allocation.",
    "請問這個項目的預算是多少？",
    "We reviewed the report and found three material discrepancies.",
]


def synthesize(tmp_dir):
    """Render the sentences with macOS `say`. Offline, and no fixture has to be committed."""
    paths = []
    for index, sentence in enumerate(SENTENCES):
        path = os.path.join(tmp_dir, f"line{index}.aiff")
        voice = ["-v", "Meijia"] if any("一" <= ch <= "鿿" for ch in sentence) else []
        result = subprocess.run(["say", *voice, "-o", path, sentence], capture_output=True)
        if result.returncode == 0 and os.path.exists(path):
            paths.append((sentence, path))
        else:
            print(f"  ! could not synthesize {sentence!r}: {result.stderr.decode()[:80]}")
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=20,
                        help="how long to keep the session open after the audio finishes")
    args = parser.parse_args()

    import bootstrap
    settings = bootstrap.read_settings()
    if not bootstrap.is_configured(settings):
        sys.exit("no storage root configured; open the app and set one first")
    bootstrap.apply_environment(settings)
    bootstrap.enforce_offline()

    import system_audio
    from global_state import GlobalState

    backend, detail = system_audio.available_backend()
    print(f"backend: {backend} ({detail})")

    state = GlobalState()
    print("warming up (minutes on a cold NPU)...")
    started = time.monotonic()
    state.warm_up(asr_model=(settings.get("ASR_MODEL") or "").strip() or None,
                  mic_device=(settings.get("MIC_DEVICE") or "").strip())
    print(f"  warm in {time.monotonic() - started:.1f}s"
          f" — mic {state.me_name!r}, system {state.other_name!r}")

    tmp_dir = os.environ.get("CLAUDE_JOB_DIR", "/tmp")
    tmp_dir = os.path.join(tmp_dir, "tmp") if os.path.isdir(os.path.join(tmp_dir, "tmp")) else tmp_dir
    clips = synthesize(tmp_dir)
    print(f"synthesized {len(clips)} clips")

    print("starting capture...")
    state.start_recording(enable_rag=False)
    try:
        print(f"  backend now: {state.audio_backend} ({state.audio_backend_detail})")
        print(f"  participant device: {state.other_name!r}")
        for sentence, path in clips:
            print(f"  playing: {sentence}")
            subprocess.run(["afplay", path], check=False)
            time.sleep(1.5)
        print(f"  waiting {args.seconds}s for inference to drain...")
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            time.sleep(1.0)
    finally:
        print("stopping...")
        state.stop_recording()

    lines = state.buffer.get_full_dialogue()
    print("\n===== what reached the dialogue buffer =====")
    print(json.dumps(lines, ensure_ascii=False, indent=2)[:4000])

    by_role = {}
    for entry in lines:
        by_role.setdefault(entry.get("role", "?"), []).append(entry.get("text", ""))
    print("\n===== summary =====")
    for role, texts in by_role.items():
        print(f"  {role}: {len(texts)} lines")
    if not lines:
        print("  NOTHING. A silent run is a result, not a crash -- check the backend line above.")

    # `stop` re-initialises PortAudio itself, so this reads the current table rather than the
    # cached one. The first run of this tool did not, reported "still present", and sent me
    # looking for a teardown bug that was really a stale enumeration -- which then turned out to
    # be a real bug anyway, in the opposite direction: the *next* Start would have trusted it.
    import audio_devices
    gone = not any(d["name"] == system_audio.TAP_DEVICE_NAME
                   for d in audio_devices.list_input_devices())
    print(f"  tap device removed after stop: {gone}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
