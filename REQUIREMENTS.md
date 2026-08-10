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
| Relying on a context-overflow error code | Ollama truncates silently and does not forward `num_ctx`; vLLM errors where the spec says truncate. Own the bound locally instead. | V26, V32 |
| macOS Keychain for credentials | Plaintext `.env` plus UI masking is consistent with a product that already stores full meeting transcripts in plaintext under `history/` — the credential is not the weakest link, and a platform binding buys little. Masking still earns its place against shoulder-surfing and screen sharing. | R32 |
| Three-state sentinel handling for masked credential fields | Unnecessary once the settings form renders **only locally** (**R34**): the field always carries the real value, so writing it back is idempotent. There is no way to save a row of asterisks over a real key. | R32, R34 |
| ASR model choice as a pre-flight control | It would grey out Start for minutes (**V33**), and once the default model is multilingual there is no per-meeting reason to switch — it detects language per VAD segment (**V4**). It belongs in the persisted layer. | R11, R24, V4, V33 |
| Splitting `MULTILINGUAL_MODE` into two settings | It can be **deleted** instead: `turbo` is multilingual unconditionally, and the embedding-model choice becomes a `build_index.py` argument recorded in the Qdrant collection. | V2, V3, V4 |
