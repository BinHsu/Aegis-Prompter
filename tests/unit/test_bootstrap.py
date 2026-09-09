"""Unit tests for the configuration bootstrap.

Every test builds its own `.env` under `tmp_path`. Nothing here reads the repository's real
`.env`, which is the operator's private file -- `bootstrap.ENV_PATH` is never passed to
anything below, and the default argument is never relied on.
"""
import os
import pathlib

import pytest

from src import bootstrap


@pytest.fixture
def env_file(tmp_path):
    return str(tmp_path / ".env")


def blank_settings():
    return {key: "" for key in bootstrap.PERSISTED_KEYS}


# ===== `.env` round-trip (R32) =====

def test_round_trip_preserves_awkward_values(env_file, tmp_path):
    """Write the form, read it back, get identical values -- including the characters that a
    naive `KEY=value` serializer silently truncates."""
    values = blank_settings()
    values.update({
        "STORAGE_ROOT": str(tmp_path / "vault"),
        "QDRANT_API_KEY": "abc=def#ghi",          # `=` and `#` both matter to a dotenv parser
        "LLM_API_KEY": 'quote " and \\ backslash',
        "LLM_MODEL": "  spaced  ",
        "EMBEDDING_MODEL": "paraphrase-multilingual-MiniLM-L12-v2",
    })
    bootstrap.write_settings(values, env_file)
    read_back = bootstrap.read_settings(env_file)

    for key in ("QDRANT_API_KEY", "LLM_API_KEY", "LLM_MODEL", "EMBEDDING_MODEL"):
        assert read_back[key] == values[key], key


def test_blank_field_survives_as_blank_not_the_string_none(env_file, tmp_path):
    """A field the operator left empty must come back empty. `"None"` is the classic failure
    here, and it would be persisted as a real credential."""
    values = blank_settings()
    values["STORAGE_ROOT"] = str(tmp_path / "vault")
    bootstrap.write_settings(values, env_file)
    read_back = bootstrap.read_settings(env_file)

    assert read_back["LLM_API_KEY"] == ""
    assert read_back["QDRANT_URL"] == ""
    assert "None" not in open(env_file, encoding="utf-8").read()


def test_write_drops_keys_the_form_does_not_own(env_file, tmp_path):
    """`.env` is a snapshot of the form and the app is its only writer, so there is no second
    place configuration can hide."""
    with open(env_file, "w", encoding="utf-8") as handle:
        handle.write('LEFTOVER_FLAG="true"\nSTORAGE_ROOT="/old"\n')
    values = blank_settings()
    values["STORAGE_ROOT"] = str(tmp_path / "vault")
    bootstrap.write_settings(values, env_file)

    assert "LEFTOVER_FLAG" not in open(env_file, encoding="utf-8").read()


def test_hf_home_is_derived_not_taken_from_the_caller(env_file, tmp_path):
    values = blank_settings()
    values["STORAGE_ROOT"] = str(tmp_path / "vault")
    values["HF_HOME"] = "/somewhere/the/operator/typed"
    persisted = bootstrap.write_settings(values, env_file)

    assert persisted["HF_HOME"] == bootstrap.derive_paths(values["STORAGE_ROOT"])["models"]
    assert bootstrap.read_settings(env_file)["HF_HOME"] == persisted["HF_HOME"]


# ===== Atomic write (V46) =====

def test_failure_between_temp_write_and_replace_leaves_the_original_intact(
        env_file, tmp_path, monkeypatch):
    """Streamlit re-executes the script constantly; a torn `.env` reads as a half-configured
    machine and looks like operator error."""
    good = blank_settings()
    good["STORAGE_ROOT"] = str(tmp_path / "vault")
    good["LLM_API_KEY"] = "original-secret"
    bootstrap.write_settings(good, env_file)
    before = open(env_file, encoding="utf-8").read()

    def exploding_replace(src, dst):
        raise OSError("simulated crash between temp-write and replace")

    monkeypatch.setattr(bootstrap.os, "replace", exploding_replace)
    doomed = dict(good)
    doomed["LLM_API_KEY"] = "half-written"
    with pytest.raises(OSError):
        bootstrap.write_settings(doomed, env_file)

    assert open(env_file, encoding="utf-8").read() == before
    assert bootstrap.read_settings(env_file)["LLM_API_KEY"] == "original-secret"
    leftovers = [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]
    assert leftovers == []


# ===== Path derivation (R48) =====

def test_one_root_produces_the_fixed_layout(tmp_path):
    paths = bootstrap.derive_paths(str(tmp_path / "vault"))
    assert paths["models"] == os.path.join(str(tmp_path), "vault", "AegisPrompter", "models")
    assert paths["audio"] == os.path.join(str(tmp_path), "vault", "AegisPrompter", "audio")


def test_equivalent_roots_normalise_to_byte_identical_paths(tmp_path, monkeypatch):
    """"The same root re-entered" has to mean the same derived path, or an existing cache is
    invisible and re-downloaded in full (V47)."""
    monkeypatch.chdir(tmp_path)
    target = os.path.join(str(tmp_path), "vault")
    variants = [
        target,
        target + os.sep,
        target + os.sep + os.sep,
        os.path.join(target, "."),
        os.path.join(target, "sub", ".."),
        "vault",                    # relative to the working directory
        " " + target + " ",         # stray whitespace from a paste
    ]
    derived = {bootstrap.derive_paths(v)["models"] for v in variants}
    assert len(derived) == 1, derived


def test_tilde_expands_to_the_same_place_as_the_absolute_form():
    assert (bootstrap.derive_paths("~/AegisVault")["models"]
            == bootstrap.derive_paths(os.path.expanduser("~/AegisVault"))["models"])


def test_empty_root_derives_nothing_rather_than_the_filesystem_root():
    assert bootstrap.derive_paths("")["models"] == ""
    assert bootstrap.derive_paths("   ")["models"] == ""


def test_archive_directory_falls_back_to_the_derived_path(tmp_path):
    settings = blank_settings()
    settings["STORAGE_ROOT"] = str(tmp_path / "vault")
    assert bootstrap.resolve_archive_dir(settings) == bootstrap.derive_paths(
        settings["STORAGE_ROOT"])["audio"]

    settings["AUDIO_ARCHIVE_DIR"] = str(tmp_path / "elsewhere") + os.sep
    assert bootstrap.resolve_archive_dir(settings) == str(tmp_path / "elsewhere")


# ===== Absent configuration (R20) =====

def test_missing_file_yields_a_blank_form(tmp_path):
    settings = bootstrap.read_settings(str(tmp_path / "does-not-exist"))
    assert settings == blank_settings()
    assert bootstrap.is_configured(settings) is False


def test_empty_file_yields_a_blank_form(env_file):
    open(env_file, "w").close()
    settings = bootstrap.read_settings(env_file)
    assert settings == blank_settings()
    assert bootstrap.is_configured(settings) is False


def test_file_without_the_required_key_names_what_is_missing(env_file):
    with open(env_file, "w", encoding="utf-8") as handle:
        handle.write('ASR_MODEL="mlx-community/distil-whisper-large-v3"\n')
    settings = bootstrap.read_settings(env_file)
    assert bootstrap.is_configured(settings) is False
    assert bootstrap.missing_required(settings) == ["Storage root"]


def test_bare_key_with_no_value_reads_as_blank(env_file):
    with open(env_file, "w", encoding="utf-8") as handle:
        handle.write("STORAGE_ROOT\nLLM_API_KEY=\n")
    settings = bootstrap.read_settings(env_file)
    assert settings["STORAGE_ROOT"] == ""
    assert settings["LLM_API_KEY"] == ""


# ===== Reset (R22, R47) =====

def test_reset_deletes_only_the_env_file(env_file, tmp_path):
    values = blank_settings()
    values["STORAGE_ROOT"] = str(tmp_path / "vault")
    bootstrap.write_settings(values, env_file)
    models = tmp_path / "vault" / "AegisPrompter" / "models"
    models.mkdir(parents=True)
    (models / "weights.bin").write_bytes(b"expensive")

    assert bootstrap.delete_settings(env_file) is True
    assert not os.path.exists(env_file)
    assert (models / "weights.bin").exists(), "reset must never touch downloaded weights"
    assert bootstrap.delete_settings(env_file) is False


# ===== Reporting a root before writing to it (R48, V47) =====

def test_inspect_root_reports_an_existing_cache(tmp_path):
    root = tmp_path / "vault"
    models = root / "AegisPrompter" / "models"
    models.mkdir(parents=True)
    (models / "a.bin").write_bytes(b"x" * 2048)
    audio = root / "AegisPrompter" / "audio"
    audio.mkdir(parents=True)
    (audio / "Meeting_1_mic.wav").write_bytes(b"y" * 100)

    report = bootstrap.inspect_root(str(root))
    assert report["models"] == {"files": 1, "bytes": 2048}
    assert report["audio"] == {"files": 1, "bytes": 100}
    assert report["writable"] is True


def test_cache_size_counts_each_byte_once_despite_symlinks(tmp_path):
    """`huggingface_hub` stores every file once under `blobs/` and links to it from
    `snapshots/<commit>/`. Following those links reports exactly double — measured as 2.8 GB
    against a 1.4 GB repository. The figure is shown on Configure as "existing cache found" and
    is also the numerator of download progress, so it is wrong in two visible places at once."""
    root = tmp_path / "vault"
    repo = root / "AegisPrompter" / "models" / "hub" / "models--org--name"
    blobs = repo / "blobs"
    snapshot = repo / "snapshots" / "abc123"
    blobs.mkdir(parents=True)
    snapshot.mkdir(parents=True)
    payload = blobs / "deadbeef"
    payload.write_bytes(b"x" * 4096)
    os.symlink(payload, snapshot / "model.safetensors")
    os.symlink(blobs, repo / "linked-dir")

    files, total = bootstrap._tree_stats(str(repo))
    assert total == 4096, "a symlinked blob must not be counted twice"
    assert files == 1

    report = bootstrap.inspect_root(str(root))
    assert report["models"]["bytes"] == 4096


def test_inspect_root_of_a_nonexistent_path_reports_empty_and_writable(tmp_path):
    report = bootstrap.inspect_root(str(tmp_path / "not-created-yet"))
    assert report["models"]["files"] == 0
    assert report["writable"] is True     # the parent exists and is writable


# ===== Restart detection =====

def test_changing_a_baked_in_setting_requires_a_restart(tmp_path, monkeypatch):
    """`HF_HOME` cannot be moved once `huggingface_hub` has imported (V19), so a live change
    must be reported rather than silently ignored."""
    # Isolate the process environment: `apply_environment` writes into `os.environ` for real.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    monkeypatch.setattr(bootstrap, "_applied_fingerprint", None)
    settings = blank_settings()
    settings["STORAGE_ROOT"] = str(tmp_path / "vault")

    assert bootstrap.needs_restart(settings) is False   # nothing applied yet
    bootstrap.apply_environment(settings)
    assert bootstrap.needs_restart(settings) is False

    moved = dict(settings)
    moved["STORAGE_ROOT"] = str(tmp_path / "other")
    assert bootstrap.needs_restart(moved) is True

    recoloured = dict(settings)
    recoloured["LLM_API_KEY"] = "changing this is harmless"
    assert bootstrap.needs_restart(recoloured) is False


def test_a_revoked_boot_cannot_overwrite_restart_required(monkeypatch):
    """A warm-up that finishes after the operator changed the storage root must not flip the
    UI back to Ready — that was the race that made Start pressable against the wrong HF_HOME."""
    monkeypatch.setattr(bootstrap, "_boot_id", 0)
    monkeypatch.setattr(bootstrap, "_readiness", {"state": bootstrap.NO_CONFIG, "detail": ""})

    boot_id = bootstrap.begin_boot()
    assert bootstrap.set_readiness(bootstrap.WARMING, "model-a", boot_id=boot_id) is True

    # Operator changed a baked-in setting; the UI demands a restart and revokes the boot.
    bootstrap.invalidate_boot()
    bootstrap.set_readiness(bootstrap.RESTART_REQUIRED, "configuration changed")

    # Late completion from the revoked boot — must not stick.
    assert bootstrap.set_readiness(bootstrap.READY, boot_id=boot_id) is False
    assert bootstrap.get_readiness()["state"] == bootstrap.RESTART_REQUIRED


def test_asr_model_warning_names_a_restart_not_a_live_rewarm():
    """The fingerprint forces a process restart for ASR_MODEL changes; the field warning must
    say so rather than promising an in-process return to warming (V33 vs V19)."""
    warning = bootstrap.FIELDS_BY_KEY["ASR_MODEL"].warning.lower()
    assert "restart" in warning
    assert "warming" not in warning


def test_expected_repo_bytes_passes_a_timeout_and_returns_zero_on_failure(monkeypatch):
    """A hung Hub metadata call must not leave readiness at DOWNLOADING with no byte updates."""
    calls = {}

    class FakeApi:
        def repo_info(self, repo_id, **kwargs):
            calls["timeout"] = kwargs.get("timeout")
            raise ConnectionError("no route to hub")

    import huggingface_hub
    monkeypatch.setattr(huggingface_hub, "HfApi", FakeApi)

    assert bootstrap.expected_repo_bytes("org/name") == 0
    assert calls["timeout"] == bootstrap.REPO_INFO_TIMEOUT_S


def test_watch_repo_bytes_reports_growth_not_preexisting_cache(tmp_path, monkeypatch):
    """Leftover blobs from an earlier revision must not pin the bar at 100% before this fetch
    has written anything."""
    import threading
    import time

    monkeypatch.setenv("HF_HOME", str(tmp_path / "models"))
    monkeypatch.setattr(bootstrap, "_progress", {})
    repo = "org/name"
    blobs = os.path.join(bootstrap.repo_cache_dir(repo), "blobs")
    os.makedirs(blobs)
    with open(os.path.join(blobs, "old-revision"), "wb") as handle:
        handle.write(b"x" * 5000)

    stop = threading.Event()

    def grow():
        time.sleep(0.15)
        with open(os.path.join(blobs, "new-bytes"), "wb") as handle:
            handle.write(b"y" * 800)
        time.sleep(0.15)
        stop.set()

    threading.Thread(target=grow, daemon=True).start()
    bootstrap._watch_repo_bytes(repo, total=800, stop_event=stop, interval=0.05)

    entry = bootstrap.progress_snapshot()[repo]
    assert entry["done"] == 800, entry
    assert entry["total"] == 800
    assert entry["done"] <= entry["total"]


def test_offline_is_entered_after_configuration_not_at_boot(tmp_path, monkeypatch):
    """The app promises zero external dependencies, and `huggingface_hub` 1.27 pings the Hub
    during warm-up even with every file cached. But the download step runs first and needs the
    network, so `apply_environment` must NOT set it -- offline is the state the app enters once
    it has what it needs."""
    monkeypatch.setattr(os, "environ", dict(os.environ))
    os.environ.pop("HF_HUB_OFFLINE", None)

    settings = blank_settings()
    settings["STORAGE_ROOT"] = str(tmp_path / "vault")
    bootstrap.apply_environment(settings)
    assert "HF_HUB_OFFLINE" not in os.environ, "downloads would be blocked before they run"

    bootstrap.enforce_offline()
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_required_repos_falls_back_to_the_documented_defaults():
    settings = blank_settings()
    assert bootstrap.required_repos(settings) == [
        bootstrap.FIELDS_BY_KEY["ASR_MODEL"].default,
        bootstrap.FIELDS_BY_KEY["EMBEDDING_MODEL"].default,
    ]
    settings["ASR_MODEL"] = bootstrap.FIELDS_BY_KEY["EMBEDDING_MODEL"].default
    assert len(bootstrap.required_repos(settings)) == 1, "duplicates must collapse"


@pytest.mark.parametrize("key", ["ASR_MODEL", "EMBEDDING_MODEL"])
def test_default_model_names_are_fully_qualified_repository_ids(key):
    """`sentence-transformers` resolves a bare name by prefixing its own namespace;
    `huggingface_hub` does not. A bare default therefore 404s at download time — which, before
    this was fixed, left readiness permanently FAILED and Start permanently disabled on a stock
    configuration. Unit tests cannot catch it because they never reach the network, so the shape
    of the id is asserted instead."""
    default = bootstrap.FIELDS_BY_KEY[key].default
    assert default.count("/") == 1, f"{key} default {default!r} is not <namespace>/<name>"
    assert not default.startswith("/") and not default.endswith("/")


def test_the_download_filter_excludes_formats_this_runtime_cannot_load():
    """Measured 2026-08-10: an unfiltered fetch of the default embedding repository pulled 4.1 GB,
    of which onnx (2.4 GB), openvino (563 MB) and tf_model.h5 (449 MB) were formats neither MLX nor
    sentence-transformers can read. `pytorch_model.bin` is deliberately kept — preferring
    safetensors is the loader's decision, and guessing wrong yields a model that will not load."""
    patterns = bootstrap.UNUSED_WEIGHT_FORMATS
    for dead in ("onnx/*", "openvino/*", "*.h5"):
        assert dead in patterns
    assert not any(p.endswith(".bin") or p == "*.safetensors" for p in patterns), (
        "excluding the weights the loader actually reads would break the model"
    )


def test_only_the_asr_model_can_block_startup():
    """The embedding model may never be used: retrieval is a per-meeting choice, and when armed
    `LocalAdvisor` loads the model named inside the compiled index instead (V3, V36). A failure to
    fetch it must not leave Start disabled forever."""
    settings = blank_settings()
    essential = bootstrap.essential_repos(settings)
    assert essential == [bootstrap.FIELDS_BY_KEY["ASR_MODEL"].default]
    assert bootstrap.FIELDS_BY_KEY["EMBEDDING_MODEL"].default not in essential
    assert set(essential).issubset(set(bootstrap.required_repos(settings)))


# ===== Local versus remote (V37) =====

@pytest.mark.parametrize("host, expected", [
    ("localhost:8501", True),
    ("localhost", True),
    ("127.0.0.1:8501", True),
    ("127.0.0.1", True),
    ("[::1]:8501", True),
    # Everything below must fail CLOSED. The empty case and the exception case were the two
    # fail-open paths in the previous implementation (V37).
    ("192.168.1.24:8501", False),
    ("10.0.0.8", False),
    ("aegis.local:8501", False),
    ("", False),
    (None, False),
    ("evil-localhost.example.com", False),
    ("localhost.attacker.net:8501", False),
    ("127.0.0.1.attacker.net", False),
])
def test_is_local_host(host, expected):
    assert bootstrap.is_local_host(host) is expected


def test_is_local_host_treats_an_unusable_value_as_remote():
    class Hostile:
        def __bool__(self):
            return True

        def strip(self):
            raise RuntimeError("header accessor blew up")

    assert bootstrap.is_local_host(Hostile()) is False


def test_enforce_offline_patches_the_loaded_library_not_only_the_environment(monkeypatch):
    """The environment variable alone does nothing once `huggingface_hub` is imported.

    It reads HF_HUB_OFFLINE into a module constant at import time, and `download_models` always
    imports it before this runs -- so setting the variable afterwards changes a string nobody reads
    again. That made this function a no-op for its whole existence: verified 2026-08-12 from a live
    run where warm-up issued a request to huggingface.co 238 ms after it returned.

    The stand-in mimics the real shape (a module object carrying the flag) so the test does not
    depend on `huggingface_hub` being installed or on which of its submodules binds the name.
    """
    import sys as _sys
    import types

    fake = types.ModuleType("huggingface_hub.constants")
    fake.HF_HUB_OFFLINE = False
    unrelated = types.ModuleType("something_else")
    unrelated.HF_HUB_OFFLINE = False
    monkeypatch.setitem(_sys.modules, "huggingface_hub.constants", fake)
    monkeypatch.setitem(_sys.modules, "something_else", unrelated)

    patched = bootstrap.enforce_offline()

    assert fake.HF_HUB_OFFLINE is True
    assert unrelated.HF_HUB_OFFLINE is False, "only huggingface_hub modules may be touched"
    assert "huggingface_hub.constants" in patched
    assert os.environ["HF_HUB_OFFLINE"] == "1", "the variable still matters for later imports"


def test_enforce_offline_is_safe_when_the_library_was_never_loaded(monkeypatch):
    """A process that never imported the library is the correct case for finding nothing."""
    import sys as _sys
    for name in [n for n in _sys.modules if n.startswith("huggingface_hub")]:
        monkeypatch.delitem(_sys.modules, name, raising=False)
    assert bootstrap.enforce_offline() == []


# ===== `.env.example` is the tracked template, and AGENTS.md makes that a hard rule =====

def test_every_settings_field_appears_in_the_env_template():
    """*"Any new `.env` flag must be added to it in the same change."* — AGENTS.md.

    **It was a rule with no enforcement until 2026-08-17**, and it was broken the same day:
    `DIARIZE_MODEL` shipped in `SETTINGS_FIELDS` and not in the template, so a fresh clone would
    have had no idea the field existed. A hard rule that nothing checks is a convention, and this
    repository has spent a week on the difference.
    """
    import re

    template = pathlib.Path(bootstrap.REPO_ROOT, ".env.example").read_text(encoding="utf-8")
    missing = [field.key for field in bootstrap.SETTINGS_FIELDS
               if not re.search(rf"^{field.key}=", template, re.M)]
    assert missing == [], f"{missing} are settings fields with no line in .env.example"


def test_the_template_does_not_claim_a_count_that_can_drift():
    """It said "the nine settings below" while there were eleven. A number in prose beside a list
    is a second source of truth for the length of that list."""
    template = pathlib.Path(bootstrap.REPO_ROOT, ".env.example").read_text(encoding="utf-8")
    for word in ("nine settings", "ten settings", "eleven settings", "eight settings"):
        assert word not in template
