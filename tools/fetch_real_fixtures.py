#!/usr/bin/env python3
"""Build speech fixtures from a public corpus instead of macOS TTS.

Why this exists: the speech fixtures were `say` output -- no accent, no overlap, no background,
no slurred endings -- which is the weakest possible evidence for the accuracy differences the ASR
choice turns on (STATE 7.2). CAiRE/ASCEND is conversational Mandarin-English, and its `mixed`
split is **intra-sentence** code-switching, which is what R8 is actually about and what
REQUIREMENTS notes every candidate is weak at.

Deliberately does **not** use `datasets`: streaming a sample from it did not return in ten
minutes here, while fetching the same split's parquet directly took six seconds. Fewer moving
parts, and the download lands in the wipeable bake-off cache rather than the product's.

Everything this writes is gitignored and disposable:

    rm -rf fixtures/asr/real

Ground truth is written beside the audio as `refs.tsv`, so a scorer never has to reach the
network or guess what was said.
"""

import argparse
import io
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
REAL_ROOT = os.path.join(FIXTURE_ROOT, "real")
BAKEOFF_CACHE = os.path.join(REPO_ROOT, ".hf_cache-bakeoff")

DATASET = "CAiRE/ASCEND"
SPLIT_FILE = "main/test-00000-of-00001.parquet"
TARGET_SR = 16000


def _resample_linear(samples, src_sr, dst_sr):
    """Linear resample. Adequate here: the clips are already 16 kHz in practice, and this only
    guards against a corpus revision changing that -- it is not the production resample path."""
    import numpy as np

    if src_sr == dst_sr:
        return samples
    duration = len(samples) / float(src_sr)
    dst_n = int(round(duration * dst_sr))
    src_t = np.linspace(0.0, duration, num=len(samples), endpoint=False)
    dst_t = np.linspace(0.0, duration, num=dst_n, endpoint=False)
    return np.interp(dst_t, src_t, samples).astype("float32")


def _write_wav(path, samples):
    import wave

    import numpy as np

    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype("<i2")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(TARGET_SR)
        handle.writeframes(pcm.tobytes())


def fetch(counts, min_s, max_s, seed):
    import random

    import numpy as np
    import pyarrow.parquet as pq
    import soundfile as sf
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(DATASET, SPLIT_FILE, repo_type="dataset", cache_dir=BAKEOFF_CACHE)
    table = pq.read_table(path).to_pydict()

    by_lang = {}
    for idx, lang in enumerate(table["language"]):
        duration = table["duration"][idx]
        if duration is None or not (min_s <= duration <= max_s):
            continue
        by_lang.setdefault(lang, []).append(idx)

    rng = random.Random(seed)
    rows = []
    for lang, want in counts.items():
        pool = by_lang.get(lang, [])
        if not pool:
            print(f"  {lang}: none in {min_s}-{max_s}s", file=sys.stderr)
            continue
        picked = sorted(rng.sample(pool, min(want, len(pool))))
        for n, idx in enumerate(picked):
            blob = table["audio"][idx]["bytes"]
            samples, sr = sf.read(io.BytesIO(blob), dtype="float32", always_2d=False)
            if getattr(samples, "ndim", 1) > 1:
                samples = samples.mean(axis=1)
            samples = _resample_linear(np.asarray(samples, dtype="float32"), sr, TARGET_SR)
            rel = os.path.join("real", lang, f"{lang}_{n:03d}.wav")
            _write_wav(os.path.join(FIXTURE_ROOT, rel), samples)
            rows.append((rel, lang, f"{table['duration'][idx]:.2f}",
                         (table["transcription"][idx] or "").strip()))
        print(f"  {lang}: wrote {len(picked)} of {len(pool)} eligible")

    refs = os.path.join(REAL_ROOT, "refs.tsv")
    os.makedirs(REAL_ROOT, exist_ok=True)
    with open(refs, "w", encoding="utf-8") as handle:
        handle.write("path\tlanguage\tduration_s\treference\n")
        for row in rows:
            handle.write("\t".join(row) + "\n")
    print(f"  refs -> {os.path.relpath(refs, REPO_ROOT)} ({len(rows)} rows)")
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mixed", type=int, default=40,
                        help="intra-sentence code-switch clips (R8)")
    parser.add_argument("--zh", type=int, default=20, help="Mandarin-only clips")
    parser.add_argument("--en", type=int, default=20, help="English-only clips")
    parser.add_argument("--min-seconds", type=float, default=2.0)
    parser.add_argument("--max-seconds", type=float, default=15.0)
    parser.add_argument("--seed", type=int, default=7,
                        help="Fixed so a re-run selects the same clips; record it with results")
    args = parser.parse_args()

    print(f"Fetching from {DATASET} into {os.path.relpath(REAL_ROOT, REPO_ROOT)} "
          f"(seed={args.seed}, {args.min_seconds}-{args.max_seconds}s)")
    fetch({"mixed": args.mixed, "zh": args.zh, "en": args.en},
          args.min_seconds, args.max_seconds, args.seed)


if __name__ == "__main__":
    main()
