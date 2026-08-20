# 0015 — The voice gate ships on

**Status:** Accepted 2026-08-20 by the operator, on the same criterion as `0014`: *is there a
significant improvement, and what does it cost in resources?* Both halves were measured before the
decision.

**Amends** the reasoning recorded at `settings_from` in `src/voice_gate.py` and the `VAD_GATE` field
default in `src/bootstrap.py`. Does not supersede any earlier record.

## The decision

`VAD_GATE` defaults to `"true"`. `.env.example` and the field's help text follow. This machine's
`.env` was set through the settings page at the same time (**R18**, **R32** — never edited by hand).

## Improvement

**Off was never a neutral default.** Ungated, the shipped model invents an utterance from
**essentially every real non-speech segment — 253 of 253, twice, in two environments** (**V102**).
Whisper's own no-speech gate cannot arm: the distilled decoder reports `0.000` there, and five
decoding configurations changed nothing (**V72**, **V73**, **V79**). So "leave it off" was a choice
to keep that behaviour, not an absence of one.

| Measured | Value |
|---|---|
| False lines on real non-speech, through the shipped module | **253 → 88** (**V84**, **V92**) |
| Cost in real degraded speech | 6 utterances of 204, and 23 of 25 removals cannot carry an utterance at all (**V84**) |
| Per rejected segment | **33 ms**, against **3142 ms** to decode it (**V83**, **V92**) |
| An hour with the gate **genuinely live** | 67 rejections, **worst-case queue dwell 6521 → 2898 ms**, medians flat across all five fifths, zero exceptions, zero network (**V97**) |

## Resource cost

**Negative on latency.** The detector runs on CPU deliberately — Metal is 10 ms faster and shares
the accelerator `NPU_LOCK` exists to serialise. Rejected audio never enters `inference_queue`, so
**V97** measured worst-case queue dwell falling by 56% and non-zero dwell falling from 5.4% to 3.4%
of segments. The gate's 32 ms buys back head-of-line blocking, which **V67** identified as the cause
of the tail.

**Weights: 5.6 MB**, already required for nothing else, already cached.

## What the R41 reasoning said, and why it is not overturned

`settings_from` read *"off unless explicitly enabled — a gate that starts discarding audio because a
dependency appeared would be a behaviour change nobody asked for (R41)"*.

**That reasoning stands.** It is about an *appearing dependency* silently changing behaviour, and
`settings_from` still reads the **setting** rather than the presence of the package — so installing
`pyannote.audio` still changes nothing by itself. What moved is a shipped default, deliberately and
with this record. `tests/unit/test_voice_gate.py::test_the_gate_is_off_unless_it_is_turned_on` still
passes unchanged, which is the mechanical form of that distinction.

## The failure mode this decision inherits, and the mitigation

**A default-on gate can be silently inert.** The gate fails open on every path — missing package,
absent weights, load error, exception mid-segment — because a wrong `False` deletes a participant's
sentence (**R3**, **V64**). So on a machine without the weights, `VAD_GATE=true` screens nothing
while every number looks healthy. **That is exactly V91**, where three overnight soaks and the hour
behind **V86** were published as *gate on* while failing open.

Default-on makes that trap more likely, not less, so the mitigation is a precondition of this
decision rather than a nice-to-have:

- `voice_gate.is_live()` screens two seconds of digital silence. Every failure path returns `True`,
  so a `False` cannot come from a gate that did not run.
- `tools/soak_capture.py --gate` **refuses to run** when the gate is not live.
- `tools/run_overnight.sh` prints `voice gate LIVE` in its preflight.
- `tools/measure_segmentation.py --gate` refuses likewise.

**And the weights cannot be fetched on this machine**: `huggingface_hub` fails on a Cloudflare
Gateway CA while `curl` and `pip` succeed (**V93**, and the known issue in `STATE.md`).
`tools/hf_curl_place.py` is the route, and it needs no change to what any tool trusts.

## Alternatives rejected

| Option | Why not |
|---|---|
| Leave it off and let each operator turn it on | The measured default was "invent a sentence from every non-speech segment". Requiring an act to *stop* that is the wrong way round. |
| Ship on **and** fail closed | A wrong `False` deletes a hearing. **V64**'s ranking is explicit: noise costs a line, a destroyed answer costs the record. |
| Raise the 0.25 s floor for safety | **V82** measured the knee: 0.40 s buys 23 more rejections for 19 destroyed utterances, 0.60 s buys 11 for 31. Every larger value is a worse bargain than the one before. |

## Not settled by this record

Whether the gate helps in a **real meeting**, which no fixture answers, and whether the 3% quiet-speech
cost matters for a soft-spoken participant — **V84** notes that transcription of quiet speech collapses
with level anyway (CER 0.207 at −38 dBFS, 0.592 at −50), which softens but does not remove the question.
