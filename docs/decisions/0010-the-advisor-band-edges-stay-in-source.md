# 0010 — The advisor band edges stay in source, unexposed, until a meeting gives them a basis

- **Status:** superseded
- **Decided:** 2026-08-13
- **Superseded by:** [0011](0011-the-advisor-slots-do-not-gate-each-other.md), the same day
- **Follows from:** R28, R31, R33, R36, V22, V23

> ⚠️ **This record was wrong when it was written, and is kept unaltered below.** It argues about
> where two band edges should live, on the premise that the retrieval score routes between the
> advisor slots. The operator had already dissolved that premise on 2026-08-12 — *there is no
> band; both are sent to, both are shown, and the source is labelled* — and it was recorded in
> `STATE.md` under *Open decisions*, entry 3. The session that wrote this read the plan section
> of the same file, which still described the routing, and did not read the entry that closed it.
> `0011` carries the decision that actually holds.

## Context

The advisor-backends plan left one question open — *are the two band edges adjustable, and if so
from where?* — and instructed that it be resolved **by measurement during that item, not before
it**. Three-band routing gates the generative slot on the retrieval score:

| Score | Action |
|---|---|
| ≥ `SERVE_THRESHOLD` (0.65) | serve the retrieved cue; send nothing to the LLM |
| `GROUND_THRESHOLD` (0.45) – 0.65 | send, with the near-miss chunks as grounding |
| < 0.45 | send nothing |

The two numbers do not have the same standing, and that asymmetry is the whole decision:

- **0.65 has shipped since Phase 6.** `local_advisor.py` has computed it against a real index and
  served hints on it (**V22**). It is not *measured* in the sense **REQUIREMENTS.md** reserves that
  word for — no `V*` records a false-trigger rate at 0.65 versus 0.60 — but it has been exercised.
- **0.45 has no empirical basis whatsoever.** It was proposed while drafting the advisor-backends
  plan and no utterance has ever been scored against it. It is a guess, and the plan said so.

The measurement the plan asked for cannot be taken during the advisor-backends work. Scoring a
band edge needs utterances a knowledge base half-covers, and the only source of those is a real
hearing — the real-meeting validation, which the plan puts last deliberately. Fixtures cannot
supply it: the score is a property of the *pair* (this index, this room), and a fixture would
measure a knowledge base written to match its own audio.

## Decision

**Both edges are constants in `src/advisors.py`. Neither is a settings field, and neither moves
until the real-meeting validation produces scored utterances.**

Two things follow, and they are the reason this is a decision rather than a deferral:

**Exposing an unmeasured number invites tuning by superstition.** A `.env` field says "this is
yours to set", and the operator has nothing to set it *from* — no distribution of scores, no
false-trigger rate, no worked example. The first bad meeting would be followed by moving a
threshold in the direction that feels right, which is indistinguishable from moving it at random
and is much harder to unwind than an unexposed constant.

**A wrong lower edge fails in the expensive direction, in both directions.** Too low floods the
speaker with generated text that R30 says is not safe to read aloud. Too high silently disables
the LLM band entirely — and a disabled band presents identically to a backend that is down, which
is exactly the failure **R36** exists to prevent. Neither failure announces itself; both would be
attributed to the model rather than to the edge.

**What makes the deferral honest rather than an evasion:** every score is logged unconditionally,
already, on every utterance — `local_advisor.py` has done this since Phase 6 and the running view
now surfaces the most recent one (**V35**, **R36**). So the real-meeting validation needs no
special instrumented build to produce the basis. It produces it by running.

## Rejected

| Option | Why not | Against |
|---|---|---|
| Expose both edges in `.env` | The typed-not-enumerable argument under **R33** is right about *where* a threshold would live if it were exposed, but it does not argue that it *should* be. Handing the operator two numbers and no basis is worse than handing them neither. | R33 |
| Expose them on the pre-flight panel | A band edge is a property of the knowledge base and the domain, not of a single meeting. Per-meeting placement would invite re-tuning between sessions, which destroys the comparability the eventual measurement needs. | R33 |
| Expose 0.65 only, since it has been exercised | The two edges interact: raising 0.65 widens the LLM band from above while 0.45 holds it from below. Exposing one of a pair is how a system acquires a setting whose effect nobody can predict. | — |
| Pick a defensible 0.45 from the literature | There is no literature about *this* index against *this* room. A number with a citation and no local basis is worse than an admitted guess, because the citation stops anyone questioning it. | — |

## When this reopens

When the real-meeting validation has produced a session's worth of scored Participant utterances.
The question to ask of that log is not "what is the right threshold" but **what fraction of
utterances land in each band, and were the middle-band generations worth reading** — an operator
judgement of the same kind **R9** already asks for, not a metric. Record the outcome as a `V*` and
amend this record; do not move a constant without one.
