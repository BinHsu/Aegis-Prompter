# Handover — Aegis Prompter, Phase 7

You are taking over development. You have no context from the sessions that produced the current
state; everything you need is in this repository. **This file is a map, not a substitute** — where
it points at a source of truth, read that source rather than trusting the summary here.

Treat every claim below as a claim. Check it against the code before acting on it.

> **Written 2026-08-10, and it will go stale.** Counts, commit totals and "what is done" are a
> snapshot. `AGENTS.md`, `REQUIREMENTS.md` and `STATE.md` are the living sources and win wherever
> they disagree with this file. Sections 2, 5, 6 and 7 — the rules, the conventions and the traps —
> are the parts meant to last; treat sections 3 and 4 as needing verification before you rely on
> them. When this file is more wrong than useful, delete it rather than patching it.

---

## 1. Read these first, in this order

| # | File | Why |
|---|---|---|
| 1 | `AGENTS.md` | The hard rules. Breaking one of these breaks the product or leaks the user's data. |
| 2 | `REQUIREMENTS.md` | What the product must do (`R*`) and what has been measured (`V*`). **Normative.** |
| 3 | `STATE.md` | Where the project is, the Phase 7 plan, open decisions, known issues. **Volatile.** |
| 4 | `docs/decisions/` | Why rejected options were rejected. Read `0006` and `0007` before touching ASR, retention, cleanup, or configuration. |
| 5 | `FILEMAP.md` | Generated inventory of the Python surface. Use it to find things; never hand-edit it. |
| 6 | `CHANGELOG.md` | What shipped and when. |

`README.md` is the operator-facing document and is bilingual on purpose. That is not a licence to
write Chinese anywhere else.

**The `REQUIREMENTS.md` / `STATE.md` split is the single most important convention here.** The test
is: *does the statement stop being true once the work is done?* If yes it is a plan item or a known
issue and lives in `STATE.md`, which you rewrite freely. If no it is a requirement, a measured
constraint, or a closed decision, and it lives in `REQUIREMENTS.md`, where a large deletion is a
warning sign rather than tidying. `tools/check_state.py` enforces the mechanics.

---

## 2. Hard rules

- **Never read, commit, or quote the contents of `.env`, `context/`, `history/`, or `logs/`.**
  These are the user's meeting transcripts, private notes and secrets. They are gitignored. Tests
  build their own fixtures with `tmp_path` and must never touch them.
  - This has already been violated once: a test called `delete_settings()` with its default
    argument, which is the real `.env`. When you write a test that touches configuration, redirect
    **every** entry point — read, write *and* delete.
  - You may need to analyse a live log. Extract only what you need (counts, lengths, latencies) and
    do not print transcript text back.
- **English-only codebase.** Identifiers, docstrings, comments, log strings, test assertions, commit
  messages, and every string rendered in the interface (**R38**). Content flowing *through* the app
  — transcript lines, retrieved cues — stays in whatever language the meeting is in, and nothing may
  translate or normalise it.
- **`.env.example` is the tracked template.** Any new `.env` key is added there in the same change.
- **`FILEMAP.md` is generated from the AST.** Regenerate with `.venv/bin/python tools/gen_filemap.py`.
  If it disagrees with the code, the code wins.
- **There is no bare `python` on this machine.** Use `.venv/bin/python`.

### Invariants that break the app if violated

Each exists because breaking it produced a real failure. Read the surrounding code before touching
any of them.

- **Serialize all NPU access.** Every `mlx_whisper` call, warm-up included, holds the module-level
  `NPU_LOCK` in `transcriber.py`. Concurrent Metal calls from the two transcriber threads crash the
  process.
- **Never block the audio callback.** It may do VAD and enqueue, nothing more.
- **Match audio devices by name substring, never by index.** Indices move between runs.
- **Streamlit re-runs the entire script on every poll tick, per session.** Anything expensive or
  stateful lives behind the `GlobalState` singleton or a cache decorator, never at module scope.
- **Nothing heavy may be imported before a storage root exists.** `huggingface_hub` freezes
  `HF_HOME` at its own import time (**V19**), so `src/bootstrap.py` must set the environment first.
  This is why that module imports only stdlib and `dotenv`, and why two of its functions import
  third-party libraries inside the function body. `tests/unit/test_app_screens.py` asserts it.

---

## 3. Where the work is

Branch **`feat/configuration-and-startup`**, 15 commits ahead of `main`, **not pushed**. The repo
owner treats pushing as out-of-hours work — commit freely, but ask before anything reaches the
remote.

Also unpushed: the local tag `archive/streaming-transcriber`, pinning `467a442`.
⚠️ **Do not delete `origin/feat/streaming-transcriber`.** `docs/decisions/0006` originally said it
could be and its own amendment retracts that: the retention and cleanup items are expected to take
working code from it.

### Done

- **Configuration and startup.** `src/bootstrap.py` (new), `src/app.py` rewritten as five
  sequential screens, `warm_up()` split from `start_recording()`. See `docs/decisions/0007` for the
  five places the implementation departed from its plan.
- **The anti-hallucination filter** now matches whole utterances instead of substrings
  (`src/text_filters.py`), verified on live human speech.

### Verified by execution, on this machine (macOS 26.6.1, M-series)

- Weights land under `<storage root>/AegisPrompter/models`, not `~/.cache/huggingface`.
- A second launch reuses that cache with nothing refetched.
- `warm_up()` loads in ~3.4 s, is idempotent, and opens no audio device.
- **Capture works end to end on the microphone track**, with a session transcript written.
- The hallucination filter both drops a bare "Thank you." and preserves "Thank you very much…", in
  live speech.
- 77 unit tests, including screen routing driven through Streamlit's own `AppTest` harness.

### Never executed — do not assume any of it works

- 🔴 **The Participant (system-audio) track.** BlackHole is deliberately not installed here and the
  Core Audio process tap is not built, so there is no second source on this machine. That means
  **`R2` (two tracks, never mixed), dual-track latency, and retention's two files have never run.**
- Audio retention writes no audio at all — the toggle persists a preference and says so on screen.
- The native folder dialog has never raised a real dialog (**V45**).
- `download_models` error paths are reasoned, not observed.

---

## 4. The plan, and what to do next

`STATE.md` holds the Phase 7 plan as items `7.2` through `7.8`. **Plan numbers are execution order
and are renumbered whenever the order changes — never cite them in `REQUIREMENTS.md` or in a
decision record.** Cite `R*` and `V*` instead; `tools/check_state.py` fails the build if you don't.

**The immediate next action is the formal ASR bake-off under `STATE.md` §7.2** (after ✅ 7.3).
Operator sequencing: do **not** wire a provisional `ASR_MODEL` until that formal run records
latency **and** resources (see `fixtures/asr/FORMAL_MEASURE.md`), then choose under **R11**.
Indicative CLI bake-off numbers (incl. Qwen on `.venv-bakeoff`) already exist in §7.2; they are
not the closing record. Shipping Qwen still needs open decision **V44**. Product `.venv` is still
Python 3.9; Qwen measurement used disposable Python 3.12 `.venv-bakeoff`.

**7.3 is done** (2026-08-11): fragment running view; V52 remeasure 0sess vs 3sess, n=30, both
**0%** >2000 ms (see §7.3 table). Next plan item after the formal bake-off choice is **7.4**
(mic dropdown) unless the operator reorders.

Read the whole of `7.2` before continuing; step 0 records the **V51** baseline every candidate is
judged against.

**Five open decisions in `STATE.md` are marked blockers.** Resolve the relevant one before
implementing the item it blocks; do not resolve one by choosing silently.

---

## 5. Commit conventions

The history is the primary handover artefact in this repo — assume the next reader has none of your
context and cannot ask you anything.

**Format.** `type(scope): subject`, scope optional, subject lower-case, imperative, no trailing
period. Types actually in use here, and nothing else without a reason:

| Type | For |
|---|---|
| `feat` | new capability |
| `fix` | a defect, including one you introduced earlier in the same branch |
| `docs` | `REQUIREMENTS.md`, `STATE.md`, `docs/decisions/`, `README.md`, `CHANGELOG.md` |
| `test` | tests only |
| `chore` | release mechanics, tooling upkeep |

**The body carries the why, and it is not optional.** Specifically:

- State the failure the change prevents, concretely enough to be checked — inputs, sequence,
  consequence. "Fixes a bug" is not a commit message.
- **Record what you rejected and on what grounds.** If a choice was contested, the reasoning belongs
  here so nobody spends a second round relitigating it.
- **Cite the `R*` / `V*` the change answers to.** That is what lets a reader verify the change
  against the standard rather than against your judgement.
- **Say what you did not verify.** If a claim is reasoned rather than executed, mark it. Confident
  phrasing over an unchecked claim is the failure mode this project is organised against.
- If you correct an earlier claim of your own, say so plainly in the message rather than quietly
  overwriting it.

Sample the last twenty commits before writing your first one; the register is consistent and it is
easier to match than to describe.

**Branches**: `feat/…`, `fix/…`, kebab-case, named for the work not the ticket. Never commit to
`main` directly.

**Trailers**: keep the co-author trailer your tooling adds. Do not invent `Signed-off-by`.

---

## 6. Testing standards

```bash
bash run_tests.sh                                             # the full gate
PYTHONPATH="$PWD" .venv/bin/python -m pytest tests/unit -q     # ad hoc; PYTHONPATH is required
```

`run_tests.sh` regenerates `FILEMAP.md`, runs `tools/check_state.py`, then pytest. **Expect
`77 passed` and `OK: 48 requirements, 52 constraints, 7 decision records`.** All three stages must
be green before you commit.

**Import conventions — both are load-bearing, do not align one to the other.**

- Tests import with the `src.` prefix (`from src.bootstrap import …`) and need the repo root on
  `PYTHONPATH`.
- Runtime code imports bare (`import bootstrap`), because `app.py` appends `src/` to `sys.path`.
- **One exception, and it is deliberate**: `tests/unit/test_app_screens.py` imports `bootstrap`
  bare, off `src/` on `sys.path`, because it drives the app as it actually runs. `src.bootstrap` and
  `bootstrap` are two distinct module objects with separate readiness state; patching the wrong one
  silently does nothing and every assertion drifts to whatever the app would have rendered anyway.

**Rules that are not negotiable.**

1. **Do not report tests as passing without having run them.** Paste the count.
2. **A test you have never seen fail is not evidence.** Before trusting a test that guards a
   concurrency or ordering property, revert the fix, watch it go red, then restore. The warm-up
   locking test in `tests/unit/test_global_state_locking.py` was validated this way and the commit
   message says so.
3. **Never mock a hardware measurement.** `STATE.md` names what unit tests cannot cover — NPU
   warm-up under `NPU_LOCK`, real device enumeration, the Core Audio tap, whether PortAudio
   resamples (**V12**), whether the folder dialog blocks Streamlit's rerun (**V45**), false-trigger
   rate on non-speech (**R37**). A green mock over any of those is worse than no test, because it
   reports success about something never exercised.
4. **Unit tests never reach the network.** Two real defects hid there — a model id that 404s, and a
   download that fetched 3.4 GB of formats this runtime cannot load. Neither was reachable offline.
   When a behaviour needs the network, assert the *shape* offline (that a repository id is
   `<namespace>/<name>`, that a filter excludes the dead formats) and verify the behaviour itself by
   running it once, deliberately, and recording the result.
5. **Tests build their own fixtures with `tmp_path`.** See the hard rule above.
6. New pure logic gets tests. `STATE.md`'s verification table names the surfaces that matter and the
   cases that matter for each.

---

## 7. Traps this project has already fallen into

Offered so you do not spend the time again.

- **Rewriting a requirement to match the implementation.** This happened in `ad36867`, where the
  enablement table in `REQUIREMENTS.md` was edited so that changing the ASR model "requires a
  process restart", citing **V19**. **V19** is about `HF_HOME`, which is derived from the storage
  root alone and is untouched by an ASR-model change; the real cause is that `warm_up()` has no
  reload path. It was reverted and recorded as a known issue instead. **If a plan cannot satisfy a
  requirement, that is a finding to record, not a wording problem to smooth over.**
- **Measurement artefacts that flatter your hypothesis.** While measuring **V52**, redirected stdout
  turned out to be block-buffered — an early read looked like a dead pipeline and was briefly
  reported as a failure. And the access-code banner prints with `\r` and no newline, so log lines
  acquire a prefix *only while the script is re-running*; a line-anchored regex therefore dropped
  samples precisely in the condition under test. Both biases pointed toward the conclusion being
  sought.
- **Claiming more confidence than the sample supports.** **V52** is recorded at `p = 0.084` with a
  nine-sample control arm and says so. Keep doing that.
- **Taking another agent's output at face value.** Two review passes have already run over this
  branch; both found real defects and one made the requirement-rewrite mistake above. Check claims
  about code against the code, and say which ones you verified and which you took on trust.
- **The richest defects are the ones just introduced.** Before building on recent work — especially
  your own — re-read what the file actually says rather than what you remember writing.

---

## 8. What to do when you finish a piece of work

1. `bash run_tests.sh` — all three stages green.
2. Update `STATE.md`: the item's status, and any known issue that is now fixed or newly discovered.
3. If you measured something, add a `V*` to `REQUIREMENTS.md`, dated, with the method and the
   strength of the evidence. IDs are never reordered and gaps are never closed up.
4. If you rejected an option that a future reader might reasonably propose again, add a record to
   `docs/decisions/` — filename `NNNN-kebab-case-summary.md`, and it must carry a `**Status:**` line
   and cite at least one `R*` or `V*`. `tools/check_state.py` checks both.
5. Evaluate whether `README.md` needs updating. Adding a feature, changing architecture, or
   introducing a configuration toggle makes this obligatory, not optional.
6. Add a `CHANGELOG.md` entry for anything notable.
7. Commit, following section 5. Do not push without asking.
