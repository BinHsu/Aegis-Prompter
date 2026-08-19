"""Unit tests for tools/analyze_soak_contention.py (no audio, no devices, no NPU).

One thing here is genuinely easy to get wrong and impossible to notice afterwards: pairing each
`Segment ...` line with the text that survived the filter. `transcriber.py` emits the `Transcribed
in <ms>ms: <text>` line only when `is_acceptable` passes, so pairing the two sequences by position
within a role shifts every later segment's text by one as soon as a single segment is dropped -- and
on the 2026-08-12 hour 76 of 570 solo segments were dropped, which would have mis-paired most of the
run while still producing a plausible density table.

The permutation helper is pinned for the property that makes it a null at all: shifting one role's
timeline must preserve every window's length, or it stops being the same latency distribution.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "tools"))

import analyze_soak_contention as asc  # noqa: E402
import soak_capture  # noqa: E402


def segment_line(clock, role, seg=1.0, queue=0, inference=500):
    return (f"2026-08-12 19:0{clock} [INFO] Transcriber: [{role}] "
            f"Segment {seg:.2f}s: queue {queue}ms, inference {inference}ms")


def accepted_line(clock, role, ms, text):
    return f"2026-08-12 19:0{clock} [INFO] Transcriber: [{role}] Transcribed in {ms}ms: {text}"


def write(tmp_path, lines):
    path = tmp_path / "soak.out"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def parse(path):
    with open(path, encoding="utf-8") as handle:
        return soak_capture.parse_segments(handle)


# ===== pairing text to segments =====

def test_text_attaches_to_the_segment_it_followed(tmp_path):
    path = write(tmp_path, [segment_line("3:10,000", "Participant", inference=275),
                            accepted_line("3:10,000", "Participant", 275, "hello there.")])
    (seg,) = asc.attach_accepted_text([path], parse(path))
    assert seg["text"] == "hello there."


def test_a_dropped_segment_keeps_none_and_does_not_steal_the_next_text(tmp_path):
    # The first segment's text was filtered out, so no `Transcribed` line follows it. Pairing by
    # position within the role would hand it the second segment's text and shift everything after.
    path = write(tmp_path, [segment_line("3:10,000", "Participant", inference=275),
                            segment_line("3:11,000", "Participant", inference=300),
                            accepted_line("3:11,000", "Participant", 300, "second only.")])
    first, second = asc.attach_accepted_text([path], parse(path))
    assert first["text"] is None
    assert second["text"] == "second only."


def test_text_does_not_cross_roles(tmp_path):
    path = write(tmp_path, [segment_line("3:10,000", "Speaker (You)", inference=275),
                            accepted_line("3:10,000", "Participant", 275, "the other track.")])
    (seg,) = asc.attach_accepted_text([path], parse(path))
    assert seg["text"] is None


def test_a_matching_ms_is_required_so_a_later_line_cannot_be_claimed(tmp_path):
    path = write(tmp_path, [segment_line("3:10,000", "Participant", inference=275),
                            accepted_line("3:12,000", "Participant", 999, "different segment.")])
    (seg,) = asc.attach_accepted_text([path], parse(path))
    assert seg["text"] is None


# ===== the permutation null =====

def test_shifting_preserves_every_window_length(tmp_path):
    path = write(tmp_path, [segment_line("3:10,000", "Participant", seg=2.0, inference=600),
                            segment_line("3:11,000", "Speaker (You)", seg=1.0, inference=300)])
    segments = soak_capture.mark_contended(parse(path))
    before = sorted(round(s["end"] - s["inf_start"], 6) for s in segments)
    moved = asc.relabelled_after_shift(segments, 0.37, "Participant")
    assert sorted(round(s["end"] - s["inf_start"], 6) for s in moved) == before


def test_shifting_can_change_the_labels(tmp_path):
    # Two windows that collide as measured must be separable by a shift, or the null is degenerate.
    # The span has to be wide enough to move inside -- hence the distant third segment.
    path = write(tmp_path, [segment_line("3:10,000", "Participant", inference=500),
                            segment_line("3:10,100", "Speaker (You)", inference=500),
                            segment_line("3:20,000", "Participant", inference=500)])
    segments = soak_capture.mark_contended(parse(path))
    assert [s["contended"] for s in segments] == [True, True, False]
    moved = asc.relabelled_after_shift(segments, 5.0, "Participant")
    assert not any(s["contended"] for s in moved)


def test_a_shift_of_exactly_the_span_is_a_no_op(tmp_path):
    # Wrapping is modulo the run's span, so span-sized draws land back on the observed labelling.
    # Harmless over an hour where the span dwarfs any single window; worth pinning so a future
    # shorter-run caller knows the null contains the observed value by construction, not by chance.
    path = write(tmp_path, [segment_line("3:10,000", "Participant", inference=500),
                            segment_line("3:10,100", "Speaker (You)", inference=500)])
    segments = soak_capture.mark_contended(parse(path))
    span = max(s["end"] for s in segments) - min(s["inf_start"] for s in segments)
    moved = asc.relabelled_after_shift(segments, span, "Participant")
    assert [s["contended"] for s in moved] == [s["contended"] for s in segments]


def test_median_ratio_withholds_itself_when_a_group_is_too_small(tmp_path):
    path = write(tmp_path, [segment_line("3:10,000", "Participant", inference=500),
                            segment_line("3:10,100", "Speaker (You)", inference=900)])
    assert asc.median_ratio(soak_capture.mark_contended(parse(path))) is None
