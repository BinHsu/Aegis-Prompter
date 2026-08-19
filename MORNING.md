# Morning of 2026-08-20 — the night is read and recorded

**You do not need to read any logs.** The queue finished with `== DONE` at 03:28 (started 22:30, five
hours, every stage), and every result is already a `V*` entry in `REQUIREMENTS.md` with its method and
its limits. This file is the index to that, and then the short list of what still needs you.

Raw output, gitignored, on this machine only:

    fixtures/asr/results/20260819-2230-overnight/     the run that matters
    fixtures/asr/results/20260819-2121-overnight/     a false start, kept as evidence
    fixtures/asr/results/*-extra/                     the follow-on: diarization on retained audio

## What the night settled

| | Finding |
|---|---|
| **V96** | V87's missing hour: the speaker leak holds at **~0.41 CER** over 60 min, 487 lines. Headphones stay a precondition. **And**: the bucketed CER metric V87 introduced as a fix is unbounded, so its error grows with the number of buckets — do not quote the 60-minute *mean* of 0.8388. |
| **V97** | **The gate ran live for a full hour** — the thing every previous "gate on" run only claimed. 67 rejections, and worst-case queue dwell fell **6521 → 2898 ms** because rejected audio never enters the queue. Latency unchanged, zero exceptions, zero network. |
| **V98** | **Retention wrote two distinct files**, first time since the toggle shipped 2026-08-13. Both within 0.2 s of the soak duration, and their first five seconds differ — which is the check that matters, because one stream written to two paths would pass everything else while breaching **R2**. |
| **V99** | The advisor as a rate, 140 calls: fabrication **3%**, prose-declines **14%**, both confined to one question shape. **New**: it declines questions it *can* answer — 19 of 20 on one case. |
| **V100** | **V95 reproduced exactly**: 0 of 5 cues fired at the shipped 0.65 threshold. Not a one-run artefact. |
| **V101** | Gated, the segmentation table **can choose again** — R37 spread goes from 3 points to 16 — and it endorses the `flush=0.4` already shipped. **V66 survives on merit.** |
| **V102** | V92's unexplained 239 was run-to-run variation, **not** the environment: both venvs read 253/253 the same night. Ungated, the model invents on **essentially every** non-speech segment. |
| **V103** | **V67 is retired.** Dual-track cost at conversational pace on the shipped model: **1.32x**, between V67's withdrawn 1.47x and its own 1.20x null. Tail is **10.4 s**, on `Participant`. |
| **V104** | Simplified output is **81%** on current data. V90's 88% came from a stage that globbed a hardcoded directory and could only ever reprint an old number. |
| **V105** | **Speaker separation ran on audio the product recorded**, for the first time since it was built. But the tap and the microphone — two recordings of the *same* sound — disagree on speaker count at ten minutes (**3 vs 2**). Attribution accuracy is still unmeasured. |

## The one thing worth carrying forward

**Five separate instances of one pattern turned up in three days**, and every one of them looked healthy
from the outside:

- **V91** — the voice gate failed open for every run labelled "gate on", including the hour behind V86.
- Two **preconditions** that matched their own invoking shell, so they reported a busy GPU and a
  running measurement that were themselves.
- A **guard** broken by `grep -c` printing `0` and exiting `1`, so a rung that captured nothing was
  waved through instead of aborting the queue.
- A **measurement stage** globbing a frozen directory, so it replayed V90's number every night.
- And one of my own, written *during* this work: a diarization sanity line that flags "a floor of
  exactly 0" for empty turns, while the real output floor is **0.02 s** — twenty milliseconds, which is
  the same degeneracy one threshold-width away from being caught (**V105**).

**A check or a measurement that cannot fail reads exactly like one that is passing.** The only defence
that worked in all five cases was asking *what would this print if the thing were broken* — and then
arranging to see it. Where a probe now exists (`voice_gate.is_live`, the retention head-comparison,
the R37 gated column), it exists because of one of these.

## Decided at 05:30 on your criterion, and implemented

Both on *significant improvement, and what it costs in resources* — `docs/decisions/0014`.

- **`SERVE_THRESHOLD` 0.65 → 0.45.** Improvement 0/5 → 4/5 cues fired, false positives still 0/5,
  re-verified after the change (9/10 labelled utterances now correct, against 5/10). **Cost: none** —
  the lookup already ran on every line; the threshold only gated display.
- **The generative slot ships off.** 52% of answerable questions answered, 3% fabrication, 14%
  displayed noise (**V99**) — and it **doubles ASR inference while answering** (**V106**: 649 →
  1308 ms, paired, median 2.01x). Nothing deleted; a URL in settings brings it back.

## What still needs you — two items

1. **V45** — one click on the folder-dialog opt-in button. A native dialog cannot be simulated.
2. **The real meeting**, on headphones — **V87** and **V96** make that evidence, not preference.

Everything else that could be taken off your plate has been: speaker separation runs with no Hugging
Face account (**V93**), the generative advisor has produced tokens, retention has written files, and
the gate has been observed live.

## Two small things to put back

- ✅ Output volume put back to **25**, where you had it. The queue had restored it to 45, because
  the relaunch captured the level I had set by hand.
- `.venv-diarize` and `.venv-llm` are disposable and gitignored — `rm -rf` either, whenever.

**Then delete this file.** It is dated and it expires by construction.
