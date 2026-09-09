# 0009 — The ASR model is `Qwen/Qwen3-ASR-0.6B`

- **Status:** superseded
- **Superseded by:** [0012](0012-the-asr-model-is-whisper-large-v3-turbo-on-supply-chain-grounds.md)
- **Decided:** 2026-08-11 by the operator
- **Follows from:** R8, R10, R11, R37, V1, V39, V40, V41, V44, V51, V53, V54, V55

## Context

**R11** requires the ASR model to be a deliberate choice, re-examined rather than inherited. Until
today it was inherited: `mlx-community/distil-whisper-large-v3` had been the default since Phase 6
and was never chosen by anyone. **V1** recorded from the model card that Distil-Whisper is
English-only *by design*, which blocks **R8**.

Four candidates were measured on 2026-08-11 in one toolchain, offline, each in its own process,
on 80 clips of real conversational Mandarin-English from CAiRE/ASCEND (**V55**) plus programmatic
non-speech for **R37**:

| Candidate | CER mixed (**R8**) | CER zh | CER en | Latency median | Peak MLX | **R37** raw |
|---|---|---|---|---|---|---|
| `distil-whisper-large-v3` (was default) | 1.199 | **2.722** | 0.157 | 648 ms | 1988 MB | 63/63 |
| `whisper-large-v3-turbo` | 0.214 | 0.138 | 0.145 | 660 ms | 2085 MB | 63/63 |
| `Qwen/Qwen3-ASR-1.7B` | **0.075** | 0.060 | **0.091** | 2123 ms | 6857 MB | **0/63** |
| **`Qwen/Qwen3-ASR-0.6B`** | 0.085 | **0.059** | 0.099 | **771 ms** | 3207 MB | **0/63** |

## Decision

**`Qwen/Qwen3-ASR-0.6B`.**

**R37 decides first, and it is not close.** REQUIREMENTS ranks "non-speech must not become an
utterance" *above* transcription accuracy, because a false line fires a defensive cue at the worst
possible moment. Both Whisper candidates produced text on **every one** of 63 non-speech segments;
both Qwen sizes produced **none**. **Read that as a comparison, not as an absolute — see V60**,
measured 2026-08-12: those 63 were synthesized tones, chimes and clicks, and on real non-speech
Qwen produces text on 23 of 253. It does not change this decision, which was a choice *between*
candidates on identical material and would come out the same way; it does mean the winner does not
satisfy **R37** on its own. That is categorical, not marginal, and it is the model's own
behaviour — measured before the text blacklist, which had been hiding it (the previously reported
"45/63" was the blacklist's work, not the model's).

**Between the two Qwen sizes it is not a trade-off — 1.7B is beaten on two axes out of three and
wins the third by less than a percentage point:**

| | 0.6B | 1.7B | |
|---|---|---|---|
| CER mixed | 0.085 | **0.075** | 1.7B better by 1.0 pp |
| CER en | 0.099 | **0.091** | 1.7B better by 0.8 pp |
| CER zh | **0.059** | 0.060 | 0.6B better by 0.1 pp |
| Peak MLX | **3207 MB** | 6857 MB | 1.7B **+114%** |
| Latency median | **771 ms** | 2123 ms | 1.7B **+175%** |

Everything 1.7B wins is inside a rounding difference; everything it loses, it loses by more than
double. The proportionality rule below is the backstop for a genuine trade; here it is not needed,
because there is no axis on which the larger model is worth its cost.

**The model it replaces is not merely weaker.** A CER of 2.722 means distil emits more wrong
characters than the reference contains. The product has been shipping a default that is
destructive on Chinese.

### Rejected, with reasons

| Option | Why not |
|---|---|
| `whisper-large-v3-turbo` | Best code-switch of the Whisper pair and still 2.5x Qwen's error, but it fails the criterion that ranks first: text on 63 of 63 non-speech segments. Retained as the documented fallback in `docs/decisions/0008` if the Qwen package becomes unobtainable — with that cost stated. |
| `Qwen/Qwen3-ASR-1.7B` | Wins code-switch by **1.0 percentage point** and costs **+114% memory**. Rejected under the operator's rule below, and **closed rather than deferred** — a dual-track memory run for it was queued and cancelled on 2026-08-11, because no result it could produce would change the answer. Do not re-open it to gather a number; re-open it only if a much larger accuracy gap turns up in work being done for another reason. |
| `distil-whisper-large-v3` | **V1**, now measured: unusable for Chinese. |
| Deciding from published benchmarks | Already closed in REQUIREMENTS: no leaderboard measures whether music becomes an utterance. |

### The operator's rule, stated 2026-08-11

> *"A difference of less than two percentage points is not worth more than thirty percent extra
> memory — even if memory were unlimited."*

Recorded because it makes this choice reproducible instead of resting on someone's judgement, and
because the second clause is the part that would otherwise be argued away. It is **not** a
resource constraint: the machine has headroom for either model. It is a stance about proportion —
paying 114% more for 1.0 point buys a number that looks better in a table and changes nothing a
speaker on a podium would notice.

It also settles the comparison in advance of measurements that were still queued. Dual-track
memory for 1.7B cannot change the outcome — it can only make 1.7B cost more, never less — so that
run was cancelled rather than completed for tidiness. **Finishing a measurement whose result cannot
move a decision is the same mistake as the one this rule refuses**, spent in GPU time instead of
memory.

## What this decision does **not** settle

- **V41 stands.** Qwen advertises singing and music-with-backing-track as supported input. Its
  0/63 was measured on *programmatic* music, chimes and keyboard noise. The operator decided on
  2026-08-11 not to test real music with vocals; that is an accepted risk, not evidence of safety.
- **The anti-hallucination blacklist was built for Whisper** and is now largely inapplicable.
  Qwen's failure mode is repetition, not subtitle ghosts. Entries that are plausible real speech
  — `I don't know.`, `Bye.` — now buy nothing and can only destroy a real utterance, so they are
  removed with this change. In a hearing, "I don't know." is one of the most consequential things
  a witness says.
- **Latency doubles under two tracks** (**V56**), so 771 ms is a single-track figure. The realistic
  turn-taking number is being measured separately.
- **R10 is unaffected.** Every candidate that can do Chinese produced Simplified against a
  Traditional reference. Script remains a post-processing concern; the operator has recorded that
  it is not a decision driver.
- **Nothing here closes the bake-off.** The 48 kHz path and dual-track measurement still wait on
  the process tap. This chooses a default to wire, which is what the sequencing allowed.

## Consequences

- `mlx-qwen3-asr` becomes a **product** dependency, pinned per `docs/decisions/0008`, which is why
  that record's recovery path exists.
- `transcriber.py` needs a backend dispatch: it hardcoded `mlx_whisper`, and Qwen has a different
  entry point and no `no_speech_threshold` equivalent.
- Changing `ASR_MODEL` forces a process restart (`bootstrap.fingerprint`).
- The weights must reach the product's storage root; they were fetched into the disposable
  bake-off cache.
