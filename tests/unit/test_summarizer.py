"""Pure-function BVA unit tests for the local-LLM summary layer.

These tests must run WITHOUT loading any model and WITHOUT requiring mlx-lm. summarizer imports
mlx_lm lazily (inside summarize()), so importing the module here proves that contract. `src/` is on
sys.path so the module imports under its package-free name, matching retranscribe's lazy
`import summarizer`."""
import os
import sys
import importlib

import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

import summarizer                                  # noqa: E402
from retranscribe import build_arg_parser          # noqa: E402


# ---------- build_summary_prompt (pure, no model) ----------

REQUIRED_HEADERS = ["TL;DR", "Key Points", "Decisions", "Action Items"]


def test_build_summary_prompt_contains_headers_and_no_hallucination_rule():
    prompt = summarizer.build_summary_prompt("Speaker: we ship on Friday.")
    for header in REQUIRED_HEADERS:
        assert header in prompt
    # The transcript text is embedded verbatim.
    assert "we ship on Friday" in prompt
    # The grounding / no-invention instruction is present.
    assert "Do NOT invent" in prompt
    # The "None" fallback instruction is present.
    assert "None" in prompt
    assert isinstance(prompt, str)


@pytest.mark.parametrize("transcript", [
    "",                                   # BVA: empty string
    "Hi.",                                # BVA: short single line
    "Speaker: a\nParticipant: b\nSpeaker: c",  # BVA: multi-line
])
def test_build_summary_prompt_valid_for_boundary_inputs(transcript):
    prompt = summarizer.build_summary_prompt(transcript)
    assert isinstance(prompt, str) and len(prompt) > 0
    # Headers are always present regardless of input size.
    for header in REQUIRED_HEADERS:
        assert header in prompt
    # Non-empty transcript content is embedded.
    if transcript:
        assert transcript.splitlines()[0] in prompt


def test_build_summary_prompt_handles_none():
    # None must not raise; it is coerced to an empty transcript.
    prompt = summarizer.build_summary_prompt(None)
    assert isinstance(prompt, str) and "TL;DR" in prompt


# ---------- resolve_summary_model (pure) ----------

def test_resolve_summary_model_default_and_override():
    assert summarizer.resolve_summary_model("") == summarizer.DEFAULT_SUMMARY_MODEL
    assert summarizer.resolve_summary_model("   ") == summarizer.DEFAULT_SUMMARY_MODEL
    assert summarizer.resolve_summary_model("custom/model") == "custom/model"
    assert summarizer.resolve_summary_model("  custom/model  ") == "custom/model"


# ---------- _auto_summarize_enabled (env flag BVA) ----------

@pytest.mark.parametrize("env_val, expected", [
    (None, True),        # unset -> default on
    ("", True),          # empty -> default on
    ("true", True),
    ("TRUE", True),      # case-insensitive
    ("false", False),
    ("FALSE", False),    # case-insensitive
    ("  false  ", False),  # whitespace tolerated
    ("0", True),         # only the literal "false" disables; everything else stays on
])
def test_auto_summarize_enabled(env_val, expected):
    assert summarizer._auto_summarize_enabled(env_val) is expected


# ---------- retranscribe --summarize argparse flag ----------

def test_summarize_flag_true_when_present():
    args = build_arg_parser().parse_args(["recordings/foo", "--summarize"])
    assert args.summarize is True


def test_summarize_flag_false_when_absent():
    args = build_arg_parser().parse_args(["recordings/foo"])
    assert args.summarize is False


# ---------- lazy-import contract: importing summarizer must NOT import mlx_lm ----------

def test_importing_summarizer_does_not_import_mlx_lm():
    # Drop any already-loaded mlx_lm + summarizer, reimport summarizer fresh, and confirm the
    # fresh import did not drag mlx_lm in. This proves the lazy-import keeps the no-summary paths
    # free of the heavy dependency.
    for mod in ("mlx_lm", "summarizer"):
        sys.modules.pop(mod, None)
    importlib.import_module("summarizer")
    assert "mlx_lm" not in sys.modules
