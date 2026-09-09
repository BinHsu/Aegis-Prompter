"""WAV feed path for V52 lab inject (no mic device required)."""

import os
import sys
import threading
import time

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

from asr_eval import TARGET_SR, write_wav_mono_int16  # noqa: E402


@pytest.fixture
def tone_wav(tmp_path):
    # ~1.2 s of tone so VAD+min-duration can form a segment if speech-like enough;
    # for queue injection we only assert frames arrive.
    path = tmp_path / "tone.wav"
    samples = [0.2 * np.sin(2 * np.pi * 220 * i / TARGET_SR) for i in range(TARGET_SR)]
    write_wav_mono_int16(str(path), samples)
    return str(path)


def test_feed_wav_enqueues_frames(tone_wav, monkeypatch):
    import transcriber as tr

    # Skip NPU warm-up in __init__. Stub the backend seam rather than a specific package:
    # `transcriber` no longer imports one at module scope, and which family is default is a
    # decision (docs/decisions/0009) that this test has no business depending on.
    monkeypatch.setattr(tr, "NPU_LOCK", threading.Lock())
    monkeypatch.setattr(tr, "resolve_backend", lambda model_path: ("stub", lambda audio: ""))

    class FakeVad:
        def is_speech(self, buf, sr):
            return True

    t = tr.Transcriber(device_idx=None, role="Speaker (You)", buffer_instance=object())
    t.vad = FakeVad()
    t.is_running = True

    # Faster than realtime for the test.
    thread = threading.Thread(target=lambda: t.feed_wav(tone_wav, realtime=False), daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive()

    assert t.audio_queue.qsize() > 0
    chunk, is_speech = t.audio_queue.get_nowait()
    assert is_speech is True
    assert len(chunk) == t.block_size


# ===== realtime pacing =====
#
# `realtime=True` slept a flat frame_s per frame, so per-frame work (RMS, VAD, enqueue) landed on
# top of every sleep instead of inside it and the feed ran permanently slow -- 0.887x measured on
# this machine, which a `--realtime` arm sat exactly on and which was first misdiagnosed as CPU
# starvation (V67). These pin the deadline schedule that replaced it. A fake clock rather than real
# sleeps: the property under test is arithmetic, and timing it for real would be flaky.


class FakeClock:
    """Stands in for the `time` module inside `transcriber`. Work advances it; sleeps advance it."""

    def __init__(self, work_per_frame):
        self.now = 1000.0
        self.work = work_per_frame
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def do_frame_work(self):
        self.now += self.work


def _feed_with_clock(tone_wav, monkeypatch, work_per_frame):
    import transcriber as tr

    monkeypatch.setattr(tr, "NPU_LOCK", threading.Lock())
    monkeypatch.setattr(tr, "resolve_backend", lambda model_path: ("stub", lambda audio: ""))

    clock = FakeClock(work_per_frame)
    monkeypatch.setattr(tr, "time", clock)

    class WorkingVad:
        def is_speech(self, buf, sr):
            clock.do_frame_work()          # the cost the flat sleep used to ignore
            return False                   # no segments: this test is about pacing only

    t = tr.Transcriber(device_idx=None, role="Speaker (You)", buffer_instance=object())
    t.vad = WorkingVad()
    t.is_running = True
    started = clock.now
    t.feed_wav(tone_wav, realtime=True)
    return t, clock, clock.now - started


def test_realtime_pacing_absorbs_per_frame_work_instead_of_adding_it(tone_wav, monkeypatch):
    t, clock, elapsed = _feed_with_clock(tone_wav, monkeypatch, work_per_frame=0.010)
    frame_s = t.block_size / float(t.sample_rate)
    frames = len(clock.sleeps)
    assert frames > 10

    # Every sleep is the REMAINDER of the frame, not the whole frame.
    assert all(abs(s - (frame_s - 0.010)) < 1e-9 for s in clock.sleeps)

    # And the run takes one frame of wall clock per frame of audio. Under the flat sleep this
    # would have been frames * (frame_s + work) -- 1.33x longer at these numbers.
    assert abs(elapsed - frames * frame_s) < frame_s
    assert elapsed < frames * (frame_s + 0.010) - 1e-6


def test_falling_far_behind_resyncs_and_says_so_rather_than_sprinting(tone_wav, monkeypatch, caplog):
    # 1.5 s of work per 30 ms frame: the deadline is unreachable from the first frame. The feed must
    # not sleep a negative remainder, and it must not silently catch up -- feeding as fast as the
    # queue accepts turns a realtime arm into a saturating one, which is the load shape that made
    # every earlier dual-track figure an upper bound (V56).
    with caplog.at_level("WARNING"):
        _t, clock, _elapsed = _feed_with_clock(tone_wav, monkeypatch, work_per_frame=1.5)

    assert clock.sleeps == []                                    # nothing negative, nothing at all
    resyncs = [r for r in caplog.records if "resyncing" in r.getMessage()]
    assert len(resyncs) > 5
    assert "NOT continuous" in resyncs[0].getMessage()
