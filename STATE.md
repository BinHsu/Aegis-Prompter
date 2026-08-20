# Project State

Where the project is now, and what happens next. **Every item here is meant to be deleted** — plan
items flow into [CHANGELOG.md](CHANGELOG.md) once they ship, and known issues disappear when they
are fixed. Anything that does *not* become obsolete by doing work belongs in
[REQUIREMENTS.md](REQUIREMENTS.md) instead. For how to work in the repo, see [AGENTS.md](AGENTS.md).

**Current release: `v0.0.1`** — BlackHole audio backend.

---

## ✅ The two-track realtime arm finished — 2026-08-12, 18:53. Result is **V67**.

**The answer: a 650 ms median for two-track conversational operation.** The **1.47x**
contended/solo figure this line first reported is **mostly a selection artifact** — a permutation
test the same day put the null at 1.20x with the observed value inside its 90% interval — so do not
quote it as the cost of a second track. **V67** carries the amendment and the reason. `V56`'s 2.00x is an
upper bound reached only under saturation. Full table, caveats and limits are in **V67**; do not
re-derive them here. Rescore any time with:

```bash
.venv-bakeoff/bin/python tools/measure_overlap_turns.py --sleep-seconds 4410
```

`--sleep-seconds` matters: the machine slept 4410 s mid-run, and counting that as elapsed reports a
near-realtime feed as "2.3x slower than realtime". Get the number from
`pmset -g log | grep -E "Clamshell|Wake from"`.

**What it does not settle** — inference is under 20% of the wait a speaker experiences, so **V67**
refines the minority term. The term that was missing, queue dwell, is now instrumented (`923deb3`)
and the answer arrived before anyone ran a measurement for it:

### ✅ Queue dwell measured under a real two-track load: no hidden term in the 3.75 s

**The hour, 1385 segments, both roles live (738 Speaker / 567 Participant lines), 66% of segments
contended:** dwell **median 0 ms, non-zero 17 of 1385, max 2037 ms**, with **6 segments at or above
500 ms (0.43%)**. The 10-minute stage read max 176 ms over 242 segments, so **quote the hour** — the
tail is an order of magnitude larger and a figure of "max 176 ms" reads as an assurance the longer
run withdraws. Details and the three limits on the reading are in **V67**.

**The non-zero events cluster rather than scatter**: five inside minutes 40.1–42.9, three in
53.7–55.5, the rest isolated. Their median segment duration is **0.69 s against 1.08 s overall** —
short segments, which is what one role bursting faster than its own worker drains looks like. Dwell
is per-role by construction, so a burst on one track cannot be explained by the other.

| Term | Figure | Source |
|---|---|---|
| Segment close (median segment + 0.4 s flush) | ~3.43 s | **V66** |
| Inference | ~0.65 s | **V67** |
| Queue dwell | **0 ms on 98.8% of segments, 2037 ms on one** | soak, 60-min stage |
| Against the measured wait for the first word | **3.75 s** | **V66** |

**The decomposition closes for the typical line.** The `923deb3` decision rule has now fired on the
premise it actually names — *if dwell is negligible, contention work stops* — so **the only lever on
the typical wait is segmentation**, which **V66** measured and the operator settled at 0.4 s.

⚠️ **The rule fired on the median, and the tail is not covered by it.** 17 lines in an hour waited,
one for 2 s, and **R9 is a judgement about whether the transcript is usable from a podium** — a
2-second stall on one line is the kind of thing a person notices even at 0.4% frequency, in a way an
unchanged median does not capture. Nothing here says that tail is acceptable; it says it is rare and
that no *systematic* hidden term exists.

**Diagnosed the same evening, so the judgement is now informed rather than open.** All **17 of 17**
waits overlap an inference already running on the same role, and the blocking segments are the long
ones — up to the **15 s** VAD cap. The 2037 ms case is a **5.16 s** segment taking **3469 ms** while a
**0.75 s** segment queued behind it. That is head-of-line blocking, so **the tail is bounded by the
longest single inference and is the price of the segmentation V66 chose**; removing it means lowering
the cap against **V66**'s accuracy finding. A trade for the operator, not a defect for the next agent.
Full numbers in **V67**.

⚠️ **An earlier version of this block claimed the same thing off a muted 3-minute run**, where the
tap read the mix before device volume and the microphone produced zero lines — effectively a
single-track figure. The conclusion happened to survive the correction; the reasoning did not, and
the difference is the whole point. Caught by the session that ran it, not by me.

**Contention itself is a separate question and is not closed by this.** Dwell cannot contain
cross-role lock wait by construction — dwell ends at dequeue, `NPU_LOCK` is taken after — so the
cost of a second track lives inside the inference term, where **V67**'s withdrawn 1.47x and the
soak's length-controlled ~1.26x both sit. **The clean way to settle it is to stop inferring it from
labels**: two timestamps around `with NPU_LOCK` in `transcriber.py` would make lock wait its own
measured term. Queued for when the soak releases `src/`.

### ❌ Recorded anyway: this run should not have been an hour, and it measured the wrong quantity

Judged against the *justify the run before you occupy the machine* rule, stated after it started.
Recorded as a failure rather than quietly dropped, because the reasoning generalises.

| Test | Verdict |
|---|---|
| A question that can come back false | ✅ "does realistic turn-taking cost V56's 2.00x?" |
| A decision that changes on the answer | 🟡 weak — nothing was waiting on it |
| **The shortest run that answers it** | ❌ **failed** — an hour was inherited from the fixture's length, not derived from the question |
| **Is it the quantity that matters?** | ❌ **failed** — see below |

**The decisive one.** `elapsed_ms` is lock wait plus inference, and **inference is under 20% of the
3.75 s a speaker actually waits for the first word** (**V66**). The dominant term is segment
accumulation — the speech itself plus the 0.4 s flush — which **V66** already measured and the
operator already settled. So this run spent two hours refining a minority term to more decimal
places while the term that decides **R9** was never in view.

**What should have been measured instead was queue dwell** — the gap between a segment entering
`inference_queue` and inference starting on it — which was instrumented nowhere. **Now closed, and
for the cost of the instrumentation alone: it is ~0 ms, see above.** The hour spent on the minority
term bought a number; a timestamp and a subtraction bought the decomposition.

### ⚠️ Pacing: one real cap, one retracted alarm, one misread field

**Retracted: "the premise of this run is damaged".** That heading stood here for an hour and was
wrong. Excluding sleep, the feed ran at **0.920x** of real time — *above* the ceiling its own loop
imposes — so the run is sound and **V67** may be quoted.

**The real cap is `feed_wav`'s flat sleep, and it is inherent.** `feed_wav(realtime=True)` sleeps a
flat `0.03 s` per frame with no deadline schedule, so per-frame work accumulates. Measured directly:
100 × `sleep(0.03)` takes 3.38 s, i.e. **0.887x**. A feed sitting at 0.89x is therefore at full
speed, not in trouble — which is exactly the observation that should have ruled out CPU starvation
immediately. Fixing it means a deadline schedule (`next_deadline += frame_s`; sleep the remainder),
which touches every measurement that used `realtime=True`, including **V52**'s basis. A decision,
not a tidy-up, and worth about 11%.

**`t` in the JSONL is wall clock since child start, not fixture position** — confirmed against `ps`
ELAPSED. An earlier note here read it as fixture position, which flatters a slow run: a third of the
way through reads as "a third done" rather than "3x slow". `tools/measure_overlap_turns.py` printed
the same error and is fixed.

Three anchors located by grepping the transcript text against `turns.tsv` (turns 711, 919 and 724,
each an exact match on a long distinctive line) give the profile — kept because it is what the
sleep window looks like from inside a measurement:

| Phase | Wall | Fixture advance | Pace |
|---|---|---|---|
| 1 | 0 → 2114 s | 0 → 1876.2 s | **0.888x** |
| 2 | 2114 → 6917 s | 1876.2 → 2354.1 s | **0.099x** — an ~80 min stall |
| 3 | 6917 → 7331 s | 2354.1 → 2723.0 s | **0.891x** — full recovery |

Phases 1 and 3 sit on the **0.887x** ceiling measured above. Phase 2 is the lid.

### 🚨 The stall was the lid closing, not `nice`. Corrected 2026-08-12, 18:50.

**The machine was asleep.** `pmset -g log` records `Entering Sleep state due to 'Clamshell Sleep'`
at **17:07:10** and `Wake from Deep Idle … due to … lid` at **18:20:40**. The child started
16:29:51, so the phase-2 window above is **17:05:05 → 18:25:08** — the same window, within the
coarseness of anchors located by matching transcript text. The operator confirmed independently
that they closed the lid on leaving. The intervening DarkWake / Maintenance Sleep cycles are why
phase 2 reads 0.099x rather than a flat zero.

**An earlier version of this section blamed `nice +10`, and that diagnosis is withdrawn.** The nice
level is real — `ps -o ni` still shows the child at **NI 10** against the session's **NI 5** — but
it had no measurable effect, and three things say so:

- Phases 1 and 3 ran at **0.888x / 0.891x**, and 100 × `sleep(0.03)` measured standalone on this
  machine is **0.888x**. They are sitting exactly on the no-contention ceiling. A starved process
  would be *below* it.
- A starved process does not recover to full speed at the precise moment a lid opens.
- The load average `2.37 / 3.34 / 5.30` was sampled once, *after* the wake. It describes the
  machine coming back, not the stall.

**Two claims that rested on that diagnosis are therefore also withdrawn:**

- *"Do not take timing measurements from a background agent job."* Nothing here supports it, and
  phases 1 and 3 hitting the theoretical ceiling is evidence against it. Recording `ps -o ni` and
  `uptime` beside a measurement is still cheap and still worth doing — but as hygiene, not as a
  rule derived from this run. **What this run does justify is checking `pmset -g log` for sleep
  before quoting any long-running wall-clock figure.**
- *"Treat the latency table from this arm as void."* That followed from `elapsed_ms` including
  thread scheduling under a nice level that turned out not to bind. The inference medians held flat
  at 518–666 ms across all three phases, which is what a healthy run looks like. The table is
  usable, with the pacing caveat below.

**How this got written.** The stall was diagnosed from `ps`, `uptime` and the pace profile without
ever checking whether the machine had been awake. Every fact gathered was true; the one question
that would have settled it was not asked. The general prohibition was then derived from the
unchecked cause and committed — which is how a single missing check becomes a rule other work has
to obey.

Backpressure on `audio_queue.put(..., timeout=1.0)` was the earlier hypothesis and is **not
needed** to explain the profile; it is neither confirmed nor excluded, and the harness fix in
`ccab813` is what would let a re-run tell.

**Why it could not be diagnosed: the harness discarded the evidence.** `npu_lock_trial.py`'s child
attached only its JSON `Sink` to the `Transcriber` logger, which suppresses `logging.lastResort`,
while root had no handler — so every `logger.warning`, including `Audio queue full`, was dropped at
emission. The 0-byte stderr meant *no reporting*, not *no problems*. **Fixed in `ccab813`**, so a
re-run will say what this one could not.

**What this invalidates, and what survives.** Both tracks are slowed *equally*, so the conversation's
relative timing — and therefore the overlap structure — is preserved. Inference duration is not
slowed, so the accelerator still gets more slack per unit of audio than reality would give it and
**the contended fraction remains a lower bound** — but by **~12%**, the awake pace being 0.888x, not
by the ~3x an earlier draft claimed. That figure came from reading 0.33x as a steady rate when it
was a cumulative average across the sleep, and is withdrawn with the diagnosis it rested on.
What is unaffected by pacing at all is **CER against the reference and completeness**, since
accuracy does not depend on how fast the audio arrived.

**So: do not open a new measured constraint from this run's contention numbers.** (An earlier draft
named the next unused constraint number here as though it existed; `tools/check_state.py` rejected
it, correctly. Citing an identifier before defining it is how a dangling reference is born, and the
checker matches the bare token — putting it in backticks or in a sentence explaining the mistake
does not exempt it, which is the right behaviour and cost two attempts to respect.)
Score it for CER and completeness if it
finishes; the turn-taking figure needs a feed with a deadline schedule
(`next_deadline += frame_s`; sleep the remainder) rather than a flat per-frame sleep. That is a
change to `src/transcriber.py` and it touches every measurement that used `realtime=True`, so it is
a decision, not a tidy-up.

If it died early, the log is still valid for what ran — relaunch with the command in
`tools/measure_overlap_turns.py`'s docstring rather than inventing one.

**Do not run `tools/soak_capture.py --microphone` at the same time.** Both want the NPU, and
running them together corrupts both measurements.

---

## 🔌 Resume point — 2026-08-19, 05:20. The overnight run finished; read this first.

Everything is committed and **nothing is pushed**. No job is running.

✅ **`.env` is fixed — the application will start.** It named `Qwen/Qwen3-ASR-0.6B`, removed on
**R50**; `ASR_MODEL` is now `mlx-community/whisper-large-v3-turbo`. Saved **through the settings
page**, not by hand (**R18**, **R32**): `src/app.py` was driven through Streamlit's `AppTest`
harness with `selected_role="staff"` and `show_configure=True`, and the real
`💾 Save configuration` button was clicked, so the write went through `bootstrap.write_settings`
exactly as a click does. Verified afterwards — **exactly one key moved** (`ASR_MODEL`), 17 keys
before and after, `missing_required` empty, both required repos already cached under the storage
root, `needs_restart` false, and `transcriber.resolve_backend` now returns `whisper` while still
raising on the old id, so the **R50** guard is live rather than merely quiet.

**Not done, and it is one field on the same page:** the gate still ships off. `VAD_GATE=true` with
`VAD_MIN_SPEECH=0.25` turns on the measured mitigation — see outstanding item 3, which is a
judgement and not a number.

**macOS updated 26.6.1 → 26.6.2 at 05:00 on 2026-08-19** (`softwareupdated`, reboot 04:59). It did
not interrupt anything: `RUN.log` reached `== DONE` at 23:58:43 and the last results write was
00:14, five hours earlier. Re-checked after it: **406 tests pass** and `mlx` 0.32.0 runs a matmul on
`Device(gpu, 0)`, so the Metal path survived the update.

**What the night measured, in order of what it changes:**

- **The dual-track penalty is pure lock wait and it lands on the wrong track** (**V88**). Identical
  NPU time both ways — 618 ms and 606 ms — and the entire 2x is waiting: **0 ms against 573 ms,
  every time**. The track that waits is `Participant`, the far party, whose question is what the
  product exists to deliver on time (**R9**). This is ordering, not capacity, and nothing has been
  changed about it.
- **On speakers the leak is legible and lasts** (**V87**): ~0.39 CER against the intended path's
  0.214, 489 lines across a full hour, whole phrases intact, all labelled `Speaker (You)`.
  **Headphones are a precondition for the real meeting, not advice.**
- **An hour holds through the real microphone** (**V88**): +0.4 MB, flat medians, RMS moving on all
  180 samples, zero exceptions, zero network. **V65** and **V69** now hold for the replacement model
  in the arrangement they were written about. 🚨 **This line said "with the gate on" and that was
  false** — see **V91**: all three soaks logged `⚠️ [VoiceGate] unavailable` and rejected nothing.
  The hour is an ungated hour.
- **The segmentation table can no longer choose** (**V89**): **V66**'s direction survives, but its
  false-line column has saturated at 95-98% everywhere. Do not read the lowest row as safest.
- **88% of Chinese output is Simplified** (**V90**), 67 against 9. **R10** wants Traditional; it is
  subject to **R9** and therefore a post-processing concern.

**Raw output:** `fixtures/asr/results/20260818-overnight/` (gitignored, survives on this machine).

**Still outstanding, and none of it needs a person except the last:**

1. **The dual-track re-run of V67 in the lab arrangement.** A 3-hour attempt on 2026-08-18
   produced nothing, and `npu_lock_trial.py` is close to unobservable while running — noted in the
   tool. **V88** has largely answered the question from the acoustic side already.

   ⚠️ **Earlier versions of this item said "V56/V67", and that was wrong about V56.** **V56** was
   measured on `whisper-large-v3-turbo` — the model that is shipping again — so its 2.00x needs no
   re-run on model grounds. **V67** is the Qwen one. Correcting it changes what is outstanding: the
   open question is conversational pace, not saturation, and **V88** answers it for the current
   model at 635 ms against 1173 ms per-track medians over an hour.
2. **Whether to act on V88's asymmetry.** Making the far party's track win the lock is a product
   decision with an **R9** justification, not a tidy-up.
3. ✅ **Decided 2026-08-20: the gate ships ON** (`docs/decisions/0015`), on the operator's
   criterion of significant improvement against resource cost. Off was never neutral — ungated the
   model invents from 253 of 253 non-speech segments (**V102**) — and **V97** measured an hour with
   the gate genuinely live: 67 rejections, worst-case queue dwell 6521 → 2898 ms, medians flat, zero
   exceptions. The **R41** reasoning is not overturned: `settings_from` still reads the setting and
   not the presence of the package, so an appearing dependency still changes nothing by itself.
   **The blacklist stays out** — built the modern way it removes 5% (**V85**).

   ⚠️ **Default-on makes V91's trap more likely, not less.** A gate that fails open screens nothing
   while every number looks healthy. `voice_gate.is_live()`, the `--gate` refusals in
   `soak_capture.py` and `measure_segmentation.py`, and the preflight's `voice gate LIVE` line are
   preconditions of this decision, not extras.

   ✅ **Two neighbouring decisions are now closed, both on the operator's criterion of "significant
   improvement, and what it costs"** — see `docs/decisions/0014`. `SERVE_THRESHOLD` is **0.45**:
   at 0.65 the retrieval slot fired on none of five paraphrases (**V95**, **V100**), at 0.45 it
   fires on four and still on none of the five unrelated lines, and the change costs nothing because
   the query always ran. The **generative slot ships off**: 52% of answerable questions answered,
   3% fabrication, 14% displayed noise (**V99**) — and it **doubles ASR inference while answering**
   (**V106**, 649 → 1308 ms paired). The gate default below is *not* settled by either.

   ⚠️ **The evidence for the gate is thinner than this list implied, and it took until 2026-08-19
   to notice.** Effectiveness is real — 252 → 88 false lines through the shipped module (**V84**),
   32 ms against a 2235 ms non-speech decode (**V83**). What did **not** exist is an hour of the
   gate actually running in the live engine: every soak labelled *gate on* failed open because its
   weights were never in the product's `HF_HOME` (**V91**). The weights are now in place and the
   gate loads offline, so that hour is finally runnable — **`bash tools/run_overnight.sh --only
   soak` is the run**, and it needs sound on this machine, not a decision.
4. **The real meeting**, which is the operator's and stays last.

**To run anything unattended:** `bash tools/run_overnight.sh` — it carries the five preconditions
that each fail *silently and look like success*. `--check` runs the preflight and changes nothing.

## 📍 Handoff — rewritten 2026-08-17, end of day. Read this before anything else.

## ▶ Start here: **Phase 7 is code-complete. One thing reopened on 2026-08-17 and it is not in the plan.**

**7.0 through 7.10 are built and committed.** The only plan item not closed is **7.9, the real
meeting**, and it is the operator's by definition. Every other next step needs their hands, their
account, or a preference only they hold — the list is at the bottom of this section.

⚠️ **Read `## 🔄 The ASR model changed on supply-chain grounds` before anything else in this
file.** The ASR model was replaced on **R50** the evening of 2026-08-17, which is not a plan item
and does not appear in the 7.x sections. It left **one open question that is genuinely the
operator's** — whether to restore the anti-hallucination blacklist, reversing their own 2026-08-12
decision — and it made **R37** fail by an order of magnitude more than before (**V72**). Nothing
about "the plan is finished" describes that.

**So the honest instruction to the next session is: do not go looking for work in the plan.**
It is finished. What is unfinished is *contact with reality*, and four of the five ways to get it
are gated on a person.

---

### What is verified by having been run, and what is only tested

This is the distinction that matters most on arrival, because the test count is high and it is
easy to read it as confidence.

| | ran for real | tested only |
|---|---|---|
| Retrieval (Qdrant, embeddings, cosine scores) | ✅ 2026-08-17, against the shipped benchmark file | |
| Re-listening (segmentation, ASR, two-track merge) | ✅ 2026-08-17, 2×120 s of real audio, 31.4 s | |
| Capture, devices, the tap | ✅ **V61**–**V70**, 2026-08-12 | |
| The post-meeting prompt | | no agent has read it |
| The generative advisor | | **no LLM has ever answered** — no runtime installed |
| **Speaker separation** | | **pyannote has never been installed or run.** First press is first run |
| The inverted boot (Start downloads → warms → captures) | | never pressed under the new flow |

**Three of those were verified by running them today and each one found a defect no test had.**
That is the pattern to expect, not an anomaly:

- the filler floor discarded most short **Chinese** questions — `這筆預算是誰核的？` is 9
  characters and the floor was 10, calibrated for Latin text in a product built for a Taiwan
  hearing;
- `"microseconds"` in a code comment was wrong by four orders of magnitude (measured: embedding
  8.8 ms, vector search 0.9 ms);
- the re-listened transcript carried the **live** transcript's briefing, telling an agent about a
  0.4 s flush in a file whose own header said 1.2 s.

---

### The three things a new session will get wrong if it does not read this

**1. Only Start costs anything.** The boot inverted on 2026-08-14 and **R24 was rewritten** to say
so. Opening the app, choosing a role, reading Settings and browsing the archive are all free —
nothing downloads, nothing warms, no device opens. Start does all of it; Stop releases the models
(*退駕*). If you find code loading something at page load, that is a regression, and
`test_a_configured_machine_reaches_preflight_with_nothing_loaded` is what catches it.

**2. The application performs no post-processing.** **R49 was rewritten** on 2026-08-13. Every
transcript ends with a *prompt* at a stable marker; the operator's own agent does the work. There
is no `cleanup.py`, no `CLEANUP_COMMAND`, and no local summarising model — all three existed for
a few hours and were deleted deliberately. Re-listening is the exception and the reason is
structural: it reads **audio**, which no outside agent can do.

**3. The passes are split by what goes in.** Review reads *text*; re-listening reads *audio*. Who
is speaking is an audio property, so it belongs to re-listening and **must not** be reintroduced
into the review prompt. That has been attempted twice and withdrawn twice, the second time by the
operator; the reasoning is under the diarization item.

---

### Where the work is

Branch `feat/configuration-and-startup`, **no upstream, nothing pushed**. Standing rule: *nothing
reaches the remote without an explicit go-ahead, asked each time.* The operator declined on
2026-08-17. **Do not push to tidy up.**

Counts are deliberately not written here — they have drifted every time anyone has written one
down. Run them:

```bash
git rev-list --count main..HEAD     # commits ahead of main
bash run_tests.sh                   # regenerates FILEMAP.md, then runs the suite
python tools/check_state.py         # R*/V* citations in this file and REQUIREMENTS.md
python tools/gen_filemap.py --check
```

**`run_tests.sh` now exits non-zero on failure.** Until 2026-08-17 it printed `✅ [COMPLETE]` and
returned 0 whatever pytest did — a collection error printed a green tick. If you are reading an
older commit's claim that "tests pass", that is the caveat.

**`context/` contains a benchmark file this session put there** —
`context/docs/taiwan_wiki_benchmark.md`, the example the repository ships, plus the Qdrant index
built from it. **Delete that file before putting real notes in**, or it pollutes the index.
`rm -rf context/` removes everything.

---

### 📋 Every item, at a glance

**Restored 2026-08-17** — an earlier rewrite of this handoff deleted it along with the section it
sat in. It is the only place the whole plan is visible at once.

| Item | State |
|---|---|
| 7.0 streaming-branch evaluation | ✅ |
| 7.1 configuration and startup | ✅ |
| 7.2 ASR bake-off + segmentation | ✅ model chosen (`docs/decisions/0009`), 0.4 s flush kept (**V66**) |
| 7.3 cheap polling | ✅ |
| 7.4 microphone selection | ✅ |
| 7.5 system-audio tap | ✅ both fixtures (**V67**, **V69**), BlackHole out of `setup_mac.sh` (**R6**) |
| 7.6 advisor backends | ✅ two slots, neither gates the other (`docs/decisions/0011`), Qdrant. **Retrieval ran for real 08-17; the LLM slot never has** |
| 7.7 dual-track retention | ✅ two WAVs per session, tapped upstream of VAD. **No device has been opened** |
| 7.8 the post-meeting prompt | ✅ the app runs nothing; every transcript ends with an instruction. **No agent has read it** |
| **7.9 real meeting** | **the only open item, and it is the operator's** |
| 7.10 re-transcription + speaker attribution | ✅ built. Re-listening ran on real audio 08-17; **speaker separation has never been installed or run** |
| Runtime | Python 3.12 |
| ASR model | `mlx-community/whisper-large-v3-turbo` (a settings field, not a constant) — changed 2026-08-17 on **R50** |
| Archive rate | 16 kHz, reversing `docs/decisions/0001` |
| Retrieval store | Qdrant, local collection under `context/qdrant/` |
| Optional, installed on first press | `pyannote.audio` — **not in `requirements.txt` and will not be** |
| Open decisions | none |

### 🌿 One loose end that is not work: the unmerged branch

`origin/feat/streaming-transcriber` has been held since 2026-08-10 under a "do not delete yet"
note, and **its stated reasons have mostly expired.** Checked 2026-08-17:

- the capture writer and its shutdown ordering were **taken** by the retention work;
- `retranscribe.py` was **not** taken — `src/relisten.py` was written fresh;
- `summarizer.py` is **void**, because the cleanup work it belonged to was deleted outright.

So the branch is being preserved by a note whose grounds are spent. Whether it still earns its
keep is the operator's call — `retranscribe.py`'s merge logic was verified by experiment there and
`relisten.py`'s has been run once on a slice, so comparing them may be worth an hour. **The
commits survive regardless**: the local tag `archive/streaming-transcriber` points at `467a442`,
confirmed today, and it is unpushed so it protects this clone only. `docs/decisions/0006` carries
the full amendment.

### 🔭 What the next session picks up

**Rewritten 2026-08-20 07:58. The previous version of this section said "Nothing, without the
operator" and listed three things that have since happened** — re-listen has run, the generative
advisor has produced tokens, and retention has written files. It was stale for a day and would have
sent a cold reader looking for work that was already done. Assume this section decays the same way
and check the dates on the `V*` entries it cites.

#### A. Experiments that need no person, in priority order

1. **`tools/probe_ui_flow.py` is committed and does not work.** It drives the real `app.py` through
   `AppTest` to Start → fed transcript → Stop, and three of its checks fail: no transcript lines
   reach the buffer, no Stop control appears, and no session record is written. Observed 2026-08-20:
   the streams open and close about half a second later, so **the session does not stay up across
   the poll re-runs**. Its docstring also claims it "opens no microphone" and **that is false** —
   the log shows `Input stream live on [0] 'MacBook Pro Microphone'`, so `AEGIS_V52_FEED` was not
   honoured. Fix the tool or delete it; a broken probe in `tools/` is worse than none, because the
   next reader assumes it works. **This is the only path in the product that no test or soak
   covers**: everything else drives `GlobalState` directly and bypasses Streamlit entirely.
2. ✅ **Done 2026-08-20: `cer_bucketed_60s` is now the median** (**V96**), the mean is kept under its
   own name, and every stored run was rescored. **But the next step is already visible and is
   better than what landed.** The 3-minute rung of the 19:32 run produced a bucket scoring **6.15**,
   giving a mean of 2.4065 against a median of 0.7045 — at *three* minutes, not sixty. So the
   mechanism is **not** "error grows with bucket count", which is only the probability of hitting a
   bad bucket; it is **buckets whose reference text is short**, where a near-silent minute gives a
   tiny denominator and any microphone output becomes an enormous insertion ratio.

   **The principled statistic is a micro-average: total edits divided by total reference characters
   across buckets.** It avoids the single-string alignment problem **V87** rejected *and* the
   small-denominator explosion the bucketed mean introduced. It needs the tool to record per-bucket
   edit counts and reference lengths rather than only the ratio, which it does not yet do. Do this
   before quoting any leakage figure to two decimal places.

3. **~~`cer_bucketed_60s` is an unclipped mean and must not be quoted (V96).~~** One bucket scored
   **16.59**, which decided the 60-minute figure on its own. Median and clipped mean both survive it.
   The stored `cer_buckets` list is what makes this auditable — keep writing it. Fix the summary
   field, then rescore the runs under `fixtures/asr/results/*-overnight/`.
3. **Test V99's hypothesis, which is cheap and untested.** The advisor answered a question whose
   answer was the numeral `11,000` 20/20, and one whose answer was the words *"eighteen months"*
   1/20. Two shapes is not a pattern. Add cases whose answers are words versus numerals to
   `tools/probe_advisor.py` and settle it.
4. **`SERVE_THRESHOLD = 0.45` rests on ten utterances written by the session that wrote the
   queries** (**V95**, **V100**, `docs/decisions/0014`). It is enough to prove 0.65 fired on
   nothing and thin for the replacement value. Build a larger, independently written set for
   `tools/probe_rag_cues.py` before anyone treats 0.45 as settled.
5. ✅ **Done 2026-08-20, and it changed the answer (V109).** The ladder was repeated; ten runs now
   exist. **The median spans 0.320 to 0.705**, so **V87**'s "~0.39" and **V96**'s "~0.41" are
   single-run figures and the metric cannot support two decimals — quote **roughly 0.3 to 0.7**. The
   qualitative conclusion is untouched: anywhere in that range the leak is legible, so headphones
   remain a precondition. The mechanism is also settled: bucket count raises the *probability* of a
   pathological bucket while short reference text is the *cause* — buckets above 1.0 appeared at
   n=3, n=10 and n=44, so neither half of that explanation works alone.

#### B. Needs the operator, and cannot be simulated

1. **V45** — one click on the folder-dialog opt-in button. The question is whether a *native* dialog
   deadlocks Streamlit's rerun; stubbing `subprocess.run` is precisely what proves nothing.
2. **The real meeting, on headphones.** **V87** and **V96** make headphones evidence rather than
   preference. Every latency figure here measures the machine; whether a person can read the running
   view while speaking is what **R9** claims and no fixture answers it.
3. **Speaker-attribution accuracy has no ground truth (V105)**, and the tap and microphone tracks of
   one session disagree on speaker count at ten minutes. A real meeting with known participants is
   the cheapest ground truth available.

#### C. Operational facts that will otherwise be rediscovered the hard way

- **CodeRabbit is parked until the review budget resets** — the operator's disposition,
  2026-08-20: *明天過後 budget reset 再說*. Four attempts produced no findings and the account hit its
  fair-usage ceiling, so further retries cost money for the same result. If it is picked up again,
  the useful alternative is a real GitHub Actions workflow running `run_tests.sh`, because the repo
  has no `.github/workflows` at all and that would be a check whose green means something.

- **The CodeRabbit check cannot fail, so do not treat it as a merge gate.** Across four attempts on
  PR #1 it reported `pass` for four *different* states in which no review happened: skipped for OSS
  policy, skipped for exceeding 100 files, `Review completed` while `Failed to post review comments`,
  and rate limited. There is no observable state in which it is not green. A review only runs on a
  manual `@coderabbitai full review` comment, once per head commit, and the account has a fair-usage
  ceiling. `.coderabbit.yaml` does load and does filter (verified: profile ASSERTIVE, 9 files
  filtered, 100 selected) — it is the *status* that is meaningless.
- **Pressing Start writes to `.env`.** `app.py` persists `ARCHIVE_AUDIO` and `MIC_DEVICE` at Start
  so a failed download does not lose the operator's preferences. Any probe that drives the UI
  therefore **changes their configuration as a side effect** — one did, on 2026-08-20, arming
  retention and leaving two stray WAVs under the archive directory.
- **`RETAIN_AUDIO` is not a setting.** The key is `ARCHIVE_AUDIO`. A report of "retention is off"
  was once made by reading the non-existent name, which returns empty for any spelling and is
  therefore evidence of nothing. Check names against `bootstrap.SETTINGS_FIELDS`.
- **`huggingface_hub` cannot reach the Hub on this machine** — `CERTIFICATE_VERIFY_FAILED` against a
  Cloudflare Gateway CA — while `curl` and `pip` can. So `bootstrap.download_models` and the settings
  page's availability check are both dead here, and the error reads as "check your connection".
  `tools/hf_curl_place.py` is the workaround and needs no change to what any tool trusts.
- **Shell traps, all three found here.** macOS ships bash 3.2: `mapfile` and `readarray` do not
  exist. `grep -c` prints its count *and* exits non-zero at zero, so `$(grep -c … || echo 0)` yields
  two lines and breaks the integer test after it. A `trap` on INT or TERM must `exit` explicitly or
  bash continues to the next command with state already restored.
- **`finally` does not run on SIGTERM** in Python — the default handler terminates without
  unwinding, so only SIGINT would trigger it. A teardown written in `finally` and relied on for
  SIGTERM is decorative; register `signal.signal` explicitly, or do not spawn a child from a process
  nothing can address.

#### D. The one pattern behind most of the above

Six safeguards in this work looked healthy and could not fail: a voice gate that failed open for
every run labelled *gate on* (**V91**), two preconditions that matched their own invoking shell, a
guard broken by `grep -c` exiting 1, a measurement stage globbing a frozen directory (**V104**), a
diarization sanity line checking for a floor of *exactly* 0 against a real floor of 0.02 s
(**V105**), and CodeRabbit's own status. **A check or a measurement that cannot fail reads exactly
like one that is passing.** The only defence that worked in every case was asking what the check
would print if the thing it guards were broken, and then arranging to see it. `voice_gate.is_live`,
the retention first-five-seconds comparison, and the gated R37 column all exist for that reason.

---

### How 2026-08-13 to 08-17 actually went, because the pattern will repeat

**Four designs were built and then reversed by the operator**, each time because the first version
had absorbed an assumption nobody had stated: three-band advisor routing (dissolved — the two
advisors do not compete), post-processing at Stop (dissolved — the app runs nothing), a review
pass that collected speaker names (withdrawn — review does not touch titles), and warm-up at page
load (inverted — only Start costs anything). **Every reversal made the product simpler.** If a
design here feels elaborate, that is a reason to check the record before defending it.

**Three requirements were rewritten rather than reinterpreted** — **R24**, **R49**, and the review
flag on **R15** — each quoting its previous wording and saying what was wrong with it. That is the
sanctioned move when a promise collides with what was learned. Silently narrowing the
implementation to fit old text is not.

**And the recurring defect is not in the code.** It is a document describing a decision after that
decision was reversed: a plan section still asking for routing that had been dissolved the day
before, another still requiring 48 kHz after the archive rate was reversed, a decision record
inheriting a reversal it never heard of, a prompt describing a different file, `GOAL.md` going
stale in two hours, and `.env.example` missing a field added minutes earlier. **Six instances in
five days.** Most were found by a person asking a plain question, not by a test — so when the
operator asks something that sounds obvious, check it rather than answering from memory.

**What changed as a result**: `run_tests.sh` fails loudly, `.env.example` is checked against
`SETTINGS_FIELDS` by a test, and `GOAL.md` states no status at all. Each of those was a rule with
no mechanism, and each broke within a day of being written down.

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
downloads 1.6–3.4 GB, and `HF_HOME` did not work (**V19**). Running it first would have landed
weights in `~/.cache/huggingface`, and once a storage root is configured the derived path under
**R48** points elsewhere — so the fixed layout that exists to make re-download impossible (**V47**)
would have been defeated by the plan's own first step. **That item is now done**, so the bake-off is
free to run: configure a storage root first and the weights land where they belong.

The bake-off has **two halves and they unblock at different times**: choosing a provisional default
needs only configuration + fixtures (both now available); the 48 kHz dependency that once gated
*closing* it was removed on 2026-08-12 with the archive-rate reversal, leaving the 48 kHz path
from the process-tap item. What still stands between this project and a measured ASR default is
finishing the candidate table (**V44** / Qwen), acting on the first-run **R37** failures, and
recording the choice under **R11** — not regenerating fixtures.

**A third pass added `7.0`**, to evaluate an unmerged branch (**V49**) that already implements parts of
the ASR, retention and cleanup items. **That item is now done** — see below — and the pieces it
released are folded into the items that inherit them.

Plan numbers are execution order and are renumbered whenever it changes. Older commits saying
"7.4" for configuration mean the *configuration work*, not today's section number.

## 7.0 — Evaluate the unmerged streaming branch — ✅ done 2026-08-10

Addressed **V49**. Delivered `docs/decisions/0006`, which sorts every piece of
`origin/feat/streaming-transcriber` into adopt / adopt-after-rework / re-derive / discard. **Read that
record, not this summary**, before touching the ASR, retention or cleanup items.

The branch was run in an isolated worktree with its own virtualenv. **Its suite is 60 tests and all 60
pass** — not the "roughly 29" **V49** recorded — so it is a source of code, not only of ideas. Nothing
was merged, rebased or cherry-picked; that work belongs to the items below.

What the evaluation changed, beyond the corrections now folded into **V49** and the new **V50**:

- **One piece is adoptable as-is**: the whole-utterance hallucination filter. `main` still matches the
  blacklist as a *substring*, so real speech containing "謝謝" or "thank you" is destroyed — now listed
  under Known Issues, because it is a `main` bug independent of the branch.
- **The retention item inherits a nearly complete implementation** with four named contradictions,
  which is a better starting position than this plan assumed.
- **The cleanup item's premise is reopened.** The branch summarises locally with `mlx-lm`; this plan
  specifies headless Claude. Recorded as an open decision below rather than settled here.
- **Two pieces are discarded outright** — the unsignalled lossy ring buffer and the `atexit` detached
  summary spawn — with reasons in the record so they are not rediscovered as novelties.

⚠️ **Do not delete the remote branch yet.** `0006` originally said it could be, and its own
amendment of 2026-08-10 retracts that: the record preserves what the branch *knew*, not the code it
still holds. The retention and cleanup items below are expected to take working implementations
from it — capture writer, shutdown ordering, `retranscribe.py`, `summarizer.py`. Tip is `467a442`;
a local tag `archive/streaming-transcriber` points at it, unpushed. Delete only once those items
have taken their pieces.

## 7.1 — Configuration and startup — ✅ done 2026-08-10

Satisfies **R17**, **R18**, **R19**, **R20**, **R21**, **R22**, **R23**, **R24**, **R25**,
**R32**, **R33**, **R34**, **R35**, **R38**, **R39**, **R40**, **R41**, **R43**, **R46**,
**R47**, **R48**. Addressed **V18**, **V19**, **V37**, **V46**, **V47**; enabled by **V20**;
constrained by **V21**, **V33**, **V45**.

**Read `docs/decisions/0007` before building on this.** It records the five places the
implementation had to depart from the plan written here, and why each was the requirement's call
rather than the implementer's — including the plan's own file table, which was wrong.

What shipped:

- **`src/bootstrap.py` (new)** — stdlib plus `dotenv` only, so it can export `HF_HOME` before
  anything imports `huggingface_hub` (**V19**). It owns the `.env` round-trip as an atomic
  rewrite (**V46**), the fixed layout derived from one storage root (**R48**), the report of what
  already exists beneath a root before anything is written (**V47**), the readiness state machine
  (**R24**), the download-progress surface (**R21**, **R23**, **V21**), and the local/remote
  verdict.
- **`src/app.py`** — five sequential states: Access → Role → Configure → Pre-flight → Running.
  The module-scope auto-start is gone (**V18**, **R25**), and `global_state` is imported only
  once a storage root exists (**V20**). `is_local` fails **closed and loudly** (**V37**,
  **R39**), and now gates the whole Configure and Pre-flight screens rather than only the PIN
  prompt (**R34**, **R43**). A remote device arriving before Start gets a waiting state
  (**R35**). Configure renders blank on first run and refills from `.env` afterwards (**R20**,
  **R32**); reset deletes `.env` and lists what it orphans (**R22**, **R47**); every field that
  costs something warns as it is changed (**R41**), and every disabled control names what is
  missing (**R40**).
- **`src/global_state.py`** — `warm_up()` split out of `start_recording()`, so models warm as
  soon as configuration exists while opening the streams still waits for Start (**R24**,
  **R25**, **V33**). Arming the retrieval advisor became a per-session choice on the panel
  (**R27**, **R33**) instead of an `.env` flag.
- **`src/text_filters.py` (new)** and `src/transcriber.py` — the whole-utterance hallucination
  filter from `docs/decisions/0006`, with its nine boundary cases ported and actually run.
- **`src/build_index.py`** — takes the embedding model as an argument, defaulting to
  `EMBEDDING_MODEL`. `MULTILINGUAL_MODE` is deleted outright; that file was its only reader.
- **`.env.example`, `README.md`, `setup_mac.sh`** — regenerated against the persisted inventory,
  the browser-first setup flow, and a storage root that is no longer project-local.
- **55 new unit tests** (8 → 63) covering the `.env` round-trip, the atomic write, path
  derivation, absent configuration, reset, root inspection, restart detection, the host verdict,
  the text filter, and screen routing driven through Streamlit's own app-test harness — which is
  what pins the rule that nothing heavy may be imported before a storage root exists (**V20**).

Deliberately **not** delivered, and disclosed on screen rather than faked:

- The retention toggle persists its preference and warns when armed (**R16**, **R41**, **R46**),
  but writes no audio. The panel says so in as many words.
- The microphone dropdown and the active-backend indicator are still read-only detected values,
  filled by the items below.
- The generative advisor row is hidden unless an LLM base URL is configured, and disabled when
  shown (**R28**, **R40**).
- **V45** is still unmeasured, so the folder chooser ships as a validated text field with the
  native dialog as an opt-in button beside it.

## 7.2 — ASR bake-off — ✅ **fully closed 2026-08-12**, and **the choice it made was reversed 2026-08-17**

Satisfied **R8, R10, R11, R37**. **The default is `mlx-community/whisper-large-v3-turbo`** since
2026-08-17 — see the section on the supply-chain change below. `docs/decisions/0009` records the
four-candidate comparison and every rejection with its reason and is **still the reference for how
a replacement gets judged**; what it no longer records is the winner, because **R50** disqualified
it on provenance rather than on any column of that table. The measurements live in
`REQUIREMENTS.md` as **V51**–**V60**, and the new ones land there too; this section is not
their home and does not repeat them.

**Rewritten 2026-08-12 because it had become misleading.** It still instructed the reader not to
change `ASR_MODEL` until measurements existed — they exist and it was changed — and listed as
pending eight things that had all closed: the 48 kHz remeasure (moot, `docs/decisions/0001`
reversed to 16 kHz), the **V44** supply-chain decision (`docs/decisions/0008`), rebuilding the
anti-hallucination defence (blacklist emptied; the length guard settled by **V64**), the resource
band (remeasured with MLX's own counter after `ps` under-reported by 6.5 GB), whether `NPU_LOCK` is
still needed (**V57**: removing it buys 0%), replacing TTS fixtures with public corpora (**V55**,
CAiRE/ASCEND), and whether context biasing earns its place (**V59**, and the operator ruled it does
not belong in the live path). A plan that describes finished work as pending costs the next reader
a day — this file was already the source of one such error today.

### Segmentation — settled 2026-08-12, keep 0.4 s

The last open question, inherited from the branch evaluation (`docs/decisions/0006`) and never
measured until now. **Measured — V66**, and **the operator kept production's 0.4 s silence flush.**

`flush=0.8` won accuracy, false lines and total compute *simultaneously*, and lost only the wait for
the first word — **3.75 s → 7.84 s**, because a segment cannot be transcribed until it closes. The
**R37**-above-accuracy ranking cannot settle a case where one option wins both, so it came down to
what **R9** is for: the live path owes the speaker a *timely* gist, and doubling the lag is the one
change that attacks that directly.

**The constant in `transcriber.py` now carries the reasoning**, including the boundary — do not
raise it past about a second, because at 1.5 s the median segment lands on the 15 s cap and cuts
happen on a clock rather than at silence (CER 0.17 → 0.27). Raising it is the tempting edit and its
cost does not appear in a table.

**`webrtcvad` stays too.** Whether to replace it with Silero was folded into this question, since
**V50**'s objection was about 48 kHz decimation and became moot at 16 kHz. With the segmentation
unchanged there is nothing left asking for a different VAD, so it is decided on its merits: no
reason to change.

### Kept as a pointer, not a task

**Models specialised for Chinese + English are worth a look when the ASR question is next opened.**
0.6B matched a model three times its size to within a percentage point on every language, which
suggests the ceiling here is not parameter count. **R11** requires a deliberate re-examination
rather than inheritance, so this is a note for that occasion, not work.

**Do not adopt hardware-conditional model selection.** The unmerged branch auto-selects a lighter
model on fanless Macs by marketing name, which would make any measured default untrue on half the
machines and defeats **R11**. The underlying concern — thermal headroom over a long hearing —
belongs in measurement criteria, and **V65** now covers an hour of it.

## 7.3 — Make the running view cheap enough to poll — ✅ done 2026-08-11

Addresses **V52**; bounded by **V51**; constrained by **V33**. Satisfies nothing new — it protects
**R23** and **R36**, both of which depend on the UI staying responsive while the NPU is busy.

**Closing remeasure (observed, in-process WAV feed, distil, n=30 per arm):**

| Browser sessions | n | median | p95 | max | >2000 ms |
|---|---|---|---|---|---|
| **0sess** (1 staff tab) | 30 | 1394 ms | 1489 ms | 1548 ms | **0 (0%)** |
| **3sess** (1 staff + 2 speaker) | 30 | 1430 ms | 1583 ms | 1732 ms | **0 (0%)** |

Old **V52** (5 tabs, full-script poll): max **4983 ms**, **29%** of calls >2000 ms. After
`st.fragment` on the running view + dropping the `\r` banner + Pre-flight fragment poll, the
multi-session **tail is controlled**; median still barely moves (contention shape, not thermal).
Keep poll at **0.5 s**. Raw tables: `fixtures/asr/results/v52_summary.md` (gitignored logs beside it).

Also shipped with this item: Start/Stop are local **Staff Mode** only (R34 + R35); Speaker has no
Start; `?role=` overrides session_state; V52 lab path `AEGIS_V52_FEED` injects WAV without
speaker→mic; graceful Stop joins NPU threads (avoids Metal mutex abort on teardown).

**Unblocks** the operator-gated formal ASR bake-off in §7.2 (latency **and** resources —
`fixtures/asr/FORMAL_MEASURE.md`). Do not change `ASR_MODEL` until that formal run + **R11** / **V44**.

Not in scope (still): the advisor worker loop's own `0.3 s` poll — belongs to the advisor item.

## 7.4 — Microphone selection in the web UI — ✅ done 2026-08-12

Satisfies **R26**, **R27**. Settled by **V13, V14**: this remote-controls the *host Mac's* devices;
it is not a browser device picker.

**Shipped.** A dropdown on the pre-flight panel, defaulting to *follow the system input*, with the
choice persisted as sticky `MIC_DEVICE` and applied without reloading the model.

- **`src/audio_devices.py` (new)** holds enumeration and name→index resolution, and carries no ASR
  dependency. Split for the same reason as `text_filters.py`: the panel lists inputs while the
  model may still be downloading, and importing `transcriber` to populate a dropdown would pull
  `huggingface_hub` in ahead of the boot sequence (**V19**, **V20**).
- **Stored as a name, never an index.** PortAudio's indices are positional and shift between runs
  and machines, so a persisted index silently comes to mean a different microphone. `start()`
  re-resolves from the name rather than trusting what warm-up resolved — minutes pass in between,
  and a device appearing or leaving renumbers everything after it.
- **`""` is the default and is meaningful**: *ask macOS now*, re-read at each Start rather than
  frozen. An operator who never chose keeps getting the system's current answer.
- **An unmatched preference resolves to nothing, not to the default.** Falling back would leave
  the panel naming a headset while the built-in microphone recorded the room, with nothing for the
  operator to notice. The panel shows it as `— not connected` and warns.
- **The reconstruct-vs-reload trap is closed.** `Transcriber.set_device` is two assignments;
  `MIC_DEVICE` is deliberately absent from `bootstrap.fingerprint`, so changing microphone never
  demands a restart. A test asserts both.

**The hardcoded-keyword bug is gone, and it was live on this machine.** `warm_up` matched
`["MacBook Air Microphone", "Built-in Microphone"]`; this is a MacBook **Pro**, so neither matched
and it fell through to the system default — which on 2026-08-12 was a Bluetooth headset that
happened to be connected. The product was recording through whichever headset paired last, exactly
the case the override exists for.

**A test-harness fault was found and fixed on the way.** `test_app_screens.py` asserts that nothing
heavy is imported before a storage root exists (**V19**, **V20**) by checking `sys.modules`, which
made it only as strong as the file's alphabetical position — any earlier test importing
`global_state` turned the check into a no-op. The fixture now unloads those modules for the
duration, so the assertion measures the app run rather than the test order.

**Not done here, deliberately:** the read-only active-backend indicator stays with the tap item,
and the level meters were already present (**R36**). Scope shrinks because of **R1**: system audio
is everything, so the Participant track has no source to choose and no second dropdown exists.

**Unverified:** this has not been exercised against a real capture, because capture itself has
never run on any machine. The resolution logic is tested against a fixed device table and was
sanity-checked against this machine's real one; what is untested is a stream actually opening on a
chosen device.

## 7.5 — Core Audio process tap, then make it the default

Satisfies **R1, R2, R5, R6, R7**. Built on **V6–V11**; **V12** is the first unknown to hit and is
**load-bearing** once 48 kHz archival is required.

**Why the tap is structurally right, not merely newer — noted 2026-08-12 and not previously
written down.** The two approaches differ in what they *do* to the machine, and only one of them is
a read:

| | BlackHole | Process tap |
|---|---|---|
| How it obtains audio | **must become the default output device** | reads the mix; touches no device |
| Can the operator still hear? | not without hand-building a Multi-Output Device | yes, with no setup |
| A second app wanting the same thing | they contend for one setting | independent readers, no contention |
| Operator switches to headphones mid-meeting | the arrangement breaks | unaffected |

A tap reads the mix **before** it is rendered, so which microphone, speaker or headset any
application selected is not information a tap has — device choice happens downstream of it. That is
why capture can be source-agnostic (**R1**) without being told anything (**R5**), and it is the
argument for **R6** that the record was missing: BlackHole is not merely an older route to the same
place, it is a route that commandeers a setting the operator needs.

The operator observed the same behaviour from the outside — a conferencing app capturing a meeting
running in a *different* app regardless of the devices that app had selected. Two mechanisms produce
that appearance and they are worth telling apart before citing it as evidence: a genuine tap, or the
microphone hearing the speakers. **Headphones distinguish them** — a tap is unaffected, acoustic
leakage stops. Not tested here, and no third-party audio driver is installed on this machine
(checked 2026-08-12: the only HAL plugin present is Apple's own).

**Provisioning stance, decided 2026-08-10: the old path is kept, but not installed here.** BlackHole
stays in the code as the permanent fallback (**R6**) and is deliberately **not installed on this
development machine**, which runs macOS 26.6.1 — far above the 14.2 floor (**V6**) and the very
machine **V7**, **V9** and **V10** were measured on. New hardware takes the new route; only machines
that cannot run the tap take the old one.

The consequence is not free, and it lands on the work below rather than on this item: **there is no
Participant source on this machine until the tap exists.** Any end-to-end run before then is
microphone-only, so nothing that needs two tracks — dual-track latency in the ASR item, the
never-mixed guarantee (**R2**), retention's two files — can be exercised here yet. That is an
argument for pulling this item earlier than its current position, and the counter-argument is that
the ASR item's decisive measurements (false triggers on non-speech, code-switching) run from audio
fixtures fed straight to the transcriber and need no device at all. Left as a live question rather
than a silent reordering.

**The unified alternative was raised and rejected on 2026-08-12; the design below stands.** The
operator asked for one mechanism giving both directions so nobody has to think about which
microphone. ScreenCaptureKit does that — `captureMicrophone`, `microphoneCaptureDeviceID`, and a
distinct `SCStreamOutputTypeMicrophone` that keeps **R2** intact, all macOS 15.0. It was rejected
because `SCStream` has no audio-only form: the filter is mandatory, so audio comes bundled with a
screen capture and its consent prompt. **The reasoning is closed and lives in the rejected-options
table in `REQUIREMENTS.md`** — do not re-derive it here.

Three things from that evaluation change this item and must not be lost with it:

- **`V12` is back on the critical path and nothing else dissolves it.** SCK could have been asked
  for 16 kHz directly (`SCStreamConfiguration.sampleRate`); the tap is fixed at 48 kHz (**V7**)
  while `docs/decisions/0001` made 16 kHz the single rate everywhere. With SCK gone, **someone has
  to measure who resamples**, which is step 1 below.
- **Two tracks are not in question under any mechanism.** Confirmed by the operator the same day.
  The reasoning was missing from the repo entirely and now sits under **R2**, backed by **V60**'s
  cross-talk measurement. A single merged track is not an option, and was not one for SCK either.
- **The microphone default needs no new mechanism.** The current design opens the mic itself and
  can follow the system default — **R26**'s *sensible default, freely overridable*. Nothing about
  SCK was required for that, and **no macOS API picks a live microphone from several**:
  `microphoneCaptureDeviceID` is one nullable string. The dropdown is the override, and it earns
  its place because the system default input is often whichever headset connected last.

0. ~~**Two device-topology unknowns V7 does not cover.**~~ **Both closed 2026-08-12 — V63.**
   Switching output to a Bluetooth headset changes **nothing measurable**: identical peak, identical
   frame count against the built-in speakers. Forcing the narrowband duplex profile does not degrade
   it either — the level rises by exactly √2, which is a stereo-to-mono mixdown gain change, not a
   codec effect. The tap reads the mix before it is encoded for the link.

   The second half is moot for this deployment anyway: the operator stated the same day that capture
   always uses the **built-in microphone**, with output being the headset or the built-in speakers,
   so the Bluetooth microphone is never opened and HFP is never negotiated. Measured and recorded
   regardless, because a fork will do it.

   **What this leaves behind is a microphone-default consequence, not a tap one.** While the headset
   is connected it is also the system default *input*, so a first run defaults to a microphone this
   operator never wants. The sticky override built in the microphone item is the answer, and this
   makes it the normal case rather than an edge case — see the panel note added with **V63**.

1. ~~**Measure V12 before writing production code that assumes an answer.**~~ **Done
   2026-08-12** — `tools/measure_tap_stream.py`. **PortAudio resamples the tap on request**:
   asked for 16000 it delivers ~15919 frames per second, not ~48000, with the peak unchanged. So
   `transcriber.py` opens the tap exactly as it opens the microphone and **the planned
   VAD-at-48k fallback should not be built**. Numbers and their caveat are in **V12**.
2. ~~Add `src/native/aegis_tap.m` — a global mono mixdown tap, compiled by `setup_mac.sh`.~~
   **Done 2026-08-12.** Measured working on this machine — **V61**. `setup_mac.sh` builds it with
   Command Line Tools `clang` and warns rather than aborts when it cannot, because BlackHole is
   still the fallback (**R6**).
3. ~~`global_state.py` launches it as a subprocess on start, SIGTERMs it on stop.~~ **Done
   2026-08-12.** `src/system_audio.py` (new) owns backend selection and the helper's lifetime;
   `global_state` starts it inside `start_recording` and nowhere else (**R25**), tears it down
   after the streams in `stop_recording`, and again unconditionally at exit — `stop_recording`
   returns early when `is_running` is false, which is exactly the state a Start that raised
   mid-way leaves behind, and the cost of missing it is a phantom input device until reboot.

   Degrades in one step and says so (**R39**): tap → BlackHole if that machine has it → a silent
   Participant track that reports being silent. What it may never do is continue while claiming
   the tap is live.

   **The PortAudio device-table cache turned out to be worse than recorded** and the fix is in
   `wait_for_device`: a single re-initialisation saw the device **0 times out of 5**, one attempt
   50 ms later saw it **5 out of 5**. See **V61** — reliably wrong, and it announces success. **Microphone and
   system-audio tracks stay separate all the way through** (**R2**) — the tap replaces BlackHole
   as the *Participant* source; it must not be mixed into the mic track.
4. **Partly done 2026-08-12.** Backend selection and the pre-flight indicator are built and
   derived from capability as described below. What remains is **proving it in a real meeting**,
   which is step 5. **Auto-detect rather than configure**: use the tap when the OS supports it and the device
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
5. **Prove it, then make the tap the default (R7). The mechanical half is proven; the judgement
   half is not.**

   **Split into two on 2026-08-12, at the operator's prompting** — *"can't this be done with a
   benchmark?"* It could, and mostly was. A meeting settles two things at once, and only one of
   them needs a person:

   | | Status |
   |---|---|
   | **Does the machinery hold up for an hour?** | ✅ **V65** — no drift, no leak, no dropped frames, tap alive throughout |
   | **Is the transcript usable from a podium (R9)?** | ✅ **passed 2026-08-12** — the operator read the hour and judged it. R9's bar is a judgement, not a metric; no CER number substitutes for a person deciding they could have worked from it |
   | **Real overlap and interruption** | ➡️ **not this item's debt — it belongs to 7.9** and is tracked there. Recorded here only because this row misstated the reason until 2026-08-12 ("the fixture carries less of both"): the fixture carries **606.5 s of simultaneous speech, 16.8% of the hour**, and what it cannot supply is people interrupting *because they are arguing* |
   | **The built-in microphone over an hour** | ✅ **V69**, 2026-08-12 — staged 3 → 10 → 60 min. **V65** had fed the Speaker track from a WAV, so the device itself had never been soaked |

   **Two of four closed, and the other two do not need a meeting either** — re-examined the same
   day under the *simulate everything that can be simulated* stance, which the operator stated after
   this table was first written:

   - **Overlap and interruption at hearing density.** ⚠️ **This bullet was wrong and is kept as
     written above only in corrected form — see item 1 of the handoff.** It claimed
     `build_conversation_fixture.py` "lays them out without overlap because that is what the source
     has"; the fixture holds **480 cross-track overlapping pairs, 606.5 s, 16.8% of the hour**, and
     **V57** said so already. No variant was needed. What was missing was the **pace** — every
     dual-track figure came from a saturating feed — and `tools/measure_overlap_turns.py` closes
     that. The **V60** clause does not apply: two separate WAV files have no acoustic path, so
     mixed-audio cross-talk cannot arise on this fixture at all.
   - **The built-in microphone sustained for an hour.** Play a track through the **speakers** and let
     the microphone hear it. The transcript will be poor — room acoustics, and **V62**'s leakage —
     but the question is device durability, not accuracy, and a poor transcript answers it exactly
     as well as a good one.

   Both are unbuilt rather than impossible, and that distinction is the point of the stance.

   **On R7 compliance, stated plainly rather than left to be discovered.** The tap has been the
   default in `available_backend()` since the auto-detection step — *before* the evidence existed.
   That sequence was forced, not chosen: BlackHole is deliberately not installed here, so a build
   that declined to default to the tap would have had no Participant source and nothing could have
   been measured at all. The proof arrived after the default. It is now in place (**V65** plus the
   operator's judgement), but a reviewer checking R7 should know the order.

   **What that session established.** Both streams open and are named in the log — mic on
   `[2] MacBook Pro Microphone`, Participant on `[4] Aegis System Audio` — the tap needed two
   attempts to appear (**V61**) as it does every time, system audio transcribed correctly in
   English and Chinese at 747–1145 ms, both tracks reached the running view under the right roles,
   and warm-up contacted the network **zero** times against **one** before `enforce_offline` was
   repaired.

   **What it cost to learn: six defects, five fixed.** A headset connecting silently reset the
   microphone selection; applying that selection was wrapped in a bare `except: pass`; the
   microphone stream logged nothing at all, which is why the first two could not be diagnosed from
   the log; `enforce_offline` had never worked; the transcript ran turns together and did not
   escape its content. The sixth is **V64**, deferred to the operator as an open decision.

   ✅ **Nothing remains in this item. The last piece — taking the BlackHole install out of
   `setup_mac.sh` (R6) — went in 2026-08-12.** A real meeting is **7.9**, which exists for exactly
   that and must not be double-booked here: a plan item that lists another item's work never closes.
   Two things for 7.9 to watch that this session already hints at:
   latency was **1145 / 1086 ms with two browsers polling** against **750 ms** headless, which is
   two samples and not a finding; and the Participant track misheard 「稽核」 as 「集合」, which is
   the first live instance of what **V59** measured and what **R49**'s cleanup pass exists to fix. Everything reachable without a meeting is now measured: capture runs end
   to end (**V62**), three consecutive sessions in one process work with no drift and no leftover
   device (**V62**), and the output device — Bluetooth included — does not affect the tap
   (**V63**).

   **Two things to do in the same sitting, because the second is the larger untested surface:**

   a. A real meeting through the tap, with the operator's own audio and other people's.
   b. **The web path — mostly closed 2026-08-12, and this item contradicted the rest of the file
      until it was corrected.** It read *"which nobody has ever driven"*, while the headline of this
      same file says capture *"works, end to end, driven from a browser"*, the lesson below it
      describes *"one person driving the real UI for an hour"*, this very item quotes **1145 / 1086
      ms with two browsers polling**, and **V62** carries an amendment beginning *"after the first
      web-driven session"*. Four places against one; the one was stale.

      What the evidence covers: **Start pressed in a browser ✅**, the **running view watched while
      repainting ✅** (the operator read the hour and judged **R9** from it), **two browsers polling
      ✅**.

      What it does **not** cover, kept open deliberately: **a second physical device following into
      the transcript.** "Two browsers polling" does not say whether they were two tabs on this Mac
      or a second machine, and the difference is the whole point — a phone or laptop acting as the
      Speaker role exercises `is_local` (**V37**, **R34**, **R35**) and the remote-waiting state,
      which two local tabs never touch. That is the residue of this item, not the whole of it.

   Expect the microphone track to contain lines nobody said if the operator is on speakers
   (**V62**); headphones remove it. That is not a fault to fix live — see the *garbage in, garbage
   out* stance — but it is the thing to look at first in the transcript, because it is the failure
   that looks like success.
6. Keep the BlackHole fallback permanently for macOS older than 14.2 (**R6**).
7. **Take the BlackHole install out of `setup_mac.sh`** (**R6**). This step was missing from the
   item until 2026-08-10 and is the half of **R6** the four steps above do not deliver: they make
   the tap the *runtime* default while `setup_mac.sh:22-28` still installs the driver
   unconditionally — and does it with `brew reinstall --cask` plus `sudo killall coreaudiod`, so
   the normal install path demands the operator's password for a component the product is trying
   to stop requiring. `setup_mac.sh` **is** the "normal install path" **R6** names, so **R6** is
   not satisfied while that block runs by default.

   What replaces it is not deletion: **R6** keeps support for machines that still need it. The
   driver install becomes something the app *offers* when it has a reason to — macOS older than
   14.2 (**V6**), or a tap that failed at Start — rather than something every first-time install
   pays for. Note the ordering constraint this creates with the pre-flight indicator: capability
   is knowable before Start, but whether the tap actually produces its device is not (step 4), so
   the offer cannot be made at install time on the strength of an OS check alone.

Largest ongoing cost: the aggregate device binds a specific output device as its main
sub-device, so it goes stale when the operator switches output. Needs a
`kAudioHardwarePropertyDefaultOutputDevice` listener to rebuild. BlackHole does not have this
problem — the only respect in which it is superior.

The bake-off has no deferred re-measurement waiting on this item any more: the archive is 16 kHz
(`docs/decisions/0001`, reversed 2026-08-12), so the callback path this item builds resamples once
to 16 kHz and everything downstream is what the ASR numbers already describe.

## 7.6 — Pluggable advisor backends — ✅ done 2026-08-13

Satisfies **R28**, **R29**, **R30**, **R31**, **R36**, **R42**. Built on **V22**, **V23**,
**V24**, **V25**, **V26**, **V27**, **V28**, **V29**, **V30**, **V31**, **V32**, **V34**,
**V35**, **V36**, **V48**.

⚠️ **This section previously described three-band routing on the retrieval score, and that had
been dissolved by the operator on 2026-08-12** — recorded in *Open decisions* entry 3 below, in
this same file, while this section went on describing the scheme it had replaced. The session that
implemented this read here and not there, built the rejected design, and caught it only while
writing the handoff. `docs/decisions/0011` carries the decision and supersedes `0010`, which
argued about band edges that do not exist. **The general shape is worth more than the incident: a
plan section is not amended when a decision it rests on is closed elsewhere, and the plan section
is the one an implementer opens.**

**Read the code and `docs/decisions/0011`, not this summary.** What shipped, in one line each:

| Piece | Where |
|---|---|
| `AdvisorBackend` protocol, `Retrieval` / `Advice`, fan-out to both slots, single-flight worker | `src/advisors.py` (new) |
| Qdrant collection: `COSINE` pinned at creation and verified at read, embedding model recorded and read back | `src/knowledge_store.py` (new) |
| Retrieval returns the **score** and whether the query ran at all, not just a hit | `src/local_advisor.py` |
| One advice slot **per kind**, labelled into the session log as well as the screen | `src/dialogue_buffer.py` |
| Three distinct cards, fixed order, generated marked `UNVERIFIED`, plus a liveness line | `src/app.py` |
| Per-session arming of both slots; the collection's lock released at Stop | `src/global_state.py` |

**Three things a later reader will otherwise re-derive:**

1. **Nothing is attached to the generative request as grounding, and that is deliberate.** Handing
   retrieval's near-miss chunks to the model was the dissolved middle band's mechanism; putting it
   back couples the two slots again one layer down. A test pins it.
2. **The query-side embedding model comes from the collection, not from `EMBEDDING_MODEL`.** That
   is what keeps **V36**'s mismatch *impossible* rather than merely detected. A disagreement
   between the two is reported on the panel; it is not resolved silently.
3. **The local collection's lock is held for a session, not a process.** Otherwise the pre-flight
   panel cannot read its own chunk count after the first meeting, and `build_index.py` cannot run
   without quitting the app.

**`qdrant-client` is a new dependency** — the operator took that call on 2026-08-13 after being
shown that it resolves to 10 packages including `grpcio` and `pydantic`, and that **V29** says the
swap buys no performance. It was named as the retrieval store from the outset; the alternative
considered and rejected was talking to a remote Qdrant over its REST API with stdlib and keeping
numpy locally, which avoids the dependency at the cost of two implementations of one thing.

**The old `context/knowledge_index.pkl` is no longer read.** It is not deleted — it is the
operator's data — and both the panel and `build_index.py` say "rebuild" rather than "nothing was
ever built".

⚠️ **What is *not* verified, and it is a real gap.** ~~`context/` does not exist on this machine~~
— **that half is out of date**: checked 2026-08-19, `context/` holds 4 files and
`bootstrap.index_status()` reports a live local collection of **4 chunks built 2026-08-17** with the
configured embedding model. Whether those four are real notes or placeholders is not something to
determine by reading them, so the claim that survives is the narrower one: **an index exists and no
cue has ever been observed firing from it during a meeting** (**V34** is the same gap from the other
side — advisor liveness is visible before a meeting and not during one).
Everything above is tested against a real embedded Qdrant with stubbed embeddings, which proves
the plumbing and proves nothing about whether a cue fires when it should. **No LLM has ever
answered either** — no OpenAI-compatible runtime is installed here (checked: nothing on
11434/1234/8000/8080, no Ollama, no LM Studio). The transport is exercised against a loopback stub
server through the production `urllib` path; that says the request is well-formed, not that the
prompt makes a real model behave. **Nothing has been driven in a browser.**

Both gaps close the same way and it is the same lesson this file already records: one person
driving the real UI found six defects that no automated measurement had. Before quoting the
advisor as working, someone should put notes in `context/docs/`, build the index, point the LLM
slot at a local runtime, and watch it.

## 7.7 — Optional dual-track audio retention — ✅ done 2026-08-13

Satisfies **R16**, **R44**, **R45**, **R46**; bounded by **R4**; warned about per **R41**;
constrained by **V48**. **R3** was rewritten 2026-08-12 and no longer claims completeness, so this
item claims only what it delivers: the means to keep the audio, offered to an operator who decides.

⚠️ **This section carried a stale tail until 2026-08-13.** It closed by requiring the capture
stream to open at **48 kHz**, making **V12**'s VAD-at-48k fallback mandatory and coupling this item
to the tap work. All of that was superseded before it was read: `docs/decisions/0001` reversed to
**16 kHz** on 2026-08-11, and **V12** then measured that PortAudio resamples the tap on request, so
the fallback *should not be built* — 7.5 step 1 says so in as many words. The same shape as the
advisor item's stale routing paragraph, two sections up. **Nothing about the sample rate changed
here: capture stays at 16 kHz throughout and the archive is what the transcriber heard.**

| Piece | Where |
|---|---|
| `TrackWriter` — queue, writer thread, per-track WAV, dropped-block counting | `src/audio_archive.py` (new) |
| Tap point in the raw callback, upstream of VAD; WAV finalised before any slow wait in `stop()` | `src/transcriber.py` |
| Per-session arming, derived paths, outcome recorded at Stop | `src/global_state.py` |
| Session header states retention and a millisecond-precise start; a closing section states the outcome | `src/dialogue_buffer.py` |
| Sticky toggle, size-and-consent warning, the archive path disclosed, a live recording line | `src/app.py` |

**Five things a later reader will otherwise re-derive:**

1. **The tap is in `_audio_callback`, upstream of VAD, and it must stay there.** `_processing_thread`
   discards whatever VAD calls non-speech, so an archive taken downstream would be missing precisely
   the VAD misjudgements — the material worth going back to check.
2. **The WAV is closed before `stop()` waits on anything slow**, and specifically before `NPU_LOCK`,
   which can hold for a whole inference. A `wave` header never rewritten with its final length is a
   truncated record, and under **R45** a lost record does not come back. Ordering taken from the
   streaming branch; a test asserts the order rather than trusting the comment.
3. **Dropped blocks are counted and reach the session record**, not just a log. The queue is bounded
   because an unbounded one turns a stalled disk into unbounded memory in a process holding two ASR
   models — but a file that is 40 minutes of a 60-minute hearing is worse than no file if nothing
   says so.
4. **Retention status is written into the session header at Start, not at Stop.** Sessions end badly.
   Without it, "recorded and later deleted" and "never recorded" are the same file, and **R4** makes
   deletion normal rather than anomalous.
5. **Each track records the wall-clock instant of its own first frame.** The streaming branch's
   offline merge assumed a shared `t=0` that nothing established; the two streams do not start
   together, and only the frame clock converts a transcript timestamp into an offset into a WAV.

**One live defect fixed on the way.** `ARCHIVE_HOURLY_GB` was **0.69** — the 48 kHz figure, which
outlived the reversal to 16 kHz — so the consent-and-disk warning overstated the cost by 3x. It is
now **0.23** (115 MB per track per hour).

**No measurement was run and none is justified.** The writer's throughput is arithmetic: 16 kHz mono
int16 is 32 KB/s per track, 64 KB/s for both, which no disk in this machine's lifetime fails to
absorb. What a soak could answer that arithmetic cannot — whether an hour of real capture leaves a
playable pair of files — is **7.9**'s, and it will get it for free by running.

**Taken from the unmerged branch, and what did not come with it.** The queue-plus-writer-thread
shape and the close-first ordering (`docs/decisions/0006`). Of the four contradictions that record
lists, **only three were real by the time this was built**: the rate is no longer one, because
`0001` reversed to 16 kHz the day *after* `0006` was written and the branch's 16 kHz turned out to
be right. The other three are fixed here — location derived from the storage root, filenames paired
by `session_id`, and a sticky toggle with a warning instead of unconditional capture. The branch's
`app.py` / `global_state.py` diffs were already worthless and were not consulted.

⚠️ **`retranscribe.py` has not been taken.** It is **R45**'s "re-transcribe an archived meeting
with a better model", it is built on the branch, and it needs the rework `0006` lists — a shared
timebase (which this item now provides), no hardcoded 16 kHz, no hardcoded model, outputs under the
storage root. **The branch must not be deleted until it is taken.**

⚠️ **Not verified: no real capture has been recorded.** No audio device was opened — the tests drive
`_audio_callback` directly and read the bytes back with `wave`. What that proves is the writer, the
ordering, the naming and the record; what it does not prove is a real hour on a real disk with a
real microphone. That is 7.9's, and it is the same gap 7.6 has.

## 7.8 — The post-meeting prompt — ✅ done 2026-08-13

Satisfies **R14**, **R15**, **R49** — and **R49 was rewritten by the operator the same day**, one
day after it was added. Read the requirement, which quotes its own previous wording and says what
was wrong with it. Bounded by **R9**, **R10**.

**The application does no post-processing.** Every session transcript ends with a prompt block
after a stable marker (`<!-- aegis:post-meeting-prompt -->`), and that is the whole feature. The
operator copies it into whatever agent they use, or lifts it out with one `sed`. Nothing is
executed, no model is loaded, nothing is downloaded, nothing leaves the machine.

| Piece | Where |
|---|---|
| The prompt: three deliverables, the file format, the known defects, the audio | `src/postmeeting.py` (new, pure, no I/O) |
| Appended when the session closes, armed or not | `src/dialogue_buffer.py`, `src/global_state.py` |

**What the prompt carries, and why each part is in it.** A foreign agent reading
`Meeting_2026-08-13_101500.md` cold knows none of this, and fills every gap it is not told about:

- **the line format**, and that the two roles are two *separate audio tracks that were never
  mixed* (**R2**) — so a role label is a fact about which device the audio came from, not a guess
  from the words that an agent might helpfully "correct";
- **that advisor lines are not speech.** `⚡ Staff override`, `🛡️ Retrieved cue` and
  `🤖 Generated — UNVERIFIED` are prompts shown to the speaker mid-meeting. An agent reading them
  as utterances puts words in someone's mouth, and the generated ones were never verified (**R30**);
- **the measured defects**: segments close after 0.4 s of silence so one sentence arrives as
  several lines (**V66**); non-speech becomes a plausible short sentence at **23 of 253**
  (**V60**); short noise reaches the transcript on purpose so real one-word answers survive
  (**V64**);
- **that individual speakers were never separated** (**R12**), with an explicit instruction not to
  invent names — a cleaned transcript is the artefact that later reads as authoritative;
- **where the retained audio is**, named rather than alluded to, or an explicit statement that
  there is none and the transcript is therefore the only record.

Everything in it is a fact this repository measured. A prompt that quietly loses one of them
produces a report with that half invented.

### What this replaced, and why — the operator reversed a requirement one day old

An earlier build the same day ran a local 3B model (`mlx-lm`) or an external command at Stop, with
Stop blocking until it finished, armed on the pre-flight panel. **R49** required exactly that, and
its timing argument was *"deciding afterwards is deciding at the worst moment"*.

**That argument was borrowed from retention, where it is correct and here it is not.** Unrecorded
audio is gone, so retention genuinely must be armed in advance. A transcript on disk does not
expire — deciding tomorrow costs nothing. So pre-arming bought nothing and a blocking Stop bought
less than it cost. Once the app runs nothing, the local model, the external command and
`CLEANUP_COMMAND` have no work left.

**Deleted with it, and worth naming so nobody restores one without the rest**: `src/cleanup.py`
and its 30 tests, the `mlx-lm` dependency and its 1.7 GB model, the `CLEANUP_COMMAND` settings
field, `bootstrap.fetch_repo` / `offline_lifted`, and the ASR release path added hours earlier —
that existed to stop a 3B model coexisting with the ASR weights, and there is no second model any
more. **Its measurement survives in V58** and is the durable part: the ASR weights live in the
package's process-local cache, one warm instance is 1794.3 MB, dropping the `Transcriber` objects
frees nothing, and clearing that cache frees all of it. If a local model ever returns, that is
already known and the code is one `git revert` away.

⚠️ **Not verified: no agent has ever been given this prompt.** It is tested for what it contains,
which is the part that can rot silently; whether a real agent produces a usable report from it is
a judgement, and it belongs with the same dry run 7.6 and 7.7 are waiting for.

## 7.9 — Validate in a real meeting — **the last item in Phase 7, deliberately**

Satisfies nothing new. This is **validation, not testing**: everything a simulation can settle is
settled elsewhere, and what remains is a real room, real people, real stakes, and an operator who
has to act on what is on the screen while it matters.

**Placed last on the operator's instruction, 2026-08-12** — *"real meetings wait until the end of
Phase 7; anything that can go through simulation should, and that is what shows we are abstract
enough."* The stance is recorded in `REQUIREMENTS.md`; the scheduling consequence is here.

**Why last rather than first, stated so it is not re-litigated as procrastination.** A verdict from
a real meeting is worth having only once everything cheaper has been ruled out as the cause. A
failure in a meeting that a fixture could have caught costs a meeting *and* still needs the fixture
written; the reverse never happens.

**What it must observe**, none of which a simulation reaches:

- Turn-taking at human speed with real interruption, where both parties talk over each other because
  they are arguing rather than because a fixture said to.
- Whether the operator can **read the running view while speaking**. Every latency figure in this
  file measures the machine; none measures a person under load. **R9** is a claim about attention.
- Whether the advisor output is worth reading aloud, once **7.6** exists.
- Sustained thermals in whatever the room actually is, on battery or not.

**Do not treat a clean meeting as proof of anything a fixture already covers**, and do not treat a
messy one as a reason to re-open a closed measurement before checking the fixtures still pass.

## 7.10 — Offline re-transcription and speaker attribution — ✅ built 2026-08-17, unverified

Satisfies **R12**, **R13**, and **the half of R14 the cleanup item cannot reach** — *"corrects
speaker labels"*; completes **R45**. Added 2026-08-13, when the cleanup work found that both of
its halves already exist in packages this project depends on and neither is used.

**Why this is not simply part of the cleanup item, since the two look alike from a distance.**
They consume different things. Cleanup reads `history/Meeting_<id>.md` and produces a readable
version of *the transcript the system actually produced*; it runs whether or not audio was kept,
which matters because retention is off by default (**R16**). This reads the retained WAVs and runs
recognition **again**, producing a *different* transcript. Who was speaking lives in the timbre;
once recognition has collapsed that into a `Participant:` line, no amount of re-reading the words
recovers it. Same for context biasing, which changes what the recogniser *hears*.

They also compose in one direction: re-transcribe, then clean the result. Merging them would fix
that order and take cleanup away from every session that did not retain audio.

**This item exists because R12 had no home.** The cleanup plan assigned speaker splitting to an LLM
pass over text, and that is the wrong mechanism — a model asked to infer who is speaking from
words alone invents boundaries, in the one artefact that later reads as authoritative. The cleanup
item records the finding; this is where it lands.

Two capabilities, both read from installed package signatures on 2026-08-13 rather than from a
model card:

- **Diarization.** `mlx_qwen3_asr.transcribe` takes `diarize=True`, `diarization_num_speakers`,
  `diarization_min_speakers` and `diarization_max_speakers`. That is **R12**, in the ASR package
  already pinned by `docs/decisions/0008`. **R13** already permits it to run after the meeting, so
  nothing forces it into the live path — where it would cost NPU time the live path does not have.

  ⚠️ **It is not free, and it does not reuse the ASR model.** Read from the package source
  2026-08-14: `mlx_qwen3_asr.diarization` delegates to **`pyannote/speaker-diarization-community-1`**
  through `pyannote.audio`, which is **not installed here**, pulls **torch**, and gates its
  weights — `HfApi().model_info(...).gated` returns `auto`, so downloading it needs a Hugging Face
  account, accepting the model's terms, and a token. **This application has no token concept at
  all.** Anyone reading `diarize=True` in a signature and assuming it is a flag on a model already
  present will be wrong, which is why this is written here rather than left to be discovered.

  **So this item splits in two, and the halves have very different prices:**

  | Half | Needs |
  |---|---|
  | **Re-transcribe and fill in** — better segmentation, context biasing, recovering what the live path dropped | nothing new. The `ASR_MODEL` already configured, already downloaded |
  | **Speaker separation** (**R12**) | `pyannote.audio` + `torch`, a gated model, an HF token field the app does not have |

  The first half is worth doing on its own and delivers most of what "補完" means. The second is a
  dependency decision for the operator, and it should not be smuggled in as part of the first.
- **Context biasing.** `transcribe(..., context=...)` took rare proper nouns from 1 recovered of 11
  to 9 of 11 (**V59**) — company names, place names, the name of the person asking. It also
  rendered an English sentence in mixed Chinese, breaching **R38**, which is survivable in a pass
  the operator reads first and is not survivable live. The cleanup plan put it there; it acts on
  *audio*, so it belongs here.

✅ **The half that needs no new dependency shipped 2026-08-14** — `src/relisten.py`, a button in
Archive Mode. It re-runs recognition over the retained WAVs with a **1.2 s** silence flush instead
of the live path's 0.4 s, so a sentence spoken with a breath in it arrives as one line; it reads
the archive, which is written upstream of voice detection, so material VAD threw away is heard
again; and it biases recognition with vocabulary taken from **this meeting's own transcript**
(**V59**), which is the one source of terms guaranteed to be about this hearing.

**Three things it does that the streaming branch's merge did not:**

- **It aligns on each track's own recorded first-frame instant**, read back from the live
  transcript's audio section. The branch assumed a shared `t=0` that nothing established
  (`docs/decisions/0006`); 7.7 records those instants precisely so the assumption is unnecessary.
- **When they are missing it says so in the output** — an older session, or one that never
  stopped cleanly — rather than aligning anyway and looking authoritative.
- **It declares that speakers were not separated**, in the file, because a re-listened transcript
  is exactly the artefact someone reads a month later as fact.

It writes `Meeting_<id>_relistened.md`, never touches the live transcript, and carries the same
post-meeting prompt — it is a transcript too and needs the same review.

**A note on the naming, because it half survived a design change.** Three passes were named on
2026-08-13 — **字幕稿 / live**, **校稿 / review**, **重聽 / relisten** — with a file each. Only two
of those files are written by this application. `review` stopped having a producer when the app
stopped doing post-processing: `src/cleanup.py` was deleted and the operator's own agent produces
whatever it produces, under whatever name they give it. The three names remain useful vocabulary
for talking about the passes; they are not three files this app creates, and an earlier sentence
here said "the other two" as though they were.

⚠️ **The speaker-separation half is still not started**, and it is a dependency decision rather
than work: `pyannote.audio` + torch + a gated model + an HF token field this app does not have.
**R12 remains unsatisfied and the output says so.**

⚠️ **Not verified: no real audio has been re-listened to.** The segmentation rule, the timebase,
the vocabulary scoping and every declaration in the output are tested — against WAVs written by
the retention writer itself, so the two halves of the round trip check each other — but the
recogniser is stubbed, because a constant tone is not speech to `webrtcvad` and what these tests
are about is merging and honesty rather than model quality.

**It starts from the branch, not from nothing.** `retranscribe.py` on
`origin/feat/streaming-transcriber` is built and its merge ordering verified;
`docs/decisions/0006` lists the rework — drop the hardcoded 16 kHz, stop hardcoding the model,
write outputs under the storage root (**R48**), and establish a shared timebase. **The timebase is
no longer missing**: retention now records each track's first-frame wall-clock instant, which is
exactly what the branch's merge assumed and never established. **Do not delete the branch before
this item takes it.**

**It needs retained audio, so it is gated on the operator arming retention** — and on a real
meeting having happened. Sequenced after **7.9** for that reason, not because it is optional.

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
| Advisor fan-out (**V22**, **V23**, **V24**) | Both slots receive every utterance and neither gates the other; the retrieved cue is gated by `0.65` and only by that; a suppressed repeat and a broken index each change nothing about what the generative slot receives. The band edges this row demanded were dissolved on 2026-08-12 — `docs/decisions/0011` |
| Retention naming (**R44**, **R45**) | `session_id` plus an archive directory resolves the `_mic`/`_system` pair; the session header records retention status and path |

**What unit tests cannot cover, so nobody should pretend otherwise:** NPU warm-up and its
serialization under `NPU_LOCK`, real device enumeration, the Core Audio tap, whether PortAudio
resamples (**V12**), whether a native folder dialog blocks Streamlit's rerun (**V45**), and the
false-trigger rate on non-speech (**R37**). Those are measurements on hardware, and each is already
named as such in the item that needs it. A mocked test asserting one of them would be worse than no
test, because it would report green about something never exercised.

---

## 🔓 Open decisions

**Nothing is open.** Every entry below is closed and kept with its reasoning rather than deleted,
because a closed decision that vanishes gets re-opened by the next reader. Most were decided; **one
was withdrawn by changing the requirement that created it** — the distinction matters and is
spelled out in that entry. Decisions taken after this section was written are recorded beside the
work they belong to rather than added here, and the ones from 2026-08-13 onward are in the
advisor, post-meeting, model-field and speaker-separation items.

**The count and the date that used to open this paragraph are gone on purpose.** It read "None
open as of 2026-08-12. All seven were resolved…" while two further decisions had been opened and
closed since — a number beside a list is a second source of truth for that list, and a date is a
claim that goes stale in silence. Same correction as `.env.example`'s "the nine settings below"
and `GOAL.md`'s status paragraph.

A new entry belongs here when work cannot honestly proceed until someone chooses, not when a choice
is merely upcoming. These are blockers, not polish.

0. ~~**What should the length guard in `text_filters.is_acceptable` do?**~~ **Closed 2026-08-12 by
   the operator: leave the behaviour alone, correct the documentation.** Found in production —
   see **V64**. The guard measures the raw string, and the model punctuates nearly every utterance,
   so `哦。` and `じ。` pass while only a lone `.` is caught.

   The choice was between three, and the middle one is the trap: normalising before measuring makes
   it consistent **and drops `是。`, `不。`, `Yes.`** — the shortest answers are the ones a hearing
   turns on, and with retention off nothing recovers them. Removing the guard entirely differs from
   today only by letting a lone `.` through, which is not worth a change.

   So **short noise reaches the transcript on purpose**, and `R49`'s cleanup pass removes it where
   a person can see what is being removed. The operator's framing: *"let it through as it is; it
   does not affect anything."* The docstring now says this outright, and two tests pin both halves
   — noise passes, and short real answers pass — so the fix that looks obvious cannot land silently.

1. ~~**How does R3 coexist with default-off retention?**~~ **Withdrawn 2026-08-12 by rewriting
   R3.** The question only existed because **R3** claimed completeness of capture as the system's
   responsibility while **V48** showed the live path discarding material every session and **R16**
   left the recording off by default. The operator's resolution is the third option neither branch
   offered: **stop making the guarantee.** **R3** now says the system does not discard on its own
   initiative and offers retention as the means to keep what the transcript cannot — and whether to
   keep it is the operator's call (**R4**).

   This is a requirement change, not a reinterpretation, and it is recorded as one in
   `REQUIREMENTS.md` with the old wording quoted. The rule it appears to break — *do not quietly
   rewrite a requirement to match the plan* — is about doing it **quietly**, and about doing it to
   make an implementation look compliant. Here the implementation was already non-compliant and
   visibly so; the promise was the thing that was wrong.

   The retention item may now claim what it actually does. Nothing about its design changes: writing
   from the raw stream upstream of VAD is still right, because if you retain at all you retain what
   was heard rather than what survived the filters.


2. ~~**LLM-only liveness under R36.**~~ **Closed 2026-08-12.** Two halves, decided separately.

   **During the meeting: return code plus the response.** An in-flight call is the *absence* of a
   result, which `is_thinking` already models (**V25**). A dead backend raises or returns non-2xx.
   Deliberate silence is 200 with empty content. Those three are distinguishable — with one gap:
   **V32** records that this backend family lies through 200s (Ollama truncates silently and does
   not forward `num_ctx`), so a 200 with nothing in it might be a working model choosing silence or
   a broken one. `usage.completion_tokens == 0` plus a plausible latency separates them. Whether
   every OpenAI-compatible server returns `usage` is **unverified** and must be checked when the
   slot is built.

   ✅ **Both halves built, the rehearsal on 2026-08-14.** The one-word probe is gone; the
   rehearsal replaces it and absorbs its job, exactly as this entry said it would. The operator
   types questions, presses a button, and reads what their own endpoint answers **through the
   production prompt** — so a model that answers the small-talk line instead of declining it is
   visible here rather than mid-hearing, which is V23's flooding risk made observable. A decline
   is reported as a decline; the `PASS` sentinel is never shown as though the model said it. The
   app judges nothing. The distinction matters — the rehearsal is
   what turns "unverified" into something the operator has read for themselves, and this entry is
   its specification. The `usage.completion_tokens` question below was **not** needed: a working
   model declines by returning the `PASS` token the prompt asks for, so a blank 200 is a fault
   rather than the normal decline path, and no token count is consulted.

   **Before the meeting: an optional rehearsal, not a gate.** The operator may enter a set of
   questions, press a button, and see what their own endpoint answers. It does **not** block Start,
   it is never required, and the app does not judge the answers — the operator does, which is the
   only party able to. It doubles as the liveness probe without being one.

   Three things this settles that a liveness signal alone would not: the model never assesses its
   own output (the plan had delegated that to the system prompt, which is the thing being assessed
   asking whether to speak); **V23**'s flooding risk becomes visible in rehearsal rather than
   mid-hearing; and *"this is your responsibility"* stops being a disclaimer and becomes the
   operator having read their own model's output.

   ⚠️ **This narrows R36 deliberately.** R36 asks for the signal to be visible *before* and during.
   An optional button makes "before" available on request rather than always shown. That is
   proportionate rather than lax: **V34**'s RAG failure is silent and permanent, so its readiness
   line must always be visible; an LLM backend announces its own death on the first call.

   **Rejected: requiring RAG alongside the LLM.** Proposed as a way to keep an external gate on
   generated output, and wrong — it assumes the LLM is remote, slow and domain-ignorant. An
   operator who has fine-tuned a local model has the knowledge in the weights, gains nothing from
   retrieval, and pays no latency penalty. **R28** says neither, either or both, and this would
   have quietly made it "either, or both, but never LLM alone".


3. ~~**Advisor band edge `0.45`.**~~ **Dissolved 2026-08-12 — there is no band.** The operator's
   answer to "which backend wins when both are filled" is that neither does: **both are sent to,
   both are shown, and the source is labelled** — `[STAFF]`, `[RAG]`, `[LLM]`. A number nobody had
   measured is not replaced by a better number; the question it answered stops being asked.

   This also settles **V24** (one advice slot, so two backends overwrite each other). That was a
   collision because two sources competed for one display position, and three-band routing was the
   plan's way of deciding the winner. Separate labelled outputs remove the competition instead of
   arbitrating it — and it is **R42** implemented directly, since that requirement already asks the
   three kinds of advisor output to be visually distinct at a glance.

   What survives: RAG keeps its own `0.65` gate (**V22**), which is not a band edge but the answer
   to "is this retrieved chunk about the question at all" — showing an unrelated pre-written answer
   is worse than showing nothing. The LLM gets every Participant utterance with no score gate,
   which is consistent with decision 2: the model does not judge itself, the operator has already
   seen how it behaves in rehearsal, and the `[LLM]` label carries **R30**'s "unverified, not safe
   to read aloud".

   Left for the item that builds it, and not a blocker: three simultaneous sources compete for a
   speaker's attention mid-sentence. **R42** says a glance must be enough to tell them apart —
   which is a layout problem, not a routing one.

   ✅ **Implemented 2026-08-13, and this entry had to correct the implementation once.** The
   advisor item's own plan section still described three-band routing, so the session that built
   it built the rejected scheme and only found this entry while writing the handoff. Recorded in
   `docs/decisions/0011`, which supersedes `0010` — a record that argued at length about band
   edges that had already stopped existing. **The plan section is now consistent with this entry.**
   The layout half is answered by three labelled cards in a fixed order; whether that survives a
   podium is a judgement nobody has made yet.
5. ~~**Does post-meeting cleanup run locally or through headless Claude?**~~ **Closed 2026-08-12:
   both, and the operator chooses per meeting.** The question assumed the product had to pick one.
   It does not — arming cleanup reveals a backend choice, **built-in** local model or **external**
   command, and neither is ranked by the product.

   What makes that safe under **R15** is one rule: **the external backend exists only when the
   operator has typed the executable in full** (`CLEANUP_COMMAND`). It is never discovered from
   `PATH`, never defaulted, never inferred from what is installed. Meeting content therefore cannot
   leave the machine because a tool happened to be present — only because someone wrote down where
   it is. That is the same shape as the advisor slots (**R31**): the operator supplies the endpoint,
   the app sends and receives.

   `docs/decisions/0006`'s finding stands and now has a home: the unmerged branch's local `mlx-lm`
   summariser is the natural starting point for the built-in backend, after the rework that record
   lists.

   ⚠️ **Implemented as decided on 2026-08-13, then dissolved the same day — this entry is
   obsolete and is kept for its reasoning.** Both backends were built exactly as described. The
   operator then removed the question rather than answering it: the app now **executes nothing**
   and simply writes a prompt at the end of the transcript, so there is no backend to pick.
   `docs/decisions/0006`'s local `mlx-lm` summariser is no longer a starting point for anything
   here, and **R49** was rewritten. See the post-meeting item.

   What survives is the principle this entry established and the new design satisfies more
   completely: **meeting content leaves the machine because someone chose to send it**, never
   because a tool happened to be installed. Handing the operator a paragraph is the strongest
   available form of that.


---

## ✅ Closed 2026-08-14 — the model field says whether its default still exists, and hands over a prompt when it does not

**The operator's argument, and it is not a preference:** whatever is pinned today eventually stops
being downloadable, so the operator has to be able to change it. `docs/decisions/0008` wrote half
of this for the *package* — *"'we do not need updates' only holds while the artefact still
exists"* — and assumed weights were the safer half because they are the vendor's own
repositories. **That assumption is too optimistic**, and the counterexample turned up in the same
week: `pyannote/speaker-diarization-community-1` reports `gated: auto`. A vendor repository does
not have to disappear to become unusable; it can simply acquire a gate.

**The resolution, in the operator's words: a default, whether it still exists, and other options
do not conflict — and we can give a prompt so their own agent finds a compliant download.** That
is the same shape as the post-meeting prompt: the app states requirements and does not search.

| | |
|---|---|
| `ASR_MODEL` | already a settings field with a default. Unchanged |
| The default's standing | now labelled as **what measured best on 2026-08-11**, not as correct |
| A **Check availability** button | cached → available → gated → missing → unknown. Behind a button, because this screen re-renders per keystroke |
| When it cannot be had | a **prompt for the operator's own agent**, stating what a replacement must satisfy |
| `src/model_search.py` | the family table, the availability check, the prompt |

**Two measurements settled the shape, both 2026-08-14 against the live Hub:**

- **`author="mlx-community", pipeline_tag="automatic-speech-recognition"` returns 149 and does not
  contain the model this product runs on.** That query was mine and it was wrong for a reason
  already written down: the port reads *Qwen's own* repositories, which `0008` records as a
  feature. Scoping to the porting org excludes the weights by construction.
- **The operator's scoping, `author="Qwen", search="ASR"`, returns four** — all official. But
  **two of the four do not load, and the metadata cannot tell you which**: `Qwen3-ASR-0.6B` and
  `Qwen3-ASR-0.6B-hf` report the same `architectures=['Qwen3ASRForConditionalGeneration']` and the
  same `model_type=qwen3_asr`. Only the file list separates them —
  `mlx_qwen3_asr.tokenizer` reads `vocab.json` and `merges.txt` directly, and the `-hf` variants
  ship `tokenizer.json` instead.

**So a dropdown built from search alone would be half traps on this family**, and that is why the
app states requirements instead of listing candidates. The requirements are knowable here, from
the backend's own source; the judgement about which model is *good* is not, and maintaining one
is what goes stale.

**`model_search.FAMILIES` is now the single home of the dispatch rule.**
`transcriber.resolve_backend` imports it rather than repeating `startswith("qwen")` — two copies
would drift and the drifted one would be the one nobody runs. Each entry carries the query that
finds its candidates and the files that backend actually requires. **The whisper entry's
requirements are marked UNVERIFIED**, because they were never read from `mlx_whisper`; a guess
presented as a fact is how a filter silently excludes working models.

⚠️ **Not verified: no default has ever actually gone missing here.** The availability states are
tested against a stubbed Hub, and the live queries above were run by hand. What has never happened
is the real sequence — a default 404s, the operator reads the prompt, their agent finds a
replacement that loads. Until it does, the rescue path is designed rather than proven.

**What did not change, and it is the durable half**: the answer to *"which model should I pick
now?"* is not a list. `docs/decisions/0009` records the four-candidate comparison and every
rejection, and `tools/asr_bakeoff.py` still runs against the fixtures. **R11** already requires
the choice to be re-examined rather than inherited; this argument makes that re-examination
inevitable rather than merely advisable.

## 🐛 Fixed 2026-08-14 — `run_tests.sh` printed a green tick when the tests did not run

The script ended with `echo "✅ [COMPLETE] Testing suite finished execution…"` and returned **0
whatever pytest did**. A collection error printed that tick immediately below `1 error during
collection`. Found by accident: a syntax error in a test file produced exactly that, and the tick
below it is what made it visible.

**This matters more than a shell bug.** `AGENTS.md` says *"Do not report tests as passing without
having run them"*, and the sanctioned way to run them was this script. An agent could follow that
instruction exactly, see ✅, and report passing tests that never executed. **It is this system's
characteristic bug — reporting success while doing nothing — sitting in the thing that exists to
catch it.**

Now: the exit status is captured, a failure prints `❌ [FAILED] … Nothing above is a green light`,
and the script exits with pytest's code. Verified in both directions rather than assumed — a
deliberately broken test file gives exit 2 and the failure line; removing it gives exit 0 and
`✅ [PASSED]`.

**Nothing about earlier green runs is retracted.** They were also verified with a direct
`python -m pytest`, whose count and exit code are in the commit messages. What was unsafe was the
*possibility*, not a known instance.

## 🔁 The boot inverted, 2026-08-14 — nothing is loaded until Start

**Operator's rule: only Start costs anything.** Opening the app, choosing a role, reading the
settings and browsing the archive are all free. Pressing **Start capture** downloads what is
missing, warms the model, and opens the streams. Pressing **Stop capture** is *退駕* — the models
are released and the process returns to `idle`.

**R24 was rewritten to say this** and quotes its previous wording; read it there rather than here.
The argument that settled it is the third one, and it has no fix inside the old shape: **an early
fetch can only fetch a guess.** Which model to download is unknown until the operator has finished
configuring, and the old build proved the cost — save with the default, change `ASR_MODEL`, and it
demanded a restart *while the multi-gigabyte download of the model just replaced ran to
completion*. `set_readiness` revokes a stale boot only between repositories, and a
`snapshot_download` already in flight cannot be interrupted.

**The lock the operator asked for is a refusal, not a mutex.** Archive Mode is closed whenever
readiness is anything but `idle`, and it guards three things in descending order: the
**accelerator** (re-listening re-runs speech recognition, and a live capture already has two
tracks queueing on `NPU_LOCK` — **V56**, **V57**, **V58**), the screen's **own promise** that
entering it finds no model of ours in memory, and the **operator's attention** during a hearing.
The readiness state stays a polled flag rather than a blocking lock: a mutex held in Streamlit's
script thread freezes the page, which is what 7.3 and **V52** were about. The engine's own
`_state_lock` plus `is_warm` / `is_running` is what stops two tabs warming twice.

**Two defects this inversion exposed immediately**, both found by the test that now asserts
pre-flight imports nothing heavy:

- **The microphone picker called `engine()`** to apply a device choice live. Harmless when the
  boot had already built the engine; under the new rule that call *creates* it, importing the
  whole ASR stack on the one screen whose promise is that nothing is loaded. It now applies the
  choice only if the engine already exists, and says so otherwise — the preference is persisted
  and `warm_up` resolves it at Start regardless.
- **The Last session panel called `engine()`** for the same reason and with the same effect. It
  reads `history/` now, which is also the better source: after Stop the last session is simply
  the newest file.

**`transcriber.release_models()` is back**, on a different justification than the one it was
deleted with yesterday. It went when the second model it protected against stopped existing; it
returns because the lifecycle rule says the model exists for the duration of a session and not
one moment longer. **V58**'s measurement never stopped being true — 1794.3 MB, held by the ASR
package's own cache, freed entirely by clearing it — which is why the deletion commit said the
code was one revert away.

⚠️ **Not verified: no capture has been started under the new boot.** The states and the gates are
tested through Streamlit's own harness, and the transitions are asserted; what has not happened is
a real Start on this machine downloading, warming and opening streams in that order. That belongs
to the same dry run three other items are waiting for.

## ✅ Re-listening met real audio for the first time — 2026-08-17

**Ran without the operator**, on a slice rather than the whole fixture. The question was *does
this path work end to end with the real model* — segmentation, transcription, two-track merge,
output — and two minutes answers it exactly as well as an hour would. `fixtures/asr/conversation`
is 60 minutes per track; **120 s from each was taken, from ten minutes in.**

| | |
|---|---|
| Elapsed | **31.4 s** for 2 × 120 s of audio |
| Segments | 24 (16 Speaker, 8 Participant) |
| Timebase | **aligned** — the transcript's per-track start times were read back and applied |
| Merge | correct: a deliberate **2.5 s** offset put the two tracks in the right interleaved order |
| Output | real code-switched Mandarin/English, whole sentences rather than fragments |

**The path is verified.** What is not: quality against a reference, an hour of continuous running,
and anything about a real meeting's acoustics.

⚠️ **One thing the output shows and the design already accounts for**: the model emits **Simplified**
characters. **R10** names Traditional as the target, and normalising is the *review* pass's job —
the post-meeting prompt asks for it explicitly. So this is consistent rather than a defect, but a
reader seeing 简体 in a re-listened transcript should know it is expected there.

## 📐 Design for speaker separation, stated by the operator 2026-08-17

**This changes the decision below, so read it first.**

> Rather than titles, use **與會者1 / 與會者2 / 與會者3** — labels derived from **voice timbre** —
> and mark which line belongs to whom. At the end, provide a **guessed** mapping of 與會者N to a
> title, for the operator to confirm and then apply themselves with a find-and-replace.

**Why this is the right shape, and why it answers the objection this repository has been making
for four days.** The objection was that a model inventing names produces a document that later
reads as fact. This separates the two things that were being conflated:

| | what it is | who asserts it |
|---|---|---|
| `與會者2` on a line | an **acoustic fact** — these lines share a voice | the machine, from the audio |
| 與會者2 = 王委員 | an **identity guess** | proposed by the machine, **applied by the operator** |

The transcript body then contains only what the acoustics support. The naming never enters the
document unless a human puts it there.

**It also makes imperfect diarization safe, which is a new argument for adopting it.** If 與會者2
is really two people, or one person is split across two labels, the operator sees it *in the
table* and declines — before anything is written. Diarization no longer has to be right; it has
to be reviewable. That materially lowers what the dependency has to buy.

**What it requires**: there is no version of "與會者1/2/3 from 音色" without diarization. The
numbered labels *are* the diarizer's output. So the decision below moves from *"after the real
meeting"* to *"now, or this waits"*.

## ✅ Speaker separation — adopted 2026-08-17, installed only when the operator presses it

**The decision was the operator's and so was the shape that made it safe.** Both are recorded
because either alone would look like a shortcut.

### The shape

| | what it is | who asserts it |
|---|---|---|
| `與會者2` on a line | an **acoustic fact** — these lines share a voice | the machine, from the audio |
| 與會者2 = 王委員 | an **identity guess** | proposed in a table, **applied by the operator** |

The transcript body carries only what the acoustics support. Naming is a table at the end with the
evidence and a timestamp beside each row, and **this application never applies it** — the operator
reads it, decides, and does a find-and-replace. So a wrong guess is visible *before* it is written
anywhere, and **imperfect separation becomes recoverable rather than permanent**. That last point
is what changed the cost/benefit: diarization no longer has to be right, only reviewable.

### The install rule, which is what preserves R15

**`pyannote.audio` is not in `requirements.txt` and will not be.** It is installed by a button, on
the first re-listen that asks for labels. A process that never asks contains no telemetry exporter
and no cloud SDK, so **R15**'s offline guarantee stays *structurally* true — checkable by reading
the dependency list — for everyone who never presses it. After they press, it is their explicit
act, the same shape as every other door out of this application.

The screen states the cost before the press: **47 packages**, mostly a research lab's training
apparatus rather than anything inference needs; and `opentelemetry-*` plus `pyannoteai-sdk` as
**core** requirements of `pyannote-audio`. Neither transmits anything unconfigured — what changes
is that the promise stops being checkable from the dependency list, and the warning says exactly
that.

### The token is the *weights*' requirement, not pyannote's — and there is a path without one

Checked against the Hub 2026-08-17, because "you need a token" was being repeated without anyone
asking whether that was true of the library or of one particular repository:

| | gated | notes |
|---|---|---|
| `pyannote/speaker-diarization-community-1` (default) | **yes** | needs an account, accepted terms, a token |
| `pyannote/segmentation-3.0` (the default's dependency) | **yes** | |
| `pyannote/wespeaker-voxceleb-resnet34-LM` (embeddings) | no | official, CC-BY-4.0 |
| **`ivrit-ai/pyannote-speaker-diarization-3.1`** | **no** | MIT, and its segmentation mirror is ungated too — **the whole path needs no token** |

So `DIARIZE_MODEL` is a settings field with the official model as its default, and the gated
failure **names the ungated alternative** — an operator who does not want to create a token would
not otherwise know one exists. The mirror is a third party re-hosting MIT weights, which is a
supply-chain judgement of the same shape `docs/decisions/0008` took deliberately, not a free lunch.

⚠️ **And a trap, guarded rather than documented.** `pyannote/speaker-diarization-precision-2` is
**ungated and has no weights at all**: its `config.yaml` reads
`name: pyannote.audio.pipelines.pyannoteai.sdk.SDK`, so "using" it uploads the meeting to
pyannoteAI's API. It is exactly what an operator avoiding the token would reach for. `diarize.py`
now reads a pipeline's config before running it and **refuses anything whose pipeline runs in
somebody else's datacentre**, saying why. That also explains the `pyannoteai-sdk` dependency.

**`MODEL_ID` was a constant for three hours**, which contradicted the rule this repository states
in `model_search.py` — every model id is a settings field, because whatever is pinned today
eventually stops being downloadable. Fixed rather than argued.

### What is built and what is not verified

Built: the label scheme, the line-to-voice matching, the proposal table with its evidence, the
opt-in, the cost disclosure, the token gate, and the wiring into the re-listening pass. Only the
far-side track is clustered — the microphone is the operator by construction (**R2**), and a
microphone shared with a room would need the same treatment and does not get it.

⚠️ **`pyannote` has never been installed or run here.** Everything above is tested without it,
which is the honest limit of what can be tested without it: the install path, the real
`Pipeline.from_pretrained` call, the clustering quality and the token flow are all **unverified**.
The first press is the first run.

⚠️ **A guess needs a known surname.** The first version matched "any one to three characters"
before a title and produced `那李主席` — it absorbed the preceding particle. It is anchored on a
surname list now, so a name the list does not know yields **no guess rather than a wrong one**. An
empty row asks a question; a wrong row answers one.

## 🔄 The ASR model changed on supply-chain grounds — 2026-08-17

**`Qwen/Qwen3-ASR-0.6B` is out; `mlx-community/whisper-large-v3-turbo` is in.** The operator raised
that the weights are Alibaba's and the MLX port is maintained from the same region, which is a
procurement question in the proceedings this product is built for. That became **R50** —
provenance outranks measurement — and `docs/decisions/0012` carries the survey of every model and
package, the reproduction of the old comparison, and what the change cost.

**What is verified by having been run**, not merely tested:

- The product path — `transcriber.resolve_backend` on the shipped default, offline, out of the
  product storage root — transcribed a Chinese fixture correctly, released its weights and
  reloaded them.
- `release_models()` frees essentially the whole warm allocation through the new backend's holder
  (**V71**). The old figure belonged to a package that is no longer installed.
- The 2026-08-11 bake-off reproduced on today's toolchain to three decimal places on CER and
  exactly on peak memory, so `docs/decisions/0009`'s table is still trustworthy where this change
  does not overwrite it.

**The honest cost, stated where it cannot be missed:** this is a **regression on R37**, the
criterion REQUIREMENTS ranks first, and it is much larger than `docs/decisions/0009` could have
known. On **real** non-speech — the same 253 segments **V60** used — the removed model produced
text on **23**; this one produces text on **252**, and **243** reach the buffer (**V72**). On the
synthesized fixtures it is 63 of 63 against 0 of 63. Code-switch CER goes from 0.085 to 0.214, and
run-to-run variability from CER 0.025 to 0.167 (**V58**). Both models fail **R37** on their own —
that was already true — but not by the same margin, and pretending otherwise would be the wrong
lesson to leave here.

**Two things the next session should not re-derive:**

- **Whisper has decoder gates the removed model did not have at all** — a temperature ladder,
  `logprob_threshold`, `no_speech_threshold` and `compression_ratio_threshold`. Whether they buy
  **R37** back, and what they cost on **R8**, is measured by `tools/measure_decode_thresholds.py`.
  The product ships the stock values until that says otherwise.
- **Two ways to attack the false lines, both the operator's call, neither taken.** **V72** now
  shows what the model actually invents, and it is subtitle-corpus wreckage —
  `Субтитры сделал DimaTorzok`, `ご視聴ありがとうございました`, `Applaudissements`,
  `We'll be right back.`, `Thank you.` everywhere.

  1. **Restore `HALLUCINATION_PHRASES`.** It was fitted to exactly these strings and emptied on
     2026-08-12 because the model then shipping produced **none** of them. That model is gone and
     Whisper is back, so the list did not stop being right — the thing it was written for
     returned. Restoring it still reverses an operator decision with recorded reasoning, so it is
     theirs.
  2. **A script gate**, which is *not* what was decided against. Drop a line whose script is
     neither Chinese nor Latin. It reaches the Russian, Japanese and Korean ghosts that no
     deployment-specific list could anticipate, and destroys nothing a participant in this
     product's meetings would say. **R8** already draws that language boundary.

  **Carry the counter-argument with either one:** `Thank you.` and `I don't know.` are ordinary
  meeting speech, and laughter produced `I'm so sorry. I would like to come to town.` — a fluent
  invented sentence neither mechanism reaches.

**One defect found and deliberately not fixed, because it is not what was asked for.** The refusal
of a removed model id lands in `transcriber.resolve_backend`, which runs during warm-up — but
`app.py` calls `bootstrap.download_models` *first*. So an operator on a fresh machine whose `.env`
still names the old model **downloads 1.2 GB of weights and is then told they cannot be used**.
Verified by reading `app.py`'s start path, not by running it. The failure itself is correct and
legible — `warm_up`'s exception is caught and its message is shown verbatim, so the operator reads
the R50 reason and what to set instead — it is only wasteful, and only on a machine that does not
already have the weights. The clean fix is to refuse where the id first appears, or to surface it
on the settings screen next to `render_model_availability` so Start is never the place it is
discovered (**R40**).

### What "completely replaced" would mean, and what is still missing

The operator asked on 2026-08-18 what remains before the new model can be called a complete
replacement. **The test used here: every constraint that was measured on the removed model, and
that informs a product decision, has an equivalent measurement on the shipped one.** By that test:

**Done** — R37 on synthesized (63/63) and real (**V72**) non-speech; **R8**/**R10** through the VAD
path; CER mixed/zh/en, reproduced three times independently; single-track latency and peak memory;
`release_models()` (**V71**); the five-arm decoding sweep (**V73**); biasing (**V74**); the
non-speech cost penalty (**V75**); **V64** re-checked; and the product path run offline end to end.

**Still missing, and this is the list that matters:**

| # | Missing | Why it is a gap | Whose |
|---|---|---|---|
| 1 | **Dual-track** — **V56**, **V58**, **V67** | 2x per call, +371 MB weight sharing, 1.47x at conversational pace are **all the removed model's numbers**, and dual-track is the product's actual configuration | mine |
| 2 | **The one-hour soak** — **V58**, **V65**, **V69** | The only experiment that answers "will it survive a real meeting" without one | mine |
| 3 | **V41, music with vocals** | Open and untested since 2026-08-11, and the most dangerous gap after **V72**. MUSAN is fetched | mine |
| 4 | **V70 speaker leakage** | 61% is the removed model's figure; the replacement is far more eager on degraded input | mine |
| 5 | **V66 segmentation** | The 0.4 s flush was chosen against the removed model | mine |
| 6 | **The removed model re-run on today's toolchain** | Makes the comparison same-day rather than cited across four days | mine |
| 7 | **What greedy costs on degraded speech** | **V73** flags it unmeasured, and it gates adopting the free 3.4x | mine |
| 8 | **`large-v3` + tightened `logprob_threshold`** | Opened by **V73**'s corrected mechanism; may actually reach **R37** | mine |
| 9 | **R10 quantified** | Only the observation "simplified-leaning" exists, no number | mine |
| 10 | **V52 browser-session latency tail** | Needs Streamlit and real tabs | **operator** |
| 11 | **The real meeting** | Theirs by definition, and deliberately last | **operator** |

Nine of the eleven need nobody. Suggested order: **8** (may change the product decision), **3**
(most dangerous unknown), **2** (the one that would stop a real meeting failing), then 1, 6, 4, 5,
7, 9.

### The queue authorised for the night of 2026-08-17, in order

The operator authorised unattended work, benchmark downloads, audio playback in the room, and
local commits — **not `git push`**. Written down because a cold reader otherwise cannot tell an
authorised overnight run from an agent inventing work.

1. ✅ **`tools/measure_decode_thresholds.py`** — done, **V73**. Five arms, all 253/253, CER
   identical. No decoding setting buys back **R37**; the ladder costs 3.4x and prevents nothing.
2. ✅ **`tools/measure_biasing.py`** — done, **V74**. `initial_prompt` reaches 10 of 11 rare terms
   against 4 unbiased, **improves** CER 5.8x, and produces zero **R38** language flips and zero
   decoy insertions. The re-listening pass's biasing survives the backend change intact.
2b. ✅ **The decoder-depth question — answered, and it closed the audio-side search.** **V76**,
   **V77**. Turbo's no-speech head reports **0.000** and cannot arm its own gate; full `large-v3`'s
   reports 0.903 and works. But **every audio-side lever moves false lines and real quiet speech
   together**, because the two populations overlap: `large-v3` + a tightened gate reaches 39/253
   on non-speech — near the model this product gave up — while destroying **92 real utterances**
   to remove 131 false ones. Under **V64** that is not a trade worth making.

   **So there is nothing left to try on the audio side.** The remaining levers are text-side and
   both are the operator's (**V72**): restore `HALLUCINATION_PHRASES`, or add a script gate.
2c. ✅ **The control ran, and it decided the comparison against us.** **V77**: the removed model
   scores 23/253 on non-speech *and* 203/204 on degraded speech — identical to the shipping
   model's 203/204. **Its silence was free.** So **R50**'s cost is now a number: ~230 additional
   invented lines per 253 non-speech segments, for no accuracy or memory benefit.
2d. ✅ **Text-side filters scored — the only efficient lever, and still not enough.** **V78**:
   5.6 ghosts removed per real utterance lost against the audio side's 1.4, and zero clean speech
   touched — but 42% removal leaves ~146 invented lines against 23. **No available mitigation
   returns this product to where it was**, and that is a finding rather than a step toward one.

2e. ✅ **V41 answered — and it is total failure.** **V79**: 154 of 154 music segments produce text,
   151 reach the buffer, including **verbatim Italian lyrics**. The failure REQUIREMENTS names by
   example is reproduced exactly.
2f. ✅ **The stage nobody had searched, and it changes the recommendation.** **V80**: a neural VAD
   in front of the decoder rejects **231 of 253** non-speech segments, **54 of 56** instrumental
   music segments, and **zero** clean speech. That is **22 reaching the decoder against the
   removed model's 23 — parity on R37, with OpenAI weights, inside R50.** The earlier conclusion
   that the audio side was exhausted had swept the *decoder* and never looked in front of it; the
   253 segments were simply what `webrtcvad` at aggressiveness 3 had already passed. This is what
   `faster-whisper` and WhisperX ship, and structurally what the removed model did internally.

2g. ✅ **Decided 2026-08-18: `pyannote`, at a 0.25 s speech floor.** **V82**, `docs/decisions/0013`.
   It rejects 65% of non-speech for **3%** of real speech where Silero rejects 91% for 28%; under
   **V64** that is the better trade, and it is also the operator's provenance choice. The knee is
   sharp — every setting above 0.25 s is a worse bargain than the one before.

   **The record exists because this reverses `diarize.py`'s "never in `requirements.txt`".** 47
   packages including a telemetry framework and a cloud SDK become always-present, so **R15**
   stops being *checkable from the dependency list* — still true, no longer verifiable the same
   way. Accepted with the cost stated first.

**Next, in order, and none of it needs the operator:**

1. **The gate's own latency.** Unmeasured, lands in **R9**'s budget, and CPU-versus-Metal matters
   because Metal contends with MLX. **Measure on a quiet machine** — a number taken under a soak
   is one I would have to disown.
2. **Wire it into `transcriber.py`** between segmentation and `inference_queue.put`, so rejected
   audio never occupies the queue at all — which also avoids **V75**'s 3.4x non-speech decode cost.
   Then correct `diarize.py`'s docstring and `README.md`'s offline claim, which will otherwise
   contradict the build.
3. **Re-run V72's probe with the gate in place**, to get the shipped false-line number rather than
   an inferred one, and **compose it with V78's text filters**, which has not been measured.
4. The 60-minute soak, dual-track (**V56**/**V67**), segmentation (**V66**), leakage (**V70**),
   and **R10** quantified.

⚠️ **Whatever is chosen, sung vocals remain.** 15 of 56 vocal-music segments still reach the
decoder, because singing is voice and a voice detector is right to pass it (**V80**). **V79**'s
risk falls by roughly three quarters and does not go away.
3. **The same suite against `Qwen/Qwen3-ASR-0.6B`**, on today's toolchain rather than quoted from
   2026-08-12: bake-off, real-speech CER, and `probe_nonspeech_real.py`. The product refuses that
   id (**R50**); the harness reaches it through `asr_bakeoff.backend_kind_for`, which exists for
   exactly this and lives in `tools/` rather than `src/`. Verified loading before the queue was
   started, so an overnight failure is a result and not a wiring error.
4. **`tools/probe_music.py`** — **V41**, open and untested since 2026-08-11 and now the most
   dangerous gap in the file. MUSAN's music subset, split by its own vocals flag. The existing
   `fixtures/asr/nonspeech/music/` clips are programmatic sine stacks and cannot answer it.
5. **Acoustic runs, played out loud.** The operator cleared both the noise question and playing
   benchmark audio through the speakers on 2026-08-17. **This is worth more than it first
   looks:** `afplay` sending a corpus to the speakers is *process audio*, so the system-audio tap
   captures it as the `Participant` track **while the microphone picks up the acoustic leak as the
   `Operator` track**. That is the product's real dual-track configuration, with real recorded
   speech, through the real device path — everything a meeting exercises except a person.

   It reaches, in one arrangement: **V70**'s leakage proportion (now against known ground truth
   rather than against another transcript), **V62**'s end-to-end capture, **V63**'s output-device
   independence, and the dual-track half of **V56** / **V67**. `feed_wav` was built to *avoid*
   speaker→mic acoustics; this deliberately does the opposite, because the acoustics are the
   thing **V70** is about.

   **It is not a substitute for the real meeting**, which stays last by the operator's
   instruction — no turn-taking, no interruption, no one reacting to the screen.
6. **The one-hour soak against the new model** — **V58**, **V65** and **V69** in one run: does the
   pipeline survive an hour, do two `Transcriber` instances share weights, does memory drift, and
   how variable is the transcript run to run. All three were measured on the model that was
   removed. This is the only experiment that answers *"will it hold up in a real meeting"* without
   a real meeting.
7. **`tools/measure_segmentation.py`** against both models — see below.

⚠️⚠️ **An unattended queue dies at the first command that needs permission, and the guard against
sleep is what needs it.** This cost the night of 2026-08-17: a run launched at 22:35 had produced
**7m44s of elapsed time by 05:00**, and the session had diagnosed it — wrongly, and then written
the wrong diagnosis down here — as the machine sleeping after a `caffeinate -t` expired. **It was
not sleep.** The command was sitting on a permission prompt, and the operator was asleep and could
not press it. The correction came from the operator, not from the evidence, which is the part worth
noticing: `ps etime` excludes *both* sleep and never-having-started, so the two are
indistinguishable from inside.

**The specific trap, and it is self-inflicted.** Every measurement run here is wrapped in
`caffeinate -dis …` so it survives idle sleep. That makes the *command* a `caffeinate` command —
and `caffeinate` was not in the permission allowlist, so every run prompted. The protection
against one failure created another.

**Before starting an unattended queue, confirm the allowlist covers the wrapper, not just the
interpreter.** `.claude/settings.local.json` needs `Bash(caffeinate:*)` alongside
`Bash(.venv/bin/python:*)` and `Bash(.venv-bakeoff/bin/python:*)`. An agent cannot add these
itself — the auto-mode classifier refuses to let one grant itself permissions, which is correct —
so it is an operator action and it belongs in the handover, not in an agent's plan.

**Sizing `caffeinate -t` to the whole queue is still right**, and is a separate precaution from
this one; it simply was not what went wrong.

⚠️ **Wrap every run in `caffeinate -dis`, and check the machine's state before starting — both
holes were found the hard way on 2026-08-17.** `pmset -g custom` on this machine says `sleep 1`,
and the machine entered sleep **four times** between 19:37 and 20:46 while a measurement was
running unwrapped; the only assertion up was an agent session's renewing `caffeinate`, the
expiring kind **V67**'s note names. `-d` is not belt-and-braces: the events were
`Dark Wake Thermal Emergency`, reached *through* dark wake after the 5-minute display sleep, so
holding the display up is what removes the path into them. Separately, `output muted` was **true**
with volume at 81 — an acoustic run would have played nothing and, per `soak_capture.py`'s own
record, reported itself healthy while measuring silence.

**Every one of these runs at 3 minutes, then 10, then 60 — the operator's instruction, 2026-08-17,
and it is the house rule about occupying the machine made concrete.** The 3-minute rung is not a
smoke test to be skipped when confident: it is where a wrong device, a silent track, a mis-set
volume or a harness fault shows up for the price of three minutes instead of an hour. **Stop
climbing the moment a rung answers the question** — if the 10-minute run already separates
"survives" from "does not", the 60-minute run buys a number, not a decision, and a measurement
whose result cannot move a decision is not worth its GPU time (`docs/decisions/0009` cancelled one
on exactly that reasoning).

### The next test, named so it does not have to be rediscovered

**`tools/measure_segmentation.py` against the new model.** **V66** chose the 0.4 s silence flush by
comparing 0.4 / 0.8 / 1.5 s and fixed 8 s windows, and its **R37** column was measured on the model
that has been removed. Two of its three axes are model-dependent and one is not: the latency
argument survives untouched (segment close dominates, and that is arithmetic about silence, not
about the decoder), but the CER ranking and the false-line column both have to be re-read. The tool
now takes `--model`, so it is one command.

**Deferred deliberately, not forgotten.** It was ranked below the threshold sweep because it
compares *segmentation* strategies, and if a decoding change turns out to alter the false-line rate
by an order of magnitude then every row of the segmentation table would have to be produced again
anyway. Run it after the decoding question is settled, not before.

**Not re-run, and it does not need to be:** the **V57** / **V58** `NPU_LOCK` trials. The lock was
kept on the grounds that removing it bought 0% because there is one GPU — an argument about the
hardware, not about which model is loaded — and two independent models already agreed on it.

## 🐛 Known Issues

- **Every latency constraint in this repo measures the minority term, and the majority term is
  measured nowhere.** Found 2026-08-12 while asking whether the realtime arm was worth its runtime.

  `elapsed_ms` in `src/transcriber.py` starts its clock *after* `inference_queue.get()` returns, so
  it is lock wait plus inference and nothing else. **V51**, **V52**, **V55**, **V56**, **V57** and
  **V58** all report that same quantity — `tools/measure_overlap_turns.py`'s docstring says so
  explicitly, which is what makes those tables comparable to each other.

  **It is under a fifth of what a user waits.** **V66** puts the wait for the first word at
  **3.75 s** in production against 637–715 ms of inference; the rest is segment close (median
  segment 3.03 s plus the 0.4 s silence flush). Optimising the inference term to convergence leaves
  the number a person notices almost unchanged.

  **Queue wait is the part nobody has measured.** Harmless while people take turns, because the
  queue stays near empty. The case to worry about is a burst: continuous speech hits
  `max_speech_chunks` (15 s), several segments close in sequence, and the wait behind them is
  bounded by nothing. No measurement here would show it — and a contention scorer would read that
  burst as *low* contention, because contention is observed only on the inference window.

  **Not verified:** whether any decision was actually taken on the strength of the dual-track 2x.
  The risk being recorded is that the docs framed it as the headline, so the next reader optimises
  the wrong term. The overreaching sentence in **V56** was withdrawn the same day.

- **The filter probe is finished, and it corrected the reason the blacklist was emptied.** Full
  result is **V60**; read that, not a summary. Short version: the `0/63` behind
  `docs/decisions/0009` was 63 synthesized sounds and does not generalise — on real non-speech it is
  **23 / 253**, from laughter, coughing, sneezing and room tone below −45 dBFS with no speech in it.
  **R37 is therefore not satisfied by the model alone.**

  **The list still stays empty**, on a narrower argument than before: all eight deleted strings match
  **none** of what the probe produced, and the one output that would actually mislead a speaker —
  laughter yielding `I would like to come for tea.` — is exactly the kind no list can anticipate.

  **The operator decided 2026-08-12 not to chase this**, and V60 records why: denoising belongs to
  whatever app produced the audio, we inherit its result, and we cannot detect how much it already
  did. Nothing enters the live path. Removal is the cleanup pass's job (**R49**).

  **Two corrections against earlier notes in this file, so the next reader is not misled by them.**
  An entry written at 05:47 from an incomplete pass reported `real: 2/84`; a later one reported
  `14/186` and concluded every miss came from a human throat. Both were wrong in the same way — the
  room-tone files were bucketed with speech-derived material, so genuine non-speech was undercounted
  and the throat conclusion did not survive contact with the full set. **Neither number should be
  quoted; V60 is the record.**

- **What has and has not been run, as of 2026-08-10.** The venv was repaired on that date
  (`portaudio` via Homebrew, then `pip install -r requirements.txt`: `mlx` 0.29.3,
  `mlx-whisper` 0.4.3, `webrtcvad` 2.0.10, `sounddevice` 0.5.5). BlackHole was **not** installed —
  it is not needed for any of the below, and taking it out of the install path is the process-tap
  item's job (**R6**).

  **Executed and observed:** weights download to `<root>/AegisPrompter/models/hub/...` and *not*
  to `~/.cache/huggingface` (**V19** is now measured, not inferred); a second launch resolves them
  from cache with nothing refetched (**V47**); `warm_up()` loads the model in ~3.4 s, is
  idempotent, leaves `is_running` false, and **opens no audio device** (**R24**, **R25**); a
  missing system-audio device degrades to a warning and a silent Participant track rather than a
  crash (**R39**).

  ✅ **Executed 2026-08-12, and it works — see V62.** Start, both tracks, the VAD and inference
  threads, and `stop_recording` all ran end to end via `tools/verify_capture_end_to_end.py`:
  3 of 3 system-audio lines transcribed correctly at 640–826 ms, roles correct, clean teardown.

  🟡 **The web path is exercised; one clause of this entry survives. Corrected 2026-08-12 — it said
  "nobody has pressed Start in a browser" while four other places in this file and `REQUIREMENTS.md`
  record that someone had.** V62 itself drove `GlobalState` directly, which is what this entry
  originally described, but the browser-driven session that followed is what found the six defects in
  the lesson above.

  **What remains is narrower than the old wording**: no **second physical device** has followed into
  the transcript. The recorded evidence says "two browsers polling" without saying whether they were
  two tabs here or a separate machine, and only a separate machine exercises `is_local` (**V37**),
  the remote-device gate (**R34**) and the waiting state (**R35**). `test_app_screens.py` covers the
  screens through Streamlit's harness, which is neither a person nor a second device.
- **The RAG advisor's liveness is visible before a meeting but not during one** — see **V34**. The
  pre-flight panel now reports chunk count and build date, and refuses to arm an empty index, so a
  missing or unbuilt index is caught before Start. What is still missing is the *running* signal: an
  armed advisor that matches nothing looks identical to a dead one. Closed by the advisor-backend
  item's liveness work (**R36**, **V35**).
- **Changing the ASR model needs a process restart, where the requirement asks for a re-warm.**
  The enablement table in [REQUIREMENTS.md](REQUIREMENTS.md) says the field returns the app to
  `warming` (**V33**). This build demands a full restart instead, and `fingerprint()` enforces it.
  **The reason is not `HF_HOME`** — that path derives from the storage root alone, so an
  ASR-model change leaves it byte-identical, and **V19** does not apply to this field. The real
  reason is narrower: `warm_up()` is idempotent, so a second call with a different model returns
  immediately and the old one stays loaded. Without the restart the app would silently transcribe
  with the model the operator just replaced. **Satisfying the requirement means giving `warm_up()`
  a reload path** — discard both `Transcriber` instances and re-enter `warming` — after which
  `ASR_MODEL` can leave the restart fingerprint. Recorded here rather than resolved by rewording
  the table, which was attempted in `ad36867` and reverted.
- **Download progress under-reports on a resumed fetch.** The numerator is bytes *added* since the
  watch began, which is what stops leftover blobs from an earlier revision pinning the bar at 100%.
  The cost is the mirror case: an interrupted download that resumes counts only the remainder
  against the full total, so it finishes reporting roughly half. The bar still moves and the
  `finished` flag still drives completion correctly, so nothing is misreported as done — the
  percentage is simply low. Fix by counting only the current revision's files, which needs the
  per-file metadata already fetched for the denominator.
- **The retention toggle persists a preference and records nothing.** Shipped deliberately with the
  configuration item and labelled as such on the panel (**R46**), but until the retention item lands,
  a session marked "retain" produces no audio. Do not rely on it for corroboration (**R45**).
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
- **Observed 2026-08-10, no longer a prediction:** on this MacBook Pro the device actually selected
  was `MacBook Pro Microphone (System Default)` — neither keyword matched and the fallback carried
  it.
- `global_state.py` looks for `["MacBook Air Microphone", "Built-in Microphone"]`. On a MacBook
  Pro neither matches, so microphone selection silently relies on `fallback_to_default`. The
  result is usually correct, but the keyword list is not doing its job. Superseded by the
  microphone-selection item.
- Capturing the far end currently requires the BlackHole driver *plus* a manually configured
  Multi-Output Device, or the operator cannot hear the meeting while it is captured. Superseded
  by the process-tap item.
- **`V12` is still unverified and is now on the critical path** for both the process tap and
  retention. Building either against an assumed resample behaviour is how hearings lose audio.
- **The application cannot download a model on this machine, and the error will read as "no
  internet".** Confirmed 2026-08-19: `huggingface_hub` fails every request with
  `CERTIFICATE_VERIFY_FAILED` against a Cloudflare `Gateway CA` in the System keychain, while
  `curl` and `pip` reach the same URLs fine. So `bootstrap.download_models` and the settings page's
  availability check are both dead here, and the failure surfaces as `LocalEntryNotFoundError`,
  whose message asks the operator to check their connection.

  **Nothing is broken today** — every weight the product needs is cached, and the runtime enforces
  offline anyway (**R15**), so the live path never asks. **It bites the first time a model id
  changes**, which is a plausible thing to do shortly before a meeting.

  Workaround, and it needs no change to what any tool trusts:
  `tools/hf_curl_place.py <hub-dir> <repo-id> <file>...` fetches with `curl` and writes the cache
  layout. Used for the diarization weights (**V93**) and the voice gate's (**V91**). Gated
  repositories still answer 401 and still need a token.

  The alternative — exporting `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` from a bundle containing the
  interception certificate — was offered and **declined by the operator on 2026-08-19**, on the
  grounds that what the tooling trusts should not change to save some fetching. Recorded so it is
  not re-proposed as an obvious fix.

- **`V45` folder chooser still untested.** Configure ships the validated text field as the primary
  input with the native dialog behind an opt-in button, precisely because no Streamlit callback has
  yet been observed raising one without deadlocking the rerun. Measure before promoting it.
- ~~**`ASR_MODEL` still defaults to an English-only model.**~~ **Resolved.** The shipped default is
  `mlx-community/whisper-large-v3-turbo` (`src/bootstrap.py`, `.env.example`), and it does Chinese —
  **V87** and **V90** are scored on its Chinese output. The English-only
  `mlx-community/distil-whisper-large-v3` this bullet named (**V1**, blocking **R8**) has not been the
  default since the model swap of 2026-08-17. Kept struck through rather than deleted only because the
  bullet was quoted as live in earlier sessions; the successor concern is **V90** — 88% of that Chinese
  output is Simplified where **R10** wants Traditional.
