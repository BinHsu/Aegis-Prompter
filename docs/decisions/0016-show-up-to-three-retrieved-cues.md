# 0016 — Show up to three retrieved cues, not one

**Status:** Accepted 2026-08-21 by the operator — *「顯示提示三則為上限」*. Implemented the same day.

Amends the display side of the retrieval slot. Does not touch `docs/decisions/0011` (the two advisor
slots still do not feed each other) or `0014` (the threshold stays 0.45 and the generative slot stays
off).

## The decision

`advisors.MAX_CUES = 3`. `local_advisor` asks the store for that many points instead of one and
returns every one that clears `SERVE_THRESHOLD` on its own merit, strongest first. The pipeline emits
**one** `Advice` carrying them, numbered and each labelled with its own score.

## Why — the ranking was being computed and thrown away

**V111** measured the retrieval slot naming the wrong note. **V112** then found the right note is
usually *near* the top rather than absent:

| Notes | recall@1 | **recall@3** | Gated: right note among the shown ≤3 |
|---|---|---|---|
| 50 | 58.0% | **84.0%** | **75.3%** (from 57.3% at one cue) |
| 200 | 55.3% | 72.3% | 67.0% (from 54.3%) |

`local_advisor` queried with `limit=1`. **V113** then showed the store's query costs **0.25–0.55 ms
regardless of how many points are asked for** — the ranking was already computed and positions two
and three were discarded. So this recovers accuracy that had already been paid for.

## Why three and not five

Gated recall gains only ~3 points from three to five (75.3% → 78.7% at fifty notes) while the average
number of cues on screen rises toward three. **The cost of more cues is entirely R9** — a speaker
scanning a list is not reading a line — and R9 is a claim about attention under load, which no
measurement here can settle. Three was the operator's call.

**Measured afterwards, and it makes the R9 cost smaller than the name suggests:** over 60 questions
against 20 distinct notes, **68% of firings still show exactly one cue**; the distribution was 4
silent, 41 one-cue, 8 two-cue, 7 three-cue, averaging **1.39 cues when it fires**. The cap is a
ceiling that rarely binds, not a habit of showing three.

## What this does not fix

**V114** narrowed the problem this addresses: with a prepared set of twenty distinct notes the slot is
already right 85% of the time, and V111's 40% was an artefact of a thousand mutually confusable
Wikipedia paragraphs. So this change converts residual misses rather than rescuing a broken slot.
The two heavier fixes — a retrieval-trained encoder and hybrid sparse-plus-dense — are **deliberately
not taken**: at the note count this product uses they would buy little, and neither should be bought
before a real meeting says the slot is worth improving at all.

## The defect this nearly shipped, recorded because the shape recurs

The first implementation emitted **one `Advice` per cue**. `dialogue_buffer.advice_slots` holds a
single dict per source and `set_advice` overwrites it (**V24**), so three emissions would have left
**the lowest-scoring cue on screen** and written all three to the session log. It was inert only
because `local_advisor` had not yet been changed to populate `hints`, so the loop always ran once.

**A half-applied change is worse than an unstarted one**: the field existed, the loop existed, the
comment claimed the behaviour, and nothing failed. Caught by auditing my own unfinished work rather
than by a test, which is why the tests below exist.

## Rejected

| Option | Why not |
|---|---|
| Pad to three cues regardless of score | Puts a 0.2-scoring note beside one that was actually found. The gate means something or it does not. |
| Suppress repeats per cue independently | A stable second-place note would reappear beside a changing first, reading as the pane half-refreshing. Suppression keys on the top hit only. |
| Change `advice_slots` to hold a list | A wider change to the display contract for no gain — joining inside one `Advice` keeps **V24**'s one-slot design intact. |
| Five cues | +3 points of gated recall for nearly double the reading. R9. |

## Not settled

Whether three short cues are *readable* from a podium. That is **R9**, it is what the real meeting is
for, and no fixture answers it.
