# External review brief

What to hand a reviewer — human or agent — when the requirements and the plan need an independent
read, and what to ask them for. The file list matters less than the last section.

## Provide these

| File | Why |
|---|---|
| `REQUIREMENTS.md` | The judgement layer. Its **Decided and closed** table is the highest-value part: without it a reviewer re-proposes ASR-side diarization, per-application capture and browser-side capture, and a large share of the review is spent relitigating settled ground. |
| `STATE.md` | The plan itself, plus open decisions and known issues. |
| `AGENTS.md` | Specifically **Invariants that break the app if violated**. A reviewer who does not know that all NPU access is serialized, or that the audio callback must never block, will produce recommendations that violate them. It also states that no hand-written architecture description in the repo should be trusted. |
| `FILEMAP.md` | Generated from the AST, so the reviewer learns what exists without grepping or guessing. |
| `src/*.py` (6 files, ~830 lines) | **Not optional.** Without the code a reviewer can only check the plan for internal consistency; they cannot check whether `V1`–`V37` still hold. Nearly every plan item hangs off a `V*`, so a review that cannot verify those is a review of the prose, not of the plan. |

Roughly 90 KB in total — small enough to hand over whole, so there is no reason to be selective.

## Withhold these

| | Why |
|---|---|
| `.env`, `context/`, `history/`, `logs/` | The operator's secrets, private notes and meeting transcripts. Withholding is not enough: **say so explicitly**, because a diligent reviewer checking `V34` (the RAG index failing silently) will want to look inside `context/` to see whether an index exists. |
| `README.md` | Known stale — it still documents `MULTILINGUAL_MODE`, which the plan deletes. Handing it over manufactures findings that are already known. Include it only when documentation sync is itself part of the review, and say that it is stale. |
| `CHANGELOG.md` | No signal for a plan review. |

## Ask for these four things

Not "please review". Ask questions with checkable answers:

1. **Coverage** — is every `R*` satisfied by some plan item, or explicitly refused by a closed
   decision? Name any that are neither.
2. **Contradiction** — does any plan item conflict with a `V*`?
3. **Sequencing** — does any item depend on the output of an item scheduled after it? This is where
   plans of this shape fail, because each item reads as reasonable in isolation.
4. **Decay** — which `V*` are old enough, or load-bearing enough, that they should be re-measured
   before the item that relies on them is built?

State the citation rule up front: **cite `R*` and `V*`, never `7.*`.** Plan numbers are renumbered
whenever execution order changes, so a review written against them expires within days.

## Run it blind the first time

Do **not** hand over the list of gaps already found internally, and keep that list outside the
bundle — a gap written into `STATE.md` is a gap the reviewer reads rather than finds, which voids
the test for that item.

If an independent reviewer names a gap unprompted, it is confirmed. If they miss one, that
calibrates how much weight the rest of their review deserves. Anything they find that is *not* on
the internal list is pure gain.

Share the internal list only on a second pass, as a comparison — never as the opening prompt.

The trade-off is real and worth stating: a gap held back for the sake of the test is a gap not yet
scheduled for repair. Hold one back only while it is still under discussion. Once it is accepted as
a defect, it belongs in `STATE.md` and its blind test is spent.
