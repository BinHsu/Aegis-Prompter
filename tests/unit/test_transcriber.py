"""Pure-function BVA unit tests for the durable-capture transcriber helpers.

These tests cover ONLY staticmethods that do not touch hardware or load any model. Importing
`transcriber` / `retranscribe` is safe: model load happens inside `Transcriber.__init__`, which is
never called here. `src/` is added to sys.path so the modules import under their own package-free
names (matching how retranscribe.py imports `from transcriber import ...`)."""
import os
import sys

import numpy as np
import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from transcriber import Transcriber          # noqa: E402
from retranscribe import should_run_batch     # noqa: E402


# ---------- Transcriber._acceptable ----------

@pytest.mark.parametrize("text, expected", [
    # Bare known hallucinations are dropped (whole-utterance exact match).
    ("謝謝", False),
    ("Thank you.", False),
    # Real speech that merely CONTAINS a hallucination phrase survives.
    ("謝謝大家", True),
    ("Okay, thank you, see you", True),
    # Latin case is ignored.
    ("THANK YOU.", False),
    # Trailing punctuation / missing punctuation variants still match.
    ("謝謝。", False),
    ("Thank you", False),
    # A normal short non-phrase survives.
    ("OK", True),
])
def test_acceptable_phrase_matching(text, expected):
    assert Transcriber._acceptable(text) is expected


def test_acceptable_len_boundary():
    """BVA around the len<=1 guard (B=1): len 0 -> False, len 1 -> False, len 2 -> True."""
    assert Transcriber._acceptable("") is False        # B-1: empty
    assert Transcriber._acceptable(" ") is False        # whitespace collapses to empty
    assert Transcriber._acceptable("a") is False        # B: single char
    assert Transcriber._acceptable("OK") is True         # B+1: two-char non-phrase


# ---------- Transcriber._float_to_int16 ----------

def test_float_to_int16_basic_range():
    out = Transcriber._float_to_int16(np.array([-1.0, 0.0, 1.0]))
    assert out.tolist() == [-32767, 0, 32767]


def test_float_to_int16_clips_out_of_range():
    out = Transcriber._float_to_int16(np.array([2.0, -2.0]))
    assert out.tolist() == [32767, -32767]


def test_float_to_int16_dtype_is_int16():
    out = Transcriber._float_to_int16(np.array([0.5]))
    assert out.dtype == np.int16


def test_float_to_int16_clip_boundary():
    """BVA around the +1.0 clip boundary (B=1.0): 0.9999 < cap, 1.0 == cap, 1.0001 saturates.
    Verifies >1.0 saturates at 32767 with no overflow/wrap into negatives."""
    below = Transcriber._float_to_int16(np.array([0.9999]))[0]
    at = Transcriber._float_to_int16(np.array([1.0]))[0]
    above = Transcriber._float_to_int16(np.array([1.0001]))[0]
    assert below < 32767                  # B-1: below the cap
    assert at == 32767                    # B: exactly at the cap
    assert above == 32767                 # B+1: saturates, does not wrap
    assert above > 0                      # no int16 overflow into negatives


# ---------- Transcriber.slug_track_name ----------

@pytest.mark.parametrize("role, expected", [
    ("Speaker (You)", "Speaker"),          # parenthetical qualifier dropped
    ("Participant", "Participant"),
])
def test_slug_track_name_basic(role, expected):
    assert Transcriber.slug_track_name(role) == expected


def test_slug_track_name_sanitizes_unsafe_chars():
    out = Transcriber.slug_track_name("Bin@Hsu! #1")
    assert out == "Bin_Hsu_1"
    # Result contains only filesystem-safe characters.
    assert all(c.isalnum() or c in "_-" for c in out)


def test_slug_track_name_all_symbol_falls_back():
    assert Transcriber.slug_track_name("###") == "track"


# ---------- retranscribe.should_run_batch ----------

@pytest.mark.parametrize("argv, expected", [
    (["-at", "x.wav"], True),
    (["--audio", "x.wav"], True),
    (["recordings/foo"], False),
    ([], False),
])
def test_should_run_batch(argv, expected):
    assert should_run_batch(argv) is expected


# ---------- Transcriber._wants_word_timestamps (deferred "1a") ----------

@pytest.mark.parametrize("mode, expected", [
    ("localagreement", True),     # LA needs word tokens for prefix agreement
    ("window", False),            # window commits whole-utterance text only -> skip word timestamps
    ("", False),                  # unknown/empty mode defaults to off
    ("LOCALAGREEMENT", False),    # exact match only; mode is not case-normalized
])
def test_wants_word_timestamps(mode, expected):
    assert Transcriber._wants_word_timestamps(mode) is expected
