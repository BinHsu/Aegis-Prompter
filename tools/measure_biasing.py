#!/usr/bin/env python3
"""Does decoder biasing still recover rare proper nouns, now that the mechanism has changed?

**V59** measured this on the ASR backend that shipped until 2026-08-17: that package took a
`context=` vocabulary list, and biasing took rare terms from **1 recovered of 11** to **9 of 11**
while flipping one English sentence into mixed Chinese (**R38**). `docs/decisions/0012` replaced
the backend on provenance (**R50**), and Whisper has no `context=`. Its nearest equivalent is
`initial_prompt`, and **it is not the same mechanism**:

- `context=` conditioned the decoder on a vocabulary.
- `initial_prompt` is *prepended text*. The decoder continues from it, so it transfers **style as
  well as vocabulary** — and it is text the model can copy out verbatim, which is a false-line
  source (**R37**). This is why biasing lives in the re-listening pass and not the live one.

So **V59's numbers cannot be carried over**, and the arm that would have been invisible under the
old mechanism is the one this tool exists to expose: prompt *shape*. Observed on 2026-08-17 while
verifying the swap — the same audio, biased with a bare comma-separated list, came back with the
punctuation stripped out of it. If that reproduces, the way `relisten.vocabulary_from` renders its
output is a product decision and not a formatting detail, because the re-listened transcript is
read by a person and by the post-meeting agent.

**Arms**, each differing from the one before by a single variable:

    none         no prompt at all — the control
    list         the vocabulary as a bare comma-separated list, which is what `vocabulary_from`
                 produces today
    sentence     the same terms inside a punctuated sentence
    decoys       the list arm plus terms that are NOT in the audio, which is the realistic case:
                 a vocabulary harvested from a whole meeting is mostly irrelevant to any one
                 segment, and a decoder that copies from its prompt will insert them

**What would refute the hypothesis that biasing is worth keeping:** the `list` and `sentence` arms
recover no more rare terms than `none`, or the `decoys` arm inserts terms that were never spoken.
Either outcome argues for dropping biasing from the re-listening pass rather than porting it.

⚠️ Synthesized speech (macOS `say`), for the reason **V59** gives: the effect needs rare proper
nouns that no available corpus contains. It verifies the mechanism and its failure modes; the
magnitudes are not product numbers. The sentences here are **not** V59's — those lived in a
scratch directory that no longer exists — so the counts are not comparable with V59's, only the
directions are.

Run:
    PYTHONPATH="$PWD" .venv/bin/python tools/measure_biasing.py
"""

import argparse
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import asr_bakeoff as harness  # noqa: E402
from asr_eval import load_wav_mono_float32  # noqa: E402

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
CLIP_DIR = os.path.join(FIXTURE_ROOT, "biasing")

# English-framed sentences carrying Taiwanese place names, an organisation and a person's name --
# the shape a hearing actually produces, and the shape V59 found the failure in. `TERMS` is what
# counts as recovered; matching is case-insensitive and whitespace-insensitive so a correct term
# is not scored wrong for capitalisation.
CLIPS = [
    ("hualien_hearing",
     "The Hualien County procurement for the Chungtan substation was reviewed last Tuesday.",
     ["Hualien", "Chungtan"]),
    ("kaohsiung_coating",
     "Kaohsiung Chungtan Industrial applied a Vantablack coating to the housing.",
     ["Kaohsiung", "Chungtan", "Vantablack"]),
    ("legislator_question",
     "Legislator Wang Chu-chen questioned the Taoyuan precinct procurement in committee.",
     ["Wang Chu-chen", "Taoyuan"]),
    ("agency_budget",
     "The Hsinchu Science Park Bureau returned the Miaoli budget line for revision.",
     ["Hsinchu", "Miaoli"]),
    ("vendor_award",
     "Aegis Prompter was awarded the Yilan interpretation contract without objection.",
     ["Aegis Prompter", "Yilan"]),
]

# Present in no clip. A decoder that copies from its prompt will emit these, and that is the
# failure worth catching -- a harvested vocabulary is mostly decoys with respect to any one
# segment.
DECOYS = ["Pingtung", "Keelung", "Nantou", "Changhua", "Taitung"]

CJK = re.compile(r"[一-鿿]")


def all_terms():
    seen = []
    for _name, _text, terms in CLIPS:
        for term in terms:
            if term not in seen:
                seen.append(term)
    return seen


def build_clips(force=False):
    """Synthesize the clips with macOS `say`. Returns [(name, wav_path, text, terms)]."""
    from gen_asr_fixtures import write_speech_clip

    os.makedirs(CLIP_DIR, exist_ok=True)
    built = []
    for name, text, terms in CLIPS:
        path = os.path.join(CLIP_DIR, f"{name}.wav")
        if force or not os.path.exists(path):
            mode = write_speech_clip(path, text, "Samantha")
            if mode != "say":
                print(f"  !! {name}: macOS `say` unavailable — this run measures a beep, not "
                      f"speech. Stop and read the warning in the docstring.", file=sys.stderr)
        built.append((name, path, text, terms))
    return built


def prompts_for(terms):
    """One prompt per arm. `None` means no prompt at all, not an empty string."""
    listed = ", ".join(terms)
    return {
        "none": None,
        "list": listed,
        "sentence": f"The following names are mentioned: {listed}.",
        "decoys": ", ".join(terms + DECOYS),
    }


def recovered(text, terms):
    flat = re.sub(r"\s+", " ", (text or "")).lower()
    return [t for t in terms if re.sub(r"\s+", " ", t).lower() in flat]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    parser.add_argument("--hf-home", default=os.path.join(REPO_ROOT, ".hf_cache-bakeoff"))
    parser.add_argument("--force-build", action="store_true")
    parser.add_argument("--out", default=os.path.join(FIXTURE_ROOT, "results", "biasing.json"))
    args = parser.parse_args()

    clips = build_clips(args.force_build)
    harness._boot_hf_home(args.hf_home, offline=True)

    import numpy as np
    import mlx_whisper
    from score_real_fixtures import cer
    from transcriber import NPU_LOCK

    def transcribe(audio, prompt):
        with NPU_LOCK:
            result = mlx_whisper.transcribe(
                audio, path_or_hf_repo=args.model, fp16=True, no_speech_threshold=0.6,
                condition_on_previous_text=False, initial_prompt=prompt)
        return (result.get("text") or "").strip()

    terms = all_terms()
    prompts = prompts_for(terms)
    print(f"model={args.model}")
    print(f"{len(clips)} clips, {len(terms)} rare terms, {len(DECOYS)} decoys")
    for arm, prompt in prompts.items():
        print(f"  arm {arm:<9} prompt={prompt!r}")
    print()

    rows = []
    for arm, prompt in prompts.items():
        got, total, cers, flips, injected, unpunctuated = [], 0, [], 0, set(), 0
        outputs = []
        for name, path, text, clip_terms in clips:
            samples, _sr = load_wav_mono_float32(path)
            audio = np.asarray(samples, dtype=np.float32)
            hypothesis = transcribe(audio, prompt)
            outputs.append((name, hypothesis))
            hits = recovered(hypothesis, clip_terms)
            got.extend(hits)
            total += len(clip_terms)
            value = cer(text, hypothesis)
            if value is not None:
                cers.append(value)
            # R38: an English sentence must not come back in Chinese.
            if CJK.search(hypothesis):
                flips += 1
            for decoy in DECOYS:
                if decoy.lower() in hypothesis.lower():
                    injected.add(decoy)
            if hypothesis and not hypothesis.rstrip().endswith((".", "!", "?", "。", "！", "？")):
                unpunctuated += 1

        row = {
            "arm": arm, "prompt": prompt,
            "recovered": len(got), "recoverable": total,
            "cer": sum(cers) / len(cers) if cers else None,
            "language_flips": flips,
            "decoys_injected": sorted(injected),
            "unpunctuated_clips": unpunctuated,
            "outputs": outputs,
        }
        rows.append(row)
        print(f"== {arm}")
        print(f"   rare terms recovered {row['recovered']}/{row['recoverable']}   "
              f"CER {row['cer']:.4f}   R38 flips {flips}/{len(clips)}   "
              f"decoys inserted {row['decoys_injected'] or 'none'}   "
              f"unpunctuated {unpunctuated}/{len(clips)}")
        for name, hypothesis in outputs:
            print(f"     [{name}] {hypothesis}")
        print(flush=True)

    print("| Arm | Rare terms recovered | CER | R38 flips | Decoys inserted | Unpunctuated |")
    print("|---|---|---|---|---|---|")
    for row in rows:
        print(f"| {row['arm']} | {row['recovered']}/{row['recoverable']} | "
              f"{row['cer']:.4f} | {row['language_flips']}/{len(clips)} | "
              f"{', '.join(row['decoys_injected']) or '—'} | "
              f"{row['unpunctuated_clips']}/{len(clips)} |")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"model": args.model, "arms": rows}, handle, ensure_ascii=False, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
