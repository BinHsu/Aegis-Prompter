"""Keep the suite out of the operator's private directories.

`AGENTS.md` forbids tests reading, writing or fabricating anything in `.env`, `context/`,
`history/` or `logs/`. Two breaches were found on 2026-08-21, both with the same shape -- a default
argument that happened to be the production path:

- `start_recording` calls `buffer.start_session(...)` with no `history_dir`, so it wrote a session
  record into the real meeting history on every run of `test_rag_gate.py`. 131 header-only files had
  accumulated.
- `global_state` builds a `logging.FileHandler` **at import time**, so every test importing it left
  an engine log behind. 1268 had accumulated.

The second is why this file exists rather than a fixture: a handler created during module import
cannot be redirected by a fixture that runs afterwards, so the environment variable has to be set
before any test imports `global_state`. `test_private_dirs_untouched.py` is the check that this
keeps working -- it counts files rather than trusting this comment.
"""
import os
import tempfile

_LOG_DIR = os.path.join(tempfile.gettempdir(), "aegis-test-logs")
os.makedirs(_LOG_DIR, exist_ok=True)
os.environ.setdefault("AEGIS_LOG_DIR", _LOG_DIR)
