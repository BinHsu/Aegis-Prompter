"""Screen-routing tests for `src/app.py`, driven through Streamlit's own app-test harness.

These cover the three things about the startup path that are cheap to get wrong and expensive to
discover live: which screen a given origin and configuration lands on, that no reachable state is
a dead end (R39), and that **nothing heavy is imported until a storage root exists** (V20, V19).
That last one is the whole reason `bootstrap` carries no project imports, and it is invisible to
every other test.

The real `.env` is never read or written: `read_settings` and `write_settings` are redirected to
`tmp_path` before the script runs. `download_models` is stubbed out so no test reaches the
network, and `streamlit.rerun` is neutralised on the polling screens so a script that is designed
to re-run forever terminates once.
"""
import os
import sys

import pytest
import streamlit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(REPO_ROOT, "src")
APP = os.path.join(SRC, "app.py")

# Import `bootstrap` the way `app.py` does -- bare, off `src/` on sys.path -- not as
# `src.bootstrap`. Those are two distinct module objects with separate readiness state, so
# patching the wrong one silently does nothing and every assertion below drifts to the screen
# the app would have rendered anyway. The rest of the suite uses the `src.` prefix; this file
# is the exception because it drives the app as it actually runs.
if SRC not in sys.path:
    sys.path.insert(0, SRC)
import bootstrap  # noqa: E402

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
PASSWORD_INPUT = pytest.importorskip("streamlit.proto.TextInput_pb2").TextInput.PASSWORD

HEAVY_MODULES = ("global_state", "transcriber", "local_advisor", "mlx_whisper")


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    """Point the app at a throwaway `.env` and keep it off the network."""
    env_path = str(tmp_path / ".env")
    real_read = bootstrap.read_settings
    real_write = bootstrap.write_settings
    real_delete = bootstrap.delete_settings
    monkeypatch.setattr(bootstrap, "read_settings", lambda path=None: real_read(env_path))
    monkeypatch.setattr(bootstrap, "write_settings",
                        lambda values, path=None: real_write(values, env_path))
    # Redirecting `delete_settings` is not optional. Without it the reset test calls it with the
    # default argument, which is the operator's real `.env` in the repository root.
    monkeypatch.setattr(bootstrap, "delete_settings", lambda path=None: real_delete(env_path))
    monkeypatch.setattr(bootstrap, "download_models",
                        lambda settings, on_complete=None, boot_id=None: None)
    monkeypatch.setattr(bootstrap, "_applied_fingerprint", None)
    monkeypatch.setattr(bootstrap, "_readiness", {"state": bootstrap.NO_CONFIG, "detail": ""})
    monkeypatch.setattr(bootstrap, "_boot_id", 0)
    monkeypatch.setattr(os, "environ", dict(os.environ))

    # Unload the heavy modules for the duration, and put them back afterwards. Without this the
    # guard below is only as good as the alphabetical position of this file: any earlier test
    # that imports `global_state` or `transcriber` leaves them in `sys.modules`, and `app.py`
    # importing them again becomes an undetectable no-op. Removing the entries makes "did this
    # run import anything heavy" an actual measurement rather than a claim about test ordering.
    # Safe because these tests never touch those modules, and anything already holding a
    # reference keeps the module object it has -- only the cache entry goes.
    unloaded = {name: sys.modules.pop(name) for name in HEAVY_MODULES if name in sys.modules}
    for name, module in unloaded.items():
        monkeypatch.setitem(sys.modules, name, module)
        del sys.modules[name]

    return {"env": env_path, "root": str(tmp_path / "vault")}


def configure(app_env, **overrides):
    values = {key: "" for key in bootstrap.PERSISTED_KEYS}
    values["STORAGE_ROOT"] = app_env["root"]
    values.update(overrides)
    bootstrap.write_settings(values)
    return values


def assert_nothing_heavy_was_imported():
    loaded = [name for name in HEAVY_MODULES if name in sys.modules]
    assert loaded == [], (
        f"{loaded} imported before a storage root existed — HF_HOME is frozen at "
        "huggingface_hub import time, so this defeats the fixed cache layout (V19, V20)"
    )


def test_an_undeterminable_origin_is_treated_as_remote_and_says_so(app_env):
    """The harness sends no Host header, which is exactly the case that used to grant local
    privileges. It must fail closed, and it must not fail closed silently (V37, R39)."""
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()

    assert [t.value for t in at.title] == ["🔒 Staff Officer Security"]
    assert any("Cannot determine whether this is a local connection" in w.value
               for w in at.warning)
    assert any("localhost" in w.value for w in at.warning), "must say how to get out of this state"
    assert not at.exception
    assert_nothing_heavy_was_imported()


def test_an_unconfigured_local_machine_gets_a_blank_form_not_an_error(app_env, monkeypatch):
    """R20: absent configuration leads to a prompt. R32: the form renders blank."""
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "speaker"
    at.run()

    assert [t.value for t in at.title] == ["⚙️ Configure this machine"]
    labels = [i.label for i in at.text_input]
    assert labels == [f.label + (" *" if f.required else "") for f in bootstrap.SETTINGS_FIELDS]
    assert all(i.value == "" for i in at.text_input), "first run must render blank"
    assert not at.exception
    assert_nothing_heavy_was_imported()


def test_credentials_render_masked_and_their_dependants_are_disabled(app_env, monkeypatch):
    """R32 masking, and R40: a control whose precondition is unmet names what is missing."""
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "speaker"
    at.run()

    by_label = {i.label: i for i in at.text_input}
    # `TextInput.type` is the element name, not the HTML input type -- the masking flag lives on
    # the protobuf. Asserting the wrong attribute here passes against a plaintext credential.
    assert by_label["Qdrant credential"].proto.type == PASSWORD_INPUT
    assert by_label["LLM credential"].proto.type == PASSWORD_INPUT
    assert by_label["Storage root *"].proto.type != PASSWORD_INPUT
    # No Qdrant URL and no LLM base URL are configured, so the fields they gate are dead.
    assert by_label["Qdrant credential"].disabled is True
    assert by_label["LLM model name"].disabled is True
    assert any("Set a Qdrant URL first." in c.value for c in at.caption)
    assert any("Set an LLM base URL first." in c.value for c in at.caption)


def test_saving_is_blocked_until_the_one_required_field_is_filled(app_env, monkeypatch):
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "speaker"
    at.run()

    save = [b for b in at.button if "Save" in b.label][0]
    assert save.disabled is True

    at.text_input(key="cfg_STORAGE_ROOT").set_value(app_env["root"]).run()
    save = [b for b in at.button if "Save" in b.label][0]
    assert save.disabled is False
    # The root is reported back before anything is written to it (R48, V47).
    assert any("AegisPrompter" in c.value for c in at.code)


def test_the_folder_dialog_fills_the_field_it_belongs_to(app_env, monkeypatch):
    """Streamlit forbids assigning to a widget's `session_state` key once the widget exists, so
    the obvious implementation of a Browse button raises instead of filling the field. The
    dialog result is staged under a separate key and the widget rebuilt from it."""
    import subprocess

    class Chosen:
        returncode = 0
        stdout = app_env["root"] + "\n"
        stderr = ""

    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Chosen())

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "speaker"
    at.run()
    [b for b in at.button if "Browse" in b.label][0].click().run()

    assert not at.exception
    assert at.text_input(key="cfg_STORAGE_ROOT").value == app_env["root"]


def test_reset_through_the_ui_deletes_the_env_file_and_nothing_else(app_env, monkeypatch):
    """R22/R47: weights and recordings are the operator's, and a recursive delete against a
    typed path is unacceptable. Reset lists what it orphans, then removes one file."""
    configure(app_env)
    weights = os.path.join(app_env["root"], "AegisPrompter", "models")
    os.makedirs(weights)
    with open(os.path.join(weights, "expensive.bin"), "wb") as handle:
        handle.write(b"3.4GB, notionally")

    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "speaker"
    at.session_state["show_configure"] = True
    at.run()

    [b for b in at.button if "Reset" in b.label][0].click().run()
    assert not at.exception
    assert any("nothing else" in s.value for s in at.subheader)

    [b for b in at.button if b.label == "Delete .env"][0].click().run()
    assert not at.exception
    assert not os.path.exists(app_env["env"])
    assert os.path.exists(os.path.join(weights, "expensive.bin"))


def test_a_configured_machine_reaches_preflight_with_nothing_loaded(app_env, monkeypatch):
    """**Inverted 2026-08-14, and it reverses R24.** Start used to be disabled until warm-up had
    already happened on page load. Nothing is loaded on page load any more — Start is what causes
    the download and the warm — so it is live, and the wait happens behind it.

    The assertion that carries the change is the last one: reaching pre-flight on a *configured*
    machine must now import nothing heavy at all. Under the old boot it imported `global_state`
    and warmed 1794 MB before anyone asked.

    Start is on local Staff Mode (R34 local-only + R35 staff officer presses Start).
    """
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    assert [t.value for t in at.title] == ["🚦 Pre-flight"]
    assert "Recording" in [s.value for s in at.subheader]
    assert "Advisors" in [s.value for s in at.subheader]
    start = [b for b in at.button if "Start" in b.label][0]
    assert start.disabled is False, "Start is what loads things now, so it cannot wait for them"
    assert_nothing_heavy_was_imported()
    # R46: a sticky setting is disclosed in its current state every session. Off here, and the
    # panel says what that costs rather than leaving it blank.
    assert any("Retain dual-track audio" in c.label for c in at.checkbox)
    assert any("gone" in c.value for c in at.caption)
    assert not at.exception


def test_local_speaker_mode_has_no_start_capture(app_env, monkeypatch):
    """Speaker Mode is the teleprompter; it does not start capture on this Mac."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(bootstrap, "set_readiness", lambda *a, **k: None)
    monkeypatch.setattr(bootstrap, "get_readiness", lambda: {
        "state": bootstrap.READY, "detail": "",
    })
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "speaker"
    at.run()

    assert [t.value for t in at.title] == ["🚦 Pre-flight"]
    assert not [b for b in at.button if "Start" in b.label]
    assert any("Speaker Mode has no Start capture" in i.value for i in at.info)
    assert not at.exception


def test_the_retrieval_toggle_cannot_be_armed_without_an_index(app_env, monkeypatch):
    """V34: an armed toggle over a missing index is the failure discovered at the worst moment."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(bootstrap, "index_status", lambda settings=None: {
        "present": False, "chunks": 0, "built": "", "model": "", "error": "index missing"})
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    rag = [c for c in at.checkbox if "retrieval advisor" in c.label][0]
    assert rag.disabled is True
    assert any("index missing" in w.value for w in at.warning)


def _grant_local_origin_only(monkeypatch):
    """Treat this run as local without also declaring every configured URL to be on-machine.

    `is_local_host` answers two questions: whether the *request* came from this Mac (R34) and
    whether a configured backend URL leaves it (R41). Patching it to a flat `True`, as the
    tests above do, silently answers the second one too -- which would make an off-machine
    advisor host look local and delete the warning that is the whole point of R41.
    """
    real = bootstrap.is_local_host
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: not host or real(host))


def test_the_generative_row_is_hidden_entirely_until_a_host_is_configured(app_env, monkeypatch):
    """R40: where the whole capability is unconfigured the control is hidden, not disabled --
    offering something that cannot work is worse than not offering it."""
    configure(app_env, LLM_BASE_URL="")
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    assert not [c for c in at.checkbox if "generative advisor" in c.label]
    assert not [b for b in at.button if "LLM endpoint" in b.label]
    assert not at.exception


def test_arming_the_generative_advisor_warns_that_its_output_is_unverified(app_env, monkeypatch):
    """R30/R41: the warning lands when the choice is made, not after a hearing."""
    configure(app_env, LLM_BASE_URL="http://127.0.0.1:11434/v1", LLM_MODEL="qwen")
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(bootstrap, "index_status", lambda settings=None: {
        "present": True, "chunks": 12, "built": "2026-08-13 09:00", "model": "m", "error": "",
        "target": "local collection", "collection": "aegis_knowledge"})
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    llm = [c for c in at.checkbox if "generative advisor" in c.label][0]
    assert llm.disabled is False
    assert llm.value is False          # off by default even when configured (R28)
    llm.set_value(True).run()

    assert any("unverified" in w.value.lower() for w in at.warning)
    # And the panel states that the two slots do not gate each other, so nobody has to discover
    # that a well-matched cue does not suppress the model.
    assert any("do not gate each other" in c.value for c in at.caption)
    assert not at.exception


def test_a_local_llm_host_is_not_warned_about_as_if_it_left_the_machine(app_env, monkeypatch):
    """R4/R41 warn about data leaving the machine. Saying it about `127.0.0.1` would train the
    operator to ignore the one warning that matters."""
    configure(app_env, LLM_BASE_URL="http://127.0.0.1:11434/v1")
    _grant_local_origin_only(monkeypatch)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()
    [c for c in at.checkbox if "generative advisor" in c.label][0].set_value(True).run()

    assert not any("leave this machine" in w.value for w in at.warning)


def test_an_off_machine_llm_host_says_the_transcript_leaves(app_env, monkeypatch):
    configure(app_env, LLM_BASE_URL="https://api.example.com/v1")
    _grant_local_origin_only(monkeypatch)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()
    [c for c in at.checkbox if "generative advisor" in c.label][0].set_value(True).run()

    assert any("leave this machine" in w.value for w in at.warning)


def test_archive_mode_loads_nothing(app_env, monkeypatch):
    """The point of the mode. Opening the app days later to read last week's transcript must not
    cost 1794 MB of speech-recognition weights and a warm-up nobody is waiting on — warm-up
    exists to serve the live path's latency requirement and nothing else should inherit it."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)
    # If the boot sequence ran, this would be reached.
    monkeypatch.setattr(bootstrap, "download_models",
                        lambda *a, **k: pytest.fail("Archive Mode must not boot the engine"))

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    assert [t.value for t in at.title] == ["🗂 Archive"]
    assert not at.exception
    assert_nothing_heavy_was_imported()


def test_archive_mode_still_exports_the_storage_root(app_env, monkeypatch):
    """It skips the boot but not the environment. `HF_HOME` is derived from the storage root
    (R48), and a re-listening pass that ran without it would download weights into
    `~/.cache/huggingface` — the exact failure V19 describes."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)
    applied = []
    real = bootstrap.apply_environment
    monkeypatch.setattr(bootstrap, "apply_environment",
                        lambda values: (applied.append(values), real(values))[1])

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    assert applied, "the storage root must still reach the environment"
    assert not at.exception


def test_an_empty_archive_is_a_state_not_a_blank_page(app_env, monkeypatch):
    """R39: no dead ends."""
    import postmeeting

    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(postmeeting, "list_sessions", lambda history_dir="history": [])
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    assert any("No sessions yet" in i.value for i in at.info)
    assert not at.exception


def _archive_with(monkeypatch, audio):
    import postmeeting

    monkeypatch.setattr(postmeeting, "list_sessions", lambda history_dir="history": [
        {"session_id": "S1", "path": "history/Meeting_S1.md", "modified": 1.0,
         "bytes": 2048, "has_prompt": True}])
    monkeypatch.setattr(postmeeting, "read_prompt", lambda path: "a prompt block")
    monkeypatch.setattr(postmeeting, "audio_paths", lambda archive_dir, session_id: audio)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)


def test_relisten_is_disabled_when_no_audio_was_retained(app_env, monkeypatch):
    """R40: a control that cannot work names what is missing rather than being absent — and what
    is missing here is a decision the operator had to make *before* the meeting."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    _archive_with(monkeypatch, {})

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    button = [b for b in at.button if "Re-listen" in b.label][0]
    assert button.disabled is True
    assert any("Needs retained audio" in c.value for c in at.caption)
    assert not at.exception


def test_relisten_is_offered_when_the_audio_is_there(app_env, monkeypatch):
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    _archive_with(monkeypatch, {"mic": "/vault/Meeting_S1_mic.wav",
                                "system": "/vault/Meeting_S1_system.wav"})

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    button = [b for b in at.button if "Re-listen and fill in" in b.label][0]
    assert button.disabled is False
    assert "loads the model when you press it" in " ".join(c.value for c in at.caption)
    assert not at.exception
    # Pressing it is what loads anything; merely rendering the screen must not.
    assert_nothing_heavy_was_imported()


def test_relisten_survives_an_unmet_precondition_of_speaker_separation(app_env, monkeypatch):
    """**A regression, found 2026-08-18 when `pyannote` became a hard dependency.**

    Speaker separation is optional; re-listening is not conditional on it. The gated-model branch
    used to `return` out of the screen, so an operator who ticked separation without a Hugging
    Face token lost the **re-listen button entirely** — a control missing rather than disabled
    with a reason (**R40**), and a dead end (**R39**). It went unnoticed because the branch never
    ran while the package was installed on demand; `docs/decisions/0013` made it run for everyone
    without a token."""
    import diarize

    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(diarize, "available", lambda: True)
    _archive_with(monkeypatch, {"system": "/vault/Meeting_S1_system.wav"})

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()
    [c for c in at.checkbox if "separate the voices" in c.label][0].set_value(True).run()

    assert any("gated" in e.value for e in at.error), "the token problem must still be stated"
    button = [b for b in at.button if "Re-listen and fill in" in b.label]
    assert button, "re-listening must survive speaker separation being unusable"
    assert button[0].disabled is False


def test_speaker_separation_is_off_until_asked_for_even_when_installed(app_env, monkeypatch):
    """The checkbox defaulted to *installed*, which was a fair reading of intent while installing
    was a deliberate act. Since **0013** the package is always present, so that default silently
    switched on a feature nobody asked for — and, before the fix above, took the screen down with
    it."""
    import diarize

    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(diarize, "available", lambda: True)
    _archive_with(monkeypatch, {"system": "/vault/Meeting_S1_system.wav"})

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    assert [c for c in at.checkbox if "separate the voices" in c.label][0].value is False


def test_speaker_separation_states_its_cost_before_it_is_installed(app_env, monkeypatch):
    """It is installed on the press and never before, so a process that never asks contains no
    telemetry exporter and no cloud SDK (R15). What the press costs has to be visible first."""
    import diarize

    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(diarize, "available", lambda: False)
    _archive_with(monkeypatch, {"system": "/vault/Meeting_S1_system.wav"})

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()
    [c for c in at.checkbox if "separate the voices" in c.label][0].set_value(True).run()

    warnings = " ".join(w.value for w in at.warning)
    assert "47 packages" in warnings
    assert "OpenTelemetry" in warnings and "cloud SDK" in warnings
    assert "stops being checkable by reading the dependency list" in warnings
    assert [b for b in at.button if "Install speaker separation" in b.label]
    assert not at.exception


def test_speaker_separation_asks_for_the_token_only_once_it_is_installed(app_env, monkeypatch):
    """The weights are gated. Naming the model page is what turns a 401 into an instruction."""
    import diarize

    configure(app_env, HF_TOKEN="")
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(diarize, "available", lambda: True)
    _archive_with(monkeypatch, {"system": "/vault/Meeting_S1_system.wav"})

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()
    [c for c in at.checkbox if "separate the voices" in c.label][0].set_value(True).run()

    errors = " ".join(e.value for e in at.error)
    assert "Hugging Face account" in errors and "token in Settings" in errors
    assert diarize.DEFAULT_MODEL_ID in errors
    # Naming the way out matters as much as naming the problem.
    assert diarize.UNGATED_ALTERNATIVE in errors
    assert "no token" in errors
    assert not at.exception


def test_the_labels_are_declared_anonymous_before_anything_runs(app_env, monkeypatch):
    """The operator's design: the label is an acoustic fact, the name is a separate proposal they
    apply themselves. The screen says so before the button, not after the file exists."""
    import diarize

    configure(app_env, HF_TOKEN="hf_x")
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(diarize, "available", lambda: True)
    _archive_with(monkeypatch, {"system": "/vault/Meeting_S1_system.wav"})

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()
    [c for c in at.checkbox if "separate the voices" in c.label][0].set_value(True).run()

    captions = " ".join(c.value for c in at.caption)
    assert "sound alone, no names" in captions
    assert "apply yourself with a find-and-replace" in captions
    assert "Nothing is applied for you" in captions


def test_a_remote_device_before_start_gets_a_waiting_state(app_env, monkeypatch):
    """R35: the speaker routinely connects before the staff officer presses Start."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: False)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "speaker"
    at.session_state["authenticated"] = True
    at.run()

    assert at.title[0].value.startswith("⏳")
    # R34: no machine control is offered to a remote device.
    assert not [b for b in at.button if "Start" in b.label]
    assert not at.text_input
    assert not at.exception


def test_moving_the_storage_root_in_a_live_process_demands_a_restart(app_env, monkeypatch):
    """V19: HF_HOME cannot be moved once huggingface_hub has imported, so a live change must be
    reported rather than appearing to work."""
    settings = configure(app_env)
    bootstrap.apply_environment(settings)
    moved = dict(settings)
    moved["STORAGE_ROOT"] = app_env["root"] + "-elsewhere"
    bootstrap.write_settings(moved)

    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    assert any("Restart required" in e.value for e in at.error)
    assert [b for b in at.button if "Start" in b.label][0].disabled is True


# ===== Microphone selection (R26) =====

def _fake_devices(monkeypatch, names, default=""):
    """Give the panel a fixed device table.

    `audio_devices` is patched, not `transcriber`: the panel deliberately reaches for the light
    module so that listing inputs cannot drag the ASR stack in ahead of the boot sequence
    (V19, V20). Patching the wrong one would leave these assertions describing whatever hardware
    the test machine happens to have.
    """
    import audio_devices
    monkeypatch.setattr(audio_devices, "list_input_devices",
                        lambda: [{"index": i, "name": n} for i, n in enumerate(names)])
    monkeypatch.setattr(audio_devices, "default_input_name", lambda: default)


def test_the_microphone_dropdown_defaults_to_following_the_system(app_env, monkeypatch):
    """R26: a sensible default, freely overridable. The default is *follow macOS*, not a snapshot
    of it -- an operator who never chose keeps getting the system's current answer."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)
    _fake_devices(monkeypatch, ["MacBook Pro Microphone", "JLab Work Buds"],
                  default="JLab Work Buds")

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    assert "Microphone" in [s.value for s in at.subheader]
    picker = [s for s in at.selectbox if s.key == "pf_mic"]
    assert picker, "the pre-flight panel must offer a microphone dropdown"
    assert picker[0].value == "", "an operator who never chose must land on the system default"
    # The harness reports `options` already run through `format_func`, so these are the labels an
    # operator reads; `value` above is the raw stored value.
    assert picker[0].options == ["System default (follow macOS)",
                                 "MacBook Pro Microphone", "JLab Work Buds"]
    assert not at.exception


def test_a_stored_microphone_that_is_gone_is_shown_rather_than_dropped(app_env, monkeypatch):
    """The silent-substitution failure this item exists to prevent.

    Falling back to the default would leave the panel naming a headset while the built-in
    microphone recorded the room, with nothing for the operator to notice.
    """
    configure(app_env, MIC_DEVICE="Scarlett Solo USB")
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)
    _fake_devices(monkeypatch, ["MacBook Pro Microphone"], default="MacBook Pro Microphone")

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    picker = [s for s in at.selectbox if s.key == "pf_mic"][0]
    assert picker.value == "Scarlett Solo USB", "the operator's choice must survive being absent"
    assert any("not connected" in w.value for w in at.warning), "and it must say so"
    assert not at.exception


def test_the_participant_track_is_not_selectable(app_env, monkeypatch):
    """R1/R5: system audio is everything, so there is no source to choose. Only one dropdown."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)
    _fake_devices(monkeypatch, ["MacBook Pro Microphone"], default="MacBook Pro Microphone")

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    assert [s.key for s in at.selectbox] == ["pf_mic"]
    assert not at.exception


def test_a_device_appearing_does_not_reset_the_operators_choice(app_env, monkeypatch):
    """Plugging in a headset must not silently undo the microphone selection.

    The preference is only written to `.env` when Start is pressed, so before that the persisted
    value is usually empty. Deriving the widget's index from it reset the selection to "system
    default" on every full rerun -- and connecting a device causes a full rerun, because the option
    list changes. Observed 2026-08-12 in the first web-driven session: the operator selected the
    built-in microphone, connected a headset, and had to choose again with nothing saying why.
    """
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)
    _fake_devices(monkeypatch, ["MacBook Pro Microphone"], default="MacBook Pro Microphone")

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()
    at.selectbox(key="pf_mic").select("MacBook Pro Microphone").run()
    assert at.selectbox(key="pf_mic").value == "MacBook Pro Microphone"

    # The headset arrives: the device list grows and macOS makes it the default input.
    _fake_devices(monkeypatch, ["MacBook Pro Microphone", "JLab Work Buds"],
                  default="JLab Work Buds")
    at.run()

    assert at.selectbox(key="pf_mic").value == "MacBook Pro Microphone", (
        "a new device must not move the operator's selection"
    )


def test_a_selected_device_that_goes_away_is_kept_and_flagged(app_env, monkeypatch):
    """The mirror case: unplugging must not silently substitute the built-in microphone."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)
    _fake_devices(monkeypatch, ["MacBook Pro Microphone", "JLab Work Buds"],
                  default="MacBook Pro Microphone")

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()
    at.selectbox(key="pf_mic").select("JLab Work Buds").run()

    _fake_devices(monkeypatch, ["MacBook Pro Microphone"], default="MacBook Pro Microphone")
    at.run()

    assert at.selectbox(key="pf_mic").value == "JLab Work Buds"
    assert any("not connected" in w.value for w in at.warning)


def test_the_archive_is_closed_while_the_engine_is_busy(app_env, monkeypatch):
    """The lock the operator asked for. It guards the accelerator first — re-listening re-runs
    speech recognition and a live capture already has two tracks on `NPU_LOCK` — and this
    screen's own promise second: entering it is supposed to find no model of ours in memory."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(bootstrap, "_readiness", {"state": bootstrap.READY, "detail": ""})
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    assert [t.value for t in at.title] == ["🗂 Archive"]
    assert any("closed while the engine is busy" in w.value for w in at.warning)
    # Refused, not silently empty: it says what to do about it.
    assert any("Stop the capture" in w.value for w in at.warning)
    assert not at.exception


def test_the_archive_opens_once_the_engine_has_been_released(app_env, monkeypatch):
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(bootstrap, "_readiness", {"state": bootstrap.IDLE, "detail": ""})
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "archive"
    at.run()

    assert not any("closed while the engine is busy" in w.value for w in at.warning)
    assert_nothing_heavy_was_imported()


def test_a_failed_start_can_be_retried_in_place(app_env, monkeypatch):
    """R39: no dead ends. While the boot ran once at startup, "restart the app" was a true
    instruction — a failed boot was a failed launch. Since Start became a repeatable action, a
    download that timed out or a device that was unplugged has to be retryable without quitting
    Streamlit. Found 2026-08-14, one commit after the inversion introduced it."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(bootstrap, "_readiness",
                        {"state": bootstrap.FAILED, "detail": "connection refused"})
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()

    assert any("Start failed" in e.value for e in at.error)
    assert any("press Start again" in c.value for c in at.caption)
    assert [b for b in at.button if "Try again" in b.label], "a failure must offer a way out"
    assert not at.exception


def test_retrying_returns_to_idle_so_the_promise_of_idle_stays_true(app_env, monkeypatch):
    """`idle` has to mean nothing loaded, or the archive lock and the memory promise are lies."""
    configure(app_env)
    monkeypatch.setattr(bootstrap, "is_local_host", lambda host: True)
    monkeypatch.setattr(bootstrap, "_readiness",
                        {"state": bootstrap.FAILED, "detail": "connection refused"})
    monkeypatch.setattr(streamlit, "rerun", lambda *args, **kwargs: None)

    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["role"] = "staff"
    at.run()
    [b for b in at.button if "Try again" in b.label][0].click().run()

    assert bootstrap.get_readiness()["state"] == bootstrap.IDLE
    assert not at.exception
