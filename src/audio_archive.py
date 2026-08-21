"""Durable per-track WAV capture. stdlib `wave`, a queue, and a writer thread.

Retention is optional and off until the operator arms it (R16). What this module does is make
the kept copy trustworthy once they have: lossless, per-track, never mixed (R2), and honest about
anything it failed to write.

**The shape is taken from the unmerged streaming branch** (`docs/decisions/0006`), which had it
right in three ways that are not obvious and were verified there rather than guessed here:

1. **No file I/O in the audio callback, ever.** The callback hands a block to a queue and
   returns. A disk write in the callback drops frames, which is the invariant `AGENTS.md`
   records from a real failure.
2. **The WAV is finalised before anything waits on the ASR worker.** A `wave` file whose header
   was never rewritten with its final length is a truncated, partly unreadable record -- and
   under R45 a lost record is not recoverable. So the sentinel, the join and the close happen
   while the impatient operator's second Ctrl+C would still find them cheap.
3. **int16 mono, one file per track.** The float32 stream is converted once, in the callback,
   by the same line that feeds VAD -- so the archive is a faithful record of *what the
   transcriber heard*, which is exactly what `docs/decisions/0001` chose when it settled the
   archive at 16 kHz.

**What the branch got wrong and this does not:** it captured unconditionally with no toggle and
no warning, wrote into the repository tree, named files after roles rather than the session, and
recorded no start time -- so the offline merge it fed assumed a shared `t=0` that nothing
established. Every track here records the wall-clock instant its first frame was written, which
is the only thing that turns a transcript timestamp into an offset into a WAV.

**Loss is counted and reported, never silent.** The queue is bounded: an unbounded one turns a
stalled disk into unbounded memory growth in a process that is also holding two ASR models. When
it fills, the block is dropped, logged, and counted into `dropped_blocks`, which reaches the
session record. This system's characteristic failure is reporting success and doing nothing
(`REQUIREMENTS.md`); a retention feature that quietly wrote 40 minutes of a 60-minute hearing
would be the worst possible instance of it.
"""
import datetime
import logging
import os
import queue
import threading
import wave

logger = logging.getLogger("AudioArchive")

# ~30 s of 30 ms blocks. Large enough that a spinning-disk hiccup or a Spotlight pass costs
# nothing, small enough that a genuinely stuck writer cannot grow without bound.
QUEUE_BLOCKS = 1000

SAMPLE_WIDTH_BYTES = 2      # int16
CHANNELS = 1                # never mixed, never stereo -- one file per track (R2)

# `_mic` and `_system`, paired with `history/Meeting_<session_id>.md` by sharing its stem, so the
# cleanup script resolves the trio from one session id plus one configured directory rather than
# by assuming files sit next to each other (R44).
TRACK_MIC = "mic"
TRACK_SYSTEM = "system"


def track_path(archive_dir, session_id, track):
    """Where one track's WAV goes. Pure -- makes no directory and touches no disk."""
    return os.path.join(archive_dir, f"Meeting_{session_id}_{track}.wav")


class TrackWriter:
    """One track, one WAV, one writer thread.

    Not thread-safe for `open`/`close`; `write` is safe from the audio callback and is the only
    method that may be called from it.
    """

    def __init__(self, path, sample_rate, label=""):
        self.path = path
        self.sample_rate = int(sample_rate)
        self.label = label or os.path.basename(path)

        self._queue = queue.Queue(maxsize=QUEUE_BLOCKS)
        self._thread = None
        self._wav = None

        self.frames_written = 0
        self.dropped_blocks = 0
        self.started_at = None      # wall clock of the first frame accepted, not of `open()`
        self.error = ""

    # --- lifecycle ---

    def open(self):
        """Create the file and start the writer. Returns `""` or a reason it could not.

        Failing here is a visible, reported state rather than an exception: the operator is
        mid-Start, capture itself still works, and losing the archive must not lose the meeting
        (R39). What it may never do is proceed while claiming to be recording.
        """
        try:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            self._wav = wave.open(self.path, "wb")
            self._wav.setnchannels(CHANNELS)
            self._wav.setsampwidth(SAMPLE_WIDTH_BYTES)
            self._wav.setframerate(self.sample_rate)
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self._wav = None
            logger.error("❌ [Archive] %s could not be opened: %s", self.path, self.error)
            return self.error

        self._thread = threading.Thread(target=self._writer_loop, daemon=True,
                                        name=f"archive-{self.label}")
        self._thread.start()
        logger.info("💾 [Archive] %s open at %d Hz", self.path, self.sample_rate)
        return ""

    def write(self, block_int16):
        """Hand one block to the writer. Called from the audio callback -- never blocks.

        `block_int16` is a numpy int16 array; only `.tobytes()` is used, so any buffer works.
        """
        if self._wav is None:
            return
        try:
            self._queue.put_nowait(block_int16.tobytes())
        except queue.Full:
            # Counted and logged, never silent. The count reaches the session record so an
            # operator reading it later knows the file is not the whole hearing.
            self.dropped_blocks += 1
            if self.dropped_blocks == 1 or self.dropped_blocks % 100 == 0:
                logger.warning("⚠️ [Archive] %s writer is behind; %d blocks dropped so far",
                               self.label, self.dropped_blocks)

    def close(self, timeout=10.0):
        """Drain, join, and close the file so the header carries its final length.

        Called before anything waits on the ASR worker: a `wave` file closed properly is a
        record, and one killed mid-write is not (R45).
        """
        if self._wav is None:
            return
        self._queue.put(None)          # sentinel; blocking put, because this is not the callback
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("⚠️ [Archive] %s writer did not drain within %.0fs; closing anyway",
                               self.label, timeout)
        try:
            self._wav.close()
        except Exception as exc:
            self.error = self.error or f"close failed: {type(exc).__name__}: {exc}"
            logger.warning("⚠️ [Archive] closing %s failed: %s", self.path, exc)
        self._wav = None
        logger.info("💾 [Archive] %s closed: %.1f s, %d blocks dropped",
                    self.path, self.duration_s, self.dropped_blocks)

    # --- the writer thread ---

    def _writer_loop(self):
        while True:
            block = self._queue.get()
            if block is None:
                return
            if self.started_at is None:
                # The instant the first frame reached disk, not the instant the file was made.
                # A stream can open seconds before it delivers, and a transcript timestamp is
                # only convertible to an offset against the frame clock (decision 0001).
                self.started_at = datetime.datetime.now()
            try:
                self._wav.writeframes(block)
                self.frames_written += len(block) // (SAMPLE_WIDTH_BYTES * CHANNELS)
            except Exception as exc:
                self.error = self.error or f"{type(exc).__name__}: {exc}"
                logger.error("❌ [Archive] write to %s failed: %s", self.path, exc)
                return

    # --- reporting ---

    @property
    def duration_s(self):
        return self.frames_written / float(self.sample_rate) if self.sample_rate else 0.0

    def summary(self):
        """What the session record needs to say afterwards (R45)."""
        frames = self.frames_written
        # 44 bytes of canonical WAV header, plus the PCM payload. Reported rather than stat()ed
        # so the number is available before the file is closed as well as after.
        size = (frames * SAMPLE_WIDTH_BYTES * CHANNELS + 44) if frames else 0
        return {
            "path": self.path,
            "started_at": (self.started_at.isoformat(timespec="milliseconds")
                           if self.started_at else ""),
            "seconds": round(self.duration_s, 2),
            "frames": frames,
            "bytes": size,
            "dropped_blocks": self.dropped_blocks,
            "error": self.error,
        }
