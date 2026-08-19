# 0001 — Retained audio is archived at 16 kHz

- **Status:** accepted · **reversed 2026-08-11**, having been accepted at 48 kHz on 2026-08-07
- **Follows from:** R3, R16, R45, V7, V12, V51, V56, V58

## Context

Dual-track audio may optionally be retained, for post-processing and for **corroboration** —
settling disputes about what was actually said (**R16**). **R3** was worded, when this record was
written, as making completeness of capture the system's own responsibility; it was rewritten on
2026-08-12 to promise only that the system does not discard on its own initiative. That does not
disturb this decision — the rate question is about what a retained file contains, not about whether
one exists — but it removes the obligation the original framing implied.

The Core Audio process tap produces **48 kHz** mono float32 (**V7**), while every ASR model this
product can run consumes **16 kHz** — verified 2026-08-11: `mlx_whisper.audio.SAMPLE_RATE` is
16000, and `transcriber.py` has always opened its streams at that rate. So there are two candidate
archive rates: 16 kHz, matching what the inference path processes, or 48 kHz, matching what the
hardware produces.

## Decision

**Archive at 16 kHz.** One resample at capture, and everything downstream — inference, archive,
re-transcription — shares the same rate.

Three measurements made on 2026-08-11 decided it, none of which existed when this record first
chose 48 kHz:

- **Sample rate buys the model nothing.** Whisper pads every input to a fixed 30-second window, so
  cost is set by the window and not by the input: 1 s and 10 s of audio measured 597 ms and 607 ms
  (**V51**), and peak memory does not move either (**V58**). A higher archive rate cannot improve
  transcription because the transcriber never sees it.
- **Two rates means two paths, and the second one was missing.** With a 48 kHz archive, capture
  feeds the archive at 48 kHz and a *separate* step must downsample for inference. That step was
  never built, and **V56** measured what its absence costs: inference at 48 kHz took **3426 ms
  against 660 ms**, because the model reads the samples as though the audio were three times
  longer, and VAD segmentation shifted too (30 segments to 24). One rate throughout removes the
  path that produced that failure rather than adding the step it needed.
- **Disk: 690 MB against 2.1 GB** for a three-hour hearing across both tracks.

## What this gives up, deliberately

**R45** asks that an archived meeting can be re-transcribed later with a better model. At 16 kHz
that holds for any ASR in sight — they all consume 16 kHz — but it does **not** hold for uses that
want the acoustic detail rather than the words: acoustic speaker attribution as the fallback if
text-only attribution proves inadequate (**R12**), or any forensic question about the recording
itself. Those are foreclosed by this decision and cannot be recovered afterwards.

That is the trade being made: **the archive is now a faithful record of what the transcriber heard,
not of what the microphone captured.** The earlier decision put it the other way round.

## Why it was 48 kHz until 2026-08-11 — kept so this is not relitigated a third time

The original reasoning, recorded here because it was not foolish and someone will reach for it
again: an archive kept for corroboration should not be a *resampled derivative* of the record.
48 kHz is what the hardware produces (**V7**); 16 kHz is merely what the inference path happens to
consume. On that view, storing 16 kHz means the only surviving copy of a hearing has already been
degraded by a processing decision, and the 3x disk cost was accepted for it.

What changed is not the principle but its price. Three separate things had been assumed and were
then measured: that a higher rate might help transcription (it cannot), that keeping both rates was
free (it costs an extra path, and that path was the one broken), and that the evidentiary value
justified the cost (it does, but only for non-ASR uses, which are not in this product's scope).

**If you are considering reversing this again**, the question to answer first is whether acoustic
analysis of the recording — not the transcript — has become a real requirement. If it has, this
decision should change. If it has not, nothing in the ASR path will ever ask for 48 kHz.

## Consequences

- The capture stream resamples **once**, at the device boundary, and `transcriber.py`'s
  `sample_rate = 16000` becomes the single rate in the pipeline rather than one of two.
- **V12** stays open and becomes *more* load-bearing, not less: whether PortAudio resamples a
  48 kHz-only source down to 16 kHz on request, or whether that has to be done in software, is now
  the only rate conversion in the system. It still needs measuring on hardware.
- The retention item's sizing table uses the 16 kHz row: **115 MB per hour per track**, ~690 MB for
  a three-hour hearing across both.
- `webrtcvad` accepting 48 kHz (measured 2026-08-11) is no longer needed for the archive path. It
  remains relevant only if a future VAD choice wants to run before the resample.
