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

**Reordered twice on 2026-08-10.** First pass: microphone selection and retention both need the
pre-flight panel, the cleanup script should see retention's filename contract, and the 48 kHz
capture path must exist before ASR latency and false-trigger numbers are treated as final.

Second pass moved **configuration ahead of the ASR bake-off**, for one concrete reason: the bake-off
downloads 1.6–3.4 GB, and `HF_HOME` does not work yet (**V19**). Running it first lands weights in
`~/.cache/huggingface`, and once a storage root is configured the derived path under **R48** points
elsewhere — so the fixed layout that exists to make re-download impossible (**V47**) would be
defeated by the plan's own first step. Configuration also clears three known issues and builds the
pre-flight panel every later item assumes.

The bake-off has **two halves and they unblock at different times**: choosing a provisional default
needs only configuration, while *closing* it needs the 48 kHz path from the process-tap item. Its
long-lead task — recording audio fixtures — depends on neither and can start immediately, in
parallel with configuration.

Plan numbers are execution order and are renumbered whenever it changes. Older commits saying
"7.4" for configuration mean the *configuration work*, not today's section number.

## 7.1 — Configuration and startup: one new file plus `app.py` — 🔴 do first

Satisfies **R17–R25, R32–R35, R38–R41, R43, R46–R48**. Addresses **V18, V19, V37, V46, V47**;
enabled by **V20**; constrained by **V21, V33, V45**.

### There is no wizard — there is a form, and `.env` is its snapshot

`.env` is not a configuration file the operator maintains; it is where the settings form
persists itself (**R32**). That collapses what was previously described as a first-run wizard and
a separate settings screen into **one Configure state**, which on first run simply renders blank.
Pre-flight is the **next** local state once readiness is `ready` — not a second copy of the form
and not a single scrollable mash-up. See *Screens* in [REQUIREMENTS.md](REQUIREMENTS.md).

`setup_mac.sh` keeps its current scope — Homebrew dependencies, `.venv`, `pip install`. Only the
**model download** moves behind the UI (**R21**):

```
bash setup_mac.sh          # brew + .venv + pip install (unchanged)
streamlit run src/app.py
  └─ Configure: blank on first run, refilled from .env afterwards       (R20, R32)
     → operator fills the one required field                            (R19, R48)
     → app writes .env                                                  (R18)
     → downloads models, progress shown in the UI                       (R23)
     → warms the NPU
     → Pre-flight unlocks                                               (R24)
```

Reset is deleting `.env` (**R22**) — the form goes blank again. The operator never opens it in an
editor (**R18**). Three mechanics carry that:

- **The reset button deletes `.env` and touches nothing else** (**R47**). Before deleting it lists the
  paths that are about to go unreferenced, with sizes — not to offer removal, but because the operator
  is about to lose the only on-screen record of where their data is.
- **Re-entering the same storage root restores everything** (**R48**, **V47**): the layout beneath it
  is fixed, so the derived cache path is byte-identical and the weights are recognised, not refetched.
  The form reports what it found under the root before writing anything.
- **Saving the form is an atomic rewrite** (**V46**) — temporary file plus `os.replace()`. Streamlit
  reruns the script constantly, and a torn `.env` reads as a half-configured machine rather than as an
  interrupted write.

### The settings form

**The field inventory (including `.env` keys), the enablement rules and the warnings are specified
in [REQUIREMENTS.md](REQUIREMENTS.md) under *The control surface* (**R38–R48**) — nine fields, one of
them required, plus derived `HF_HOME` and sticky `ARCHIVE_AUDIO`.** This item implements that table;
it must not restate it, because two copies of a UI spec is how they start disagreeing.

What is left for the plan is the work the table does not describe:

- **Masked fields are plain `type="password"` rendering, not a separate value.** The eye control flips
  the input type; the value is the real one throughout. Streamlit's password input has no built-in
  reveal, so the toggle is a small piece of work rather than free. Because the form renders only
  locally (below), no sentinel handling is needed — see *Decided and closed*.
- **The two folder choosers are the only genuinely unknown widget** (**V45**). Test the native macOS
  dialog first; fall back to a validated text field rather than blocking on it. **Measure before
  coding the happy path** — an untested `choose folder` call that blocks Streamlit's rerun bricks
  Configure.
- **The warnings are part of this item, not polish** (**R41**). Re-warming, index invalidation and
  off-machine egress each have to be stated at the moment the operator changes the field, and every
  disabled control has to say which field would enable it (**R40**).
- **Cross-field enablement runs on every re-run**, since Streamlit re-executes the whole script.
  Derive the disabled/hidden state from the current field values each pass rather than storing it.
- **Download progress cannot be tailed from the log** (**V21**). Capture tqdm/stdout (or use
  `huggingface_hub` callbacks) into a structure `bootstrap.py` owns and the Configure view polls.
  Inventing "just stream the log file" will miss the phase **R23** cares about.
- **Show the access code on the local Configure / Pre-flight chrome**, not only as a console banner.
  Remote staff still need a PIN (**R34**, **R43**); once Start is gated, staring at the terminal is
  not an interface.

### `is_local` gates the whole screen, and must fail closed *loudly*

**R34** makes this a screen-level gate rather than a per-widget decision: Configure and Pre-flight
both operate the capturing machine, so both are local-only. `is_local` already exists (**V37**) and
needs two changes:

1. **Gate Configure and Pre-flight on it**, not just the PIN prompt. This also keeps credentials
   off the LAN — remote pages are served over plain HTTP (**V13**), so a real API key rendered into
   a remote browser would cross the network in the clear (**R43**). The same item states the
   unencrypted-LAN fact on the local page, since the transcript crosses the network whether or not
   a credential does.
2. **Flip every fail-open branch to fail closed** — empty host and the bare `except` both grant
   local today (**V37**). Treat an undetectable host as remote. But a silent fail-closed is a
   bricked app: the operator would face a control panel with no Start button and no explanation.
   **The failure must be stated on screen** (**R39**) — "cannot determine whether this is a local
   connection; treating as remote".

Resulting screen flow:

```
local:   (no PIN)  →  role  →  Configure  →  Pre-flight  →  running
remote:  PIN       →  role  →      ✗      →   waiting    →  running
```

**A remote device that arrives before Start needs a waiting state** (**R35**) — the speaker
routinely connects before the staff officer starts capture. Today the question never arises
because `app.py:27` auto-starts; removing that auto-start creates this state.

### Where the work goes

**V20** makes this far smaller than it looks — deferring one import is sufficient.

| File | Change |
|---|---|
| `src/bootstrap.py` (new) | Zero project imports — stdlib plus `dotenv` only. Reads and writes `.env` atomically (**V46**), resolves the storage root and derives the fixed layout beneath it (**R48**), sets `os.environ["HF_HOME"]` *before* anything heavy loads, reports what already exists under the root, owns the readiness state machine and download-progress surface for **R23**. |
| `.env.example` | **Regenerate to match the persisted inventory** — the nine settings keys plus `ARCHIVE_AUDIO`, with `MULTILINGUAL_MODE` removed. `AGENTS.md` makes this obligatory in the same change as the flag, and the template is currently a snapshot of the pre-Phase-7 scheme. |
| `README.md` | **Rewrite the setup section.** It currently instructs the operator to set `MULTILINGUAL_MODE` by hand (lines 105 and 132) and documents a `.env` the operator is no longer allowed to edit (**R18**). The new flow is `setup_mac.sh` → open the page → fill the storage root → the app downloads. `AGENTS.md`'s documentation-sync rule makes this part of the item, not follow-up work. |
| `app.py` | Move `from global_state import ...` out of module scope into a function called only once configuration exists; drop the `app.py:27` auto-start (**V18**); add Configure, the `is_local` gate, the waiting state, Pre-flight shell, and Start gating. |
| `transcriber.py` | **Untouched** by this item. |
| `local_advisor.py` | **Untouched** by this item (advisor backends change it later). |
| `global_state.py` | **Untouched**, until `ENABLE_LOCAL_RAG` becomes a UI toggle — lands with the advisor-backend item. |

Implementation ordering note: checking whether weights already exist is most reliably done via
`huggingface_hub`'s cache API, but importing it fixes `HF_HOME` (**V19**). So `bootstrap.py` must
set the path *first*, then import to inspect. Internal to that one file, but easy to get backwards.

Also decide, in code review of this item, how `@st.cache_resource` on `get_global_state` is
invalidated when Configure rewrites `.env` — today's singleton is created once per process and
reads the environment in `_init_once`. Without an explicit rebuild path, saving a new storage root
appears to work and then keeps using the old one.

### Readiness state machine

```
no-config → downloading → warming → ready
```

Start is `disabled` until `ready` (**R24**), which also satisfies **R25**: capture cannot begin
early because the control that begins it is not pressable. Changing the ASR model returns the
machine to `warming` (**V33**) — expected, and the UI says why.

Warm-up begins when configuration becomes complete (storage root saved, weights present or
finished downloading) — **not** on every Streamlit rerun while the operator is still typing, and
**not** deferred until Start (see departures below).

### The pre-flight panel

Once `ready`, the operator sees one screen holding **every per-meeting decision** (**R27**), so
later items do not each grow their own UI. **The controls, their defaults and their enablement
rules are specified in [REQUIREMENTS.md](REQUIREMENTS.md).** This item ships the panel shell,
Start/Stop, level meters (already `st.progress(rms)`), the sticky retention toggle's *disclosure*
(**R46** — wiring the writer is a later item), and disabled/placeholder advisor rows until the
advisor-backend item fills them. Microphone dropdown and active-backend indicator are filled by
the items that follow — the panel must exist first.

Two consequences worth carrying in the plan:

- **The RAG row is a status, not a checkbox.** Chunk count and build date show whether the defence can
  fire at all, armed or not — an invisible precondition (**V34**) made visible while the operator can
  still act on it (**R36**, **R40**). Until the Qdrant migration lands, read those facts from the
  pickle (or show "index missing") rather than inventing a second source of truth.
- **Pressing Start commits everything and opens the streams.** Choices are fixed for the session;
  changing one means stopping and starting again. That is what lets stream setup and the audio writer
  be configured exactly once instead of being mutable mid-capture.

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
| `STORAGE_ROOT` / derived `HF_HOME` | once per machine | `.env`, written by the app (**R48**) |
| `AUDIO_ARCHIVE_DIR` | once per machine, optional | `.env`, written by the app (**R44**) |
| Advisor hosts, credentials, model names | once per machine | `.env`, written by the app (**R32**) |
| `ASR_MODEL` | once per machine | `.env`; changing it re-warms (**V33**) |
| `ENABLE_LOCAL_RAG` and the LLM toggle | per session | pre-flight panel |
| audio backend | capability, not preference | auto-detected (process-tap item) |
| `ARCHIVE_AUDIO` | **sticky per machine** | pre-flight toggle that writes itself back to `.env` (**R16, R46**) |
| microphone | per meeting, enumerable | pre-flight dropdown, not persisted (**R33**) |
| `MULTILINGUAL_MODE` | — | **deleted** (ASR bake-off item) |
| `PIP_CACHE_DIR` | during `pip install` only | `setup_mac.sh`, which already exports it |

## 7.2 — ASR bake-off, then a default

Satisfies **R8, R10, R11, R37**. Addresses **V1, V2, V3**; candidates and their traps are **V4, V5,
V38–V44**.

This item previously named a winner before the field had been examined. **V38–V44**, read on
2026-08-10, changed the picture: a stronger candidate exists (**V39**), it brings a capability the
plan never considered (**V40**), and it brings a specific regression against **R37** (**V41**).
**R11** asks for a deliberate choice, so this item measures rather than asserts.

| Candidate | Why it is here | Why it might lose |
|---|---|---|
| `whisper-large-v3-turbo` | Incumbent path, `mlx_whisper` already wired in, has `no_speech_threshold` | Weaker accuracy; script not guaranteed (**V5**) |
| Qwen3-ASR 1.7B (MLX) | Better on every published number; trained-in context biasing (**V39, V40**) | No no-speech gate and transcribes music (**V41**); community port (**V44**) |
| Qwen3-ASR 0.6B (MLX) | Faster again, which matters under a shared `NPU_LOCK` | Accuracy cost |

Measure in this order. **The first one decides; it is not a tie-breaker:**

1. **False-trigger rate on non-speech** (**R37**) — music, notification chimes and keyboard noise,
   counting how many lines reach the buffer as `Participant`. No published benchmark covers this, and
   it is the failure that fires a cue at the worst possible moment.
2. **Code-switching** on real bilingual audio (**R8**), and which script the Chinese arrives in
   (**R10**, **V42**).
3. **Latency with both tracks running**, since the two instances share `NPU_LOCK`. Confirm
   `audio_queue` does not resume dropping frames — that regression was only fixed in `201eeea`.
4. **Whether context biasing earns its place** (**V40**) — the same terms, with and without.

Then, and only then:

1. Write the winner in as the default and record the measurements as new constraints.
2. **Delete `MULTILINGUAL_MODE`.** Every candidate is multilingual unconditionally, so the ASR half of
   the flag has no meaning; the embedding half becomes a `build_index.py` argument recorded in the
   index. The runtime environment variable disappears entirely.
3. **Rebuild the anti-hallucination defence for whichever model wins.** Whisper's ghost strings and an
   LLM-based model's repetition loops are different failures, so the blacklist at
   `transcriber.py:163` cannot simply carry over. If the winner has no `no_speech_threshold`
   equivalent (**V41**), **R37** has to be met upstream — stricter VAD, or an energy/duration gate
   ahead of `inference_queue`.

**Blocked on something this repo does not have: audio fixtures.** `history/` holds real meetings and
is off limits, so the test material has to be recorded deliberately for the purpose. That recording is
the first task of this item, not an afterthought.

**Provisional until the 48 kHz path lands.** Today's `transcriber.py` opens streams at 16 kHz.
Retention and the process tap make 48 kHz + software resample mandatory (**V12**, **V7**, decided
in `docs/decisions/0001-audio-archive-sample-rate.md`). A winner chosen only on the 16 kHz path is
allowed as a *default to wire in*, but **R37** false-trigger rate and dual-track latency must be
re-measured on the production resample path before the bake-off is closed — otherwise the numbers
describe a pipeline the product is about to abandon.

Already favourable: code-switching needs no architectural change, because each VAD segment is a
separate call with no language argument, so language is auto-detected per chunk. Intra-*sentence*
code-switching stays weak in every candidate.

No OpenCC in the live path regardless of winner — see *Decided and closed*.

## 7.3 — Microphone selection in the web UI

Satisfies **R26**. Settled by **V13, V14**: this remote-controls the *host Mac's* devices; it is
not a browser device picker. **Depends on the Pre-flight panel from the configuration item** —
without that panel there is nowhere shippable to put the control, so this is not independently
shippable ahead of Configure/Pre-flight.

Scope shrinks because of **R1**: if system audio is "everything", there is no source to choose.
So this contributes a **microphone dropdown** and leaves the read-only **active backend indicator**
to the process-tap item. Both live on the pre-flight panel (**R27**).

The `st.progress(rms)` level meters already in `app.py` are exactly the meter Zoom shows beside
its device picker, so the familiar UX needs no new visual work — and they are the existing
example of **R36**, a component that shows it is alive while producing nothing.

Trap: `Transcriber.__init__` preloads the model into the NPU (**V33**). Switching devices must
**not** naively reconstruct a `Transcriber` — separate "change device" from "reload model".

Bonus: a dropdown makes the hardcoded microphone-keyword bug (Known Issues) irrelevant.

## 7.4 — Core Audio process tap, then make it the default

Satisfies **R1, R2, R5, R6, R7**. Built on **V6–V11**; **V12** is the first unknown to hit and is
**load-bearing** once 48 kHz archival is required.

1. **Measure V12 on this machine before writing production code that assumes an answer.** Open a
   PortAudio stream on a 48 kHz-only source (or the tap) at 16 kHz and at 48 kHz; record whether
   the library resamples, which rate actually arrives in the callback, and whether `webrtcvad`
   accepts the chosen rate for the block size in use. Until that measurement exists, the resample
   design is a guess.
2. Add `src/native/aegis_tap.m` — a global mono mixdown tap, compiled by `setup_mac.sh`.
3. `global_state.py` launches it as a subprocess on start, SIGTERMs it on stop. **Microphone and
   system-audio tracks stay separate all the way through** (**R2**) — the tap replaces BlackHole
   as the *Participant* source; it must not be mixed into the mic track.
4. **Auto-detect rather than configure**: use the tap when the OS supports it and the device
   appears, otherwise BlackHole. Surface which is active on the pre-flight panel — this is a
   capability, not a preference (**R7**).

   ⚠️ **The obvious implementation is circular.** The tap's aggregate device exists only while the
   helper process runs (**V9**), and the helper must not run before Start, because creating a tap
   *is* capture (**R25**). But the pre-flight panel has to show the active backend **before** Start.
   So the indicator cannot be derived from device enumeration. Derive it from **capability** instead
   — OS version ≥ 14.2 (**V6**), helper binary present and executable — and treat a helper that then
   fails to produce its device at Start as a **runtime failure with a visible message** (**R39**),
   falling back to BlackHole for that session rather than silently capturing nothing.

   The same circularity applies to the microphone dropdown: it enumerates real input devices before
   Start, so the tap device will never be among them. That is correct, not a bug — the tap is the
   *Participant* source and is never operator-selectable (**R1**, **R5**).
5. Prove it in real meetings, **then** make the tap the default (**R7**).
6. Keep the BlackHole fallback permanently for macOS older than 14.2 (**R6**).

Largest ongoing cost: the aggregate device binds a specific output device as its main
sub-device, so it goes stale when the operator switches output. Needs a
`kAudioHardwarePropertyDefaultOutputDevice` listener to rebuild. BlackHole does not have this
problem — the only respect in which it is superior.

After the 48 kHz callback path exists, finish the bake-off's deferred re-measurement (**R37**,
dual-track latency) before calling the ASR default final.

## 7.5 — Pluggable advisor backends (RAG via Qdrant, LLM via OpenAI-compatible)

Satisfies **R28–R31, R36, R42**. Built on **V22–V36**, **V48**.

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
- **The prompt lives in source, not in the settings form.** It encodes a safety boundary rather than a
  preference, and **R31** caps per-backend configuration at a host and a credential. Making it
  editable would let the clause that permits returning nothing be deleted, which is the one edit that
  turns the advisor into a flooder — see *Decided and closed*. Domain vocabulary belongs in the
  knowledge base, which is where **V40**'s context biasing would draw from anyway.

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
4. **Label by vendor, and mark generated content unverified** (**R29, R30, R42**). `🛡️ [Aegis
   Triggered]` and `⚡ [STAFF OVERRIDE]` exist; a third label needs to be visually distinct. This
   is a safety boundary, not decoration — a hallucinated figure read aloud at an interpellation is
   worse than no cue, and **R42** is why the distinction has to survive a glance rather than a read.
5. **Surface liveness** (**R36, R42**, **V34**, **V35**). Two places:
   - *Pre-flight*: the RAG row shows chunk count and build date, so an unbuilt or empty index is
     caught before the meeting rather than during it.
   - *Running*: show the most recent similarity score when RAG is in play. `local_advisor.py:84`
     already computes and logs it unconditionally, so this is close to free — and it is what makes
     `RAG 0.31` ("alive, nothing matched") distinguishable from no score at all ("dead").
   - *LLM-only*: there is no score. **R36** still applies — ship an explicit liveness signal
     (last request latency / "waiting" / "error" / "returned empty") rather than a blank advisor
     pane that looks like "nothing matched".

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

Resolve by measurement during this item, not before it.

## 7.6 — Optional dual-track audio retention

Satisfies **R16, R44, R45, R46**; bounded by **R4**; warned about per **R41**; constrained by
**V12, V48**. Claims on **R3** wait for open decision 1 — this item builds the archive path
**R3** would need, but must not pretend default-off retention already satisfies it.

A **toggle on the pre-flight panel** (**R27**) that **persists its own state** — off until the
operator first enables it, then sticky on that machine (**R16**). Off initially on disk-space grounds
and because recording carries consent expectations the system should not assume, which is why turning
it on warns with a size estimate rather than silently starting to fill a disk (**R41**). Sticky rather
than per-meeting because a default of off means the one meeting that later turns out to matter is the
one nobody armed; and because it is sticky, the panel shows its current state before every Start
(**R46**) rather than only at the moment it was chosen.

**The toggle is always available once a storage root exists** (**R48**) — the archive path is
derived, so retention cannot be "unconfigured". An optional `AUDIO_ARCHIVE_DIR` override relocates
files; it does not gate the switch. (An earlier draft of this item contradicted that and is wrong.)

Two things follow from **R45**, and both are cheap only if done now:

- **The session record states whether audio was kept, and where.** Decision 0001 already requires the
  precise session start time in that header; retention status and archive path go beside it. Without
  them, "recorded and later deleted" is indistinguishable from "never recorded" — and **R4** makes
  deletion a normal event, not an anomaly.
- **The transcript is a lossy interpretation (**V48**), and the plan should stop implying otherwise.**
  With retention off, whatever VAD and the no-speech filters discarded is gone. That is a real tension
  with **R3** in the default configuration — recorded as an open decision below rather than papered
  over by rewording **R3**.

Because the choice is known before the streams open, the writer thread is configured once at
Start rather than having to be attachable to a running capture.

Constraints, ordered by how easily each silently ruins the feature:

- **Write from the raw stream, upstream of VAD.** `_processing_thread` discards whatever VAD
  calls non-speech, so archiving downstream would lose precisely the **VAD misjudgements** —
  exactly the material worth going back to verify. **R3** only holds for the archive if the tap
  point is the continuous callback stream.
- **Separate files per track; never mix** (**R2**). Mixing destroys the role attribution this
  architecture gets for free, and which comparable products only obtain because the OS forces
  the same split on them (**V16**).
- **Do not block the audio callback.** Disk writes go through a queue and a writer thread, the
  same pattern already used for `inference_queue`. A load-bearing invariant, not a preference.
- **Lossless only** — lossy undermines evidentiary value. Python's stdlib `wave` module needs
  **no new dependency**; FLAC is a later size optimization.
- **Pair filenames with the transcript** — `Meeting_<session_id>_mic.wav` and `_system.wav`, named
  from the same `session_id` as `history/Meeting_<session_id>.md`, so the cleanup script can find them
  without guessing. They live in the configured archive directory rather than beside the transcript
  (**R44**), so that script resolves the pair by `session_id` plus one configured path — not by
  assuming a sibling file.
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
couples this item to the process-tap work. `transcriber.py:46` currently hardcodes
`sample_rate = 16000`, and the plan asserts `webrtcvad` accepts 48000 — **confirm in the V12
measurement**, do not discover it mid-hearing. The change is confined to stream setup plus one
resample step before `inference_queue`.

## 7.7 — Post-meeting cleanup script

Satisfies **R9, R10, R12, R13, R14, R15**. Uses the retention filename contract when audio exists.

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
- **If retained audio is present**, resolve
  `Meeting_<session_id>_{mic,system}.wav` via `session_id` + archive directory (**R44**, **R45**)
  and tell the operator the paths — the script may still be text-only for v1, but it must not
  invent a sibling-file layout the retention item does not use. This is why cleanup ships *after*
  retention's naming contract, not before.

---

## 🧪 Verification — what gets a test, and what cannot

The plan adds a lot of logic that is pure and cheap to test, and the repo currently has eight tests
across two files. Naming the testable surface here stops it from being decided by whoever is tired
at the end of an item.

Tests build their own fixtures with `tmp_path` and never read `context/`, `history/` or `logs/` —
`AGENTS.md` makes that a hard rule, and it is also why none of the below needs a real meeting.

| Surface | Cases that matter |
|---|---|
| `bootstrap` — `.env` round-trip | Write the form, read it back, get identical values including empty strings and credentials containing `=` and `#`. A blank field must survive as blank, not as the string `"None"` (**R32**) |
| `bootstrap` — atomic write (**V46**) | Simulate a failure between temp-write and replace; the original `.env` must still be intact and parseable |
| `bootstrap` — path derivation (**R48**) | One storage root produces `<root>/AegisPrompter/{models,audio}`; trailing slashes, `~`, and a relative path all normalise identically, because "the same root re-entered" must mean byte-identical derived paths |
| `bootstrap` — absent configuration (**R20**) | No `.env`, empty `.env`, and `.env` missing the required key each yield a blank form, never an exception |
| `is_local` (**V37**) | Table-driven over the `Host` header: `localhost`, `127.0.0.1`, a LAN IP, **empty**, and a raising header accessor. Only the first two may return local — the empty and raising cases are today's fail-open bugs |
| Advisor factory (**R28**) | Neither slot / RAG only / LLM only / both configured each select the documented behaviour |
| Three-band routing (**V22**, **V23**) | Scores `0.449`, `0.45`, `0.649`, `0.65`, `0.651` — the two band edges are the whole logic, and an off-by-one comparison here either floods the speaker or silently disables the LLM band |
| Retention naming (**R44**, **R45**) | `session_id` plus an archive directory resolves the `_mic`/`_system` pair; the session header records retention status and path |

**What unit tests cannot cover, so nobody should pretend otherwise:** NPU warm-up and its
serialization under `NPU_LOCK`, real device enumeration, the Core Audio tap, whether PortAudio
resamples (**V12**), whether a native folder dialog blocks Streamlit's rerun (**V45**), and the
false-trigger rate on non-speech (**R37**). Those are measurements on hardware, and each is already
named as such in the item that needs it. A mocked test asserting one of them would be worse than no
test, because it would report green about something never exercised.

---

## 🔓 Open decisions

Resolve before the cited work is implemented. These are blockers, not polish.

1. **How does R3 coexist with default-off retention?** **R3** says completeness of capture is the
   system's job; **R16** leaves archival off until the operator arms it; **V48** shows the live
   transcript path already discards material. Either the stance means "do not drop frames on the
   live dual-track path" (and archival completeness is opt-in under **R4**/**R16**), or default-off
   retention is the wrong default. **Do not quietly rewrite R3 to match the plan** — pick one and
   record it. Blocks closing the retention item as "satisfies R3".
2. **LLM-only liveness under R36.** When RAG is off there is no cosine score (**V35** does not
   apply). What signal distinguishes "LLM returned nothing on purpose", "call in flight", and
   "backend dead"? Blocks the advisor-backend item's LLM-only configuration.
3. **Advisor band edge `0.45`.** No measurement backs it (see advisor-backend item). Leave as a
   constant until measured, or measure before exposing. Wrong value floods the speaker or silently
   disables the LLM band.
4. **Qwen3-ASR supply chain (**V44**).** Community MLX reimplementation, single maintainer, product
   premise is offline forever. Accept the risk, vendor-pin a commit hash + wheel mirror, or
   disqualify on supply-chain grounds even if it wins the bake-off numbers.

---

## 🐛 Known Issues

- **The RAG advisor fails silently when the index is missing or stale** — see **V34**. The toggle
  reads as armed and nothing will ever fire, with no signal in the UI. This is the failure this
  product can least afford: it is discovered at the moment the defence was needed. Fixed by the
  advisor-backend item's liveness work (**R36**).
- **`HF_HOME` in `.env` has never taken effect** — see **V19**. Fixed by the configuration item.
  Confirm afterwards by checking where weights actually land on a fresh run.
- **Capture starts before authentication** — see **V18**. Fixed by the configuration item.
- **`is_local` fails open** — see **V37** (empty host *and* bare `except`). Harmless while it only
  skips a PIN prompt; not harmless once it gates credentials. Fixed by the configuration item,
  which must also make the failure visible (**R39**).
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
  **V48** is the precise discard list; **R37** ranks stopping false lines above raw WER.
- **`MULTILINGUAL_MODE` is misleadingly named** — see **V2, V3**. Deleted by the ASR bake-off.
- `global_state.py` looks for `["MacBook Air Microphone", "Built-in Microphone"]`. On a MacBook
  Pro neither matches, so microphone selection silently relies on `fallback_to_default`. The
  result is usually correct, but the keyword list is not doing its job. Superseded by the
  microphone-selection item.
- Capturing the far end currently requires the BlackHole driver *plus* a manually configured
  Multi-Output Device, or the operator cannot hear the meeting while it is captured. Superseded
  by the process-tap item.
- **`V12` is still unverified and is now on the critical path** for both the process tap and
  retention. Building either against an assumed resample behaviour is how hearings lose audio.
- **`V45` folder chooser untested.** Configure cannot promise a native picker until a Streamlit
  callback has actually raised one without deadlocking the rerun.
- **`.env.example` is pre-Phase-7** — still documents `MULTILINGUAL_MODE` and project-local
  `HF_HOME=./.hf_cache`, which contradicts **R48** and **V19**. Regenerated with the configuration
  item; until then the template teaches the broken layout.
- **`README.md` teaches a workflow the plan removes** — hand-editing `.env` and setting
  `MULTILINGUAL_MODE` (lines 105, 132), both contradicting **R18**. It is also the only document a
  new operator reads, so it is the most expensive one to leave stale. Rewritten with the
  configuration item.
