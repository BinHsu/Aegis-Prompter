# 0012 — The ASR model is `mlx-community/whisper-large-v3-turbo`, chosen on supply chain

- **Status:** accepted
- **Decided:** 2026-08-17 by the operator
- **Follows from:** R8, R10, R11, R15, R37, R50, V39, V40, V41, V44, V54, V55, V59, V60
- **Supersedes:** `docs/decisions/0009` (which chose `Qwen/Qwen3-ASR-0.6B`) and the acceptance in
  `docs/decisions/0008` (which accepted that package's supply chain)

## Context

`docs/decisions/0009` chose `Qwen/Qwen3-ASR-0.6B` on 2026-08-11, and it chose correctly on the
evidence it had: the model won the criterion that ranks first (**R37**) categorically, won
code-switch accuracy by 2.5x, and cost less memory and latency than the alternative that came
closest. `docs/decisions/0008` had examined the *package* — `mlx-qwen3-asr`, a community
reimplementation with a single maintainer (**V44**) — and accepted it, pinned, with a local wheel
and a documented recovery path.

Both records asked "will this artefact still exist?" **Neither asked whose it was.** The operator
raised that on 2026-08-17: the weights are Alibaba's and the MLX port is maintained from the same
region, and this product is deployed into Taiwanese proceedings where a PRC-origin component in
the speech path is a procurement question before it is a technical one.

That is a constraint no measurement in this repository can see. `tools/asr_bakeoff.py` scores
error rate, latency, memory and false lines; nothing it prints changes if the vendor changes.

## Decision

**Adopt `mlx-community/whisper-large-v3-turbo` as `ASR_MODEL`, and record the new constraint as
R50 rather than as a one-off.**

The model is not a new candidate. It is the runner-up in `docs/decisions/0009`'s own table — the
"documented fallback" that record named, adopted now for the reason that record did not weigh.
`R50` is written into **REQUIREMENTS.md** as a requirement rather than noted here, because a
constraint that lives only in a decision record gets re-litigated by the next person who reads a
table where a disqualified model wins.

### The provenance survey behind R50

Read from installed package metadata and model cards on 2026-08-17, not recalled:

| Component | Ships as | Published / maintained by | Verdict |
|---|---|---|---|
| ASR weights | `mlx-community/whisper-large-v3-turbo` | Whisper is OpenAI's (US); the MLX conversion is the `mlx-community` org | **ok** |
| ASR loader | `mlx-whisper` 0.4.3 | MLX Contributors, `mlx@group.apple.com`, MIT | **ok** |
| Accelerator | `mlx` / `mlx-metal` 0.32 | same, Apple | **ok** |
| Embeddings | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | Sentence-Transformers / UKP Lab, TU Darmstadt (Germany), over a Microsoft base | **ok** |
| Embedding library | `sentence-transformers` v5 | Nils Reimers, Tom Aarsen | **ok** |
| Speaker separation *(optional)* | `pyannote/speaker-diarization-community-1`, alt `ivrit-ai/pyannote-speaker-diarization-3.1` | pyannote (France); the mirror is ivrit.ai (Israel) | **ok** |
| Voice detection | `webrtcvad-wheels` 2.0.14 | David Zurow, over Google's WebRTC | **ok** |
| Retrieval store | `qdrant-client` 1.19 | Qdrant (Germany) | **ok** |
| Web surface | `streamlit` 1.61 | Snowflake Inc (US) | **ok** |
| Audio I/O | `sounddevice` 0.5.5 | Matthias Geier, over PortAudio | **ok** |
| Generative advisor | **no default** — the operator supplies the endpoint | whoever they point it at | **operator's to apply** |
| ~~ASR weights~~ | ~~`Qwen/Qwen3-ASR-0.6B`~~ | ~~Alibaba~~ | **removed** |
| ~~ASR loader~~ | ~~`mlx-qwen3-asr` 0.3.5~~ | ~~single maintainer, `moona3k`~~ | **removed** |

The advisor is the one row this project cannot close. It ships empty by **R31**, so no vendor is
asserted; applying **R50** to it is the operator's, and `README.md` says so rather than implying
the table covers everything.

### What was re-measured rather than carried over

Every figure below was produced on 2026-08-17 in this repository's harness, offline, on the same
fixtures, because a table quoted from a record written under a different toolchain is a claim
(**V53**). The numbers reproduce `docs/decisions/0009` almost exactly, which is itself the useful
result — it means that comparison can still be trusted where this one does not repeat it.

| | 0009, measured 2026-08-11 | reproduced 2026-08-17 |
|---|---|---|
| CER mixed (**R8**) | 0.214 | **0.214** |
| CER zh | 0.138 | **0.138** |
| CER en | 0.145 | **0.145** |
| Latency median | 660 ms | **645 ms** |
| Peak MLX | 2085 MB | **2085 MB** |
| **R37** raw, synthesized non-speech | 63 / 63 | **63 / 63** |

Artefacts: `fixtures/asr/results/20260817T104632Z.md` (bake-off) and
`fixtures/asr/results/20260817T104846Z.md` (real-speech CER).

The product path itself was run, not merely built: `transcriber.resolve_backend` against the
shipped default, offline, out of the product storage root, produced correct Chinese on a fixture
and reloaded after release.

## What this costs, stated plainly

**This is a regression on the criterion REQUIREMENTS ranks first, and it was accepted knowing
that.** **R37** says non-speech must not become an utterance and ranks *above* transcription
accuracy. On the synthesized fixtures the model that was removed produced text on **0 of 63**
non-speech segments; the model adopted here produces text on **63 of 63**, and **62** of those
survive `text_filters.is_acceptable` and reach the buffer. Accuracy is also worse: CER on
intra-sentence code-switching goes from 0.085 to 0.214, roughly 2.5x.

**And on real non-speech it is far worse than the synthesized fixtures suggested.** Re-running
**V60**'s probe on the same 253 segments, 2026-08-17 (**V72**):

| Genuine non-speech, 253 identical segments | produced text | reached the buffer |
|---|---|---|
| `Qwen/Qwen3-ASR-0.6B` (**V60**) | **23 / 253** | — |
| `mlx-community/whisper-large-v3-turbo` | **252 / 253** | **243 / 253** |

That is the number this record exists to make impossible to miss. `docs/decisions/0009` knew only
turbo's 63/63 on programmatic tones and chimes; nobody had ever put it against a room. Laughter,
coughing, footsteps, a washing machine, and room tone with no speech in it all produce an
utterance.

Two things stop this from being a *simple* downgrade, and neither comes close to cancelling it:

- **The 0/63 was never the whole picture.** The removed model did not satisfy **R37** on its own
  either — 23 of 253. The honest comparison is between two models that both fail **R37**, on
  material the synthesized fixtures do not represent. It is a difference of degree, and the degree
  is an order of magnitude.
- **The live path is scoped to the gist (R9)**, and **R49**'s post-meeting cleanup is where a
  person reads the transcript before anyone acts on it.

**One more cost, inherited rather than introduced.** **V58** measured run-to-run variability at
CER **0.167** for turbo against **0.025** for the model removed — the same audio gives a
noticeably different transcript each time, which **V54** attributes to the temperature ladder
falling back to sampling. The previous model had no ladder. Pinning the decoder to greedy is the
obvious lever and is one of the arms in the measurement below.

**It was measured rather than assumed, and the answer is that the regression stands.** Whisper has
gates the removed model did not have at all — a temperature ladder, `logprob_threshold`,
`no_speech_threshold`, `compression_ratio_threshold` — so this lever existed for the first time and
was worth trying. `tools/measure_decode_thresholds.py` ran five configurations over the same
corpora. **All five produced text on 253 of 253 real non-speech segments, with CER identical to
three decimal places** (**V73**).

That is stronger than "no arm won the trade-off": there was **no trade-off to make**. Nothing was
exchanged for a silence that never arrived.

**The reason, measured afterwards, is worse than a mis-set threshold and points somewhere useful.**
`whisper-large-v3-turbo` reports `no_speech_prob` = **0.0000** on non-speech — exactly zero, on 18
of 18 real segments. The skip's first condition is `no_speech_prob > no_speech_threshold`, which
against zero is false for every positive threshold, so all five arms were tuning a gate that was
never armed. **This is a property of the checkpoint, not of Whisper:** on the identical audio, full
`large-v3` reports **0.903**, and real speech sits at 0.05. Turbo is a distilled **4-layer** decoder
against large-v3's 32, and the no-speech token is a decoder prediction — the distillation appears
to have taken the no-speech head with it.

**Full `large-v3` was then measured, because its no-speech head is alive and the question stopped
being speculative.** It is the same family, loader and provenance, ungated, 3.08 GB. The results
(**V76**, **V77**) close the audio-side search rather than opening it:

| Configuration | Real non-speech | **Degraded *real* speech** | Clean speech |
|---|---|---|---|
| `Qwen3-ASR-0.6B` (**V60**) | 23 / 253 | *never measured* | *never measured* |
| `large-v3-turbo`, stock — shipping | 253 / 253 | 203 / 204 | 10 / 10 |
| `large-v3`, stock | 170 / 253 | 183 / 204 | 10 / 10 |
| `large-v3` + tightened gate | **39 / 253** | **91 / 204** | 9 / 10 |

**R37 is purchasable and the price is half the quiet speech in the room.** The last row nearly
matches the model this decision gave up — and destroys 92 real utterances to remove 131 false
ones. **V64** already settled which of those costs more, and **R3** says the transcript is the
record; the sacrificed bucket is a quiet witness, a bad line, a gallery.

**The generalisation, corrected.** Every lever *inside the decoder* — checkpoint, no-speech
threshold, logprob threshold, temperature — moves both columns together, because it decides
whether to decode a segment and the two populations overlap (**V76**). This record originally
generalised that into *"the audio-side search is finished"*. **It was not finished: it had never
looked at the stage before the decoder.**

**A neural VAD in front of Whisper rejects 231 of 253 non-speech segments and no clean speech at
all (V80)** — 22 reaching the decoder against the removed model's 23. That is **parity on R37,
with OpenAI weights, inside R50**, and it is what `faster-whisper` and WhisperX have shipped all
along. The 253 segments argued over above are simply what `webrtcvad` at aggressiveness 3 — a 2011
energy detector — had already called speech.

**So the R37 cost recorded here is a cost of the pipeline, not of the checkpoint.** Three options
remain and they now rank differently: a **VAD pre-filter** (largest effect by far, and the
provenance of the VAD is an open procurement question — Silero is Russian-authored, `pyannote` is
French and already a dependency); a text-side filter (**V78**, useful and much smaller); or
acceptance with **R49** behind it.

⚠️ **One control was never run, and it limits what this record may claim.** **V60** never measured
the removed model on degraded speech, so whether its silence was free is unknown. *"It was better
on R37"* is established; *"it was better overall"* is not.

**One thing the sweep did establish, on a different axis.** The temperature ladder accounts for a
**3.43x** wall-clock penalty on non-speech and **none** of the false lines (**V73**, **V75**).
Greedy decoding is a free 3.4x saving on noisy input at zero measured accuracy cost — worth having,
and a separate decision from **R37**, gated on measuring what it costs on degraded speech.

### Rejected, with reasons

| Option | Why not |
|---|---|
| Keep `Qwen/Qwen3-ASR-0.6B` because it measures better | The constraint is not about quality. It disqualifies the best candidate on these fixtures, which is exactly what a procurement constraint does; a measurement cannot answer it. |
| Keep the Qwen branch in `resolve_backend`, dormant, for operators who want it | `ASR_MODEL` is a free-text settings field. A dormant branch is a model an operator reaches by typing an id, and the constraint would then hold only for people who did not. Removed from `model_search.FAMILIES`, which removes it from dispatch. |
| `Qwen/Qwen3-ASR-1.7B` | Same disqualification, larger. |
| `mlx-community/distil-whisper-large-v3` | **V1**, measured in `docs/decisions/0009`: CER 2.722 on Chinese — it emits more wrong characters than the reference contains. Unusable under **R8**. |
| A newer non-PRC ASR model found by searching now | Not rejected — deferred, and deliberately. **R11** wants a deliberate choice, and `model_search.build_search_prompt` now carries **R50** so the next search applies it. Adopting an unmeasured model in the same change that removed a measured one would have left nothing trustworthy in the pipeline. |
| Restoring `HALLUCINATION_PHRASES` to catch Whisper's ghosts | **Not taken here, and not because it would not work** — the bake-off's accepted strings on non-speech were `Bye.`, which the emptied list held. It was emptied on 2026-08-12 by an operator decision with a stated reason (a fork transcribing a podcast says those words in earnest), and reversing that is the operator's call, not a consequence of changing the model. Raised, not decided. |

## Consequences

- `mlx-qwen3-asr` leaves `requirements.txt`. Nothing in `src/` imports it. `tools/asr_bakeoff.py`
  and `tools/score_real_fixtures.py` can still score that family behind `--include-disqualified`,
  which prints the reason — reproducing the comparison must not require reinstating the
  dependency, and must not happen by accident either.
- `docs/decisions/0008`'s recovery path — pinned wheel, sha256, build-from-upstream — is now
  **history rather than instruction**. Do not follow it.
- `resolve_backend` gained an `initial_prompt` parameter. Whisper has no `context=`, so the
  re-listening pass's proper-noun recovery (**V59**) is a different mechanism and is re-measured
  by `tools/measure_biasing.py` rather than assumed to carry over.
- `release_models()` clears `mlx_whisper.transcribe.ModelHolder` instead of the previous package's
  LRU cache. Measured: it frees essentially all of the warm allocation.
- The **V60** probe was promoted out of a gitignored scratch directory into
  `tools/probe_nonspeech_real.py`. A measurement a requirement leans on cannot live one
  `rm -rf` from deletion.
- `model_search.FAMILIES` has one entry, and its `requires` is no longer a guess: read from
  `mlx_whisper/load_models.py`, it is `config.json` plus `weights.safetensors`. A
  transformers-format repository of the same model will not load and the Hub's tags do not say so.
