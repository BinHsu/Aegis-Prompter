"""Measure what actually arrives when PortAudio opens the system-audio tap.

Answers two questions the plan cannot proceed without:

  **V9** — is the aggregate device the helper publishes visible to a *different* process as an
  ordinary input? Everything about the capture design rests on this: if it is, system audio goes
  through the same `sd.InputStream` path as the microphone and there is one pipeline, not two.

  **V12** — the tap is fixed at 48 kHz and `docs/decisions/0001` made 16 kHz the single rate
  through the whole product. Someone has to resample. This measures whether PortAudio will do it
  on request, by asking for a rate and then timing what arrives: a stream that reports 16000 but
  delivers 48000 frames per second is not resampling, it is relabelling, and the audio would be
  read as three times longer than it is -- the exact failure V56 measured at 3426 ms against
  660 ms.

Run:  PYTHONPATH="$PWD" .venv/bin/python tools/measure_tap_stream.py [--seconds 4]

Opens an audio device, so it is a measurement tool and not something the app calls. Plays a system
sound through the default output while measuring, because a tap over silence cannot distinguish
"working" from "delivering nothing".
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(REPO, "src", "native", "aegis_tap")
CHIME = "/System/Library/Sounds/Submarine.aiff"


def start_helper():
    """Launch the tap helper and return (process, its first JSON line)."""
    if not os.path.exists(HELPER):
        sys.exit(f"helper not built: {HELPER}\n  clang -fobjc-arc -framework Foundation "
                 f"-framework CoreAudio -o {HELPER} {HELPER}.m")
    proc = subprocess.Popen([HELPER], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    line = proc.stdout.readline()
    try:
        info = json.loads(line)
    except json.JSONDecodeError:
        proc.kill()
        sys.exit(f"helper did not emit JSON: {line!r}")
    if not info.get("ok"):
        proc.kill()
        sys.exit(f"helper failed: {info}")
    return proc, info


def find_device(name):
    import sounddevice as sd
    # PortAudio caches its device table at initialisation, and the helper published the device
    # after this process started. Re-initialise or the device is invisible however correct
    # everything else is.
    sd._terminate()
    sd._initialize()
    for index, dev in enumerate(sd.query_devices()):
        if name.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
            return index, dev
    return None, None


def measure(index, rate, seconds):
    """Open at `rate` and report what actually arrived."""
    import numpy as np
    import sounddevice as sd

    frames = {"n": 0, "peak": 0.0}

    def callback(indata, count, time_info, status):
        frames["n"] += count
        peak = float(np.abs(indata).max()) if count else 0.0
        if peak > frames["peak"]:
            frames["peak"] = peak

    try:
        stream = sd.InputStream(device=index, channels=1, samplerate=rate,
                                blocksize=int(rate * 0.03), dtype="float32", callback=callback)
    except Exception as exc:
        return {"requested": rate, "opened": False, "error": f"{type(exc).__name__}: {exc}"}

    with stream:
        started = time.monotonic()
        # Signal, so "no frames" and "frames of silence" stay distinguishable.
        for _ in range(max(1, int(seconds))):
            subprocess.run(["afplay", CHIME], check=False)
        elapsed = time.monotonic() - started
        reported = stream.samplerate

    observed = frames["n"] / elapsed if elapsed else 0.0
    return {
        "requested": rate,
        "opened": True,
        "reported_by_portaudio": reported,
        "observed_frames_per_second": round(observed, 1),
        "ratio_to_requested": round(observed / rate, 3) if rate else None,
        "frames": frames["n"],
        "seconds": round(elapsed, 2),
        "peak": round(frames["peak"], 4),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=4)
    parser.add_argument("--rates", type=int, nargs="+", default=[16000, 48000])
    args = parser.parse_args()

    proc, info = start_helper()
    print(json.dumps({"helper": info}, ensure_ascii=False))
    try:
        index, dev = find_device(info["device_name"])
        visible = index is not None
        print(json.dumps({"V9_visible_cross_process": visible,
                          "device": dev["name"] if visible else None,
                          "default_samplerate": dev["default_samplerate"] if visible else None,
                          "max_input_channels": dev["max_input_channels"] if visible else None},
                         ensure_ascii=False))
        if not visible:
            return 1
        for rate in args.rates:
            print(json.dumps(measure(index, rate, args.seconds), ensure_ascii=False))
    finally:
        proc.send_signal(signal.SIGTERM)
        proc.wait(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
