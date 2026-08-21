"""Queue dwell reporting, and the log-format contract it must not break.

`Transcribed in <ms>ms` starts its clock *after* the worker has already taken the segment off
`inference_queue`, so the time a segment spent waiting is invisible in it. **V66** puts inference
under 20% of the 3.75 s a speaker waits for the first word and **V67** measured contention on that
same minority term, so the remainder has to come from somewhere — this is the instrumentation that
makes it visible.

The regression these tests exist for is not the arithmetic. It is that **five tools parse
`Transcribed in <ms>ms: <text>`** with regexes whose final group is greedy — `measure_dual_track`,
`npu_lock_trial`, `measure_asr_latency`, `soak_capture`, and the harness in
`test_measure_asr_latency`. Appending the new figures to that line would have been the obvious
implementation and would have silently folded them into every captured transcript, corrupting CER
comparisons in a way that still looks like a working measurement.
"""

import logging
import os
import re
import sys
import threading
import time

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

# The exact expressions the tools use, copied rather than imported: if a tool's regex is relaxed
# later, this file should keep testing the contract that shipped with these ones.
PARSERS = {
    "measure_dual_track": re.compile(r"\[(?P<role>[^\]]+)\] Transcribed in\s+(?P<ms>\d+(?:\.\d+)?)\s*ms"),
    "npu_lock_trial": re.compile(r"\[(?P<role>[^\]]+)\] Transcribed in\s+(?P<ms>[\d.]+)\s*ms:\s*(?P<text>.*)"),
    "measure_asr_latency": re.compile(r"Transcribed in\s+(?P<ms>\d+(?:\.\d+)?)\s*ms"),
    "soak_capture": re.compile(
        r"^(?P<time>[\d\-]+ [\d:,]+) .*\[(?P<role>[^\]]+)\] Transcribed in (?P<ms>\d+)ms: (?P<text>.*)$"),
}

SEGMENT_LINE = re.compile(
    r"\[(?P<role>[^\]]+)\] Segment (?P<seg_s>[\d.]+)s: "
    r"queue (?P<queue_ms>\d+)ms, inference (?P<infer_ms>\d+)ms")

# The soak tool's own parser, copied verbatim from tools/soak_capture.py. It deliberately has no
# `$` anchor and stops after `inference`, so fields may be APPENDED to the segment line but never
# inserted between existing ones. That is a cross-tool contract, not an implementation detail:
# breaking it silently changes every band analysis that tool produces.
SOAK_PARSER = re.compile(
    r"^(?P<time>[\d\-]+ [\d:]+),(?P<msec>\d+) .*\[(?P<role>[^\]]+)\] "
    r"Segment (?P<seg>[\d.]+)s: queue (?P<queue>\d+)ms, inference (?P<inf>\d+)ms")

SPLIT_LINE = re.compile(
    r"Segment (?P<seg_s>[\d.]+)s: queue (?P<queue_ms>\d+)ms, inference (?P<infer_ms>\d+)ms, "
    r"lock (?P<lock_ms>\d+)ms, npu (?P<npu_ms>\d+)ms")


def test_segment_line_is_invisible_to_every_transcribed_in_parser():
    line = "[Speaker (You)] Segment 3.04s: queue 812ms, inference 655ms"
    for name, pattern in PARSERS.items():
        assert pattern.search(line) is None, f"{name} would mis-parse the new segment line"


def test_transcribed_in_line_still_parses_and_carries_only_the_text():
    stamped = "2026-08-12 19:05:00,123 [INFO] Transcriber: [Speaker (You)] Transcribed in 655ms: hello world"
    m = PARSERS["npu_lock_trial"].search(stamped)
    assert m and m.group("ms") == "655"
    # The greedy trailing group is why nothing may be appended: it would land in the transcript.
    assert m.group("text") == "hello world"
    m2 = PARSERS["soak_capture"].match(stamped)
    assert m2 and m2.group("text") == "hello world"


@pytest.fixture
def stub_transcriber(monkeypatch):
    """A Transcriber with no model and no device, following test_transcriber_feed_wav's pattern."""
    import transcriber as tr

    monkeypatch.setattr(tr, "NPU_LOCK", threading.Lock())
    monkeypatch.setattr(tr, "resolve_backend", lambda model_path: ("stub", lambda audio: "hello world"))

    class FakeBuffer:
        def __init__(self):
            self.entries = []

        def add_entry(self, role, text):
            self.entries.append((role, text))

    t = tr.Transcriber(device_idx=None, role="Speaker (You)", buffer_instance=FakeBuffer())
    return t


def _run_inference_thread_once(t, payload, timeout=10.0):
    """Drive `_inference_thread` over exactly one queued segment and return the log records."""
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = Capture(level=logging.INFO)
    logger = logging.getLogger("Transcriber")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        t.is_running = True
        thread = threading.Thread(target=t._inference_thread, daemon=True)
        thread.start()
        t.inference_queue.put(payload)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if any("Segment " in r for r in records):
                break
            time.sleep(0.02)
        t.is_running = False
        thread.join(timeout=timeout)
    finally:
        logger.removeHandler(handler)
    return records


def test_dwell_is_reported_and_reflects_the_time_actually_waited(stub_transcriber):
    t = stub_transcriber
    seconds = 2.0
    audio = np.zeros(int(t.sample_rate * seconds), dtype=np.float32)

    # Enqueue with a timestamp 0.5 s in the past: the worker must report roughly that, not zero.
    waited = 0.5
    records = _run_inference_thread_once(t, (audio, time.monotonic() - waited))

    segment = next((r for r in records if "Segment " in r), None)
    assert segment is not None, f"no segment line emitted; got {records}"
    m = SEGMENT_LINE.search(segment)
    assert m, f"segment line did not match the documented format: {segment!r}"
    assert float(m.group("seg_s")) == pytest.approx(seconds, abs=0.01)
    # Generous upper bound: this asserts the dwell is measured at all, not a timing guarantee.
    assert 400 <= int(m.group("queue_ms")) <= 2000


def test_segment_line_is_emitted_even_when_the_filter_drops_the_text(monkeypatch, stub_transcriber):
    """The denominator must count every segment, not only the ones that produced a transcript."""
    import transcriber as tr

    monkeypatch.setattr(tr, "is_acceptable", lambda text: False)
    t = stub_transcriber
    audio = np.zeros(int(t.sample_rate * 1.0), dtype=np.float32)

    records = _run_inference_thread_once(t, (audio, time.monotonic()))

    assert any("Segment " in r for r in records), "a filtered segment still costs queue and NPU time"
    assert not any("Transcribed in" in r for r in records)
    assert t.buffer.entries == []


def test_appended_lock_fields_do_not_break_the_soak_parser():
    """The cross-tool contract: append, never insert."""
    stamped = ("2026-08-12 20:31:04,882 [INFO] Transcriber: [Speaker (You)] "
               "Segment 3.04s: queue 0ms, inference 655ms, lock 120ms, npu 535ms")
    m = SOAK_PARSER.match(stamped)
    assert m, "appending lock/npu must leave the soak tool's prefix match intact"
    assert m.group("seg") == "3.04" and m.group("queue") == "0" and m.group("inf") == "655"
    for name, pattern in PARSERS.items():
        assert pattern.search(stamped) is None, f"{name} would mis-parse the segment line"


def test_lock_wait_is_measured_when_the_accelerator_is_already_held(stub_transcriber):
    """The whole point: waiting for the lock is its own number, not inferred from a label."""
    import transcriber as tr

    t = stub_transcriber
    audio = np.zeros(int(t.sample_rate * 1.0), dtype=np.float32)

    held = threading.Event()
    release = threading.Event()

    def hog():
        with tr.NPU_LOCK:
            held.set()
            release.wait(timeout=10)

    blocker = threading.Thread(target=hog, daemon=True)
    blocker.start()
    assert held.wait(timeout=5), "could not acquire the lock to block with"

    threading.Timer(0.4, release.set).start()
    records = _run_inference_thread_once(t, (audio, time.monotonic()))
    blocker.join(timeout=5)

    line = next((r for r in records if "Segment " in r), None)
    assert line is not None, f"no segment line emitted; got {records}"
    m = SPLIT_LINE.search(line)
    assert m, f"segment line lacks the lock/npu split: {line!r}"

    lock_ms = int(m.group("lock_ms")); npu_ms = int(m.group("npu_ms"))
    infer_ms = int(m.group("infer_ms"))
    # Blocked for roughly 0.4 s. Generous bounds: this asserts the wait is measured, not its value.
    assert 250 <= lock_ms <= 3000, f"lock wait not captured: {lock_ms} ms"
    # `inference` keeps its historical meaning, so the two parts must reconstruct it.
    assert abs((lock_ms + npu_ms) - infer_ms) <= 2, f"{lock_ms} + {npu_ms} != {infer_ms}"


def test_uncontended_call_reports_no_lock_wait(stub_transcriber):
    """With the lock free, the time belongs to the accelerator, not to waiting for it."""
    t = stub_transcriber
    audio = np.zeros(int(t.sample_rate * 1.0), dtype=np.float32)

    records = _run_inference_thread_once(t, (audio, time.monotonic()))
    line = next((r for r in records if "Segment " in r), None)
    m = SPLIT_LINE.search(line or "")
    assert m, f"segment line lacks the lock/npu split: {line!r}"
    assert int(m.group("lock_ms")) <= 5, "an uncontended call must not report lock wait"
