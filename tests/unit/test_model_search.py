"""Whether a configured model still exists, and what the operator is handed when it does not.

No network: the Hub client is stubbed. What is under test is the policy — cache outranks
everything, a gate is a failure and not a warning, and the prompt states requirements the Hub's
metadata does not carry.
"""
import os
import sys
import types

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import model_search  # noqa: E402


def _stub_hub(monkeypatch, info=None, raises=None):
    class _Api:
        def model_info(self, model_id, expand=None):
            if raises is not None:
                raise raises
            return info

    module = types.ModuleType("huggingface_hub")
    module.HfApi = _Api
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)


def _no_cache(monkeypatch):
    module = types.ModuleType("bootstrap")
    module.weights_present = lambda repo: False
    monkeypatch.setitem(sys.modules, "bootstrap", module)


def _cached(monkeypatch):
    module = types.ModuleType("bootstrap")
    module.weights_present = lambda repo: True
    monkeypatch.setitem(sys.modules, "bootstrap", module)


# ===== The dispatch rule is shared with the transcriber =====

def test_the_family_rule_matches_what_resolve_backend_dispatches_on():
    """Two copies of "which loader does this id mean" would drift, and the one that drifted would
    be the one nobody runs. `resolve_backend` imports this table rather than repeating the test."""
    assert model_search.family_for("mlx-community/whisper-large-v3-turbo")["id"] == "whisper"
    assert model_search.family_for("")["id"] == "whisper"


def test_a_disqualified_vendor_id_gets_no_backend_of_its_own():
    """`docs/decisions/0012` removed the second family on **R50**, and removing it from this table
    is what removes it from dispatch — no dormant branch is left behind, because a dormant branch
    is a PRC-origin model an operator reaches by typing an id into the settings form.

    **This asserts the table, not the refusal.** `family_for` answers "which loader *would* try",
    and it still answers `whisper` for any id, including a removed one — that is what makes the id
    fall through to a backend rather than to a `KeyError`. Whether it may actually be loaded is
    `disqualified_reason`, tested directly below, and enforced in `resolve_backend`."""
    assert model_search.family_for("Qwen/Qwen3-ASR-0.6B")["id"] == "whisper"
    assert all(family["id"] != "qwen" for family in model_search.FAMILIES)


def test_the_removed_family_is_refused_by_name_rather_than_failing_inside_mlx():
    """**`.env` survives a version change**, so an operator who configured the removed model still
    has that id — and its weights are still in their cache, so the settings screen reports it as
    `cached` and nothing upstream looks wrong. Measured 2026-08-17: without an explicit refusal the
    failure is `TypeError: ModelDimensions.__init__() got an unexpected keyword argument
    'architectures'`, raised inside MLX, naming neither the model nor the reason.

    The reason has to be in the message. "Not supported" sends someone hunting for a bug; **R50**
    tells them it was removed on purpose and that no amount of debugging brings it back."""
    reason = model_search.disqualified_reason("Qwen/Qwen3-ASR-0.6B")
    assert reason is not None
    assert "R50" in reason and "0012" in reason
    assert model_search.disqualified_reason("qwen/anything") is not None
    assert model_search.disqualified_reason("mlx-community/whisper-large-v3-turbo") is None
    assert model_search.disqualified_reason("") is None


def test_the_whisper_family_records_the_files_the_metadata_does_not_expose():
    """Read from `mlx_whisper/load_models.py` on 2026-08-17, not guessed: it opens `config.json`
    and then `weights.safetensors`. A transformers-format Whisper repository ships
    `model.safetensors` and identical tags, and will not load."""
    family = model_search.family_for("mlx-community/whisper-large-v3-turbo")
    assert "config.json" in family["requires"]
    assert "weights.safetensors" in family["requires"]
    assert "model.safetensors" in family["notes"]
    # The `npz` fallback is the half a guess would have missed, and missing it is not harmless:
    # `mlx-community/whisper-large-v3-mlx` ships `weights.npz`, so a `requires` naming only
    # `weights.safetensors` would reject a working, R50-clean model. Confirmed against that
    # repository 2026-08-17, not inferred from the loader alone.
    assert "weights.npz" in family["notes"]


def test_the_requirement_is_no_longer_labelled_a_guess():
    """It carried an `UNVERIFIED` marker for as long as it was one — the whisper branch was the
    fallback arm nobody had read the source for. It is now the only arm, so the guess was paid
    off rather than inherited."""
    notes = model_search.family_for("mlx-community/whisper-tiny")["notes"]
    assert "UNVERIFIED" not in notes
    assert "load_models.py" in notes


# ===== Availability =====

def test_a_downloaded_model_needs_no_network_and_outranks_everything(monkeypatch):
    """A model on disk works whatever the Hub does. That is both the commonest answer and the
    only one that survives being offline, which is why it is checked first."""
    _cached(monkeypatch)
    _stub_hub(monkeypatch, raises=AssertionError("must not reach the Hub"))

    result = model_search.availability("mlx-community/whisper-large-v3-turbo")
    assert result["state"] == model_search.CACHED
    assert "whatever the" in result["detail"]


def test_a_gate_is_a_failure_not_a_warning(monkeypatch):
    """`pyannote/speaker-diarization-community-1` is the live example: a vendor repository does
    not have to disappear to become unusable. This app has no token concept at all."""
    _no_cache(monkeypatch)
    _stub_hub(monkeypatch, info=types.SimpleNamespace(gated="auto", downloads=5347277))

    result = model_search.availability("pyannote/speaker-diarization-community-1")
    assert result["state"] == model_search.GATED
    assert result["gated"] is True
    assert "token" in result["detail"]


def test_a_missing_repository_is_reported_as_missing(monkeypatch):
    _no_cache(monkeypatch)

    class RepositoryNotFoundError(Exception):
        pass

    _stub_hub(monkeypatch, raises=RepositoryNotFoundError("404"))
    assert model_search.availability("mlx-community/gone")["state"] == model_search.MISSING


def test_an_unreachable_hub_is_unknown_rather_than_missing(monkeypatch):
    """Offline is not the same as deleted, and telling an operator their model is gone when
    their wifi is off would send them to change a setting that was correct."""
    _no_cache(monkeypatch)
    _stub_hub(monkeypatch, raises=OSError("connection refused"))

    result = model_search.availability("mlx-community/whisper-large-v3-turbo")
    assert result["state"] == model_search.UNKNOWN
    assert "could not be checked" in result["detail"]


def test_availability_can_be_asked_not_to_touch_the_network(monkeypatch):
    _no_cache(monkeypatch)
    _stub_hub(monkeypatch, raises=AssertionError("must not reach the Hub"))

    result = model_search.availability("mlx-community/whisper-large-v3-turbo", allow_network=False)
    assert result["state"] == model_search.UNKNOWN


def test_an_empty_model_id_is_answered_rather_than_queried(monkeypatch):
    _stub_hub(monkeypatch, raises=AssertionError("must not reach the Hub"))
    assert model_search.availability("")["detail"] == "no model configured"


# ===== The replacement prompt =====

def test_the_prompt_states_requirements_rather_than_naming_candidates():
    """Naming candidates would mean this project maintaining a judgement about models — the
    thing that goes stale, and the thing the app deliberately does not do."""
    prompt = model_search.build_search_prompt("mlx-community/whisper-large-v3-turbo")
    assert "mlx-whisper" in prompt
    assert "config.json" in prompt and "weights.safetensors" in prompt
    assert "must not be gated" in prompt
    assert "Mandarin and English" in prompt


def test_the_prompt_carries_the_constraint_no_hub_field_expresses():
    """**R50** disqualifies candidates no measurement would reject, and nothing in the Hub's
    metadata says where a model came from. Left implicit, a search returns the same PRC-origin
    models that were just removed — they are genuinely the best on these fixtures."""
    prompt = model_search.build_search_prompt("mlx-community/whisper-large-v3-turbo")
    assert "PRC" in prompt
    assert "loader package" in prompt
    assert "how you established it" in prompt


def test_the_prompt_warns_that_the_trap_is_invisible_in_metadata():
    """The whole reason a dropdown built from search would be half traps."""
    prompt = model_search.build_search_prompt("mlx-community/whisper-large-v3-turbo")
    assert "not visible in the Hub's metadata" in prompt
    assert "check the file list, not the tags" in prompt


def test_the_prompt_asks_the_agent_to_separate_verified_from_assumed():
    """The same standard this repository holds its own agents to."""
    prompt = model_search.build_search_prompt("mlx-community/whisper-large-v3-turbo")
    assert "actually" in prompt and "assumed" in prompt


def test_the_prompt_does_not_claim_its_own_search_is_complete():
    """A family-scoped query is small and official and still misses things — the weights live
    under the vendor's account, not the porting org's, which is what made the obvious query
    return 149 results without the model actually in use."""
    prompt = model_search.build_search_prompt("mlx-community/whisper-large-v3-turbo")
    assert "do not trust it to be complete" in prompt


def test_an_empty_model_id_still_produces_a_usable_prompt():
    """It falls to the same family `resolve_backend` would — the whisper branch is the default
    arm there too — so the prompt names that family's example rather than nothing."""
    prompt = model_search.build_search_prompt("")
    assert model_search.FAMILIES[-1]["example"] in prompt
    assert "mlx-whisper" in prompt


def test_the_durable_answer_points_at_the_bake_off_not_at_a_list():
    advice = model_search.replacement_advice()
    assert "0012" in advice and "asr_bakeoff" in advice
    assert "not a list" in advice
