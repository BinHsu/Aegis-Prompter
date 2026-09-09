#!/usr/bin/env python3
"""Measure what a second capture track costs, without a second capture device.

`STATE.md` lists dual-track latency as blocking the ASR bake-off's close, and it was assumed to
wait on the Core Audio process tap because this machine has no second audio source. It does not:
`Transcriber.feed_wav` already injects a WAV into `audio_queue` exactly where the microphone
callback would, and `start(open_input_stream=False)` runs the pipeline with no device at all. Two
instances fed concurrently reproduce the thing that actually matters -- **both serialize on the
module-level `NPU_LOCK`** (**V33**) -- which is a property of the inference path, not of where the
audio came from.

What this does **not** reproduce: real device timing, the 48 kHz capture rate of the tap
(**V7**), and whether PortAudio resamples (**V12**, still unmeasured and still needing hardware).
The `--sample-rate` option runs the VAD and queueing at 48 kHz to exercise the arithmetic, but the
audio still arrives from a file rather than a device.

Latency comes from the transcriber's own log lines, so it measures the same quantity V51 and V52
did rather than a parallel implementation of the same idea.
"""

import argparse
import logging
import os
import re
import statistics
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
LATENCY_RE = re.compile(r"\[(?P<role>[^\]]+)\] Transcribed in\s+(?P<ms>\d+(?:\.\d+)?)\s*ms")


class LatencyCollector(logging.Handler):
    """Read latencies off the transcriber's own log records, per role."""

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.by_role = {}
        self._lock = threading.Lock()

    def emit(self, record):
        match = LATENCY_RE.search(record.getMessage())
        if not match:
            return
        with self._lock:
            self.by_role.setdefault(match.group("role"), []).append(float(match.group("ms")))

    def summary(self):
        out = {}
        for role, values in self.by_role.items():
            ordered = sorted(values)
            out[role] = {
                "n": len(ordered),
                "median": statistics.median(ordered),
                "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
                "max": ordered[-1],
            }
        return out


def run_arm(model_path, wav_paths, sample_rate, realtime):
    """Feed one WAV per track concurrently and return per-role latency stats."""
    from dialogue_buffer import DialogueBuffer
    from transcriber import Transcriber

    collector = LatencyCollector()
    logging.getLogger("Transcriber").addHandler(collector)

    buffer = DialogueBuffer(max_history=15)
    roles = ["Speaker (You)", "Participant"][: len(wav_paths)]
    transcribers = []
    for role in roles:
        transcriber = Transcriber(role=role, device_idx=None, buffer_instance=buffer,
                                  model_path=model_path)
        if sample_rate != transcriber.sample_rate:
            transcriber.sample_rate = sample_rate
            transcriber.block_size = int(sample_rate * 0.03)
        transcribers.append(transcriber)

    for transcriber in transcribers:
        transcriber.start(open_input_stream=False)

    started = time.time()
    threads = []
    for transcriber, wav in zip(transcribers, wav_paths):
        thread = threading.Thread(target=transcriber.feed_wav, args=(wav,),
                                  kwargs={"realtime": realtime}, daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()

    # Let the inference queue drain before tearing down; stop() waits on NPU_LOCK itself.
    deadline = time.time() + 120
    while time.time() < deadline:
        if all(t.inference_queue.empty() for t in transcribers):
            break
        time.sleep(0.5)
    for transcriber in transcribers:
        transcriber.stop()

    logging.getLogger("Transcriber").removeHandler(collector)
    return collector.summary(), time.time() - started


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/distil-whisper-large-v3")
    parser.add_argument("--wav", default=os.path.join(FIXTURE_ROOT, "speech/en/v52_ten_line_en.wav"))
    parser.add_argument("--second-wav", default="",
                        help="Audio for the Participant track; defaults to the same file")
    parser.add_argument("--sample-rate", type=int, default=16000,
                        help="Run VAD and queueing at this rate. 48000 exercises the arithmetic "
                             "the process tap will need; it does not test PortAudio (V12)")
    parser.add_argument("--fast", action="store_true",
                        help="Feed as fast as the pipeline accepts instead of in real time. "
                             "Maximises NPU_LOCK contention; not a wall-clock simulation")
    parser.add_argument("--hf-home", default="")
    args = parser.parse_args()

    import bootstrap
    if args.hf_home:
        os.environ["HF_HOME"] = os.path.abspath(os.path.expanduser(args.hf_home))
    else:
        bootstrap.apply_environment(bootstrap.read_settings())
    bootstrap.enforce_offline()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    second = args.second_wav or args.wav
    print(f"model={args.model}  rate={args.sample_rate}  realtime={not args.fast}")

    print("\n== single track ==")
    single, single_wall = run_arm(args.model, [args.wav], args.sample_rate, not args.fast)
    print("\n== dual track (both on NPU_LOCK) ==")
    dual, dual_wall = run_arm(args.model, [args.wav, second], args.sample_rate, not args.fast)

    rows = ["", "| Arm | Role | n | median | p95 | max |", "|---|---|---|---|---|---|"]
    for label, stats in (("single", single), ("dual", dual)):
        for role, s in sorted(stats.items()):
            rows.append(f"| {label} | {role} | {s['n']} | {s['median']:.0f} | "
                        f"{s['p95']:.0f} | {s['max']:.0f} |")
    print("\n".join(rows))

    single_all = [v for s in single.values() for v in [s["median"]]]
    dual_all = [v for s in dual.values() for v in [s["median"]]]
    if single_all and dual_all:
        ratio = (sum(dual_all) / len(dual_all)) / (sum(single_all) / len(single_all))
        print(f"\ndual/single median ratio: {ratio:.2f}x   "
              f"wall clock {single_wall:.0f}s -> {dual_wall:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
