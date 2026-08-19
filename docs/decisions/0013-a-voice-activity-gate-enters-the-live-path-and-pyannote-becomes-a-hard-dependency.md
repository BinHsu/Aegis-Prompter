# 0013 — A voice-activity gate enters the live path, and `pyannote` stops being optional

- **Status:** accepted
- **Decided:** 2026-08-18 by the operator
- **Follows from:** R3, R8, R9, R15, R37, R49, R50, V60, V64, V72, V73, V77, V78, V79, V80, V82
- **Reverses:** the "not in `requirements.txt` and never will be" stance recorded in
  `src/diarize.py`, which `docs/decisions/0012` relied on when it described **R15** as
  structurally true

## Context

`docs/decisions/0012` replaced the ASR model on supply-chain grounds and accepted a measured
regression on **R37**: the shipping model invents an utterance from **252 of 253** real non-speech
segments (**V72**) where the removed model produced 23, and from **154 of 154** music segments
including verbatim sung lyrics (**V79**).

That record then searched for a mitigation and reported twice that the audio side was exhausted —
five decoding configurations (**V73**), two checkpoints (**V76**, **V77**). **Both searches swept
the decoder and neither looked at the stage in front of it.** The 253 segments are simply what
`webrtcvad` at aggressiveness 3, a 2011 energy/GMM detector, had already called speech.

The field's answer to this problem has never been decoder thresholds. `faster-whisper` and WhisperX
put a **neural voice-activity detector** in front of Whisper, and the published work on non-speech
hallucination agrees. It is also structurally what the removed model did internally, which is why
its silence was free (**V77**).

## Decision

**Put a neural voice-activity gate between segmentation and the decoder, and use `pyannote`.**

### Why `pyannote`, when Silero measures better on rejection

Two candidates were measured on identical corpora (**V80**, **V82**):

| | Silero | **`pyannote` @ 0.25 s** |
|---|---|---|
| Non-speech rejected | 231 / 253 (91%) | 165 / 253 (65%) |
| **Real degraded speech destroyed** | 58 (28%) | **6 (3%)** |
| Clean speech destroyed | 0 | 0 |
| Ratio | 4 : 1 | **27.5 : 1** |
| Provenance | MIT, Russian-authored | **French** |
| Added packages | 2 (`torch` already present) | **47** |

**The operator chose `pyannote`, and stated the frame rather than only the choice:**
*非紅是這次的改動目標* — reducing this class of supply-chain exposure **is** the purpose of the
change. **R50**'s text bars PRC origin and is silent between a Russian option and a French one; the
intent is not silent, and where both candidates clear the wording, the one clearing the intent by
more wins. That clarification is now in **R50** itself, because the sentence alone would not have
produced this decision.

**The engineering agrees, which is not why it was chosen but is worth recording.** Under **V64** —
*noise costs a line, a destroyed answer costs the record* — `pyannote` at its knee is the better
trade despite rejecting less: it costs six isolated filled pauses against Silero's fifty-eight
segments of real quiet speech. Pushed to Silero's rejection rate it costs **41%**, worse than
Silero at the same point (**V82**). It is not a better detector; it is a better-placed one.

### What it costs, stated because it is the reason this needed a decision

`pyannote.audio` pulls **47 packages**, including **nine `opentelemetry-*` and `pyannoteai-sdk`
packages — a telemetry framework and a cloud SDK — declared as core requirements, not extras**.
Verified by installing it, not quoted.

`src/diarize.py` kept all of that to an *on-demand* install for one stated reason: **R15**'s
offline guarantee stayed *structurally* true for anyone who never pressed "separate speakers" —
there is no telemetry exporter and no cloud SDK in a process that never installed them. Its
docstring says the package "is not in `requirements.txt` and never will be".

**This decision reverses that.** A gate in the live path is loaded by every session, so those
packages become always-present, and **R15 stops being checkable by reading the dependency list**.
Neither transmits anything unconfigured — that was true when `diarize.py` accepted them and is
still true — but the property that changes is *checkability*, and it changes for every user rather
than for the ones who opted in.

**The operator accepted this with the cost in front of them.** It was put to them explicitly, with
the package count and the two offending names, before the choice was confirmed.

## What this does not settle

- **The gate's own latency is unmeasured** and lands directly in **R9**'s budget. **V75** showed
  this pipeline is latency-sensitive on exactly this path. Whether the detector runs on CPU or
  Metal also matters, because Metal contends with MLX. **Not estimated here.**
- **65% is not enough on its own.** 88 non-speech segments still reach the decoder against the
  removed model's 23. A text-side filter (**V78**) composes with this and has not been measured
  together with it.
- **Sung vocals survive.** 15 of 56 vocal-music segments pass a neural VAD (**V80**), because
  singing is voice. **V79**'s risk falls by roughly three quarters and does not go away.
- **Whether the gate is a settings field or a constant.** Every model id in this product is a
  field (`model_search.py`), and this adds a second one plus a threshold.

## Consequences

- `pyannote.audio` enters `requirements.txt`. `src/diarize.py`'s docstring must be corrected rather
  than left contradicting the build, and its on-demand install becomes redundant for the package
  while remaining relevant for the *weights*.
- `README.md`'s offline claim needs the same treatment: still true, no longer checkable the same
  way.
- The ungated `ivrit-ai/pyannote-segmentation-3.0` re-host avoids a Hugging Face token, which
  `diarize.py` already verified. That is a third-party re-host and therefore a supply-chain
  judgement of its own — the same shape `docs/decisions/0008` once accepted, and worth re-examining
  rather than inheriting.
