#!/usr/bin/env python3
"""Derive the hallucination list from measured output instead of guessing it.

**This is what the field does now, and it answers the objection that emptied our list.**
`HALLUCINATION_PHRASES` was hand-written and was emptied on 2026-08-12 for a good reason: every
entry — `Thank you.`, `謝謝`, `I don't know.`, `Bye.` — is a normal thing to say in *some*
deployment, and **we cannot predict what a forker records**. A list somebody wrote from a subtitle
corpus is a guess about other people's meetings.

A **Bag of Hallucinations** is not a guess. It is built from *this* deployment's own measured
output: strings the model produced **from audio containing no speech**, ranked by how often it
produced them. The published approach filters candidates by log-probability and occurrence
frequency; this uses frequency plus a safety test the literature does not emphasise and this
repository's history demands.

**The safety test: a candidate is rejected if any real speaker produced it.** Every string is
checked against the `control` and `degraded-speech` buckets — real recorded speech, attenuated,
overlapped and obscured. Anything a person actually said is disqualified no matter how often
non-speech produced it. That is the mechanical form of *noise costs a line, a destroyed answer
costs the record* (**V64**).

**Derived on one run, evaluated on another.** Fitting a list to a corpus and then scoring it on
the same corpus measures memorisation. `--derive` and `--evaluate` take different JSONL files —
different process, different day, and for the gated run a different pipeline — so the reported
removal rate is what the list generalises to, not what it memorised.

Run:
    PYTHONPATH="$PWD" .venv/bin/python tools/derive_hallucination_list.py \\
        --derive  fixtures/asr/results/20260817-model-swap/E3_nonspeech_real_turbo.jsonl \\
        --evaluate fixtures/asr/results/20260817-model-swap/E17_shipped_with_gate.jsonl
"""

import argparse
import collections
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from probe_nonspeech_real import bucket_of  # noqa: E402


def load(path):
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def by_bucket(rows, pass_no=0):
    out = collections.defaultdict(list)
    for row in rows:
        if row["pass"] == pass_no and row.get("text"):
            out[bucket_of(row)].append(row["text"])
    return out


def derive(rows, min_count, pass_no=0):
    """Candidate strings, and the real speech that vetoes them."""
    from text_filters import normalize_phrase

    buckets = by_bucket(rows, pass_no)
    spoken = {normalize_phrase(t) for t in buckets["control"] + buckets["degraded-speech"]}
    counts = collections.Counter(normalize_phrase(t) for t in buckets["nonspeech"])

    kept, vetoed = [], []
    for phrase, count in counts.most_common():
        if not phrase:
            continue
        if phrase in spoken:
            vetoed.append((phrase, count))
        elif count >= min_count:
            kept.append((phrase, count))
    return kept, vetoed, len(buckets["nonspeech"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--derive", required=True, help="JSONL to build the list from")
    parser.add_argument("--evaluate", default="", help="a DIFFERENT JSONL to score it on")
    parser.add_argument("--min-count", type=int, default=2,
                        help="Occurrences in non-speech before a string is a candidate. 1 would "
                             "admit every one-off invention, which is the half no list reaches.")
    args = parser.parse_args()

    from text_filters import normalize_phrase, is_acceptable

    kept, vetoed, total = derive(load(args.derive), args.min_count)
    print(f"derived from {os.path.basename(args.derive)}: {total} non-speech lines")
    print(f"  {len(kept)} candidates at >= {args.min_count} occurrences")
    print(f"  {len(vetoed)} rejected because a real speaker said them\n")
    print(f"{'count':>6}  phrase")
    for phrase, count in kept[:25]:
        print(f"{count:>6}  {phrase!r}")
    if vetoed:
        print(f"\n  vetoed by real speech: " + ", ".join(f"{p!r}" for p, _c in vetoed[:8]))

    if not args.evaluate:
        return 0

    listed = {p for p, _c in kept}
    rows = load(args.evaluate)
    buckets = by_bucket(rows)
    print(f"\n=== held out: {os.path.basename(args.evaluate)} ===")
    print(f"| Population | lines | removed by the derived list |")
    print("|---|---|---|")
    for name in ("nonspeech", "degraded-speech", "control"):
        texts = buckets[name]
        hit = sum(1 for t in texts if normalize_phrase(t) in listed)
        if texts:
            print(f"| {name} | {len(texts)} | **{hit}** ({100 * hit / len(texts):.0f}%) |")
    print("\nRemoval on `nonspeech` is the win; anything removed from the other two is the cost,")
    print("and the derivation already vetoed every string a real speaker was recorded producing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
