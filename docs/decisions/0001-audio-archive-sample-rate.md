# 0001 — Retained audio is archived at 48 kHz

- **Status:** accepted
- **Decided:** 2026-08-07 · **Recorded:** 2026-08-10
- **Follows from:** R3, R16, V7, V12

## Context

Dual-track audio may optionally be retained, for post-processing and for **corroboration** —
settling disputes about what was actually said (**R16**) — under a stance that makes completeness of
capture the system's own responsibility (**R3**).

The capture path opens its streams at 16 kHz today, because that is what `mlx_whisper` consumes and
what `webrtcvad` needs at the 30 ms block size in use. The Core Audio process tap, measured in
**V7**, produces 48 kHz mono float32. So there were two candidate archive rates: 16 kHz, matching
what the inference path actually processed, or 48 kHz, matching what the hardware produced.

The plan originally suggested 16 kHz, reasoning that the record would then match the transcript.

## Decision

**Archive at 48 kHz.**

16 kHz is merely what the inference path happens to consume. 48 kHz is the rate the hardware
produces. Archiving at 16 kHz would store a resampled *derivative* of the record — and an archive
whose entire purpose is corroboration must not be a derivative of the thing it corroborates.

The disk cost is accepted: 691 MB per hour for both tracks and roughly 2.1 GB for a three-hour
hearing, against 230 MB and ~690 MB at 16 kHz.

## Consequences

- The capture stream must open at **48 kHz**, which moves resampling out of the audio device and
  into the software path. **V12**'s fallback — run VAD at 48 kHz and resample only immediately
  before inference — becomes the *mandatory* design rather than a contingency.
- Audio retention is therefore coupled to the process-tap work. It can no longer be built as an
  isolated writer thread bolted onto an existing 16 kHz stream.
- `transcriber.py` hardcodes `sample_rate = 16000`, and `webrtcvad` accepts 48000, so the code
  change is confined to stream setup plus one resample step ahead of `inference_queue`.
- **V12 is still unverified.** Whether PortAudio resamples on its own was never tested, and this
  decision makes that measurement load-bearing rather than incidental.
- The archive stops matching the transcript sample-for-sample. Mapping a transcript timestamp to an
  offset in the WAV now requires the session start time to be recorded precisely — which **R16**'s
  corroboration use already depended on.
