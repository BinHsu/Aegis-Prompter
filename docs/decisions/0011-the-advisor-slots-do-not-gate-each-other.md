# 0011 — The advisor slots do not gate each other; the band that 0010 argued about does not exist

- **Status:** accepted
- **Decided:** 2026-08-12 by the operator; recorded 2026-08-13
- **Supersedes:** [0010](0010-the-advisor-band-edges-stay-in-source.md)
- **Follows from:** R28, R29, R30, R42, V22, V23, V24

## Context

`0010` argued at length about where two band edges should live, on the premise that the retrieval
score routes between the two advisor slots. **That premise was already dead when `0010` was
written.** The operator dissolved it on 2026-08-12, and it was recorded in `STATE.md` under *Open
decisions*, entry 3:

> **Advisor band edge `0.45`. Dissolved 2026-08-12 — there is no band.** The operator's answer to
> "which backend wins when both are filled" is that neither does: **both are sent to, both are
> shown, and the source is labelled**. […] The LLM gets every Participant utterance with no score
> gate.

`STATE.md` held both versions at once — the plan section still described three-band routing and
listed the band edges as an open question, while the *Open decisions* section recorded that the
question had been dissolved. The implementing session read the plan section and not the other, and
built the scheme that had been rejected. That is recorded here rather than quietly corrected,
because the failure is instructive and cheap to repeat: **a plan section is not amended when the
decision it depends on is closed elsewhere in the same file**, and the section that reads as
"current work" is the one an implementer opens.

## Decision

**Every armed slot receives every Participant utterance. Neither backend gates the other.**

| | |
|---|---|
| Retrieval | keeps its own `0.65` threshold (**V22**) |
| Generation | **no numeric gate at all** |
| Both armed | both are sent to, both are shown, each labelled with what produced it |

Three consequences worth stating so they are not re-derived:

**`0.65` is not a band edge and survives the dissolution.** It answers a different question —
*is this retrieved chunk about what was just said at all* — and showing an unrelated pre-written
answer is worse than showing nothing. It gates what retrieval *displays*, never what the model
receives.

**`0.45` is gone, not deferred.** `0010` proposed keeping it as an unexposed constant until a real
meeting gave it a basis. There is nothing to give a basis to: the number existed only to decide a
competition that no longer takes place.

**Nothing is attached to the generative request as grounding.** Handing the near-miss chunks to
the model was the middle band's mechanism, and reintroducing it would put the retrieval score back
into the generative path by the back door — the same coupling, one layer down. The two slots are
independent, and the transcript is all the model is given.

What replaces routing is the display, and it was already required: **R42** asks the three kinds of
advisor output to be visually distinct at a glance, and **R30** marks generated text unverified.
Separate labelled panes remove the competition instead of arbitrating it, which also settles
**V24** — that was a collision because two sources fought over one display position.

What replaces the gate is **V23**'s clause in the system prompt, which permits the model to return
nothing, plus the operator having seen how their own endpoint behaves before the meeting. The model
does not assess its own output; the operator does, and the `UNVERIFIED` label is what carries that
to the speaker.

## Rejected

| Option | Why not | Against |
|---|---|---|
| Three-band routing on the retrieval score | It picks a winner between two things that do not compete, using a lower edge nobody has measured. Both can simply be shown. | R42, V24 |
| Suppressing the model when retrieval scores high | A prepared cue does not make the model redundant; it may be answering a different part of the same question. And the suppression is invisible — the operator cannot tell it from a dead backend. | R28, R36 |
| Attaching near-miss chunks as grounding | The coupling the dissolution removed, reintroduced one layer down. | — |
| Rewriting `0010` in place | Records are append-only. `0010` stands as written, with a `Superseded by` line, because what it got wrong is the useful part. | `docs/decisions/README.md` |

## What this leaves open

Not blockers, and both are named in `STATE.md`'s *Open decisions* entries 2 and 3:

- **Three simultaneous sources compete for a speaker's attention mid-sentence.** **R42** says a
  glance must be enough to tell them apart. The three labelled cards are a first answer; whether
  they survive a podium is a judgement nobody has made yet.
- **The pre-flight rehearsal** — the operator enters questions, presses a button, and reads what
  their own endpoint answers — is what makes "unverified" a tested statement rather than a
  disclaimer. What exists today is a one-word connectivity probe, which is the liveness half only.
