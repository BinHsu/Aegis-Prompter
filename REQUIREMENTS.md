# Requirements

What this product must do, what has been measured, and what has been ruled out. **Nothing here
becomes obsolete by doing work** — a requirement still holds after it has been satisfied, and from
then on it is the standard the implementation is judged against. For where the project is now and
what happens next, see [STATE.md](STATE.md). For how to work in the repo, see [AGENTS.md](AGENTS.md).

| Layer | What it holds | Changes when |
|---|---|---|
| **Design stance** | Durable product principles | The product's purpose changes |
| **Requirements** (`R*`) | What is wanted, stated without implementation | The operator's needs change |
| **Verified constraints** (`V*`) | Measured facts that bound the solution space | Reality changes, or a measurement is redone |

The volatile fourth layer — the plan — deliberately lives in a different file, so that rewriting it
never requires opening this one.

Two rules, both learned by breaking them:

- **Do not quietly rewrite a requirement to match a plan.** If a plan cannot satisfy a requirement,
  that is a finding to record, not a wording problem to smooth over.
- **Do not restate a constraint without re-measuring it.** Every `V*` is dated to the investigation
  that produced it.

**IDs are never reordered**, even when the section around them is. That is what makes them safe to
cite from the plan, from commit messages, and from `docs/decisions/`. Gaps are left in place rather
than closed up.

---

## 🧭 Design stance

> **Whatever your ears can hear and whatever your mouth says, we ingest.**
>
> **Our job is not to lose it. What it gets used for is the file owner's decision.**

The first sentence makes capture **source-agnostic**. It does not matter whether the meeting
runs in Zoom's native app, Meet in a browser tab, Teams, or anything else.

The second draws the **product boundary**: the system is responsible for completeness of
capture, not for policy about the captured material. Retention, cleanup, redaction, disclosure,
and which advisor backend is appropriate are the operator's calls — which is why post-processing,
audio retention, and the advisor slots are opt-in tools rather than pipeline behaviour.

---

# 📋 Requirements

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
- **R37 — Non-speech must not become an utterance.** Music, notification chimes and keyboard noise
  enter the participant track by design (**R1**, **R5**). Whatever model is chosen, the pipeline must
  not turn them into `Participant` lines — a false line can fire a defensive cue, which is worse than
  silence. This ranks **above** transcription accuracy when choosing a model, because published ASR
  benchmarks measure word error on speech and none of them measure this.

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
- **R32 — `.env` is a snapshot of the settings form.** Values the operator typed are persisted
  and shown back on the next launch; absent configuration renders as **blank fields**, not an
  error. Credentials render masked, with a reveal toggle.
- **R33 — Persist what was typed; do not persist what can be enumerated.** A URL or a credential
  cannot be rediscovered at runtime, so it is stored. A device list is rebuilt on every launch,
  so storing a choice would only create a stale reference.

## Device selection and pre-flight

- **R26 — Audio input is selectable from the web page**, in the manner of Zoom or Meet web:
  a sensible default, freely overridable.
- **R27 — Every per-meeting decision is made on one pre-Start panel.** The screen shown before
  capture begins is the single place the operator chooses microphone, whether to retain audio,
  and which advisors are active — reviewed together, then committed by pressing Start. No
  per-meeting choice lives anywhere else.
- **R34 — Machine-control actions are local-only; tactical actions may be remote.** Start and
  Stop, device selection, backend configuration, and audio retention operate the machine that is
  capturing, and are available only on that machine. Viewing the transcript and injecting cues
  touch no audio hardware and stay available to a remote staff member — the README's remote-staff
  scenario is preserved.
- **R35 — A remote device that connects before capture starts must see an explicit waiting
  state**, not a blank screen and not an error. The speaker will routinely connect before the
  staff officer presses Start.

## Advisor backends

- **R28 — RAG and LLM are two independently configurable slots.** The operator may fill
  neither, either, or both. Whatever is filled gets sent to; the app is a transport, not a
  policy-maker about which backend is appropriate.
- **R29 — Every response is labelled with the vendor that produced it.**
- **R30 — Generated content is visibly marked as unverified**, distinctly from retrieved
  pre-written content. Retrieved text is safe to read aloud; generated text is not.
- **R31 — The operator supplies a host and a credential; the app sends and receives.** No
  per-vendor configuration beyond that.

## Observability

- **R36 — Any component whose normal output is "nothing" must expose a liveness signal.**
  Silence has to be distinguishable from failure, and the distinction must be visible *before*
  and *during* a meeting rather than discovered afterwards. The audio path already satisfies this
  with its level meters; the advisor path does not.

## The control surface

The web page *is* the product's only surface (**R17**), so its behaviour is a requirement, not a
design detail left to whoever implements it.

- **R38 — Operator-facing text is Traditional Chinese.** The operator reads cues aloud in a Taiwan
  hearing room, so the interface speaks the same language as the material. This does not loosen the
  English-only codebase rule in `AGENTS.md`, which governs identifiers, comments, log output and test
  assertions — a displayed string is none of those. Log files stay English so they remain greppable.
- **R39 — No dead ends.** Every reachable state renders something that says what is happening and
  what the operator can do. This includes failure states, which are the ones that get skipped: an
  undetermined local/remote verdict, a denied macOS audio-capture permission, a capture device that
  disappears mid-session, an advisor host that does not answer.
- **R40 — A control is never live before its precondition is met, and an unmet precondition must
  name what is missing.** A disabled control with no explanation is indistinguishable from a broken
  one. Where a precondition is a *credential or a host* the dependent control is disabled; where the
  whole capability is unconfigured the control is **hidden**, because offering something that cannot
  work is worse than not offering it.
- **R41 — Choices that cost something warn before they take effect**, not after. Four kinds cost
  something: disk consumption, discarding warmed model state, sending data off the machine, and
  producing text that has not been verified.
- **R42 — The three kinds of advisor output are visually distinct, and the advisor's liveness is
  visible while capture runs.** Retrieved pre-written text is safe to read aloud; generated text is
  not (**R30**); a staff override is a human instruction. A reader glancing at the screen mid-sentence
  must not have to work out which one they are looking at.
- **R43 — The LAN surface is not confidential, and the operator is told so.** Remote pages are served
  over plain HTTP (**V13**), so the transcript and the access code cross the network in the clear.
  Nothing may be rendered to a remote browser that is not already in the transcript, and the local
  page states plainly that remote viewing is unencrypted.
- **R44 — The audio archive directory is operator-specified**, for the same reason as the model cache
  (**R19**): at 48 kHz two tracks reach roughly 2.1 GB for a three-hour hearing, which may not belong
  on the internal drive.

### Screens

| State | Local | Remote | Renders |
|---|---|---|---|
| Access | no prompt | access code | Remote entry only (**V37**, and the verdict must fail closed *loudly*) |
| Role | selection | selection | Speaker view vs staff view |
| Configure | settings form | **✗** | Blank on first run, refilled from `.env` afterwards |
| Pre-flight | full panel | **waiting state** | The single place per-meeting choices are made (**R27**, **R35**) |
| Running | transcript, advisor, meters, Stop | transcript, advisor, cue injection | Control actions are local-only (**R34**) |

### Persisted fields — the settings form

Typed, so they cannot be re-enumerated (**R33**). This inventory is normative; the plan implements
it rather than restating it.

| # | Field | Required | When absent |
|---|---|---|---|
| 1 | Model cache directory | **yes** | Nothing to download weights into — the one field that blocks everything |
| 2 | Audio archive directory | only to retain audio | Retention unavailable (**R44**) |
| 3 | Qdrant URL | no | Local mode; RAG still works (**V29**) |
| 4 | Qdrant credential 🔒 | no | Local mode |
| 5 | Embedding model name | no | Has a default |
| 6 | LLM base URL | no | LLM advisor unavailable (**R28**) |
| 7 | LLM credential 🔒 | no | — |
| 8 | LLM model name | no | Has a default |
| 9 | ASR model | no | Has a default. Persisted rather than per-meeting — see *Decided and closed* |

Credential fields render as `type="password"` with a reveal toggle; the value behind them is always
the real one, never a sentinel (**R32**).

### Per-meeting controls — the pre-flight panel

Not persisted (**R33**); rebuilt from live enumeration and defaults on every launch. Pressing Start
commits all of them for the session.

| Control | Kind | Default |
|---|---|---|
| Microphone | dropdown | system default (**R26**) |
| Retain dual-track audio | toggle | off (**R16**) |
| RAG advisor | toggle **plus a readiness line** | on (**R36**) |
| LLM advisor | toggle | off, hidden unless configured (**R28**) |
| Active capture backend | read-only indicator | auto-detected (**R7**) |
| Input level meters | read-only | — |
| **Start** | button | disabled until ready (**R24**, **R25**) |

### Enablement, disclosure and warnings

The normative answer to "what does ticking this do". Nothing outside this table changes state as a
side effect of another control.

| Control | Live only when | Acting on it triggers |
|---|---|---|
| Qdrant credential | Qdrant URL is non-empty | — |
| LLM credential, LLM model name | LLM base URL is non-empty | — |
| **LLM advisor** toggle | **hidden entirely** unless LLM base URL is configured | ⚠️ generated text is unverified — not safe to read aloud (**R30**) |
| **RAG advisor** toggle | the index reports at least one chunk | — (the readiness line always shows chunk count and build date, armed or not — **V34**) |
| **Retain dual-track audio** | an audio archive directory is configured (**R44**) | ⚠️ disk estimate for the expected meeting length, plus the reminder that recording carries consent expectations (**R4**) |
| Model cache directory | always | 📁 folder chooser (**V45**) |
| Audio archive directory | always | 📁 folder chooser (**V45**) |
| ASR model | always | ⚠️ returns to `warming` for minutes, possibly preceded by a download (**V33**) |
| Embedding model name | always | ⚠️ the existing index was built with a different model and must be rebuilt (**V36**) |
| Qdrant URL / LLM base URL pointing off-machine | always | ⚠️ queries and credential leave this machine (**R4** — the operator's call, but an informed one) |
| **Start** | readiness is `ready` | Commits every per-meeting choice and opens the streams (**R27**) |

---

# 🔬 Verified constraints

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

## The ASR field moved after this plan was written

Read from published sources and vendor model cards on **2026-08-10**, **not measured on this
hardware** — which is exactly why **R11** is satisfied by a local bake-off rather than by these
numbers. Treat every figure here as a reason to test, not as a result.

- **V38 — Google's Gemma 4 (2026-06) has native audio ASR and diarization, and is still unusable
  here.** The 12B unified model is encoder-free, projecting raw 16 kHz audio directly into the
  embedding space, Apache 2.0; the E2B/E4B edge variants keep a 300M conformer audio encoder with a
  30-second ceiling. Four independent blockers: a hands-on report found **`mlx-vlm` silently ignores
  the audio input** (this project's runtime is Python + MLX, and Swift is the only working MLX path);
  BF16 needs ~23.9 GB and quantization degrades transcription; two `Transcriber` instances each hold
  their own model, so it would force an architectural rewrite; and Google published no WER at all.
- **V39 — Qwen3-ASR (0.6B / 1.7B, Apache 2.0) outperforms the model this plan selected.** Third-party
  Apple Silicon measurements on an M5 Pro: 1.32% WER at 5-bit against WhisperKit `large-v3-turbo`'s
  1.71%, RTF 0.027, 1.92 GB resident; Chinese CER 7.71 on FLEURS. 30 languages plus 22 Chinese
  dialects including Cantonese. The MLX port accepts a **numpy array** directly, which is the exact
  shape `transcriber.py` already passes to `mlx_whisper.transcribe()`.
- **V40 — Qwen3-ASR's context biasing is a trained-in capability, not a decoder trick.** The model
  card's own usage is `prompt="Vocabulary: ..."`. This is materially different from Whisper's
  `initial_prompt`, and it opens a path this plan does not contain: the same `context/docs/` knowledge
  base could bias ASR *and* serve RAG.
- **V41 — Qwen3-ASR exposes no `no_speech_threshold` equivalent, and advertises singing and
  music-with-backing-track as supported input.** The public API surfaces only `finish_reason`
  (`eos` / `repetition` / `length`). Today `transcriber.py` relies on `no_speech_threshold=0.6` plus a
  hallucination blacklist. For this product, transcribing music is a **negative** capability: a
  Spotify track becomes lyrics attributed to `Participant`. Directly threatens **R37**.
- **V42 — Neither candidate solves Traditional Chinese.** Qwen3-ASR's language list contains only
  `Chinese (zh)`, exactly as Whisper has a single `zh` token (**V5**). Script control remains a
  post-processing concern; whether a Traditional-script context prompt biases the output is untested.
- **V43 — Parakeet TDT v3 is the throughput leader and is excluded outright**: ~25 European languages,
  no Chinese. **R8** disqualifies it regardless of speed.
- **V44 — `mlx-qwen3-asr` is a community reimplementation, not a vendor port.** Apache 2.0 over
  official weights, single maintainer. For a product whose premise is running offline forever, that is
  a supply-chain consideration to decide deliberately rather than discover later.

## The web framework has no folder picker

- **V45 — Unverified.** Streamlit has no directory-selection widget; `st.file_uploader` uploads file
  contents, which is the wrong operation for **R19** and **R44**. Because both fields render only on
  the local machine (**R34**), a native macOS `choose folder` dialog invoked from the server process is
  available in principle. Whether that dialog can be raised from inside a Streamlit callback without
  blocking the script re-run has not been tested, and the fallback is a validated text field.

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
  cannot even enumerate devices. The same fact means anything sent to a remote browser crosses
  the LAN unencrypted.
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

## The startup path is eager, and eager in the wrong order

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
- **V33 — Warm-up is fused into `Transcriber.__init__`, and serialized.** Lines 57–60 run the
  NPU preload under `NPU_LOCK`, so the two `Transcriber` instances warm **sequentially**, not in
  parallel. Under the multilingual model of **V4** that is 1.61 GB. Changing the ASR model
  therefore discards warmed
  state and re-enters `warming` for both instances — minutes, possibly preceded by a download.
  *Unverified*: whether `mlx_whisper` caches by repo path, and so whether switching models back
  and forth holds two copies in memory.
- **V37 — `is_local` already exists and fails open.** `app.py:59-71` derives it from the Host
  header (`localhost` / `127.0.0.1` / empty) and currently uses it only to skip the PIN gate. The
  `except` branch sets `is_local = True`, so a detection failure silently grants local
  privileges.

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
- **V34 — The RAG path fails silently, end to end.** `local_advisor.py:30-32` logs a warning and
  **returns** when the index is missing — no exception. `self.model` and
  `self.knowledge_embeddings` stay `None`, so the guard at `:53-54` returns `None` on every
  subsequent call, forever. `_local_rag_worker_loop` does nothing with `None`, and `app.py`
  surfaces no advisor state at all — grep finds only the `.advisor-box` CSS rule and the render
  line. The operator sees an armed toggle and a defence that will never fire. Two variants
  present identically: a missing index, and a **stale** one built before today's material was
  added.
- **V35 — The liveness signal already exists, but only reaches the log.**
  `local_advisor.py:84` computes and logs the similarity score **unconditionally for every
  utterance**, including below-threshold and repeat-suppressed cases. Surfacing the most recent
  score is what distinguishes "working, nothing matched" from "dead" (**R36**).
- **V36 — The pickle currently prevents a query/build model mismatch; Qdrant would not.**
  `build_index.py` writes `model_name` into the bundle and `local_advisor.py:40` loads exactly
  that model, so querying with a different model is impossible today. Qdrant validates vector
  dimensionality but **not** model provenance, so the migration **introduces** this failure mode
  rather than inheriting it — and it too returns confident nonsense rather than an error.

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
| Persisting *enumerable* selections (a `.aegis_settings.json` for the microphone) | Meet and Zoom web persist nothing: default plus override is sufficient, and storing a device reference only creates a stale name-or-index problem. Typed values are a different case — see R32/R33. | R26, R33 |
| Archiving audio *in order to* diarize | The cleanup pass works from text. Audio retention stands on corroboration instead. | R14, R16 |
| Archiving at 16 kHz to match what the pipeline consumes | 48 kHz is the uncompressed rate the hardware produces; an archive kept for corroboration must not be a resampled derivative of the record. Costs 3x the disk and moves resampling into the software path. | R3, R16, V7, V12 |
| Deleting `.env` outright | The cache directory must stay user-choosable; large weights may not belong on the internal drive. `.env` survives as a machine-written form snapshot. | R18, R19, R32 |
| A separate local intent model to gate the LLM | The RAG score is already an intent judgement and costs microseconds; a second model would contend for the NPU that `201eeea` exists to unblock. | V22, V23 |
| RAG backends other than Qdrant | Retrieval-as-a-service has no standard interface — Qdrant, Weaviate, Pinecone and Chroma each have their own API. One vendor beats an abstraction over four. | R28, R31 |
| Gemma 4 in the live ASR path | Audio is silently dropped on the Python MLX path this project runs on, BF16 needs ~24 GB and quantization degrades it, and no WER was ever published. Its diarization is attractive but belongs to the offline cleanup pass, not the live path. | R11, V38 |
| Parakeet TDT v3 | Fastest open model measured, and it does not support Chinese. | R8, V43 |
| Choosing the ASR model from published benchmarks | Every leaderboard measures word error on speech; none measures whether music becomes an utterance, which is the failure this product cannot absorb. | R11, R37, V41 |
| Relying on a context-overflow error code | Ollama truncates silently and does not forward `num_ctx`; vLLM errors where the spec says truncate. Own the bound locally instead. | V26, V32 |
| macOS Keychain for credentials | Plaintext `.env` plus UI masking is consistent with a product that already stores full meeting transcripts in plaintext under `history/` — the credential is not the weakest link, and a platform binding buys little. Masking still earns its place against shoulder-surfing and screen sharing. | R32 |
| Three-state sentinel handling for masked credential fields | Unnecessary once the settings form renders **only locally** (**R34**): the field always carries the real value, so writing it back is idempotent. There is no way to save a row of asterisks over a real key. | R32, R34 |
| ASR model choice as a pre-flight control | It would grey out Start for minutes (**V33**), and once the default model is multilingual there is no per-meeting reason to switch — it detects language per VAD segment (**V4**). It belongs in the persisted layer. | R11, R24, V4, V33 |
| Splitting `MULTILINGUAL_MODE` into two settings | It can be **deleted** instead: `turbo` is multilingual unconditionally, and the embedding-model choice becomes a `build_index.py` argument recorded in the Qdrant collection. | V2, V3, V4 |
