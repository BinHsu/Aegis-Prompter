#!/usr/bin/env python3
"""Does a second track actually slow inference, or does the label just select slow segments?

**Superseded by design, and say so before using it.** `elapsed_ms` conflates lock wait with
inference, so "contended" here means two *elapsed* windows overlapped -- not that either segment was
blocked. Once lock wait is timed separately (two timestamps around `with NPU_LOCK` in
`transcriber.py`), contention is a measured term and none of the correction below is needed. This
exists to reproduce the 2026-08-12 numbers and to control the confounds while that is still true.

**Why any labelled split needs correcting.** Marking a segment contended requires its window to
intersect another role's, and a longer window is mechanically likelier to intersect one. So
conditioning on contention selects long segments, and inference scales with length (**V66**:
715 / 1076 / 1790 ms for 3.03 / 6.76 / 15.0 s). Two controls, applied in order:

  1. **Duration bands.** Compare within comparable segment lengths. Requires the `Segment <s>s:`
     field, which is why V67's log cannot be re-analysed -- it predates the logging.
  2. **Density core.** Within a band, sparse audio infers faster than dense audio, and in a
     correlated two-track run solo segments are disproportionately fragments and room tone. Measured
     on the 2026-08-12 hour: **76 of 570 solo segments (13%) had their text filtered out against 10
     of 1132 contended (1%)**, so the association is real. Restricting both groups to the
     interquartile core of chars-per-second removes it.

**What it found, on 1702 segments across three staged soaks** (`tools/soak_capture.py --microphone`,
3 + 10 + 60 min, one audio stream reaching both tracks -- microphone hearing the speakers):

    naive split                      1.47x
    length-matched                   1.26x
    length- and density-matched      1.15x

Each control shrinks it and none kills it. **The corrected ratio is not flat: it rises with segment
duration, 1.03x below one second to 1.55x above 4.5 s.** An earlier reading of 317 segments called
it flat across a 12x range; that was a small-sample artifact and is withdrawn. The trend is what the
label predicts -- a long window spans more of the partner's activity, so it accumulates more real
waiting, while a short window can overlap only at the margin -- which is one more reason the direct
measurement retires this whole line of argument rather than refining it.

**Do not compare the output with V56, V57, V58 or V67.** Those fed WAVs to two transcribers; this
reads a soak in which the microphone hears the speakers, so both tracks carry one audio stream and
collide 66% of the time against 16.8% in the ASCEND fixture. One stream arriving twice is not two
people taking turns.

Run:  .venv/bin/python tools/analyze_soak_contention.py <soak-stdout-or-log> [more...]
"""

import os
import re
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import soak_capture  # noqa: E402  -- one definition of contention, shared with the soak's report

BANDS = [(0, 1), (1, 2), (2, 3), (3, 4.5), (4.5, 99)]
DRAWS = 200
# Fixed: an unseeded permutation cannot be reproduced, and a number nobody can recompute is not
# evidence. The generator is a plain LCG for the same reason -- no dependency, no platform drift.
SEED = 20260812

ACCEPTED = re.compile(r"\[(?P<role>[^\]]+)\] Transcribed in (?P<ms>\d+)ms: (?P<text>.*)$")


def attach_accepted_text(paths, segments):
    """Pair each segment with the text that survived the filter, or None.

    `transcriber.py` emits `Transcribed in <ms>ms: <text>` immediately after the `Segment ...` line
    it belongs to, same role, same millisecond count, and emits nothing when the filter drops the
    text. Pairing by *order within role* would therefore silently shift every subsequent segment's
    text by one as soon as a single one is dropped, so match on adjacency plus role plus ms.
    """
    index = 0
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as handle:
            pending = None
            for raw in handle:
                if soak_capture.SEGMENT_LINE.match(raw.strip()):
                    pending = segments[index]
                    pending["text"] = None
                    index += 1
                    continue
                m = ACCEPTED.search(raw)
                if m and pending is not None and m.group("role") == pending["role"] \
                        and int(m.group("ms")) == pending["inf"]:
                    pending["text"] = m.group("text").strip()
                    pending = None
    return segments


def median_ratio(segments, key="inf"):
    con = [s[key] for s in segments if s["contended"]]
    solo = [s[key] for s in segments if not s["contended"]]
    if len(con) < 3 or len(solo) < 3:
        return None
    return statistics.median(con) / statistics.median(solo)


def relabelled_after_shift(segments, shift, role):
    """Contention labels after moving one role's windows, wrapping inside the run's own span.

    Preserves every window's length and each role's internal spacing -- so the length-selection
    effect survives -- and randomises only cross-role coincidence. In a correlated run it also
    destroys a *content* association, which is why the null it produces is not purely a length null
    and the resulting p-value overstates the contention effect specifically.
    """
    lo = min(s["inf_start"] for s in segments)
    span = max(s["end"] for s in segments) - lo
    moved = []
    for s in segments:
        start = lo + ((s["inf_start"] - lo + (shift if s["role"] == role else 0.0)) % span)
        moved.append({"role": s["role"], "inf": s["inf"], "seg": s["seg"],
                      "inf_start": start, "end": start + s["inf"] / 1000.0})
    return soak_capture.mark_contended(moved)


def band_table(segments, title, keep=None):
    print(f"\n### {title}\n")
    print("| band | n solo | n contended | solo inference | contended inference | ratio |")
    print("|---|---|---|---|---|---|")
    ratios = []
    for lo, hi in BANDS:
        rows = [s for s in segments if lo <= s["seg"] < hi and (keep is None or keep(s))]
        solo = [s for s in rows if not s["contended"]]
        con = [s for s in rows if s["contended"]]
        if len(solo) < 3 or len(con) < 3:
            continue
        ratio = statistics.median(s["inf"] for s in con) / statistics.median(s["inf"] for s in solo)
        ratios.append((ratio, len(rows)))
        print(f"| {lo}–{hi if hi < 99 else '∞'} s | {len(solo)} | {len(con)} "
              f"| {statistics.median(s['inf'] for s in solo):.0f} ms "
              f"| {statistics.median(s['inf'] for s in con):.0f} ms | **{ratio:.2f}x** |")
    if not ratios:
        print("\n**No band has 3 in both groups.** Report that rather than a number: this load shape "
              "cannot answer the question at any duration, and more minutes will not fix it.")
        return None
    pooled = sum(r * n for r, n in ratios) / sum(n for _, n in ratios)
    print(f"\npooled over {len(ratios)} band(s), weighted by n: **{pooled:.2f}x**")
    return pooled


def main(paths):
    segments = soak_capture.mark_contended(soak_capture.parse_segments(
        line for path in paths for line in open(path, encoding="utf-8", errors="replace")))
    if not segments:
        sys.exit("no `Segment ...: queue Xms, inference Yms` lines found")
    attach_accepted_text(paths, segments)

    con = [s for s in segments if s["contended"]]
    solo = [s for s in segments if not s["contended"]]
    print(f"## {len(segments)} segments from {len(paths)} run(s)\n")
    print(f"- unconditioned median inference: **{statistics.median(s['inf'] for s in segments):.0f} ms**")
    print(f"- naive split: contended {statistics.median(s['inf'] for s in con):.0f} ms (n={len(con)})"
          f" / solo {statistics.median(s['inf'] for s in solo):.0f} ms (n={len(solo)})"
          f" = **{statistics.median(s['inf'] for s in con)/statistics.median(s['inf'] for s in solo):.2f}x**")
    print(f"- median segment duration: contended {statistics.median(s['seg'] for s in con):.2f} s, "
          f"solo {statistics.median(s['seg'] for s in solo):.2f} s "
          f"— any difference here is being read as latency by the naive split")
    for label, rows in (("solo", solo), ("contended", con)):
        dropped = sum(1 for s in rows if not s.get("text"))
        print(f"- {label}: text filtered out on {dropped}/{len(rows)} "
              f"({100*dropped/len(rows):.0f}%) — the sparseness that density has to control for")

    band_table(segments, "Control 1 — matched segment duration")

    withtext = [s for s in segments if s.get("text")]
    if len(withtext) >= 8:
        density = sorted(len(s["text"]) / s["seg"] for s in withtext)
        lo_d = density[len(density) // 4]
        hi_d = density[3 * len(density) // 4]
        print(f"\nkeeping density within [{lo_d:.1f}, {hi_d:.1f}] chars/s, the interquartile core, "
              f"so neither group is represented by its own tail")
        band_table(withtext, "Control 2 — matched duration AND density",
                   keep=lambda s: lo_d <= len(s["text"]) / s["seg"] <= hi_d)

    observed = median_ratio(segments)
    print(f"\n### Permutation null — cross-role coincidence randomised, {DRAWS} draws\n")
    lo = min(s["inf_start"] for s in segments)
    span = max(s["end"] for s in segments) - lo
    # Which role gets shifted must not depend on the order segments happen to arrive in, or the
    # p-value moves when the same runs are passed in a different order. Sorted, not first-seen.
    shifted_role = sorted({s["role"] for s in segments})[0]
    print(f"    shifting {shifted_role!r}")
    state, nulls = SEED, []
    for _ in range(DRAWS):
        state = (1103515245 * state + 12345) % (2 ** 31)
        ratio = median_ratio(relabelled_after_shift(segments, span * state / (2 ** 31), shifted_role))
        if ratio:
            nulls.append(ratio)
    nulls.sort()
    if observed and nulls:
        print(f"    observed                        {observed:.3f}")
        print(f"    null (coincidence randomised)   {statistics.median(nulls):.3f}"
              f"    90% interval {nulls[len(nulls)//20]:.3f} – {nulls[-1-len(nulls)//20]:.3f}")
        print(f"    p(null >= observed)             {sum(1 for n in nulls if n >= observed)/len(nulls):.3f}")
        print("\nRead this as *not zero*, never as the size of the effect: in a correlated run the "
              "shift breaks content association too. The band tables above are the estimate.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__.strip().splitlines()[-1])
    sys.exit(main(sys.argv[1:]))
