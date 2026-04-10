# Phase 6: Staff Officer Prompter Rebuild State

This file tracks the transition of the Staff Officer project from a Gemini-dependent script to a **Pure Local + Multi-Role** architecture (English-only codebase), as mandated by the Phase 6 implementation plan.

## 🔴 Pending Tasks
- **Knowledge Compiler (`src/build_index.py`)**: Needs parsing logic and vector embedding generation to compile `.md/.txt` files into `knowledge_index.pkl`.
- **Pure Local RAG (`src/local_advisor.py`)**: Needs implementation to load the vector index and execute fast cosine-similarity-based trigger matching. Old `gemini_advisor.py` must be deprecated.
- **State & UI Refactor (`app.py`, `global_state.py`)**: 
  - Everything MUST be translated to English (variables, docstrings, console logs).
  - Add query-parameter logic for role routing (`?role=speaker` vs `?role=staff`).
  - The staff role needs a manual broadcast UI input to push messages to `global_state.buffer`.
  - **Auto-scroll UX**: The prompter UI must dynamically slice and limit text to the latest 4-5 lines so the layout never expands out of bounds and the speaker doesn't need to manually scroll.

## 🧠 Development Standards
- **Documentation Sync**: Whenever a new feature, architecture change, or configuration toggle (like `.env` flags) is implemented, you MUST evaluate whether it needs to be documented in `README.md` to keep the user manual up to date.

## 🟢 Completed Steps
- Defined Phase 6 Implementation Plan.
- Switched licensing to MIT.
- Updated `requirements.txt` to remove `google-genai` and insert `sentence-transformers`.
- Updated `.env` to support `MULTILINGUAL_MODE`.
- Created this `CLAUDE.md` to track progress!
