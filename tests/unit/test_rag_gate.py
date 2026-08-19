"""Arming an advisor slot is a per-meeting choice — disarming it must actually stop it.

`global_state` imports the audio stack at module scope, so the stubs below stand in for it.
**The reason recorded here until 2026-08-13 was false**: it said this machine's venv does not
satisfy `requirements.txt` and that `webrtcvad` / `sounddevice` / `mlx_whisper` are absent. All
three import fine here — checked rather than assumed. The real reason to stub them is that
these tests are about routing, and importing the ASR stack to test a branch would pull in
PortAudio and MLX for nothing. They are not a substitute for running the audio pipeline.
"""
import os
import sys
import threading
import time
from unittest.mock import MagicMock

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_DIR = os.path.join(REPO_ROOT, "src")


@pytest.fixture
def GlobalState(monkeypatch):
    for name in ("webrtcvad", "sounddevice", "mlx_whisper"):
        monkeypatch.setitem(sys.modules, name, MagicMock())

    monkeypatch.syspath_prepend(SRC_DIR)
    for name in ("transcriber", "global_state", "local_advisor", "dialogue_buffer", "text_filters"):
        sys.modules.pop(name, None)

    import global_state as gs

    gs.GlobalState._instance = None
    yield gs.GlobalState
    gs.GlobalState._instance = None


def _run_worker_briefly(state, seconds=0.7):
    state.is_running = True

    def stop():
        time.sleep(seconds)
        state.is_running = False

    threading.Thread(target=stop, daemon=True).start()
    state._local_rag_worker_loop()


def _started(state, GlobalState, **arming):
    """Drive `start_recording` with the audio and advisor construction stubbed out.

    The arming gate is what this file tests, and it lives inside `start_recording` -- reaching
    it means getting past warm-up, the tap and two audio streams, none of which this machine's
    venv can supply.
    """
    state.is_warm = True
    state.transcriber_me = MagicMock()
    state.transcriber_other = None
    state._start_system_audio = lambda: None
    state.start_recording(**arming)
    return state


def test_disarming_retrieval_leaves_no_advisor_at_all(GlobalState, monkeypatch):
    """The per-meeting gate (R27, R33). `_retriever` survives a session because it owns the
    embedding model, so 'an advisor object exists' can never be what decides whether it fires."""
    state = GlobalState()
    state._retriever = MagicMock()          # a previous session already paid the model load

    _started(state, GlobalState, enable_rag=False, enable_llm=False)
    try:
        assert state.advisor is None
    finally:
        state.is_running = False


def test_the_worker_does_nothing_when_no_slot_is_armed(GlobalState):
    state = GlobalState()
    state.advisor = None

    state.buffer.add_entry("Participant", "a long enough attack line for the advisor")
    _run_worker_briefly(state)

    assert all(slot["text"] == "" for slot in state.buffer.get_advice_slots().values())


def test_an_armed_pipeline_receives_the_utterance_and_the_bounded_transcript(GlobalState):
    """The pipeline gets both: the utterance is what retrieval scores, and the transcript is
    what a generative backend needs for context. The transcript is bounded by `max_history`
    rather than by anything the pipeline does (V26, V32)."""
    state = GlobalState()
    pipeline = MagicMock()
    state.advisor = pipeline

    state.buffer.add_entry("Speaker (You)", "an earlier line of my own")
    state.buffer.add_entry("Participant", "a long enough attack line for the advisor")
    _run_worker_briefly(state)

    pipeline.submit.assert_called_once()
    args, kwargs = pipeline.submit.call_args
    assert args[0] == "a long enough attack line for the advisor"
    assert "an earlier line of my own" in kwargs["transcript"]


def test_only_the_participant_track_reaches_the_advisor(GlobalState):
    """R2 keeps the tracks apart; this is what that separation is *for* on the advisor side --
    the operator's own words must not trigger defences against themselves."""
    state = GlobalState()
    pipeline = MagicMock()
    state.advisor = pipeline

    state.buffer.add_entry("Speaker (You)", "a long enough line spoken by the operator")
    _run_worker_briefly(state)

    pipeline.submit.assert_not_called()


def test_published_advice_lands_in_the_slot_its_source_names(GlobalState):
    """The callback the pipeline is handed. Retrieved and generated must not share a slot (V24),
    and the label is carried by the slot rather than glued onto the text."""
    import advisors

    state = GlobalState()
    state._publish_advice(advisors.Advice(source=advisors.SOURCE_GENERATED,
                                          text="a generated guess", vendor="qwen"))
    slots = state.buffer.get_advice_slots()
    assert slots[advisors.SOURCE_GENERATED]["text"] == "a generated guess"
    assert slots[advisors.SOURCE_RETRIEVED]["text"] == ""


# ===== Retention arming (R16, R44, R45) =====
#
# Same stubbed lifecycle as above: the point is which paths are chosen and what the session
# record ends up saying, neither of which needs a real device.

def _armed(state, tmp_path, **kwargs):
    state.is_warm = True
    state.transcriber_me = MagicMock()
    state.transcriber_other = MagicMock()
    state._start_system_audio = lambda: None
    state.buffer.start_session = MagicMock()
    state.start_recording(enable_rag=False, enable_llm=False, **kwargs)
    return state


def test_arming_retention_gives_each_track_its_own_file(GlobalState, tmp_path):
    """R2: two tracks, two files, never mixed — and both named from the session id so the
    cleanup script resolves them without guessing (R44)."""
    import audio_archive

    state = _armed(GlobalState(), tmp_path, archive_audio=True, archive_dir=str(tmp_path))
    try:
        assert state.archive_audio is True
        mic = state.transcriber_me.start.call_args.kwargs["archive_path"]
        system = state.transcriber_other.start.call_args.kwargs["archive_path"]
        assert mic != system
        assert mic.endswith("_mic.wav") and system.endswith("_system.wav")
        assert os.path.dirname(mic) == str(tmp_path)
        assert audio_archive.TRACK_SYSTEM in system
    finally:
        state.is_running = False


def test_an_unarmed_session_passes_no_path_at_all(GlobalState, tmp_path):
    state = _armed(GlobalState(), tmp_path, archive_audio=False, archive_dir=str(tmp_path))
    try:
        assert state.archive_audio is False
        assert state.transcriber_me.start.call_args.kwargs["archive_path"] is None
    finally:
        state.is_running = False


def test_arming_without_a_directory_records_nothing_and_says_so(GlobalState, tmp_path, caplog):
    """Retention cannot be "unconfigured" — the path is derived from the storage root (R44, R48).
    If it ever is empty, that is a fault to report, not a reason to write somewhere arbitrary."""
    state = _armed(GlobalState(), tmp_path, archive_audio=True, archive_dir="")
    try:
        assert state.archive_audio is False
        assert state.transcriber_me.start.call_args.kwargs["archive_path"] is None
        assert any("NOT being recorded" in r.message for r in caplog.records)
    finally:
        state.is_running = False


def test_the_session_record_is_told_what_was_armed(GlobalState, tmp_path):
    state = _armed(GlobalState(), tmp_path, archive_audio=True, archive_dir=str(tmp_path))
    try:
        retention = state.buffer.start_session.call_args.kwargs["retention"]
        assert retention["armed"] is True
        assert retention["directory"] == str(tmp_path)
        assert len(retention["tracks"]) == 2
    finally:
        state.is_running = False


def test_stopping_writes_the_outcome_including_dropped_blocks(GlobalState, tmp_path):
    """R45: a file that is 40 minutes of a 60-minute hearing is worse than no file if nothing
    says so."""
    state = _armed(GlobalState(), tmp_path, archive_audio=True, archive_dir=str(tmp_path))
    state.buffer.finish_session = MagicMock()

    state.transcriber_me.archive.summary.return_value = {
        "path": "a.wav", "started_at": "x", "seconds": 1.0, "bytes": 1,
        "frames": 1, "dropped_blocks": 7, "error": "",
    }
    state.transcriber_other.archive.summary.return_value = {
        "path": "b.wav", "started_at": "y", "seconds": 1.0, "bytes": 1,
        "frames": 1, "dropped_blocks": 0, "error": "",
    }

    state.stop_recording()

    summary = state.buffer.finish_session.call_args.args[0]
    assert set(summary) == {"Speaker (You)", "Participant"}
    assert summary["Speaker (You)"]["dropped_blocks"] == 7


# ===== The post-meeting prompt (R14, R15) =====
#
# The application executes nothing after a meeting. It appends an instruction to the transcript
# and stops, which is why this needs no toggle: writing text into a file is not post-processing.

def test_every_session_ends_with_a_post_meeting_prompt(GlobalState, tmp_path):
    import postmeeting

    state = _armed(GlobalState(), tmp_path)
    state.buffer.finish_session = MagicMock()
    state.stop_recording()

    block = state.buffer.finish_session.call_args.kwargs["prompt_block"]
    assert postmeeting.MARKER in block
    assert "Report" in block and "Meeting sections" in block


def test_the_prompt_names_the_retained_audio_when_there_is_some(GlobalState, tmp_path):
    """The one thing that can settle a question the text cannot — so it is named, not alluded
    to. Resolved by session id plus the archive directory (R44, R45)."""
    state = _armed(GlobalState(), tmp_path, archive_audio=True, archive_dir=str(tmp_path))
    session = state.session_id
    (tmp_path / f"Meeting_{session}_mic.wav").write_bytes(b"x")
    state.buffer.finish_session = MagicMock()
    state.stop_recording()

    block = state.buffer.finish_session.call_args.kwargs["prompt_block"]
    assert f"Meeting_{session}_mic.wav" in block
    assert "The audio was kept" in block


def test_the_prompt_says_so_when_nothing_was_kept(GlobalState, tmp_path):
    state = _armed(GlobalState(), tmp_path)
    state.buffer.finish_session = MagicMock()
    state.stop_recording()

    block = state.buffer.finish_session.call_args.kwargs["prompt_block"]
    assert "No audio was kept" in block
    assert "say so rather than reconstructing it" in block
