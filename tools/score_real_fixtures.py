#!/usr/bin/env python3
"""Score ASR candidates against real recorded speech with published ground truth.

The bake-off's speech numbers came from macOS `say`. This scores the same candidates on
`fixtures/asr/real` (CAiRE/ASCEND, built by `tools/fetch_real_fixtures.py`), where the `mixed`
clips are **intra-sentence** Mandarin-English code-switching -- the case REQUIREMENTS records as
weak in every candidate, and the case R8 is actually about.

Metric is **CER over a normalised string**: case folded, whitespace and punctuation removed, so a
Chinese character and an English word are compared on the same footing. That is harsher on English
than word error rate would be, but it is applied identically to every candidate, so the ranking is
comparable even though the absolute number is not the WER anyone else publishes. Do not quote
these figures against a leaderboard; quote them against each other.

R37 is **not** measured here and cannot be: no speech corpus contains the non-speech this product
must stay silent through. That stays with the synthesized fixtures.
"""

import argparse
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import asr_bakeoff as harness  # noqa: E402

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
REFS = os.path.join(FIXTURE_ROOT, "real", "refs.tsv")

_PUNCT = "。，、！？；：「」『』（）《》〈〉…—·.,!?;:'\"()[]{}<>-_/\\|`~@#$%^&*+= \t\n\r"


def normalise(text):
    """Case fold and drop punctuation and whitespace. Nothing else -- no script conversion, no
    number normalisation. Both would flatter or punish candidates unevenly (R10 is observational
    here, not a scoring axis)."""
    return "".join(ch for ch in (text or "").lower() if ch not in _PUNCT)


def cer(reference, hypothesis):
    """Levenshtein distance over normalised characters, divided by reference length."""
    ref = normalise(reference)
    hyp = normalise(hypothesis)
    if not ref:
        return None
    previous = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        current = [i]
        for j, h in enumerate(hyp, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (r != h)))
        previous = current
    return previous[-1] / len(ref)


def load_refs():
    rows = []
    with open(REFS, encoding="utf-8") as handle:
        next(handle)
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) == 4:
                rows.append({"path": parts[0], "language": parts[1],
                             "duration": float(parts[2]), "reference": parts[3]})
    return rows


def score(label, model_id, kind, qwen_backend, rows):
    try:
        transcribe = harness.make_transcribe_fn(kind, model_id, qwen_backend)
    except Exception as exc:
        return {"candidate": label, "status": f"init failed: {exc}"}

    per_lang = {}
    latencies = []
    samples = []
    with harness.ResourceSampler() as sampler:
        for row in rows:
            wav = os.path.join(FIXTURE_ROOT, row["path"])
            audio, _sr = harness.load_wav_mono_float32(wav)
            start = time.perf_counter()
            try:
                text = transcribe(audio)
            except Exception as exc:
                text = ""
                print(f"   err {row['path']}: {exc}", file=sys.stderr)
            latencies.append((time.perf_counter() - start) * 1000.0)
            value = cer(row["reference"], text)
            if value is not None:
                per_lang.setdefault(row["language"], []).append(value)
            if len(samples) < 3 and row["language"] == "mixed":
                samples.append((row["reference"], text))

    result = {"candidate": label, "status": "ok", "resources": sampler.summary(),
              "latency_median_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0.0,
              "samples": samples}
    for lang, values in per_lang.items():
        result[f"cer_{lang}"] = sum(values) / len(values)
        result[f"n_{lang}"] = len(values)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="substring filter on candidate labels")
    parser.add_argument("--hf-home", default="", help="weight cache for this run")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--include-disqualified", action="store_true",
                        help="Also score the candidates R50 rules out on provenance "
                             "(docs/decisions/0012)")
    args = parser.parse_args()

    if not os.path.exists(REFS):
        print(f"No {os.path.relpath(REFS, REPO_ROOT)}. Run tools/fetch_real_fixtures.py first.",
              file=sys.stderr)
        return 2

    harness._boot_hf_home(args.hf_home, offline=not args.allow_download)
    qwen_backend = harness.resolve_qwen_backend()
    rows = load_refs()
    counts = {}
    for row in rows:
        counts[row["language"]] = counts.get(row["language"], 0) + 1
    print(f"Real fixtures: {len(rows)} clips {counts}")

    candidates = list(harness.WHISPER_CANDIDATES)
    if args.include_disqualified:
        print(f"Including disqualified candidates: {harness.DISQUALIFIED_REASON}")
        candidates += list(harness.QWEN_CANDIDATES)
    if args.only:
        wanted = [w.strip().lower() for w in args.only.split(",") if w.strip()]
        candidates = [c for c in candidates if any(w in c[0].lower() for w in wanted)]

    results = []
    for label, model_id, kind in candidates:
        print(f"== {label} ==")
        result = score(label, model_id, kind, qwen_backend, rows)
        results.append(result)
        if result["status"] != "ok":
            print(f"   {result['status']}")
            continue
        print("   " + "  ".join(
            f"CER({lang}) {result.get(f'cer_{lang}', float('nan')):.3f}"
            for lang in ("mixed", "zh", "en") if f"cer_{lang}" in result
        ) + f"   median {result['latency_median_ms']:.0f} ms"
            f"   peak MLX {result['resources'].get('mlx_peak_mb', 0):.0f} MB"
            f"   (RSS {result['resources']['rss_peak_mb']:.0f} MB — see V55)")

    header = [
        "| Candidate | CER mixed (R8) | CER zh | CER en | Latency median (ms) | Peak MLX (MB) | Peak RSS (MB) |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        if result["status"] != "ok":
            header.append(f"| {result['candidate']} | — | — | — | — | — | — |")
            continue
        header.append(
            f"| {result['candidate']} | "
            + " | ".join(f"{result.get(f'cer_{lang}', float('nan')):.3f}"
                         for lang in ("mixed", "zh", "en"))
            + f" | {result['latency_median_ms']:.0f} "
            f"| {result['resources'].get('mlx_peak_mb', 0):.0f} "
            f"| {result['resources']['rss_peak_mb']:.0f} |"
        )
    table = "\n".join(header)
    print()
    print(table)

    if not args.no_write:
        body = "\n".join([
            "# Real-speech scoring (CAiRE/ASCEND)",
            "",
            f"- When (UTC): {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
            f"- Clips: {len(rows)} {counts}",
            "- Metric: CER over case-folded, punctuation-stripped text. Comparable between the rows"
            " below; **not** comparable with published WER.",
            "- `mixed` is intra-sentence code-switching — the R8 case.",
            "- R37 is not measurable on a speech corpus and is not attempted here.",
            "",
            "## Toolchain (V53)",
            "",
            "```",
            *harness.toolchain_fingerprint(),
            "```",
            "",
            table,
            "",
            "## Sample mixed transcripts",
            "",
        ])
        for result in results:
            if result["status"] != "ok":
                continue
            body += f"\n### {result['candidate']}\n"
            for reference, hypothesis in result.get("samples", []):
                body += f"- ref: `{reference}`\n  hyp: `{hypothesis}`\n"
        path = harness.write_results(body, FIXTURE_ROOT)
        print(f"\nWrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
