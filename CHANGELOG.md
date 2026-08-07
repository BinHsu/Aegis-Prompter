# Changelog

All notable changes to this project are documented in this file.

## [0.0.1] — 2026-08-07

First tagged release. A fully offline, multi-role teleprompter for Apple Silicon,
using the **BlackHole** virtual audio driver to capture the far-end participant.

### Added
- **Multi-Role Teleprompter** — role routing via query parameter (`?role=speaker` vs
  `?role=staff`). The speaker gets a clean auto-scrolling view; staff get a tactical
  control panel that injects live cues into the speaker's display over the local network.
- **Dual-Track Apple Silicon Transcriber** — `MLX-Whisper` on the Mac NPU, with the
  hardware microphone (You) and the BlackHole loopback (Them) transcribed as separate
  roles. A global NPU lock prevents concurrent Metal access from crashing.
- **Vector Semantic RAG** — `src/build_index.py` compiles `.md`/`.txt` knowledge files
  into `context/knowledge_index.pkl`; `src/local_advisor.py` matches transcribed dialogue
  by cosine similarity to trigger pre-written defensive scripts. No LLM generation, so no
  hallucinated advice.
- **Pure Teleprompter Mode** — `ENABLE_LOCAL_RAG=false` disables all vector computation
  and runs as a lightweight manual-only teleprompter.
- **Session archiving** — each session is written to a Markdown transcript under `history/`.
- **PIN-gated remote access** — a randomized 4-digit PIN printed at startup guards the UI
  on remote devices.
- `MULTILINGUAL_MODE` toggle.
- `LICENSE` file (MIT), matching the license already declared in `README.md`.
- `setup_mac.sh` — idempotent setup installing Homebrew deps, `portaudio`, and BlackHole.
- Unit test suite (`tests/unit`) with `run_tests.sh`.

### Changed
- Replaced the Gemini API advisor with the pure-local vector RAG advisor;
  `src/gemini_advisor.py` removed and `google-genai` dropped from `requirements.txt`.
- Translated the entire codebase to English (variables, docstrings, console logs, tests).
- Renamed `CLAUDE.md` to `AGENTS.md`; `CLAUDE.md` now imports it.

### Fixed
- **Dropped audio frames under NPU load** — the audio pipeline is decoupled from Whisper
  inference via a dedicated `inference_queue` and inference thread, so the CoreAudio
  callback never blocks on the NPU.
- **Failing buffer tests** — `tests/unit/test_buffer.py` still asserted the
  pre-translation Chinese strings (`"等待對話..."`) against the translated code
  (`"Awaiting dialogue..."`). Suite is now green (8 passed).

### Known Issues
- Requires the BlackHole virtual driver plus a Multi-Output Device for the speaker to
  hear the meeting while it is being captured. Replacing this with the native Core Audio
  process-tap API is evaluated and planned — see `AGENTS.md`.
- Microphone auto-detection keywords in `global_state.py` do not match MacBook Pro
  hardware and fall through to the system default input.
