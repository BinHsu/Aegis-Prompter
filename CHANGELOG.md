# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Changed
- **Up to three pre-written cues instead of one.** The knowledge lookup always ranked every note and
  the app only ever showed the first, which threw away most of what it had found: measured, the right
  note is in the top three far more often than it is first. Now up to three appear, strongest first,
  each with its match score, and only if each one clears the bar on its own — nothing is padded in to
  fill the space. In practice it usually still shows one: across sixty questions against twenty notes,
  two thirds of the time a single cue appeared. Costs nothing in speed; the lookup takes about five
  milliseconds either way. See `docs/decisions/0016`.
- **Pre-written cues now actually appear.** The similarity score a retrieved note has to clear before
  it is shown moved from 0.65 to 0.45. At 0.65, measured against real embeddings, **not one
  paraphrased question ever cleared it** — five rephrasings of indexed notes scored 0.37 to 0.63 —
  so the retrieval pane stayed blank in exactly the situation it exists for, and nothing on screen
  could tell you the difference between "nothing matched" and "the bar is above everything". At 0.45
  four of those five appear and none of five unrelated remarks do. Costs nothing: the lookup already
  ran on every line; the number only decided whether you saw the result. See
  `docs/decisions/0014`.

- **The generated-answer slot ships off, deliberately.** It works — point `LLM_BASE_URL` at a local
  model and it produces answers — but measured, it answered about half the questions it could,
  invented a figure on a few percent of the ones it could not, and **doubled the time the transcript
  itself took to appear**, because the language model and speech recognition share one accelerator.
  A slot that halves the speed of the thing you are reading from a podium is not worth that. Nothing
  was deleted: type a URL into settings and it comes back.

### Added
- **Re-listen a kept meeting, and optionally tell the voices apart.** One button re-runs speech
  recognition over the retained audio with a longer silence flush, so sentences arrive whole
  instead of cut at every pause, and the material voice detection discarded gets read again — the
  archive is written before detection runs, so it is still there. It aligns the two tracks on each
  one's own recorded first frame rather than assuming they started together.

  Optionally it also separates the far side **by voice**: lines that share a speaker get `與會者1`,
  `與會者2` — from sound alone, never names. Who those people are is a **guessed table at the end,
  with the evidence and a timestamp beside each row**, and this app never applies it. You check it
  and do the replacement yourself, which means a wrong guess is visible before it is written
  anywhere and an imperfect separation stays recoverable.

  **That part installs itself only when you first ask for it**, and states the cost first: 47
  packages, a gated model needing a Hugging Face token, and a telemetry framework plus a cloud SDK
  that `pyannote-audio` requires. Neither transmits anything unconfigured — but if you never press
  it, none of them is in the process at all, and the offline guarantee stays checkable by reading
  the dependency list.
- **Every transcript now ends with its own post-meeting prompt**, and the application does no
  post-processing itself. After a stable marker line, each session file carries an instruction
  asking for three things — a report, the meeting's topics, and a proofread transcript — and
  telling the agent what it could not otherwise know: the line format, that the two roles are two
  separate audio tracks that were never mixed, that sentences get cut at 0.4 s pauses, that
  non-speech occasionally becomes a plausible short sentence, that individual speakers were never
  separated so it must not invent names, and where the retained audio is if you kept any.

  Copy it into whatever agent you use, or lift it out with one `sed`. Nothing is executed, no model
  is loaded and nothing is downloaded — which is why it needs no toggle, no warning and no
  dependency.

  This replaces a version shipped earlier the same day that ran a local 3B model or an external
  command at Stop, with Stop blocking until it finished. That approach borrowed its timing
  argument from audio retention, where it is right because unrecorded audio is gone — but a
  transcript on disk does not expire, so pre-arming bought nothing. `mlx-lm`, the 1.7 GB model
  download and the `CLEANUP_COMMAND` setting are all gone with it.
- **Dual-track audio retention actually records now.** The toggle has persisted a preference since
  the configuration work while writing nothing; it writes two WAV files per session — 16 kHz mono,
  lossless, one per track, never mixed — into the archive directory derived from your storage root,
  named `Meeting_<session id>_mic.wav` and `_system.wav` so they pair with the transcript in
  `history/` by session id alone.

  Four details that decide whether a kept recording is worth keeping. It is tapped from the **raw
  audio callback, upstream of voice detection**, so what the transcript threw away is still on disk
  — that material is the whole reason to keep audio. The file is **finalised before shutdown waits
  on anything slow**, so a WAV header always carries its final length rather than being truncated by
  an impatient second Ctrl+C. Blocks the writer cannot keep up with are **counted and reported** in
  the session record, because a file that is 40 minutes of a 60-minute hearing is worse than no file
  if nothing says so. And each track records the wall-clock instant of **its own** first frame — the
  two streams do not start together, and only that converts a transcript timestamp into an offset
  into the audio.
- **The session record now states whether audio was kept, and where.** Written into the header at
  Start, so it survives a session that ends badly: without it, "recorded and later deleted" and
  "never recorded" are the same file. The header also carries the session start to the millisecond,
  and a closing section reports what each track actually produced.
- **The knowledge index moved to Qdrant**, which is what `QDRANT_URL` and `QDRANT_API_KEY` on the
  settings form were always for — they had no effect until now. Leave them empty and the collection
  is an embedded database under `context/qdrant/`: no server, no network, nothing leaves the
  machine. Fill them in and the same client talks to a remote host, which is what lets "a host and
  a credential" be the whole of the configuration. Embedding always happens locally either way —
  Qdrant Cloud Inference would send the raw utterance rather than a vector of it, and that is not a
  decision this app makes on your behalf.

  Two failures are guarded because both are otherwise **silent**: the collection's distance metric
  is pinned to `COSINE` at creation and verified at every read (the match threshold *is* a cosine
  similarity; under any other metric it means nothing and nothing raises), and the embedding
  model's name is stored in the collection and used to load the query-side model — so an index
  built with one model can never be queried with another. If your `EMBEDDING_MODEL` setting later
  disagrees with the index, the pre-flight panel says so instead of quietly resolving it.

  The old `context/knowledge_index.pkl` is no longer read. It is left where it is — it is your
  data — and the panel tells you to rebuild rather than reporting that no index was ever built.
  Rebuild with the app stopped: the local collection takes an exclusive lock, held for the length
  of a meeting rather than the life of the process.
- **A second advisor slot: any OpenAI-compatible endpoint.** Retrieval and generation are now two
  independent slots — fill neither, either, or both. The generative row stays hidden until an LLM
  base URL is configured, is off by default when it appears, and warns as it is armed. A **Test the
  LLM endpoint** button sends one fixed word — never meeting content — so an unreachable host is
  found before the meeting rather than during it. The transport is stdlib HTTP against
  `{base}/v1/chat/completions`, which covers Ollama, LM Studio, vLLM, llama.cpp and every cloud
  provider; no vendor SDK is added and no new dependency is introduced.
- **The two advisors do not gate each other.** Every line the room says goes to whichever slots you
  armed. Retrieval keeps its own 0.65 threshold — that answers "is this chunk about the question at
  all", and showing an unrelated pre-written answer is worse than showing nothing — and the
  generative slot has no numeric gate at all: the system prompt is the threshold, and it explicitly
  permits returning nothing, which is the clause without which a generative advisor floods. Both
  results appear, each labelled with what produced it, and you decide.
- **A liveness line under the advisor pane.** `RAG 0.31` means the index is alive and nothing
  matched; a named error means it never loaded; `LLM declined` and `LLM error — connection refused`
  are now different sentences. Silence and failure used to render as the same blank pane.

### Changed
- **Speech recognition now runs on `mlx-community/whisper-large-v3-turbo`, and the reason is where
  the weights come from rather than how they score.** The previous default was Alibaba's
  `Qwen/Qwen3-ASR-0.6B`, loaded through a community MLX port maintained from the same region. For a
  product built for hearings and earnings calls in Taiwan, that is a procurement question before it
  is a technical one, and nothing in the bake-off harness measures it. Provenance is now a written
  requirement that **outranks measurement** — it disqualifies whatever wins the table — and every
  other model and package was surveyed against it: embeddings from UKP Lab in Germany, optional
  speaker separation from pyannote in France, the accelerator and the Whisper loader from Apple,
  Whisper itself from OpenAI. The one row this project cannot close is the generative advisor,
  which is any endpoint you supply; the README says so instead of implying the survey covers it.

  **This costs something, and it is written down rather than softened.** The model removed was
  better on both axes that were measured: silent on 63 of 63 synthesized non-speech clips where
  this one produces text on all 63, and roughly 2.5× more accurate on sentences that switch
  between Mandarin and English. Neither model was ever silent on *real* non-speech — laughter,
  coughing and room tone were already producing invented sentences — so this is a change in degree
  on a problem that existed, not a new one. The live view was always scoped to the gist, and the
  post-meeting pass is still where a person reads the transcript before anyone acts on it.

  **What is different in your hands:** nothing to do. The model id is a settings field with a new
  default; an existing `.env` keeps whatever it holds, and the field now says what shape of
  repository will actually load, because the Hub's own tags do not distinguish the format that
  works from the one that does not. Pressing Start downloads about 1.5 GB once if you have not got
  it.

  `mlx-qwen3-asr` is out of the dependency list. The bake-off can still score that family behind
  an explicit flag that prints why it is disqualified — reproducing the old comparison must not
  require reinstalling it, and must not happen by accident either.
- **Retrieved and generated advice no longer share one slot.** A remote reply arriving seconds after
  a local one used to overwrite it: the speaker read a safe pre-written answer and had it swapped for
  generated text mid-glance. Each kind now holds its own slot and its own card — staff override,
  retrieved, generated, in that fixed order — and generated text carries the word **UNVERIFIED** on
  the card itself, in the archived transcript as well as on screen. The three are told apart by
  colour and accent, not by a label you have to stop and read.
- **An operator-requested model download can reach the network again.** The app goes offline
  before warm-up and enforces it by rewriting the flag inside `huggingface_hub` itself, which is
  what makes the promise real — and which silently killed every later download, including the one
  behind the cleanup panel's own Fetch button. A fetch you explicitly ask for now opens a window
  exactly one call wide and closes it again. Nothing else changed: the app still never reaches out
  on its own.
- **The retention warning stopped overstating disk by 3x.** It said 0.69 GB per hour across both
  tracks, which was the 48 kHz figure and outlived the reversal to 16 kHz. It is 0.23 GB.
- **The remote call runs off the poll loop.** It has its own thread, an 8-second timeout and a
  one-slot mailbox: a newer utterance replaces a queued one rather than being dropped or queued
  behind it, because advice about a line the room has moved past is worse than none. The loop that
  notices Stop no longer blocks on a host that is not answering.
- **Setup no longer installs BlackHole, and no longer asks for your password.** `setup_mac.sh` used
  to run `brew reinstall --cask blackhole-2ch` followed by `sudo killall coreaudiod` on every install
  where the driver was missing — a privileged write and a restart of the machine's audio service,
  which interrupts sound for every other application, for a component the Core Audio process tap
  replaced. System audio now works with no driver, no password and no change to your output device.
  BlackHole is still supported where it is genuinely needed — macOS older than 14.2, or a machine
  where the tap fails to build — and setup prints the one command to install it there.
- **Lab WAV feeds now pace against a deadline instead of sleeping a fixed amount per frame.** The old
  loop slept 30 ms per 30 ms frame and did the per-frame work on top, so a feed labelled "realtime"
  ran at **0.888x** of real time and never caught up — which is exactly where an hour-long
  measurement sat before being misdiagnosed as CPU starvation. Figures measured through the old feed
  are not wrong, but they were taken at ~0.89x of the pace they reported. A feed that falls more than
  a second behind now resyncs and logs that it did, rather than sprinting to catch up and silently
  saturating the pipeline it was supposed to be pacing.
- **The speech-recognition model is now `Qwen/Qwen3-ASR-0.6B`**, replacing
  `mlx-community/distil-whisper-large-v3`, which had been the default since Phase 6 and was never
  chosen by anyone. Measured on 80 clips of real Mandarin-English conversation, distil emitted
  **more wrong characters than the reference contains** (CER 2.72 on Chinese) — it is English-only
  by design. The decisive number was elsewhere: on 63 non-speech segments both Whisper candidates
  produced text on **all 63**, and both Qwen sizes on **none**. (Those 63 were synthesized; on real
  non-speech the winner is 23/253, not zero — measured after the choice and recorded as `V60`. The
  comparison stands; the absolute does not.) Full comparison and the rejection of
  the larger 1.7B are in `docs/decisions/0009`. `mlx-qwen3-asr` becomes a pinned dependency
  (`docs/decisions/0008` has the recovery path if it ever becomes unobtainable).
- **Retained audio is archived at 16 kHz, not 48 kHz**, reversing `docs/decisions/0001`. A higher
  rate cannot improve transcription — every ASR in sight consumes 16 kHz — and keeping both rates
  required a downsampling step that was never built: feeding 48 kHz straight to the model took
  **3426 ms against 660 ms**, because it reads the audio as three times longer. Disk falls from
  2.1 GB to 690 MB for a three-hour hearing. What this gives up is acoustic detail for non-ASR
  uses, and that is stated in the record.
- **`R3` no longer promises completeness of capture.** It promised something the default
  configuration contradicted: the live path discards non-speech frames, sub-0.3 s segments and
  empty output every session, and with retention off none of it is recoverable. It now says the
  system does not discard on its own initiative, and offers retention as the means to keep what the
  transcript cannot — a decision the operator makes rather than a guarantee made for them.
- **The product runtime moved to Python 3.12.** macOS ships 3.9, which reached end of life in
  October 2025 and caps `mlx` below the version its own dependencies now require. Rebuilding the
  venv on Homebrew `python@3.12` (`mlx` 0.29.3 → 0.32.0) **more than halved inference latency**,
  ~1380 ms → ~600 ms per call, with no code and no model change. `setup_mac.sh` now selects the
  newest interpreter ≥ 3.10 and refuses to build on an older one; an existing venv below 3.10 is
  moved aside rather than kept.
- `requirements.txt` pins `webrtcvad-wheels` instead of `webrtcvad`. The original imports
  `pkg_resources`, which `setuptools` ≥ 81 no longer ships, so it fails at import on any current
  environment.

### Fixed
- **The hour-long capture soak could report a fully successful run while measuring nothing.**
  `tools/soak_capture.py --microphone` refused the `--mute` flag but never asked whether the machine
  was *already* muted, and a muted run looks healthy from every angle it reports: the system-audio
  tap reads the mix before device volume, so it transcribes perfectly while the speakers emit
  silence and the microphone — the device the run exists to exercise — hears an empty room. It now
  exits before starting. The liveness signal could not catch this either: microphone RMS read
  0.0031–0.0070 muted against 0.0033–0.0046 audible over the same three minutes, the audible run
  being the *lower* one, because RMS is dominated by ambient noise between utterances. Per-role
  transcribed-line counts are the discriminator (0 versus 35), and a role at zero now prints a
  failure instead of being omitted from the summary. Long runs are also staged 3 → 10 → 60 minutes,
  so a broken configuration costs three minutes rather than an hour.
- **The transcript ran every turn together and could be broken by its own content.** Turns were
  joined with newlines and rendered as HTML, where a newline collapses to a space — so Participant
  and Speaker appeared as one paragraph. The text was also unescaped, so a line containing `<`
  truncated the box and took the rest of the session out of view. Each turn is now its own block
  with the two tracks tinted apart, and the content is escaped.
- **Connecting a headset silently reset your microphone choice.** The dropdown took its selection
  from the saved preference, which is only written when you press Start — so plugging anything in
  reset it to "system default" without saying so. Your choice now survives devices coming and going,
  and a selected device that disappears is flagged rather than replaced.
- **Warm-up really is offline now.** The previous fix set `HF_HUB_OFFLINE` in the environment, but
  `huggingface_hub` reads it once at import and had already been imported, so it never took effect.
  Measured from a live run: one request to huggingface.co before, zero after.
- **The system-audio device could be published and never seen.** PortAudio caches its device
  table, and re-reading it immediately after the tap is published missed the device in 5 runs out
  of 5 — while every log line reported success. A session would have captured only your own voice
  with nothing to indicate it. The app now waits for the device to appear and refuses to continue
  if it never does. The same cache is re-read after teardown, so the next session cannot open a
  stream on a device that no longer exists.
- **The Speaker track was recorded through whichever headset paired last.** Device detection
  matched the literal strings `MacBook Air Microphone` and `Built-in Microphone`; on a MacBook Pro
  neither matches, so it fell through to the system default. On the development machine that was a
  Bluetooth headset. Resolution is now the operator's stored preference, or the system default when
  they have expressed none — both by name, and both visible on the panel.
- **A test guarding that nothing heavy is imported before configuration exists was only as strong
  as its filename.** It checked `sys.modules` for `global_state`/`transcriber`, which any earlier
  test file could populate, turning the assertion into a no-op. The fixture now unloads them for
  the duration, so it measures the app run instead of the alphabetical test order.
- **Warm-up no longer contacts the network.** `huggingface_hub` 1.27 issues HTTPS requests to
  huggingface.co during model load even when every file resolves from the local cache. The app
  now enters `HF_HUB_OFFLINE` once its downloads are complete, which is what "zero external
  dependencies, zero telemetry" requires.
- **Three tests were silently skipping.** `pytest.importorskip("global_state")` turned a broken
  audio stack into a green suite; on the 3.12 rebuild it hid `webrtcvad` failing to import
  entirely. The import is now hard.

### Added
- **Every soak now reports how long segments waited in the inference queue, split by whether the
  other track was busy.** The dwell itself is instrumented in the transcriber; the soak reports its
  median, its maximum and the count of non-zero values, because a median of 0 ms is compatible with
  a long tail and the tail is what a speaker notices. Over an hour of two-track capture: 0 ms on
  98.8% of 1385 segments, with 17 exceptions reaching 2037 ms. `tools/analyze_soak_contention.py`
  goes further and asks whether a second track actually slows inference or whether the label merely
  selects slow segments — it controls for segment duration and for transcript density, both of which
  inflate a naive comparison, and it is explicitly superseded once lock wait is timed directly.
- **System audio is captured without BlackHole.** The tap helper is now started when you press
  Start and torn down when you stop — no virtual audio driver to install, no Multi-Output Device to
  build, and your output device is left alone, so you keep hearing the meeting through whatever you
  already chose. Where the tap cannot run (macOS below 14.2, or the helper was not built) the app
  falls back to BlackHole and says which one is active on the pre-flight panel. If neither is
  available it says that too, rather than recording only your own voice in silence.
- **`tools/verify_capture_end_to_end.py`** — runs one real session and reports what each track
  produced. First run 2026-08-12 transcribed 3 of 3 system-audio lines correctly at 640–826 ms.
- **`src/native/aegis_tap.m`** — the system-audio capture helper. A global mono mixdown Core Audio
  process tap, published as an ordinary input device named `Aegis System Audio` and held open until
  the process is signalled. It needs no virtual audio driver and does not take over your output
  device: you keep hearing the meeting through whatever you already chose, which is what BlackHole
  could never do. Built by `setup_mac.sh` with Command Line Tools `clang` — no Xcode — and if it
  cannot be built, setup warns and BlackHole remains the fallback. **Not yet wired into capture**:
  it exists, it is measured working, and the app does not launch it yet.
- **`tools/measure_tap_stream.py`** — measures what actually arrives when PortAudio opens the tap,
  by timing frames rather than trusting the reported sample rate.
- **The microphone is selectable from the pre-flight panel**, defaulting to whatever macOS calls
  the default input. The choice is sticky (`MIC_DEVICE`), persisted when Start is pressed, and
  applied without reloading the model — switching device costs two assignments, not the minutes a
  warm-up takes. Stored as a device *name*: PortAudio's indices shift between runs and machines, so
  a persisted index eventually points at a different microphone with nothing to notice. A stored
  device that is no longer connected is shown as such and warned about rather than silently
  replaced by the default — that substitution would record the room while the panel named a
  headset. The Participant track has no picker and will not get one: system audio is everything by
  design.
- **`src/audio_devices.py`** — input enumeration and name→index resolution, with no ASR dependency,
  so listing devices cannot drag `huggingface_hub` in ahead of the boot sequence.
- **ASR bake-off fixtures and CLI harness** (`fixtures/asr/`, `tools/gen_asr_fixtures.py`,
  `tools/asr_bakeoff.py`, `src/asr_eval.py`). Synthesized nonspeech + bilingual TTS clips feed
  float32 arrays into ASR candidates for **R37** / **R8** / **R10** / latency vs **V51**, without
  BlackHole or the process tap. Optional disposable `.venv-bakeoff` (Python ≥3.10) runs Qwen for
  measurement only; wipe with `rm -rf .venv-bakeoff`. Default `ASR_MODEL` is unchanged until an
  explicit **R11** / **V44** choice.
- **Configuration is done in the browser, and `.env` is its snapshot.** `src/bootstrap.py` (new)
  reads and writes `.env` as an atomic rewrite, derives the whole storage layout from one
  operator-chosen root (`<root>/AegisPrompter/{models,audio}`), reports what already exists
  beneath a root *before* writing to it, and owns the readiness state machine. It imports
  nothing but the standard library and `dotenv`, because it has to set `HF_HOME` before
  `huggingface_hub` freezes it.
- **Five sequential screens** in `src/app.py`: Access → Role → Configure → Pre-flight → Running.
  Configure renders blank on first run and refills afterwards; Pre-flight is where every
  per-meeting choice is made and committed by pressing Start.
- **Model weights download from the UI with visible progress**, after configuration rather than
  before first launch. Re-entering a storage root that already has a cache reuses it.
- **A pre-flight panel**: detected devices, retrieval-index readiness (chunk count and build
  date), the sticky audio-retention toggle, and a Start button that stays disabled until
  warm-up is confirmed complete.
- **A waiting state for remote devices** that connect before capture starts, instead of a blank
  page.
- `src/text_filters.py` — the anti-hallucination filter as pure, dependency-free functions.
- 55 unit tests (8 → 63), including screen-routing tests driven through Streamlit's app-test
  harness that assert nothing heavy is imported before a storage root exists.
- `docs/decisions/0007` — the five places this work departed from its plan, and why.
- `tools/gen_filemap.py` — generates `FILEMAP.md`, a mechanical inventory of the Python
  surface (modules, classes, functions, line numbers) parsed from the AST using only the
  standard library. Supports `--check` for CI or a pre-commit hook.
- `.claude/settings.json` — a `PostToolUse` hook regenerating `FILEMAP.md` whenever an agent
  edits a `.py` file. Together with the `run_tests.sh` and `setup_mac.sh` calls, this means
  the map cannot silently rot the way a hand-maintained architecture table does.

### Changed
- **You no longer create or edit `.env`.** `cp .env.example .env` is gone from the setup path;
  the settings form writes the file and deleting it is how you reset. `.env.example` is now a
  reference copy of what the form persists.
- **`GlobalState.warm_up()` split from `start_recording()`.** Models load as soon as
  configuration exists; opening the audio streams waits for an explicit Start. Whether the
  retrieval advisor is armed became a per-session choice on the panel rather than an `.env` flag.
- **`setup_mac.sh` no longer exports a project-local `HF_HOME` or creates `.hf_cache`.** It never
  had any effect outside that script's own shell, and where weights live is now the operator's
  choice made in the UI.
- `src/build_index.py` takes the embedding model as an argument (`--model`), defaulting to the
  `EMBEDDING_MODEL` setting.
- Restructured the agent-facing docs by purpose. The original `CLAUDE.md` was a Phase 6
  progress tracker, and renaming it to `AGENTS.md` inherited that mismatch:
  - `AGENTS.md` now contains only **boundaries** — hard rules, invariants that break the
    app if violated, and pointers to the generated sources of truth. It no longer carries a
    hand-written architecture table or `file:line` references, which were guaranteed to go
    stale.
  - `STATE.md` (new) holds project progress, roadmap, and known issues.
  - `FILEMAP.md` (generated) answers "does this file/class/function exist, and where?"

### Removed
- **Every entry in the anti-hallucination blacklist.** `HALLUCINATION_PHRASES` is now empty. It was
  built for Whisper's subtitle ghosts. Each string was also a normal thing for a human to say, and
  the filter had no way to tell which was which.
  `I don't know.` is one of the most consequential things a witness says. The list could not be
  tuned safely because we cannot predict what anyone running this records, so it was removed rather
  than trimmed; the guard against single-character output remains. Measured afterwards (`V60`): the
  shipped model *does* still invent lines on laughter and room tone, and **none of the eight deleted
  strings appears among them** — so removing those strings cost nothing, but the live path is not
  clean and the post-meeting cleanup pass is where these lines get removed. If you switch back to a Whisper
  model, read `docs/decisions/0008` first — the ghosts return with nothing behind them.
- **`MULTILINGUAL_MODE`.** It never reached the speech-recognition layer at all, and its only
  real effect — choosing between two embedding models at index-build time — is now the
  `EMBEDDING_MODEL` setting.
- **`ENABLE_LOCAL_RAG`.** Arming the retrieval advisor is a per-meeting decision made on the
  pre-flight panel, not a stored setting.
- **`PIP_CACHE_DIR` from `.env.example`.** `setup_mac.sh` exports it itself; it was never a
  runtime setting.

### Added
- **`tools/measure_asr_latency.py`** and `fixtures/asr/V52_REMEASURE.md` — live protocol to close
  **7.3** / remeasure **V52** (median / p95 / max / %>2000ms; optional RSS/CPU sampling).
- **`tools/gen_v52_prompt_audio.py`** — reusable V52 prompt WAV via macOS TTS (optional teleprompter
  mic record); play while capture runs so 7.3 does not require live reading.
- **`tools/run_v52_remeasure.zsh` / `run_v52_arm.zsh`** — one-shot zsh drivers for the V52 arms.
  Arms set `AEGIS_V52_FEED` so Start injects the prompt WAV into the Speaker pipeline
  in-process (no speaker→mic); browser shows transcript, speakers stay silent.

### Fixed
- **V52 remeasure closed 7.3:** with fragment running view, 3 browser sessions no longer stretch
  the ASR tail (0% of calls >2000 ms at n=30; old full-script poll hit ~29% / max ~5 s).

### Changed
- **Running view polls inside `st.fragment` instead of re-running the whole script** every 0.5 s.
  Staff form and Stop stay outside the fragment. Removes the per-rerun `\r` access-code banner that
  corrupted logs under multi-session polling (**V52**). Formal ASR default choice waits until after
  this cheapening and a latency+resource measurement (`fixtures/asr/FORMAL_MEASURE.md`).
  Fragment is defined only on the running path (not at module import) so Stop → Pre-flight does not
  leave a `run_every` timer that stacked a second **Start capture** on the page. Pre-flight no
  longer uses `sleep`+full `rerun` (that also stacked Start); readiness refreshes in a fragment.
  **Start / Stop** are local **Staff Mode** only (R34 + R35); Speaker Mode follows without Start.

### Fixed
- **Whisper nonspeech ghosts `I don't know.` and `Bye.` reached the buffer.** The bake-off's
  first **R37** run showed both on music/chime/keyboard segments; they are now whole-utterance
  blacklist entries in `text_filters.py`, same boundary as the existing subtitle ghosts.
- **Download progress could hang before any bytes moved, or look finished while still
  fetching.** Sizing a repo called the Hub with no timeout (a captive portal left the panel on
  Downloading forever), and the byte numerator counted the whole cache directory — leftover
  blobs from an earlier revision pinned the bar at 100% on the first poll. The metadata call is
  now bounded, and the numerator is growth since the watch started.
- **A late warm-up could clear Restart-required.** Changing the storage root (or another
  baked-in setting) mid-boot set `restart-required`, but the in-flight warm thread could still
  flip readiness back to `ready` and unlock Start against the wrong `HF_HOME`. Boot attempts now
  carry an id; invalidating the boot makes subsequent readiness writes from that attempt no-ops.
- **Disarming retrieval on Pre-flight did not stop it.** After a session that had armed the
  advisor, a later Start with the toggle off still fired cues because the worker checked
  `self.advisor` and ignored `enable_rag`. The per-meeting gate is honoured now.
- **The ASR-model field warned about re-warming but the app demands a restart.** Warning text
  and `.env.example` now match the fingerprint behaviour.
- **The anti-hallucination filter destroyed real speech.** The Whisper ghost-string blacklist
  was matched as a *substring*, so "謝謝大家" and "Okay, thank you, see you" were dropped before
  reaching the transcript — and with no audio retained, unrecoverable. It now matches the whole
  utterance, ignoring trailing punctuation and Latin case. Adopted from the unmerged streaming
  branch with its nine boundary tests.
- **Capture began before authentication.** Merely opening the URL started both audio streams and
  wrote a session file, above the PIN gate and above role selection. Capture now begins only when
  a local operator presses Start.
- **`HF_HOME` from `.env` never took effect**, so weights landed in `~/.cache/huggingface`
  regardless of configuration. It is now derived from the storage root and exported before
  anything that reads it is imported.
- **The local/remote check failed open.** An empty `Host` header and any exception both granted
  local privileges, and the check matched by substring — so `localhost.attacker.net` passed. It
  now parses the host, accepts only loopback, treats an undeterminable origin as remote, and says
  so on screen rather than silently locking the operator out.

## [0.0.1] — 2026-08-07

First tagged release. A fully offline, multi-role teleprompter for Apple Silicon,
using the **BlackHole** virtual audio driver to capture the far-end participant.

### Added
- **Multi-Role Teleprompter** — role routing via query parameter (`?role=speaker` vs
  `?role=staff`). The speaker gets a clean auto-scrolling view; staff get a tactical
  control panel that injects live cues into the speaker's display over the local network.
- **Dual-Track Apple Silicon Transcriber** — `MLX-Whisper` on the Mac NPU, with the
  hardware microphone (You) and the BlackHole loopback (Them) transcribed as separate
  roles. A global NPU lock prevents concurrent Metal access from crashing.
- **Vector Semantic RAG** — `src/build_index.py` compiles `.md`/`.txt` knowledge files
  into `context/knowledge_index.pkl`; `src/local_advisor.py` matches transcribed dialogue
  by cosine similarity to trigger pre-written defensive scripts. No LLM generation, so no
  hallucinated advice.
- **Pure Teleprompter Mode** — `ENABLE_LOCAL_RAG=false` disables all vector computation
  and runs as a lightweight manual-only teleprompter.
- **Session archiving** — each session is written to a Markdown transcript under `history/`.
- **PIN-gated remote access** — a randomized 4-digit PIN printed at startup guards the UI
  on remote devices.
- `MULTILINGUAL_MODE` toggle.
- `LICENSE` file (MIT), matching the license already declared in `README.md`.
- `setup_mac.sh` — idempotent setup installing Homebrew deps, `portaudio`, and BlackHole.
- Unit test suite (`tests/unit`) with `run_tests.sh`.

### Changed
- Replaced the Gemini API advisor with the pure-local vector RAG advisor;
  `src/gemini_advisor.py` removed and `google-genai` dropped from `requirements.txt`.
- Translated the entire codebase to English (variables, docstrings, console logs, tests).
- Renamed `CLAUDE.md` to `AGENTS.md`; `CLAUDE.md` now imports it.

### Fixed
- **Dropped audio frames under NPU load** — the audio pipeline is decoupled from Whisper
  inference via a dedicated `inference_queue` and inference thread, so the CoreAudio
  callback never blocks on the NPU.
- **Failing buffer tests** — `tests/unit/test_buffer.py` still asserted the
  pre-translation Chinese strings (`"等待對話..."`) against the translated code
  (`"Awaiting dialogue..."`). Suite is now green (8 passed).

### Known Issues
- Requires the BlackHole virtual driver plus a Multi-Output Device for the speaker to
  hear the meeting while it is being captured. Replacing this with the native Core Audio
  process-tap API is evaluated and planned — see `STATE.md`.
- Microphone auto-detection keywords in `global_state.py` do not match MacBook Pro
  hardware and fall through to the system default input.
