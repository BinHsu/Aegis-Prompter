#!/usr/bin/env python3
"""Rescore every stored speaker-leak run with a micro-average, from disk. No measurement.

**Why a third statistic.** **V87** replaced a whole-run CER because one early insertion dominated the
single-string alignment. **V96** replaced its bucketed *mean* because CER is edits over reference
characters, so a bucket with a short reference is unbounded -- one bucket scored 41.86 -- and the mean
became that bucket. **V109** then showed the surviving median still spans 0.32-0.70 across ten runs,
so no leakage figure has ever supported two decimal places.

A **micro-average** -- total edit distance divided by total reference characters across buckets -- has
neither failure. It aligns per bucket, so no single early insertion propagates; and it weights each
bucket by how much reference text it actually contains, so a near-silent minute contributes almost
nothing instead of dominating.

**Nothing is re-measured.** The stored JSONs keep every line with its offset, and the reference is
derivable from the fixture, so edits and reference lengths are recoverable: `cer` divides by
`len(normalise(reference))` at the end, so `edits = cer x len(ref)`.

USAGE
    PYTHONPATH="$PWD" .venv/bin/python tools/rescore_leakage_micro.py
"""
import glob
import json
import os
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "tools"))

from score_real_fixtures import cer, normalise  # noqa: E402
import measure_speaker_leakage as leak  # noqa: E402


def micro_average(lines, minutes):
    """`(micro, buckets, total_ref_chars)` for one run, or `(None, [], 0)`.

    **Runs from before timestamps were stored cannot be done at all**, and that is a real limit
    rather than a quirk of this script. The earliest runs wrote `lines` as a list of strings; the
    tool notes at its own JSON writer that "the first version stored only the text, so a run could
    not be re-scored in buckets afterwards -- the data to fix the metric had been collected and then
    thrown away". Those runs are reported as skipped rather than silently averaged over fewer
    buckets, because a table that quietly drops rows is how a shrinking sample becomes invisible.
    """
    if lines and not isinstance(lines[0], dict):
        return None, [], -1
    edits_total = 0.0
    ref_total = 0
    buckets = []
    for start in range(0, int(minutes * 60), 60):
        ref = leak.bucket_reference(start, start + 60)
        hyp = " ".join(entry["text"] for entry in lines
                       if start <= entry["at"] < start + 60)
        ratio = cer(ref, hyp)
        if ratio is None:
            continue
        n_ref = len(normalise(ref))
        edits_total += ratio * n_ref
        ref_total += n_ref
        buckets.append((ratio, n_ref))
    if not ref_total:
        return None, buckets, 0
    return edits_total / ref_total, buckets, ref_total


def main():
    paths = sorted(glob.glob(os.path.join(
        REPO, "fixtures", "asr", "results", "*-overnight", "leakage_*min.json")))
    if not paths:
        sys.exit("no stored leakage runs found")
    print(f"  {'run':<30}{'n':>3}{'micro':>9}{'median':>9}{'mean':>10}   worst bucket (ratio, ref chars)")
    micros, medians, means, clips, skipped = [], [], [], [], []
    for path in paths:
        data = json.load(open(path, encoding="utf-8"))
        lines = data.get("lines") or []
        minutes = data.get("minutes") or 0
        micro, buckets, ref_total = micro_average(lines, minutes)
        tag = "/".join(path.split(os.sep)[-2:]).replace("-overnight", "").replace("leakage_", "")
        if ref_total == -1:
            print(f"  {tag:<30}  SKIPPED — stored before timestamps existed, cannot be bucketed")
            skipped.append(tag)
            continue
        if micro is None:
            continue
        ratios = [r for r, _ in buckets]
        med = statistics.median(ratios)
        mean = sum(ratios) / len(ratios)
        worst = max(buckets, key=lambda b: b[0])
        print(f"  {tag:<30}{len(buckets):>3}{micro:>9.4f}{med:>9.4f}{mean:>10.4f}"
              f"   {worst[0]:.2f} on {worst[1]} chars")
        clip = sum(min(r, 1.0) for r in ratios) / len(ratios)
        micros.append(micro); medians.append(med); means.append(mean); clips.append(clip)

    def spread(name, values):
        print(f"  {name:<10}{min(values):>8.3f} - {max(values):<8.3f} spread {max(values)-min(values):.3f}")

    print(f"\n  scored {len(micros)} runs; skipped {len(skipped)} for lacking timestamps"
          + (f" ({', '.join(skipped)})" if skipped else ""))
    print("  across runs:")
    spread("micro", micros)
    spread("median", medians)
    spread("clipped", clips)
    spread("mean", means)
    print("\n  **The micro-average is refuted as an improvement, and V109's reasoning for it was")
    print("  wrong.** It assumed the pathology was SHORT references, so weighting by reference length")
    print("  would tame it. But the worst buckets include 6.15 on 232 characters -- a large reference")
    print("  whose hypothesis was seven times longer. Edits scale with the HYPOTHESIS, so weighting by")
    print("  reference characters hands a bad bucket more weight when it has plenty of reference.")
    print("  Bounded statistics are what work: compare the spreads above.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
