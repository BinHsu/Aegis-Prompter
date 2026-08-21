"""Boundary tests for the anti-hallucination filter.

Adopted from `origin/feat/streaming-transcriber` with `docs/decisions/0006`, converted to the
`src.`-prefix import convention this repo's tests use. They exercise the one behaviour the fix
is about: the blacklist matches a **whole utterance**, never a substring.
"""
import pytest

from src.text_filters import HALLUCINATION_PHRASES, is_acceptable, normalize_phrase


@pytest.mark.parametrize("text, expected", [
    # Bare known hallucinations are dropped (whole-utterance exact match).
    ("謝謝", True),     # likewise; and the shipped model emits Simplified (R10), so a
                        # Traditional entry never matched anyway
    ("Thank you.", True),    # removed 2026-08-12 — ordinary speech, see docs/decisions/0009
    # Real speech that merely CONTAINS a hallucination phrase survives. This is the regression:
    # substring matching destroyed both of these before they reached the buffer.
    ("謝謝大家", True),
    ("Okay, thank you, see you", True),
    # Latin case is ignored.
    ("THANK YOU.", True),
    # Trailing punctuation / missing punctuation variants still match.
    ("謝謝。", True),
    ("Thank you", True),
    # A normal short non-phrase survives.
    ("OK", True),
    # Bake-off R37 ghosts (whole utterance only).
    ("I don't know.", True),   # no longer blacklisted — see docs/decisions/0009
    ("Bye.", True),
    ("I don't know what they meant", True),
    ("Bye for now", True),
])
def test_acceptable_phrase_matching(text, expected):
    assert is_acceptable(text) is expected


def test_acceptable_len_boundary():
    """BVA around the len<=1 guard (B=1): len 0 -> False, len 1 -> False, len 2 -> True."""
    assert is_acceptable("") is False         # B-1: empty
    assert is_acceptable(" ") is False        # whitespace collapses to empty
    assert is_acceptable("a") is False        # B: single char
    assert is_acceptable("OK") is True        # B+1: two-char non-phrase


def test_every_blacklisted_phrase_is_dropped_bare():
    """Each entry still does its job on its own, so the list stays meaningful."""
    for phrase in HALLUCINATION_PHRASES:
        assert is_acceptable(phrase) is False, phrase


def test_every_blacklisted_phrase_survives_inside_real_speech():
    """The whole point of the change: a ghost string embedded in speech is not a ghost."""
    for phrase in HALLUCINATION_PHRASES:
        assert is_acceptable(f"我剛才說的是 {phrase} 這件事情") is True, phrase


def test_normalize_phrase_is_not_used_to_alter_stored_text():
    """Normalisation exists only for comparison. It lower-cases and strips, so it must never be
    mistaken for something safe to store -- transcript content is never rewritten (R3, R38)."""
    assert normalize_phrase("  Thank You!! ") == "thank you"
    assert normalize_phrase("謝謝，") == "謝謝"


def test_the_blacklist_is_empty_until_something_is_measured():
    """The list is empty on purpose, and the reason is not that the strings were wrong.

    Every entry it ever held was judged implausible as real meeting speech — from one scenario, a
    legislative hearing. A fork transcribing a podcast or a language class says `請訂閱`, `字幕`
    and `Thank you.` in earnest. We cannot predict what a forker records, so we do not guess which
    words they never say, and R37 is met by the model rather than by a filter: zero text on 441
    non-speech calls.

    Adding an entry means having measured that *this* deployment produces it. A string from
    somebody else's subtitle corpus is not evidence about your audio.
    """
    from src.text_filters import HALLUCINATION_PHRASES

    assert HALLUCINATION_PHRASES == [], (
        "entries were added without the measurement this test asks for; see the module docstring"
    )


def test_only_the_length_guard_remains():
    """What survives is the one rule that carries no assumption about anyone's vocabulary."""
    assert is_acceptable("") is False
    assert is_acceptable(" ") is False
    assert is_acceptable("a") is False
    assert is_acceptable("OK") is True
    assert is_acceptable("Thank you.") is True
    assert is_acceptable("請訂閱") is True


def test_short_noise_reaches_the_buffer_on_purpose():
    """V64, decided by the operator 2026-08-12: the guard measures the raw string, so anything the
    model punctuates survives. This is the behaviour, not a gap -- pinned so the "obvious fix"
    cannot land silently.

    Normalising first would make it consistent and would also drop the second group below. A
    witness answering "Yes." is among the most consequential things said in a hearing, and with
    retention off nothing recovers it. Noise costs a line; a destroyed answer costs the record.
    """
    for noise in ("哦。", "嗯。", "啊！", "じ。"):
        assert is_acceptable(noise), f"{noise!r} is expected through -- cleanup removes it (R49)"
    for answer in ("是。", "不。", "Yes.", "No."):
        assert is_acceptable(answer), f"{answer!r} must never be filtered"


def test_only_a_lone_punctuation_mark_is_removed():
    for lone in (".", "。", "!", "", " "):
        assert not is_acceptable(lone)
