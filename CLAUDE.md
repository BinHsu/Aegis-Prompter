# Phase 6: Staff Officer Prompter Rebuild State

This file tracks the transition of the Staff Officer project from a Gemini-dependent script to a **Pure Local + Multi-Role** architecture (English-only codebase), as mandated by the Phase 6 implementation plan.

## 🔴 Pending Tasks (P1 — deferred, not yet addressed)
- **Window-mode `word_timestamps` (deferred "1a")**: `Transcriber._decode` still passes `word_timestamps=True` even in `window` mode, where only the whole-utterance text is committed. Word timestamps are needed only by `localagreement` mode; computing them in window mode is wasted NPU work. Make it conditional on `mode == "localagreement"`.
- **Live throughput / thermal throttling**: Sustained dual-mic Whisper passes on the NPU can throttle on long meetings. The durable-capture + offline retranscribe path now guarantees a lossless record as a backstop, but the live path's throughput under thermal pressure is not yet measured or tuned.

## 🧠 Development Standards
- **Documentation Sync**: Whenever a new feature, architecture change, or configuration toggle (like `.env` flags) is implemented, you MUST evaluate whether it needs to be documented in `README.md` to keep the user manual up to date.

## 🟢 Completed Steps
- Defined Phase 6 Implementation Plan.
- Switched licensing to MIT.
- Updated `requirements.txt` to remove `google-genai` and insert `sentence-transformers`.
- Updated `.env` to support `MULTILINGUAL_MODE`.
- Created this `CLAUDE.md` to track progress!
- **Knowledge Compiler (`src/build_index.py`)**: Parses `.md/.txt` into `knowledge_index.pkl` vector embeddings.
- **Pure Local RAG (`src/local_advisor.py`)**: Loads the vector index and runs cosine-similarity trigger matching. `gemini_advisor.py` deprecated/removed.
- **State & UI Refactor (`app.py`, `global_state.py`)**: English-only artifacts; `?role=speaker` / `?role=staff` routing; staff manual-broadcast UI; auto-scroll UX limited to the latest ~5 lines.
- **Anti-data-loss durable raw-audio capture (`src/transcriber.py`, `src/global_state.py`)**: Each session writes one lossless mono 16kHz/16-bit WAV per track to `recordings/<session_id>/<Track>.wav` via a dedicated writer thread off the audio callback, plus a `_final_flush` that decodes residual audio at shutdown. A whole-utterance exact-match hallucination filter (`_acceptable` / `_normalize_phrase`) replaces the old substring filter, so real speech containing "謝謝"/"thank you" survives.
- **Offline / batch re-transcription (`src/retranscribe.py`)**: Ungated, loss-free engine. `python3 src/app.py -at <audio> -o <out.txt>` (single file; `app.py` routes batch away from Streamlit before importing it) and `python src/retranscribe.py recordings/<session_id>/` (per-track WAV merge → `transcript.md`/`.txt`). Channel-split limited to 16kHz 16-bit WAV to avoid new pip dependencies.
- **BVA unit tests (`tests/unit/test_transcriber.py`)**: Pure-function boundary tests for `_acceptable`, `_float_to_int16`, `slug_track_name`, and `should_run_batch` — no model load.
- **`.gitignore`**: Added `recordings/` (durable capture + generated transcripts are not committed).
