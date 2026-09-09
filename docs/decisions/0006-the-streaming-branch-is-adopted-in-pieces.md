# 0006 — The streaming branch is adopted in pieces, not merged

- **Status:** accepted
- **Decided:** 2026-08-10
- **Follows from:** R3, R4, R11, R15, R16, R25, R32, R37, R39, R41, R44, R45, R48, V12, V18, V19, V20, V48, V49

## Context

`origin/feat/streaming-transcriber` (tip `467a442`, 10 commits, 2026-07-02) forks from `201eeea` and
was never merged. **V49** recorded its existence from its commit messages and warned that its claims
were unverified. This record is the result of actually running it.

Method: a detached worktree with **its own virtualenv**, so the branch's `silero-vad` and `mlx-lm`
could not change what the project venv resolves. Its suite was run, its diff read in full, and two
claims that could be settled without audio fixtures were settled by experiment.

**What the evaluation corrects in V49**, all verified 2026-08-10:

- **The suite is 60 tests, not "roughly 29"** — 35 in `test_transcriber.py`, 17 in
  `test_summarizer.py`, plus the 8 already on `main`. All 60 pass. So the branch stands up on its own
  and is a source of code, not merely of ideas.
- **The branch ships a second live model that V49 does not mention at all.** `resolve_default_model()`
  auto-selects `whisper-medium-mlx` on fanless Macs (MacBook Air, detected by `system_profiler`
  marketing name) and `large-v3-turbo` elsewhere, while the offline path hardcodes `large-v3-turbo`.
  V49 describes the default as `large-v3-turbo` unconditionally. The product would run up to three
  model configurations depending on chassis and code path.
- **The VAD measurement means something narrower than V49 implies.** The branch's own note says
  *incremental* Silero VAD was benchmarked and **dropped**; the ≈0.3%-of-decode figure is why that
  optimisation was rejected, not a general endorsement of the VAD. Its model benchmark used "short,
  clean TTS clips", which its author flags as never measured against real noisy audio.
- **It reads five environment keys, not three** — `WHISPER_MODEL`, `WHISPER_LANGUAGE`,
  `TRANSCRIBE_MODE`, plus `SUMMARY_MODEL` and `AUTO_SUMMARIZE_ON_EXIT`. Only the first three reached
  `.env.example`; the other two exist solely in source and prose, which is the drift `AGENTS.md`
  forbids.
- **It does not fix capture-before-authentication, and makes it worse.** The auto-start at the top of
  `app.py` survives untouched (**V18**), and capture now also opens two WAV files on the disk of
  anyone who loads the URL. **R25** is breached harder than on `main`.

Two experiments, because reading could not settle them:

- **Per-track merge is correct given a shared `t=0`, and the branch never establishes one.** With
  `transcribe_audio` stubbed, `run_session_dir` ordered and labelled four interleaved segments across
  two tracks exactly as intended. But the two `Transcriber` instances are constructed and started
  *sequentially*, each opening its WAV inside its own `start()`, so the Participant track begins later
  than the Speaker track by however long the second construction takes. No per-track start timestamp
  is written anywhere. `decision 0001` requires the precise session start time for exactly this
  reason, and **R45**'s "jump to this moment" does not survive an unrecorded skew.
- **Silero accepts 48 kHz, but by 3:1 decimation.** `get_speech_timestamps` does
  `audio[::step]` with no anti-alias filter when the rate is a multiple of 16 kHz. It *does* rescale
  the returned indices by the same factor, so the branch's buffer-slicing arithmetic would survive the
  move to 48 kHz — but the VAD would be judging aliased audio. Since `decision 0001` makes 48 kHz
  capture mandatory and this branch deletes `webrtcvad` outright, that is a live design input for
  **V12**, recorded as **V50**.

## Decision

**Do not merge, do not rebase, do not rescue.** Each piece is sorted below and carried forward
individually. The branch predates every Phase 7 requirement, so agreement with them is coincidental
where it occurs.

### Adopt now

| Piece | Why, and what comes with it |
|---|---|
| Whole-utterance hallucination filter (`_acceptable`, `_normalize_phrase`) | `main` still matches the blacklist as a **substring** at `transcriber.py:163-164`, so "謝謝大家" and "Okay, thank you, see you" are discarded as ghosts. That is real speech destroyed with no archive to recover it from (**V48**, **R3**). Isolated, pure, and arrives with 9 boundary tests. Convert those tests to the `src.`-prefix import convention before landing. |

### Adopt after rework

| Piece | Which requirement the implementation contradicts |
|---|---|
| Durable per-track WAV capture — queue, writer thread, never any I/O in the audio callback | The **pattern** is precisely what the retention item specifies and satisfies the never-block-the-callback invariant. The implementation writes **16 kHz** (`decision 0001` requires 48 kHz), into `recordings/<session_id>/` under the repo (**R44**, **R48** require a derived path under the storage root), named `Speaker.wav` / `Participant.wav` (**R44**/**R45** pair files by `session_id` as `_mic`/`_system`), **unconditionally** (**R16** requires a sticky toggle, off until armed, and **R41** a size-and-consent warning), and records **no session start time** (`decision 0001`, **R45**). |
| WAV-close-first shutdown ordering in `stop()` | The ordering itself is worth keeping and is not obvious: clear the running flag, close the stream, then sentinel → join the writer → close the file, all *before* waiting on the Whisper worker, so an impatient second Ctrl+C still leaves a closed header. A truncated header is a lost record under **R45**. What must not come with it is the coupling to `flush=False`, which buys shutdown speed by discarding the residual decode — that trade belongs to the open **R3** question, not to a shutdown path. |
| `retranscribe.py` — offline re-transcription and per-track merge | This is **R45**'s "re-transcribe an archived meeting with a better model", already built and its merge logic verified. Rework: establish and persist a shared timebase; drop the hardcoded 16 kHz; stop hardcoding the model so an explicit choice is not silently ignored offline; write outputs under the storage root (**R48**). |
| `_float_to_int16`, `slug_track_name` | Correct and tested, but `slug_track_name` produces the branch's filename contract, not **R44**/**R45**'s. |

### Re-derive under Phase 7

| Piece | What survives, and why the shape does not |
|---|---|
| Silero sliding-window streaming replacing the webrtcvad fragment pipeline | The insight is strong — transcribing coherent windows instead of sub-second fragments preserves sentence context and stops words being cut at silence boundaries. But whether it lowers the false-trigger rate on non-speech is the **R37** measurement, and that is blocked on audio fixtures this repo does not have. Deleting `webrtcvad` is a decision the ASR work must make deliberately, now informed by **V50**. |
| `large-v3-turbo` default and the bilingual `initial_prompt` | **R11** requires a deliberate, measured choice; this is an assertion. The bilingual prompt is *content*, not interface, so it does not breach **R38** (`decision 0003`) and is a good candidate to carry into the bake-off. |
| Hardware auto-selection of `whisper-medium-mlx` on fanless Macs | The concern is real: a fanless chassis throttles over a long hearing, and that belongs in the bake-off's criteria. Selecting a *different model* by marketing-name detection is not the answer — it defeats **R11**, makes any measured default untrue on half the machines, and its supporting benchmark used short clean TTS clips by its author's own admission. |
| Local `mlx-lm` summary (`summarizer.py`) | Strictly better than the planned headless-Claude cleanup for **R15**, and the grounding rules in its prompt are well built. But it is a *different deliverable* from the cleanup pass — it produces a four-section summary, not a normalised transcript — and it introduces a further undeclared model download that must land under **R48**. Whether cleanup goes local is now an open decision in `STATE.md`, not something this record settles. |
| Advisor poll interval 0.3 s → 0.1 s | Unmeasured, and the advisor work rewrites that loop to be off-thread and single-flight anyway. Fold the latency goal into that item rather than carrying a one-line change. |

### Discard

| Piece | Reason, recorded so it is not rediscovered as a novelty |
|---|---|
| Bounded ring buffer that silently drops the oldest audio | Its own README states the live path "drops the oldest audio under load", with no counter, no log and no UI signal — invisible loss, which **R39** forbids and **R3** is about. The branch's answer is that the durable WAV is the complete record; that is a coherent position, and it is precisely one horn of the open **R3** question. Adopt the *position* there if it wins, not this unsignalled implementation. |
| `app.py` batch-mode routing via `should_run_batch` | Puts `import retranscribe` — and therefore `torch`, `mlx_whisper`, `silero_vad` — at `app.py` module scope. Configuration must set `HF_HOME` *before* anything heavy imports (**V19**, **V20**, **R48**), so this hook defeats the one mechanism that makes the fixed cache layout work. An entry point under `tools/` costs nothing and keeps the import graph clean. |
| Detached auto-spawn of the summary at `atexit` (`AUTO_SUMMARIZE_ON_EXIT`, default on) | Launches a detached process running a 3B model with no operator consent, no visible progress, and failures reported only into a log file inside a directory nobody is watching (**R39**, **R41**). It also fires from `atexit` in a Streamlit app that re-executes constantly. |
| The env keys `WHISPER_MODEL`, `WHISPER_LANGUAGE`, `TRANSCRIBE_MODE`, `SUMMARY_MODEL`, `AUTO_SUMMARIZE_ON_EXIT` | The persisted inventory in `REQUIREMENTS.md` is normative (**R32**). `WHISPER_MODEL` is absorbed by `ASR_MODEL`; the rest are not settings the operator maintains — language is auto-detected per chunk (**R8**, **R10**), and commit mode is derived from whether the advisor is armed. |

## Amendment, 2026-08-17 — the reasons for keeping the branch have mostly expired

The 2026-08-10 amendment held the branch until later work took three pieces. Checked today, item
by item, because a "do not delete" note whose grounds have quietly gone is worse than no note —
the next reader obeys it without being able to say why.

| Piece it was held for | Now |
|---|---|
| `_capture_writer` and the `stop()` finalisation ordering | ✅ **taken** by the retention work, 2026-08-13 |
| `retranscribe.py` | ❌ **not taken.** The re-listening pass was written fresh as `src/relisten.py` |
| `summarizer.py` | ❌ **void.** The cleanup work it belonged to was deleted outright — this application performs no post-processing at all, so there is no local summariser to inherit and there will not be |

So one obligation is discharged and two are dead. **`relisten.py` was written without consulting
`retranscribe.py`**, which is worth stating plainly rather than implying it was considered: the
design changed underneath it — a shared timebase now exists because retention records each track's
first frame, and the operator's numbered-label scheme has no counterpart on the branch.

**What the branch is still worth** is a question, not an answer, and it is the operator's:
`retranscribe.py`'s merge logic was verified by experiment there and `relisten.py`'s has been run
once on a two-minute slice. Comparing them may be worth an hour, or may not.

**The commits are safe either way** — the local tag `archive/streaming-transcriber` points at
`467a442`, confirmed today, which is the same tip this record names. It is **not pushed**, so it
protects this clone and no other.

## Amendment, 2026-08-13 — one of the four contradictions stopped being one

The adopt-after-rework row for durable WAV capture lists four things wrong with the branch's
implementation, and the first of them was **"writes 16 kHz (`decision 0001` requires 48 kHz)"**.
That was true when this record was written on 2026-08-10 and **false the next day**: `0001` was
reversed on 2026-08-11 and now requires 16 kHz, which is what the branch was doing all along.

The row is left as written, per the never-rewrite rule. What the retention work actually took, and
what it had to fix, is in `STATE.md`'s retention item. **Three contradictions were real** — the
location, the filenames, and capturing unconditionally with no toggle and no warning — and the
rate was not one of them.

Recorded because the failure generalises and has now happened twice in this repository in one
week: **a record that cites another record inherits its reversals, and nothing walks them back.**
Read the cited record's current status before acting on a claim about it.

## Amendment, 2026-08-10 — do not delete the branch yet

The consequence below saying the branch may be deleted is **wrong as written**, and the error is
worth naming rather than quietly editing: this record preserves what the branch *knew*, not what
it *is*. Knowledge and code are not the same asset. Two of the pieces sorted above are not ideas
to be re-derived from prose — they are working implementations that later work is expected to take
and rework:

- `src/transcriber.py`'s `_capture_writer` queue-and-thread capture and its `stop()` finalisation
  ordering, which the retention work inherits (**R45**).
- `src/retranscribe.py` (262 lines, merge logic verified by experiment) and `src/summarizer.py`
  (136 lines), which the retention and cleanup work inherit (**R45**, **R15**).

Deleting the remote ref makes tip `467a442` unreachable and eventually collectable. **The branch
stays until the retention and cleanup work have taken their pieces.** A local tag
`archive/streaming-transcriber` now points at the tip so the commits survive a branch deletion;
it is not pushed, so it protects this clone only.

Separately, one piece sorted above **has since become worthless**: the branch's `app.py` and
`global_state.py` diffs. They build on the module-scope auto-start that the configuration work
deleted, and `start_recording()` has since been split into `warm_up()` plus `start_recording()`
(`docs/decisions/0007`). The WAV capture must be attached to the new lifecycle; its wiring on the
branch cannot be copied.

## Consequences

- ~~**The remote branch may now be deleted.**~~ Superseded by the amendment above. This record is
  the preserved copy of what the branch knew — but not of the code it still holds.
- **`V49` is updated to what was verified**, and **`V50`** is added for the Silero 48 kHz behaviour.
  Neither of the branch's own benchmark numbers becomes a constraint — the ≈0.3% figure describes a
  rejected optimisation, and the fanless model comparison was measured on clean TTS clips.
- **The ASR work inherits a fourth candidate question** — whether windowed streaming beats fragment
  VAD — and inherits it as something to measure against the fixtures, not to assume.
- **The retention work inherits a nearly complete implementation** and four contradictions to fix,
  which is a better starting position than the plan assumed.
- **The cleanup work's premise is reopened**: a local model may replace headless Claude entirely.
  Recorded as an open decision rather than decided here.
- **Nothing in this record relieves the configuration work**, which remains first. The branch's
  reliance on a project-local `.hf_cache` is the same failure **V19** describes.
