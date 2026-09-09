# 0007 — What the configuration work had to do differently from its plan

- **Status:** accepted
- **Decided:** 2026-08-10
- **Follows from:** R11, R16, R18, R20, R21, R22, R24, R25, R32, R33, R36, R39, R40, R41, R45, R46, R47, R48, V2, V3, V19, V20, V33, V36, V37, V45, V46, V47

## Context

The configuration item was planned in detail before it was built. Five things the plan asserted
turned out to be wrong or under-specified once the code existed. They are recorded here rather
than left as surprises in a diff, because each one is a place where a later reader would
otherwise conclude the implementation drifted from the plan by accident.

## Decisions

### 1. `global_state.py` could not stay untouched, because **R24** forbids it

The plan's file table marked `global_state.py` and `transcriber.py` as untouched by this item.
That cannot hold together with the same plan's *warm eagerly, open streams lazily* section, and
**R24** decides it: Start must be unavailable until warm-up is *confirmed complete*, so warm-up
has to finish before Start is pressable.

Warm-up is fused into `Transcriber.__init__` (**V33**), and `Transcriber` instances were
constructed inside `start_recording()`. Leaving that alone means warm-up happens *at* Start, and
**R24** becomes vacuous. So `start_recording()` is split:

- `warm_up()` — resolves devices and constructs both `Transcriber` instances, which is what
  preloads the models. Touches no stream.
- `start_recording(enable_rag=...)` — opens the streams, starts the session, starts the worker.
  Raises if warm-up has not run.

`transcriber.py` genuinely did stay untouched by this half; its only change belongs to the
anti-hallucination fix below. **The plan's file table was wrong, not the requirement.**

### 2. A settings change after boot means *restart*, not a silent cache rebuild

The plan deferred to code review the question of how `@st.cache_resource` on `get_global_state`
is invalidated when the form rewrites `.env`. The answer is that it cannot be, honestly.
`huggingface_hub` freezes `HF_HOME` at its own import time (**V19**), so once the models have
loaded there is no rebuild that makes a new storage root take effect in this process. A cache
clear would produce a UI reporting one path while weights land in another.

So `bootstrap` records a fingerprint of the settings it applied to the environment
(`STORAGE_ROOT`, `AUDIO_ARCHIVE_DIR`, `ASR_MODEL`, `EMBEDDING_MODEL`) and compares it on every
re-run. A mismatch yields a `restart-required` readiness state with Start disabled and the reason
on screen (**R39**, **R40**). Credentials and URLs are deliberately *not* in the fingerprint —
changing those needs no restart.

### 3. `MULTILINGUAL_MODE` is deleted now, not with the ASR work

The plan scheduled its deletion with the ASR bake-off. But the persisted inventory this item
implements contains `EMBEDDING_MODEL` (**R32**, **R33**), and `build_index.py` was
`MULTILINGUAL_MODE`'s only reader (**V2**, **V3**). Shipping a form that writes a key nothing
reads, alongside a flag no form writes, is the drift these documents exist to prevent.

`build_index.py` now takes the model as an argument, defaulting to `EMBEDDING_MODEL` and then to
the documented default, and still records the name inside the bundle (**V36**). The flag has no
readers left, so its deletion is complete rather than partial. What remains for the ASR work is
unaffected: the flag never reached the ASR layer in the first place.

### 4. The anti-hallucination filter lives in its own module, so its tests can run

`docs/decisions/0006` marked the whole-utterance filter adoptable as-is, as staticmethods on
`Transcriber`. Importing `transcriber` pulls `webrtcvad`, `sounddevice` and `mlx_whisper`, so its
boundary tests can only run where the full audio stack is installed — and **on this machine it is
not**: the project venv satisfies neither `webrtcvad`, `sounddevice` nor `mlx-whisper` from
`requirements.txt`. Tests that skip on import failure would have reported green about a fix
nobody exercised.

The logic is pure, so it moved to `src/text_filters.py` with no dependencies, and `transcriber.py`
imports it. The nine boundary cases from the branch are ported verbatim and **run**.

### 5. Two capabilities are disclosed as absent rather than faked

- **Audio retention.** The pre-flight toggle is sticky and disclosed every session (**R16**,
  **R46**), and warns with a size estimate when armed (**R41**). It writes no audio — that is the
  retention work. The panel says so in as many words, because a switch labelled "retain audio"
  that silently retains nothing is the exact failure **R45** is about.
- **The native folder chooser.** **V45** is still unmeasured: whether a macOS `choose folder`
  dialog can be raised from inside a Streamlit callback without stalling the re-run has not been
  tested. The validated text field is therefore the primary input and the dialog is an opt-in
  button beside it, so a dialog that misbehaves cannot brick the form.

Also deliberate, and smaller: `LLM_MODEL` ships with an **empty** default although the inventory
says it has one. Any value would assert a vendor before the advisor work has chosen one
(**R11**'s stance, applied to a different slot). The field is present and persisted; only the
default is withheld.

## Consequences

- `is_local` now fails closed and additionally accepts `::1`, which the previous host-substring
  check never handled. Names such as `localhost.attacker.net` no longer pass, because the
  comparison is on the parsed host rather than a substring (**V37**).
- `setup_mac.sh` no longer exports a project-local `HF_HOME` or creates `.hf_cache`. It never
  worked outside that script's own shell, and the storage root now owns that path (**R48**).
- The audio pipeline remains **unverified on this machine**: with `webrtcvad`, `sounddevice` and
  `mlx-whisper` absent from the venv, warm-up, Start and the running view have not been executed.
  Only the pure surfaces — settings, path derivation, readiness, host verdict, text filter — are
  covered by tests that were run.
