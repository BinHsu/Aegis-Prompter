# Project State

Tracks requirements, verified constraints, the plan, and open issues. For how to work in the
repo, see [AGENTS.md](AGENTS.md). For release history, see [CHANGELOG.md](CHANGELOG.md).

**Current release: `v0.0.1`** — BlackHole audio backend.

This document is deliberately layered, because the three layers decay at different rates:

| Layer | What it holds | Changes when |
|---|---|---|
| **Design stance** | Durable product principles | The product's purpose changes |
| **Requirements** (`R*`) | What is wanted, stated without implementation | The operator's needs change |
| **Verified constraints** (`V*`) | Measured facts that bound the solution space | Reality changes, or a measurement is redone |
| **Plan** (`7.*`) | How to get there, citing `R*` and `V*` | Freely — this is the volatile layer |

Rewrite the plan as often as needed. Do not quietly rewrite requirements to match a plan, and
do not restate a constraint without re-measuring it.

**Cite `R*` and `V*`, not `7.*`.** Plan numbers follow execution order and are renumbered
whenever the order changes — they are not stable identifiers. Requirement and constraint IDs
are. (Commits before `a066498` reference an older plan numbering; read them against the
requirements they describe, not the section numbers.)

---

## 🧭 Design stance

> **Whatever your ears can hear and whatever your mouth says, we ingest.**
>
> **Our job is not to lose it. What it gets used for is the file owner's decision.**

The first sentence makes capture **source-agnostic**. It does not matter whether the meeting
runs in Zoom's native app, Meet in a browser tab, Teams, or anything else.

The second draws the **product boundary**: the system is responsible for completeness of
capture, not for policy about the captured material. Retention, cleanup, redaction, and
disclosure are the operator's calls — which is why post-processing and audio retention are
opt-in tools rather than pipeline behaviour.

---

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

# 📋 Phase 7 — Requirements

Stated without implementation. Each item is something the product must do, or must not do.

## Capture

- **R1 — Source-agnostic.** Capture must work regardless of where the meeting runs: Zoom app,
  Zoom web, Meet, Teams, or anything else. The system must not need to know or be told.
- **R2 — Two tracks, never mixed.** What the operator *hears* (system output) and what the
  operator *says* (microphone) are separate tracks and stay separate all the way through.
- **R3 — Do not lose anything.** Completeness of capture is the system's responsibility.
- **R4 — Do not set policy.** What happens to captured material — retention, cleanup,
  disclosure — is the file owner's decision, not the system's.
- **R5 — No per-application filtering.** Do not try to capture "only the meeting app".
- **R6 — Remove the BlackHole prerequisite** from the normal install path, without dropping
  support for machines that still need it.
- **R7 — The newest supported capture method becomes the default** once proven.

## Transcription and language

- **R8 — One meeting may contain both English and Chinese.** Both must be transcribed.
- **R9 — Live subtitle quality is explicitly not a goal.** The speaker on stage needs the
  gist. Cosmetic correctness is deferred to post-processing.
- **R10 — Traditional Chinese** is the target script for the Taiwan context — subject to R9
  for the live path.
- **R11 — The ASR model must be a deliberate choice**, re-examined rather than inherited.

## Speaker attribution

- **R12 — Distinguish individual remote speakers** (speaker 1, speaker 2, …), not merely
  "me vs. everyone else".
- **R13 — Attribution may be resolved after the meeting.** It does not have to be live.

## Post-processing and retention

- **R14 — A post-hoc cleanup path exists**, run by the operator against an archived
  transcript, that re-flows the text using full context and corrects speaker labels.
- **R15 — Post-processing is not a product feature.** It is a script the operator chooses to
  run. No runtime code path in the application may depend on it, and the application's offline
  guarantee must remain intact.
- **R16 — Dual-track audio may optionally be retained**, for post-processing and for
  **corroboration** — settling disputes about what was actually said.

## Configuration and startup

- **R17 — The local web page is the control surface.** Configuration belongs there.
- **R18 — The user must never hand-edit `.env`.**
- **R19 — The model cache directory is user-specified**, not fixed by the project layout —
  the weights are large and may not belong on the internal drive.
- **R20 — If configuration is absent, the web page asks for it.** No `.env`, or no cache path
  in it, must lead to a prompt rather than an error.
- **R21 — Nothing needs to be downloaded before the first cold start.** Launching must not
  presuppose that models were already fetched.
- **R22 — Reset means deleting `.env`**, by hand or by button. There must be no other
  configuration state to clear.
- **R23 — Setup progress must be visible**, including console output, while it happens.
- **R24 — Start must be unavailable until warm-up is confirmed complete.**
- **R25 — Capture must not begin before authentication** and an explicit operator action.

## Advisor backends

- **R28 — RAG and LLM are two independently configurable slots.** The operator may fill
  neither, either, or both. Whatever is filled gets sent to; the app is a transport, not a
  policy-maker about which backend is appropriate.
- **R29 — Every response is labelled with the vendor that produced it.**
- **R30 — Generated content is visibly marked as unverified**, distinctly from retrieved
  pre-written content. Retrieved text is safe to read aloud; generated text is not.
- **R31 — The operator supplies a host and a credential; the app sends and receives.** No
  per-vendor configuration beyond that.

## Device selection and pre-flight

- **R26 — Audio input is selectable from the web page**, in the manner of Zoom or Meet web:
  a sensible default, freely overridable.
- **R27 — Every per-meeting decision is made on one pre-Start panel.** The screen shown before
  capture begins is the single place the operator chooses microphone, whether to retain audio,
  and whether the RAG advisor is active — reviewed together, then committed by pressing Start.
  No per-meeting choice lives anywhere else.

---

# 🔬 Phase 7 — Verified constraints

Measured or read from source, not inferred. Each is dated to this investigation (2026-08-07,
macOS 26.6). Re-measure rather than assume if any becomes load-bearing again.

## The current ASR model cannot do Chinese

- **V1** — `transcriber.py` defaults to `mlx-community/distil-whisper-large-v3`, and
  Distil-Whisper is **English-only** by design; its speedup comes from being trained on English
  audio only. Chinese is *unsupported*, not merely inaccurate. Blocks **R8**.
- **V2** — `MULTILINGUAL_MODE` appears **only** in `build_index.py`, where it selects the RAG
  embedding model. It has never reached the ASR layer, so setting it `true` yields multilingual
  retrieval over an English-only transcript.
- **V3** — `local_advisor.py` loads the embedding model recorded *inside* the index pickle
  (`bundle["model_name"]`), so the flag is a **runtime no-op for RAG** as well. Its only real
  effect is at index build time.
- **V4** — `mlx-community/whisper-large-v3-turbo` is multilingual (99+ languages), 1.61 GB
  quantized in MLX form, roughly 5x faster than `large-v3`. Candidate for **R8**/**R11**.
- **V5** — Whisper has a single `zh` token and was trained on mixed Simplified/Traditional
  text, so Traditional output is not guaranteed. Relevant to **R10**.

## Core Audio process tap is viable

Verified with Command Line Tools `clang` only — **no Xcode required**.

- **V6** — `AudioHardwareCreateProcessTap` is `API_AVAILABLE(macos(14.2))` — **14.2, not
  14.4**, read directly from `AudioHardwareTapping.h`.
- **V7** — A global mono mixdown tap works: `err=0`, format **48 kHz / mono / float32
  packed**, and **190,976 frames captured over 4 seconds** with real signal (`peak=0.297`).
  This is the shape **R1**/**R5** call for.
- **V8** — `CATapDescription.bundleIDs` and `.processRestoreEnabled` require **macOS 26.0**.
  They are the *only* members that do — so declining per-app capture (**R5**) lowers the OS
  floor from 26.0 to 14.2.
- **V9** — A tap exposed through a **non-private aggregate device is visible cross-process**
  as an ordinary input device; a separate process enumerated it as `in[1 ch] Aegis System
  Audio`, and it disappeared cleanly when the helper exited. So `sounddevice`/PortAudio see it
  as just another microphone.
- **V10** — `muteBehavior = CATapUnmuted` keeps the audio audible to the operator, removing
  BlackHole's Multi-Output Device requirement (**R6**).
- **V11** — Tap capture triggers a **`kTCCServiceAudioCapture`** check, attributed to the
  **responsible process — the terminal app, not the tap binary**. Not a new class of risk: the
  same log shows the existing microphone path attributing `kTCCServiceMicrophone` to that same
  responsible process.
- **V12 — Unverified, and the first thing implementation will hit.** The tap is fixed at
  48 kHz while `transcriber.py` opens its stream at 16 kHz; whether PortAudio resamples was not
  tested. `webrtcvad` accepts 48000, so the fallback is to run VAD at 48 k and resample only
  before Whisper.

## Browser-side audio capture is impossible here

- **V13** — `navigator.mediaDevices` is `[SecureContext]`. Outside a secure context it is
  **`undefined`** and `getUserMedia()` throws `TypeError`. Secure contexts are HTTPS,
  `file://`, and **localhost** — `http://192.168.x.x:8501` is none of them, so the remote iPad
  cannot even enumerate devices.
- **V14** — No browser reliably supplies system output audio on macOS: Safari does not support
  `getDisplayMedia` audio at all, Firefox ignores it, and Chrome supports tab audio with system
  audio only from **Chrome 141+ on macOS 14.2+** — itself built on the same process-tap API.
  Together with V13 this settles **R26** as a server-side concern.

## Comparable products hold no extra card

- **V15** — Zoom's *in-meeting* captions attribute speech by **active speaker detection** over
  per-participant connections: transport metadata, not inference. Not transferable — this
  project captures the post-mix output, where that identity was already destroyed. It also
  fails when several people share one connection, which is exactly the hearing-room case.
- **V16** — Zoom's *listen-to-the-meeting* mode (AI Companion / My Notes, including over Teams
  and Meet) lands on the same two-track architecture, because macOS offers no single API
  yielding microphone and system output together. Zoom's own wording — AI Companion "will do
  its best to differentiate between **you and other parties**" — indicates inference, and the
  you-vs-others boundary is the mic-vs-system-output boundary. Whether they send the two
  captures to ASR separately or pre-mixed is **undocumented**; it does not matter, since this
  project already keeps them separate (**R2**).
- **V17** — Zoom's live transcription is **cloud-processed**, so it is unusable under this
  project's premise regardless.

## The startup path has two defects

- **V18 — Capture begins before authentication.** `app.py` runs `get_global_state()` then
  `g_state.start_recording()` at module scope, which opens both audio streams and calls
  `buffer.start_session()` (writing a file into `history/`) — *above* the PIN gate and *above*
  role selection. Opening the URL is sufficient. Violates **R25**.
- **V19 — `HF_HOME` from `.env` has never taken effect.** Two measurements combine:
  `huggingface_hub.constants.HF_HOME` is fixed at import time (a late `os.environ` assignment
  left it at `~/.cache/huggingface`), and `load_dotenv()` runs inside `_init_once()` — *after*
  `global_state.py:6-7` has already imported `sentence_transformers` and `mlx_whisper` at
  module scope. So weights land outside the project, contradicting `setup_mac.sh`'s closing
  claim that they are cached in the project folder and leaving `.hf_cache/` unused.
  `setup_mac.sh` does export `HF_HOME`, but only inside its own shell.

## The advisor seam already exists, and so does its gate

- **V22 — The cosine threshold *is* the intent judgement.** `local_advisor.py` computes a
  similarity score and returns a hint only when `best_score >= THRESHOLD` (0.65), plus a
  `< 10` character filter and a repeat-suppression check on `last_matched_idx`. So the current
  design already sends every Participant utterance to RAG unconditionally and lets the score
  decide. **No separate intent model exists or is needed** for the RAG path.
- **V23 — A generative model has no equivalent threshold.** RAG returns `None` below 0.65; an
  LLM produces output for any input, because that is what generative models do. Any gate on
  the LLM path has to be built.
- **V24 — There is one advice slot, so two backends overwrite each other.**
  `dialogue_buffer.set_advice()` assigns a single `self.advice` string and `app.py` renders one
  value. Local RAG returns in milliseconds, a remote LLM in seconds — so an LLM reply would
  reliably replace an already-displayed RAG hint a beat later. Worse than showing nothing: the
  speaker reads a safe pre-written answer, and it is swapped for generated text mid-glance.
- **V25 — A pending state already exists.** `set_advice(advice, is_thinking=True)` updates the
  display but deliberately skips the session log. Built for the Gemini-era slow advisor;
  exactly the state an in-flight LLM call needs.
- **V26 — The conversation buffer is bounded by construction.**
  `DialogueBuffer(max_history=15)` evicts with `pop(0)` past 15 entries. Fifteen utterances of
  meeting speech is roughly 1–3K tokens. **Context-window exhaustion is therefore not a
  realistic failure mode** — the cap is a product decision, not an API-error-handling problem.
- **V27 — The worker loop is synchronous and only ever reads the newest entry.**
  `_local_rag_worker_loop` runs `while` with `time.sleep(0.3)` and calls `analyze_dialogue`
  inline, reading only `full_dialogue[-1]`. A slow remote call stalls the loop, and utterances
  arriving during the stall are skipped rather than queued — the loop coalesces to "the latest
  utterance at the moment the previous call returned." Useful behaviour, but currently
  accidental rather than designed.

## Advisor backend interfaces

- **V28 — OpenAI-compatible is the de facto standard for the LLM slot**:
  `POST {base_url}/v1/chat/completions`, `Authorization: Bearer <key>`. Implemented by Ollama
  (`:11434/v1`), LM Studio (`:1234/v1`), vLLM (`:8000/v1`), llama.cpp, LocalAI, and every cloud
  provider. Local and remote differ only by URL.
- **V29 — Qdrant's local mode exposes the same API surface as remote.**
  `QdrantClient(path=...)` runs in-process on SQLite with no server;
  `QdrantClient(url=..., api_key=...)` is the remote form. Documented for datasets up to
  ~20,000 points, which is far above a hand-written knowledge base. **Adopting it is not a
  performance win** — numpy dot product over a few hundred 384-dim vectors is already
  microseconds. The reason is that one API covers local and remote, which is what makes R31
  implementable.
- **V30 — Qdrant Cloud Inference covers the embedding half, server-side.** Passing a `Document`
  with `cloud_inference=True` has Qdrant embed the text itself. So embedding location follows
  from which Qdrant is targeted — local mode uses local `sentence-transformers`, Cloud uses
  Cloud Inference — and no third configuration knob is needed. Qdrant accepts
  `Authorization: Bearer` as well as `api-key`, so one credential shape serves both slots.
- **V31 — Anthropic's API fits neither slot.** It is `POST /v1/messages` with `x-api-key` +
  `anthropic-version` headers, not OpenAI-shaped, and it has **no embeddings endpoint at all**.
  Using Claude in the LLM slot requires either an OpenAI-compatible gateway or a dedicated
  adapter.
- **V32 — Context-overflow errors are not reliable across the target runtimes.** OpenAI proper
  returns HTTP 400 `context_length_exceeded`. **Ollama silently truncates to `num_ctx`
  (default 4096) and its OpenAI-compatible wrapper does not even forward `num_ctx`** — no error
  is raised. vLLM currently returns a 400 where the spec calls for auto-truncation. So a local
  backend can answer confidently from a silently truncated transcript, invisibly. The defence is
  owning the bound locally (**V26**), not catching an error.

## The import graph is narrow

- **V20** — The entire heavy import chain hangs off **one line**. `app.py:20` is the only
  import of `global_state`; `global_state.py:6-7` are the only imports of `transcriber` and
  `local_advisor`, which are in turn the only places `mlx_whisper`, `sentence_transformers`,
  `sounddevice`, and `webrtcvad` appear; `app.py:27` is the only `start_recording()` call. And
  `import streamlit` pulls **none** of those heavy modules (measured). So deferring one import
  is sufficient — `transcriber.py` and `local_advisor.py` need no edits.
- **V21** — `huggingface_hub` download progress is reported through **tqdm on stdout, not
  through `logging`**. Tailing `logs/aegis_engine_*.log` will therefore miss the download phase,
  which is exactly the phase **R23** most needs to show.

---

# ✅ Decided and closed

Recorded so they are not relitigated. Reopening any of these means revisiting the stance or
requirement it follows from.

| Rejected | Why | Follows from |
|---|---|---|
| Per-app audio capture via `bundleIDs` | Cannot isolate a meeting running in a browser tab, and a bundle-ID allowlist is unmaintainable. Also costs the 14.2 → 26.0 OS floor. | R1, R5, V8 |
| Browser-side capture (`getUserMedia`, as Zoom/Meet web do) | Impossible, not merely awkward — the remote device cannot reach the API, and no browser reliably yields system audio on macOS. | V13, V14 |
| ASR-side speaker diarization (pyannote / sherpa-onnx / embeddings) | Live transcription never needs speaker identity; the RAG worker triggers on `role == "Participant"` only. Deleting this removes the roadmap's highest-risk item rather than deferring it. | R12, R13 |
| OpenCC in the live path | Simplified/Traditional ambiguities need surrounding context, which only the post-processing pass has. | R9, R10, V5 |
| Settings persistence (`.aegis_settings.json`) | Meet and Zoom web persist nothing: default plus override is sufficient. Also dissolves the device *name* vs *index* question. | R26 |
| Archiving audio *in order to* diarize | The cleanup pass works from text. Audio retention stands on corroboration instead. | R14, R16 |
| Deleting `.env` outright | The cache directory must stay user-choosable; large weights may not belong on the internal drive. `.env` survives as a machine-written file. | R18, R19 |
| A separate local intent model to gate the LLM | The RAG score is already an intent judgement and costs microseconds; a second model would contend for the NPU that `201eeea` exists to unblock. | V22, V23 |
| RAG backends other than Qdrant | Retrieval-as-a-service has no standard interface — Qdrant, Weaviate, Pinecone and Chroma each have their own API. One vendor beats an abstraction over four. | R28, R31 |
| Relying on a context-overflow error code | Ollama truncates silently and does not forward `num_ctx`; vLLM errors where the spec says truncate. Own the bound locally instead. | V26, V32 |

---

# 🗺️ Phase 7 — Plan

Ordered so each step is independently shippable and the riskiest work lands last. Every item
cites the requirements it satisfies.

## 7.1 — Multilingual ASR — 🔴 do first

Satisfies **R8, R10, R11**. Addresses **V1, V2, V3**.

1. Default to `mlx-community/whisper-large-v3-turbo` (**V4**).
2. Make `MULTILINGUAL_MODE` govern both layers, or split it — see 7.4.
3. Bias decoding toward Traditional Chinese with an `initial_prompt` (**V5**). No OpenCC in the
   live path — see *Decided and closed*.
4. Re-measure latency: `turbo` is slower than `distil`, and two tracks share `NPU_LOCK`. Confirm
   `audio_queue` does not resume dropping frames — that regression was only fixed in `201eeea`.

Already favourable: no architectural change is needed for code-switching, because each VAD
segment is a separate `transcribe()` call with no `language` argument, so language is
auto-detected per chunk. Intra-*sentence* code-switching stays weak — a Whisper limitation.

Open risk: `turbo` is reportedly weaker than `large-v3` on some languages. Mandarin is generally
fine, but measure on real meeting audio rather than inferring from specs.

## 7.2 — Core Audio process tap, then make it the default

Satisfies **R1, R5, R6, R7**. Built on **V6–V11**; **V12** is the first unknown to hit.

1. Add `src/native/aegis_tap.m` — a global mono mixdown tap, compiled by `setup_mac.sh`.
2. `global_state.py` launches it as a subprocess on start, SIGTERMs it on stop.
3. **Auto-detect rather than configure**: use the tap when the OS supports it and the device
   appears, otherwise BlackHole. Surface which is active in the UI — this is a capability, not a
   preference.
4. Prove it in real meetings, **then** make the tap the default (**R7**).
5. Keep the BlackHole fallback permanently for macOS older than 14.2 (**R6**).

Largest ongoing cost: the aggregate device binds a specific output device as its main
sub-device, so it goes stale when the operator switches output. Needs a
`kAudioHardwarePropertyDefaultOutputDevice` listener to rebuild. BlackHole does not have this
problem — the only respect in which it is superior.

## 7.3 — Microphone selection in the web UI

Satisfies **R26**. Settled by **V13, V14**: this remote-controls the *host Mac's* devices; it is
not a browser device picker. That is more useful than the Zoom/Meet model here — staff off-stage
can retune the speaker's capture without touching the Mac.

Scope shrinks because of **R1**: if system audio is "everything", there is no source to choose.
So this contributes a **microphone dropdown** and a read-only **active backend indicator** — not
a screen of its own. Both live on the pre-flight panel defined in 7.4 (**R27**). Two dropdowns
became one.

The `st.progress(rms)` level meters already in `app.py` are exactly the meter Zoom shows beside
its device picker, so the familiar UX needs no new visual work.

Trap: `Transcriber.__init__` preloads the model into the NPU. Switching devices must **not**
naively reconstruct a `Transcriber` — separate "change device" from "reload model".

Bonus: a dropdown makes the hardcoded microphone-keyword bug (Known Issues) irrelevant.

## 7.4 — Configuration and startup: one new file plus `app.py`

Satisfies **R17–R25**. Addresses **V18, V19**; enabled by **V20**; constrained by **V21**.

### First-run flow

`setup_mac.sh` keeps its current scope — Homebrew dependencies, `.venv`, `pip install`. Only the
**model download** moves behind the UI (**R21**):

```
bash setup_mac.sh          # brew + .venv + pip install (unchanged)
streamlit run src/app.py
  └─ no .env, or no cache path in it → prompt for the model cache directory   (R19, R20)
     → app writes .env                                                        (R18)
     → downloads models, progress shown in the UI                             (R23)
     → warms the NPU
     → Start unlocks                                                          (R24)
```

Reset is deleting `.env` (**R22**). The user never opens it in an editor (**R18**); to change the
cache directory, reset and choose again.

### Where the work goes

**V20** makes this far smaller than it looks — deferring one import is sufficient.

| File | Change |
|---|---|
| `src/bootstrap.py` (new) | Zero project imports — stdlib plus `dotenv` only. Reads and writes `.env`, resolves the cache directory, sets `os.environ["HF_HOME"]` *before* anything heavy loads, checks whether weights are present, owns the readiness state machine. |
| `app.py` | Move `from global_state import ...` out of module scope into a function called only once configuration exists; drop the `app.py:27` auto-start (**V18**); add the first-run prompt and Start gating. |
| `transcriber.py` | **Untouched.** |
| `local_advisor.py` | **Untouched.** |
| `global_state.py` | **Untouched**, until `ENABLE_LOCAL_RAG` becomes a UI toggle — a separate, smaller step. |

Implementation ordering note: checking whether weights already exist is most reliably done via
`huggingface_hub`'s cache API, but importing it fixes `HF_HOME` (**V19**). So `bootstrap.py` must
set the path *first*, then import to inspect. Internal to that one file, but easy to get backwards.

### Readiness state machine

```
no-config → downloading → warming → ready
```

Start is `disabled` until `ready` (**R24**), which also satisfies **R25**: capture cannot begin
early because the control that begins it is not pressable.

### The pre-flight panel

Once `ready`, the operator sees one screen holding **every per-meeting decision** (**R27**), so
the three plan items below do not each grow their own UI:

| Control | Kind | Default | From |
|---|---|---|---|
| Microphone | dropdown | system default | 7.3 / **R26** |
| Retain dual-track audio | toggle | off | 7.7 / **R16** |
| RAG advisor active | toggle | on | 7.4 (`ENABLE_LOCAL_RAG`) |
| Active capture backend | **read-only** indicator | auto-detected | 7.2 / **R7** |
| Input level meters | read-only | — | already built (`st.progress(rms)`) |
| **Start** | button | disabled until `ready` | **R24, R25** |

Pressing Start **commits** these choices and opens the streams. They are fixed for the session;
changing one means stopping and starting again. That keeps stream setup and the audio writer
configured once, rather than being mutable mid-capture.

Nothing here is persisted (see *Decided and closed*) — the panel is rebuilt from live enumeration
and defaults on every launch.

### Warm eagerly, open streams lazily

Fully lazy loading is the wrong correction — `turbo` is 1.61 GB across two `Transcriber`
instances, so deferring everything to Start puts that wait at the worst moment. Split the two
concerns currently fused in `Transcriber.__init__`:

- **Model warm-up** touches no audio device; it may run automatically once configuration exists.
- **Opening the audio streams** waits for authentication *and* an explicit Start.

### Configuration lifecycle

`.env` keeps exactly one job: the user-chosen model cache directory (**R19**), which genuinely
must be an environment variable because `huggingface_hub` reads it at import (**V19**).

| Setting | Real lifecycle | Belongs in |
|---|---|---|
| `HF_HOME` | once per machine | `.env`, written by the app |
| `ENABLE_LOCAL_RAG` | per session | UI toggle, default on |
| audio backend | capability, not preference | auto-detected (7.2) |
| `ARCHIVE_AUDIO` | per **meeting** | UI toggle, default off (7.7) |
| `MULTILINGUAL_MODE` | spans build time and run time (**V2, V3**) | split: a `build_index.py` argument, plus a UI selector for ASR |
| `PIP_CACHE_DIR` | during `pip install` only | `setup_mac.sh`, which already exports it |

## 7.5 — Pluggable advisor backends (RAG via Qdrant, LLM via OpenAI-compatible)

Satisfies **R28–R31**. Built on **V22–V32**.

The existing seam is already the right shape: `global_state.py` constructs an advisor and calls
`analyze_dialogue(text) -> str | None`. Formalize that into a `Protocol` plus a factory; the
worker loop does not change.

| Slot filled | Behaviour |
|---|---|
| Neither | `advisor = None` — already works today via `enable_rag` |
| RAG only | Qdrant query; the score gates as it does now (**V22**) |
| LLM only | Send unconditionally — see below |
| Both | Three-band routing on the RAG score |

**Three-band routing when both are filled.** The cosine score is a free, local, millisecond
relevance signal, so it gates the LLM too:

| Score | Meaning | Action |
|---|---|---|
| ≥ 0.65 | A prepared answer exists | Serve the RAG hint — fast, no hallucination risk |
| 0.45 – 0.65 | Related subject, no exact match | **The LLM's value band** — send, with the near-miss chunks as grounding context |
| < 0.45 | Off-topic (music, chatter, notification sounds) | Send nothing |

This is where an unanticipated question in a known domain gets answered, and the near-miss
chunks make it genuine retrieval-augmented generation rather than bare generation.

**LLM-only: send unconditionally, and let the prompt be the threshold.** With no RAG score there
is no gate, and the decision is to send every Participant utterance with the accumulated
transcript so the model has maximum context awareness. Two things make that safe rather than
reckless:

- **The bound already exists** (**V26**) — `max_history=15` caps the transcript by construction,
  so context exhaustion is not a realistic failure mode. **Do not raise `max_history` for the
  LLM's benefit without measuring**: past ~4096 tokens an Ollama backend truncates silently
  (**V32**) and the model will answer confidently from a transcript it never fully saw.
- **The system prompt carries the threshold the model lacks** (**V23**). It must explicitly
  permit returning nothing — without that instruction the prompter floods, because a generative
  model produces output for every input.

Required changes:

1. **`analyze_dialogue` must return the score, not just the text.** Below-threshold and
   repeat-suppressed cases currently discard it, and three-band routing needs it.
2. **Resolve the single-slot collision** (**V24**) — separate fields per backend, or an explicit
   merge policy. An LLM reply must not silently replace a displayed RAG hint. `is_thinking`
   (**V25**) already models the in-flight state.
3. **Take the remote call off the poll thread** (**V27**) with a timeout and single-flight
   semantics. The loop's coalescing behaviour is desirable — make it deliberate.
4. **Label by vendor, and mark generated content unverified** (**R29, R30**). `🛡️ [Aegis
   Triggered]` and `⚡ [STAFF OVERRIDE]` exist; a third label needs to be visually distinct. This
   is a safety boundary, not decoration — a hallucinated figure read aloud at an interpellation is
   worse than no cue.

Two migration traps in moving the index to Qdrant:

- **Pin the collection's distance metric to `COSINE` at creation time.** The current `THRESHOLD =
  0.65` is cosine similarity from `np.dot / norms`. Under `DOT` or `EUCLID` the returned score
  means something entirely different — and the threshold fails **silently**, with no error.
- **Store the embedding model's identity in the collection.** Qdrant validates vector
  dimensionality, not model provenance. The pickle carried `bundle["model_name"]` and
  `local_advisor.py` read it back; dropping the pickle **moves** this problem rather than solving
  it. Querying with a different model of the same dimensionality returns confident nonsense.

Open question: **where does the credential live?** It is per-machine, not per-meeting, so it
belongs beside `HF_HOME` in the app-written `.env` — but that is plaintext on disk. Gitignored,
but plaintext. macOS Keychain is the correct home and costs a platform binding.

## 7.6 — Post-meeting cleanup script

Satisfies **R9, R10, R12, R13, R14, R15**.

A script under `tools/` that feeds an archived `history/Meeting_*.md` to headless Claude
(`claude -p`) with a fixed prompt, writing a cleaned copy alongside it. Using full-document
context, the prompt covers: normalizing to Traditional Chinese, re-flowing punctuation and
segment boundaries broken by VAD flushes, splitting `Participant` into distinct speakers, and
dropping residual Whisper hallucinations.

- Write to a **new file**. The raw transcript is the record of what was actually heard.
- **The application's offline guarantee is unaffected** (**R15**) — this is an operator tool run
  deliberately outside the app, and no runtime code path reaches the network. It should still
  carry a one-line notice that running it sends transcript content to Claude, since `history/`
  holds meeting records.

## 7.7 — Optional dual-track audio retention

Satisfies **R3, R16**; bounded by **R4**.

A **toggle on the pre-flight panel** (7.4, **R27**), **default off** — a per-meeting decision,
committed when Start is pressed and fixed for the session. Off by default on disk-space grounds
and because recording carries consent expectations the operator should choose deliberately.
`history/` is already gitignored.

Because the choice is known before the streams open, the writer thread is configured once at
Start rather than having to be attachable to a running capture.

Constraints, ordered by how easily each silently ruins the feature:

- **Write from the raw stream, upstream of VAD.** `_processing_thread` discards whatever VAD
  calls non-speech, so archiving downstream would lose precisely the **VAD misjudgements** —
  exactly the material worth going back to verify. **R3** only holds if the tap point is the
  continuous callback stream.
- **Separate files per track; never mix** (**R2**). Mixing destroys the role attribution this
  architecture gets for free, and which comparable products only obtain because the OS forces
  the same split on them (**V16**).
- **Do not block the audio callback.** Disk writes go through a queue and a writer thread, the
  same pattern already used for `inference_queue`. A load-bearing invariant, not a preference.
- **Lossless only** — lossy undermines evidentiary value. Python's stdlib `wave` module needs
  **no new dependency**; FLAC is a later size optimization.
- **Pair filenames with the transcript** — `history/Meeting_<session_id>_mic.wav` and
  `_system.wav` beside `Meeting_<session_id>.md`, so 7.6 can find them without guessing.
- **Record the precise session start time**, so a transcript timestamp converts to an offset
  into the WAV. Without it, "jump to this moment" — the point of corroboration — does not work.

Size at 16 kHz mono int16:

| | per hour, per track | both tracks | 3-hour hearing |
|---|---|---|---|
| WAV @ 16 kHz | 115 MB | 230 MB | ~690 MB |
| WAV @ 48 kHz (tap's native rate) | 346 MB | 691 MB | ~2.1 GB |

**Open decision:** archive at 16 kHz (matches what the pipeline processed, so the record matches
the transcript) or at 48 kHz (higher fidelity for disputes, 3x the disk). 16 kHz suggested.

---

## 🐛 Known Issues

- **`HF_HOME` in `.env` has never taken effect** — see **V19**. Fixed by 7.4. Confirm afterwards
  by checking where weights actually land on a fresh run.
- **Capture starts before authentication** — see **V18**. Fixed by 7.4.
- **Speaker-audio echo causes double transcription and false RAG triggers.** If the operator uses
  loudspeakers rather than headphones, the microphone also picks up the far end, so the same
  utterance is transcribed twice — once as `Speaker (You)`, once as `Participant`. Since
  `_local_rag_worker_loop` fires only on `role == "Participant"`, the operator's own echoed voice
  can trigger defensive cues. This affects BlackHole today and will affect the tap equally; it is
  introduced by neither. Practical mitigation: **require headphones or an earpiece** — normal in
  hearings and earnings calls anyway. A software fix means AEC, which is far more expensive.
- **Noise enters the participant track by design.** Spotify, Slack chimes, and notification
  sounds follow from **R1**. The defences are `webrtcvad` (severity 3), Whisper's
  `no_speech_threshold`, and the anti-hallucination blacklist in `transcriber.py`. VAD is
  unreliable on *music*, which can be misclassified as speech and then hallucinated into text.
- **`MULTILINGUAL_MODE` is misleadingly named** — see **V2, V3**. Fixed by 7.1 and 7.4.
- `global_state.py` looks for `["MacBook Air Microphone", "Built-in Microphone"]`. On a MacBook
  Pro neither matches, so microphone selection silently relies on `fallback_to_default`. The
  result is usually correct, but the keyword list is not doing its job. Superseded by 7.3.
- Capturing the far end currently requires the BlackHole driver *plus* a manually configured
  Multi-Output Device, or the operator cannot hear the meeting while it is captured. Superseded
  by 7.2.
