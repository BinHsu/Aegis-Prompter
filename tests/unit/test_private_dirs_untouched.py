"""Nothing in the suite may write into the operator's private directories.

**This exists because the rule was already broken twice.** `AGENTS.md` forbids tests reading,
writing or fabricating anything in `.env`, `context/`, `history/` or `logs/`, and records the first
breach: a test called a delete helper with its default argument, and that default was the real
`.env`. The second was found on 2026-08-21 -- `test_rag_gate.py` reached `start_recording`, which
calls `buffer.start_session(session_id, retention=...)` with no `history_dir`, so it defaulted to the
real one and **every run wrote a session record into the operator's meeting history**. 131
header-only files had accumulated there.

Both breaches share a shape: a default argument that happens to be the production path. Neither was
caught by review, because the calling code looks correct and says nothing about where it writes. So
this file does not inspect code -- it counts files before and after, which is the only check that
cannot be argued with.
"""
import glob
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WATCHED = ("history", "context", "logs")


def _snapshot():
    """Path -> mtime for everything currently in the watched directories."""
    seen = {}
    for name in WATCHED:
        root = os.path.join(REPO, name)
        for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
            if os.path.isfile(path):
                seen[path] = os.stat(path).st_mtime
    return seen


def test_no_test_writes_into_the_real_private_directories():
    """Run the rest of the suite in a subprocess and assert the private directories are untouched.

    A subprocess rather than an in-process fixture, because a fixture cannot observe what happened
    before it was set up, and the breach this guards happened during collection-time module import
    in one earlier variant.
    """
    before = _snapshot()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", os.path.join(REPO, "tests", "unit"), "-q",
         "--ignore", os.path.abspath(__file__), "-p", "no:cacheprovider"],
        cwd=REPO, env={**os.environ, "PYTHONPATH": REPO},
        capture_output=True, text=True, timeout=900,
    )
    after = _snapshot()

    created = sorted(set(after) - set(before))
    modified = sorted(p for p in set(after) & set(before) if after[p] != before[p])
    assert not created, (
        f"the suite created {len(created)} file(s) in the operator's private directories: "
        f"{[os.path.relpath(p, REPO) for p in created[:5]]}"
    )
    assert not modified, (
        f"the suite modified {len(modified)} file(s) there: "
        f"{[os.path.relpath(p, REPO) for p in modified[:5]]}"
    )
    assert result.returncode == 0, f"the inner suite failed:\n{result.stdout[-2000:]}"
