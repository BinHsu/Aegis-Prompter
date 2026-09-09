"""Durable capture: what lands on disk, and what happens when it cannot.

Real files under `tmp_path`, read back with stdlib `wave`. The point of retention is that the
file is still there and still readable a month later, so nothing here asserts against a mock of
the writer -- it asserts against the bytes.
"""
import os
import sys
import threading
import time
import wave

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import audio_archive  # noqa: E402
from audio_archive import TrackWriter, track_path  # noqa: E402

RATE = 16000
BLOCK = 480          # 30 ms, the block the audio callback delivers


def _block(value=1000, size=BLOCK):
    return np.full(size, value, dtype=np.int16)


def _read(path):
    with wave.open(path, "rb") as handle:
        return {
            "channels": handle.getnchannels(),
            "width": handle.getsampwidth(),
            "rate": handle.getframerate(),
            "frames": handle.getnframes(),
            "data": np.frombuffer(handle.readframes(handle.getnframes()), dtype=np.int16),
        }


def _drain(writer, expected_frames, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline and writer.frames_written < expected_frames:
        time.sleep(0.005)


def test_what_goes_in_is_what_comes_out(tmp_path):
    """Lossless, mono, int16, at the rate it was told. A lossy archive has no evidentiary value
    and a wrong rate silently changes every timestamp derived from it."""
    path = str(tmp_path / "one.wav")
    writer = TrackWriter(path, RATE)
    assert writer.open() == ""

    blocks = [_block(v) for v in (100, -100, 32767, -32768)]
    for block in blocks:
        writer.write(block)
    writer.close()

    out = _read(path)
    assert out["channels"] == 1
    assert out["width"] == 2
    assert out["rate"] == RATE
    assert out["frames"] == BLOCK * len(blocks)
    assert np.array_equal(out["data"], np.concatenate(blocks))


def test_the_header_carries_the_final_length_after_close(tmp_path):
    """A `wave` file whose header was never rewritten is a truncated record, and under R45 a lost
    record does not come back. This is what the close-before-anything-slow ordering protects."""
    path = str(tmp_path / "closed.wav")
    writer = TrackWriter(path, RATE)
    writer.open()
    for _ in range(10):
        writer.write(_block())
    writer.close()

    out = _read(path)
    assert out["frames"] == 10 * BLOCK
    # 44-byte canonical header plus the payload, which is what `summary()` reports without stat.
    assert os.path.getsize(path) == 10 * BLOCK * 2 + 44
    assert writer.summary()["bytes"] == os.path.getsize(path)


def test_the_callback_is_never_blocked_by_the_disk(tmp_path):
    """`write` is called from the audio callback. It hands over and returns; it does not wait for
    a thread, a lock it might contend on, or a file."""
    path = str(tmp_path / "fast.wav")
    writer = TrackWriter(path, RATE)
    writer.open()
    try:
        block = _block()
        started = time.perf_counter()
        for _ in range(200):
            writer.write(block)
        elapsed = time.perf_counter() - started
        # 200 blocks is 6 s of audio. Anything near a millisecond each would be a disk write.
        assert elapsed < 0.05, f"write() took {elapsed * 1000:.1f} ms for 200 blocks"
    finally:
        writer.close()


def test_a_full_queue_drops_and_counts_rather_than_blocking_or_lying(tmp_path, monkeypatch):
    """The characteristic failure of this system is reporting success and doing nothing. A
    writer that fell behind and said nothing would produce 40 minutes of a 60-minute hearing
    with a file that looks complete."""
    monkeypatch.setattr(audio_archive, "QUEUE_BLOCKS", 4)
    path = str(tmp_path / "slow.wav")
    writer = TrackWriter(path, RATE)
    writer.open()

    # Wedge the writer thread so the queue genuinely fills.
    held = threading.Event()
    original = writer._wav.writeframes
    monkeypatch.setattr(writer._wav, "writeframes",
                        lambda data: (held.wait(timeout=5.0), original(data))[1])
    try:
        for _ in range(50):
            writer.write(_block())
        assert writer.dropped_blocks > 0
    finally:
        held.set()
        writer.close()

    # And the loss reaches the session record rather than only the log.
    assert writer.summary()["dropped_blocks"] == writer.dropped_blocks


def test_the_start_time_is_the_first_frame_not_the_file_creation(tmp_path):
    """A stream can open seconds before it delivers. Only the frame clock converts a transcript
    timestamp into an offset into the WAV, which is the point of keeping one (decision 0001)."""
    path = str(tmp_path / "late.wav")
    writer = TrackWriter(path, RATE)
    writer.open()
    assert writer.started_at is None, "opening a file is not the same as recording"

    time.sleep(0.05)
    writer.write(_block())
    _drain(writer, BLOCK)
    first = writer.started_at
    assert first is not None

    writer.write(_block())
    _drain(writer, 2 * BLOCK)
    assert writer.started_at == first, "the start time is the first frame, not the latest"
    writer.close()


def test_a_file_that_cannot_be_opened_reports_why_and_does_not_raise(tmp_path):
    """The operator is mid-Start. Losing the archive must not lose the meeting (R39) — but it
    must never continue while claiming to be recording."""
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("occupied", encoding="utf-8")
    writer = TrackWriter(str(blocked / "impossible.wav"), RATE)

    error = writer.open()
    assert error
    assert writer.error == error
    # And it stays inert rather than half-working.
    writer.write(_block())
    writer.close()
    assert writer.frames_written == 0


def test_an_unwritten_track_reports_zero_rather_than_a_plausible_duration(tmp_path):
    path = str(tmp_path / "silent.wav")
    writer = TrackWriter(path, RATE)
    writer.open()
    writer.close()

    summary = writer.summary()
    assert summary["frames"] == 0
    assert summary["seconds"] == 0.0
    assert summary["started_at"] == ""
    assert summary["bytes"] == 0


def test_filenames_pair_with_the_transcript_by_session_id():
    """R44/R45: the cleanup script resolves the trio from one session id plus one configured
    directory, never by assuming files sit next to each other."""
    mic = track_path("/vault/audio", "2026-08-13_101500", audio_archive.TRACK_MIC)
    system = track_path("/vault/audio", "2026-08-13_101500", audio_archive.TRACK_SYSTEM)

    assert mic.endswith("Meeting_2026-08-13_101500_mic.wav")
    assert system.endswith("Meeting_2026-08-13_101500_system.wav")
    assert os.path.dirname(mic) == "/vault/audio"
    # Same stem as `history/Meeting_<session_id>.md`.
    assert "Meeting_2026-08-13_101500" in mic and "Meeting_2026-08-13_101500" in system


def test_two_tracks_are_two_files_and_are_never_mixed(tmp_path):
    """R2. Mixing destroys the role attribution this architecture gets for free."""
    mic = TrackWriter(track_path(str(tmp_path), "S1", audio_archive.TRACK_MIC), RATE)
    system = TrackWriter(track_path(str(tmp_path), "S1", audio_archive.TRACK_SYSTEM), RATE)
    mic.open()
    system.open()
    mic.write(_block(111))
    system.write(_block(222))
    mic.close()
    system.close()

    assert mic.path != system.path
    assert set(_read(mic.path)["data"].tolist()) == {111}
    assert set(_read(system.path)["data"].tolist()) == {222}


# ===== The lifecycle it is attached to =====
#
# `Transcriber` with the backend seam stubbed and no device opened -- the same idiom
# `test_transcriber_feed_wav.py` uses. What is under test is where the tap sits and when the file
# is closed, neither of which a mock of the writer could tell you.

@pytest.fixture
def stub_transcriber(monkeypatch):
    import transcriber as tr

    monkeypatch.setattr(tr, "NPU_LOCK", threading.Lock())
    monkeypatch.setattr(tr, "resolve_backend", lambda model_path: ("stub", lambda audio: ""))

    class _Vad:
        def is_speech(self, buf, sr):
            return False

    def _build(role="Speaker (You)"):
        t = tr.Transcriber(device_idx=None, role=role, buffer_instance=object())
        t.vad = _Vad()
        return t

    return _build


def test_the_archive_is_tapped_upstream_of_voice_detection(stub_transcriber, tmp_path):
    """The constraint that most easily ruins the feature silently. `_processing_thread` discards
    whatever VAD calls non-speech, so a tap downstream of it would lose precisely the VAD
    misjudgements — the material worth going back to verify (R3, R45)."""
    path = str(tmp_path / "upstream.wav")
    t = stub_transcriber()
    t.start(open_input_stream=False, archive_path=path)
    try:
        assert t.archive is not None
        # `_Vad` says nothing is speech, so the pipeline will keep none of this.
        frames = np.zeros((BLOCK, 1), dtype=np.float32)
        frames[:, 0] = 0.5
        for _ in range(5):
            t._audio_callback(frames, BLOCK, None, None)
        _drain(t.archive, 5 * BLOCK)
    finally:
        t.stop()

    out = _read(path)
    assert out["frames"] == 5 * BLOCK, "non-speech must still reach the archive"
    assert np.all(out["data"] != 0)


def test_stopping_closes_the_wav_before_waiting_on_the_npu(stub_transcriber, tmp_path):
    """Ordering taken from the streaming branch and it is not obvious: an impatient second
    Ctrl+C during the NPU wait should still find a closed header (R45)."""
    import transcriber as tr

    path = str(tmp_path / "ordered.wav")
    t = stub_transcriber()
    t.start(open_input_stream=False, archive_path=path)
    frames = np.full((BLOCK, 1), 0.25, dtype=np.float32)
    t._audio_callback(frames, BLOCK, None, None)
    _drain(t.archive, BLOCK)

    order = []
    real_close = t.archive.close
    t.archive.close = lambda *a, **k: (order.append("wav"), real_close(*a, **k))[1]

    class _WatchedLock:
        def __init__(self, inner):
            self._inner = inner

        def acquire(self, timeout=None):
            order.append("npu")
            return self._inner.acquire(timeout=timeout) if timeout else self._inner.acquire()

        def release(self):
            self._inner.release()

    monkeyed = _WatchedLock(threading.Lock())
    saved = tr.NPU_LOCK
    tr.NPU_LOCK = monkeyed
    try:
        t.stop()
    finally:
        tr.NPU_LOCK = saved

    assert order == ["wav", "npu"], f"WAV must be finalised first, got {order}"
    assert _read(path)["frames"] == BLOCK


def test_an_unarmed_session_writes_nothing_and_creates_nothing(stub_transcriber, tmp_path):
    """Retention is off until armed (R16), and off must mean no file rather than an empty one —
    an empty WAV in the archive directory is indistinguishable from a failed recording."""
    t = stub_transcriber()
    t.start(open_input_stream=False)
    try:
        assert t.archive is None
        t._audio_callback(np.zeros((BLOCK, 1), dtype=np.float32), BLOCK, None, None)
    finally:
        t.stop()
    assert list(tmp_path.iterdir()) == []


def test_a_writer_that_cannot_open_leaves_capture_running(stub_transcriber, tmp_path):
    """R39: losing the archive must not lose the meeting. It must also not pretend."""
    blocked = tmp_path / "occupied"
    blocked.write_text("x", encoding="utf-8")

    t = stub_transcriber()
    t.start(open_input_stream=False, archive_path=str(blocked / "nope.wav"))
    try:
        assert t.archive is None, "a failed writer must not be attached"
        assert t.is_running is True
        t._audio_callback(np.zeros((BLOCK, 1), dtype=np.float32), BLOCK, None, None)
        assert t.audio_queue.qsize() == 1, "transcription continues without the archive"
    finally:
        t.stop()
