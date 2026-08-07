# Project State

Tracks progress, roadmap, and open issues. For how to work in the repo, see
[AGENTS.md](AGENTS.md). For the release history, see [CHANGELOG.md](CHANGELOG.md).

**Current release: `v0.0.1`** — BlackHole audio backend.

## 🧭 Design stance

> **Whatever your ears can hear and whatever your mouth says, we ingest.**

Capture is deliberately **source-agnostic**. It does not matter whether the meeting runs in
Zoom's native app, Meet in a browser tab, Teams, or anything else — the system takes the
entire system output mix as one track and the microphone as the other. There are exactly
**two tracks, forever**, and the existing dual-`Transcriber` architecture is exactly the
right shape for that.

Consequences that follow directly from this stance, and should not be relitigated without
revisiting the stance itself:

- **No per-application audio filtering.** Tapping "only Zoom" is useless when the meeting is
  a browser tab (tapping Chrome captures all of Chrome), and a bundle-ID allowlist is
  unmaintainable across apps the user may switch between. Take the global mix.
- **Noise is accepted at the capture layer and filtered downstream.** Spotify, Slack chimes,
  and notification sounds will enter the participant track. The defences are `webrtcvad`
  (severity 3), Whisper's `no_speech_threshold`, and the anti-hallucination blacklist in
  `transcriber.py`. Note VAD is unreliable on *music*, which can be misclassified as speech
  and then hallucinated into text.
- **Headphones are an operational requirement, not a preference.** See Known Issues.

## 🟢 Completed — Phase 6

Transition from a Gemini-dependent script to a **Pure Local + Multi-Role** architecture
with an English-only codebase.

- Defined the Phase 6 implementation plan.
- Switched licensing to MIT; added the `LICENSE` file.
- Updated `requirements.txt` to drop `google-genai` and add `sentence-transformers`.
- Added `MULTILINGUAL_MODE` support to `.env`.
- **Knowledge Compiler (`src/build_index.py`)** — compiles `.md`/`.txt` into
  `context/knowledge_index.pkl` via `sentence-transformers`.
- **Pure Local RAG (`src/local_advisor.py`)** — loads the vector index and runs
  cosine-similarity trigger matching. `gemini_advisor.py` removed.
- **State & UI refactor (`app.py`, `global_state.py`)**
  - Codebase translated to English. `tests/unit/test_buffer.py` was the last holdout — its
    assertions still expected the pre-translation Chinese strings and failed until fixed.
  - Role routing via query parameter (`?role=speaker` vs `?role=staff`).
  - Staff manual broadcast UI pushing into `global_state.buffer`.
  - Auto-scroll UX via `get_formatted_dialogue(max_lines=5)`.
- **Decoupled the audio pipeline from the NPU bottleneck** to stop dropped frames —
  `transcriber.py` now uses a separate `inference_queue` and a dedicated inference thread.

---

# 🔵 Phase 7 Roadmap

Five goals, in the order they should be executed. Order is chosen so that each step is
independently shippable and the riskiest work lands last.

## 7.1 — Multilingual ASR (EN + ZH in one meeting) 🔴 BLOCKING BUG

**The current model cannot transcribe Chinese at all.** `transcriber.py` defaults to
`mlx-community/distil-whisper-large-v3`, and Distil-Whisper is **English-only** by design —
its 6x speedup comes precisely from being trained on English audio only. This is not a
quality problem; Chinese is simply unsupported.

**`MULTILINGUAL_MODE` does not do what its name implies.** It appears only in
`build_index.py`, where it selects the *RAG embedding model*. It has never reached the ASR
layer. Setting it to `true` gives multilingual retrieval over an English-only transcript.

Plan:

1. Switch the default to **`mlx-community/whisper-large-v3-turbo`** — multilingual (99+
   languages), 1.61 GB in quantized MLX form, roughly 5x faster than `large-v3`.
2. **Make `MULTILINGUAL_MODE` govern both layers** (ASR model *and* embedding model) so the
   flag is finally honest.
3. **Handle Traditional vs Simplified Chinese.** Whisper has a single `zh` token and was
   trained on a mix, so it will sometimes emit Simplified characters. Simplified text on a
   Taiwanese teleprompter is a hard failure. Mitigation: a Traditional-Chinese
   `initial_prompt` to bias decoding, plus OpenCC post-processing as a backstop.
4. **Re-measure latency.** `turbo` is faster than `large-v3` but slower than `distil`, and
   two tracks share `NPU_LOCK`. Confirm `audio_queue` does not start dropping frames again —
   that regression was only fixed in `201eeea`.

Already favourable: no architectural change is needed for code-switching. Each VAD segment
is a separate `transcribe()` call with no `language` argument, so language is auto-detected
per chunk. Intra-*sentence* code-switching will still be weak — a Whisper limitation, not
fixable by model choice.

Risk: `turbo` is known to be slightly weaker than `large-v3` on some languages. Mandarin is
generally fine, but this must be measured on real meeting audio, not inferred from specs.

## 7.2 — Core Audio process tap, as the default backend

Replace BlackHole with the native Core Audio process-tap API. Feasibility was verified
empirically on macOS 26.6 using Command Line Tools `clang` only — no Xcode required.

Verified findings:

- `AudioHardwareCreateProcessTap` is `API_AVAILABLE(macos(14.2))` — **14.2, not 14.4**.
- **A global mono mixdown tap is the shape we want** (`initMonoGlobalTapButExcludeProcesses`
  with an empty exclude list), per the design stance above. Measured: `err=0`, format
  **48kHz / mono / float32 packed**, and 190,976 frames captured over 4 seconds with real
  signal (`peak=0.297`).
- **Dropping per-app capture lowers the OS requirement from 26.0 to 14.2.**
  `CATapDescription.bundleIDs` and `.processRestoreEnabled` are the only members needing
  macOS 26.0, and a global tap needs neither — it does not care whether Zoom restarts.
- A tap exposed through a **non-private aggregate device is visible cross-process** as an
  ordinary input device. This is the key architectural result: `sounddevice`/PortAudio
  enumerate it like any mic, so **`transcriber.py` needs no changes** — only the device
  keyword list in `global_state.py`.
- `muteBehavior = CATapUnmuted` lets the user keep hearing the audio, removing the need for
  a Multi-Output Device (BlackHole requires one or the speaker goes deaf).
- **TCC**: tap capture triggers a `kTCCServiceAudioCapture` check, attributed to the
  **responsible process — the terminal app (e.g. `Terminal.app`), not the tap binary**. This
  is *not* a new class of risk: the BlackHole path already requires that same responsible
  process to hold `kTCCServiceMicrophone`.

Open risks:

- **Sample rate is the one unverified integration point.** The tap is fixed at 48kHz but
  `transcriber.py` opens the stream at 16kHz; whether PortAudio resamples is untested. This
  is the first thing to hit during implementation. `webrtcvad` accepts 48000, so the fallback
  is to run VAD at 48k and resample only before Whisper.
- **Largest ongoing cost**: the aggregate device binds a specific output device as its main
  sub-device, so it goes stale when the user switches output (plugging in headphones).
  Requires a `kAudioHardwarePropertyDefaultOutputDevice` listener to rebuild. BlackHole does
  not have this problem — the only respect in which it is superior.

Plan — **additive backend first, then flip the default**:

1. Add `src/native/aegis_tap.m`, compiled by `setup_mac.sh`.
2. `global_state.py` launches it as a subprocess in `start_recording()`, SIGTERMs it in
   `stop_recording()`.
3. Add `AUDIO_BACKEND=tap|blackhole` to `.env` and `.env.example`; document in `README.md`.
4. Prove it in real meetings, **then** make `tap` the default.
5. Keep the BlackHole fallback permanently — it covers macOS older than 14.2.

## 7.3 — Device selection in the web UI

**Decision: the dropdown remote-controls the host Mac's capture devices. It is not a browser
device picker.** Browser-side capture (`getUserMedia`, as Zoom/Meet web do it) was
considered and rejected as *impossible*, for two independent reasons:

1. **The remote iPad cannot access the API at all.** `navigator.mediaDevices` is
   `[SecureContext]`; outside a secure context it is `undefined` and calling `getUserMedia()`
   throws `TypeError`. Secure contexts are HTTPS, `file://`, and **localhost** —
   `http://192.168.x.x:8501` is none of these. Only the browser on the Mac itself qualifies.
2. **Even locally, the browser cannot supply the participant track.** Safari on macOS does
   not support `getDisplayMedia` audio at all; Firefox ignores it; Chrome supports tab audio,
   and system audio only from Chrome 141+ on macOS 14.2+ — which is itself built on the very
   same Core Audio process tap. Going through the browser yields a more constrained version
   of what the native tap already gives us.

So the browser could at best supply the Mac's microphone, which server-side PortAudio
already does better: no encoding, no transport, no permission prompt.

This framing is *more* useful than the Zoom/Meet model for this product: staff off-stage can
retune the speaker's capture from an iPad without touching the Mac.

Scope, reduced by the design stance — if system audio is "everything", there is no source to
choose:

- **Microphone dropdown** — genuinely useful (built-in / AirPods / USB mic).
- **Backend selector** (`tap` / `blackhole`) — transitional; can be retired later.
- No system-audio source dropdown. It was going to be two dropdowns; it is one.

Implementation note: the UI already has half of this. The `st.progress(rms)` level meters in
`app.py` are exactly the meter Zoom shows beside its device picker, so dropdown + existing
meter gives the familiar UX with no new visual work.

Implementation trap: `Transcriber.__init__` preloads the Whisper model into the NPU, which is
slow. Switching devices must **not** naively reconstruct a `Transcriber` — separate "change
device" from "reload model".

Bonus: a dropdown makes the hardcoded-microphone-keyword bug (Known Issues) irrelevant.

## 7.4 — Speaker diarization (Participant A / B) — do last

Scope: **the microphone track does not need this** (one person). Only the system-audio track
does, since all remote participants arrive mixed into one stream.

Whisper does not diarize; this needs a second model. Candidates: pyannote segmentation 3.0
exported to ONNX by sherpa-onnx (a single 6.6 MB file), or FluidAudio (native Swift + MLX).
Caveat: sherpa-onnx on macOS has **no ANE support** and runs on CPU.

The real difficulty is architectural, not the model. The current pipeline flushes on 0.4s of
silence and transcribes each segment in isolation, but diarization needs continuous audio to
cluster speaker embeddings. That means maintaining a **separate rolling raw-audio buffer**
alongside the existing VAD segmentation.

Why this is last, and why it needs a spike before any commitment:

- Speaker embeddings are unreliable on segments under ~1 second — and short interjections are
  exactly the hostile-questioning case this product exists for.
- The design stance makes it harder: music and unrelated audio in the global mix contaminate
  speaker clustering.

## 🐛 Known Issues

- **Speaker-audio echo causes double transcription and false RAG triggers.** If the speaker
  uses loudspeakers instead of headphones, the microphone also picks up the far end, so the
  same utterance is transcribed twice — once as `Speaker (You)` and once as `Participant`.
  Because `_local_rag_worker_loop` only fires on `role == "Participant"`, the speaker's own
  echoed voice can trigger defensive cues. This affects BlackHole today and will affect the
  tap equally; it is not introduced by either. Practical mitigation: **require headphones or
  an earpiece** — normal in hearings and earnings calls anyway. A software fix means AEC,
  which is far more expensive.
- **`MULTILINGUAL_MODE` is misleadingly named** — it only selects the RAG embedding model,
  never the ASR model. Being fixed in 7.1.
- `global_state.py` looks for `["MacBook Air Microphone", "Built-in Microphone"]`. On a
  MacBook Pro neither keyword matches, so mic selection silently relies on
  `fallback_to_default`. The result is usually correct, but the keyword list is not doing
  its job. Superseded by 7.3.
- Capturing the far end currently requires the BlackHole driver *plus* a manually configured
  Multi-Output Device, otherwise the speaker cannot hear the meeting while it is captured.
  Superseded by 7.2.
