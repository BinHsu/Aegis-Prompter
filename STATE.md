# Project State

Tracks progress, roadmap, and open issues. For how to work in the repo, see
[AGENTS.md](AGENTS.md). For the release history, see [CHANGELOG.md](CHANGELOG.md).

**Current release: `v0.0.1`** — BlackHole audio backend.

## 🧭 Design stance

> **Whatever your ears can hear and whatever your mouth says, we ingest.**
>
> **Our job is not to lose it. What it gets used for is the file owner's decision.**

Capture is deliberately **source-agnostic**. It does not matter whether the meeting runs in
Zoom's native app, Meet in a browser tab, Teams, or anything else — the system takes the
entire system output mix as one track and the microphone as the other. There are exactly
**two tracks, forever**, and the existing dual-`Transcriber` architecture is exactly the
right shape for that.

The second half of the stance draws the product boundary: the system is responsible for
**completeness of capture**, not for policy about the captured material. Retention,
post-processing, redaction, and disclosure are the operator's calls — which is why cleanup
(7.4) and audio retention (7.5) are opt-in tools rather than pipeline behaviour.

Consequences that follow directly from this stance, and should not be relitigated without
revisiting the stance itself:

- **No per-application audio filtering.** Tapping "only Zoom" is useless when the meeting is
  a browser tab (tapping Chrome captures all of Chrome), and a bundle-ID allowlist is
  unmaintainable across apps the user may switch between. Take the global mix.
- **Noise is accepted at the capture layer and filtered downstream.** Spotify, Slack chimes,
  and notification sounds will enter the participant track. The defences are `webrtcvad`
  (severity 3), Whisper's `no_speech_threshold`, and the anti-hallucination blacklist in
  `transcriber.py`. Note VAD is unreliable on *music*, which can be misclassified as speech
  and then hallucinated into text.
- **Headphones are an operational requirement, not a preference.** See Known Issues.

## 🟢 Completed — Phase 6

Transition from a Gemini-dependent script to a **Pure Local + Multi-Role** architecture
with an English-only codebase.

- Defined the Phase 6 implementation plan.
- Switched licensing to MIT; added the `LICENSE` file.
- Updated `requirements.txt` to drop `google-genai` and add `sentence-transformers`.
- Added `MULTILINGUAL_MODE` support to `.env`.
- **Knowledge Compiler (`src/build_index.py`)** — compiles `.md`/`.txt` into
  `context/knowledge_index.pkl` via `sentence-transformers`.
- **Pure Local RAG (`src/local_advisor.py`)** — loads the vector index and runs
  cosine-similarity trigger matching. `gemini_advisor.py` removed.
- **State & UI refactor (`app.py`, `global_state.py`)**
  - Codebase translated to English. `tests/unit/test_buffer.py` was the last holdout — its
    assertions still expected the pre-translation Chinese strings and failed until fixed.
  - Role routing via query parameter (`?role=speaker` vs `?role=staff`).
  - Staff manual broadcast UI pushing into `global_state.buffer`.
  - Auto-scroll UX via `get_formatted_dialogue(max_lines=5)`.
- **Decoupled the audio pipeline from the NPU bottleneck** to stop dropped frames —
  `transcriber.py` now uses a separate `inference_queue` and a dedicated inference thread.

---

# 🔵 Phase 7 Roadmap

Goals in the order they should be executed, chosen so that each step is independently
shippable and the riskiest work lands last.

**Do 7.6a first.** It is a small change and it closes a security ordering defect — capture
currently starts before authentication.

## 7.1 — Multilingual ASR (EN + ZH in one meeting) 🔴 BLOCKING BUG

**The current model cannot transcribe Chinese at all.** `transcriber.py` defaults to
`mlx-community/distil-whisper-large-v3`, and Distil-Whisper is **English-only** by design —
its 6x speedup comes precisely from being trained on English audio only. This is not a
quality problem; Chinese is simply unsupported.

**`MULTILINGUAL_MODE` does not do what its name implies.** It appears only in
`build_index.py`, where it selects the *RAG embedding model*. It has never reached the ASR
layer. Setting it to `true` gives multilingual retrieval over an English-only transcript.

Plan:

1. Switch the default to **`mlx-community/whisper-large-v3-turbo`** — multilingual (99+
   languages), 1.61 GB in quantized MLX form, roughly 5x faster than `large-v3`.
2. **Make `MULTILINGUAL_MODE` govern both layers** (ASR model *and* embedding model) so the
   flag is finally honest.
3. **Handle Traditional vs Simplified Chinese.** Whisper has a single `zh` token and was
   trained on a mix, so it will sometimes emit Simplified characters. Simplified text on a
   Taiwanese teleprompter is a hard failure. Mitigation: a Traditional-Chinese
   `initial_prompt` to bias decoding, plus OpenCC post-processing as a backstop.
4. **Re-measure latency.** `turbo` is faster than `large-v3` but slower than `distil`, and
   two tracks share `NPU_LOCK`. Confirm `audio_queue` does not start dropping frames again —
   that regression was only fixed in `201eeea`.

Already favourable: no architectural change is needed for code-switching. Each VAD segment
is a separate `transcribe()` call with no `language` argument, so language is auto-detected
per chunk. Intra-*sentence* code-switching will still be weak — a Whisper limitation, not
fixable by model choice.

Risk: `turbo` is known to be slightly weaker than `large-v3` on some languages. Mandarin is
generally fine, but this must be measured on real meeting audio, not inferred from specs.

## 7.2 — Core Audio process tap, as the default backend

Replace BlackHole with the native Core Audio process-tap API. Feasibility was verified
empirically on macOS 26.6 using Command Line Tools `clang` only — no Xcode required.

Verified findings:

- `AudioHardwareCreateProcessTap` is `API_AVAILABLE(macos(14.2))` — **14.2, not 14.4**.
- **A global mono mixdown tap is the shape we want** (`initMonoGlobalTapButExcludeProcesses`
  with an empty exclude list), per the design stance above. Measured: `err=0`, format
  **48kHz / mono / float32 packed**, and 190,976 frames captured over 4 seconds with real
  signal (`peak=0.297`).
- **Dropping per-app capture lowers the OS requirement from 26.0 to 14.2.**
  `CATapDescription.bundleIDs` and `.processRestoreEnabled` are the only members needing
  macOS 26.0, and a global tap needs neither — it does not care whether Zoom restarts.
- A tap exposed through a **non-private aggregate device is visible cross-process** as an
  ordinary input device. This is the key architectural result: `sounddevice`/PortAudio
  enumerate it like any mic, so **`transcriber.py` needs no changes** — only the device
  keyword list in `global_state.py`.
- `muteBehavior = CATapUnmuted` lets the user keep hearing the audio, removing the need for
  a Multi-Output Device (BlackHole requires one or the speaker goes deaf).
- **TCC**: tap capture triggers a `kTCCServiceAudioCapture` check, attributed to the
  **responsible process — the terminal app (e.g. `Terminal.app`), not the tap binary**. This
  is *not* a new class of risk: the BlackHole path already requires that same responsible
  process to hold `kTCCServiceMicrophone`.

Open risks:

- **Sample rate is the one unverified integration point.** The tap is fixed at 48kHz but
  `transcriber.py` opens the stream at 16kHz; whether PortAudio resamples is untested. This
  is the first thing to hit during implementation. `webrtcvad` accepts 48000, so the fallback
  is to run VAD at 48k and resample only before Whisper.
- **Largest ongoing cost**: the aggregate device binds a specific output device as its main
  sub-device, so it goes stale when the user switches output (plugging in headphones).
  Requires a `kAudioHardwarePropertyDefaultOutputDevice` listener to rebuild. BlackHole does
  not have this problem — the only respect in which it is superior.

Plan — **additive backend first, then flip the default**:

1. Add `src/native/aegis_tap.m`, compiled by `setup_mac.sh`.
2. `global_state.py` launches it as a subprocess in `start_recording()`, SIGTERMs it in
   `stop_recording()`.
3. **Auto-detect rather than configure** (per 7.6c): use the tap when the OS supports it and the
   device appears, otherwise BlackHole. Surface which one is active in the UI; this is a
   capability, not a user preference.
4. Prove it in real meetings, **then** make `tap` the default.
5. Keep the BlackHole fallback permanently — it covers macOS older than 14.2.

## 7.3 — Device selection in the web UI

**Decision: the dropdown remote-controls the host Mac's capture devices. It is not a browser
device picker.** Browser-side capture (`getUserMedia`, as Zoom/Meet web do it) was
considered and rejected as *impossible*, for two independent reasons:

1. **The remote iPad cannot access the API at all.** `navigator.mediaDevices` is
   `[SecureContext]`; outside a secure context it is `undefined` and calling `getUserMedia()`
   throws `TypeError`. Secure contexts are HTTPS, `file://`, and **localhost** —
   `http://192.168.x.x:8501` is none of these. Only the browser on the Mac itself qualifies.
2. **Even locally, the browser cannot supply the participant track.** Safari on macOS does
   not support `getDisplayMedia` audio at all; Firefox ignores it; Chrome supports tab audio,
   and system audio only from Chrome 141+ on macOS 14.2+ — which is itself built on the very
   same Core Audio process tap. Going through the browser yields a more constrained version
   of what the native tap already gives us.

So the browser could at best supply the Mac's microphone, which server-side PortAudio
already does better: no encoding, no transport, no permission prompt.

This framing is *more* useful than the Zoom/Meet model for this product: staff off-stage can
retune the speaker's capture from an iPad without touching the Mac.

Scope, reduced by the design stance — if system audio is "everything", there is no source to
choose:

- **Microphone dropdown** — genuinely useful (built-in / AirPods / USB mic).
- **Backend selector** (`tap` / `blackhole`) — transitional; can be retired later.
- No system-audio source dropdown. It was going to be two dropdowns; it is one.

Implementation note: the UI already has half of this. The `st.progress(rms)` level meters in
`app.py` are exactly the meter Zoom shows beside its device picker, so dropdown + existing
meter gives the familiar UX with no new visual work.

Implementation trap: `Transcriber.__init__` preloads the Whisper model into the NPU, which is
slow. Switching devices must **not** naively reconstruct a `Transcriber` — separate "change
device" from "reload model".

Bonus: a dropdown makes the hardcoded-microphone-keyword bug (Known Issues) irrelevant.

## 7.4 — Speaker labels and transcript cleanup: an offline operator script

**Decision: no ASR-side diarization. No second model.** Speaker attribution and text cleanup
happen after the meeting, in a shell script the operator runs by hand.

The reasoning that removes the whole ML problem:

- **Live transcription does not need speaker identity.** `_local_rag_worker_loop` triggers on
  `role == "Participant"` only; it never cares *which* remote person is speaking. Participant
  A vs B matters solely for the archive, and the archive is read after the fact.
- **Live subtitle quality is explicitly not a goal.** The speaker on stage needs the gist,
  not a clean transcript. Everything cosmetic is deferred.

So the plan is a script — `tools/` — that feeds an archived `history/Meeting_*.md` to headless
Claude (`claude -p`) with a fixed prompt, and writes a cleaned copy alongside it. The prompt
covers, using full-document context:

- normalizing to Traditional Chinese (see below on why this beats OpenCC),
- re-flowing punctuation and segment boundaries broken by VAD flushes,
- splitting `Participant` into distinct speakers from conversational context,
- dropping residual Whisper hallucinations.

Consequences worth recording:

- **This deletes what was the highest-risk item on the roadmap.** No pyannote / sherpa-onnx,
  no speaker embeddings, no online clustering, no extra rolling raw-audio buffer, and no
  exposure to the unsolved problem that speaker embeddings are unreliable on sub-second
  segments — exactly the short-interjection case this product exists for.
- **Speaker labelling itself needs no archived audio** — the cleanup pass works from text.
  Audio retention is a separate feature with a separate rationale; see 7.5.
- **Do not apply OpenCC in the live path.** Its Simplified/Traditional ambiguities (后/後 and
  similar, worst in names and places) are precisely the cases that need surrounding context to
  resolve, which is what the post-processing pass has and a character-mapping rule does not.
  Live keeps only the `initial_prompt` nudge from 7.1.
- **The app's offline guarantee is unaffected.** This is an operator tool run deliberately
  outside the application; no runtime code path reaches the network. It should still carry a
  one-line notice that running it sends transcript content to Claude, since `history/`
  contains meeting records.
- Write to a new file rather than overwriting. The raw transcript is the record of what was
  actually heard.

### How the comparable products split their audio

Two different Zoom features get confused here, and only the second is a real comparison.

**Zoom's in-meeting live captions** are not comparable. Zoom *is* the conferencing layer, so
each participant is a separate connection, and it labels the transcript by **active speaker
detection** — which connection is currently transmitting. That is transport metadata, not
inference, which is why those labels are accurate. It also means the approach cannot be
borrowed: this project captures the **post-mix system output**, where per-participant identity
was destroyed by the mixer before the audio reached the speakers. An information asymmetry,
not a capability gap. And it fails in this product's own scenario anyway — several people
sharing one connection (a hearing room, one conference mic) all get attributed to the same
participant.

**Zoom's "listen to the meeting" mode** (AI Companion / My Notes, which also works over
third-party platforms like Teams and Meet) *is* the real comparison, and it lands on the same
architecture as this project — because the OS forces it:

- **macOS provides no single API that yields microphone and system output as one stream.** The
  mic is an input device; system output needs either a virtual driver or a Core Audio process
  tap. Capture is necessarily two separate operations for any device-audio listener — Zoom's
  My Notes, Granola, or this project.
- **Zoom's own wording indicates inference, not metadata**: AI Companion "will do its best to
  differentiate between **you and other parties** to keep track of **multiple speakers**."
  "Does its best" is not how transport metadata is described. And the you-vs-others boundary
  is exactly the mic-vs-system-output boundary — the same split as `Speaker (You)` /
  `Participant` here, for the same physical reason. Distinguishing multiple speakers *within*
  the others is still guesswork on their side too.
- **Unverified**: whether Zoom sends the two captures to its ASR separately or mixes them
  first. Undocumented, and it does not matter here — this project already keeps them separate,
  which is strictly better since role labels come for free.

Conclusion: the comparable products hold no extra card on speaker attribution. Also, Zoom's
version is cloud-processed (Cloud Recordings, summary emailed), so it is unusable under the
zero-trust premise regardless. Local ASR remains the right call.

## 7.5 — Optional dual-track audio retention

> **The system's job is not to lose anything. What the recording is used for is the file
> owner's decision.**

Retaining audio serves two purposes, neither of them live: **post-processing** and
**corroboration**. The second is the stronger one — a transcript is an inferred artifact,
whereas the audio is the record. In an interpellation or an earnings call, "I did not say
that" is a dispute the transcript alone cannot settle.

Design constraints, in order of how easily each one silently ruins the feature:

- **Write from the raw stream, upstream of VAD.** `_processing_thread` discards everything VAD
  classifies as non-speech, so archiving downstream would lose precisely the **VAD
  misjudgements** — exactly the material worth going back to verify. "Do not lose anything"
  only holds if the tap point is the continuous callback stream.
- **Keep the two tracks in separate files. Never mix them.** Mixing destroys the role
  attribution that this architecture gets for free, and which comparable products only obtain
  because the OS forces the same split on them.
- **Do not block the audio callback.** Disk writes go through a queue and a dedicated writer
  thread, the same pattern already used for `inference_queue`. This is a load-bearing
  invariant, not a preference.
- **Lossless only.** Lossy compression undermines evidentiary value. Python's stdlib `wave`
  module writes WAV with **no new dependency**; FLAC is a later size optimization if needed.
- **Name files to pair with the transcript** — `history/Meeting_<session_id>_mic.wav` and
  `_system.wav` alongside the existing `Meeting_<session_id>.md`, so the 7.4 cleanup script can
  find them without guessing.
- **Record the precise session start time** so a transcript line's wall-clock timestamp can be
  converted to an offset into the WAV. Without it, "jump to this moment in the audio" — the
  whole point of corroboration — does not work.

Size, at 16 kHz mono int16 lossless:

| | per hour, per track | both tracks | 3-hour hearing |
|---|---|---|---|
| WAV @ 16 kHz | 115 MB | 230 MB | ~690 MB |
| WAV @ 48 kHz (tap's native rate) | 346 MB | 691 MB | ~2.1 GB |

Open decision: archive at 16 kHz (what the pipeline actually processed, so the record matches
the transcript) or at the tap's native 48 kHz (higher fidelity for disputes, 3x the disk).
16 kHz is the suggested default.

A **UI toggle, defaulting to off** — per 7.6c this is a per-meeting decision, not a file
setting. Off by default on disk-space grounds, and because recording carries consent
expectations the operator should choose deliberately. `history/` is already gitignored, so audio
stays out of version control.

## 7.6 — Move configuration into the UI; gate capture behind an explicit Start

The local web page is the control surface, and the app does not currently treat it as one.
Configuration is hand-maintained in `.env`, and capture begins on page load rather than on
user intent.

### 7.6a — Capture must not start before authentication 🔴 SECURITY ORDERING

`app.py` executes in this order:

1. `get_global_state()` — loads `.env`, constructs `LocalAdvisor` (loads the embedding model)
2. `g_state.start_recording()` — constructs both `Transcriber`s, preloads Whisper into the NPU,
   **opens the microphone and system-audio streams**, and calls `buffer.start_session()`, which
   writes a transcript file into `history/`
3. *…then* the PIN gate
4. *…then* role selection

**The microphone goes live, and a transcript file starts being written, before anyone
authenticates.** Opening the URL is sufficient — no PIN, no role selected. For a product whose
premise is protecting confidential meetings, this is an ordering defect, not merely eager
startup. Fixing it is a small, independent change and should land early, ahead of the rest of
Phase 7.

### 7.6b — Warm the model eagerly, open the streams lazily

Purely lazy loading is the wrong correction: `turbo` is 1.61 GB and there are two
`Transcriber` instances, so deferring everything to the Start button puts that wait at the
worst possible moment — the meeting is about to begin.

Split the two concerns, which are currently fused inside `Transcriber.__init__`:

- **NPU/model warm-up** — harmless, touches no audio device. May run eagerly in a background
  thread on page load.
- **Opening the audio streams** — must be gated behind authentication *and* an explicit Start.

That yields no hot microphone and no wait at Start.

### 7.6c — `.env` stays, but the app writes it; the user never edits it

The problem was never the file, it is **hand-maintaining** it. `.env` keeps exactly one job:
recording the **user-chosen model cache directory**. That path genuinely must be configurable
rather than derived from the repo location — the weights are multi-gigabyte, and an internal
SSD may not be where the operator wants them. It also genuinely must be an environment
variable, because `huggingface_hub` reads it at import time.

Everything else leaves the file:

| Setting | Real lifecycle | Belongs in |
|---|---|---|
| `HF_HOME` (model cache dir) | chosen once per machine | **`.env`, written by the app** from a first-run UI prompt |
| `ENABLE_LOCAL_RAG` | per session | UI toggle, default on |
| `AUDIO_BACKEND` (planned) | capability, not preference | auto-detect: use the tap when available, else BlackHole |
| `ARCHIVE_AUDIO` (planned) | per **meeting** | UI toggle, default off |
| `MULTILINGUAL_MODE` | **split across two lifecycles** — see below | must be separated |

`MULTILINGUAL_MODE` is a genuine design smell. The embedding model is chosen in
`build_index.py` and baked into the pickle as `model_name`, which `local_advisor.py` then
loads — so at runtime the flag is a **no-op for RAG**. Only the ASR model choice is a runtime
decision. One flag spanning build time and run time should become two things: an argument to
`build_index.py`, and a language/model selector in the UI.

`PIP_CACHE_DIR` matters only during `pip install`, which `setup_mac.sh` already exports for
itself, so it does not belong in `.env` either.

### 7.6d — First-run flow: the web page is the setup wizard

Nothing needs to be downloaded before the first cold start. `setup_mac.sh` keeps its current
scope — Homebrew dependencies, `.venv`, `pip install` — and **only the model download moves
behind the UI**:

```
bash setup_mac.sh          # brew + .venv + pip install (unchanged)
streamlit run src/app.py
  └─ no .env, or no cache path in it → first-run prompt: choose the model cache directory
     → app writes .env
     → downloads models, progress shown in the UI
     → warms the NPU
     → Start button unlocks
```

- **Reset is deleting `.env`** — by hand or via a UI button. That returns the app to the
  first-run prompt. There is no other configuration state to clear.
- **The user never opens `.env` in an editor.** If they need to change the cache directory, they
  reset and choose again.

#### The enabling prerequisite: defer one import

**This design does not work unless the ML libraries are imported after the cache path is
known.** `huggingface_hub.constants.HF_HOME` is fixed at import time — measured, see Known
Issues — so once `huggingface_hub` is loaded, writing `.env` and setting `os.environ` afterwards
**cannot take effect in that process**.

That is the whole reason. It does *not* additionally follow that a bare clone must be able to
boot: the chosen setup boundary keeps `pip install` inside `setup_mac.sh`, so by the time
`streamlit run` happens every package is present.

#### The change is smaller than it looks: one new file plus `app.py`

The entire heavy import chain hangs off a **single line**. Verified by tracing the graph:

- `app.py:20` — `from global_state import get_global_state`, the **only** import of `global_state`
- `global_state.py:6-7` — the **only** imports of `local_advisor` and `transcriber`, which in turn
  are the only places `sentence_transformers`, `mlx_whisper`, `sounddevice`, and `webrtcvad`
  appear
- `app.py:27` — the **only** call to `start_recording()`
- `import streamlit` pulls **none** of those heavy modules (measured)

So there is no need to rewrite import statements inside `transcriber.py` or `local_advisor.py`.
Those modules may keep their module-scope imports, because they are only loaded *after* the cache
path is set. Deferring `app.py:20` alone is sufficient.

| File | Change |
|---|---|
| `src/bootstrap.py` (new) | Zero project imports — stdlib plus `dotenv` only. Reads and writes `.env`, resolves the cache directory, sets `os.environ["HF_HOME"]` before anything heavy loads, checks whether weights are present, owns the readiness state machine. |
| `app.py` | Move `from global_state import ...` out of module scope into a function called only once configuration exists; drop the `app.py:27` auto-start; add the first-run wizard and Start gating. |
| `transcriber.py` | **Untouched.** |
| `local_advisor.py` | **Untouched.** |
| `global_state.py` | **Untouched**, until `ENABLE_LOCAL_RAG` moves to a UI toggle — a separate, smaller step. |

Concentrating the work this way is also what makes 7.6 safe to do *after* 7.1: the model-string
change in `transcriber.py` and the bootstrap work do not overlap.

#### Readiness state machine

`GlobalState` needs an explicit lifecycle so the UI can gate on it:

```
no-config → downloading → warming → ready
```

The Start button is `disabled` until `ready`. This subsumes 7.6a: capture cannot begin early
because the control that begins it does not become pressable until warm-up completes.

#### Surfacing progress

`logging` already writes to `logs/aegis_engine_<ts>.log` (configured in `global_state.py`), so
the UI can tail that file — half the plumbing exists.

**Caveat**: `mlx_whisper` / `huggingface_hub` report download progress through **tqdm on
stdout, not through `logging`**, so tailing the log will not show it — and the download is
precisely the phase the user most needs feedback on. This needs either `huggingface_hub`'s
progress callbacks or explicit stdout capture. Not free.

### 7.6e — No settings persistence beyond the cache path

Considered and rejected for everything else. Each remaining setting has a sensible default plus
a UI override — exactly the model Meet and Zoom web use for device selection: show the system
default, let the user change it, persist nothing.

`find_device_index(fallback_to_default=True)` already provides that default; only the dropdown
to override it is missing (7.3). So there is no `.aegis_settings.json`, and storing no device
reference also removes the question of whether to store a device *name* (disappears when AirPods
disconnect) or *index* (changes between reboots). Enumerate live, every time.

## 🐛 Known Issues

- **`HF_HOME` in `.env` has never taken effect; model weights land outside the project.**
  Two facts combine. First, import order: `app.py` imports `global_state`, which imports
  `local_advisor` and `transcriber` at module scope, pulling in `sentence_transformers` and
  `mlx_whisper` — while `load_dotenv()` runs later, inside `_init_once()`. Second, measured
  directly: `huggingface_hub.constants.HF_HOME` is computed at import time, and setting the
  environment variable afterwards is ignored (verified — the constant kept
  `~/.cache/huggingface` after a late `os.environ` assignment).
  So weights download to `~/.cache/huggingface`, contradicting `setup_mac.sh`'s closing claim
  that "GBs of ML weights are safely cached within the project folder", and leaving the
  gitignored `.hf_cache/` unused. `setup_mac.sh` does export `HF_HOME`, but only inside its own
  shell — it is gone by the time `streamlit run` happens in a new shell.
  Fix per 7.6d: defer the ML library imports so the path can be set before the first one runs.
  The path itself stays user-chosen in `.env` rather than derived, since multi-gigabyte weights
  may not belong on the internal drive. Confirm afterwards by checking where weights actually
  land on a fresh run.
- **Speaker-audio echo causes double transcription and false RAG triggers.** If the speaker
  uses loudspeakers instead of headphones, the microphone also picks up the far end, so the
  same utterance is transcribed twice — once as `Speaker (You)` and once as `Participant`.
  Because `_local_rag_worker_loop` only fires on `role == "Participant"`, the speaker's own
  echoed voice can trigger defensive cues. This affects BlackHole today and will affect the
  tap equally; it is not introduced by either. Practical mitigation: **require headphones or
  an earpiece** — normal in hearings and earnings calls anyway. A software fix means AEC,
  which is far more expensive.
- **`MULTILINGUAL_MODE` is misleadingly named** — it only selects the RAG embedding model,
  never the ASR model. Being fixed in 7.1.
- `global_state.py` looks for `["MacBook Air Microphone", "Built-in Microphone"]`. On a
  MacBook Pro neither keyword matches, so mic selection silently relies on
  `fallback_to_default`. The result is usually correct, but the keyword list is not doing
  its job. Superseded by 7.3.
- Capturing the far end currently requires the BlackHole driver *plus* a manually configured
  Multi-Output Device, otherwise the speaker cannot hear the meeting while it is captured.
  Superseded by 7.2.
