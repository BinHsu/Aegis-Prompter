#!/usr/bin/env python3
"""Can Whisper's decoding thresholds buy back R37, and what does that cost on speech?

**The question this exists to answer, stated so it can come back false.** `docs/decisions/0012`
replaced the ASR model on provenance (**R50**) and inherited a measured regression on the
criterion **REQUIREMENTS** ranks first: `whisper-large-v3-turbo` produces text on **63 of 63**
synthesized non-speech segments where the model it replaced produced none. The live path passes
`no_speech_threshold=0.6` and takes every other `mlx_whisper` default, and nobody has ever
measured whether those defaults are the reason.

Whisper has three gates the previous backend did not have at all, and the product uses one of
them at its stock value:

- **`temperature`** defaults to a *ladder* — `(0.0, 0.2, 0.4, 0.6, 0.8, 1.0)`. A segment whose
  decode fails a threshold is retried at a higher temperature, so the pipeline's answer on hard
  input is a *sampled* one. This is the mechanism behind **V54**: the same command varying
  30-60 of 63. Pinning it to `(0.0,)` makes a failed decode stay failed instead of being resampled
  into something fluent.
- **`logprob_threshold`** and **`no_speech_threshold`** are an **AND**, which is the part that
  reads backwards. `mlx_whisper` skips a segment only when the no-speech probability is above the
  one *and* mean token logprob is below the other. Raising `no_speech_threshold` alone therefore
  does almost nothing; the pair has to move together.
- **`compression_ratio_threshold`** catches the repetition loop, which is a different failure from
  a short invented sentence and needs saying separately.

**A configuration that silences non-speech and damages speech has not won.** So every arm is
scored on both corpora and the table shows both. **R37** ranks above accuracy, but "above" is not
"alone" — **R8** is still a requirement, and a decoder that has been throttled into skipping quiet
real speech fails the product in the way nobody notices until a hearing.

**What would refute the hypothesis:** no arm reaches a materially lower false-line count than the
baseline without a materially worse CER. Recorded before the run so the result cannot be narrated
either way afterwards. "Materially" is the operator's call on the table, not a threshold this
script asserts.

Run:
    PYTHONPATH="$PWD" .venv/bin/python tools/measure_decode_thresholds.py
    PYTHONPATH="$PWD" .venv/bin/python tools/measure_decode_thresholds.py --passes 2 --arms A,C
"""

import argparse
import json
import os
import statistics
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import asr_bakeoff as harness  # noqa: E402
from asr_eval import iter_fixture_wavs, load_wav_mono_float32  # noqa: E402

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")

# One arm per hypothesis, each differing from the baseline in as few parameters as possible so a
# result can be attributed. `A` is what `transcriber.resolve_backend` passes today -- it is the
# control, and it must be re-measured in this process rather than quoted from the bake-off, or a
# toolchain difference would be read as an effect (**V53**).
ARMS = [
    ("A", "production today", {}),
    ("B", "greedy only, no temperature ladder",
     {"temperature": (0.0,)}),
    ("C", "greedy + both gates tightened",
     {"temperature": (0.0,), "no_speech_threshold": 0.3, "logprob_threshold": -0.5}),
    ("D", "greedy + logprob gate only",
     {"temperature": (0.0,), "logprob_threshold": -0.5}),
    ("E", "greedy + gates + repetition gate",
     {"temperature": (0.0,), "no_speech_threshold": 0.4, "logprob_threshold": -0.7,
      "compression_ratio_threshold": 2.0}),
]

BASE_OPTIONS = {
    "fp16": True,
    "no_speech_threshold": 0.6,
    "condition_on_previous_text": False,
}


def make_fn(model_id, overrides):
    """A transcribe callable with the product's options plus this arm's overrides."""
    import numpy as np
    import mlx_whisper
    from transcriber import NPU_LOCK

    options = dict(BASE_OPTIONS)
    options.update(overrides)

    def _run(audio):
        arr = np.asarray(audio, dtype=np.float32)
        with NPU_LOCK:
            result = mlx_whisper.transcribe(arr, path_or_hf_repo=model_id, **options)
        return (result.get("text") or "").strip()

    # Warm once so the first scored call is not paying for the load.
    _run(np.zeros(16000, dtype=np.float32))
    return _run


def nonspeech_segments():
    """Every VAD segment of genuine non-speech, through the product's own segmentation."""
    import numpy as np

    out = []
    for path in iter_fixture_wavs(FIXTURE_ROOT, "nonspeech_real"):
        rel = os.path.relpath(path, FIXTURE_ROOT)
        samples, _sr = load_wav_mono_float32(path)
        audio = np.asarray(samples, dtype=np.float32)
        for idx, chunk in enumerate(harness.vad_speech_segments(audio)):
            out.append((f"{rel}#{idx}", chunk))
    return out


def synthetic_segments():
    """The original 63. Kept as the control that ties this run to every earlier one."""
    import numpy as np

    out = []
    for path in iter_fixture_wavs(FIXTURE_ROOT, "nonspeech"):
        rel = os.path.relpath(path, FIXTURE_ROOT)
        samples, _sr = load_wav_mono_float32(path)
        audio = np.asarray(samples, dtype=np.float32)
        for idx, chunk in enumerate(harness.vad_speech_segments(audio)):
            out.append((f"{rel}#{idx}", chunk))
    return out


def score_arm(transcribe, nonspeech, synthetic, speech_rows, passes):
    """Both corpora through one arm. Returns the row the table is built from.

    **The pooled `nonspeech` count mixes two things and the split is reported alongside it.**
    `fixtures/asr/nonspeech_real/` holds genuine non-speech *and* real speech that has been
    attenuated, overlapped or obscured (`quiet_speech_*`, `babble_*`, `mumble_*`, `crosstalk_*`,
    `filled_pauses`). Text from the second kind is bad transcription, not an invented utterance,
    and **R37** is not about it. The arms are comparable to each other on either count -- they see
    identical audio -- but only the `nonspeech` column can be read against **V60** and **V72**,
    whose denominator is 253.
    """
    from probe_nonspeech_real import DEGRADED_SPEECH_PREFIXES
    from score_real_fixtures import cer
    from text_filters import is_acceptable

    def is_degraded(label):
        return os.path.basename(label.split("#")[0]).startswith(DEGRADED_SPEECH_PREFIXES)

    raw_runs, buffer_runs, synth_runs = [], [], []
    true_raw_runs, true_buffer_runs = [], []
    true_total = sum(1 for label, _c in nonspeech if not is_degraded(label))
    examples = []
    for _pass in range(passes):
        raw = kept = true_raw = true_kept = 0
        for label, chunk in nonspeech:
            text = transcribe(chunk)
            degraded = is_degraded(label)
            if text:
                raw += 1
                if not degraded:
                    true_raw += 1
                if is_acceptable(text):
                    kept += 1
                    if not degraded:
                        true_kept += 1
                    if len(examples) < 12 and not degraded:
                        examples.append((label, text))
        raw_runs.append(raw)
        buffer_runs.append(kept)
        true_raw_runs.append(true_raw)
        true_buffer_runs.append(true_kept)

        synth = sum(1 for _label, chunk in synthetic if transcribe(chunk))
        synth_runs.append(synth)

    per_lang = {}
    latencies = []
    for row in speech_rows:
        wav = os.path.join(FIXTURE_ROOT, row["path"])
        audio, _sr = harness.load_wav_mono_float32(wav)
        started = time.perf_counter()
        text = transcribe(audio)
        latencies.append((time.perf_counter() - started) * 1000.0)
        value = cer(row["reference"], text)
        if value is not None:
            per_lang.setdefault(row["language"], []).append(value)

    result = {
        "nonspeech_total": len(nonspeech),
        "true_nonspeech_total": true_total,
        "synthetic_total": len(synthetic),
        "raw_runs": raw_runs,
        "buffer_runs": buffer_runs,
        "true_raw_runs": true_raw_runs,
        "true_buffer_runs": true_buffer_runs,
        "synth_runs": synth_runs,
        "latency_median_ms": statistics.median(latencies) if latencies else 0.0,
        "examples": examples,
    }
    for lang, values in per_lang.items():
        result[f"cer_{lang}"] = sum(values) / len(values)
    return result


def _range(values):
    """`n` for one observation, `min-max (k runs)` for several. Never a bare mean (**V54**)."""
    if not values:
        return "—"
    if len(set(values)) == 1:
        return f"{values[0]}"
    return f"{min(values)}-{max(values)} ({len(values)} runs)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    parser.add_argument("--passes", type=int, default=2,
                        help="Non-speech passes per arm. Two is the floor for the baseline, "
                             "whose temperature ladder makes a single count a draw (V54)")
    parser.add_argument("--arms", default="", help="Comma list of arm letters, e.g. A,C")
    parser.add_argument("--hf-home", default=os.path.join(REPO_ROOT, ".hf_cache-bakeoff"))
    parser.add_argument("--out", default=os.path.join(FIXTURE_ROOT, "results",
                                                      "decode_thresholds.json"))
    args = parser.parse_args()

    harness._boot_hf_home(args.hf_home, offline=True)
    from score_real_fixtures import load_refs

    wanted = [a.strip().upper() for a in args.arms.split(",") if a.strip()]
    arms = [a for a in ARMS if not wanted or a[0] in wanted]

    nonspeech = nonspeech_segments()
    synthetic = synthetic_segments()
    speech_rows = load_refs()
    print(f"model={args.model}")
    print(f"non-speech segments={len(nonspeech)}  synthetic control={len(synthetic)}  "
          f"speech clips={len(speech_rows)}  passes={args.passes}")
    print(f"arms: {', '.join(a[0] for a in arms)}\n", flush=True)

    results = []
    for letter, description, overrides in arms:
        print(f"== {letter}: {description}  {overrides or '(stock)'}", flush=True)
        started = time.time()
        transcribe = make_fn(args.model, overrides)
        row = score_arm(transcribe, nonspeech, synthetic, speech_rows, args.passes)
        row.update({"arm": letter, "description": description, "overrides": {
            k: list(v) if isinstance(v, tuple) else v for k, v in overrides.items()}})
        results.append(row)
        print(f"   TRUE non-speech (R37, comparable with V60/V72) "
              f"raw {_range(row['true_raw_runs'])}/{row['true_nonspeech_total']}   "
              f"reaching buffer {_range(row['true_buffer_runs'])}")
        print(f"   pooled incl. degraded speech {_range(row['raw_runs'])}/{row['nonspeech_total']}"
              f"   synthetic {_range(row['synth_runs'])}/{row['synthetic_total']}")
        print(f"   CER mixed {row.get('cer_mixed', float('nan')):.3f}  "
              f"zh {row.get('cer_zh', float('nan')):.3f}  "
              f"en {row.get('cer_en', float('nan')):.3f}   "
              f"median {row['latency_median_ms']:.0f} ms   ({time.time() - started:.0f}s)",
              flush=True)

    print("\n| Arm | Decoding | R37 non-speech raw | Reaching buffer | Synthetic 63 | "
          "CER mixed | CER zh | CER en | Median ms |")
    print("|---|---|---|---|---|---|---|---|---|")
    for row in results:
        overrides = ", ".join(f"`{k}={v}`" for k, v in row["overrides"].items()) or "stock"
        print(f"| {row['arm']} — {row['description']} | {overrides} | "
              f"{_range(row['true_raw_runs'])}/{row['true_nonspeech_total']} | "
              f"{_range(row['true_buffer_runs'])} | "
              f"{_range(row['synth_runs'])}/{row['synthetic_total']} | "
              f"{row.get('cer_mixed', float('nan')):.3f} | "
              f"{row.get('cer_zh', float('nan')):.3f} | "
              f"{row.get('cer_en', float('nan')):.3f} | "
              f"{row['latency_median_ms']:.0f} |")

    print("\nR37 ranks above accuracy, but an arm that silences non-speech by refusing to "
          "transcribe quiet speech has not won it — read both halves of the row.")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"model": args.model, "passes": args.passes, "arms": results}, handle,
                  ensure_ascii=False, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
