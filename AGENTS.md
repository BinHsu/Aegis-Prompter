# AGENTS.md

Boundaries for agents working in this repo. Not a manual — the code is the manual.

Aegis Prompter is a 100% offline, multi-role teleprompter for Apple Silicon.

## Where to look things up

Do not build a mental map by grepping the tree, and do not trust any hand-written
architecture description — including one in this file.

| Question | Source of truth |
|---|---|
| Does this file / class / function exist, and where? | `FILEMAP.md` (generated) |
| What must the product do, what has been measured, what is ruled out? | `REQUIREMENTS.md` |
| Where is the project now, and what is next? | `STATE.md` |
| Why was a rejected option rejected, and when? | `docs/decisions/` |
| What shipped, and when? | `CHANGELOG.md` |
| How does a user set this up and run it? | `README.md` |

`REQUIREMENTS.md` and `STATE.md` split along one line: **does the statement stop being true once
the work is done?** If yes it is a plan item or a known issue, and it lives in `STATE.md`, which is
rewritten freely. If no it is a requirement (`R*`), a measured constraint (`V*`), or a closed
decision, and it lives in `REQUIREMENTS.md`, where a large deletion is a warning sign rather than
routine tidying. Reference direction is one-way: the plan cites `R*`/`V*`, never the reverse.
`tools/check_state.py` enforces both.

**Both files are edited from outside this repo's normal loop.** External reviewers revise
`REQUIREMENTS.md` and `STATE.md` and commit directly, so their contents may have changed since any
previous session. **Re-read both at the start of a session and run `python tools/check_state.py`
before acting on them — never work from remembered content.** `git log --oneline REQUIREMENTS.md
STATE.md` shows what moved and when.

`FILEMAP.md` is **generated from the AST** by `tools/gen_filemap.py`. Never hand-edit it.

Three things regenerate it automatically: the `PostToolUse` hook in `.claude/settings.json`
(fires whenever an agent edits a `.py` file), `run_tests.sh`, and `setup_mac.sh`. If none of
those has run — a human editing by hand, or a fresh clone — regenerate it yourself:

```bash
python tools/gen_filemap.py            # rewrite
python tools/gen_filemap.py --check    # exit 1 if stale
```

If `FILEMAP.md` disagrees with the code, the code wins — regenerate rather than reason
from the stale copy.

## Hard rules

- **English-only codebase.** Variables, docstrings, comments, console logs, and test
  assertions. The repo went through a full migration off Chinese; do not reintroduce it.
  (`README.md` prose is intentionally bilingual — that is not code.)
- **Never read, commit, or fabricate the contents of `.env`, `context/`, `history/`, or
  `logs/`.** These are the user's private notes, meeting transcripts, and secrets. They are
  gitignored. Tests must build their own fixtures with `tmp_path` and must never depend on
  real files there.
- **`.env.example` is the tracked template.** Any new `.env` flag must be added to it in the
  same change.
- **Documentation Sync.** When you add a feature, change architecture, or introduce a
  configuration toggle, you MUST evaluate whether `README.md` needs updating. Put requirements and
  measured constraints in `REQUIREMENTS.md`, progress in `STATE.md`, and notable changes in
  `CHANGELOG.md` — not in this file.

## Invariants that break the app if violated

These are not style preferences. Each one exists because breaking it produced a real
failure. Read the surrounding code before touching any of them.

- **Serialize all NPU access.** Concurrent Metal calls from the two transcriber threads
  crash the process. Every `mlx_whisper` call, including the warm-up call, must hold the
  module-level lock in `transcriber.py`.
- **Never block the audio callback.** It may do VAD and enqueue, nothing more. Whisper
  inference runs on its own queue and thread specifically because running it inline dropped
  frames.
- **Match audio devices by name substring, never by index.** Device indices shift between
  runs and between machines.
- **Streamlit re-runs the entire script on every poll tick.** Anything expensive or
  stateful must live behind the `GlobalState` singleton or a cache decorator, never at
  module scope.

## Verifying your work

```bash
bash run_tests.sh                              # regenerates FILEMAP.md, then runs tests
PYTHONPATH="$PWD" .venv/bin/python -m pytest tests/unit -q   # ad-hoc; PYTHONPATH is required
```

Tests import with the `src.` prefix and need the repo root on `PYTHONPATH`. Runtime code
does not: `app.py` appends `src/` to `sys.path`, so the modules import each other bare.
Both conventions are load-bearing — do not align one to the other without changing both.

Do not report tests as passing without having run them.
