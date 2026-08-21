"""Voice separation: the label is a fact, the name is a proposal, and they stay apart.

`pyannote.audio` is not installed and is not a dependency of this project — it is fetched on the
operator's first press. So nothing here imports it. What is tested is the part that decides
whether the output is honest: how a cluster becomes a label, how a line is matched to a cluster,
and that the name table proposes rather than applies.
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import diarize  # noqa: E402


def test_labels_are_numbered_and_carry_no_identity():
    """The operator's design: the label is what the audio supports and nothing more."""
    assert diarize.label_for(0) == "與會者1"
    assert diarize.label_for(2) == "與會者3"


def test_importing_this_module_still_loads_nothing():
    """**This test used to assert `pyannote` was absent from `requirements.txt`, and that
    assertion was correct until 2026-08-18.** It pinned a real decision: the package stayed
    on-demand so a process that never asked for speaker separation contained no telemetry exporter
    and no cloud SDK, and **R15** was therefore structurally true for it.

    `docs/decisions/0013` reversed that deliberately, with the cost put to the operator first: a
    voice-activity gate in the *live* path (**V80**, **V82**) is loaded every session, so the
    package is loaded every session regardless. **R15** is still true — nothing transmits
    unconfigured — but it is no longer checkable by reading the dependency list, and pretending
    otherwise by keeping this assertion green would be worse than losing it.

    **What survives is the half that is still this module's own promise:** importing `diarize`
    imports nothing heavy by itself. The weights are still fetched only when someone asks for
    labels, so the *on-demand* discipline for the model has not gone away with the one for the
    package."""
    import pathlib

    requirements = pathlib.Path(REPO, "requirements.txt").read_text()
    assert "pyannote" in requirements, "0013 made it a hard dependency; see the docstring"
    assert "pyannote.audio" not in sys.modules, "importing diarize must still load nothing"


def test_running_without_it_installed_says_so_rather_than_raising(monkeypatch):
    monkeypatch.setattr(diarize, "available", lambda: False)
    turns, error = diarize.run("/nonexistent.wav")
    assert turns == []
    assert "not installed" in error


# ===== Matching a transcript line to a voice =====

TURNS = [(0.0, 4.0, 0), (4.5, 9.0, 1), (9.5, 14.0, 0)]


def test_a_line_inside_a_turn_takes_that_voice():
    assert diarize.speaker_at(TURNS, 2.0) == 0
    assert diarize.speaker_at(TURNS, 6.0) == 1
    assert diarize.speaker_at(TURNS, 11.0) == 0


def test_a_line_just_off_a_boundary_still_matches():
    """A transcript segment opens at its first speech frame; a diarization boundary sits wherever
    the voice actually changed. They do not have to coincide."""
    assert diarize.speaker_at(TURNS, 4.3) is not None
    assert diarize.speaker_at(TURNS, 9.2) is not None


def test_a_line_in_a_long_silence_matches_nothing():
    """Better an unlabelled line than a confidently wrong one."""
    assert diarize.speaker_at(TURNS, 60.0) is None
    assert diarize.speaker_at([], 1.0) is None


# ===== The name table proposes; it never applies =====

LINES = [
    (0.0, "與會者1", "王委員請問這筆預算的核銷程序"),
    (12.0, "與會者2", "依照第三條規定辦理"),
    (30.0, "與會者1", "那李主席有沒有補充"),
    (44.0, "與會者3", "我補充一點"),
]


def test_a_guess_comes_with_the_evidence_and_the_timestamp():
    """A table nobody can check is worse than none — checking it is the whole mechanism by which
    an imperfect separation stays recoverable."""
    rows = {row["label"]: row for row in diarize.propose_titles(LINES)}

    assert rows["與會者2"]["guess"] == "王委員"
    assert "王委員請問" in rows["與會者2"]["evidence"]
    assert rows["與會者2"]["second"] == 0.0

    assert rows["與會者3"]["guess"] == "李主席"


def test_a_label_with_no_evidence_gets_no_guess():
    """Silence is the honest answer. Filling it in is what the whole design exists to prevent."""
    rows = {row["label"]: row for row in diarize.propose_titles(LINES)}
    assert rows["與會者1"]["guess"] == ""


def test_one_row_per_label_in_first_appearance_order():
    rows = diarize.propose_titles(LINES)
    assert [r["label"] for r in rows] == ["與會者1", "與會者2", "與會者3"]


def test_the_table_states_that_nothing_has_been_applied():
    rows = diarize.propose_titles(LINES)
    table = diarize.render_table(rows)

    assert "Nothing below has been applied" in table
    assert "do the replacement yourself" in table
    assert "only what the audio supports" in table
    assert "與會者1" in table and "王委員" in table


def test_names_the_transcript_contains_but_no_voice_claims_are_listed_separately():
    """Someone was addressed by that title. Which voice they are is not something the evidence
    settles, and saying so beats attaching it to the nearest label."""
    table = diarize.render_table(diarize.propose_titles(LINES), unmatched=["陳部長"])
    assert "陳部長" in table
    assert "not something the evidence above settles" in table


def test_candidate_names_are_titles_a_hearing_actually_uses():
    text = "王委員請問，李主席補充，陳部長回應，然後 Mr. Chen 也說了"
    found = diarize.candidate_names(text)
    assert "王委員" in found and "李主席" in found and "陳部長" in found
    assert "Mr. Chen" in found


def test_ordinary_prose_does_not_become_a_candidate_name():
    """A wide net produces a table nobody can check, and checkability is the point."""
    assert diarize.candidate_names("這筆預算的核銷程序是什麼？我不知道。") == []


def test_a_preceding_particle_is_not_absorbed_into_the_name():
    """`那李主席` — the greedy version matched the whole thing, particle included. A table with
    `那李主席` in it is one the operator stops trusting. Found by a test, 2026-08-17."""
    assert diarize.candidate_names("那李主席有沒有補充") == ["李主席"]
    assert diarize.candidate_names("請問王委員") == ["王委員"]
    assert diarize.candidate_names("剛才陳部長說") == ["陳部長"]


def test_a_compound_surname_survives():
    assert diarize.candidate_names("歐陽委員請說") == ["歐陽委員"]


def test_an_unknown_surname_produces_no_guess_rather_than_a_wrong_one():
    """The safe direction: an empty row asks a question, a wrong row answers one."""
    assert diarize.candidate_names("這位甯委員") == []


# ===== What the pipeline actually returns =====
#
# Read from `pyannote_audio-4.0.7`'s own source, by downloading the wheel and reading it without
# installing anything. An earlier version called `itertracks` on the return value directly and
# would have raised `AttributeError` on the operator's very first press — the one run that has to
# work, because it is also the one that just installed 47 packages.

class _Annotation:
    def __init__(self, tracks):
        self._tracks = tracks

    def itertracks(self, yield_label=False):
        for start, end, speaker in self._tracks:
            yield type("Seg", (), {"start": start, "end": end})(), None, speaker


class _DiarizeOutput:
    """4.x returns this dataclass, not an Annotation."""

    def __init__(self, exclusive, overlapping):
        self.exclusive_speaker_diarization = exclusive
        self.speaker_diarization = overlapping


def test_the_four_x_dataclass_is_unwrapped():
    exclusive = _Annotation([(0.0, 1.0, "SPEAKER_00")])
    overlapping = _Annotation([(0.0, 5.0, "SPEAKER_00"), (0.5, 5.0, "SPEAKER_01")])

    got = diarize._annotation_from(_DiarizeOutput(exclusive, overlapping))
    assert got is exclusive, "the exclusive one, which its own comment calls adapted to transcription"


def test_the_overlapping_field_is_the_fallback_not_the_default():
    """Overlaps would give one transcribed line two competing speakers and nothing to arbitrate
    between them."""
    overlapping = _Annotation([(0.0, 1.0, "SPEAKER_00")])
    output = _DiarizeOutput(None, overlapping)
    assert diarize._annotation_from(output) is overlapping


def test_a_three_x_annotation_still_works():
    annotation = _Annotation([(0.0, 1.0, "SPEAKER_00")])
    assert diarize._annotation_from(annotation) is annotation


def test_something_with_no_diarization_is_reported_rather_than_crashing():
    assert diarize._annotation_from(object()) is None


# ===== A model id must not be able to turn this into an upload =====

def test_a_cloud_pipeline_is_refused_before_it_runs(monkeypatch, tmp_path):
    """`pyannote/speaker-diarization-precision-2` is **not gated and has no weights**: its
    `config.yaml` is `name: pyannote.audio.pipelines.pyannoteai.sdk.SDK`, so using it uploads the
    meeting. It looks like the free option to anyone browsing the Hub to avoid the token, which
    is exactly why it is caught by what the config says rather than left to be discovered."""
    config = tmp_path / "config.yaml"
    config.write_text("pipeline:\n  name: pyannote.audio.pipelines.pyannoteai.sdk.SDK\n"
                      "  params:\n    model: precision-2\n", encoding="utf-8")

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download",
                        lambda repo, name, token=None: str(config))

    cloud, detail = diarize.is_cloud_pipeline("pyannote/speaker-diarization-precision-2")
    assert cloud is True
    assert "uploads the audio" in detail
    assert "no weights to gate" in detail


def test_a_local_pipeline_is_allowed(monkeypatch, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("pipeline:\n  name: pyannote.audio.pipelines.SpeakerDiarization\n"
                      "  params:\n    embedding: pyannote/wespeaker-voxceleb-resnet34-LM\n",
                      encoding="utf-8")

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "hf_hub_download",
                        lambda repo, name, token=None: str(config))

    assert diarize.is_cloud_pipeline("ivrit-ai/pyannote-speaker-diarization-3.1") == (False, "")


def test_an_unreadable_config_does_not_block_a_good_model(monkeypatch):
    """Refusing on a failed download would block a perfectly good local model whenever the
    network is down — and offline is the normal state for this product."""
    import huggingface_hub

    def boom(repo, name, token=None):
        raise OSError("connection refused")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", boom)
    assert diarize.is_cloud_pipeline("anything/at-all") == (False, "")


def test_the_ungated_alternative_is_named_in_the_gated_failure():
    """An operator who does not want to create a token would not otherwise know one exists."""
    hint = diarize._auth_hint(Exception("401 Client Error"), diarize.DEFAULT_MODEL_ID)
    assert diarize.UNGATED_ALTERNATIVE in hint
    assert "no token at all" in hint
