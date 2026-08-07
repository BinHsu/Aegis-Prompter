# AGENTS.md — Working on Aegis Prompter

Aegis Prompter is a **100% offline, multi-role teleprompter** for high-pressure meetings,
built for Apple Silicon. It transcribes two audio tracks on the Mac NPU via `MLX-Whisper`,
matches the far-end speech against a local vector index to trigger pre-written defensive
scripts, and lets a remote staff operator inject live cues into the speaker's display.

> Project status, roadmap, and known issues live in **[STATE.md](STATE.md)**.
> This file is about *how to work in the repo*, not what is left to do.

## Commands

```bash
bash setup_mac.sh                # idempotent setup: portaudio, BlackHole, .venv, deps
source .venv/bin/activate        # setup_mac.sh does NOT activate for you
python src/build_index.py        # compile context/docs/*.{md,txt} -> context/knowledge_index.pkl
streamlit run src/app.py         # run the app (serves on :8501, prints LAN URL + 4-digit PIN)
bash run_tests.sh                # unit tests (requires .venv to already exist)
```

Ad-hoc test run without the wrapper script — `PYTHONPATH` **must** be the repo root:

```bash
PYTHONPATH="$PWD" .venv/bin/python -m pytest tests/unit -q
```

## Standards

- **English-only codebase.** Variables, docstrings, comments, console logs, and test
  assertions are all in English. This was a full-repo migration; do not reintroduce
  Chinese into code. User-facing README prose is intentionally bilingual.
- **Documentation Sync.** Whenever you add a feature, change architecture, or introduce a
  configuration toggle (e.g. a new `.env` flag), you MUST evaluate whether `README.md`
  needs updating to keep the user manual accurate.
- Notable changes go in `CHANGELOG.md`; project state goes in `STATE.md`.

## Architecture

| File | Role |
|---|---|
| `src/app.py` | Streamlit UI, PIN auth, role routing, polling loop |
| `src/global_state.py` | `GlobalState` singleton — owns both transcribers and the RAG worker thread |
| `src/transcriber.py` | One audio device → VAD → NPU inference → buffer. Instantiated twice |
| `src/dialogue_buffer.py` | Thread-safe transcript ring buffer + session archiving to `history/` |
| `src/local_advisor.py` | Loads the vector index, cosine-similarity trigger matching |
| `src/build_index.py` | Offline knowledge compiler (`.md`/`.txt` → pickled embeddings) |

Audio flows as **two independent tracks**, never mixed: the hardware mic is the
`Speaker (You)` role, and the BlackHole loopback is the `Participant` role. Each gets its
own `Transcriber` instance with its own VAD state and queues.

## Gotchas

- **Two import conventions.** At runtime `app.py:19` appends `src/` to `sys.path`, so
  modules import each other bare (`from global_state import ...`). Tests import with the
  package prefix (`from src.dialogue_buffer import ...`) and need `PYTHONPATH` at the repo
  root. Don't "fix" one to match the other without changing both.
- **`NPU_LOCK` in `transcriber.py` is load-bearing.** Concurrent Metal access from the two
  transcriber threads crashes the process. Every `mlx_whisper` call — including the
  warm-up call in `__init__` — must hold it.
- **Never block the audio callback.** `_audio_callback` only does VAD and enqueues.
  Whisper inference lives on a separate `inference_queue` + thread precisely because
  running it inline dropped frames. Keep that separation.
- **`GlobalState` is a singleton behind `@st.cache_resource`.** Streamlit re-runs the whole
  script on every poll tick, so module-level code executes constantly. Anything expensive
  or stateful must sit behind the singleton or a cache decorator.
- **Audio devices are matched by name substring**, not index — see
  `Transcriber.find_device_index`. Device indices shift between runs, so never hardcode one.
- **`context/` is gitignored.** The knowledge base is the user's private notes. Tests must
  never depend on real files there; build fixtures with `tmp_path`.
- **`build_index.py` chunks on double-newlines** and drops chunks of 10 characters or
  fewer (`build_index.py:47`). Blank lines inside a Q&A block split it into separate
  vectors and weaken matching.
- **`MULTILINGUAL_MODE` is a compile-time flag only.** It is read in `build_index.py:18` to
  pick the embedding model, and the choice is then baked into the pickle as `model_name`.
  `local_advisor.py:40` always loads whatever the bundle recorded, so editing `.env` has
  **no effect until you recompile the index**. Compiling non-English notes under the
  English-only `all-MiniLM-L6-v2` yields an index that loads fine but never matches.
- **`.env` is gitignored**; `.env.example` is the tracked template. Update both together.
