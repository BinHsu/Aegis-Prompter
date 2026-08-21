# 0014 — Lower `SERVE_THRESHOLD` to 0.45, and ship the generative slot off

**Status:** Accepted 2026-08-20 by the operator, on a stated criterion: *is there a significant
improvement, and what does it cost in resources?* Both halves were measured before deciding.

Supersedes nothing. It changes one constant that `docs/decisions/0010` and `0011` discuss without
ever fixing, and it records a second decision those two anticipated and could not settle.

## The decision

1. **`SERVE_THRESHOLD` moves from 0.65 to 0.45** (`src/advisors.py`).
2. **The generative advisor slot ships off** — `LLM_BASE_URL` empty is the shipped default and stays
   that way. Nothing is deleted: the code, the pre-flight rehearsal and the probe all remain, so the
   decision is reversible by typing a URL into the settings page.

## Why the threshold moves — improvement, and cost

**0.65 had never been measured against anything.** It shipped from Phase 6. **V22** records that the
threshold *is* the intent judgement, which is a statement about the design, not about the value.

**V95**, reproduced independently as **V100**, measured it with the real embedding model against a
temporary index of invented notes:

| Utterance kind | Score range | Fires at 0.65 | Fires at 0.45 |
|---|---|---|---|
| Five paraphrases of indexed notes | 0.366 – 0.634 | **0 of 5** | **4 of 5** |
| Five unrelated meeting lines | 0.033 – 0.380 | 0 of 5 | **0 of 5** |

- **Improvement: 0 of 5 → 4 of 5**, with false positives unchanged at zero. Re-verified after the
  change landed: 9 of 10 labelled utterances now judged correctly, against 5 of 10 before.
- **Resource cost: none.** The retrieval query runs on every Participant utterance regardless; the
  threshold only decides whether the result is displayed. No extra computation, memory or latency.

**0.45 rather than 0.35, and the tie-break is the reasoning.** A sweep separates the two populations
anywhere from 0.35 to 0.45. 0.35 fires all five paraphrases and admits one false positive; 0.45 gives
up one cue and admits none. Ties went to the higher threshold because **a missed cue costs the
speaker a cue, while a false cue costs attention on a teleprompter, and R9 is a claim about
attention**.

### What this does not do

It **reintroduces no band**. `0011` dissolved a three-band scheme whose lower edge was also 0.45;
that coincidence is arithmetic, not a revival. One number moved. Both slots still receive every
utterance and both still display in their own labelled pane.

### The limit, stated because it is the weak part

Ten utterances against five notes, written in the same session as the queries, one embedding model.
That is enough to prove 0.65 fired on nothing — a claim about one number needs one counterexample and
had five — and thin for choosing the replacement. `tools/probe_rag_cues.py` re-runs the whole thing in
seconds and is in the overnight queue, so the next change to the embedding model or the index will
move these scores where someone can see it.

## Why the generative slot ships off — the same two questions, opposite answer

**V99**, over 140 calls through the production prompt and transport:

| Measure | Value |
|---|---|
| Answerable questions answered correctly | **21 of 40 — 52%** |
| Fabricated figures on unanswerable questions | 3% of calls |
| Prose declines the application would display as advice | 14% of calls |

**V106** measured what it costs, paired against a control arm of the same inputs in the same order:

| | Median per input |
|---|---|
| Whisper alone | **649 ms** |
| Whisper while the model generates | **1308 ms** |
| Per-input ratio | **median 2.01x**, up to 4.47x |

**A slot that answers about half of what it could, invents on a few percent, puts noise on screen for
14%, and halves the speed of the transcript is not paying for itself** — and **R9** is a promise about
that speed. One Metal accelerator serves both, and `NPU_LOCK` serialises callers inside a process and
does nothing across processes.

### The alternative that was rejected, and on what grounds

**Widening `is_pass` to recognise prose declines** — the 14% — was the obvious fix and is rejected.
Matching phrases like *"not available"* would also swallow a genuine answer containing them, and that
mistake fails **silent** at a hearing, which **V64**'s ranking puts above noise. It also would not
touch the 2.01x, which is the finding that decides this.

### What would reopen it

A model that does not share the accelerator — a remote endpoint the operator accepts sending
transcript text to, or hardware with a second inference path. **V106**'s penalty is a property of one
accelerator serving two consumers, not of the prompt or the model size.

## Not covered by this record

Whether **R10**'s Traditional-Chinese requirement is met (**V104**: 81% of Chinese output is
Simplified) and whether the voice gate should default on. Both are open and neither is affected by
the two decisions above.
