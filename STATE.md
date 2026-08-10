# Project State

Where the project is now, and what happens next. **Every item here is meant to be deleted** — plan
items flow into [CHANGELOG.md](CHANGELOG.md) once they ship, and known issues disappear when they
are fixed. Anything that does *not* become obsolete by doing work belongs in
[REQUIREMENTS.md](REQUIREMENTS.md) instead. For how to work in the repo, see [AGENTS.md](AGENTS.md).

**Current release: `v0.0.1`** — BlackHole audio backend.

Rewrite the plan as often as needed; that is what this file is for.

**Cite `R*` and `V*`, not `7.*`.** Plan numbers follow execution order and are renumbered whenever
the order changes — they are not stable identifiers. Requirement and constraint IDs are, and they
live in [REQUIREMENTS.md](REQUIREMENTS.md). (Commits before `a066498` reference an older plan
numbering; read them against the requirements they describe, not the section numbers.)

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

# 🗺️ Phase 7 — Plan

Ordered so each step is independently shippable and the riskiest work lands last. Every item
cites the requirements it satisfies.

## 7.1 — Multilingual ASR — 🔴 do first

Satisfies **R8, R10, R11**. Addresses **V1, V2, V3**.

1. Default to `mlx-community/whisper-large-v3-turbo` (**V4**).
2. **Delete `MULTILINGUAL_MODE`.** `turbo` is multilingual unconditionally, so the ASR half of
   the flag has no meaning; the embedding half becomes a `build_index.py` argument recorded in
   the index. The runtime environment variable disappears entirely.
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
not a browser device picker.

Scope shrinks because of **R1**: if system audio is "everything", there is no source to choose.
So this contributes a **microphone dropdown** and a read-only **active backend indicator** — not
a screen of its own. Both live on the pre-flight panel defined in 7.4 (**R27**). Two dropdowns
became one.

The `st.progress(rms)` level meters already in `app.py` are exactly the meter Zoom shows beside
its device picker, so the familiar UX needs no new visual work — and they are the existing
example of **R36**, a component that shows it is alive while producing nothing.

Trap: `Transcriber.__init__` preloads the model into the NPU (**V33**). Switching devices must
**not** naively reconstruct a `Transcriber` — separate "change device" from "reload model".

Bonus: a dropdown makes the hardcoded microphone-keyword bug (Known Issues) irrelevant.

## 7.4 — Configuration and startup: one new file plus `app.py`

Satisfies **R17–R25, R32–R35**. Addresses **V18, V19, V37**; enabled by **V20**; constrained by
**V21, V33**.

### There is no wizard — there is a form, and `.env` is its snapshot

`.env` is not a configuration file the operator maintains; it is where the settings form
persists itself (**R32**). That collapses what was previously described as a first-run wizard and
a separate settings screen into **one screen**, which on first run simply renders blank.

`setup_mac.sh` keeps its current scope — Homebrew dependencies, `.venv`, `pip install`. Only the
**model download** moves behind the UI (**R21**):

```
bash setup_mac.sh          # brew + .venv + pip install (unchanged)
streamlit run src/app.py
  └─ settings form: blank on first run, refilled from .env afterwards   (R20, R32)
     → operator fills the one required field                            (R19)
     → app writes .env                                                  (R18)
     → downloads models, progress shown in the UI                       (R23)
     → warms the NPU
     → Start unlocks                                                    (R24)
```

Reset is deleting `.env` (**R22**) — the form goes blank again. The operator never opens it in an
editor (**R18**).

### The settings form

Persisted, because these were typed and cannot be re-enumerated (**R33**):

| # | Field | When absent |
|---|---|---|
| 1 | Model cache directory | **The only required field** — without it there is nothing to download Whisper into |
| 2 | Qdrant URL | Blank ⇒ local mode; RAG still works (**V29**) |
| 3 | Qdrant credential 🔒 | Blank ⇒ local mode |
| 4 | Embedding model name | Has a default |
| 5 | LLM base URL | Blank ⇒ LLM advisor unavailable (**R28**) |
| 6 | LLM credential 🔒 | — |
| 7 | LLM model name | Has a default |
| 8 | ASR model | Has a default (`turbo`). Here rather than pre-flight — see *Decided and closed*. Changing it re-enters `warming` (**V33**), and the UI must say so. |

**Masked fields are plain `type="password"` rendering, not a separate value.** The eye control
flips the input type; the value is the real one throughout. Streamlit's password input has no
built-in reveal, so the toggle is a small piece of work rather than free. Because the form
renders only locally (below), no sentinel handling is needed — see *Decided and closed*.

### `is_local` gates the whole screen, and must fail closed *loudly*

**R34** makes this a screen-level gate rather than a per-widget decision: the pre-flight panel
and the settings form both operate the capturing machine, so both are local-only. `is_local`
already exists (**V37**) and needs two changes:

1. **Gate the settings form and pre-flight panel on it**, not just the PIN prompt. This also
   keeps credentials off the LAN — remote pages are served over plain HTTP (**V13**), so a
   real API key rendered into a remote browser would cross the network in the clear.
2. **Flip the `except` branch to fail closed** — treat an undetectable host as remote. But a
   silent fail-closed is a bricked app: the operator would face a control panel with no Start
   button and no explanation. **The failure must be stated on screen** ("cannot determine whether
   this is a local connection; treating as remote").

Resulting screen flow:

```
local:   (no PIN)  →  role  →  settings + pre-flight  →  running
remote:  PIN       →  role  →         ✗               →  running (or waiting)
```

**A remote device that arrives before Start needs a waiting state** (**R35**) — the speaker
routinely connects before the staff officer starts capture. Today the question never arises
because `app.py:27` auto-starts; removing that auto-start creates this state.

### Where the work goes

**V20** makes this far smaller than it looks — deferring one import is sufficient.

| File | Change |
|---|---|
| `src/bootstrap.py` (new) | Zero project imports — stdlib plus `dotenv` only. Reads and writes `.env`, resolves the cache directory, sets `os.environ["HF_HOME"]` *before* anything heavy loads, checks whether weights are present, owns the readiness state machine. |
| `app.py` | Move `from global_state import ...` out of module scope into a function called only once configuration exists; drop the `app.py:27` auto-start (**V18**); add the settings form, the `is_local` gate, the waiting state, and Start gating. |
| `transcriber.py` | **Untouched.** |
| `local_advisor.py` | **Untouched** by this item (7.5 changes it). |
| `global_state.py` | **Untouched**, until `ENABLE_LOCAL_RAG` becomes a UI toggle — a separate, smaller step. |

Implementation ordering note: checking whether weights already exist is most reliably done via
`huggingface_hub`'s cache API, but importing it fixes `HF_HOME` (**V19**). So `bootstrap.py` must
set the path *first*, then import to inspect. Internal to that one file, but easy to get backwards.

### Readiness state machine

```
no-config → downloading → warming → ready
```

Start is `disabled` until `ready` (**R24**), which also satisfies **R25**: capture cannot begin
early because the control that begins it is not pressable. Changing the ASR model returns the
machine to `warming` (**V33**) — expected, and the UI says why.

### The pre-flight panel

Once `ready`, the operator sees one screen holding **every per-meeting decision** (**R27**), so
the plan items below do not each grow their own UI:

| Control | Kind | Default | From |
|---|---|---|---|
| Microphone | dropdown | system default | 7.3 / **R26** |
| Retain dual-track audio | toggle | off | 7.7 / **R16** |
| RAG advisor | toggle + **readiness** | on | 7.5 / **R36** |
| LLM advisor | toggle | off; hidden unless configured | 7.5 / **R28** |
| Active capture backend | **read-only** indicator | auto-detected | 7.2 / **R7** |
| Input level meters | read-only | — | already built (`st.progress(rms)`) |
| **Start** | button | disabled until `ready` | **R24, R25** |

The RAG row is a **status, not a checkbox** — `知識庫：148 chunks · 2026-08-05 編譯` versus
`⚠️ 0 chunks — 尚未編譯`. That turns an invisible precondition (**V34**) into a visible one at
the moment the operator can still act on it.

Pressing Start **commits** these choices and opens the streams. They are fixed for the session;
changing one means stopping and starting again. That keeps stream setup and the audio writer
configured once, rather than being mutable mid-capture.

None of these are persisted (**R33**) — the panel is rebuilt from live enumeration and defaults
on every launch.

### Warm eagerly, open streams lazily

Fully lazy loading is the wrong correction — `turbo` is 1.61 GB across two `Transcriber`
instances warmed sequentially (**V33**), so deferring everything to Start puts that wait at the
worst moment. Split the two concerns currently fused in `Transcriber.__init__`:

- **Model warm-up** touches no audio device; it may run automatically once configuration exists.
- **Opening the audio streams** waits for authentication *and* an explicit Start.

### ⚠️ Two places where this item departs from what was asked for

Recorded because both were requested one way and planned another. Neither is a silent
reinterpretation to be discovered later; if either reason stops holding, the plan should change
back rather than the request being quietly forgotten.

| Asked for (2026-08-07) | Planned instead | Why |
|---|---|---|
| Warm-up also waits for Start — nothing heavy happens until the operator presses it | Warm-up runs as soon as configuration exists; **only stream opening** waits for Start | **V33**: two `Transcriber` instances warm *sequentially* under `NPU_LOCK`, minutes for a 1.61 GB model. Deferring that to Start puts the whole wait at the worst possible moment — after the operator has committed to starting. The half that carries the actual guarantee is preserved: no capture before authentication and an explicit Start (**R24, R25**). |
| The web page runs `setup_mac.sh` once the operator has chosen a cache directory | `setup_mac.sh` keeps its current scope; only the **model download** moves behind the UI | Streamlit is already running *inside* `.venv` by the time the form is visible, so it cannot rebuild that `.venv` from within, and Homebrew installs need a shell the app does not own. The stated goal still holds — nothing must be downloaded before the first cold start (**R21**) — because the weights are the only part that was ever large. |

### Configuration lifecycle

| Setting | Real lifecycle | Belongs in |
|---|---|---|
| `HF_HOME` | once per machine | `.env`, written by the app |
| Advisor hosts, credentials, model names | once per machine | `.env`, written by the app (**R32**) |
| ASR model | once per machine | `.env`; changing it re-warms (**V33**) |
| `ENABLE_LOCAL_RAG` and the LLM toggle | per session | pre-flight panel |
| audio backend | capability, not preference | auto-detected (7.2) |
| `ARCHIVE_AUDIO` | per **meeting** | pre-flight toggle, default off (7.7) |
| microphone | per meeting, enumerable | pre-flight dropdown, not persisted (**R33**) |
| `MULTILINGUAL_MODE` | — | **deleted** (7.1) |
| `PIP_CACHE_DIR` | during `pip install` only | `setup_mac.sh`, which already exports it |

## 7.5 — Pluggable advisor backends (RAG via Qdrant, LLM via OpenAI-compatible)

Satisfies **R28–R31, R36**. Built on **V22–V36**.

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

Scale to budget for: a two-hour meeting with an utterance every few seconds is **hundreds to low
thousands of calls**, bounded by **V27**'s coalescing rather than by utterance count.

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
5. **Surface liveness** (**R36**, **V34**, **V35**). Two places:
   - *Pre-flight*: the RAG row shows chunk count and build date, so an unbuilt or empty index is
     caught before the meeting rather than during it.
   - *Running*: show the most recent similarity score. `local_advisor.py:84` already computes and
     logs it unconditionally, so this is close to free — and it is what makes `RAG 0.31` ("alive,
     nothing matched") distinguishable from no score at all ("dead").

Two migration traps in moving the index to Qdrant, both of which fail **silently**:

- **Pin the collection's distance metric to `COSINE` at creation time.** The current `THRESHOLD =
  0.65` is cosine similarity from `np.dot / norms`. Under `DOT` or `EUCLID` the returned score
  means something entirely different — and the threshold fails with no error.
- **Store the embedding model's identity in the collection** (**V36**). Qdrant validates vector
  dimensionality, not model provenance. The pickle carried `bundle["model_name"]` and
  `local_advisor.py` read it back, so this failure is *impossible today*; dropping the pickle
  **introduces** it. Querying with a different model of the same dimensionality returns confident
  nonsense.

**Open decision — are the two band edges adjustable, and if so from where?** `0.65` is the
threshold already shipping in `local_advisor.py` (**V22**), so it has at least been exercised
against a real index. **`0.45` has no empirical basis whatsoever** — it was proposed while drafting
this plan and has never been measured. Two separate questions follow:

- **Whether to expose them at all**, or leave both as constants until real meetings give them a
  basis. Exposing an unmeasured number invites tuning by superstition, and a wrong lower edge fails
  in the expensive direction: too low floods the speaker with generated text, too high silently
  disables the LLM band.
- **If exposed, which layer.** A threshold is *typed*, not enumerable, so **R33** places it in
  `.env` with the other persisted settings rather than on the pre-flight panel — it is a property
  of the knowledge base and the domain, not of a single meeting.

Resolve by measurement during 7.5, not before it.

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

Size, mono int16 — the chosen row is 48 kHz:

| | per hour, per track | both tracks | 3-hour hearing |
|---|---|---|---|
| WAV @ 16 kHz | 115 MB | 230 MB | ~690 MB |
| **WAV @ 48 kHz** (native rate of both the tap and the microphone) | **346 MB** | **691 MB** | **~2.1 GB** |

**Sample rate — decided 2026-08-07: 48 kHz.** 48 kHz is the uncompressed rate the hardware
actually produces (**V7**); 16 kHz is merely what the inference path happens to consume. Archiving
at 16 kHz would store a resampled *derivative* of the record, and an archive kept for
corroboration (**R16**) must not be a derivative of what was heard. The 3x disk cost is accepted.

Consequence, and it is not free: the capture stream must open at **48 kHz**, so resampling moves
from the device into the software path. That makes **V12**'s fallback — run VAD at 48 kHz, resample
only immediately before inference — the *mandatory* design rather than a contingency, and it
couples this item to 7.2. `transcriber.py:46` currently hardcodes `sample_rate = 16000`, and
`webrtcvad` accepts 48000, so the change is confined to stream setup plus one resample step before
`inference_queue`.

---

## 🐛 Known Issues

- **The RAG advisor fails silently when the index is missing or stale** — see **V34**. The toggle
  reads as armed and nothing will ever fire, with no signal in the UI. This is the failure this
  product can least afford: it is discovered at the moment the defence was needed. Fixed by 7.5's
  liveness work (**R36**).
- **`HF_HOME` in `.env` has never taken effect** — see **V19**. Fixed by 7.4. Confirm afterwards
  by checking where weights actually land on a fresh run.
- **Capture starts before authentication** — see **V18**. Fixed by 7.4.
- **`is_local` fails open** — see **V37**. Harmless while it only skips a PIN prompt; not harmless
  once it gates credentials. Fixed by 7.4, which must also make the failure visible.
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
- **`MULTILINGUAL_MODE` is misleadingly named** — see **V2, V3**. Deleted by 7.1.
- `global_state.py` looks for `["MacBook Air Microphone", "Built-in Microphone"]`. On a MacBook
  Pro neither matches, so microphone selection silently relies on `fallback_to_default`. The
  result is usually correct, but the keyword list is not doing its job. Superseded by 7.3.
- Capturing the far end currently requires the BlackHole driver *plus* a manually configured
  Multi-Output Device, or the operator cannot hear the meeting while it is captured. Superseded
  by 7.2.
