"""Unit tests for the queue-dwell report in tools/soak_capture.py (no audio, no devices).

The dwell block was added on 2026-08-12 so a soak answers "did anything wait in `inference_queue`"
without a scratch script. Its arithmetic was previously exercised only by the run it summarised,
which is the worst place to discover a parsing bug: an hour of audio has already been spent.

Three things are pinned, each because getting it wrong produces a plausible-looking number:

  1. **The line format.** `queue Xms, inference Yms` is emitted for *every* segment including those
     whose text the filter drops (`transcriber.py`), which is what makes it the honest denominator.
     A regex that also matched `Transcribed in Yms:` would count accepted lines instead.
  2. **Which window contention is read from.** `queue_wait_ms` is enqueue-to-dequeue and `NPU_LOCK`
     is acquired *after* it, so cross-role contention lives in the inference window and never in the
     dwell. Contention must therefore be computed from `[end - inf, end]`, not from the dwell.
  3. **Same-role overlap is not contention.** One worker per role makes a role's segments serial, so
     counting same-role intersections would mark a single busy track as contended with itself.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

import soak_capture as sc  # noqa: E402


def line(clock, role, seg=1.0, queue=0, inference=500):
    return (f"2026-08-12 19:0{clock} [INFO] Transcriber: [{role}] "
            f"Segment {seg:.2f}s: queue {queue}ms, inference {inference}ms")


# ===== parsing =====

def test_parses_role_queue_and_inference_from_a_real_line():
    raw = ("2026-08-12 19:03:10,719 [INFO] Transcriber: [Speaker (You)] "
           "Segment 4.29s: queue 12ms, inference 275ms")
    (seg,) = sc.parse_segments([raw])
    assert seg["role"] == "Speaker (You)"
    assert seg["queue"] == 12
    assert seg["inf"] == 275
    # The window ends when the line is stamped and opens `inference` earlier, to the millisecond.
    assert round(seg["end"] - seg["inf_start"], 3) == 0.275


def test_ignores_the_transcribed_line_so_the_denominator_stays_every_segment():
    raw = ["2026-08-12 19:03:10,719 [INFO] Transcriber: [Participant] Segment 1.00s: "
           "queue 0ms, inference 275ms",
           "2026-08-12 19:03:10,719 [INFO] Transcriber: [Participant] Transcribed in 275ms: hello.",
           "2026-08-12 19:03:11,000 [INFO] SystemAudio: tap published"]
    assert len(sc.parse_segments(raw)) == 1


def test_survives_a_truncated_final_line():
    # A run killed mid-write leaves a partial line; the report must still produce numbers.
    assert sc.parse_segments(["2026-08-12 19:03:10,719 [INFO] Transcriber: [Participant] Segm"]) == []


# ===== contention =====

def test_overlapping_windows_on_different_roles_are_contended():
    # Both stamped at 19:03:10 with 500 ms of inference: the windows are identical, so they collide.
    segs = sc.mark_contended(sc.parse_segments([
        line("3:10,000", "Speaker (You)"), line("3:10,100", "Participant")]))
    assert [s["contended"] for s in segs] == [True, True]


def test_same_role_overlap_is_not_contention():
    # One worker per role: these cannot really coexist, and counting them would mark a single busy
    # track as contended with itself -- which is how a one-track run reports 100% contention.
    segs = sc.mark_contended(sc.parse_segments([
        line("3:10,000", "Participant"), line("3:10,100", "Participant")]))
    assert [s["contended"] for s in segs] == [False, False]


def test_disjoint_windows_are_solo_even_on_different_roles():
    segs = sc.mark_contended(sc.parse_segments([
        line("3:10,000", "Speaker (You)", inference=200),
        line("3:12,000", "Participant", inference=200)]))
    assert [s["contended"] for s in segs] == [False, False]


def test_contention_is_read_from_inference_not_from_the_dwell():
    # Same completion times, so the inference windows are disjoint; only the *queue* windows would
    # overlap. Reading contention off the dwell would call these contended -- and would be measuring
    # a term that cannot contain lock wait, since NPU_LOCK is taken after the dequeue.
    segs = sc.mark_contended(sc.parse_segments([
        line("3:10,000", "Speaker (You)", queue=900, inference=100),
        line("3:11,000", "Participant", queue=900, inference=100)]))
    assert [s["contended"] for s in segs] == [False, False]
