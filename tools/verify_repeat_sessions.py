"""Start and stop capture several times in one process, and check the later sessions still work.

The app is long-lived: the operator holds one Streamlit process across a whole day and starts a
session per meeting. Every capture measurement so far -- including V62 -- was a *first* session in
a fresh process, which is the one case that cannot expose the risk this checks.

The risk is specific and was created on the same day it is being tested. Starting the tap
re-initialises PortAudio and waits for the device to appear; stopping it re-initialises again so
the destroyed device leaves the table. Both are global operations on a library the microphone
stream is also using, and the second session is where an asymmetry shows up:

  - a stale device entry surviving teardown would make the *next* Start find the device
    immediately, satisfy its wait, and open a stream on an index pointing at nothing;
  - a device index that shifted because the tap left the table would silently move the microphone
    to a different input;
  - a helper subprocess not reaped would hold the aggregate device and make the next
    `AudioHardwareCreateAggregateDevice` fail on a duplicate UID.

None of those raise. All of them produce a session that reports success and transcribes nothing,
which is the failure mode this project keeps finding and the reason this runs three times rather
than once.

Run:  PYTHONPATH="$PWD" .venv/bin/python tools/verify_repeat_sessions.py [--rounds 3]
"""

import argparse
import os
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

SENTENCE = "Round {n}. The witness will answer the question."


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--drain", type=int, default=8)
    args = parser.parse_args()

    import bootstrap
    settings = bootstrap.read_settings()
    if not bootstrap.is_configured(settings):
        sys.exit("no storage root configured")
    bootstrap.apply_environment(settings)
    bootstrap.enforce_offline()

    import audio_devices
    import system_audio
    from global_state import GlobalState

    state = GlobalState()
    state.warm_up(asr_model=(settings.get("ASR_MODEL") or "").strip() or None,
                  mic_device=(settings.get("MIC_DEVICE") or "").strip())
    print(f"warm — mic {state.me_name!r}, system {state.other_name!r}")

    tmp = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp")
    tmp = tmp if os.path.isdir(tmp) else "/tmp"

    results = []
    for round_number in range(1, args.rounds + 1):
        sentence = SENTENCE.format(n=round_number)
        clip = os.path.join(tmp, f"repeat{round_number}.aiff")
        subprocess.run(["say", "-o", clip, sentence], check=False, capture_output=True)

        before = len(state.buffer.get_full_dialogue())
        state.start_recording(enable_rag=False)
        participant_device = state.other_name
        # The device the Participant stream actually opened, not the one we hoped for.
        opened_index = getattr(state.transcriber_other, "device_idx", None)
        mic_index = getattr(state.transcriber_me, "device_idx", None)
        subprocess.run(["afplay", clip], check=False)
        deadline = time.monotonic() + args.drain
        while time.monotonic() < deadline:
            time.sleep(0.5)
        state.stop_recording()

        new_lines = state.buffer.get_full_dialogue()[before:]
        participant = [entry for entry in new_lines if entry.get("role") == "Participant"]
        leftover = any(device["name"] == system_audio.TAP_DEVICE_NAME
                       for device in audio_devices.list_input_devices())
        results.append({
            "round": round_number,
            "participant_device": participant_device,
            "participant_index": opened_index,
            "mic_index": mic_index,
            "participant_lines": [entry.get("text") for entry in participant],
            "device_left_behind": leftover,
        })
        print(f"round {round_number}: device={participant_device!r} idx={opened_index} "
              f"mic_idx={mic_index} lines={len(participant)} leftover={leftover}")
        for entry in participant:
            print(f"    {entry.get('text')}")

    print("\n===== verdict =====")
    silent = [r for r in results if not r["participant_lines"]]
    if silent:
        print(f"  ❌ {len(silent)} of {len(results)} rounds produced NO Participant line: "
              f"{[r['round'] for r in silent]}")
    else:
        print(f"  ✅ all {len(results)} rounds transcribed system audio")
    if any(r["device_left_behind"] for r in results):
        print("  ❌ the tap device survived teardown in at least one round")
    indices = {r["mic_index"] for r in results}
    if len(indices) > 1:
        print(f"  ⚠️  the microphone's resolved index changed across rounds: {indices}. "
              f"Not wrong by itself -- the name is what is stored -- but worth knowing.")
    return 0 if not silent else 1


if __name__ == "__main__":
    sys.exit(main())
