"""Loops the recogniser got stuck on, folded after re-listen. The turn is not this module's
concern: it only rewrites the text of one segment."""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import pytest  # noqa: E402

import repetition  # noqa: E402

MARKER = repetition.MARKER


def test_a_repeated_phrase_is_dropped_when_the_segment_is_only_the_loop():
    """The 17:42 call: 'Look at' until the segment ended."""
    text = "Look at Look at Look at Look at"
    assert repetition.collapse_repetition(text) == MARKER
    assert repetition.collapse_repetition(text + "…") == MARKER


def test_a_repeated_syllable_is_dropped_when_the_segment_is_only_the_loop():
    """The same call: 'adadad…' with no other words."""
    assert repetition.collapse_repetition("adadadadadad") == MARKER


def test_a_repeated_name_with_a_connector_is_dropped_when_it_is_the_whole_segment():
    """The same call: 'ddtrace, and ddtrace…' — four whole copies, then the cut-off fifth."""
    text = "ddtrace, and ddtrace, and ddtrace, and ddtrace, and ddtrace"
    assert repetition.collapse_repetition(text) == MARKER


def test_a_loop_inside_a_sentence_keeps_one_copy_and_the_surrounding_words():
    text = "Please check ddtrace, and ddtrace, and ddtrace, and ddtrace, and ddtrace tomorrow"
    assert repetition.collapse_repetition(text) == (
        "Please check ddtrace, and" + MARKER + " tomorrow")


def test_agreement_of_three_characters_stays():
    """`對對對` is something a person says. Three is not yet a loop."""
    sentence = "他說對對對，我們就開始檢查 JSON 和 Datadog。"
    assert repetition.collapse_repetition("對對對") == "對對對"
    assert repetition.collapse_repetition(sentence) == sentence


def test_a_longer_run_of_the_same_character_is_a_loop():
    assert repetition.collapse_repetition("對" * 6) == MARKER
    assert repetition.collapse_repetition("他說" + "對" * 6 + "，然後停止") == (
        "他說對" + MARKER + "，然後停止")


@pytest.mark.parametrize("said", [
    "No, no, no, no.",
    "bye bye bye",
    "the the the",
    "very very very good",
    "thank you thank you thank you",
    "好的好的好的",
    "對啊對啊對啊",
    "是的是的是的，我知道",
    "哈哈哈哈",
    "謝謝謝謝大家",
    "hahaha",
    "see www.datadog.com",
    "version 1.1.1 is out",
    "bind 0.0.0.0",
    "call 888 now",
    "code 000",
    "pin 121212",
    "1 1 1 1 1 1 1",
])
def test_what_people_say_is_not_folded(said):
    """Each of these was folded by the first version. A false fold deletes words someone said."""
    assert repetition.collapse_repetition(said) == said


@pytest.mark.parametrize("unit, kept, folded", [
    ("對", 5, 6),          # one character: six is a loop
    ("no ", 5, 6),         # one word: the same
    ("好的", 5, 6),        # a two-character Chinese unit counts as short
    ("Look at ", 3, 4),    # a phrase: four copies
])
def test_each_threshold_folds_at_its_boundary_and_not_one_below(unit, kept, folded):
    below = (unit * kept).strip()
    at = (unit * folded).strip()
    assert repetition.collapse_repetition(below) == below
    assert repetition.collapse_repetition(at) == MARKER


def test_a_syllable_tiling_folds_at_five_repeats_and_not_four():
    assert repetition.collapse_repetition("adadadad") == "adadadad"
    assert repetition.collapse_repetition("adadadadad") == MARKER


def test_whisper_decode_options_pass_the_repetition_gates(monkeypatch):
    """mlx_whisper.transcribe accepts both. The values are the ones already in force:
    conditioning off, and the library's own compression default of 2.4, not a tighter guess."""
    import mlx_whisper
    import transcriber

    seen = {}

    def transcribe(audio, **kwargs):
        seen.update(kwargs)
        return {"text": "ok"}

    monkeypatch.setattr(mlx_whisper, "transcribe", transcribe)
    _kind, fn = transcriber.resolve_backend("mlx-community/whisper-large-v3-turbo")
    assert fn([0.0]) == "ok"
    assert seen["condition_on_previous_text"] is False
    assert seen["compression_ratio_threshold"] == 2.4
