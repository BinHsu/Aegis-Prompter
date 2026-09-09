# 0008 — The Qwen ASR supply chain is accepted, pinned, and documented for whoever hits it

- **Status:** superseded
- **Superseded by:** [0012](0012-the-asr-model-is-whisper-large-v3-turbo-on-supply-chain-grounds.md)
- **Decided:** 2026-08-11
- **Follows from:** R11, R15, R21, V39, V40, V41, V44

## Context

**V44** recorded that `mlx-qwen3-asr` is a **community reimplementation, not a vendor port** —
Apache-2.0 over Qwen's official weights, published by a single maintainer — and left three options
open: accept the risk, pin and mirror, or disqualify Qwen on supply-chain grounds even if it wins
the measurements. It has now won them: on this repository's fixtures both Qwen sizes produce
**zero** text on 63 non-speech segments where both Whisper candidates produce text on all 63, and
both satisfy **R8** through the production VAD path.

Verified 2026-08-11 rather than recalled:

| | |
|---|---|
| Package | `mlx-qwen3-asr` **0.3.5**, `py3-none-any` |
| Upstream | https://github.com/moona3k/mlx-qwen3-asr |
| Licence | Apache-2.0 |
| Wheel sha256 | `5c7169392a8d06f38ccc791b768cdc9e7fd6038a34130576c2af8b3afa28d06b` |
| Requires | Python >= 3.10 |
| Weights | `Qwen/Qwen3-ASR-0.6B`, `Qwen/Qwen3-ASR-1.7B` — vendor-published, not the port's |

## Decision

**Accept the supply-chain risk, on the operator's stated reasoning, subject to one condition.**

The reasoning, recorded because it is not obvious and a future reader will otherwise re-open this:
**a product that runs offline forever does not depend on the package being maintained.** An
abandoned dependency is a liability for a service that must keep pace with a moving world; it is
close to inert for software that is pinned, offline (**R15**), and does whatever it did on the day
it was pinned. And model choice is expected to churn regardless — the field moves, and the standing
intent is to pick whatever is best *now* rather than to bet on one lineage.

**The condition: "we do not need updates" only holds while the artefact still exists.** Not needing
a newer version is not the same as being able to reinstall the version you have. A rebuilt venv, a
new machine, or a `rm -rf` followed by a fresh install all go back to PyPI, and a package that has
been yanked, renamed or deleted takes the capability with it. So the acceptance is paired with:

- **Pin the exact version.** `mlx-qwen3-asr==0.3.5`, never a range.
- **Keep a local wheel.** `.vendor-bakeoff/mlx_qwen3_asr-0.3.5-py3-none-any.whl`, gitignored, with
  the digest above. It protects this machine; it does not travel with a clone.
- **Weights are a separate and safer dependency.** They are Qwen's own repositories on the Hub, not
  the port's, so the port disappearing does not take them.

## What to do when this breaks — read this first, it is the point of the record

If `pip install mlx-qwen3-asr==0.3.5` fails for you, in order of preference:

1. **Install the local wheel** if you are on the machine that has it:
   `pip install .vendor-bakeoff/mlx_qwen3_asr-0.3.5-py3-none-any.whl`. Verify the sha256 above
   first — a wheel you cannot attribute is worse than no wheel.
2. **Build from the upstream repository** at the tag or commit matching 0.3.5. Apache-2.0 permits
   vendoring it outright; if the repository is gone, any fork of it is equally usable under the
   same licence.
3. **Fall back to `mlx-community/whisper-large-v3-turbo`**, and understand what you are giving up:
   measured on this repository's synthesized fixtures, turbo produces text on **63 of 63** non-speech
   segments where Qwen produces **none**. On *real* non-speech Qwen is 23/253 rather than zero
   (**V60**); turbo was never rerun on that material, so the gap is a floor, not a measured ratio. **There is no longer a filter behind it** — `HALLUCINATION_PHRASES`
   was emptied on 2026-08-12 because every entry was a normal thing to say in some deployment, and
   because the shipped model made the list redundant. Falling back therefore means those false lines
   reach the buffer. If you take this path, measure what your audio actually produces and put those
   strings in the list deliberately; a blacklist of known strings cannot generalise — **R37** ranks stopping false
   lines above transcription accuracy precisely because a spurious cue fires at the worst possible
   moment. Falling back is a real regression on the criterion that matters most, not a lateral move.
4. **Do not silently substitute a different model.** **R11** requires the ASR model to be a
   deliberate, re-examined choice. If you change it, measure it — `tools/asr_bakeoff.py` exists for
   this and `fixtures/asr/FORMAL_MEASURE.md` says what a run must observe.

## Consequences

- Open decision 4 in `STATE.md` is closed by this record.
- **This does not by itself wire Qwen in as the default.** The measurements behind it rest on
  synthesized TTS speech and programmatic non-speech; **V41** (Qwen advertises singing and
  music-with-backing-track as supported input) is **not** disproven by a clean run on those
  fixtures, and real bilingual audio has not been scored. Choosing the default under **R11** is a
  separate step.
- ~~Nothing here changes `ASR_MODEL`.~~ **Superseded 2026-08-11 by `docs/decisions/0009`**, which
  chose `Qwen/Qwen3-ASR-0.6B` and wired it. This record was written the day before that decision.
