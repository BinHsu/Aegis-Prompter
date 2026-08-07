# Aegis Prompter — Project State

This file tracks the state of the Staff Officer project after its transition from a
Gemini-dependent script to a **Pure Local + Multi-Role** architecture (English-only
codebase), as mandated by the Phase 6 implementation plan.

**Current release: `v0.0.1`** — BlackHole audio backend.

## 🧠 Development Standards
- **Documentation Sync**: Whenever a new feature, architecture change, or configuration toggle (like `.env` flags) is implemented, you MUST evaluate whether it needs to be documented in `README.md` to keep the user manual up to date.
- **English-only codebase**: All variables, docstrings, comments, console logs, and test assertions must be in English.

## 🟢 Completed — Phase 6
- Defined Phase 6 Implementation Plan.
- Switched licensing to MIT; added the `LICENSE` file.
- Updated `requirements.txt` to remove `google-genai` and insert `sentence-transformers`.
- Updated `.env` to support `MULTILINGUAL_MODE`.
- **Knowledge Compiler (`src/build_index.py`)**: compiles `.md`/`.txt` into `context/knowledge_index.pkl` via `sentence-transformers`.
- **Pure Local RAG (`src/local_advisor.py`)**: loads the vector index and runs cosine-similarity trigger matching. `gemini_advisor.py` removed.
- **State & UI Refactor (`app.py`, `global_state.py`)**:
  - Codebase translated to English (`tests/unit/test_buffer.py` was the last holdout — its assertions still expected the pre-translation Chinese strings and failed until fixed).
  - Role routing via query parameter (`?role=speaker` vs `?role=staff`) — `app.py:96`.
  - Staff manual broadcast UI pushing into `global_state.buffer` — `app.py:183`.
  - Auto-scroll UX via `get_formatted_dialogue(max_lines=5)` — `app.py:164`.
- **Decoupled audio pipeline from the NPU bottleneck** to stop frames dropping (`transcriber.py` now uses a separate `inference_queue` + dedicated inference thread).

## 🔵 Next: Core Audio Process Tap (evaluated, not yet implemented)

Goal: replace the BlackHole dependency with the native Core Audio process-tap API.
Feasibility was verified empirically on macOS 26.6 using Command Line Tools `clang`
only (no Xcode required). Findings worth keeping:

- `AudioHardwareCreateProcessTap` is `API_AVAILABLE(macos(14.2))` — **14.2, not 14.4**.
  `CATapDescription.bundleIDs` and `.processRestoreEnabled` require macOS 26.0.
- Tap stream format is fixed at **48kHz / float32**; a mono mixdown tap yields 1 channel.
  `transcriber.py` requests `samplerate=16000`, so resampling behaviour through
  PortAudio is **the one integration point still unverified**. `webrtcvad` accepts
  48000, so the fallback is to run VAD at 48k and resample only before Whisper.
- A tap exposed through a **non-private aggregate device is visible cross-process** as an
  ordinary input device. This is the key architectural result: `sounddevice`/PortAudio
  enumerate it like any mic, so **`transcriber.py` needs no changes** — only the device
  keyword list in `global_state.py:77`.
- `muteBehavior = CATapUnmuted` lets the user keep hearing the audio, removing the need
  for a Multi-Output Device (BlackHole requires one or the speaker goes deaf).
- **TCC**: tap capture triggers a `kTCCServiceAudioCapture` check, and TCC attributes it
  to the **responsible process — the terminal app (e.g. `Terminal.app`), not the tap
  binary**. This is *not* a new class of risk: the existing BlackHole path already
  requires that same responsible process to hold `kTCCServiceMicrophone`.
- **Largest ongoing cost**: the aggregate device binds a specific output device as its
  main sub-device, so it goes stale when the user switches output (plugs in headphones).
  Requires a `kAudioHardwarePropertyDefaultOutputDevice` listener to rebuild.
  BlackHole does not have this problem — the only respect in which it is superior.

Planned approach — **additive backend, BlackHole retained as fallback**:
- Add `src/native/aegis_tap.m`, compiled by `setup_mac.sh`.
- `global_state.py` launches it as a subprocess in `start_recording()`, SIGTERMs it in `stop_recording()`.
- Add `AUDIO_BACKEND=tap|blackhole` to `.env` (and document it in `README.md`).
- Fall back to BlackHole when the tap device is absent or macOS is older than 14.2.

## 🐛 Known Issues
- `global_state.py:76` looks for `["MacBook Air Microphone", "Built-in Microphone"]`.
  On a MacBook Pro neither keyword matches, so mic selection silently relies on
  `fallback_to_default`. The result is usually correct but the keyword list is not
  doing its job.
