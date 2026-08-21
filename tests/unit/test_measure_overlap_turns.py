"""Unit tests for tools/measure_overlap_turns.py (tmp_path only).

These pin the two definitions the V67 measurement rests on, both of which are easy to get subtly
wrong and impossible to notice afterwards:

  1. **What counts as cross-track overlap in the fixture** -- a union of speech per track, then the
     intersection. Counting turn *pairs* instead would double-count a turn that overlaps two others,
     and summing per-pair durations would exceed the wall clock.
  2. **What counts as contention** -- two inference windows on *different* roles intersecting.
     `elapsed_ms` starts before `with NPU_LOCK`, so the window is lock-wait plus inference; a line
     is contended when the other track held the lock during part of it.

The second is where a plausible implementation goes wrong quietly: same-role windows must never
count (one track's segments are serial by construction, so they would mark everything), and the
early `break` over start-sorted windows must not skip a later window that still overlaps.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

import measure_overlap_turns as mot  # noqa: E402


# ===== interval algebra =====

def test_merge_unions_overlapping_and_touching_runs():
    assert mot.merge([[0, 1], [0.5, 2], [5, 6]]) == [[0, 2], [5, 6]]
    # Touching at a point is one run, not two: speech does not stop between them.
    assert mot.merge([[0, 1], [1, 2]]) == [[0, 2]]
    # A window entirely inside another must not extend it.
    assert mot.merge([[0, 10], [2, 3]]) == [[0, 10]]
    assert mot.merge([]) == []


def test_intersect_finds_only_genuine_simultaneity():
    assert mot.intersect([[0, 5]], [[3, 8]]) == [[3, 5]]
    # Disjoint tracks produce nothing, whichever order they arrive in.
    assert mot.intersect([[0, 1]], [[2, 3]]) == []
    assert mot.intersect([[2, 3]], [[0, 1]]) == []
    # One long turn spanning several short ones on the other track yields one region per short turn.
    assert mot.intersect([[0, 10]], [[1, 2], [4, 5]]) == [[1, 2], [4, 5]]
    # Touching at a single point is not simultaneous speech.
    assert mot.intersect([[0, 1]], [[1, 2]]) == []


# ===== fixture description =====

def _turns_file(tmp_path, rows):
    path = tmp_path / "turns.tsv"
    lines = ["turn\ttrack\tspeaker\tstart_s\tend_s\tlanguage\tsession\treference"]
    for n, (track, start, end, ref) in enumerate(rows):
        lines.append(f"{n}\t{track}\t1\t{start}\t{end}\ten\t1\t{ref}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def test_load_turns_parses_times_as_floats(tmp_path):
    turns = mot.load_turns(_turns_file(tmp_path, [("A", 0.0, 1.5, "hello")]))
    assert turns[0]["track"] == "A"
    assert turns[0]["start_s"] == 0.0 and turns[0]["end_s"] == 1.5
    assert turns[0]["reference"] == "hello"


def test_describe_fixture_measures_overlap_as_seconds_not_pairs(tmp_path):
    # A speaks 0-10; B speaks 1-2 and 4-5. Two overlapping pairs, but only 2 s of simultaneity.
    path = _turns_file(tmp_path, [
        ("A", 0.0, 10.0, "long turn"),
        ("B", 1.0, 2.0, "interjection"),
        ("B", 4.0, 5.0, "another"),
    ])
    got = mot.describe_fixture(mot.load_turns(path))
    assert got["turns"] == 3
    assert got["per_track"] == {"A": 1, "B": 2}
    assert got["overlap_pairs"] == 2
    assert got["overlap_s"] == 2.0
    assert got["span_s"] == 10.0
    assert got["overlap_pct_of_span"] == 20.0
    # Speech per track is a union, so B's two turns sum rather than merge.
    assert got["speech_s"] == {"A": 10.0, "B": 2.0}


def test_describe_fixture_reports_no_overlap_when_speakers_take_turns(tmp_path):
    path = _turns_file(tmp_path, [
        ("A", 0.0, 1.0, "you first"),
        ("B", 1.0, 2.0, "then me"),
    ])
    got = mot.describe_fixture(mot.load_turns(path))
    assert got["overlap_pairs"] == 0
    assert got["overlap_s"] == 0.0


# ===== contention =====

def _line(t, role, ms):
    return {"t": t, "role": role, "ms": ms, "text": "x"}


def test_contention_requires_two_roles():
    # Both windows are [0.5, 1.0] and [0.9, 1.4] -- they intersect, but on the SAME role. One
    # track's segments are serial by construction, so counting these would mark the whole run.
    windows = mot.label_contention([
        _line(1.0, "Speaker (You)", 500),
        _line(1.4, "Speaker (You)", 500),
    ])
    assert [w["contended"] for w in windows] == [False, False]


def test_contention_marks_both_sides_of_a_cross_role_collision():
    # Speaker occupies [0.0, 1.0]; Participant occupies [0.8, 1.3]. They intersect.
    windows = mot.label_contention([
        _line(1.0, "Speaker (You)", 1000),
        _line(1.3, "Participant", 500),
    ])
    assert all(w["contended"] for w in windows)


def test_solo_lines_are_not_contended_when_windows_do_not_meet():
    # Speaker [0.0, 0.5], Participant [1.0, 1.5] -- different roles, no shared time.
    windows = mot.label_contention([
        _line(0.5, "Speaker (You)", 500),
        _line(1.5, "Participant", 500),
    ])
    assert [w["contended"] for w in windows] == [False, False]


def test_early_break_does_not_miss_a_later_overlapping_window():
    # The regression this guards: windows are scanned in start order and the loop breaks at the
    # first b whose start is past a's end. A long window must still reach the *third* line, whose
    # start is later than the second line's but still inside the long one.
    #   Speaker      [0.0, 5.0]   (t=5.0, ms=5000)
    #   Participant  [1.0, 1.2]   (t=1.2, ms=200)   -- inside
    #   Participant  [4.0, 4.2]   (t=4.2, ms=200)   -- also inside, and after the first
    windows = mot.label_contention([
        _line(5.0, "Speaker (You)", 5000),
        _line(1.2, "Participant", 200),
        _line(4.2, "Participant", 200),
    ])
    assert all(w["contended"] for w in windows), "the long window must reach every line inside it"


def test_zero_length_window_never_contends():
    # A 0 ms line occupies a point; nothing can be simultaneous with it. Guards against an
    # off-by-one that would turn `>=` into `>` and mark touching windows as collisions.
    windows = mot.label_contention([
        _line(1.0, "Speaker (You)", 0),
        _line(1.5, "Participant", 500),
    ])
    assert [w["contended"] for w in windows] == [False, False]


def test_stats_reports_n_median_p95_max():
    assert mot.stats([]) is None
    got = mot.stats([100.0, 200.0, 300.0])
    assert got["n"] == 3 and got["median"] == 200.0 and got["max"] == 300.0
