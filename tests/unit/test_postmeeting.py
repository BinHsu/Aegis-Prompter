"""The post-meeting prompt: what an outside agent is told, and what it is warned about.

This is the whole of the product's post-processing — an instruction written at the end of the
transcript, for the operator to hand to whatever agent they use. Nothing here runs a subprocess,
loads a model or reaches the network, which is why these tests need none of those either.

What they check is that the prompt still carries the things a foreign agent cannot know: the line
format, that the two roles are two unmixed tracks, the specific ways the transcript is lossy, and
where the audio is. Those are the facts this repository measured; a prompt that quietly loses one
of them produces a report with the gap filled in by invention.
"""
import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import postmeeting  # noqa: E402


def test_the_three_deliverables_are_named_in_order():
    """Shortest first: the report is what gets read the moment a meeting ends, the transcript is
    what gets scrolled to afterwards."""
    prompt = postmeeting.build_prompt()
    for heading in ("Report", "Meeting sections", "Proofread transcript"):
        assert heading in prompt
    assert (prompt.index("Report") < prompt.index("Meeting sections")
            < prompt.index("Proofread transcript"))


def test_the_line_format_is_explained():
    """An agent reading `Meeting_2026-08-13_101500.md` cold has never seen this layout."""
    prompt = postmeeting.build_prompt()
    assert "**[HH:MM:SS] Role**: text" in prompt
    assert "Speaker (You)" in prompt and "Participant" in prompt


def test_the_two_roles_are_explained_as_two_unmixed_tracks():
    """R2 is why a role label is trustworthy: it is which device the audio came from, not an
    inference from the words. An agent told nothing would treat it as a guess and 'correct' it."""
    prompt = postmeeting.build_prompt()
    assert "never mixed" in prompt
    assert "microphone" in prompt


def test_the_advisor_lines_are_flagged_as_not_speech():
    """They are prompts shown to the speaker mid-meeting. An agent that reads them as utterances
    puts words in someone's mouth — and the generated ones were never verified (R30)."""
    prompt = postmeeting.build_prompt()
    assert "Staff override" in prompt
    assert "UNVERIFIED" in prompt
    assert "not things anyone said" in prompt


def test_the_known_failure_modes_are_named_with_their_measurements():
    """Each of these is a measured property of this pipeline. Told them, an agent reads a defect
    as a defect; told nothing, it reads one as something a person did oddly."""
    prompt = postmeeting.build_prompt()
    # V66's 0.4 s flush is why one sentence arrives as several lines.
    assert "0.4 s of silence" in prompt
    # V60: non-speech becomes words at a measured rate, not "sometimes, maybe".
    assert "23 of 253" in prompt
    # The length guard deliberately lets short noise through so real one-word answers survive.
    assert "Short noise reaches the transcript on purpose" in prompt


def test_speaker_attribution_is_declared_absent_and_forbidden():
    """Nobody has separated the far side. An agent asked for a clean transcript will happily
    invent 'Speaker A / Speaker B' unless told, and the result reads as fact (R12)."""
    prompt = postmeeting.build_prompt()
    assert "never separated" in prompt
    assert "Do not invent names, do not split" in prompt


def test_the_rules_forbid_inventing_and_forbid_answering():
    prompt = postmeeting.build_prompt()
    assert "Never invent a figure" in prompt
    assert "Do not answer the questions" in prompt
    assert "producing a record, not participating" in prompt


def test_retained_audio_is_named_rather_than_alluded_to():
    """"There is a recording somewhere" is not something anyone can act on."""
    prompt = postmeeting.build_prompt(
        session_id="S1",
        audio={"mic": "/vault/Meeting_S1_mic.wav", "system": "/vault/Meeting_S1_system.wav"},
    )
    assert "The audio was kept" in prompt
    assert "/vault/Meeting_S1_mic.wav" in prompt
    assert "/vault/Meeting_S1_system.wav" in prompt
    assert "before voice detection" in prompt


def test_no_audio_is_stated_as_a_limit_on_the_answer():
    """Not merely absent: it changes what the agent is allowed to conclude."""
    prompt = postmeeting.build_prompt(session_id="S1")
    assert "No audio was kept" in prompt
    assert "say so rather than reconstructing it" in prompt
    assert "/vault" not in prompt


def test_the_block_is_delimited_by_a_stable_marker():
    """So a script can lift it out with one `sed` and never parse Markdown."""
    block = postmeeting.render_block(session_id="S1")
    assert postmeeting.MARKER in block
    assert block.lstrip().startswith("---")

    extracted = postmeeting.extract("# a transcript\n\nsome turns\n" + block)
    assert extracted.startswith(postmeeting.HEADING)
    assert "Proofread transcript" in extracted


def test_extracting_from_a_file_without_the_marker_returns_nothing():
    assert postmeeting.extract("# an older transcript with no prompt") == ""


def test_audio_is_resolved_by_session_id_not_by_sitting_next_to_the_transcript(tmp_path):
    (tmp_path / "Meeting_S1_mic.wav").write_bytes(b"x")
    found = postmeeting.audio_paths(str(tmp_path), "S1")

    assert set(found) == {"mic"}, "only files that exist are named"
    assert postmeeting.audio_paths(str(tmp_path), "S_OTHER") == {}
    assert postmeeting.audio_paths("", "S1") == {}


def test_building_the_prompt_touches_no_disk_and_needs_no_model():
    """The whole point: post-processing is not a product feature (R15). This module can be
    imported and called in a test with nothing installed and nothing configured."""
    assert postmeeting.build_prompt()
    assert "mlx" not in postmeeting.build_prompt().lower()


# ===== The interface has to point at the file =====
#
# The whole post-meeting design is "the prompt is in the transcript". Until 2026-08-14 nothing in
# the interface said a transcript existed — a delivery mechanism the operator is never told to
# look at is this system's characteristic bug in different clothes. The renderer is sliced out of
# `app.py` the way `test_buffer.py` slices the transcript renderer: it is a Streamlit script and
# cannot be imported.
#
# It reads `history/` rather than the engine, and that is load-bearing: an earlier version called
# `engine()`, which imports the whole ASR stack on the one screen whose promise is that nothing
# is loaded until Start.

class _FakeSt:
    """Records what the panel emitted, so the assertions are about content, not about Streamlit."""

    def __init__(self):
        self.emitted = []

    def _record(self, *args, **kwargs):
        self.emitted.extend(str(a) for a in args)

    subheader = write = caption = markdown = _record

    def code(self, body, language=None):
        self.emitted.append(str(body))

    @property
    def text(self):
        return "\n".join(self.emitted)


def _last_session_renderer(sessions, audio=None):
    path = os.path.join(REPO, "src", "app.py")
    source = open(path, encoding="utf-8").read()
    start = source.index("def render_last_session():")
    end = source.index("\ndef render_preflight(", start)

    fake = _FakeSt()
    stub_postmeeting = types.SimpleNamespace(
        list_sessions=lambda history_dir="history": sessions,
        audio_paths=lambda archive_dir, session_id: audio or {},
        MARKER_TOKEN=postmeeting.MARKER_TOKEN,
    )
    namespace = {
        "st": fake,
        "postmeeting": stub_postmeeting,
        "bootstrap": types.SimpleNamespace(resolve_archive_dir=lambda values: "/vault"),
        "settings": {},
    }
    exec(compile(source[start:end], path, "exec"), namespace)
    return namespace["render_last_session"], fake


def _session(session_id="2026-08-14_101500", has_prompt=True):
    return {"session_id": session_id, "path": f"history/Meeting_{session_id}.md",
            "modified": 1.0, "bytes": 2048, "has_prompt": has_prompt}


def test_a_finished_session_names_its_transcript_and_the_way_out():
    render, fake = _last_session_renderer([_session()])
    render()

    assert "history/Meeting_2026-08-14_101500.md" in fake.text
    assert "prompt for your own agent" in fake.text
    # A copy-pasteable extraction, so nobody has to know how the marker is spelled.
    assert postmeeting.MARKER_TOKEN in fake.text
    assert "sed -n" in fake.text


def test_the_extraction_line_is_the_marker_the_file_actually_carries():
    """A one-liner that does not match the file is worse than none: it returns nothing and looks
    like the prompt was never written."""
    render, fake = _last_session_renderer([_session()])
    render()

    command = [line for line in fake.emitted if "sed -n" in line][0]
    token = command.split("'")[1].split("/")[1]
    assert token in postmeeting.render_block(session_id="S1")


def test_a_session_written_before_the_prompt_existed_says_so(monkeypatch):
    """Rather than offering a `sed` line that would return nothing."""
    render, fake = _last_session_renderer([_session(has_prompt=False)])
    render()

    assert "No prompt block" in fake.text
    assert "sed -n" not in fake.text


def test_retained_audio_is_named_in_the_panel_too():
    render, fake = _last_session_renderer(
        [_session()], audio={"mic": "/vault/M_mic.wav", "system": "/vault/M_system.wav"})
    render()

    assert "/vault/M_mic.wav" in fake.text
    assert "/vault/M_system.wav" in fake.text


def test_nothing_is_shown_before_the_first_session():
    render, fake = _last_session_renderer([])
    render()
    assert fake.emitted == []


def test_the_panel_reads_history_rather_than_the_engine():
    """The regression this replaced: calling `engine()` here imported the whole ASR stack on the
    screen whose entire promise is that nothing is loaded until Start."""
    path = os.path.join(REPO, "src", "app.py")
    source = open(path, encoding="utf-8").read()
    start = source.index("def render_last_session():")
    end = source.index("\ndef render_preflight(", start)
    body = source[start:end]

    assert "engine()" not in body.split('"""')[2], "no engine call outside the docstring"
    assert "postmeeting.list_sessions" in body


# ===== Who is speaking is not this pass's question at all =====

def test_the_review_pass_is_not_asked_to_place_participant_titles():
    """**Withdrawn 2026-08-17 at the operator's direction, and he was right.** A previous version
    asked the report to end with the names spoken aloud — carefully fenced as "a list of names
    that were said, not an attribution". Fenced or not, it put the speaker question back on the
    text side.

    The whole architecture splits the passes by **what goes in**: review reads text, re-listening
    reads audio. Who is speaking is an *audio* property — it lives in the timbre, and it is gone
    by the time text exists. Asking a text pass about it reintroduces exactly the confusion that
    split exists to prevent, and it does so in the document that later reads as authoritative.
    """
    prompt = postmeeting.build_prompt()
    assert "who was heard" not in prompt
    assert "spoken aloud" not in prompt


def test_the_transcript_rule_stays_strict():
    """The tightening that came with the withdrawn clause is kept: it moved in the right
    direction on its own."""
    prompt = postmeeting.build_prompt()
    assert "do not relabel a line" in prompt
    assert "not even where you are confident" in prompt
    assert "never separated" in prompt


# ===== Every claim has to be true of the file it is attached to =====
#
# **Found 2026-08-17 by reading a real re-listened transcript.** It carried the live briefing,
# which told an agent to rejoin fragments from a 0.4 s flush that never happened, to look for
# advisor lines that do not exist there, and to read offsets as wall clock — while the file's own
# header two lines above said the flush was 1.2 s. A document contradicting itself gets read as
# one of the two being a typo, and the reader has no way to know which.

def test_the_relistened_variant_does_not_promise_wall_clock_or_a_millisecond_header():
    live = postmeeting.build_prompt()
    relistened = postmeeting.build_prompt(kind=postmeeting.RELISTENED)

    assert "wall clock" in live and "millisecond" in live
    assert "millisecond" not in relistened
    assert "offset from the start of the recording" in relistened
    assert "`**[H:MM:SS] Role**: text`" in relistened


def test_the_relistened_variant_does_not_send_the_agent_looking_for_advisor_lines():
    relistened = postmeeting.build_prompt(kind=postmeeting.RELISTENED)
    assert "Staff override" not in relistened
    assert "no advisor lines here" in relistened


def test_the_relistened_variant_states_its_own_flush_not_the_live_one():
    """The specific self-contradiction: the header said 1.2 s and the prompt said 0.4 s."""
    relistened = postmeeting.build_prompt(kind=postmeeting.RELISTENED, flush_s=1.2)
    assert "1.2 s" in relistened
    assert "0.4 s of silence" not in relistened
    assert "less rejoining to do" in relistened


def test_the_relistened_variant_says_simplified_characters_are_expected():
    """Otherwise a reader seeing 简体 in a re-listened transcript reads it as a fault. R10 names
    Traditional as the target and normalising is part of what the prompt already asks for."""
    relistened = postmeeting.build_prompt(kind=postmeeting.RELISTENED)
    assert "Simplified characters" in relistened
    assert "not a sign that anything went wrong" in relistened


def test_the_relistened_variant_does_not_claim_material_is_unrecoverable():
    """It is the recovery pass — it read the audio captured before voice detection ran."""
    live = postmeeting.build_prompt()
    relistened = postmeeting.build_prompt(kind=postmeeting.RELISTENED)

    assert "none of it can be recovered" in live
    assert "none of it can be recovered" not in relistened
    assert "recovery pass" in relistened


def test_both_variants_still_forbid_inventing_and_relabelling():
    """The rules that do not depend on which file this is."""
    for kind in (postmeeting.LIVE, postmeeting.RELISTENED):
        prompt = postmeeting.build_prompt(kind=kind)
        assert "Never invent a figure" in prompt
        assert "do not relabel a line" in prompt
        assert "Report" in prompt and "Proofread transcript" in prompt
