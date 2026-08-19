"""Configuration, path derivation and startup readiness.

**Zero project imports, and nothing heavy at module scope** -- stdlib plus `dotenv` only.
That is not tidiness: `huggingface_hub` freezes `HF_HOME` at *its* import time (V19), so this
module has to be importable, run, and set the environment *before* anything pulls
`sentence_transformers` or `mlx_whisper`. Importing a project module here would drag those in
and defeat the one mechanism that makes the fixed cache layout (R48) work.

Two functions deliberately import third-party libraries *inside the function body*
(`weights_present`, `download_models`, `index_status`). Each is only ever called after
`apply_environment()` has run, so the ordering above is preserved. Do not lift those imports
to module scope.

Responsibilities:
  - read and write `.env` atomically, as a snapshot of the settings form (R32, V46)
  - resolve one storage root into the fixed layout beneath it (R48)
  - report what already exists under a root before anything is written (R48, V47)
  - own the readiness state machine and the download-progress surface (R23, R24)
  - decide local vs remote from the Host header, failing closed (R34, V37)
"""

import os
import sys
import tempfile
import threading

from dotenv import dotenv_values

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO_ROOT, ".env")

# The layout beneath the storage root is fixed and owned by the application (R48). It is what
# makes a re-entered root reproduce byte-identical paths, so an existing cache is recognised
# instead of re-downloaded (V47).
APP_DIR_NAME = "AegisPrompter"
MODELS_SUBDIR = "models"
AUDIO_SUBDIR = "audio"


# ===== The persisted inventory =====
# Normative source is the "Persisted fields" table in REQUIREMENTS.md. This list implements it;
# it does not get to invent keys. Adding a field here means adding it there first.

class Field:
    """One row of the settings form."""

    def __init__(self, key, label, required=False, secret=False, default="",
                 kind="text", help="", warning=""):
        self.key = key
        self.label = label
        self.required = required
        self.secret = secret
        self.default = default
        self.kind = kind          # "text" | "path"
        self.help = help
        self.warning = warning    # shown when the operator changes this field (R41)


SETTINGS_FIELDS = [
    Field("STORAGE_ROOT", "Storage root", required=True, kind="path",
          help="One folder holds everything large. The app owns the layout beneath it: "
               "<root>/AegisPrompter/{models,audio}. Re-entering the same root after a reset "
               "finds the same weights again.",
          warning="Re-entering a previous root reuses its cache; a new root downloads afresh."),
    Field("AUDIO_ARCHIVE_DIR", "Audio archive override", kind="path",
          help="Optional. Retained recordings go to <root>/AegisPrompter/audio unless this "
               "points somewhere else -- for when weights and recordings belong on different "
               "volumes."),
    Field("QDRANT_URL", "Qdrant URL",
          help="Optional. Empty means local mode; retrieval still works."),
    Field("QDRANT_API_KEY", "Qdrant credential", secret=True,
          help="Only used when a Qdrant URL is set."),
    Field("EMBEDDING_MODEL", "Embedding model",
          default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
          help="Used when compiling the knowledge index. Give the full repository id: "
               "`sentence-transformers` resolves a bare name by prefixing its own namespace, but "
               "`huggingface_hub` does not, so a bare name cannot be pre-downloaded.",
          warning="An index built with a different model must be rebuilt -- the stored vectors "
                  "are not comparable (V36)."),
    Field("LLM_BASE_URL", "LLM base URL",
          help="Optional. OpenAI-compatible endpoint. Empty hides the LLM advisor entirely."),
    Field("LLM_API_KEY", "LLM credential", secret=True,
          help="Only used when an LLM base URL is set."),
    Field("LLM_MODEL", "LLM model name",
          help="Required by most runtimes once an LLM base URL is set -- Ollama, LM Studio and "
               "vLLM all reject a request with no model. It ships empty because any default here "
               "would assert a vendor, which R31 keeps out of this app; the advisor sends the "
               "field only when it is filled, so an empty one produces the endpoint's own error "
               "rather than a wrong guess. Use the pre-flight probe to check it."),
    Field("DIARIZE_MODEL", "Speaker separation model",
          default="pyannote/speaker-diarization-community-1",
          help="Only for the optional voice separation on the re-listening pass. The default is "
               "pyannote's own and its weights are **gated**, so it needs a Hugging Face token "
               "below. `ivrit-ai/pyannote-speaker-diarization-3.1` is an MIT mirror of the older "
               "3.1 pipeline that needs **no token** — a third party re-hosting, so it is a "
               "supply-chain choice rather than a free lunch. Anything whose pipeline runs in "
               "somebody's cloud is refused before it runs.",
          warning="Changing this changes which weights are downloaded and whether a token is "
                  "needed at all."),
    Field("HF_TOKEN", "Hugging Face token", secret=True,
          help="Only needed for speaker separation on the re-listening pass. Its weights are "
               "gated, so downloading them requires an account that has accepted the model's "
               "terms. Nothing else in this application uses a token, and leaving it empty "
               "changes nothing else.",
          warning="A token is a credential. It is stored in `.env` like the others and is never "
                  "rendered to a remote browser (R43)."),
    Field("VAD_GATE", "Screen out non-speech before transcribing", default="false",
          help="Off by default. When on, a voice-activity detector runs on each segment and "
               "segments without speech are never transcribed. Measured: it removes **65%** of "
               "real non-speech and **96%** of instrumental music, costs **3%** of quiet real "
               "speech, and touches no clean speech (V82). It is also *faster* — 32 ms to skip a "
               "decode that costs up to 2235 ms (V83). Leave it off and every segment is "
               "transcribed, which is what happens today: the model invents a sentence from "
               "almost every piece of non-speech (V72, V79).",
          warning="This discards audio before it is transcribed. It fails open — any error "
                  "transcribes the segment — but when it works it is deciding what never reaches "
                  "the record (R3)."),
    Field("VAD_MODEL", "Voice-activity model", default="ivrit-ai/pyannote-segmentation-3.0",
          help="Only used when the screen above is on. The default needs no Hugging Face token; "
               "it is a third-party re-host of pyannote's weights, which is a supply-chain "
               "judgement rather than a free lunch (R50, docs/decisions/0013)."),
    Field("VAD_MIN_SPEECH", "Speech required, seconds", default="0.25",
          help="Seconds of detected speech a segment needs to be transcribed. **0.25 is the "
               "knee, measured, not a guess** (V82): every larger value is a worse bargain than "
               "the one before — 0.40 removes 23 more false lines but destroys 19 real "
               "utterances, 0.60 removes 11 more and destroys 31.",
          warning="Raising this trades real speech for silence, and V64 ranks a destroyed answer "
                  "above a noisy line."),
    Field("ASR_MODEL", "ASR model", default="mlx-community/whisper-large-v3-turbo",
          help="Persisted rather than per-meeting: switching it discards warmed NPU state. Must "
               "be an **MLX-converted** Whisper repository — one holding `config.json` and "
               "`weights.safetensors`. A transformers-format repository of the same model will "
               "not load. Provenance is a constraint here and not only quality (R50): see "
               "`docs/decisions/0012`.",
          warning="Changing this requires a process restart. The loaded ASR model cannot be "
                  "swapped in a live process — Stop Streamlit and run it again (V19, V33)."),
]

FIELDS_BY_KEY = {f.key: f for f in SETTINGS_FIELDS}

# Sticky operator preferences: not typed into the form, but persisted for the same reason --
# nothing on the machine can rediscover them and they cannot go stale (R16, R33).
#
# `MIC_DEVICE` holds a device *name*, never an index -- PortAudio's indices shift between runs
# and between machines, so a persisted index silently comes to mean a different microphone.
# Empty is a meaningful value and the default one: it means "follow whatever macOS calls the
# default input", which is R26's sensible default. It is deliberately **not** in `fingerprint()`:
# changing the microphone must not demand a restart, which is the whole point of separating
# "change device" from "reload model".
STICKY_KEYS = ("ARCHIVE_AUDIO", "MIC_DEVICE")

# Derived by the app from the storage root, never typed (R48). Written into `.env` so that the
# value the process exports and the value on disk cannot disagree.
DERIVED_KEYS = ("HF_HOME",)

PERSISTED_KEYS = tuple(f.key for f in SETTINGS_FIELDS) + STICKY_KEYS + DERIVED_KEYS


# ===== Reading and writing `.env` =====

def read_settings(path=ENV_PATH):
    """Return every persisted key as a string, absent ones as `""`.

    Absent configuration is a blank form, never an exception (R20). A key present with an empty
    value and a key that is missing entirely are deliberately indistinguishable here -- both mean
    "the operator has not filled this in".
    """
    values = {key: "" for key in PERSISTED_KEYS}
    try:
        raw = dotenv_values(path)
    except Exception:
        return values
    for key, value in (raw or {}).items():
        if key in values:
            # dotenv yields None for a bare `KEY` with no `=`; that is blank, not the string
            # "None" -- which is the failure the round-trip test exists to catch.
            values[key] = "" if value is None else str(value)
    return values


def _quote(value):
    """Quote a value so `dotenv` reads back exactly what was written.

    Double quotes with backslash escaping: measured to round-trip `#`, `=`, both quote
    characters, backslashes and surrounding whitespace.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'


def render_env(values):
    """Serialize the persisted inventory. Only known keys survive.

    `.env` is a snapshot of the form and the app is its only writer (R32), so a key the form
    does not own is not preserved across a save. That is the point: there is no second place
    configuration can hide.
    """
    lines = [
        "# Written by Aegis Prompter. Do not hand-edit -- the settings form is the interface,",
        "# and the next save overwrites this file (R18, R32). Delete it to reset (R22).",
        "",
    ]
    for field in SETTINGS_FIELDS:
        lines.append(f"{field.key}={_quote(values.get(field.key, ''))}")
    lines.append("")
    lines.append("# Sticky operator preference, set from the pre-flight panel (R16).")
    for key in STICKY_KEYS:
        lines.append(f"{key}={_quote(values.get(key, ''))}")
    lines.append("")
    lines.append("# Derived from STORAGE_ROOT by the app (R48). Editing it will not survive a save.")
    for key in DERIVED_KEYS:
        lines.append(f"{key}={_quote(values.get(key, ''))}")
    lines.append("")
    return "\n".join(lines)


def write_settings(values, path=ENV_PATH):
    """Rewrite `.env` atomically, returning the values as persisted.

    Temporary file in the same directory plus `os.replace()` (V46). Streamlit re-executes the
    whole script on every interaction, so a save interrupted halfway would leave a truncated
    file that reads as a half-configured machine and looks like operator error.
    """
    persisted = {key: str(values.get(key, "") or "") for key in PERSISTED_KEYS}

    # HF_HOME is derived, never taken from the caller.
    root = persisted.get("STORAGE_ROOT", "")
    persisted["HF_HOME"] = derive_paths(root)["models"] if root else ""

    body = render_env(persisted)
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=directory, prefix=".env.", suffix=".tmp", delete=False
    )
    try:
        with handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except Exception:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise
    return persisted


def delete_settings(path=ENV_PATH):
    """Reset: delete `.env` and touch nothing else (R22, R47).

    Nothing on disk that is not configuration is removed. Weights and recordings live under
    operator-supplied paths and are the operator's (R4) -- the UI lists them before this runs so
    the paths are not lost with the file, but it never removes them.
    """
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False


# ===== Path derivation (R48) =====

def normalize_root(raw):
    """Normalise a typed storage root to a canonical absolute path.

    Trailing slashes, `~`, `.` segments and a relative path must all land on the same string,
    because "the same root re-entered" has to mean byte-identical derived paths or the cache is
    invisible and re-downloaded in full (V47).
    """
    if not raw or not raw.strip():
        return ""
    expanded = os.path.expanduser(os.path.expandvars(raw.strip()))
    absolute = os.path.abspath(expanded)
    return os.path.normpath(absolute)


def derive_paths(raw_root):
    """One storage root produces the whole fixed layout. Empty root produces empty paths."""
    root = normalize_root(raw_root)
    if not root:
        return {"root": "", "app": "", "models": "", "audio": ""}
    app_dir = os.path.join(root, APP_DIR_NAME)
    return {
        "root": root,
        "app": app_dir,
        "models": os.path.join(app_dir, MODELS_SUBDIR),
        "audio": os.path.join(app_dir, AUDIO_SUBDIR),
    }


def resolve_archive_dir(settings):
    """Where retained audio goes: the override if given, else derived from the root (R44)."""
    override = (settings.get("AUDIO_ARCHIVE_DIR") or "").strip()
    if override:
        return normalize_root(override)
    return derive_paths(settings.get("STORAGE_ROOT", ""))["audio"]


def is_configured(settings):
    """Configuration is complete when the one required field is filled (R48)."""
    return bool((settings.get("STORAGE_ROOT") or "").strip())


def missing_required(settings):
    return [f.label for f in SETTINGS_FIELDS
            if f.required and not (settings.get(f.key) or "").strip()]


# ===== Reporting what is already there (R48, V47) =====

def format_bytes(count):
    size = float(count)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _tree_stats(path):
    """(file count, total bytes) beneath `path`, counting each byte once.

    **Symbolic links are skipped, not followed.** `huggingface_hub` stores every file once under
    `blobs/` and links to it from `snapshots/<commit>/`, so following links reports exactly double
    the real size -- measured 2026-08-10 as 2.8 GB against a 1.4 GB repository. That number is
    shown to the operator on the Configure screen as "existing cache found", and it is the
    denominator-free half of the download progress figure, so getting it wrong is visible in two
    places at once.
    """
    if not path or not os.path.isdir(path):
        return 0, 0
    files = 0
    total = 0
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                continue
            try:
                total += os.path.getsize(full)
                files += 1
            except OSError:
                continue
    return files, total


def inspect_root(raw_root):
    """Report what is already under a root, before anything is written to it.

    This is what turns re-entering a root from something the operator must get exactly right
    into something the app confirms (R48).
    """
    paths = derive_paths(raw_root)
    report = {"paths": paths, "exists": bool(paths["root"]) and os.path.isdir(paths["root"])}
    model_files, model_bytes = _tree_stats(paths["models"])
    audio_files, audio_bytes = _tree_stats(paths["audio"])
    report["models"] = {"files": model_files, "bytes": model_bytes}
    report["audio"] = {"files": audio_files, "bytes": audio_bytes}
    report["writable"] = _is_writable(paths["root"])
    return report


def _is_writable(path):
    """Whether the app could create its layout under this root.

    Walks up to the nearest existing ancestor, because the root itself may not exist yet.
    """
    if not path:
        return False
    candidate = path
    while candidate and not os.path.isdir(candidate):
        parent = os.path.dirname(candidate)
        if parent == candidate:
            return False
        candidate = parent
    return os.access(candidate, os.W_OK)


# ===== Applying configuration to the process environment =====

_applied_lock = threading.Lock()
_applied_fingerprint = None


def fingerprint(settings):
    """A stable digest of the settings that this process bakes into its environment.

    Only the keys whose effect cannot be undone after import are included -- changing any of
    them means the process must restart, and that has to be stated rather than silently ignored.
    """
    # `VAD_*` are here for the same reason `ASR_MODEL` is: `voice_gate` caches its pipeline in a
    # module global, so a changed model id cannot take effect in a live process. The gate toggle
    # and its floor are baked into each `Transcriber` at warm-up, which a running session does not
    # redo -- so all three demand a restart rather than appearing to apply and not applying.
    keys = ("STORAGE_ROOT", "AUDIO_ARCHIVE_DIR", "ASR_MODEL", "EMBEDDING_MODEL",
            "VAD_GATE", "VAD_MODEL", "VAD_MIN_SPEECH")
    return "|".join(f"{k}={settings.get(k, '')}" for k in keys)


def enforce_offline():
    """Forbid `huggingface_hub` from touching the network for the rest of this process.

    Called once the weights are on disk, immediately before the ASR stack is imported. Observed
    2026-08-11 on `huggingface_hub` 1.27: warm-up issued two HTTPS requests to huggingface.co --
    a revision lookup and a file-tree listing -- even though every file resolved from the local
    cache. The README promises zero external dependencies and zero telemetry, and a meeting
    machine that phones home on start is not that, however harmless the payload.

    Deliberately **not** set in `apply_environment()`: the download step runs after it and needs
    the network. Offline is the state the app enters once it has what it needs, not the state it
    boots in.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"

    # The environment variable alone does nothing once the library is loaded, and by this point it
    # always is -- `download_models` imported it a moment ago. `huggingface_hub` reads
    # HF_HUB_OFFLINE into a module constant at **import** time, so setting the variable afterwards
    # changes a string nobody reads again. This is V19's mechanic applied to a second variable, and
    # it meant this function had never once worked: verified 2026-08-12 from a live run, where
    # warm-up issued `GET huggingface.co/api/models/.../revision/main` 238 ms after this returned.
    #
    # Reached through `sys.modules` rather than by importing: this module carries no heavy imports
    # (V19), and a lookup that finds nothing is the correct outcome for a process that never loaded
    # the library. Only `huggingface_hub.constants` holds the value -- checked, rather than assumed,
    # by looking for every loaded submodule that binds the name.
    patched = []
    for name, module in list(sys.modules.items()):
        if name.startswith("huggingface_hub") and hasattr(module, "HF_HUB_OFFLINE"):
            module.HF_HUB_OFFLINE = True
            patched.append(name)
    return patched


def apply_environment(settings):
    """Export the derived paths into `os.environ` and record what was applied.

    Must run before `huggingface_hub` is imported anywhere, which is why this module carries no
    heavy imports of its own (V19).
    """
    global _applied_fingerprint
    paths = derive_paths(settings.get("STORAGE_ROOT", ""))
    if paths["models"]:
        os.makedirs(paths["models"], exist_ok=True)
        os.environ["HF_HOME"] = paths["models"]
    for key in ("ASR_MODEL", "EMBEDDING_MODEL", "QDRANT_URL", "QDRANT_API_KEY",
                "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "HF_TOKEN", "DIARIZE_MODEL",
                "AUDIO_ARCHIVE_DIR",
                "ARCHIVE_AUDIO"):
        value = (settings.get(key) or "").strip()
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    with _applied_lock:
        _applied_fingerprint = fingerprint(settings)
    return paths


def applied_fingerprint():
    with _applied_lock:
        return _applied_fingerprint


def needs_restart(settings):
    """True when settings changed after this process already baked the old ones in.

    `HF_HOME` cannot be moved once `huggingface_hub` has imported (V19), so pretending a live
    change took effect would send weights to one directory while the UI reports another.
    """
    applied = applied_fingerprint()
    return applied is not None and applied != fingerprint(settings)


# ===== Readiness state machine (R24) =====

NO_CONFIG = "no-config"
# Configured, and **nothing loaded**. The state a freshly opened page sits in, and the state Stop
# returns to. Added 2026-08-14 with the rule that only Start costs anything: opening the app must
# not download gigabytes or warm 1794 MB of weights nobody asked for, and merely looking at the
# settings on a metered connection must not pull a model.
IDLE = "idle"
DOWNLOADING = "downloading"
WARMING = "warming"
READY = "ready"
RESTART_REQUIRED = "restart-required"
FAILED = "failed"

_readiness_lock = threading.Lock()
_readiness = {"state": NO_CONFIG, "detail": ""}
_progress = {}
# Monotonic id of the boot attempt that is allowed to write readiness. Background download/warm
# threads capture the id they were started with; after a settings change invalidates the boot,
# their set_readiness calls become no-ops so a late READY cannot overwrite restart-required.
_boot_id = 0


def begin_boot():
    """Start a new boot attempt. Returns the id that in-flight callbacks must pass back."""
    global _boot_id
    with _readiness_lock:
        _boot_id += 1
        return _boot_id


def invalidate_boot():
    """Revoke every in-flight boot's right to update readiness.

    Called when configuration changes after models were loaded (V19): a warm-up that was already
    running must not be allowed to flip the UI back to Ready over a Restart-required banner.
    """
    global _boot_id
    with _readiness_lock:
        _boot_id += 1
        return _boot_id


def current_boot_id():
    with _readiness_lock:
        return _boot_id


def get_readiness():
    with _readiness_lock:
        return dict(_readiness)


def set_readiness(state, detail="", boot_id=None):
    """Update readiness. Returns False when a stale boot tries to write after invalidation."""
    with _readiness_lock:
        if boot_id is not None and boot_id != _boot_id:
            return False
        _readiness["state"] = state
        _readiness["detail"] = detail
        return True


def is_ready():
    return get_readiness()["state"] == READY


def progress_snapshot():
    """Per-repository download progress, as `{repo_id: {done, total, finished, error}}`."""
    with _readiness_lock:
        return {repo: dict(entry) for repo, entry in _progress.items()}


def _record_progress(repo_id, done, total, finished=False, error=""):
    with _readiness_lock:
        entry = _progress.setdefault(repo_id, {"done": 0, "total": 0, "finished": False,
                                               "error": ""})
        entry["done"] = max(entry["done"], int(done or 0))
        entry["total"] = max(entry["total"], int(total or 0))
        if finished:
            entry["finished"] = True
        if error:
            entry["error"] = error


def resolved_model(settings, key):
    """The repository id for a model setting, falling back to its documented default."""
    return (settings.get(key) or FIELDS_BY_KEY[key].default or "").strip()


def required_repos(settings):
    """The model repositories a configured machine fetches ahead of the first meeting."""
    repos = []
    for key in ("ASR_MODEL", "EMBEDDING_MODEL"):
        value = resolved_model(settings, key)
        if value and value not in repos:
            repos.append(value)
    return repos


def essential_repos(settings):
    """The subset whose absence must stop startup.

    Only the ASR model. Warm-up loads it, so failing to fetch it means there is nothing to warm
    and Start would be a lie. The embedding model is **not** essential: the retrieval advisor is a
    per-meeting choice that may never be armed, and when it is, `LocalAdvisor` loads the model
    named *inside* the compiled index rather than this setting (V3, V36). Treating its download
    failure as fatal would leave Start permanently disabled over a component the session may not
    use — which is a worse failure than the one it guards against.
    """
    asr = resolved_model(settings, "ASR_MODEL")
    return [asr] if asr else []


# Model repositories routinely ship the same weights in several framework formats. This runtime
# loads exactly one of them -- MLX for speech, PyTorch/safetensors for embeddings -- so everything
# below is bytes that can never be read. Measured on
# `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 2026-08-10: an unfiltered fetch
# pulled 4.1 GB, of which onnx (2.4 GB), openvino (563 MB) and tf_model.h5 (449 MB) were dead
# weight. Excluding them is the difference between a 450 MB download and a 4 GB one (R21).
#
# Deliberately NOT excluded: `pytorch_model.bin`, which duplicates `model.safetensors`. Preferring
# safetensors is `sentence_transformers`' choice, not something this layer gets to assume for
# every repository, and guessing wrong means a model that will not load at all.
UNUSED_WEIGHT_FORMATS = ["onnx/*", "openvino/*", "*.h5", "*.msgpack", "*.ckpt", "*.tflite"]


def weights_present(repo_id):
    """Whether `repo_id` resolves entirely from the local cache.

    Imports `huggingface_hub` lazily -- by the time this is called `apply_environment()` has
    already set `HF_HOME`, which is the ordering V19 says is easy to get backwards.
    """
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        return False
    try:
        # Same filter as the download, or a cache fetched with it would be judged incomplete and
        # re-fetched on every launch.
        snapshot_download(repo_id, local_files_only=True,
                          ignore_patterns=UNUSED_WEIGHT_FORMATS)
        return True
    except Exception:
        return False


def repo_cache_dir(repo_id):
    """Where `huggingface_hub` stores one repository beneath the configured cache."""
    hub = os.path.join(os.environ.get("HF_HOME", ""), "hub") if os.environ.get("HF_HOME") else ""
    return os.path.join(hub, "models--" + repo_id.replace("/", "--")) if hub else ""


# Bound the Hub metadata call that sizes a download. Without this, a captive portal or a hung
# DNS leaves readiness at DOWNLOADING with no byte updates — frozen, which R23 forbids — and
# `snapshot_download` never even starts. Fifteen seconds is long enough for a slow link and short
# enough that the operator still sees the panel change.
REPO_INFO_TIMEOUT_S = 15.0


def expected_repo_bytes(repo_id):
    """Total size of the files this app will actually fetch, or 0 if it cannot be determined.

    Asks the Hub for per-file metadata and applies the same exclusions as the download, so the
    denominator matches the numerator. Returns 0 on any failure -- an unknown total degrades the
    display to "in progress", which is honest, rather than to a wrong percentage. The Hub call is
    bounded by `REPO_INFO_TIMEOUT_S`; an unbounded wait here is worse than a missing denominator.
    """
    try:
        import fnmatch

        from huggingface_hub import HfApi

        info = HfApi().repo_info(
            repo_id, files_metadata=True, timeout=REPO_INFO_TIMEOUT_S,
        )
    except Exception:
        return 0
    total = 0
    for sibling in getattr(info, "siblings", None) or []:
        name = getattr(sibling, "rfilename", "") or ""
        if any(fnmatch.fnmatch(name, pattern) for pattern in UNUSED_WEIGHT_FORMATS):
            continue
        total += getattr(sibling, "size", None) or 0
    return total


def _watch_repo_bytes(repo_id, total, stop_event, interval=1.0):
    """Poll bytes *added* under one repository until told to stop.

    `huggingface_hub`'s `tqdm_class` decorates **only** the outer "Fetching N files" bar -- its own
    docstring says the class "is not passed to each individual download". An earlier version of
    this module assumed otherwise and therefore reported *file counts* dressed up as bytes: during
    a real 1.5 GB fetch the bar sat at exactly 75% (3 of 4 files) for the whole of the largest
    file. That is the frozen-progress failure R23 exists to prevent, so progress is measured from
    the cache directory instead, where a large file visibly grows.

    The numerator is growth since this watch started, not the absolute size of the cache directory.
    A repository that already holds blobs from an earlier revision would otherwise report well
    above 100% on the first poll (absolute bytes vs current-revision total), and the bar would sit
    pinned at full while the real fetch continued — the same frozen-looking failure in a different
    costume. `refs/`, `.locks` and leftover blobs all sit in the baseline and cancel out.
    """
    baseline = _tree_stats(repo_cache_dir(repo_id))[1]
    while not stop_event.is_set():
        current = _tree_stats(repo_cache_dir(repo_id))[1]
        _record_progress(repo_id, max(0, current - baseline), total)
        stop_event.wait(interval)
    current = _tree_stats(repo_cache_dir(repo_id))[1]
    _record_progress(repo_id, max(0, current - baseline), total)


def download_models(settings, on_complete=None, boot_id=None):
    """Fetch any missing weights in the background, reporting progress as it goes (R21, R23).

    Returns the thread so a caller can join it in a test. Nothing is downloaded before the
    operator has configured a storage root, which is what R21 is about. `boot_id`, when given,
    ties every readiness write to the boot attempt that started this download so a revoked boot
    cannot resurrect Ready after a restart has been demanded.
    """
    repos = required_repos(settings)
    essential = set(essential_repos(settings))

    def _run():
        try:
            from huggingface_hub import snapshot_download
        except Exception as exc:
            set_readiness(FAILED, f"huggingface_hub unavailable: {exc}", boot_id=boot_id)
            return
        for repo in repos:
            if weights_present(repo):
                _record_progress(repo, 1, 1, finished=True)
                continue
            if not set_readiness(DOWNLOADING, repo, boot_id=boot_id):
                return
            # Resolve the denominator before the watcher starts. Bound inside expected_repo_bytes;
            # a hang here would leave the panel on DOWNLOADING with no byte motion (R23).
            total = expected_repo_bytes(repo)
            stop_watch = threading.Event()
            watcher = threading.Thread(
                target=_watch_repo_bytes, args=(repo, total, stop_watch),
                name=f"aegis-progress-{repo}", daemon=True,
            )
            watcher.start()
            try:
                snapshot_download(repo, ignore_patterns=UNUSED_WEIGHT_FORMATS)
                _record_progress(repo, 1, 1, finished=True)
            except Exception as exc:
                # An essential model that will not download means there is nothing to warm, so
                # startup stops and says why. A non-essential one is recorded against its own row
                # and startup continues -- the pre-flight panel shows the error, and the feature
                # that needed it reports itself unavailable rather than blocking Start (R39, R40).
                _record_progress(repo, 0, 0, error=str(exc))
                if repo in essential:
                    set_readiness(FAILED, f"Download of {repo} failed: {exc}", boot_id=boot_id)
                    return
            finally:
                # The watcher must die on every path, including the early `return` above, or a
                # failed download leaves a thread polling the filesystem for the life of the app.
                # Join, don't only signal: the next repo's watcher would otherwise race the old
                # one on `_record_progress` for up to one poll interval.
                stop_watch.set()
                watcher.join(timeout=2.0)
        if on_complete is not None:
            on_complete()

    thread = threading.Thread(target=_run, name="aegis-download", daemon=True)
    thread.start()
    return thread


# ===== Knowledge index status (R36, V34) =====

def index_status(settings=None):
    """Chunk count, build date and embedding model of the knowledge collection, or why there is
    none.

    An invisible precondition made visible while the operator can still act on it. Delegates to
    `knowledge_store`, imported lazily: it pulls `qdrant_client`, and this module is stdlib +
    dotenv precisely so that importing it costs nothing before a storage root exists (V19, V20).
    Never raises -- an unreachable Qdrant is a line on the panel, not a broken screen.
    """
    values = settings if settings is not None else read_settings()
    try:
        import knowledge_store
        return knowledge_store.status(values)
    except Exception as exc:
        return {"present": False, "chunks": 0, "built": "", "model": "", "target": "",
                "error": f"index unreadable: {type(exc).__name__}: {exc}"}


# ===== Local versus remote (R34, V37) =====

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _host_only(host):
    """Strip the port from a Host header value, IPv6 literals included."""
    value = host.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end != -1 else value[1:]
    if value.count(":") == 1:
        value = value.split(":")[0]
    return value


def is_local_host(host):
    """True only when the request demonstrably came from this machine.

    Fails **closed**: an empty Host header, an unparseable one, or anything that is not a
    loopback name is treated as remote. The previous behaviour granted local on both of those
    paths (V37), which was harmless while it only skipped a PIN prompt and is not harmless now
    that the same verdict gates credentials rendered into a browser over plain HTTP (R43).
    """
    if not host:
        return False
    try:
        return _host_only(host) in LOOPBACK_HOSTS
    except Exception:
        return False
