# Requirements

> ## ⚠️ Read this before trusting any `V*`
>
> **Every verified constraint below describes `main`.** There is an unmerged branch,
> `origin/feat/streaming-transcriber`, whose `src/transcriber.py` **contradicts several of them** —
> it already replaces the VAD pipeline, changes the default ASR model, and writes per-track WAVs
> (**V49**). `main`'s `src/` is byte-identical to that branch's fork point, so it still applies
> cleanly; the branch is unverified on live audio, not abandoned.
>
> So before reasoning from a `V*`: **establish which tree you are talking about.** A constraint that
> is true of `main` and false of that branch is not a contradiction in this document — it is a
> question about which code will exist when the work lands. `V1`, `V4`, `V5` and the
> `transcriber.py` line references throughout are statements about `main` only.
>
> **That branch has now been evaluated** — see `docs/decisions/0006`, which sorts every piece of it
> into adopt / adopt-after-rework / re-derive / discard. Nothing has been merged, so the warning above
> still describes the tree. What changed is that the disagreements are now catalogued instead of
> merely suspected.

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
> **We do not throw it away on our own initiative, and we offer you the means to keep it.
> What it gets used for is the file owner's decision.**

The first sentence makes capture **source-agnostic**. It does not matter whether the meeting
runs in Zoom's native app, Meet in a browser tab, Teams, or anything else.

The second draws the **product boundary**: the system does not decide, on its own, that something
was not worth keeping — but nor does it promise completeness it cannot deliver. **Reworded
2026-08-12 with R3**, which used to claim completeness of capture as the system's responsibility
while the live path was measurably discarding material (**V48**). Retention is offered; keeping it
is the operator's decision. Retention, cleanup, redaction, disclosure,
and which advisor backend is appropriate are the operator's calls — which is why post-processing,
audio retention, and the advisor slots are opt-in tools rather than pipeline behaviour.

> **Show the judgement, do not make it.**

Recorded 2026-08-12, after three separate decisions took the same shape on the same day. Where the
system could either build a mechanism that decides on the operator's behalf, or surface what it
knows and let a person decide, it surfaces:

| Question | Mechanism rejected | What ships instead |
|---|---|---|
| Should context biasing run? | A switch that improves names live and can flip the output language | It runs in the cleanup pass, where the operator reads the result first (**R9**) |
| Is the LLM backend alive and sane? | A liveness signal the app computes and interprets | An optional rehearsal: the operator's own questions, their endpoint, their judgement |
| Which advisor wins when both are configured? | Score-band routing arbitrating between them | Both are shown, each labelled with its source (**R29**, **R42**) |

The pattern is not modesty about the system's abilities. It is that each of these judgements needs
context the system does not have — what this meeting is about, whether this model can be trusted,
which cue is worth reading aloud right now — and a mechanism that fakes having it produces
confident answers nobody can check. It also keeps the failure visible: a person who has seen the
output can notice it is wrong, where a gate that silently withheld it leaves nothing to notice.

> **A bare `except` is how this codebase fails. Watch for it in the code you just wrote.**

Recorded 2026-08-12 after it happened **three times in one day**, twice in changes whose stated
purpose was to stop exactly this:

| Where | What it hid |
|---|---|
| `app.py`, applying the microphone choice | The dropdown showed the operator's device while the engine kept the old one, and nothing said they disagreed — introduced by the commit that added the dropdown |
| `system_audio`, the first version of the PortAudio wait | A tap published and never seen; every log line reported success over a silent Participant track |
| `tools/measure_segmentation.py`, around `webrtcvad` | A type error made every frame non-speech, so all four strategies reported zero segments and a tidy CER of 1.0 |

The pattern is not carelessness about errors. It is that **this system's characteristic failure
does not raise** — a device published but invisible, a preference shown but unapplied, an offline
flag set but never read, a segmenter that finds nothing. Each produces a plausible empty result,
and a `try`/`except` around the one line that would have complained converts a loud failure into a
quiet wrong answer.

**So the test when adding anything is: what does this print when it fails?** If the answer is
"nothing", that is the defect, not the error handling. Catch an exception only where the caller can
do something else with the information — the fallback from tap to BlackHole is a fair example,
because it degrades *and says so* (**R39**). Catching to keep going is not error handling; it is
choosing to be wrong silently.

> **Simulate everything that can be simulated. What resists simulation is telling you something.**

Stated by the operator 2026-08-12, after asking whether an hour-long capture proof needed a real
meeting. It did not, and the reasoning generalises past scheduling: **whether a thing can be
exercised without a person in the room is a measure of how well it is abstracted.** A component
that can only be tested by holding a meeting is a component fused to its context.

The practical order is therefore: **simulate first, and treat what is left over as the finding.**
Applied to the capture item the same day, that turned "prove it in a real meeting" — one opaque
block — into four:

| | How it was settled |
|---|---|
| Does the machinery hold for an hour? | Simulated — **V65** |
| Does the transcript clear **R9**'s gist bar? | A person read the simulated hour |
| Overlap and interruption at hearing density | Simulable — the fixture builder can generate it |
| The microphone device sustained for an hour | Simulable — play into the room and let it listen |

None of those needed a meeting, and the two still open are open only because nobody has built the
fixtures yet.

**What genuinely resists simulation goes last, and goes to a real meeting**: a real room, real
people, real stakes, and an operator who has to act on what is on the screen. That is validation,
not testing, and it belongs at the end of a phase rather than blocking the middle of it — a
verdict from a real meeting is worth having only once everything cheaper has already been ruled
out as the cause.

> **Garbage in, garbage out — and that is not our problem to solve.**

Recorded 2026-08-12, from the operator, generalising a decision about laughter and room noise
(**V60**) into a boundary the whole product sits behind.

The input is somebody else's environment. **Denoising happens in whatever application produced the
audio and we inherit its result** — a Zoom call arrives suppressed, a Lark call arrives raw, and we
cannot detect which. The meeting itself is the same: without the screen being shared, half of what
is said has no recoverable referent, and no amount of transcription accuracy recovers it. A system
that tried to compensate for either would be guessing at what it could not observe, which is the
same failure as the stance above.

So the product does not add noise reduction, does not suppress laughter, and does not attempt to
infer meaning the audio does not carry. **It transcribes what arrives.** Improving the input is the
operator's lever — a better microphone, a quieter room, sharing the screen — and it is a real lever,
which is why leaving it with them is not an evasion.

**The one thing this does not license.** GIGO holds when bad output is *legibly* bad. What **V60**
found is different: laughter produced `I would like to come for tea.` — fluent, terminated normally,
indistinguishable from a real line. That is garbage in and *confident* out, and no operator reading
a live transcript can catch it. The product's answer is already chosen and needs no new mechanism:
the live path is scoped to the gist (**R9**), and the post-meeting cleanup pass (**R49**) is where a
human reads the whole transcript before anyone acts on it. **Marking suspect lines in the live view
was considered and rejected** on 2026-08-12 — a confidence badge is a judgement the system cannot
support, and the stance above applies to it.


---

# 📋 Requirements

Stated without implementation. Each item is something the product must do, or must not do.

## Capture

- **R1 — Source-agnostic.** Capture must work regardless of where the meeting runs: Zoom app,
  Zoom web, Meet, Teams, or anything else. The system must not need to know or be told.
- **R2 — Two tracks, never mixed.** What the operator *hears* (system output) and what the
  operator *says* (microphone) are separate tracks and stay separate all the way through.

  **Why, recorded 2026-08-12 — it had been stated as a bare rule since Phase 6 and the reasoning
  existed only in conversation.** Mixing is the cheaper implementation and will be proposed again,
  so the three costs are written down rather than rediscovered:

  1. **Attribution becomes impossible, not merely harder.** A mixed track cannot separate "me" from
     "them", which is the one distinction the product is built on — **R12** asks to tell individual
     remote speakers apart, and a teleprompter that cues the operator has to know whether the
     operator was the one talking. This cannot be recovered downstream.
  2. **Overlap stops being a transcription problem and becomes an invention problem.** Two tracks
     make simultaneous speech structurally impossible to conflate; one track makes it routine, and
     **V60** measured what the shipped model does with overlapped speech: 2-talker cross-talk
     produced text on **20 of 20** segments, and it is fluent invented content (`The sky is blue.
     The sky is blue.`), not garbled transcription. The failure is confident, so nobody reading the
     live view catches it (see the GIGO stance above, which names exactly this limit). Note the
     honest bound: mixing does not degrade anything while only one side is speaking. It converts
     the moments when both speak from *separated* to *fabricated*, and in a hearing those moments
     are the contested ones.
  3. **Retention and cleanup are built on two files** (**R16**, **R49**). A mixed archive cannot be
     un-mixed, so this choice is not deferrable to post-processing.

  **What it does not require: asking the operator which microphone.** The Operator track needs *a*
  microphone, not a chosen one — **R26** grants a sensible default, freely overridable, and
  following the system default input satisfies R2 completely. Keeping the tracks apart and keeping
  the choice out of the operator's way are independent, and were briefly conflated on 2026-08-12.
- **R3 — Do not discard on the system's own initiative; offer the operator a way to keep the
  audio.** **Rewritten 2026-08-12 by the operator, replacing "Do not lose anything — completeness
  of capture is the system's responsibility."** The original was a guarantee the product could not
  keep and did not keep: **V48** shows the live path discards non-speech frames, sub-0.3 s
  segments and empty output before anything reaches the transcript, and with retention off
  (**R16**) none of it is recoverable. A promise contradicted by the default configuration is worse
  than no promise, because it stops anyone looking.

  What is required instead: the pipeline does not drop audio for its own convenience — no
  unsignalled buffer eviction, no silent frame loss under load — and the operator is offered
  dual-track retention (**R16**) as the way to keep what the transcript cannot. **Whether to keep
  it is their call, not a guarantee the system makes on their behalf** (**R4**).
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
  **The review flag this carried is closed, 2026-08-13, and the wording stands unchanged.** For a
  day, **R49** put an external command inside the app and left this requirement's "must remain
  intact" describing something that was intact by default and breakable by an act. **R49** was
  then rewritten so the app executes nothing at all, and the tension disappeared rather than
  being reworded away — which is the outcome this file is organised to prefer.
- **R16 — Dual-track audio may optionally be retained**, for post-processing and for
  **corroboration** — settling disputes about what was actually said. Retention is **off unless the
  operator has turned it on**, and the choice is **sticky**: once enabled it stays enabled on that
  machine until changed, because a per-meeting default of off means the one meeting that later turns
  out to matter is the one nobody armed.
- **R45 — What is lost by not retaining is lost irreversibly, and the operator must be able to tell
  afterwards whether a session was retained.** The transcript is a lossy interpretation: silence
  judgements, minimum-duration filters and hallucination filters each discard material, and none of it
  can be recovered from the text. Five capabilities exist only while the audio does — corroboration
  (**R16**), re-transcribing an archived meeting with a better model, acoustic speaker attribution as
  the fallback if text-only attribution proves inadequate (**R12**), reproducing a false trigger after
  the fact (**R37**), and verifying rather than merely re-flowing during cleanup (**R14**). So the
  session record must state whether audio was kept and where it went; otherwise "recorded and later
  deleted" and "never recorded" are indistinguishable, and **R4** makes deletion a normal event.
- **R46 — A sticky choice is disclosed every session, not merely applied.** Any setting that carries
  over from a previous run and changes what the system does to the operator's data must be visible on
  the pre-flight panel in its current state before Start is pressed. Persistence removes the need to
  re-decide; it must not remove the opportunity to notice.

## Supply chain

- **R50 — No model weights and no loader package in the shipped product may originate from a PRC
  vendor or maintainer.** This is a procurement constraint, not a quality judgement, and it
  therefore **outranks measurement**: it disqualifies candidates that win every column of the
  bake-off table. Stated by the operator 2026-08-17, when the model chosen on 2026-08-11 turned
  out to be Alibaba's weights behind a community port maintained from the same region — a property
  neither `docs/decisions/0008` nor `docs/decisions/0009` had asked about, because nothing in the
  harness measures it.

  **Where it binds:** anything the application downloads or imports by default — speech
  recognition, embeddings, optional speaker separation, and every Python dependency in
  `requirements.txt`. The survey against this rule is in `docs/decisions/0012`.

  **Where it does not, and why that is not a loophole:** the generative advisor is an
  OpenAI-compatible endpoint the operator supplies, and **R31** keeps this project from asserting
  a vendor there at all. It ships empty, so nothing is chosen on the operator's behalf; applying
  this rule to whatever they point it at is theirs, and `README.md` says so rather than letting
  the survey read as complete.

  **The wording is a floor, not the whole intent — clarified by the operator 2026-08-18.** The rule
  above bars PRC origin and is silent between, say, a Russian option and a French one. Asked to
  choose a voice-activity detector between exactly those two, the operator chose the French one and
  stated the frame: *非紅是這次的改動目標* — reducing this class of supply-chain exposure **is** the
  purpose of the change, not a box to tick. So where two candidates both clear the literal rule,
  **prefer the one that clears its intent by more**, and do not read a tie in the text as a tie in
  the decision. Recorded because the next reader will otherwise apply the sentence and miss the
  point (the standing rule about intent outranking wording, applied to this file's own wording).

  **What satisfying it does not buy.** It says nothing about whether a model is any good, and the
  cost of applying it here was real and is recorded rather than softened: the replacement is worse
  on **R37** and roughly 2.5x worse on **R8**. A future search must apply this rule *and* the
  bake-off, in that order — `model_search.build_search_prompt` carries it, because no Hugging Face
  metadata field expresses provenance and a search that leaves it implicit returns the
  disqualified models first.

## Configuration and startup

- **R17 — The local web page is the control surface.** Configuration belongs there.
- **R18 — The user must never hand-edit `.env`.**
- **R19 — Where weights are stored is the operator's choice**, not fixed by the project layout — see
  **R48** for the shape that choice takes —
  the weights are large and may not belong on the internal drive.
- **R20 — If configuration is absent, the web page asks for it.** No `.env`, or no cache path
  in it, must lead to a prompt rather than an error.
- **R21 — Nothing needs to be downloaded before the first cold start.** Launching must not
  presuppose that models were already fetched.
- **R22 — Reset means deleting `.env`**, by hand or by button, **and nothing else.** There must be no
  other configuration state to clear, and the reset must not touch anything on disk that is not
  configuration. Before deleting, it shows the paths that are about to stop being referenced — not so
  they can be removed, but because after the form goes blank they are the only way back to data that
  is still perfectly usable (**V47**).
- **R47 — The application never deletes captured material or downloaded caches.** Transcripts, audio
  archives and model weights are the operator's, and their removal is the operator's decision
  (**R4**). This is not merely a default: no code path in the application deletes them, because the
  directories holding them are operator-supplied strings (**R19**, **R44**) and a recursive delete
  against a typed path is an unacceptable operation. The UI may *locate* them; it may not remove them.
- **R23 — Setup progress must be visible**, including console output, while it happens.
- **R24 — Nothing is loaded until Start is pressed, and every session waits on one state.**
  **Rewritten 2026-08-14 by the operator.** Opening the application costs nothing: no download, no
  weights, no devices. Pressing Start fetches what is missing, warms the model, and opens the
  streams — reporting through a single process-global readiness state, so the wait looks the same
  from every browser that is logged in and none of them is let through early. **Stop releases the
  models**, so nothing of ours is in memory outside a capture.

  **The wording this replaces:** *"Start must be unavailable until warm-up is confirmed
  complete."* It was written from **V33**'s *"minutes, possibly preceded by a download"* and it
  was right about the cost being large. What it got wrong is which part is large: warm-up from a
  warm weight cache is **2.3 s** (**V61**); the minutes are the *download*, which is a separate
  step. Three things followed from the old rule and only the third is unfixable inside it:

  1. **Opening the app was not asking for anything**, yet it pulled gigabytes — on a metered
     connection, merely reading the settings did.
  2. **Weights sat in memory for hours** between opening the page and the meeting starting.
  3. **An early fetch can only ever fetch a guess.** Which model to fetch is not known until the
     operator has finished configuring. Save with the default, change `ASR_MODEL`, and the old
     build demanded a restart *while the multi-gigabyte download of the model just replaced ran
     to completion* — `set_readiness` revokes a stale boot only between repositories, and a
     `snapshot_download` in flight cannot be interrupted. There is no version of "early" that
     avoids this, which is what settles it.

  **R25 is unaffected and is now easier to hold**: capture still begins only on an explicit
  operator action, and that action is now the only thing in the product that costs anything.
- **R25 — Capture must not begin before authentication** and an explicit operator action.
- **R32 — `.env` is a snapshot of the settings form.** Values the operator typed are persisted
  and shown back on the next launch; absent configuration renders as **blank fields**, not an
  error. Credentials render masked, with a reveal toggle.
- **R33 — Persist what cannot be rediscovered; do not persist what would go stale.** A URL, a
  credential or a directory cannot be recovered at runtime, so it is stored. A device list is rebuilt
  on every launch, so storing a choice there would only create a stale reference to a name or index
  that has moved. The test is *rediscoverable versus stale-prone*, not typed versus clicked: an
  operator's standing preference — retain audio or not (**R16**) — is a switch rather than a typed
  value, but nothing on the machine can rediscover it and it cannot go stale, so it persists too.

## Device selection and pre-flight

- **R26 — Audio input is selectable from the web page**, in the manner of Zoom or Meet web:
  a sensible default, freely overridable.
- **R27 — Every per-meeting decision is made on one pre-Start panel.** The screen shown before
  capture begins is the single place the operator chooses the microphone and which advisors are
  active — reviewed together, then committed by pressing Start. Sticky machine preferences that
  also appear on that panel (**R16**, **R46**) are disclosed and may be changed there, but they
  are not per-meeting decisions. No per-meeting choice lives anywhere else.
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

- **R49 — The application performs no post-processing. It writes an instruction and stops.**
  **Rewritten 2026-08-13 by the operator, one day after it was added.** Every session transcript
  ends with a prompt block at a stable marker: what the file format is, how the transcript is
  lossy, where the retained audio is, and the three things to produce — a report, the meeting's
  topics, and a proofread transcript. The operator copies it into whatever agent they use, or
  scripts the extraction themselves. **No runtime code path executes a command, loads a model, or
  reaches the network**, which is what makes **R15** true without qualification.

  **The wording this replaces, quoted rather than deleted, because it was not foolish:**

  > *R49 — Post-meeting cleanup is armed before the meeting, on the pre-flight panel, and says
  > what it costs. Deciding afterwards is deciding at the worst moment: the operator has just
  > finished a hearing and is closing a laptop. The control must state three things at the moment
  > it is armed — what it changes about the transcript, that Stop will block until it completes,
  > and, if the chosen backend is not local, that the meeting text leaves the machine.*
  >
  > *Two backends, and the operator picks: the built-in local model, or an external command. The
  > external path is only available when the operator has typed the executable in full.*

  **What was wrong with it.** Its timing argument was borrowed from retention, where it is
  correct — unrecorded audio is gone, so the choice genuinely must be made in advance. A
  transcript on disk does not expire. Deciding tomorrow costs nothing, so pre-arming bought
  nothing and a blocking Stop bought less than it cost. And once the app runs nothing, the
  built-in model, the external command and the whole `CLEANUP_COMMAND` mechanism have no work
  left to do. **The requirement was changed rather than narrowed** — the implementation was not
  bent to fit the old text, and the old text is above so nobody re-derives it.

  **What survives from it**: that the operator, not the product, decides what happens to meeting
  content (**R4**), and that whatever leaves the machine leaves because someone chose to send it.
  The prompt block makes that maximally true — the app hands over a paragraph, and every
  subsequent step is theirs.

- **R36 — Any component whose normal output is "nothing" must expose a liveness signal.**
  Silence has to be distinguishable from failure, and the distinction must be visible *before*
  and *during* a meeting rather than discovered afterwards. The audio path already satisfies this
  with its level meters; the advisor path does not.

## The control surface

The web page *is* the product's only surface (**R17**), so its behaviour is a requirement, not a
design detail left to whoever implements it.

- **R38 — Operator-facing interface text is English**, like the rest of the codebase. **Content is
  not interface**: transcript lines, retrieved cues and generated advice appear in whatever language
  the meeting is conducted in, and nothing may translate or normalise them — that would break
  **R3**. The distinction is between the chrome and what flows through it. Keeping the chrome English
  means `AGENTS.md`'s English-only rule extends to displayed strings with no exception to police,
  and log files stay greppable against the interface they describe.
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
- **R44 — Retained audio is stored off the project tree**, for the same reason as the model cache
  (**R19**): two tracks reach roughly 690 MB for a three-hour hearing at the archived rate, and the
  operator may still not want it on the internal drive. Its location is derived from the storage root (**R48**) rather than typed
  separately, and may be overridden when weights and recordings belong on different volumes.
- **R48 — The operator chooses one storage root; the layout beneath it is fixed and owned by the
  application.**

  ```
  <storage root>/AegisPrompter/
  ├── models/     # HF_HOME — weights
  └── audio/      # retained dual-track WAVs, unless overridden
  ```

  One field instead of two, and — more importantly — **the paths are reproducible.** Re-entering the
  same root after a reset regenerates byte-identical paths, so an existing model cache is recognised
  and reused rather than re-downloaded (**V47**). It also lets the settings form *report* what it
  found — "existing cache detected, 3.4 GB, will be reused" — which turns re-entry from something the
  operator must get exactly right into something the app confirms. A freely-typed cache path cannot
  offer either property.

### Screens

Local states are **sequential**, not simultaneous: Access → Role → Configure → Pre-flight →
Running. Configure and Pre-flight are two states, not one combined page — the operator finishes
machine settings before the Start panel is offered. Remote devices never see Configure or
Pre-flight (**R34**); before Start they see the waiting state (**R35**).

| State | Local | Remote | Renders |
|---|---|---|---|
| Access | no prompt | access code | Remote entry only (**V37**, and the verdict must fail closed *loudly*) |
| Role | selection | selection | Speaker view vs staff view |
| Configure | settings form | **✗** | Blank on first run, refilled from `.env` afterwards |
| Pre-flight | full panel | **waiting state** | The single place per-meeting choices are made (**R27**, **R35**) |
| Running | transcript, advisor, meters, Stop | transcript, advisor, cue injection | Control actions are local-only (**R34**) |

### Persisted fields — the settings form

Typed, so they cannot be re-enumerated (**R33**). This inventory is normative; the plan implements
it rather than restating it. The `.env` key column is part of that inventory — inventing keys at
implementation time is how the template and the form drift apart.

| # | Field | `.env` key | Required | When absent |
|---|---|---|---|---|
| 1 | Storage root | `STORAGE_ROOT` | **yes** | Nothing to download weights into — the one field that blocks everything (**R48**) |
| 2 | Audio archive override | `AUDIO_ARCHIVE_DIR` | no | Recordings go to `<root>/AegisPrompter/audio` (**R44**) |
| 3 | Qdrant URL | `QDRANT_URL` | no | Local mode; RAG still works (**V29**) |
| 4 | Qdrant credential 🔒 | `QDRANT_API_KEY` | no | Local mode |
| 5 | Embedding model name | `EMBEDDING_MODEL` | no | Has a default |
| 6 | LLM base URL | `LLM_BASE_URL` | no | LLM advisor unavailable (**R28**) |
| 7 | LLM credential 🔒 | `LLM_API_KEY` | no | — |
| 8 | LLM model name | `LLM_MODEL` | no | Has a default |
| 9 | ASR model | `ASR_MODEL` | no | Has a default. Persisted rather than per-meeting — see *Decided and closed* |

Derived and written by the app, not typed as free-form settings fields: `HF_HOME` =
`<STORAGE_ROOT>/AegisPrompter/models` (**R48**), and `ARCHIVE_AUDIO` = the sticky retention
switch (**R16**).

Credential fields render as `type="password"` with a reveal toggle; the value behind them is always
the real one, never a sentinel (**R32**).

### Per-meeting controls — the pre-flight panel

Rebuilt from live enumeration and defaults on every launch, and — with one exception — not persisted
(**R33**). Pressing Start commits all of them for the session.

The exception is **retain dual-track audio**, which persists its own state (**R16**). It is a single
switch with a single behaviour: whatever it reads when Start is pressed becomes the machine's standing
preference. There is deliberately **no session-only override**, because one switch with two meanings —
sometimes remembered, sometimes not — is worse than either behaviour alone.

| Control | Kind | Default |
|---|---|---|
| Microphone | dropdown | system default (**R26**) |
| Retain dual-track audio | toggle, **and it persists its own state** | whatever it was last set to; off until first enabled (**R16**, **R46**) |
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
| **Retain dual-track audio** | always — the archive path is derived from the storage root, so it cannot be unconfigured (**R48**) | ⚠️ disk estimate for the expected meeting length, plus the reminder that recording carries consent expectations (**R4**). Because the switch is sticky, the warning appears when it is **turned on**, while the pre-flight panel shows the state it is already in on every subsequent run (**R46**) |
| Storage root | always | 📁 folder chooser (**V45**), then a report of what was found beneath it — existing cache size, existing recordings — before anything is written (**R48**) |
| Audio archive override | always | 📁 folder chooser (**V45**) |
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

## The application owns `.env`, which makes two mechanics load-bearing

- **V46 — A settings save rewrites the whole file, so it has to be atomic.** The form is the only
  writer (**R32**), and Streamlit re-executes the script on every interaction, so a crash or a rerun
  landing mid-write leaves a truncated `.env` that reads as a half-configured machine — and looks like
  operator error. Write to a temporary file in the same directory and `os.replace()` it, which is
  atomic on the same filesystem. Not measured; this is the standard mechanic, and the failure it
  prevents is silent.
- **V47 — Deleting `.env` does not cost the weights.** `huggingface_hub` stores blobs
  content-addressed under `models--<org>--<repo>/blobs/<sha>` and resolves a download by comparing the
  remote ETag against what is present, so an existing cache is reused and nothing is fetched twice.
  Read from the library's cache design, not measured here.

  Two failure modes are eliminated by two different mechanisms, and both are needed:

  | Failure | Removed by |
  |---|---|
  | Same path, redundant fetch of identical weights | content addressing — this constraint |
  | *Different* path after a reset, so a complete cache on the same machine is invisible and re-downloaded in full | the fixed layout under a re-entered root (**R48**) |

  A useful consequence: switching ASR models back and forth costs one download each, ever. Both sets
  of weights coexist in the cache and neither is refetched. That answers the disk half of **V33**'s
  open question; the memory half — whether `mlx_whisper` holds two models resident — remains untested.

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
- **V61 — The helper is real, and everything V7/V9/V10 claimed holds for it.** V6–V11 were
  measured in 2026-08-10 with a throwaway prototype that never entered the tree; `src/native/
  aegis_tap.m` exists as of 2026-08-12 and was measured on the same machine. It publishes
  **`Aegis System Audio`**, 48 kHz mono float32, and:

  - **Signal, not just frames.** Peak **0.256** over five seconds with a system sound playing,
    against peak **0.0** over four seconds of a silent machine. Both runs delivered ~48 k
    frames per second, so "frames arriving" alone would not have distinguished them.
  - **Visible cross-process as an ordinary input** (**V9** reproduced): a separate Python process
    enumerated it through PortAudio as a 1-channel input with a 48 kHz default, and opened it.
  - **Torn down cleanly** on SIGTERM in every run — no aggregate device survived the helper.

  **The mechanic that decides whether this ships working, corrected the same day it was written.**
  PortAudio caches its device table at initialisation, so a process that started before the helper
  cannot see the device however correct everything else is. The first version of this constraint
  said the fix was to call `sd._terminate()` / `sd._initialize()`. **That is not enough, and the
  gap is not intermittent — it is reliably wrong:**

  | Attempt | Saw the device |
  |---|---|
  | Re-initialise immediately after the helper reports it published | **0 of 5 trials** |
  | One more attempt 50 ms later | **5 of 5 trials** |

  Publishing an aggregate device and other processes' HAL clients learning about it are **separate
  events**. A single re-initialisation lands between them every time.

  That combination is the worst kind to ship: not flaky enough to catch by accident, not reliable
  enough to work. It would have produced sessions where the Participant track is silently empty
  while every log line reports a tap that started successfully — and nobody would look, because
  the failure announces success. `system_audio.wait_for_device` therefore **polls until the device
  appears, with a deadline**, and a device that never appears ends the attempt so the caller can
  fall back rather than proceed.
- **V62 — Capture has now been executed end to end, and it works. First run 2026-08-12.** Until
  this date every latency and accuracy figure in this file came from feeding WAV files to the
  transcriber; nothing below the point where a stream opens had ever run. `tools/
  verify_capture_end_to_end.py` reproduces it: warm the model through `GlobalState`, press Start,
  play synthesized speech through the system output, read the buffer, stop.

  | | |
  |---|---|
  | Backend chosen | `tap` — Core Audio process tap, no BlackHole on this machine |
  | Warm-up | **2.3 s** from a warm weight cache (**V33**'s minutes are the cold case) |
  | Participant lines | **3 of 3 correct**, 640 / 774 / 826 ms |
  | Track separation | held — every line carried the right role (**R2**) |
  | Teardown | both pipelines stopped; the tap's device gone afterwards |

  The Participant transcripts were exact, including the code-switched Chinese line (returned in
  Simplified against a Traditional prompt, which is **R10**'s known and accepted behaviour).

  **Two things this run found that no fixture could have.**

  **1. The tap's device needed two attempts to appear** — the race in **V61**, in production, on
  the first run. Without the wait loop this session would have opened nothing and reported success.

  **2. The microphone track produced three lines nobody said.** `我。`, `对吧？`, `这是什么呀？` —
  the built-in microphone hearing the speakers, and the model doing to that attenuated leakage
  exactly what **V60** measured it doing to attenuated speech: short, fluent, confident invention.
  **Speaker and Participant were separate, correct, and one of them was fiction.** This is the
  first end-to-end confirmation that **R2** is not sufficient by itself — separation guarantees the
  labels are right, not that the content is real. Under the *garbage in, garbage out* stance the
  live path does not chase it; **R49**'s cleanup pass is where it is removed, and this is now a
  measured reason that pass exists rather than an anticipated one. An operator on headphones does
  not have this problem, which is worth saying on the pre-flight panel.

  **Amended 2026-08-12 after the first web-driven session: headphones do not remove it, because
  the mouth is closer than the speakers.** With output on a Bluetooth headset — no acoustic path
  from the speakers at all — the Speaker track still produced `哦。` and `じ。`. The operator was
  eating. Chewing is vocal-tract noise, the same category as the laughter, coughing and sneezing
  **V60** measured, and the built-in microphone is inches from it. So the leakage explanation
  above accounts for the speaker case and not for this one: **the microphone track invents short
  utterances from whatever the operator's mouth does**, and there is no output configuration that
  changes that.

  **Muting the output does not affect the tap.** Measured 2026-08-12: peak **0.2558** at system
  volume 0, identical to volume 50, because the tap reads the mix before device volume is applied.
  Practical for measurement — a long soak can run silently — and worth knowing operationally: an
  operator who mutes to avoid feedback is still being captured, which is the correct behaviour and
  not an obvious one.

  **Extended the same day: three sessions in one process, and the later ones work.**
  `tools/verify_repeat_sessions.py`. This is the shape the app actually runs in — one long-lived
  Streamlit process, one session per meeting — and it is the case a first-run measurement cannot
  reach. It is also where the same day's changes could have gone wrong: starting the tap
  re-initialises PortAudio globally and stopping it re-initialises again, both underneath a
  microphone stream using the same library.

  | Round | Participant device | Index | Line | Device left behind |
  |---|---|---|---|---|
  | 1 | `Aegis System Audio` | 4 | correct | no |
  | 2 | `Aegis System Audio` | 4 | correct | no |
  | 3 | `Aegis System Audio` | 4 | correct | no |

  Inference held at **750 / 754 / 747 ms** — no drift across sessions — and the tap resolved to the
  same index every round, which is the observable sign that teardown removes the device rather than
  leaving a hole. The failures this was built to catch raise nothing: a stale entry, a shifted index
  or an unreaped helper each yield a session that reports success and transcribes silence.

- **V65 — One hour of continuous capture through the real device path: no drift, no leak, no
  dropped frames.** Measured 2026-08-12 with `tools/soak_capture.py`. This is the mechanical half
  of **R7**'s "once proven", separated out so a real meeting can be spent on judgement rather than
  on discovering the tap dies at minute forty. It is **not** the same as the NPU_LOCK trial, which
  also ran an hour but fed WAVs straight to the transcriber and never opened a device.

  | | |
  |---|---|
  | Duration | **60.0 min**, both tracks contending for one NPU |
  | Peak MLX memory | **3578.3 MB → 3578.3 MB** — unchanged across 120 samples |
  | Tap survival | alive at every sample; device removed cleanly at stop |
  | Lines transcribed | **916** — Speaker 356, Participant 560 |
  | Dropped frames (`Audio queue full`) | **0** |
  | Inference-thread exceptions | **0** |
  | Network requests | **0** |

  **The operator's original worry is answered: it does not slow down.** Median latency by fifth of
  the run — Speaker **744, 820, 669, 666, 713 ms**; Participant **508, 505, 486, 488, 621 ms**. The
  Speaker track ends *faster* than it starts. The one number that is not flat is the Participant's
  final fifth, **+27%** over the preceding four; too small to act on and recorded rather than
  smoothed over, because it is the only direction anything moved in an hour.

  **Completeness, stated carefully.** Against `turns.tsv`: track A produced **560 lines from 676
  turns (82.8%)** and track B **356 from 454 (78.4%)**. **That is not a 17% loss.** The pipeline
  flushes on 0.4 s of silence, so adjacent turns merge and long turns split — line count and turn
  count are different units. Measuring actual loss needs text alignment against the reference,
  which this run did not do. What the ratio does show is that **the real device path retained a
  *higher* fraction than the queue-injection path**, so the tap is not where material goes missing.

  **Two holes, named so nobody assumes otherwise.** The Speaker track was fed from a WAV through
  the lab hook, so **the built-in microphone was not soaked** — it is a plain `sd.InputStream`
  verified live in **V62**, while the hour-long risk was the tap, an aggregate device backed by a
  subprocess. And the fixture is ASCEND conversation split by speaker, so it carries **less overlap
  and interruption than a hearing**. Both remain for a real meeting.

  **The operator read the hour of transcript on 2026-08-12 and passed it against R9.** That closes
  the quality half by the only means available — **R9**'s bar is "the speaker on stage needs the
  gist", which is a judgement and not a metric, and no CER number substitutes for a person deciding
  whether they could have worked from it.

  **So the tap is proven under R7 — but the code had already made it the default, and that came
  first.** `system_audio.available_backend()` has preferred the tap since the auto-detection step,
  which is before this evidence existed. Recorded rather than smoothed: the sequence was forced
  rather than chosen. BlackHole is deliberately not installed on this machine, so a build that
  declined to default to the tap would have had **no Participant source at all** and nothing could
  have been measured. Anyone reviewing R7 compliance should know the proof arrived after the
  default, not before it.

- **V68 — `mic_rms` cannot tell a live room from a dead one, so it must never be used as the
  microphone's liveness signal. Measured 2026-08-12** during the staged microphone soak, by the
  session running it.

  | Run, same room, same 3 minutes | `mic_rms` range | Speaker lines transcribed |
  |---|---|---|
  | system output **muted** | 0.0031 – 0.0070 | **0** |
  | system output **audible** (volume 35) | 0.0033 – 0.0046 | **35** |

  **The audible run reads *lower*.** RMS over a whole callback window is dominated by ambient room
  noise between utterances, and speech is too sparse to move it. A moving, plausible-looking
  `mic_rms` is therefore consistent with a microphone hearing nothing at all.

  This is worse than an absent signal, because it reads as reassurance. It is what let a muted
  3-minute stage look healthy from every angle its report showed — lines transcribing on the
  Participant track (the tap reads the mix before device volume, **V62**), `mic_rms` moving on every
  sample, no warnings, no exceptions — while the speakers emitted nothing and the microphone
  produced zero lines.

  **The only signal that separated them was per-role transcribed line counts**, and the soak's stop
  condition now reads "either role emits zero transcribed lines" rather than "`mic_rms` is zero or
  static", which the muted run would have passed.

  ⚠️ **`mic_rms` keeps a narrower job.** It still detects *callbacks stopping* — a stream that stays
  `active` while delivering nothing freezes the value, and identical readings across consecutive
  samples means no callback arrived. That is a different failure from "open and hearing nothing",
  and only the first is what this field can see. Both belong in a soak report; neither substitutes
  for the other.

- **V69 — The built-in microphone survives an hour of continuous capture alongside the tap.
  Measured 2026-08-12**, `tools/soak_capture.py --microphone`, staged 3 → 10 → 60 minutes so a
  broken path could not consume an hour. **This is the second of the two fixtures the process-tap item still needed, and it
  closes it.**

  **V65** soaked the tap for an hour but fed the Speaker track from a WAV, so the microphone device
  itself had never run that long — it had seconds behind it (**V62**). Here it is opened for real,
  hearing the conversation fixture played through the speakers.

  | | |
  |---|---|
  | Duration | **60.0 min**, no early stop |
  | Peak MLX | **3578.3 → 3578.3 MB** — flat, and the two-track plateau (**V58**) |
  | Tap alive at end / device left behind | yes / **no** |
  | Microphone stream active | yes |
  | `mic_rms` distinct samples | **120 / 120** — callbacks arrived for the whole hour |
  | Lines | **738** Speaker, **567** Participant |
  | Latency by fifth, Speaker | 436, 439, 473, 478, 479 ms — **1.10x** first to last |
  | Latency by fifth, Participant | 672, 651, 731, 707, 818 ms — **1.22x** |
  | `Audio queue full` / exceptions / network requests | **0 / 0 / 0** |
  | Battery | 100% → 91% |

  **No sleep during the window**, confirmed with `pmset -g log` rather than assumed — the machine's
  last sleep event is the 18:20:40 lid wake that cost **V67** eighty minutes. Checking this is now
  part of reading any long wall-clock run here.

  **The drift is mild and the two tracks differ.** 1.10x on the Speaker track is within noise; 1.22x
  on the Participant track is a rise worth watching rather than acting on, and it is not thermal in
  any obvious way given peak memory is flat and the accelerator is shared. A third stage would say
  whether it continues; nothing in **R9** turns on 150 ms at this level.

  ⚠️ **What this does not establish.** The transcript is not judged here — room acoustics plus the
  leakage in **V62** mean the microphone hears an attenuated copy of the speakers, and **V60** says
  the model invents fluent text from exactly that. Device durability is the question and a poor
  transcript answers it as well as a good one. It also does not cover a real meeting — the last item in Phase 7 —
  where the microphone hears a person rather than a loudspeaker.

- **V70 — On speakers, most of the Operator track is the *other party*, degraded into something the
  operator appears to have said. Measured 2026-08-12** during the microphone soak, by comparing the
  two roles' lines within an 8 s window over the 10-minute stage:

  | Relationship of a microphone line to a tap line | share |
  |---|---|
  | verbatim match | **16%** |
  | partial match | **23%** |
  | same speech, different VAD boundaries, **degraded wording** | **61%** |

  Example — the tap heard `那我专业是那个ISM Information Systems Management。` and the microphone
  rendered the same moment as `那我专业是那个ISM，都没正式研究生。`

  **This sharpens V62 from an anecdote into a proportion.** V62 found the microphone inventing a few
  short utterances from leakage; this says that when the operator is on speakers, **the majority of
  the Operator track is the remote party's speech, wearing the operator's label and carrying words
  they never said.**

  ⚠️ **R2 is not violated and that is exactly what makes this dangerous.** The two streams are
  separate, never mixed, and each line is correctly attributed *to the source that produced it* —
  the microphone genuinely did capture that audio. The structural guarantee holds perfectly while
  the reader's inference from it is false. **The label is right and the content is wrong**, which is
  a failure no amount of track separation can catch, because separation is about provenance and this
  is about meaning.

  **Consequence for the real-meeting validation, and it is a precondition rather than a
  recommendation: it must be run on headphones.** The process-tap item already notes that headphones
  distinguish a genuine tap from acoustic leakage; this makes the same arrangement mandatory for a
  transcript anyone will read, because on speakers the record will show the remote party talking in
  the operator's voice. An operator reviewing that transcript afterwards has no way to tell which
  lines were theirs.

  The **R49** cleanup pass is where this would be removed if it ever reaches a transcript, and this
  is now a second measured reason that pass exists — the first being **V62**'s invented short
  utterances. Neither is fixable in the live path: see the *garbage in, garbage out* stance.

- **V66 — Letting speech segments grow improves accuracy and false-line count, and doubles the
  wait for the first word.** Measured 2026-08-12 with `tools/measure_segmentation.py`: ten minutes
  of ASCEND conversation plus 18 real non-speech recordings, four segmentations, one parameter
  varied against production's own constants (the 0.3 s minimum and 15 s cap held fixed).

  | Strategy | Segments | Median | CER | ms/call | Total inference | False lines | Rate |
  |---|---|---|---|---|---|---|---|
  | **`flush=0.4` (production)** | 127 | 3.03 s | 0.1774 | 715 | 102.3 s | **13** | 6.99% |
  | `flush=0.8` | 62 | 6.76 s | **0.1718** | 1076 | 82.6 s | **10** | 8.77% |
  | `flush=1.5` | 41 | **15.0 s** | 0.2711 | 1790 | 71.7 s | 6 | 7.32% |
  | `window=8s` | 75 | 8.0 s | 0.1914 | 1073 | 85.2 s | **6** | 5.77% |

  **Too much patience is worse than too little, and the reason is mechanical.** `flush=1.5`'s
  median segment is **exactly 15.0 s** — production's hard cap. It has stopped cutting at silence
  and started cutting at an arbitrary clock, and CER degrades from 0.17 to 0.27. Whatever the
  answer is, it is not "wait longer".

  **The wait for the first word is what this costs**, since a segment cannot be transcribed until
  it closes: **3.75 s** at production, **7.84 s** at `flush=0.8`, **9.07 s** at `window=8s`, **16.79 s**
  at `flush=1.5`.

  **Where the false lines go is not where it looks.** The absolute count falls (13 → 10 → 6) while
  the *rate* barely moves (6.99% → 8.77% → 5.77%). The same 18 recordings yield 186 segments under
  production and 104 under `window=8s`, so fewer lines reach the buffer because **the audio gets
  fewer chances to be transcribed, not because anything discriminates better.** The reduction is
  real — what reaches the buffer is what **R37** is about — but the mechanism must not be mistaken
  for improved judgement. At these counts sampling noise is also a live explanation.

  **Decided 2026-08-12 by the operator: keep 0.4 s.** The ranking could not settle it — `flush=0.8`
  wins accuracy *and* false lines *and* compute, and loses only latency — so it came down to what
  **R9** is for. The live path owes the speaker a **timely** gist, and doubling the wait for the
  first word is the single change that attacks that directly, against 0.6 pp of CER and three
  fewer false lines from a sample where noise explains three. The constant in `transcriber.py` now
  carries this reasoning, because raising it is the tempting edit and its cost is invisible in a
  table.

  **One metric failed and is reported as failed rather than passed.** `unterminated_pct` — segments
  whose transcript lacks terminal punctuation, intended as a proxy for being cut mid-clause — read
  **0.0% for all four strategies**. Qwen punctuates whatever it is given, cut or not. The proxy
  measures the model's habit, not the segmentation, and a reader should not take four zeroes as
  four clean bills.

- **V63 — The tap is unaffected by the output device, including Bluetooth. Measured 2026-08-12.**
  **V7** was measured on a machine with one output, so nothing was known about the case the product
  actually runs in — nobody wears speakers in a hearing room. The header said a global tap should
  be device-independent (`initMonoGlobalTapButExcludeProcesses:` takes no device UID, unlike
  `initWithProcesses:andDeviceUID:withStream:`); this is that reading confirmed rather than trusted.

  | Output | Bluetooth mic | Peak | Frames over 6 s |
  |---|---|---|---|
  | MacBook Pro Speakers | — | 0.2558 | 287,232 |
  | JLab Work Buds (A2DP) | not in use | **0.2558** | **287,232** |
  | JLab Work Buds (HFP) | held open | 0.3617 | 287,232 |

  **Switching to a Bluetooth headset changes nothing measurable.** Identical peak, identical frame
  count.

  **Forcing the narrowband duplex profile does not degrade it either — it raises the level by
  exactly √2 (1.414).** That is a stereo-to-mono mixdown gain change, not a codec effect: the
  headset going mono makes applications render mono, and the tap's own mono mixdown then receives
  the full amplitude instead of an averaged pair. The tap reads the mix *before* it is encoded for
  the link, so the Bluetooth codec never touches it. **What this does not measure is bandwidth** —
  peak cannot see it — but there is no path by which it could change, for the same reason.

  **The second row is the one that matters, and the third is now moot for this deployment.** The
  operator stated 2026-08-12 that capture always uses the **built-in microphone**, with the output
  being either the Bluetooth headset or the built-in speakers. The Bluetooth microphone is never
  used, so HFP is never negotiated. Recorded anyway, because a fork will do it.

  **One consequence for the microphone default (R26):** while the headset is connected it is also
  the *system default input*, so a first run on this machine defaults to a microphone the operator
  never wants. This is exactly what the sticky override in the pre-flight dropdown is for, and it
  makes that override the normal case rather than an edge case.

  **Confirmed in operation 2026-08-12, and it is worse than "a bad first-run default": connecting
  the headset takes the input away mid-session.** The operator's words — *"as soon as the headset
  connects it steals the built-in microphone, and you have to choose again."* macOS moves the
  system default input the moment the device appears, which is a normal thing to happen in the
  minutes before a meeting starts.

  The re-selection was **a defect in the panel, not in macOS**. The dropdown derived its selected
  index from the *persisted* preference, and the preference is only written when Start is pressed —
  so before Start it is usually empty. Connecting a device changes the option list, which forces a
  full Streamlit rerun, which recomputed the index from that empty value and put the selection back
  to *system default*. **Silently.** Fixed by preferring the session's own choice over the persisted
  one, with tests for both directions: a device arriving must not move the selection, and a
  selected device going away must be kept and flagged rather than substituted.
- **V12 — Closed 2026-08-12: PortAudio resamples the tap on request, so no software resample
  step is needed.** The tap is fixed at 48 kHz (**V7**) while `docs/decisions/0001` made 16 kHz the
  single rate through the product, so something had to convert. Measured on this machine with
  `tools/measure_tap_stream.py`, against the real helper rather than a stand-in:

  | Requested | PortAudio reports | Frames actually delivered per second | Peak |
  |---|---|---|---|
  | **16000** | 16000 | **15919** | 0.2558 |
  | 48000 | 48000 | 46852 | 0.2558 |

  **The delivered rate is what decides it, not the reported one.** A stream that reported 16000
  while delivering ~48000 frames per second would be relabelling rather than converting, and the
  model would read the audio as three times longer than it is — the failure **V56** measured at
  **3426 ms against 660 ms**. It delivers ~16 k, so the conversion is real, and the identical peak
  at both rates says the signal survives it.

  Both ratios sit slightly under 1.0 (0.995 and 0.976) because the elapsed time includes stream
  open and close and the `afplay` subprocesses used to produce signal. That is measurement
  overhead, not drift; a drift measurement would need a long run against a clock and has not been
  done.

  **Consequence: `transcriber.py` opens the tap exactly as it opens the microphone**, at 16 kHz,
  with no second path. The previously planned fallback — run `webrtcvad` at 48 k and resample only
  before inference — is not needed and should not be built.
- **V50 — Silero VAD accepts 48 kHz by decimating it, and this constrains the VAD choice.** Measured
  2026-08-10 against `silero-vad` as pinned by the unmerged branch (**V49**): `get_speech_timestamps`
  does not reject a 48 kHz input. When the rate is a multiple of 16 kHz it takes `audio[::step]` —
  **plain 3:1 subsampling with no anti-alias filter** — and then rescales the returned sample indices
  by the same factor. Two consequences, and they point in opposite directions: buffer-slicing
  arithmetic built on those indices **survives** the move to 48 kHz unchanged, but the VAD would be
  judging aliased audio, and how much that costs on music and chimes (**R37**) is unmeasured. Since
  48 kHz capture is mandatory (`docs/decisions/0001`) and that branch deletes `webrtcvad` outright,
  replacing the VAD means either resampling before the VAD or accepting the decimation — a decision
  the ASR work must make explicitly rather than inherit.

## Inference cost is a constant, not a function of utterance length

- **V51 — One `mlx_whisper.transcribe()` call costs the same no matter how much audio it is
  given; the constant itself belongs to the toolchain (see V53).** Measured 2026-08-10 on this
  machine at **~1.38 s** (macOS 26.6.1, Python 3.9.6, `mlx` 0.29.3,
  `mlx-community/distil-whisper-large-v3`, fp16), controlled inputs: 1 s of silence 1386 ms, 1 s of
  white noise 1380 ms, **10 s** of silence 1379 ms, 10 s of white noise 1376 ms. Whisper pads or
  truncates every input to a single 30-second window, so the cost is structural rather than
  incidental. Setting `temperature=0.0` instead of the default fallback sequence changed nothing
  (≤6 ms), so the decoder's retry ladder is not a factor on these inputs.

  Corroborated by the first live English session on the microphone track (16 utterances, no
  dropped frames): median 1410 ms, and **no correlation with output length** — `r = -0.08` across a
  15.5x range of transcript lengths.

  **The consequence bounds the streaming design.** Any architecture that transcribes more often
  pays ~1.38 s per call no matter how little audio each call carries, and once a second track
  exists the two instances serialize on `NPU_LOCK` (**V33**). Windowed streaming buys perceived
  responsiveness with multiplied fixed cost; that trade has to be measured against **R37**, not
  assumed in either direction.

  **Re-measured 2026-08-11 after the product runtime moved to Python 3.12 / `mlx` 0.32.0**, same
  machine, same model, same inputs: silence 1 s 597 ms, noise 1 s 606 ms, silence **10 s** 607 ms,
  noise 10 s 597 ms. **The length invariance survives; the constant does not** -- it fell from
  ~1.38 s to ~0.60 s, a 2.3x change with no code and no model change. The original figures above
  are kept rather than overwritten because they describe what was true of the runtime that
  produced them, which is the point of **V53**.

  **Unexplained, and deliberately not folded into the average:** four of the sixteen live calls took
  2081-5067 ms, all on *short* outputs. The controlled measurement above refutes the obvious
  explanation (temperature fallback). The live run had a browser polling the script every 0.5 s
  across several sessions, so UI contention is the current suspect — untested.

  ⚠️ **That refutation was an OVER-READ, and **V75** supplies the mechanism it dismissed.** The
  controlled inputs were synthesized silence and white noise, which do not trigger the temperature
  ladder — so the test showed the ladder is not a factor *on synthetic audio*, and that was read as
  *not a factor*. On real non-speech the ladder costs 3.4x, with a p95 of 6.1 s, which is the
  2081-5067 ms band exactly. UI contention remains untested and is no longer needed to explain
  these four calls.

- **V75 — A call on real non-speech costs 3.4x a call on speech, and the synthesized fixtures show
  none of it.** Measured 2026-08-17 from the same run that produced **V72** — 530 calls, one
  process, offline, `mlx-community/whisper-large-v3-turbo`, no extra work required to obtain it:

  | Input | n | median | p95 | median audio |
  |---|---|---|---|---|
  | Real speech (ASCEND, the positive control) | 10 | **655 ms** | 698 ms | 3.86 s |
  | **Real non-speech** | 253 | **2235 ms** | **6116 ms** | 1.14 s |
  | Degraded speech (quiet, babble, mumble) | 204 | 656 ms | 6137 ms | 1.81 s |
  | Synthesized non-speech (the original 63) | 63 | 634 ms | 1448 ms | 0.42 s |

  **The non-speech rows carry *less* audio and cost more**, so this is not **V51**'s length
  invariance breaking — that still holds. It is the decoder's temperature ladder retrying a segment
  that keeps failing its thresholds, up to six times, on input that has no speech in it.

  **Three consequences, and the third is the one that changes a decision:**

  - **The synthesized fixtures are useless for latency too**, not only for **R37** (**V60**,
    **V72**). Their 634 ms reproduces **V51** and hides the effect completely.
  - **It explains the four unexplained live calls above** without needing UI contention.
  - **A noisy room attacks R9 directly, and through the one term nobody measures.** The known issue
    in `STATE.md` records that queue wait is measured nowhere and that a burst is bounded by
    nothing. Every segment in that burst now costs 2.2 s instead of 0.65 s, and the segments
    arriving during a burst are exactly the non-speech ones. The false lines and the latency come
    from the same mechanism, so a decoding change that fixes one may fix both — which is what
    **V73** is measuring, and it was queued before this was known.

  ✅ **Checked for the failure that cost V67 eighty minutes, because this run walked into it.**
  `pmset -g log` shows the machine entering sleep four times between 19:37 and 20:46 while this run
  was in progress — `sleep 1` on this power profile, and the only assertion up was an agent
  session's renewing `caffeinate`, which is exactly the expiring kind **V67**'s note warns about.
  The run was **not** wrapped.

  **The timings survive it, and the evidence is a signature rather than an argument.** Sleep
  windows here are hundreds of seconds; the slowest call in 941 is **16.3 s** and **no call exceeds
  60 s**. Had any call spanned a sleep, it would sit in the tail as a ~500-950 s outlier, and none
  does. That is what clears the data — **not** a claim about whether `time.perf_counter()` advances
  across system sleep on macOS, which was not tested here and should not be asserted from this.

  **Every run after this one is wrapped in `caffeinate -dis`**, and `-d` is deliberate rather than
  cautious: the sleeps were `Dark Wake Thermal Emergency`, reached *through* dark wake after the
  5-minute display sleep, so keeping the display up is what removes the path into them.

## The web UI's polling loop competes with inference


  ⚠️ **This is a fact about Whisper and does not carry to the shipped model.** Measured on
  `mlx_whisper` + `distil-whisper-large-v3`, and the constancy comes from Whisper padding every
  input to a fixed 30-second window. `Qwen/Qwen3-ASR-0.6B` does not: **V66** measured 715 ms at a
  3.03 s median segment, 1076 ms at 6.76 s and 1790 ms at 15.0 s. Anyone reasoning "longer segments
  are free" from this constraint is reasoning about a model the product no longer runs — an
  extrapolation made in this repository on 2026-08-12 and caught by the measurement it was used to
  justify.
- **V52 — Browser sessions lengthen the tail of ASR latency, and the product's real configuration
  is multi-session.** Measured 2026-08-10 on this machine, microphone track only,
  `mlx-community/distil-whisper-large-v3`, by reading the same ten-line English script aloud twice
  with deliberate four-second pauses so each line became its own segment:

  | Browser sessions | n | median | max | calls over 2000 ms |
  |---|---|---|---|---|
  | **0** | 9 | 1376 ms | 1409 ms | **0 (0%)** |
  | **5** | 24 | 1399 ms | 4983 ms | **7 (29%)** |

  Pooled against an earlier uncontrolled run with several tabs open, the tabs-open arm is 12/45
  (27%). Fisher one-tailed **p = 0.084** — indicative, **not established**; the control arm is only
  nine samples. Recorded at that strength on purpose.

  **The median barely moves (1376 → 1399 ms); only the tail stretches.** That is the shape
  contention produces: most calls complete normally and a minority collide with a burst of
  rendering. A thermal or model-side cause would drag the median with it.

  Mechanism: Streamlit re-executes the entire script on every poll tick, **per session**, so five
  connected browsers are roughly ten full script runs per second of Python work on the main
  thread, against an inference call whose own cost is a constant 1.38 s (**V51**).

  **This gets worse in production, not better.** The intended deployment is multi-session by
  design — the speaker's iPad, the staff officer's laptop, and the capturing machine itself — and
  once the process tap supplies a second track, two `Transcriber` instances serialize on
  `NPU_LOCK` (**V33**).

  ⚠️ **Two measurement artefacts were found and corrected while producing this; re-measurement
  must avoid both.** Redirected stdout is block-buffered, so the log lags reality and an early read
  looks like a dead pipeline. And the access-code banner prints with `\r` and no newline, so log
  lines acquire a prefix **only when the script is re-running** — a line-anchored regex therefore
  drops samples precisely in the high-session condition, which biases the result toward the
  hypothesis under test.

  **Remeasured 2026-08-11 after the running-view `st.fragment` work (n=30 per arm, in-process WAV
  feed, distil):** 0sess median 1394 / max 1548 / **0%** >2000 ms; 3sess median 1430 / max 1732 /
  **0%** >2000 ms. The multi-session **tail collapse** that motivated this constraint is addressed
  in the UI path; keep controlling session count when comparing models. Details in `STATE.md` §7.3.

## The toolchain is a variable, not a constant

- **V53 — The Python / `mlx` version materially changes both inference latency and ASR output, so a
  measurement is only meaningful with its toolchain recorded.** Measured 2026-08-11 on one machine,
  by rebuilding the product venv on Homebrew `python@3.12` (macOS still ships 3.9, which reached end
  of life in October 2025 and caps `mlx`, which requires >= 3.10).

  | | Python 3.9.6 / `mlx` 0.29.3 | Python 3.12.13 / `mlx` 0.32.0 |
  |---|---|---|
  | `distil-whisper-large-v3`, one call | ~1380 ms | **~600 ms** |

  Latency more than halved with no code and no model change, measured on controlled synthetic
  inputs and repeated, so the figure is not a single draw.

  ⚠️ **Corrected the same day.** This constraint first also cited **R37** counts moving in
  opposite directions across the two toolchains (turbo 13 → 1, distil 32 → 45) as evidence. That
  attribution is **withdrawn**: **V54** then measured the same count varying between 30 and 60 on
  five identical runs, a band that swallows those differences whole. The toolchain may still move
  **R37** — nobody has shown it does not — but nothing here demonstrates it. The latency half of
  this constraint stands; the quality half never had the evidence claimed for it.

  **Consequences.** Every bake-off run must hold one toolchain for all candidates and record it.
  A default chosen under one toolchain does not transfer to another. Earlier harness runs that
  straddle the two are superseded for *comparison* purposes, though they remain valid as records
  of what each runtime did.

  Two secondary facts from the same rebuild, both load-bearing for anyone repeating it:
  `webrtcvad` 2.0.10 imports `pkg_resources`, which `setuptools` >= 81 no longer ships, so it fails
  at import on a current environment -- `webrtcvad-wheels` is the drop-in that does not. And
  `huggingface_hub` 1.27 issues HTTPS requests to huggingface.co during warm-up even when every
  file resolves from the local cache; `HF_HUB_OFFLINE=1` suppresses them with no loss of function,
  which is what the product's offline claim requires.

## Whisper's false-trigger count is a random variable

- **V54 — The number of non-speech segments that survive the text filter varies by roughly 2x
  between identical runs; the number the model speaks on barely moves.** Measured 2026-08-11 over
  six consecutive invocations of the same harness command, same model
  (`distil-whisper-large-v3`), same fixtures, same toolchain, network disabled:

  | | observed values | spread |
  |---|---|---|
  | Segments the model produced text on (raw), of 63 | 63, 63, 63, 63, 63, 62 | ~1 |
  | Surviving the whole-utterance filter, of 63 | 30, 36, 53, 55, 58, 58 | **~2x** |

  Per-call latency on these fixtures moved with it (medians 1474 ms and 2231 ms on two runs),
  because a sampled decode that runs longer costs more — unlike the controlled synthetic inputs of
  **V51**, where the cost is flat.

  Cause: `mlx_whisper.transcribe` defaults to a temperature ladder
  `(0.0, 0.2, ... 1.0)` and falls back to **sampling** when a decode fails its logprob or
  compression checks — which is routine on non-speech. Which ghost string comes out is therefore
  random, and whether the blacklist catches it follows.

  **Consequences for any bake-off.**

  - **Rank candidates on the raw count.** It is stable, it is the model's actual behaviour on
    non-speech, and it is what **R11** asks about. Here it is total: distil speaks on **63 of 63**
    non-speech segments.
  - **Never rank on the filtered count from a single run.** Report it as a range over repetitions,
    or pin `temperature=0.0` and say so — noting that pinning departs from the production call,
    which uses the default ladder.
  - Any past single-run **R37** comparison in this repository is uninterpretable, including the
    ones this file previously cited.

## Real code-switched speech separates the candidates; synthesized speech did not

- **V55 — On recorded intra-sentence Mandarin-English speech, both Qwen sizes are two to three
  times more accurate than any Whisper candidate, and the incumbent default is unusable.**
  Measured 2026-08-11 against 80 clips from **CAiRE/ASCEND** test (40 `mixed`, 20 `zh`, 20 `en`,
  2-15 s, seed 7), each candidate in its own process, offline, one toolchain (**V53**). Metric is
  CER over case-folded punctuation-stripped text, so a Chinese character and an English word weigh
  the same; **comparable between these rows, not with any published WER**.

  | Candidate | CER mixed (**R8**) | CER zh | CER en | Latency median | Peak RSS |
  |---|---|---|---|---|---|
  | `distil-whisper-large-v3` (shipped default) | **1.179** | **2.493** | 0.157 | 636 ms | 2169 MB |
  | `whisper-large-v3-turbo` | 0.214 | 0.138 | 0.145 | 658 ms | 1966 MB |
  | `Qwen3-ASR-1.7B` | **0.075** | 0.060 | **0.091** | 2092 ms | 317 MB |
  | `Qwen3-ASR-0.6B` | 0.085 | **0.059** | 0.099 | **748 ms** | 1808 MB |

  **The shipped default is not merely weak, it is destructive**: a CER above 1.0 means it emits
  more wrong characters than the reference contains. **V1** predicted this from the model card;
  this is it measured on speech.

  **The two Qwen sizes are within one point of each other on every language**, while 0.6B is
  **2.8x faster**. Synthesized fixtures had suggested a gap that is not there: on a concatenated
  EN-then-ZH clip 0.6B returned Chinese only, and this session briefly recorded that as an **R8**
  failure. On real intra-sentence switching it scores 0.085. The whole-clip test was measuring
  something production never produces.

  ⚠️ **The RSS column was wrong by an order of magnitude and is superseded.** Re-measured
  2026-08-11 with `mlx.core.get_peak_memory()`, reset per candidate:

  | Candidate | Peak MLX | Peak RSS (`ps`) |
  |---|---|---|
  | `distil-whisper-large-v3` | 1988 MB | 2169 MB |
  | `whisper-large-v3-turbo` | 2085 MB | 1966 MB |
  | `Qwen3-ASR-0.6B` | **3207 MB** | 1606 MB |
  | `Qwen3-ASR-1.7B` | **6857 MB** | **375 MB** |

  `ps` under-reported the largest model by **6.5 GB** — MLX allocates in unified memory that
  resident-set accounting does not see, and the error grows with the allocation, which is why the
  first reading looked like an inverted ordering rather than an obviously broken instrument. **Use
  `mlx.core.get_peak_memory()`. RSS is not a memory measurement for anything running on MLX.**

  With a working instrument the resource band separates the two Qwen sizes as expected: 0.6B needs
  **2.1x less memory** and runs **2.8x faster** for **+0.010 CER** on code-switch.

## A second track doubles inference latency, and 48 kHz without a resample costs 5x

- **V56 — Two `Transcriber` instances serializing on `NPU_LOCK` cost exactly 2x per call, and
  running the pipeline at 48 kHz without resampling before inference costs a further 5x.**
  Measured 2026-08-11 with `tools/measure_dual_track.py`: `whisper-large-v3-turbo`, audio injected
  through `feed_wav` with no capture device, saturating feed, 30 segments per arm.

  | Rate | Arm | median | p95 | max | segments |
  |---|---|---|---|---|---|
  | 16 kHz | single | 660 ms | 678 | 687 | 30 |
  | 16 kHz | dual | **1318 / 1322 ms** | 1459-1471 | 1811 | 30 |
  | 48 kHz | single | **3426 ms** | 5815 | 6474 | 30 |
  | 48 kHz | dual | 4607 / 6489 ms | 9286-10715 | 12205 | 24-25 |

  **The dual-track ratio is 2.00x**, which is what serialization predicts exactly (**V33**). Under
  a saturating feed, every single-track latency recorded anywhere in this repository — **V51**,
  **V52**, **V55** — **doubles once the process tap supplies a second source.**

  ⚠️ **This entry previously ended "that is not a caveat to add later; it is the number a hearing
  will experience." That sentence is withdrawn, 2026-08-12**, for contradicting the ⚠️ below in the
  same entry — one paragraph called 2.00x the expected cost while the next called it an upper bound,
  and a reader got a different product expectation depending on which they reached first.

  It also misplaced the number's importance. **V66** measured the wait for the first word at
  **3.75 s** in production, of which inference is 637–715 ms — **under 20%**. The dominant term is
  segment close (median segment 3.03 s plus the 0.4 s silence flush), not contention on the
  accelerator. Doubling a fifth of the wait is worth knowing; it is not what a hearing experiences.

  **The 48 kHz arm quantifies a gap, not a property of 48 kHz.** Nothing resamples between the VAD
  and the model: `mlx_whisper` assumes 16 kHz, so the same wall-clock audio arrives as 3x the
  samples and is decoded as though it were three times longer, spilling past the 30-second window.
  Segment counts also shift (30 -> 24-25), so VAD grouping is not rate-invariant either. **V12**
  called the resample step mandatory once 48 kHz capture is required; this is what its absence
  costs.

  ⚠️ **This is an upper bound, not the expected cost.** Both tracks were fed identical audio as
  fast as the pipeline accepted it, so an inference was always in flight on both. A hearing has one
  person talking at a time: while the speaker talks the participant track is silent, the VAD drops
  it, and nothing reaches `inference_queue`. The realistic turn-taking figure is **not yet
  measured** — see `fixtures/asr/NPU_LOCK_TRIAL.md`.

  Measured without a capture device, which is the point: contention on `NPU_LOCK` is a property of
  the inference path, not of where the audio came from. It does **not** cover real device timing or
  whether PortAudio resamples (**V12**, still open, still needs hardware). Measured on Whisper
  because Qwen is not wired into `Transcriber`; the 2x shape is model-independent, the magnitude
  is not.

- **V67 — At conversational pace the dual-track cost is 1.47x on the 18% of lines that actually
  collide, and about 9% on the median. Measured 2026-08-12** with
  `tools/measure_overlap_turns.py` over the same one-hour two-track ASCEND fixture as **V57** and
  **V58** (1130 turns, 480 cross-track overlaps, **606.5 s of simultaneous speech = 16.8% of the
  hour**), `Qwen/Qwen3-ASR-0.6B`, lock held, feed paced in real time.

  This is the figure **V56** called "not yet measured", **V57** repeated as "not the realistic
  turn-taking figure", and `fixtures/asr/NPU_LOCK_TRIAL.md` listed under *left undone deliberately*.

  | Arm | n | median | p95 | max |
  |---|---|---|---|---|
  | all lines | 942 | **650 ms** | 1660 | 2996 |
  | solo — no other-track inference in flight | 775 | **597 ms** | 1555 | 2979 |
  | contended — competing for `NPU_LOCK` | 167 | **878 ms** | 1921 | 2996 |

  **Contention is read from the log, not inferred from the fixture.** `elapsed_ms` starts before
  `with NPU_LOCK`, so a line logged at `t` having taken `ms` occupied `[t - ms/1000, t]` waiting for
  and then holding the lock; two such windows on *different* roles intersecting is observed
  contention. No mapping from wall clock back to fixture time is involved, so feed drift cannot
  corrupt it.

  **The internal consistency check passes: 17.7% of lines were contended against 16.8% of the hour
  being simultaneous speech.** Those are independent quantities — one from emitted log lines, one
  from the reference timeline — and their agreement is the main reason to trust the split.

  **So V56's 2.00x is an upper bound reached only under saturation.** Serialization does not double
  a hearing's latency.

  🔴 **But the 1.47x is mostly a selection artifact, and this entry originally presented it as the
  conversational cost. Amended 2026-08-12, same day, by testing it.** Labelling a line "contended"
  requires its inference window to intersect another role's — and **a longer window is mechanically
  more likely to intersect one**, so conditioning on contention selects for slow lines whether or
  not contention slows anything.

  Quantified by permutation, 300 draws: keep every window exactly as measured, circularly shift the
  Participant role's timeline by a random offset, recompute the labels. That preserves each role's
  latency distribution, its internal spacing, and the length-selection effect, and randomises only
  cross-role coincidence.

  | | contended / solo |
  |---|---|
  | observed | **1.471** |
  | null (coincidence randomised) | **1.200**, 90% interval **0.977 – 1.547** |
  | p(null ≥ observed) | **0.061** |

  **The observed value falls inside the null's own 90% interval.** Selection alone accounts for
  1.20x of it; the contention-attributable remainder is about **1.23x** and is *not* statistically
  distinguishable from chance at conventional thresholds. **Do not quote 1.47x as the cost of a
  second track.**

  **What survives unharmed is the aggregate: 650 ms median for two-track conversational operation**,
  which is a plain median over all 942 lines with no conditioning and therefore no selection. What
  is missing is the comparison that would settle the cost cleanly — **a single-track arm on the same
  fixture and model**, whose aggregate median could be differenced against this one with no labels
  involved. That arm was never run, and the within-run split was used as a substitute for it. The
  substitute is what failed.

  The same confound applies to any contended-versus-solo split computed this way, including on the
  real device path. The instrumentation added in `923deb3` logs **segment duration**, which is the
  proper control — inference time scales with segment length (**V66**), so the question "does
  contention add anything beyond length?" becomes answerable directly instead of by permutation.
  This run predates that logging and cannot be re-analysed that way.

  **What successive controls do to the same quantity, measured on the real device path** (staged
  microphone soak, **1702 segments over three stages**, by the session running it). Recorded as a
  *method* result rather than a constraint, because the load — one audio stream reaching both tracks,
  since the microphone hears the speakers — is not the load a hearing produces:

  | Control applied | ratio |
  |---|---|
  | none (naive contended/solo) | 1.47x |
  | matched on **segment duration** | 1.26x |
  | matched on duration **and transcript density** | **1.15x** |

  **Every control shrinks it and none removes it.** But the interesting part is not the pooled
  figure, it is that **the cost is not uniform — it rises monotonically with segment duration**:

  | band | n solo | n con | length-matched | + density-matched |
  |---|---|---|---|---|
  | 0–1 s | 313 | 504 | 1.26x | **1.03x** |
  | 1–2 s | 129 | 281 | 1.24x | **1.19x** |
  | 2–3 s | 58 | 154 | 1.20x | **1.18x** |
  | 3–4.5 s | 40 | 100 | 1.31x | **1.31x** |
  | 4.5+ s | 30 | 93 | 1.44x | **1.55x** |

  **Sub-second segments pay essentially nothing (1.03x on n=817); the cost concentrates where
  segments are already long.** In absolute terms that is roughly **+13 ms on a 0.4 s segment and
  +586 ms on a 6 s one** — and a 6 s segment has already made the speaker wait 6 s for it to close,
  so contention adds ~10% to an already-bad case and ~3% to a good one.

  ⚠️ **An earlier version of this entry recorded the opposite — "roughly constant across a 12x range,
  and a pure artifact would collapse inside matched bands".** That came from 317 segments where only
  one band had usable n. At 1702 it is a clean trend, and the flatness claim is withdrawn by the
  session that made it. Part of the effect *did* collapse under the controls: the sub-second band,
  which is most of the traffic.

  **Why it trends is unsettled, and the leading hypothesis does not obviously predict the direction
  observed.** The proposal is that "contended" labels two *elapsed* windows overlapping, and a longer
  window spans more of the partner's activity, so it accumulates more real waiting. Against that:
  under `NPU_LOCK` the segment holding the lock is not delayed at all — only the one waiting is — so
  the label marks blocker and blocked alike, which dilutes a trend rather than creating one. And a
  roughly fixed lock wait divided by a growing inference time would make the *ratio fall* with
  duration, not rise. **Both readings end at the same place: the label means "overlapped", not
  "blocked", and no amount of re-analysis separates them.** Timing lock wait directly does.

  ⚠️ **Density is a real second confound and it does not point the way length does.** Pooled, *solo*
  segments are the denser group — **8.3** characters of transcript per segment-second against
  **7** — so in most bands sparser-and-slower contended segments mean density was **suppressing**
  the ratio rather than creating it. The exception is the longest band, where contended segments are 1.7x denser and
  the apparent 66% gap collapses to **0.99x** once density is matched — which is why the longest band
  cannot be used as evidence that length points the wrong way, however tempting the shorter-audio-yet-
  slower reading looks. That argument was made here and was wrong.

  **The mechanism behind the confound is measured rather than asserted: solo segments really are
  disproportionately fragments.** Over the hour, **76 of 570 solo segments (13%) had their text
  rejected by the filter, against 10 of 1132 contended (1%)**. Segments only one path caught are far
  more often ambience, a cough, or a VAD split of attenuated audio — which is why they transcribe
  faster, and why an uncontrolled solo baseline flatters contention. (This also revises a 1% pooled
  rejection rate quoted from the 13-minute sample: over the hour it is ~5% pooled. Either figure
  corroborates **V64** — the length guard almost never fires — and neither says anything about
  whether the text that passed is invented, which is **V60**'s question and needs reference text
  this load does not have.)

  No constraint is opened on any of these figures. The defensible statement at this evidence level:
  **when two tracks genuinely collide on one accelerator, the cost is negligible on short segments
  and grows with segment length — about 3% of an already-short wait and about 10% of an already-long
  one — and it is nowhere near the dominant term in what a speaker waits.** An earlier version of
  this sentence said "roughly 15–25% more" with no shape, which the 1702-segment breakdown replaces:
  a single figure averages a 1.03x band with a 1.55x one and describes neither. Turning it into a
  measured constraint needs lock wait timed directly rather than inferred from a label — see the
  note under the queue-dwell paragraph.

  ⚠️ **This does not describe what a speaker waits.** Inference is under 20% of the 3.75 s wait for
  the first word (**V66**). A 9% move in a fifth of the wait is roughly 2% of it. This entry refines
  the minority term and should not be quoted as a latency improvement or regression.

  **The remaining term is measured, and it is empty in the median and not empty in the tail.**
  Queue dwell — segment enters `inference_queue` to inference start — was instrumented nowhere when
  this entry was written, leaving open the possibility that the unexplained part of the wait hid
  there. Measured 2026-08-12 across the staged microphone soak, **hour-long stage, 1385 segments,
  both roles live**:

  | | |
  |---|---|
  | dwell median | **0 ms** |
  | non-zero | **17 of 1385 (1.2%)** |
  | ≥ 500 ms | **6 (0.43%)** |
  | max | **2037 ms** |

  **In the median there is no hidden fourth term in V66's 3.75 s** — segment close (~3.43 s) plus
  inference (~0.65 s) plus a dwell that is zero on 98.8% of segments accounts for the wait.

  ⚠️ **Do not close this on the median, and an earlier version of this entry did.** A **2 s** stall
  is exactly what **R9** notices — the requirement is about a speaker reading a line under pressure,
  and one line arriving two seconds late is a visible event however rare. **The tail is the finding;
  the median is the reassurance.** Frequency and severity have to be quoted together or the number
  misleads in whichever direction the quoter prefers.

  Three properties of the tail. **It cannot be cross-role lock wait** — dwell ends at dequeue and
  `NPU_LOCK` is acquired after it, so this is one role's segments backing up behind *its own*
  worker. **It clusters** rather than scattering: five of the seventeen fall inside minutes
  40.1–42.9 and three more in 53.7–55.5. And the segments involved are **short** — median 0.69 s
  against 1.08 s overall.

  **The mechanism is head-of-line blocking behind a long segment, and it is measured rather than
  inferred — 2026-08-12.** An earlier version of this paragraph read the short durations as "one role
  producing a burst faster than a single worker drains it". That was a guess and it was the wrong way
  round: **all 17 of 17 waits overlap an inference already running on the same role**, and the
  blocking segments are the *long* ones — 0.75, 2.16, 2.73, 3.03, 3.06, 3.12, 4.98, 5.16, 5.16,
  5.34, 5.49, 5.64, 6.21, 6.78, 7.20, 7.80 and **15.00 s**. The 2037 ms case is exact: a **5.16 s**
  segment took **3469 ms** of inference, and a **0.75 s** segment arriving behind it waited out the
  remainder. Short segments do not cause the tail; they are what the tail happens *to*.

  **So the tail is bounded by the longest inference a single segment can take, which is set by the
  15 s VAD cap** — observed maximum **3469 ms** across 1385 segments. It is the cost of the
  segmentation **V66** chose and the operator settled, not a separate defect: longer segments buy
  accuracy and fewer false lines, and this is what they charge for it on the line behind them.
  **Nothing here says the tail is acceptable** — it says what would have to change to remove it
  (a lower cap, against **V66**'s accuracy finding) and that no code fix is available without
  reopening that trade. In-order processing with one worker per role cannot do better: the delayed
  line is behind an utterance that genuinely came first.

  ⚠️ An earlier version of this paragraph rested on a 3-minute run whose **system output was muted**:
  the tap reads the mix before device volume, so the Participant track ran normally while the
  microphone produced zero lines, making it effectively a *single-track* figure. That caveat is
  retired by the 10-minute stage above, which has both roles transcribing.

  **Accuracy and completeness, both independent of pacing:** CER against the fixture's own reference
  is **0.142** (Operator track) and **0.090** (Participant track); **942 lines from 1130 turns**
  (0.83 per turn, which bounds the loss rather than measuring recall, since segments group turns).
  Peak MLX memory **3578.3 MB**, matching **V58**'s dual-track 3578 MB exactly.

  **R2 held, and the test is weaker than it looks.** Character 5-grams exclusive to the *other*
  track's reference appear in **0.3%** of each transcript, against **68.8% / 80.7%** recall of each
  track's own exclusive 5-grams. But two separate WAV files fed to two `Transcriber` instances have
  no acoustic path between them, so this confirms the plumbing and is **not** evidence about
  **V60**'s mixed-audio cross-talk, which needs one microphone hearing two voices (**V62**).

  **Three limits, stated because each is easy to miss.** The feed ran at **0.920x** of real time
  once sleep is excluded, against a measured ceiling of **0.888x** for the flat `sleep(0.03)` per
  frame the loop uses — so contention is under-represented by roughly **9%**, not by a factor. The
  machine **slept for 4410 s mid-run** (lid closed; `pmset -g log`), so raw elapsed was 8324 s and
  **this run establishes nothing about thermal drift over a continuous hour** — **V65** is that
  measurement, not this one. And the run was taken from a `nice +10` background job, which the
  evidence says did not bind (both awake phases sat on the sleep-overhead ceiling) but which is not
  how a timing measurement should be scheduled.

## The NPU lock costs nothing, and the crash it was written for no longer reproduces

- **V57 — Removing `NPU_LOCK` neither crashes nor speeds anything up on the current toolchain.**
  Measured 2026-08-11 against one hour of two-track conversation (1130 turns, 480 cross-track
  overlaps), `whisper-large-v3-turbo`, three arms in separate subprocesses, decision rule fixed
  before the data existed (`fixtures/asr/NPU_LOCK_TRIAL.md`):

  | Arm | crashed | lines | wall | peak MLX | latency by decile (ms) |
  |---|---|---|---|---|---|
  | locked-1 | no | 812 | 613.2 s | 2092 MB | 1271 1316 1307 1314 1284 1278 1275 1260 1302 **652** |
  | locked-2 | no | 829 | 613.4 s | 2092 MB | 1255 1272 1253 1287 1245 1239 1239 1251 1323 **640** |
  | unlocked-1 | no | 835 | **612.7 s** | 2332 MB | 1441 1269 1241 1024 1214 1241 1247 1248 1270 **652** |

  **No crash.** `AGENTS.md` carries the lock as an invariant on the grounds that *"concurrent
  Metal calls from the two transcriber threads crash the process"*. That was observed on an older
  toolchain and **does not reproduce** on Python 3.12 / `mlx` 0.32.0.

  **No gain either: 0%.** There is one GPU, so removing the lock moves the queue from a mutex to
  the Metal scheduler and buys nothing. **The 2x dual-track cost in V56 is not caused by the
  lock**; it is caused by twice the work on one accelerator.

  **No silent corruption at this resolution.** Unlocked transcripts differ from the locked
  baseline by CER 0.171, against 0.167 between two locked runs — inside the baseline's own
  variability (**V54**).

  **No drift over the hour**, which was the specific worry: per-call latency is flat across nine
  deciles. The tenth falls to ~650 ms because one track runs out of turns first (676 against 454),
  leaving a single stream — and ~650 ms is the single-track figure **V56** measured. Contention,
  not thermal behaviour, explains the whole shape.

  **The lock stays**, on the pre-registered rule: no crash, content within baseline, no speed gain.
  What changes is the *reason* — it is kept because it costs nothing measurable and guards a
  failure mode that may still exist under conditions not tested here, not because concurrent
  access is known to crash this runtime.

  ⚠️ **This is not the realistic turn-taking figure.** The feed was saturating, so both tracks'
  segments arrive together regardless of when they were spoken — the temporal separation that
  makes real conversation cheaper is exactly what the fast feed removes. Measuring that needs
  `--realtime`, an hour per arm.

## The model that was chosen for reproducibility is no longer the one shipping

> ⚠️ **Heading corrected 2026-08-17.** It read *"The chosen model is an order of magnitude more
> reproducible than the one it replaces"*, and the chosen model is now
> `mlx-community/whisper-large-v3-turbo` — the **less** reproducible half of the comparison below.
> **R50** (`docs/decisions/0012`) disqualified the winner on provenance. **V58 is not withdrawn:
> every number in it stands, and the one that now describes the shipping product is the one it was
> written to contrast against.** Read the `0.167` as a cost of the change, not as a historical
> note; **V73** measures whether pinning the decoder to greedy removes it, which is the obvious
> lever and one the previous model never needed.

- **V58 — `Qwen3-ASR-0.6B` runs the product pipeline for an hour without incident, shares weights
  across both tracks, and repeats itself where Whisper does not.** Measured 2026-08-11 on the same
  one-hour two-track conversation as **V57**, three arms, separate subprocesses:

  | | locked-1 | locked-2 | unlocked-1 |
  |---|---|---|---|
  | crashed | no | no | no |
  | lines from 1130 turns | 918 | 905 | 942 |
  | wall | 611.8 s | 611.7 s | 603.0 s |
  | peak MLX | 3578 MB | 3578 MB | 4657 MB |

  **Run-to-run variability is CER 0.025**, against **0.167** for `whisper-large-v3-turbo` on the
  identical fixture — an order of magnitude steadier. **V54** attributed Whisper's spread to its
  temperature ladder falling back to sampling; whatever the cause, the model now shipping does not
  inherit it. For a product whose output a speaker reads aloud under pressure, "the same audio
  gives the same transcript" is worth more than it looks on a table.

  **Weights are shared between the two `Transcriber` instances**: dual-track peak is 3578 MB
  against 3207 MB single-track, +371 MB rather than double. The same holds for Whisper (2092 vs
  2085 MB), which also settles a question **V33** left open — a second instance of the same model
  path does not hold a second copy. Removing the lock costs **+1079 MB**, because two inferences
  are then in flight at once.

  **The mechanism, found 2026-08-13 and measured on this machine.** `mlx_qwen3_asr` keeps a
  process-local `_ModelHolder._cache` keyed by `(model path, dtype)`, so a second instance on the
  same path is a cache hit. The same fact has a consequence this entry did not draw: **stopping
  capture releases nothing.** One warm instance is **1794.3 MB** active; deleting both
  `Transcriber` objects and calling `mx.clear_cache()` frees **0.0 MB**; clearing that cache frees
  **1794.3 MB** — all of it. Post-meeting work that loads its own model would otherwise run
  alongside weights nothing is using.

  **Unlocked was 1% faster and did not crash**, matching **V57** on a different model and a
  different package. Two independent models agreeing that the lock is free is a stronger result
  than either alone.

  It also produces **~10% more lines than turbo from identical audio** (918 against 812), which is
  more of the conversation reaching the buffer — relevant to **R3**, though whether the extra lines
  are correct is a separate question this run does not answer.

- **V71 — The weights are held by `mlx_whisper`, not by the `Transcriber` objects, and clearing
  its holder frees all of them.** Measured 2026-08-17 on this machine, in the product's own path
  and out of the product storage root, after `docs/decisions/0012` replaced the backend:

  | | |
  |---|---|
  | Active MLX memory, model warm | **1543.3 MB** |
  | Freed by `release_models()` | **1543.2 MB** — active drops to 0.1 MB |
  | Transcript after release and reload | identical to before |

  The mechanism is the same shape as the one **V58** found in the package that was removed, and
  the code that had to change is the line naming it: `mlx_whisper.transcribe.ModelHolder` keeps
  the model on a **class attribute**, swapped only when a different `path_or_hf_repo` is asked
  for. Both `model` and `model_path` have to be cleared — clearing only the first leaves
  `get_model()` believing the cache is warm and returning `None`.

  This is what makes the operator's lifecycle rule enforceable on the new backend: *Stop capture is
  退駕*, and the model exists for the session and not one moment longer. Reloading costs a warm-up,
  which is why `Transcriber.warm_model()` exists rather than letting the reload land on a
  speaker's first sentence (**R9**).

  Verified in the same run, and worth as much as the number: the shipped default loads through
  `transcriber.resolve_backend`, transcribes a Chinese fixture correctly with the network
  forbidden, and reloads after being released. Code that builds but has never run is not verified.

## Context biasing recovers proper nouns and destabilises the output language

- **V64 — The single-character guard is defeated by punctuation, so it almost never fires.**
  Found 2026-08-12 in production, not by reading the code. `text_filters.is_acceptable` opens with
  `if not text or len(text) <= 1`, which measures the **raw** string — and the model terminates
  essentially every utterance with punctuation. `哦。` and `じ。` are two characters and pass; only
  a bare `.` is caught. **V60**'s remark that "`.` alone is already caught by the single-character
  guard" was correct and incomplete: it did not check that `啊！`, `嗯。` and `哦。` all survive.

  **Decided 2026-08-12 by the operator: leave the behaviour, correct the documentation.** The
  obvious fix destroys real speech — normalising before measuring length would also drop `是。`,
  `不。` and `Yes.`, and in a hearing a witness answering "Yes." is among the most consequential
  things said. Same objection that emptied the blacklist: **noise costs a line, a destroyed answer
  costs the record.** Removing the guard outright differs from today only by letting a lone `.`
  through, which is not worth a change.

  So **short noise reaches the transcript on purpose** and **R49**'s cleanup pass removes it, where
  a person sees what is being removed. The docstring in `text_filters.py` now says so outright
  instead of implying the noise is filtered, and two tests pin both halves — noise passes, short
  real answers pass — so the change that looks like a bug fix cannot land silently.

  ✅ **Re-checked for the replacement model, 2026-08-17, and the conclusion survives** — which was
  not a foregone result, because the whole finding rests on a *habit* of the model rather than on
  the code. Of 938 outputs in **V72**'s run, **76.3%** end in terminal punctuation, against "essentially
  every utterance" for the model removed. So the habit weakened by roughly a quarter and the guard
  still almost never fires: **274** outputs were three characters or fewer and **17** were dropped —
  the bare `.` and `!` that the guard was always going to catch, and nothing else. `. .`, `...`,
  `Mm.` and `Hmm.` all reach the buffer, exactly as designed.

  **One thing is new and belongs to the model, not the guard:** turbo invents in languages nobody
  in the room is speaking — `Merci.`, `E aí` (Portuguese), `Mm-mm.` appear among the non-speech
  outputs. A blacklist scoped to the deployment's languages would not reach them, which is a third
  independent reason the emptied list stays empty.

- **V60 — The `0/63` that chose the ASR model does not generalise. On real non-speech
  `Qwen/Qwen3-ASR-0.6B` produces text on 23 of 253 segments, and `R37` is therefore not satisfied by
  the model alone.** Measured 2026-08-12, two full passes over 530 inputs, **zero cross-pass
  variance** (the port defaults `temperature=0.0` and takes `mx.argmax` — there is no Whisper-style
  temperature ladder, so a single pass is evidence).

  The **63** non-speech segments behind `docs/decisions/0009` were 63 distinct pieces of audio, all
  from `tools/gen_asr_fixtures.py` — synthesized tones, chimes and keyboard clicks. They reproduced
  **0/63** exactly in this run, in the same process, so what follows is not a harness difference. It
  is what happens when the material stops being programmatic:

  | Class | Produced text | |
  |---|---|---|
  | Programmatic tones / chimes / clicks (the original 63) | **0 / 63** | control |
  | Synthesized paper, chair, phone vibration, throat clear | **0 / 32** | same weakness as the 63 |
  | ESC-50 field recordings, 18 categories | **14 / 186** | real |
  | Room tone — the quietest 0.25 s of real clips, every window below −45 dBFS | **9 / 35** | real |
  | **Genuine non-speech, total** | **23 / 253** | |

  **Two sources, and the second is the one nobody predicted.** Most misses come from a human throat
  — laughter **7 of 13 segments**, then sneezing, coughing, snoring. A speech model firing on
  vocal-tract noise is at least intelligible. But **room tone with no speech in it at all** produced
  `啊。`, `嗯。`, `喂。`, `是。` and `出てきた。` (Japanese), and amplified 30 dB it produced a
  17-fold repetition loop with `finish_reason=repetition`. Silence is not safe input.

  **Silent throughout:** clapping, breathing, footsteps, doors, keyboard typing, clock tick, can
  opening, drinking, crackling fire, water drops, vacuum cleaner, washing machine.

  **The dangerous output is the one no blacklist can reach.** Laughter produced
  `I would like to come for tea.` — a fluent invented sentence. It also produced `Laughter.`, the
  exact subtitle-ghost shape the deleted list existed for. All eight deleted strings were checked
  against every string produced here: **zero matches**. So this does not argue for restoring them;
  it removes the *reason* that was given for deleting them.

  **Not tested, and named so nobody assumes otherwise:** real applause in a hall (ESC-50 `clapping`
  is a few pairs of hands), real paper / chair / phone-vibration / throat-clearing recordings, real
  HVAC, and music with vocals (**V41**). ESC-50 is close-mic'd and normalised, so it reaches the
  model louder than a room microphone would — harsh in the conservative direction.

  Reproduce: `fixtures/asr/results/.probes/` (gitignored; `build_`, `probe_`, `summarize_` scripts
  plus 1060 scored calls). Fetching ESC-50 needs the network and the Homebrew OpenSSL bundle that
  `tools/asr_bakeoff._prefer_homebrew_ssl_bundle` already selects.

  **This is not treated as fixable, decided by the operator 2026-08-12.** Two reasons, and the
  second is the structural one:

  - Laughter and room noise are properties of the room, not defects. A hearing has a gallery in it.
  - **Denoising happens upstream, in whatever application produced the audio, and we inherit
    whatever it did.** We tap system audio (**R1**, **R5**), so a Zoom call arrives already
    suppressed and a Lark call arrives raw — the operator's field observation, not a measurement
    here, and the difference is audible enough to change how speech sounds. Adding our own
    reduction would fight an unknown amount of processing we cannot detect. There is no position
    from which to do it well.

  So **no noise gate and no laughter suppressor enter the live path.** The standing rule applies:
  *during captioning, do not invest in what cannot genuinely be improved.* **R9** already scopes the
  live path to the gist, and the post-meeting cleanup pass (**R49**) is where a human reads the
  transcript before anyone acts on it — that is where these lines are removed, with the whole
  transcript visible and no real-time cost. Re-open this only if a measurement shows the live path
  firing cues on laughter often enough to matter, which is a different question from the count above.

  ⚠️ **The model this describes is no longer the one shipping (2026-08-17, `docs/decisions/0012`).**
  Every number above stands and none of it is withdrawn — but read it as the *better* half of a
  comparison now, not as the product's behaviour. **V72** is the product's behaviour, and it is an
  order of magnitude worse.

- **V72 — The replacement model invents an utterance from almost every piece of real non-speech:
  252 of 253 segments produce text, and 243 reach the buffer.** Measured 2026-08-17 on the same
  253 VAD segments **V60** used, through the same probe, same constants, offline, one candidate per
  process — `tools/probe_nonspeech_real.py`, promoted out of a gitignored scratch directory for
  exactly this reason.

  | Genuine non-speech, 253 identical segments | produced text | reached the buffer |
  |---|---|---|
  | `Qwen/Qwen3-ASR-0.6B` (**V60**, 2026-08-12) | **23 / 253** | — |
  | `mlx-community/whisper-large-v3-turbo` (2026-08-17) | **252 / 253** | **243 / 253** |

  **This is like-for-like, and establishing that took a correction worth recording.** The first
  pass reported *433 of 435*, which was neither comparable nor meaningful:
  `fixtures/asr/nonspeech_real/derived/` holds room tone **and** `quiet_speech_*`, `babble_*`,
  `mumble_*`, `crosstalk_*` and `filled_pauses` — real speech attenuated, overlapped or obscured.
  Text from attenuated speech is bad transcription, not an invented utterance, and **R37** is not
  about it. Counting the buckets separately lands the non-speech denominator on exactly **V60**'s
  253. The probe now reports the split, so the mistake cannot be repeated silently. Degraded
  speech, for the record: **203 / 204** produce text, which is the model doing its job.

  **Reproduced independently the same evening**, in a separate process by a different tool
  (`tools/measure_decode_thresholds.py`'s control arm, which passes the product's exact decoding
  options): **253 / 253** produced text and **240** reached the buffer, against 252 and 243 here.
  The small movement in the filtered column is **V54** exactly — which string appears varies, and
  whether one appears does not. The same run also returned CER 0.214 / 0.138 / 0.145, identical to
  `docs/decisions/0009`'s 2026-08-11 table to three decimal places, which is what licenses reading
  the two runs as one result rather than two.

  **Not a sampling artefact.** A second pass over the same corpus scored **134 / 134** on the
  segments it reached before the run was ended deliberately. **V54** is why passes are repeated at
  all — Whisper's temperature ladder makes a single count a draw from a distribution — but at 252
  of 253 there is no headroom for variance to move the conclusion, so the third pass was cancelled
  rather than completed for tidiness. Same reasoning `docs/decisions/0009` used to cancel a run
  whose result could not change an answer.

  **The synthesized fixtures remain a control and nothing more.** They read 63/63 here, as they did
  in 2026-08-11's bake-off and today's reproduction. Both models treat programmatic audio as a
  different world from a room, in opposite directions — which is the standing lesson: **a clean
  synthetic non-speech run is not evidence about R37.**

  **What it invents is subtitle-corpus wreckage, and that is the part that changes the argument:**

  | Source | Produced |
  |---|---|
  | vacuum cleaner | `Субтитры сделал DimaTorzok` — a **subtitle credit line** |
  | room tone, amplified 20 dB | `Продолжение следует...`, `ご視聴ありがとうございました` |
  | drinking | `시청해주셔서 감사합니다.` |
  | clapping | `Applaudissements` |
  | can opening, washing machine | `We'll be right back.` |
  | throat clear, phone vibrate, footsteps, water drops | `Thank you.` |
  | laughing | `I'm so sorry. I would like to come to town.`, `I don't know.` |
  | door creak, sneezing | `MMMMM…` ×70, `うぇっっっ…` — repetition loops |

  **Two observations follow, and they point at different mechanisms.**

  - **The emptied `HALLUCINATION_PHRASES` was fitted to precisely this.** It held `字幕`,
    `Subtitles`, `Amara.org`, `請訂閱`, `Thank you.`, `謝謝`, `I don't know.`, `Bye.` — Whisper
    ghosts, on these same fixtures. **V60** found **zero** of them in the removed model's output,
    which is what made them look like dead weight; the shipped model produces several of them
    routinely. The list did not stop being right — the model it was written for came back.
  - **A large share are in languages this deployment does not use** — Russian, Japanese, Korean,
    French, Spanish. That suggests a **script gate** rather than a phrase list: drop a line whose
    script is neither Chinese nor Latin, which **R8** already draws as the product's language
    boundary. It reaches `Продолжение следует...` and `시청해주셔서 감사합니다.`, which no
    deployment-specific blacklist could anticipate, and it destroys no utterance a participant in
    this product's meetings would actually make. It is **not** what was decided against on
    2026-08-12, which was a list of strings.

  **What this does and does not license.** It does **not** license reversing the emptied
  `HALLUCINATION_PHRASES`, nor adding a script gate. Both are product-behaviour decisions and the
  first reverses an operator decision made on 2026-08-12 with a stated reason. The counter-argument
  also survives the new evidence and must be carried with it: `Thank you.` and `I don't know.` are
  ordinary meeting speech, and `I'm so sorry. I would like to come to town.` is a fluent invented
  sentence that neither a list nor a script gate reaches. Recorded as an argument to put in front
  of the operator, not a licence to act. It does mean **R37 is
  not satisfied, at all, by the shipped model alone**, which was already true and is now true by a
  much larger margin. Whether Whisper's decoder gates — which the previous model did not have —
  can buy it back is **V73**.

- **V73 — No decoding setting buys back R37. Five configurations, five identical results:
  253 of 253.** Measured 2026-08-17 with `tools/measure_decode_thresholds.py`, two passes per arm
  over the same corpora, one process, offline. **REFUTES** the hypothesis that the replacement
  model's false lines come from the temperature ladder, and with it the cheapest available fix.

  | Arm | Decoding | Non-speech raw | Buffer | Synthetic | CER mixed / zh / en | Wall |
  |---|---|---|---|---|---|---|
  | **A** production today | stock | 253/253 | 240 | 63/63 | 0.214 / 0.138 / 0.145 | **2601 s** |
  | **B** greedy | `temperature=(0.0,)` | 253/253 | 232 | 63/63 | 0.214 / 0.138 / 0.145 | 758 s |
  | **C** greedy + both gates | `no_speech=0.3`, `logprob=-0.5` | 253/253 | 232 | 63/63 | 0.214 / 0.138 / 0.145 | 766 s |
  | **D** greedy + logprob only | `logprob=-0.5` | 253/253 | 232 | 63/63 | 0.214 / 0.138 / 0.145 | 773 s |
  | **E** greedy + gates + repetition | `+ compression_ratio=2.0` | 253/253 | 232 | 63/63 | 0.214 / 0.138 / 0.145 | 771 s |

  **This is not "no arm won the trade-off". There was no trade-off to make** — CER is identical to
  three decimals in every arm, so nothing was even exchanged for the silence that never arrived.

  **The mechanism, measured 2026-08-18 — and it is not the one this entry first gave.**

  ⚠️ The first explanation written here was that `mlx_whisper/transcribe.py:303-311` makes the skip
  an AND, so *"the confidence term vetoes the no-speech term"*. The code is quoted correctly and
  the conclusion was wrong. The real reason is one line earlier:

  > **`whisper-large-v3-turbo` reports `no_speech_prob` = `0.0000` on non-speech. Not low —
  > exactly zero, on 18 of 18 real non-speech segments, min and median and max.**

  The skip's first condition is `no_speech_prob > no_speech_threshold`. Against zero that is false
  for **every positive threshold**, so `should_skip` is never set in the first place and the veto
  never comes into it. This is why five arms produced one answer: they were all tuning a gate that
  was never armed.

  **It is a property of this checkpoint, not of Whisper.** On the identical chime segment, full
  `mlx-community/whisper-large-v3` reports `no_speech_prob` **0.903** where turbo reports
  **0.000**, and real speech sits at **0.05**. Turbo is a **distilled 4-layer decoder** against
  large-v3's 32 (same encoder), and the no-speech token is a decoder prediction — the distillation
  appears to have taken the no-speech head with it. So the gate is not merely mis-set on this
  model; **the signal it reads does not exist**.

  **What that changes.** "No decoding setting fixes R37" stands, and is now explained rather than
  merely observed. But it is no longer evidence that *Whisper* cannot satisfy **R37** — only that
  this checkpoint cannot. Scoring full `large-v3`, whose head is alive on the same audio, is
  therefore not a fishing expedition; it is the direct consequence of this measurement.

  **What did change is cost, and by exactly the ratio V75 measured independently.** Arm A is
  **3.43x** the wall clock of every other arm on identical work — the temperature ladder retrying
  non-speech. So the ladder is responsible for the whole latency penalty and **none** of the false
  lines. Greedy decoding is therefore a free 3.4x saving on noisy input at zero measured accuracy
  cost, which is worth having on its own terms and is a separate question from **R37**.

  ⚠️ **The accuracy figures come from CAiRE/ASCEND, which is reasonably clean.** The ladder exists
  to recover *failed* decodes, so pinning greedy carries an unmeasured risk on genuinely degraded
  speech — the leakage case (**V70**) above all. Adopting greedy needs that measured first; this
  run does not license it.

  **Where this leaves R37: not with a decoding fix.** The remaining levers are a text filter
  (**V72** sets out both options and both are the operator's), a different checkpoint, or
  accepting the cost with **R49**'s cleanup pass behind it. Sweeping more thresholds is refuted
  work, not unfinished work.

- **V76 — The full `large-v3` decoder cuts false lines by a third and buys it with real speech.
  It is a trade, not a fix.** Measured 2026-08-18 on the same 253 segments as **V60** and **V72**,
  same probe, one pass, `mlx-community/whisper-large-v3-mlx` (OpenAI weights, MLX conversion,
  ungated, 3.08 GB — **R50**-clean).

  | | `Qwen3-ASR-0.6B` (**V60**) | `large-v3-turbo` (**V72**) | **`large-v3`** |
  |---|---|---|---|
  | Real non-speech, produced text | **23 / 253** | 253 / 253 | **170 / 253** |
  | Reaching the buffer | — | 240 | **166** |
  | Synthesized non-speech | 0 / 63 | 63 / 63 | **52 / 63** |
  | **Degraded *real* speech** | — | **203 / 204** | **183 / 204** |

  **The last row is the cost and it is easy to skip past.** `quiet_speech_*`, `babble_*` and
  `mumble_*` are real speech that has been attenuated or obscured — a hearing's gallery, a quiet
  witness, a bad line. `large-v3` transcribes **twenty fewer** of them. Against **R37** that looks
  like progress; against **R3** and **R8** it is the product losing utterances somebody actually
  made, and **V64**'s standing principle applies — *noise costs a line, a destroyed answer costs
  the record*.

  **Why it improves at all, and why not further.** Turbo reports `no_speech_prob` = **0.000** on
  non-speech (**V73**), so its gate can never arm. `large-v3`'s head is alive — **0.903** on the
  same chime — which is what a 32-layer decoder retains and a distilled 4-layer one does not. But
  the gate still needs the *second* condition, and at `avg_logprob` −0.827 against a default
  `logprob_threshold` of −1.0 the veto fires and the segment is emitted anyway. So the head being
  alive is necessary and not sufficient.

  **Whether the two populations are separable at all — measured, and the answer is no cleanly:**

  | population | n | `avg_logprob` p5 / med / p95 | `no_speech_prob` p5 / med / p95 |
  |---|---|---|---|
  | real speech | 11 | −0.877 / −0.440 / −0.288 | 0.051 / 0.183 / **0.510** |
  | non-speech that produced text | 766 | −1.060 / −0.820 / −0.279 | **0.143** / 0.451 / 0.906 |

  They overlap on both axes: real speech reaches `no_speech_prob` 0.51 and ghosts come down to
  0.14. **A threshold cannot separate them; it can only choose the exchange rate** between false
  lines and lost quiet speech. ⚠️ The real-speech row is **n = 11** — ten control clips — which is
  enough to show overlap and **not** enough to site a threshold. Anyone tuning one needs a much
  larger speech sample first.

- **V77 — R37 can be bought on the audio side, and the price is half the quiet speech in the
  room.** Measured 2026-08-18: `large-v3` with the tightened gate (`no_speech_threshold=0.3`,
  `logprob_threshold=-0.5`, greedy), same 253 segments, same probe, one pass.

  | Configuration | Real non-speech | **Degraded *real* speech** | Clean speech |
  |---|---|---|---|
  | `Qwen3-ASR-0.6B` (**V60**) | **23 / 253** | *never measured* | *never measured* |
  | `large-v3-turbo`, stock — **shipping** (**V72**) | 253 / 253 | **203 / 204** | 10 / 10 |
  | `large-v3`, stock (**V76**) | 170 / 253 | 183 / 204 | 10 / 10 |
  | **`large-v3` + tightened gate** | **39 / 253** | **91 / 204** | **9 / 10** |

  **39 of 253 is within reach of the model this product gave up.** It is also the row that loses
  **half** of the attenuated, overlapped and obscured speech — `quiet_speech_*`, `babble_*`,
  `mumble_*`, `crosstalk_*` — and one of ten clean control clips as well. Against stock `large-v3`
  the exchange is **131 false lines removed for 92 real utterances destroyed**: roughly **seven
  real utterances for every ten ghosts**.

  **Under this file's own ranking that is not a trade worth making.** **V64** settled the
  principle when the blacklist was emptied — *noise costs a line, a destroyed answer costs the
  record* — and **R3** says the transcript is the record. A quiet witness, a bad line and a gallery
  are exactly the material in that bucket.

  **The generalisation, which is the useful part.** Every lever *inside the decoder* —
  checkpoint, no-speech threshold, logprob threshold, temperature — moves both columns together,
  because it decides *whether to decode at all* given a segment, and the two populations overlap
  (**V76**). A lever on the *text* side can do better, because it reads what was produced: the
  emptied `HALLUCINATION_PHRASES`, or a script gate (**V72** sets out both, and both are the
  operator's).

  ⚠️ **This originally said "the audio-side search is now finished". It was not, and the
  correction is V80.** The sentence generalised *"I swept the decoder"* into *"I swept the audio
  side"*, and skipped the stage before it: the segments here are what `webrtcvad` at aggressiveness
  3 already passed. A **neural VAD in front of the decoder rejects 91% of them and no clean speech
  at all** — better than every lever in this entry and than every one in **V78**. Read this entry
  as being about *decoder* settings, which is all it ever measured.

  ✅ **The missing control was run the same day, and it settles the comparison against us.**
  `Qwen/Qwen3-ASR-0.6B`, same probe, same 253 segments, today's toolchain: **23 / 253** on
  non-speech — reproducing **V60** exactly — and **203 / 204** on degraded speech, which is
  *identical to the shipping model's* 203 / 204. **Its silence was free.** It was not declining to
  transcribe quiet speakers; it separated the two populations, which is precisely what no Whisper
  configuration measured here can do. So *"the old model was better overall"* is now **established
  rather than claimed**, and the cost of **R50** is quantified: roughly **230 additional invented
  lines per 253 non-speech segments, for no accuracy or memory benefit**.

- **V78 — A text-side filter is about four times more efficient than any audio-side lever, and
  still does not close the gap.** Scored 2026-08-18 with `tools/evaluate_text_filters.py` against
  the already-collected output of the shipping model (**V72**'s run) — no GPU, no new inference,
  because the model has already spoken and the only question is what to do with what it said.

  | Filter | Ghosts removed | Real degraded speech destroyed | Clean speech destroyed |
  |---|---|---|---|
  | shipping today (length guard only) | 9 / 252 (4%) | 0 / 203 | **0 / 10** |
  | the emptied `HALLUCINATION_PHRASES` | **86 / 252 (34%)** | 8 / 203 (4%) | **0 / 10** |
  | script gate (**R8**'s language boundary) | 22 / 252 (9%) | 9 / 203 (4%) | **0 / 10** |
  | repetition shape | 17 / 252 (7%) | 2 / 203 (1%) | **0 / 10** |
  | **all three together** | **106 / 252 (42%)** | 19 / 203 (9%) | **0 / 10** |

  **The exchange rate is the point.** Text-side: **5.6 ghosts removed per real utterance lost**,
  and **zero clean speech touched in every variant**. Audio-side at its best (**V77**): **1.4**.
  That is the measured form of the claim in **V77** — a filter that reads what was produced can
  separate populations that a decision about *whether to produce* cannot.

  ⚠️ **The "stacking" estimate first written here was arithmetic, and measuring it moved the
  answer a long way.** It applied the shipping model's 42% to `large-v3`'s 170 and predicted ~99.
  Scored directly, `large-v3`'s ghosts are **far more filterable — 74%** — because a larger share
  of them are `Thank you.`-shaped rather than fluent inventions. The measured combinations:

  | Configuration | Invented lines (of 253) | **Real degraded speech kept (of 204)** | Clean |
  |---|---|---|---|
  | `Qwen3-ASR-0.6B` | **23** | **203** | 10 / 10 |
  | `large-v3-turbo`, stock — **shipping** | 252 | 203 | 10 / 10 |
  | `large-v3-turbo` + text filters | 146 | 184 | 10 / 10 |
  | `large-v3`, stock | 170 | 183 | 10 / 10 |
  | **`large-v3` + text filters** | **45** | **166** | **10 / 10** |
  | `large-v3` + tightened audio gate (**V77**) | 39 | **91** | 9 / 10 |

  **Read the last two rows against each other — that is the whole argument for the text side.**
  They reach almost the same false-line count (45 against 39) and the text route keeps **75 more
  real utterances** and loses no clean speech. The audio route buys its final six lines with
  seventy-five destroyed answers.

  **It still does not return the product to where it was**, and the honest gap is now smaller than
  first stated: 45 against 23, and 166 real utterances kept against 203. Roughly twice the invented
  lines and thirty-seven fewer real ones — not the order of magnitude the raw model comparison
  suggests, and not parity either.

  **The filters do essentially nothing for the removed model** — 2 of its 23 — which is consistent:
  its residue is laughter and room tone rendered as short plausible speech, not subtitle furniture.
  A filter fitted to one model's failure shape is not a general defence.

  **Two things a reader should not take from the table.** The blacklist's 8 destroyed utterances
  are *all* `Thank you.` — one string, and one that is genuinely said in a meeting, which is the
  exact objection that emptied the list on 2026-08-12; the 4% is concentrated, not spread. And the
  script gate would silence a participant who actually speaks Japanese, Korean or Russian — **R8**
  scopes this product to Mandarin and English, so that is in scope by definition and would stop
  being true the moment the product is used outside it.

  ⚠️ **The clean-speech column is disqualifying, and it earned that role immediately.** The first
  script gate written for this table used an *allowlist* of Unicode script names and tested for
  `HAN`, while Chinese characters are named `CJK UNIFIED IDEOGRAPH-…`. It judged every Chinese line
  foreign and destroyed **9 of 10 clean control clips**. A filter's cost column is not a formality;
  it is the only thing that catches a filter which is simply wrong.

- **V79 — V41 is answered and it is total: every music segment becomes an utterance, and sung
  lyrics are transcribed verbatim.** Measured 2026-08-18 with `tools/probe_music.py` on MUSAN's
  music subset, 65 tracks stratified across its five sources, 30 s each, through the product's own
  VAD path and the shipping model.

  | Class | VAD segments | Produced text | Reached the buffer |
  |---|---|---|---|
  | instrumental | 56 | **56** | 53 |
  | vocal | 56 | **56** | **56** |
  | unannotated | 42 | 42 | 42 |

  **V41** was opened on 2026-08-11 — the model then shipping *advertised* singing and
  music-with-backing-track as supported input — and the operator recorded a decision not to test
  it, as an accepted risk rather than evidence of safety. It is now tested, against a different
  model, and the answer is 100%.

  **The failure REQUIREMENTS names by example is reproduced exactly.** *"A Spotify track becomes
  lyrics attributed to `Participant`"*: one Jamendo clip returned
  `Sarà pure frase fatta ma da me trova rispetto Senza te tutti questi anni come ho fatto…` —
  real Italian lyrics, transcribed, ready to be attributed to the far side and to fire a cue.
  Instrumental music returns `Thank you.`, `Outro Music`, `guitar solo` and
  `Really beautiful house!` repeated four times.

  ⚠️ **Level is not controlled** — MUSAN tracks arrive at their own loudness. This establishes
  that the model invents from music, not how loud a track must be in your room to do it.

- **V80 — A neural VAD in front of the decoder rejects 91% of non-speech and touches no clean
  speech. It is the lever the earlier work missed.** Measured 2026-08-18 with
  `tools/measure_vad_gate.py`: Silero VAD applied to the segments **this product's own
  `webrtcvad` already passed**, which is what reaches Whisper today.

  | Population | Reaches the decoder | Rejected |
  |---|---|---|
  | Real non-speech | **22 / 253 (9%)** | **231 (91%)** |
  | Degraded real speech | 146 / 204 | 58 (28%) |
  | **Clean real speech** | **10 / 10** | **0** |
  | Synthesized non-speech | 0 / 63 | 63 (100%) |
  | Music — instrumental | 2 / 56 | 54 (96%) |
  | Music — **vocal** | **15 / 56** | 41 (73%) |

  **22 against the removed model's 23.** Parity on **R37**, reached with OpenAI weights and a VAD,
  inside **R50**.

  ⚠️ **V73 and V77 said the audio side was exhausted. That was wrong, and the error is worth
  naming precisely:** both swept what the *decoder* does — temperature, the two thresholds, the
  compression gate — and compared checkpoints, and neither touched the stage *before* the decoder.
  The 253 segments in **V72** are exactly what `webrtcvad` at aggressiveness 3, a 2011 energy/GMM
  detector, called speech. **"I searched the decoder" was generalised to "I searched the audio
  side."** The field's answer to this problem has been VAD pre-filtering all along —
  `faster-whisper` and WhisperX both ship it — and it is structurally what the removed model did
  internally, which is why its silence was free (**V77**).

  **The 58 rejected real-speech segments are not 58 lost utterances**, and the composition matters
  more than the total: **33 are `filled_pauses`** (isolated "um"/"uh"), **17 are the quietest
  material at −50 and −56 dBFS**, 5 are quiet speech at −38/−44 dBFS, 3 are muffled mumble. And
  **zero** crosstalk, babble, reversed or shuffled mumble were dropped — including the **20
  crosstalk segments, which are the V70 leakage case**.

  **What it does not fix: sung vocals.** 15 of 56 vocal-music segments still reach the decoder,
  because singing *is* voice and a voice detector is right to pass it. **V79**'s risk is reduced by
  roughly three quarters, not removed.

  ⚠️ **Provenance is unresolved and must not be inherited from this measurement.** Silero VAD is
  MIT and Russian-authored; `pyannote` is French and **already a project dependency**, installed on
  demand by `diarize.py`. **R50** as written bars PRC origin only, so neither is excluded — but
  R50 exists *because* provenance is a procurement question here. Silero was measured because
  `torch` was already in the disposable venv, which is a reason to measure and not a reason to
  ship.

  ⚠️ **Installing it broke the measurement venv in the way this repo already documented.**
  `silero-vad` pulled `setuptools` past 81 and `webrtcvad` stopped importing — the exact hazard
  `fixtures/asr/README.md` pins against. Re-pin `setuptools<81` after any install there.

- **V81 — The replacement runs the real dual-track pipeline: weights are shared, the queue never
  backs up, and nothing reaches the network.** Measured 2026-08-18, `tools/soak_capture.py`, three
  minutes through the Core Audio tap and the product's own path — the **first** time the new model
  has run outside a harness.

  | | |
  |---|---|
  | Peak MLX, **two tracks** | 2084.5 → **2087.9 MB** |
  | Lines produced | Speaker 36, Participant 38 |
  | Latency median by fifth (Participant) | 656 / 662 / 660 / 657 / 659 ms |
  | Queue dwell over 74 segments | **median 0 ms, max 0 ms, non-zero 0/74** |
  | Segments contended by the other role | 17/74 (23%) — queue still **0 ms** |
  | `Audio queue full`, inference exceptions, **network requests** | 0, 0, **0** |

  **Weight sharing survives the backend change.** +3.4 MB for a second `Transcriber` rather than a
  second copy — **V58** found the same for the removed model (+371 MB) by a different mechanism,
  and **V71** named this one: `mlx_whisper` holds the model on a class attribute, so the second
  instance is a cache hit.

  **The queue term that "is measured nowhere" is now measured — and the ten-minute rung found what
  the three-minute rung could not.**

  | | 3 min | 10 min |
  |---|---|---|
  | Segments | 74 | 229 |
  | Queue dwell, non-zero | **0 / 74** | **11 / 229** |
  | Queue dwell, max | **0 ms** | **3311 ms** |
  | Peak MLX | 2084.5 → 2087.9 MB | 2084.7 → 2088.3 MB |
  | Latency drift across fifths | none | none |

  At three minutes dwell was flat zero and the honest conclusion was "the ordinary case is clean".
  At ten minutes a segment waited **3.3 seconds** behind others. `STATE.md`'s known issue predicted
  exactly this — *a burst is bounded by nothing* — and had recorded it as unmeasurable. **It is the
  clearest justification in this file for the 3 → 10 → 60 ladder**: the shorter rung was not wrong,
  it was blind, and a single rung would have shipped the wrong conclusion.

  **What it means for R9.** 3.3 s of queue, plus ~0.7 s of inference, on top of **V66**'s 3.75 s
  wait for a segment to close, is a speaker waiting the better part of eight seconds. **V83** is
  the direct answer: rejected audio never enters the queue at all.

  **Zero network requests is R15 observed rather than argued**, in a process that had just
  downloaded nothing because the weights were already local.

  ⚠️ **Three minutes is the first rung of 3 → 10 → 60, not a soak.** It answers "does this path
  work at all today". Drift, memory growth and microphone-device survival are the questions of the
  later rungs, and **V65** / **V69**'s hour still belongs to the removed model until one is run.

  ⚠️ **`.env` still names the removed model, and the product therefore refuses to start.** This run
  needed `--model` to override it, and that flag exists for this reason rather than convenience:
  `.env` is written by the app and never by hand (**R18**, **R32**). Confirmed live — the first
  attempt failed with the **R50** refusal from `resolve_backend`, which is that path working
  correctly. **The operator must re-save the settings form before the application will run.**

- **V82 — `pyannote` at a 0.25 s speech floor rejects 65% of non-speech for 3% of real speech, and
  every setting above that is a worse trade than the one before.** Measured 2026-08-18,
  `tools/measure_vad_gate.py --backend pyannote`, on the segments this product's own `webrtcvad`
  already passes. The operator chose `pyannote` on 2026-08-18 for provenance (**R50**'s intent):
  French, and already a project dependency.

  | `min_speech` | Non-speech rejected | **Real degraded speech destroyed** | Ratio | **Marginal ratio** |
  |---|---|---|---|---|
  | **0.25 s** | 165 / 253 (65%) | **6 (3%)** | **27.5 : 1** | — |
  | 0.40 s | 188 (74%) | 25 (12%) | ~8 : 1 | 1.2 : 1 |
  | 0.60 s | 199 (79%) | 56 (27%) | 3.6 : 1 | 0.35 : 1 |
  | 1.00 s | 224 (89%) | 84 (41%) | 2.7 : 1 | 0.89 : 1 |
  | *(Silero, for comparison)* | *231 (91%)* | *58 (28%)* | *4.0 : 1* | — |

  **Ship 0.25 s, and the marginal column is the reason rather than the totals.** 0.25 → 0.40 buys
  23 more rejections for 19 destroyed utterances; 0.40 → 0.60 buys 11 for **31**. Clean speech is
  untouched at every setting, and all six segments lost at 0.25 s are isolated filled pauses.

  **The two detectors have different shapes, not different quality.** Silero rejects more (91%) and
  costs more (28%); `pyannote` at its knee rejects less (65%) and costs almost nothing (3%). Under
  **V64** — *noise costs a line, a destroyed answer costs the record* — the second is the better
  trade, so the provenance choice and the engineering choice point the same way here. Pushed to
  Silero's rejection rate (`min_speech=1.0`), `pyannote` costs **41%**, worse than Silero at the
  same point: it is not a strictly better detector, it is a better-placed one.

  ⚠️ **This measures what the gate *rejects*, not what it *costs to run*.** A detector adding
  hundreds of milliseconds per segment lands directly in **R9**'s budget, and **V75** already
  showed this pipeline is latency-sensitive on exactly this path. Unmeasured, and deliberately not
  estimated.

  ⚠️ **65% is not 91% and the remainder still reaches the decoder.** 88 non-speech segments would
  still be transcribed, against the removed model's 23. A text-side filter (**V78**) composes with
  this and is the obvious next reduction, but the two have not been measured together.

- **V83 — The voice-activity gate costs 32 ms and saves between 660 ms and 2235 ms. It is a
  latency *win*, not a latency budget item.** Measured 2026-08-18 on a quiet machine, 40 segments
  of median 1.71 s — the shape the live path actually produces.

  | Device | Median | p95 | Max |
  |---|---|---|---|
  | **CPU** | **32.4 ms** | 33.0 ms | 66.3 ms |
  | Metal (MPS) | 22.4 ms | 33.2 ms | 45.8 ms |

  **The arithmetic runs the other way from the concern that prompted the measurement.** Against a
  ~660 ms decode on speech (**V51**, **V81**) the gate is ~5% overhead. Against the **2235 ms** a
  *non-speech* segment costs (**V75**), it is 1.4% — and it removes that decode entirely on the 65%
  it rejects (**V82**). Every rejected segment is a net saving of roughly **2.2 seconds**, and the
  segments it rejects are precisely the expensive ones.

  **So it also attacks the queue.** **V81** measured a 3311 ms dwell at ten minutes; audio the gate
  rejects never enters the inference queue, so the burst it was queued behind gets shorter as well
  as cheaper. The gate is the same answer to **R37** and to **R9**, which is unusual enough to be
  worth stating plainly.

  **Run it on CPU.** 32 ms is comfortably enough, and Metal contends with MLX — the accelerator the
  decoder needs. A 10 ms saving is not worth putting a second consumer on the device that
  `NPU_LOCK` exists to serialise.

- **V84 — Measured through the shipped module, the gate takes the false-line count from 252 to 88
  and costs six utterances. Text filters add less than they did alone.** Run 2026-08-18 with
  `tools/probe_nonspeech_real.py --gate`, which screens through **`src/voice_gate.py` itself** —
  the product's own config parsing, lazy load and fail-open wrapper — rather than through the
  measurement tool's pipeline. **It reproduces V82 exactly (88/253), which is the wiring verified
  rather than assumed.**

  | Configuration | Invented lines (of 253) | **Real degraded speech kept (of 204)** | Clean |
  |---|---|---|---|
  | Nothing — the state before this work | 252 | 203 | 10 / 10 |
  | **Gate only** | **88** | **198** | 10 / 10 |
  | Gate + restored blacklist | 62 | 191 | 10 / 10 |
  | Gate + all three text filters | 43 | 166 | 10 / 10 |
  | *`Qwen3-ASR-0.6B`, for reference* | *23* | *203* | *10 / 10* |

  **The gate does nearly all of the work: 252 → 88, for six utterances.** After it, the text
  filters are working the same easy cases and their ratio collapses — the blacklist removed 86 for
  8 when it ran alone (**V78**) and removes 26 for 7 here. **A mitigation measured alone
  overstates what it adds to a stack**, which is the general lesson and the reason this was
  measured rather than composed on paper.

  ✅ **The cost column over-counted, and the discriminator was run the same day.** Every removal
  from the degraded bucket was scored as real speech destroyed, but the text is not always speech.
  Two checks settled it, neither circular:

  **1. Against true reference text.** `quiet_speech_*` is built from twenty ASCEND clips whose
  transcriptions the build script carries, so CER can be scored on what survives each filter.
  **No filter changes it** — 23/23, 24/24 and 27/28 lines kept, CER identical to four decimals at
  every level. The filters do not touch the material that carries words.

  **2. Where the removals actually come from.** All 25 repetition-filter removals, by source:

  | Source | n | What it is |
  |---|---|---|
  | `mumble_shuffled60ms`, `mumble_muffled350hz`, `mumble_reversed` | **15** | speech deliberately made unintelligible — **reversed audio has no recoverable content by construction** |
  | `filled_pauses` | 4 | isolated "um" / "uh" |
  | `babble_4/6/10talker` | 4 | multi-talker babble, no single recoverable utterance |
  | `crosstalk_2talker`, `quiet_speech_56dbfs` | 2 | the only arguable losses |

  **So 23 of 25 are material that cannot carry an utterance in the first place.** The repetition
  filter is close to free, and the table's "166 kept" for the full stack understates it by roughly
  the same margin.

  **Recorded because it is useful on its own: transcription of quiet speech collapses with level.**
  CER against the true reference is **0.207** at −38 dBFS, **0.301** at −44, and **0.592** at −50 —
  more than half wrong. A line recovered from audio that faint is not obviously worth defending,
  which softens the cost of every gate setting measured here.

  **Recommended, on what is now measured:** the **gate at the 0.25 s floor, plus the blacklist and
  the repetition shape**. The script gate stays out — it removes 6 of 88 and is the one whose cost
  is not explained away. This is a recommendation, not a change: switching any of it on is
  `VAD_GATE` and the blacklist is the operator's (**V72**, **V78**).

- **V85 — A hallucination list derived from measured output the way the field builds them removes
  5% of false lines, and the gap to the hand-written list is entirely the willingness to delete
  real speech.** Measured 2026-08-18 with `tools/derive_hallucination_list.py`, built as a
  **Bag of Hallucinations** — candidates ranked by how often the model produced them *from audio
  containing no speech* — and, unlike the published recipe, **vetoing any string a real speaker was
  recorded producing**.

  Derived from **V72**'s run, scored on the **V84** run — different process, different pipeline, so
  the number is generalisation rather than memorisation:

  | Population | Lines | Removed by the derived list |
  |---|---|---|
  | Non-speech | 88 | **4 (5%)** |
  | Degraded real speech | 198 | **0** |
  | Clean speech | 10 | **0** |

  **The veto is the finding.** Ten candidates were disqualified because real speakers produced
  them, and they were the *frequent* ones: `thank you`, `bye`, `hmm`, `oh`, `mm-hmm`,
  `ご視聴ありがとうございました`. What survives is a residue — `спасибо`,
  `продолжение следует`, `we'll be right back`, an `mmmm…` run — which the held-out run barely
  reproduces.

  **So the modern method does not rescue the blacklist.** **V78** measured the hand-written list at
  34%, and the difference is not technique: that list contained `Thank you.` and `I don't know.`,
  so its 34% was bought by accepting the destruction of ordinary speech. Restricted to strings no
  real speaker was recorded saying, the same idea yields 5%. **This is the 2026-08-12 decision to
  empty the list, confirmed mechanically instead of argued** — and it means the operator's open
  question about restoring it can be answered on evidence.

  ⚠️ **The veto only rejects what the reference corpus happens to contain**, and one survivor shows
  the limit: `i don't know` stayed on the list purely because nobody in ASCEND said it. In a
  hearing it is among the most consequential things a witness can say. **A derived list is safer
  than a guessed one and is not safe** — its blind spot is exactly the speech your corpus lacks.

- **V86 — An hour of the engine: no leak, no drift, nothing to the network — and the queue
  dwell keeps growing every time the run gets longer.** Measured 2026-08-18,
  `tools/soak_capture.py --minutes 60 --gate`, two tracks through the Core Audio tap.

  🚨 **The gate was never live in this run, and the heading used to say "with the gate on".**
  Found 2026-08-19 by grepping the run's own log: `⚠️ [VoiceGate] unavailable
  (LocalEntryNotFoundError)` at warm-up and **zero** rejection lines for the whole hour. The gate
  failed open exactly as designed (**V91**) and transcribed every segment, so **this hour is an
  ungated hour**. Everything below about memory, drift, latency fifths, the tap and queue dwell
  stands — none of it depends on the gate. Everything about the gate is withdrawn: it was not
  costing "nothing visible", it was not running, and *"across 942 segments the gate rejected one"*
  was miscounted off a grep that matched the unavailability warning itself. **The rejection count
  was zero.** The reason the error is instructive: the run reported a healthy hour and a gate-on
  label, and neither the tool nor the summary could tell the difference.

  | | 3 min | 10 min | **60 min** |
  |---|---|---|---|
  | Peak MLX | 2084.5 → 2087.9 MB | 2084.7 → 2088.3 MB | **2084.2 → 2088.3 MB** |
  | Lines | 74 segments | 229 | **942** |
  | Latency median by fifth | flat | flat | **711 / 690 / 667 / 684 / 697 ms** |
  | Queue dwell, non-zero | 0 / 74 | 11 / 229 | **37 / 942** |
  | **Queue dwell, max** | **0 ms** | **3311 ms** | **6913 ms** |
  | `Audio queue full`, exceptions, network | 0, 0, 0 | 0, 0, 0 | **0, 0, 0** |

  **Durability is answered for the replacement model.** Peak memory over an hour is within 4 MB of
  the single-track figure, latency does not drift across fifths, and the tap survives and is
  released. **V65** and **V69**'s hour belonged to the removed model; it now belongs to this one.
  ~~and the gate's 32 ms per segment (**V83**) costs nothing visible~~ — struck out: the gate was
  not running, so this run says nothing about its cost. That claim now rests on **V91**, which
  reproduced the 32 ms directly in the product environment.

  **The queue term grows with observation, which is what "bounded by nothing" means in practice.**
  0 ms → 3311 ms → **6913 ms** across the three rungs. Worst case is now ~6.9 s of queue plus ~0.7 s
  of inference on top of **V66**'s 3.75 s segment close: **about eleven seconds** before a speaker
  sees a line. Three rungs is not a model of the tail, and the honest reading is that **the maximum
  is a function of how long you watch**, not a constant that has been found.

  ⚠️ **This did not test what the gate is for, and the reason is worse than first recorded.** The
  entry originally read *"across 942 segments the gate rejected one"* and called the hour a
  *harmlessness* result — an hour of the gate in the live path breaking nothing. The true count is
  **zero rejections from a gate that never loaded**, so it is not a harmlessness result either:
  what an hour of the gate in the live path does is still unmeasured. It is **not** an
  effectiveness result. Effectiveness is **V82** and **V84**, on a corpus that actually contains
  non-speech. A soak on conversational audio cannot measure a filter for non-speech, and reporting
  its clean run as evidence for the gate would be the mistake this file keeps catching.

- **V87 — On speakers the leak is as legible as the real capture, and it lasts. Headphones are a
  precondition, not advice.** Measured 2026-08-18 by playing `track_B.wav` — whose reference text is
  known — through the speakers and capturing **only** on the microphone.

  | Rung | Microphone lines | **CER, mean of 60 s buckets** | whole-run CER |
  |---|---|---|---|
  | 3 min | 50 / 49 | **0.3871** | 0.2663 · 0.3249 |
  | 10 min | 176 / 165 | **0.3892** | 0.5718 · 0.2966 |
  | 60 min | **489** | *(not re-run)* | 0.5291 |

  **The figure is ~0.39, and the first version of this entry said 0.2663.** Two runs of the
  bucketed metric agree to three decimals — 0.3871 and 0.3892 — while the whole-run figure for the
  same audio ranged 0.2663 to 0.5718 across runs. **0.2663 was the most favourable single
  observation available, and building a claim on it was the error.** Against the intended path's
  **0.214** (**V73**) the leak is therefore roughly **1.8x the character error**, not the five
  percentage points first written here.

  **It is still legible enough to be the problem.** At 0.39 roughly three characters in five are
  right, and whole phrases survive intact — `他的名字叫Tony`, `我平时都喜欢跟Tony一起玩` — none
  of it said by the operator, all of it labelled `Speaker (You)`. Per-bucket values within a single
  run span **0.28 to 0.53**, so legibility varies minute to minute; the worst minutes are near
  gibberish and the best are close to the real capture.

  **V70** reached the same conclusion by comparing the microphone's transcript against the *tap's*,
  which could not separate leakage damage from ordinary error. Ground truth removes that confound
  and the finding survives it.

  **It does not decay:** 489 lines across a full hour.

  ⚠️ **Two corrections, and the second one refutes the first.** The whole-run figures were first
  explained as a metric that *degrades with length* — the tool concatenated the entire run into one
  Levenshtein, which `measure_segmentation.py` already warned against as *"dominated by one early
  insertion"*. Bucketing was the right fix and is now in place. **But the re-run refutes the
  explanation:** whole-run CER went *down* from 3 to 10 minutes (0.3249 → 0.2966), where the
  original run went up (0.2663 → 0.5718). Length was not doing the work — **run-to-run variance
  was**, and it is large enough to swamp the effect I attributed to length. The lesson is not about
  Levenshtein: **a single run of this measurement cannot be quoted**, and the bucketed mean over
  repeated runs is what generalises.

- **V88 — The dual-track penalty is entirely lock wait, and it falls entirely on the track the
  product exists to serve.** Measured 2026-08-18 over a 60-minute acoustic soak, microphone and tap
  both live — 1201 segments.

  🚨 **"gate on" was in this line and it was false.** All three overnight soaks logged
  `⚠️ [VoiceGate] unavailable` at warm-up and rejected nothing (**V91**). The lock-wait finding is
  untouched — it is about `NPU_LOCK` ordering, which the gate does not participate in — but this is
  an **ungated** hour, and the sentence below claiming **V65**/**V69** now hold *with the gate on*
  holds only for the engine without it.

  | Track | NPU time (median) | **Lock wait (median)** |
  |---|---|---|
  | `Speaker (You)` — microphone | 618 ms | **0 ms** |
  | `Participant` — tap | 606 ms | **573 ms** |

  **The model does identical work for both.** The 2x that **V56** recorded as "two `Transcriber`
  instances serializing on `NPU_LOCK` cost exactly 2x per call" is now resolved into its parts: it
  is not 2x for both tracks, it is **1x for one and 2x for the other**, the difference is pure
  waiting, and the same track waits every time — a 0 ms against 573 ms median is systematic, not a
  coin toss.

  **`Participant` is the far party.** The product exists to put their question in front of the
  speaker in time to answer it (**R9**), and that is the only track paying the full penalty. The
  operator's own voice — the least useful thing for prompting — always wins the lock.

  **This is actionable without new hardware:** the penalty is ordering, not capacity. Nothing here
  proposes a change; **R9**'s budget is where a change would have to justify itself.

  **Stability, over the hour:** medians flat across all five fifths (635 / 1176 ms), peak MLX
  +0.4 MB, microphone RMS moving on all 180 samples, tap alive and released, zero exceptions and
  zero network requests — the last of those confirmed against the log, which contains no
  `huggingface.co` at all, so `enforce_offline` held even while the gate was looking for weights it
  could not find. **V65** and **V69** now hold for the replacement model *through the real
  microphone*, which is the arrangement they were written about — **ungated**.

  ⚠️ **A 13.6 s queue dwell in the 3-minute rung was start-up backlog, not steady state**, and was
  briefly reported as though it were. The large waits all fall 52-59 s after launch and climb
  monotonically — a backlog draining while the model is still warming. Steady state is 6.5 s max
  over an hour, comparable to the muted run's 6.9 s.

- **V89 — The segmentation table's false-line column has saturated, so it no longer chooses
  anything.** **V66** re-run 2026-08-18 against the replacement model, ungated, same four
  strategies.

  | Strategy | CER | Median call | Total inference | **False lines** |
  |---|---|---|---|---|
  | `flush=0.4` (production) | 0.3923 | 624 ms | 91.7 s | **178 / 186** |
  | `flush=0.8` | **0.3158** | 664 ms | 45.0 s | 107 / 114 |
  | `flush=1.5` | 0.4059 | 728 ms | 33.0 s | 78 / 82 |
  | `window=8s` | 0.3824 | 657 ms | 64.8 s | 102 / 104 |

  **V66**'s direction survives — `flush=0.8` still wins CER by about a fifth, and the latency
  argument for keeping 0.4 is untouched because it is arithmetic about silence, not about the
  decoder. **What does not survive is the column that used to decide.** For the removed model it
  read 13 / 186 against 10 / 114 — a real difference between strategies. It now reads **95% to 98%
  everywhere**. A saturated metric cannot inform a choice, and reading the 78/82 row as "flush=1.5
  is safest" would be reading noise.

  **CER is roughly 2.2x worse than V66 recorded** (0.3923 against 0.1774), which is the model
  change and not the segmentation.

- **V90 — 88% of Chinese output is Simplified.** Counted 2026-08-18 across every scored run
  (`looks_traditional_chinese` over all stored transcripts): **67 Simplified against 9
  Traditional**, of 76 lines carrying Chinese. **R10** wants Traditional for the Taiwan context.
  Previous entries recorded only the observation *"simplified-leaning"*; this is the number.
  **R9** scopes the live path to the gist and **R10** is explicitly subject to it, so this is a
  post-processing concern (**R49**) rather than a model defect — but it should be stated as a
  proportion rather than a leaning.

  ✅ **Dispositioned by the operator 2026-08-20: accepted as is, no post-processing.** Their word was
  *無所謂* — it does not matter. **R10** wants Traditional for the Taiwan context and is explicitly
  subject to **R9**, so the live path keeps whatever the model emits and no conversion is built.
  **V104**'s 81% therefore stands as a recorded property of the output rather than an open defect,
  and `R49`'s cleanup pass remains where a person could change it by hand if a particular meeting
  needs it.

- **V91 — Every soak that reported "gate on" ran with the gate failed open, because the gate's
  weights were only ever in the disposable bake-off cache.** Found 2026-08-19, not by a test —
  by turning the gate on by hand in the product environment and watching it fail.

  | Where | `ivrit-ai/pyannote-segmentation-3.0` present? | Consequence |
  |---|---|---|
  | `.hf_cache-bakeoff/hub/` (disposable, Python 3.12) | **yes**, 5.6 MB | **V82**, **V84** are real: 252 → 88 |
  | `.hf_cache/AegisPrompter/models/hub/` (the product's `HF_HOME`) | **no** | every gated soak failed open |

  **The mechanism, and every step of it is correct behaviour.** `bootstrap.apply_environment` derives
  `HF_HOME` from the storage root (**V19**), `soak_capture.py` calls `bootstrap.enforce_offline()`
  before warm-up, `pyannote`'s `Model.from_pretrained` therefore cannot reach the Hub, `voice_gate._load`
  catches the `LocalEntryNotFoundError`, sets `_FAILED`, logs `⚠️ [VoiceGate] unavailable` **once**, and
  `has_speech` returns `True` for the rest of the process. **A gate that fails open transcribes
  everything, which is indistinguishable from a healthy ungated run in every number a soak prints.**

  **What it invalidates:** the gate label on **V86** and on **V88**, and the three overnight soaks of
  2026-08-18 — `soak_mic_3min`, `soak_mic_10min`, `soak_mic_60min`, all three carrying
  `⚠️ [VoiceGate] unavailable` and **zero** rejections. **What it does not touch:** **V82** and
  **V84**, which ran in the bake-off environment where the weights exist, and every durability figure,
  which does not depend on the gate.

  ✅ **Fixed by a local copy, no network involved** — the weights were already on this machine, 5.6 MB,
  copied from the bake-off cache into the product `HF_HOME`. Verified immediately afterwards in the
  product venv with `enforce_offline()` applied: `[VoiceGate] … loaded on CPU`, and two seconds of
  digital silence now returns **`False`**. That verdict is the discriminator — **every failure path in
  `has_speech` returns `True`**, so `False` cannot be produced by a gate that did not run. Load took
  **6.0 s** once per process; the warm call took **32 ms**, reproducing **V83**'s figure in the product
  environment rather than the bake-off one.

  ⚠️ **The preflight check could not have caught this and still cannot.** `run_overnight.sh` prints
  `voice gate available True` from `importlib.util.find_spec("pyannote.audio")` — package importability,
  which was always true. The weights are the part that was missing, and nothing observed them. A check
  that cannot fail for the reason the thing actually breaks is decorative.

  ⚠️ **TLS interception is real on this machine but is not the cause.** A fetch attempted *without*
  `enforce_offline` dies on `CERTIFICATE_VERIFY_FAILED` against a Cloudflare `Gateway CA` in the System
  keychain, so the gate could not have self-healed by downloading. Inside the product's offline
  enforcement it never gets that far. Recorded so the SSL error is not mistaken for the mechanism.

- **V92 — The gate reproduces in the shipped environment, and turning it on makes nothing worse:
  88 of 253 again, clean speech untouched.** Measured 2026-08-19 after **V91** put the weights where
  the product can reach them. Both arms run in the **product** venv against the product's own
  `HF_HOME` with `HF_HUB_OFFLINE=1`, same 467 inputs, one pass each, so *off* and *on* is a single
  comparison rather than a claim carried across environments as **V84**'s was.

  | Bucket | n | Gate **off** | Gate **on** | Removed |
  |---|---|---|---|---|
  | Non-speech (**R37**) | 253 | 239 | **88** | 151 — **63%** |
  | Degraded real speech | 204 | 203 | **198** | 5 — 2.5% |
  | **Clean speech** | 10 | **10** | **10** | **0** |

  **88 and 198 are V84's numbers to the line.** V84 ran in `.venv-bakeoff` against
  `.hf_cache-bakeoff`; this run shares nothing with it but the corpus, and lands on the same two
  counts. The gate rejected **171 of 467** calls before the decoder — 165 non-speech, 6 degraded.

  **The discriminators were written before the run and none of them fired.** *Ineffective* would
  have been a gated non-speech count near 200; it is 88. *Worse than off* would have been clean
  control dropping below 10/10; it did not move. *Too expensive* would have been degraded speech
  falling well below 198/204; it is exactly 198.

  **Cost, measured rather than inherited:** a rejected input costs a median **33 ms**, reproducing
  **V83**'s 32 ms outside the bake-off, against **3142 ms** median to decode those same inputs when
  ungated. Total measured work fell **1179 s → 693 s**, a **41%** saving, and the median kept input
  moved 647 → 660 ms — the gate's cost is invisible on the material it passes.

  ⚠️ **The ungated baseline here is 239 of 253, where V72 and V84 recorded 252.** Same model, same
  corpus, different environment and a different day. Thirteen lines is 5% of the denominator and it
  is unexplained — decode nondeterminism and an environment difference are both live, and neither
  has been tested. It does not move the finding, because both arms of *this* comparison share the
  baseline, but any cross-run subtraction against **V84**'s 252 is invalid until it is explained.

  ⚠️ **Wall clock disagrees with the measured time and I could not account for it.** The passes took
  2761 s ungated and 5885 s gated, while summed per-input time went the other way — 1179 s to 693 s.
  Unaccounted time is 57% of the off arm and **88%** of the on arm. It is present in both arms, so it
  is not the gate, but it is not identified. **Quote the per-input figures; the wall-clock comparison
  is not evidence of anything.**

- **V93 — The token-free diarization path stopped being token-free at pyannote.audio 4, and the
  2026-08-17 verification could not have caught it.** Found 2026-08-19 while trying to make speaker
  separation run without the operator.

  `src/diarize.py` names three pieces and says every one is ungated: the MIT pipeline config
  `ivrit-ai/pyannote-speaker-diarization-3.1`, the segmentation model
  `ivrit-ai/pyannote-segmentation-3.0`, and pyannote's own `wespeaker-voxceleb-resnet34-LM`
  embedding. **All three still are, and all three are now in the product cache.** The pipeline
  still fails to load.

  | Piece | Gated? | Where it comes from |
  |---|---|---|
  | pipeline config (MIT) | no | the 3.1 config, as documented |
  | segmentation | no | `ivrit-ai` re-host, in cache since **V91** |
  | embedding, 26.6 MB | no | `pyannote/wespeaker-voxceleb-resnet34-LM`, CC-BY-4.0 |
  | **PLDA calibration `plda/xvec_transform.npz`** | **yes — HTTP 401 without a token** | **`pyannote/speaker-diarization-community-1`, which nothing in this repo names** |

  **The mechanism.** In `pyannote.audio` 4.0.7 the `SpeakerDiarization` pipeline takes a `plda`
  parameter whose **default** is `{"checkpoint": "pyannote/speaker-diarization-community-1",
  "subfolder": "plda"}`, and `__init__` calls `get_plda` unconditionally. A 3.1-era config does not
  mention `plda`, so the default applies; `get_plda` accepts a `PLDA`, a `str` or a `dict` and
  raises `TypeError` on `None`, so there is no supported way to ask for no calibration. The
  requirement is a property of the **installed version**, not of any repository named in the config.

  **Why the earlier check missed it, which is the transferable part.** 2026-08-17 verified *the
  repositories* — that each was reachable and ungated. What decides whether a token is needed is
  *what the installed library asks for*, and only loading the pipeline can answer that. **A
  dependency audit of the artefacts named in a config does not cover the artefacts the code adds.**

  ⚠️ **`src/diarize.py`'s advice is therefore wrong for the installed version** — it offers
  `UNGATED_ALTERNATIVE` as the way to avoid a token, and on 4.0.7 it does not. The comment is
  corrected in place; the behaviour is not, because the fix is a choice between a token and a
  pinned `pyannote.audio` 3.x, and pinning would also move the version the **voice gate** runs on,
  which every gate measurement from **V82** onward was taken with.

- **V94 — The generative advisor produces tokens for the first time, declines correctly on most
  question shapes, and on one shape it both ignores the decline protocol and invents figures.**
  Measured 2026-08-19 against `mlx-community/Llama-3.2-3B-Instruct-4bit` served by `mlx_lm.server`
  on loopback, through `advisors.LlmAdvisor` and `advisors.build_messages` — **the production
  prompt and the production transport**, not a stub. **R30** called this slot unverified; this is
  the first evidence of any kind about it.

  **It works, and the decision it makes is mostly the right one.** Four question shapes, one call
  each: a bare question with no context — declined; social filler inside a real exchange
  (*"Thanks, that's helpful."*) — declined, which is the **V23** flooding case; a challenge
  answerable from the transcript — answered, correctly, `11,000`; a challenge about something the
  transcript does not contain — declined on 4 of 5 subjects (headcount, vendor, date, cost).
  Latency is 116-431 ms.

  🚨 **On one subject it invents a figure, and a different one each time.** Asked *"what was the
  error rate over that period?"* against a transcript that never mentions error rates, six
  identical calls produced **six answers and no declines**, five of them textually distinct:

  | Run | Returned |
  |---|---|
  | 1, 3, 5, 6 | *"Error rate data is not available."* / *"was not reported."* / *"was not provided."* |
  | 2 | *"The error rate was less than 0.1%."* |
  | 4 | *"The error rate decreased from 0.5% to 0.1% over the period."* |

  Two earlier single calls on the same prompt gave **0.01%** and **0.05%**. **A different number
  every time is the signature of fabrication rather than retrieval**, and it is the discriminator
  that makes this a finding rather than an impression.

  🚨 **The second failure is separate and arguably worse, because it is silent.** Four of those six
  runs *correctly* had nothing to offer — and said so **in prose** rather than returning the
  `PASS` sentinel the prompt asks for. `is_pass` matches `PASS` and empty text only, so the
  application treats *"Error rate was not provided."* as advice and would put it on the
  teleprompter. **That is V23's flooding, reached by a route V23 did not describe**: not a model
  that talks too much, but a model that declines in the wrong vocabulary.

  **Limits, and they are wide.** One model, one prompt, one endpoint, six runs on the failing shape
  and one run on each of the others. This does not establish a rate, and a larger model may behave
  differently. What it does establish is that **both failures are reachable with the shipped prompt
  on the first model anyone tried**, which is what **R30** asks the operator to judge — and the
  judgement can now be made on evidence rather than on a disclaimer.

  ⚠️ **Widening `is_pass` to catch prose declines is the obvious fix and is not obviously right.**
  Matching phrases like *"not available"* would also swallow a genuine answer that happens to
  contain them, and the failure mode of that mistake is silence at a hearing, which **V64**'s
  ranking puts above noise. Recorded as a finding, not fixed.

- **V95 — At the shipped threshold the retrieval advisor never fires on a paraphrase, and the
  product cannot show that it is silent.** Measured 2026-08-19 with `tools/probe_rag_cues.py`:
  five invented briefing notes indexed with the **real** embedding model into a temporary
  collection, then ten labelled utterances scored through `local_advisor.analyze_dialogue`.

  | Expected | Utterance kind | Score | Fired at 0.65? |
  |---|---|---|---|
  | fire | "how much faster did the pipeline get" | 0.474 | **no** |
  | fire | "did the programme come in over budget" | 0.366 | **no** |
  | fire | "how long to recover if storage fails again" | 0.634 | **no** |
  | fire | 你們的資料要留多久? | 0.540 | **no** |
  | fire | 客服的回應速度有改善嗎? | 0.574 | **no** |
  | quiet | five logistics / small-talk lines, two of them Chinese | 0.033-0.380 | no ✅ |

  **0 of 5 cues fired. Every quiet case correctly stayed silent.** Each `fire` utterance is a
  *paraphrase* of a note, never a copy, so this is not string matching with extra steps.

  **The retrieval is fine and the number is wrong.** The two populations barely overlap — the
  highest quiet score is 0.380 and the lowest fire score is 0.366 — so a sweep separates them:

  | Threshold | Fires | False |
  |---|---|---|
  | 0.35 | 5/5 | 1/5 |
  | **0.45** | **4/5** | **0/5** |
  | 0.55 | 2/5 | 0/5 |
  | **0.65 (shipped)** | **0/5** | **0/5** |

  Ties in that sweep go to the *higher* threshold on purpose: a missed cue costs the speaker a cue,
  a false cue costs attention on a teleprompter, and **R9** is a claim about attention.

  🚨 **`0.65` has never been measured against anything, and `advisors.py` says as much about its own
  alternative.** The constant has shipped since Phase 6; **V22** documents *that the threshold is
  the intent judgement*, not that this value is the right one. The comment above `SERVE_THRESHOLD`
  records a proposed lower edge of **0.45** and notes it "had never been measured against anything"
  — and 0.45 is exactly where this sweep separates the populations. The number someone proposed on
  instinct was closer than the one that shipped.

  🚨 **The consequence is a feature that is silently dead.** People paraphrase; that is what asking
  a question is. So in a real meeting the retrieval slot would stay blank — and **V34** and **V35**
  already established that advisor liveness is visible *before* a meeting and not *during* one, so
  **the product cannot distinguish "nothing matched" from "the gate sits above every attainable
  score".** Nobody watching the screen would learn this. It took a probe with labelled
  expectations, which is why the stubbed-embedding tests could never have found it.

  **Limits, and they matter before anyone edits the constant.** Ten utterances, five invented notes,
  one embedding model, one collection. That is enough to show **0.65 fires nothing on paraphrases**
  — a claim about one number that needs a single counterexample and has five — and **not** enough
  to fix the value. Changing `SERVE_THRESHOLD` is a product decision under **R9**, and it should be
  taken against a larger and less self-authored set than notes written by the same session that
  wrote the queries.

- **V96 — V87's missing hour is measured: the speaker leak holds at ~0.41 CER over a full hour. And
  the bucketed mean that V87 introduced as a *fix* has its own failure, which only appears at
  length.** Measured 2026-08-19/20, `tools/measure_speaker_leakage.py` at 3, 10 and 60 minutes,
  volume 45, capturing on the microphone only while a known reference plays through the speakers.

  | Rung | Lines | Buckets | mean | **median** | clipped mean | buckets > 1.0 |
  |---|---|---|---|---|---|---|
  | 3 min | 48 | 3 | 0.4055 | 0.3202 | 0.4055 | 0 |
  | 10 min | 162 | 10 | 0.3874 | 0.3780 | 0.3874 | 0 |
  | **60 min** | **487** | 44 | **0.8388** | **0.4096** | 0.4529 | **3 — 1.2, 2.2, 16.6** |

  **The finding V87 was waiting for.** Its table marked the 60-minute bucketed figure
  *(not re-run)*. By median it is **0.4096**, against 0.3871 and 0.3892 for the two rungs V87 did
  score and 0.3202 / 0.3780 here. **The leak does not fade over an hour** — 487 lines, and the
  character error rate at 60 minutes is the same as at 3. **V87's conclusion stands: headphones are
  a precondition, not advice.**

  🚨 **Do not quote the 60-minute mean of 0.8388.** CER is edits divided by reference characters, so
  a bucket whose reference is short and whose hypothesis is long is **unbounded** — one bucket here
  scored **16.59**. With 44 buckets the mean is decided by that single bucket; the 3- and 10-minute
  rungs escaped only because 3 and 10 buckets are unlikely to contain one. **The metric's error
  grows with the number of buckets, which is to say with the length of the run it was introduced to
  make safe.**

  **The irony is the transferable part.** **V87** replaced a whole-run CER *because* it was
  "dominated by one early insertion", and the bucketed mean it replaced it with is dominated by one
  bad bucket instead. The failure moved; it did not go away. **Median and a clipped mean both
  survive it** — 0.4096 and 0.4529 here, against 0.8388 — and they agree with each other and with
  the short rungs, which is the check that says the pathology is in the aggregation and not in the
  audio.

  ⚠️ **`cer_bucketed_60s` in the tool's JSON is the unclipped mean**, so every consumer of that
  field inherits this. Not changed while the queue that produces it was running; the numbers above
  were computed from `cer_buckets`, which the tool also writes and which is why this was visible at
  all. **Recording the raw per-bucket list is what made the summary statistic auditable** — a tool
  that had written only the mean would have reported 0.8388 as the hour's leak and nothing would
  have contradicted it.

  ✅ **Fixed and rescored 2026-08-20.** `measure_speaker_leakage.py` now writes the **median** as
  `cer_bucketed_60s`, keeps the mean under `cer_bucketed_60s_mean`, adds a clipped mean, and lists
  any bucket above 1.0 — so a reader sees the disagreement instead of inheriting one number. Every
  stored run was rescored from the `cer_buckets` lists that made this visible:

  | Run | Buckets | **Median** | Mean | Clipped | Over 1.0 |
  |---|---|---|---|---|---|
  | 08-18 bucketed, 3 min | 3 | 0.4095 | 0.3871 | 0.3871 | 0 |
  | 08-18 bucketed, 10 min | 10 | 0.4082 | 0.3892 | 0.3892 | 0 |
  | 08-19 2121, 3 min *(false start)* | 3 | 0.3276 | 0.3097 | 0.3097 | 0 |
  | 08-19 2121, 10 min *(false start)* | 10 | **0.5582** | **0.9467** | 0.5723 | **2** |
  | 08-19 2230, 3 min | 3 | 0.3202 | 0.4055 | 0.4055 | 0 |
  | 08-19 2230, 10 min | 10 | 0.3780 | 0.3874 | 0.3874 | 0 |
  | **08-19 2230, 60 min** | 44 | **0.4096** | **0.8388** | 0.4529 | **3** |

  **The median is stable where the mean is not: spread 0.2380 against 0.6370, a factor of 2.7.**
  That is the quantitative form of the finding — not that one hour was misreported, but that the
  mean's error scales with bucket count while the median's does not.

  ⚠️ **One earlier statement of mine needs narrowing.** The false start's 3- and 10-minute rungs were
  called "valid results" when its 60-minute rung was voided. The 10-minute rung carries **two**
  buckets above 1.0 and a mean of **0.9467**, so *its mean* was never usable either. Its median,
  0.5582, is — and it is the highest median in the set.

- **V97 — The gate has now run live for an hour, and it costs nothing measurable while more than
  halving the worst queue dwell.** Measured 2026-08-19/20, 60-minute acoustic soak, microphone and
  tap both live, **gate verified live before the run started and zero `[VoiceGate] unavailable`
  warnings in the log** — the check **V91** added, doing its job. 1128 segments,
  **67 rejected by the gate before the decoder**.

  **This is the arrangement V86 and V88 claimed and did not have.** Both were labelled *gate on* and
  both failed open (**V91**); their numbers are an ungated engine. Same tool, same fixture, same
  machine, one variable changed:

  | | **V88 — ungated** | **tonight — gated** |
  |---|---|---|
  | Gate rejections | **0** (failed open) | **67** |
  | Queue dwell, max | **6521 ms** | **2898 ms** |
  | Queue dwell, non-zero | 65 / 1201 | 38 / 1128 |
  | `Speaker (You)` lines | 634 | 570 |
  | `Speaker` median by fifth | 631-644 ms | 646-661 ms |
  | `Participant` median by fifth | 1170-1189 ms | 1143-1210 ms |
  | Peak MLX over the hour | +0.4 MB | **+4.1 MB** (2084.2 -> 2088.3) |
  | Exceptions / network / queue-full | 0 / 0 / 0 | **0 / 0 / 0** |

  **The predicted second-order effect is real.** `voice_gate.py` argued that "rejected audio never
  enters `inference_queue`, so the queue dwell **V81** measured gets shorter as well as cheaper".
  Measured: **worst-case dwell falls 6521 -> 2898 ms, a 56% reduction**, and non-zero dwell falls
  from 5.4% of segments to 3.4%. The gate's own 32 ms (**V83**, **V92**) buys back head-of-line
  blocking, which is the term **V67** identified as the tail's cause.

  **Latency is unchanged within noise.** Both tracks' medians sit inside the ungated run's spread
  across all five fifths — 646-661 against 631-644, and 1143-1210 against 1170-1189. **Flat across
  fifths in both arms**, so nothing drifts over the hour.

  **Durability holds with the gate in the path.** RMS moved on all 180 samples, the tap survived and
  was released, zero exceptions, zero network requests. **V65** and **V69** now hold for the
  replacement model *with the gate actually running*, which no previous run can claim.

  ⚠️ **64 fewer `Speaker` lines than the ungated arm, against 67 rejections.** Consistent, and this
  soak cannot say whether those lines were noise or speech: the effectiveness question belongs to
  **V84** and **V92**, on a corpus that contains labelled non-speech. **V86**'s warning stands —
  a soak on conversational audio measures harmlessness, not effectiveness.

- **V98 — Retention writes two distinct files, and R2's "never mixed" is an observation for the
  first time.** Measured 2026-08-20 with `soak_capture.py --retain`. The retention toggle shipped 2026-08-13
  and **no run had ever written a retained file**, so the promise had only ever been an
  argument about code.

  | Track | Duration | Bytes | Format |
  |---|---|---|---|
  | `mic` | 180.1 s (**+0.1 s** vs the soak) | 5,762,924 | 16 kHz, 1 ch, 16-bit |
  | `system` | 180.2 s (**+0.2 s** vs the soak) | 5,767,724 | 16 kHz, 1 ch, 16-bit |

  **Two files, and they are not the same file twice.** `distinct files: True` and
  **`first 5s differ: True`** — the second is the one that matters, because two paths holding one
  stream would satisfy every other check while breaching **R2**. That failure mode is the same shape
  as **V91**'s fail-open gate, which is why it is asserted rather than assumed.

  **No audio is lost at the edges**, which is what **V12** put on the critical path: both tracks are
  within 0.2 s of the soak's own duration, so retention neither truncates nor pads.

  ⚠️ **Three minutes, not an hour, and deliberately.** Two files with correct durations and
  different contents does not need sixty minutes, and retention writes continuously — folding it
  into the gated soak would have moved the very latency numbers **V97** exists to report. What is
  therefore **not** established: whether an hour of continuous writing drifts, fragments, or fills a
  disk. The 10-minute rung runs next; nothing here speaks for a full meeting.

- **V99 — The advisor's failures are rare, concentrated in one question shape, and accompanied by a
  worse one nobody was looking for: it declines questions it can answer.** Measured 2026-08-20 with
  `tools/probe_advisor.py`, **20 calls across each of 7 labelled cases, 140 in total**, through the
  production prompt and transport. This is **V94**'s "reachable" turned into a rate.

  | Case | Answerable | Correct | Fabrication | Prose decline | Missed |
  |---|---|---|---|---|---|
  | throughput-present | yes | **20/20** | — | — | 0 |
  | **duration-present** | **yes** | **1/20** | — | — | **19/20** |
  | **error-rate-absent** | no | 3/20 | **3/20** | **14/20** | — |
  | headcount-absent | no | **20/20** | 0 | 0 | — |
  | cost-absent | no | **20/20** | 0 | 0 | — |
  | date-absent | no | **20/20** | 0 | 0 | — |
  | filler | no | **20/20** | 0 | 0 | — |

  **Fabrication is real, rare, and localised: 3 of 100 unanswerable calls (3.0%)** — and **all three
  are the same question shape**. Four other unanswerable subjects declined 20/20. So **V94**'s
  finding survives with its severity reduced and its scope sharpened: this is not a model that
  invents freely, it is a model with one bad shape.

  **The prose-decline problem is 4.7x more common than fabrication: 14 of 100 (14.0%)**, again all in
  that one shape. Within it, only **3 of 20** used the `PASS` sentinel; **17 of 20** replied in a way
  `is_pass` does not recognise, so the application would have displayed all seventeen as advice. The
  route **V23** did not describe is the dominant failure.

  🚨 **The new finding, and it was not what this probe was built to look for: the advisor declines
  answerable questions.** *"How long did the programme run?"* against a transcript stating *"ran for
  eighteen months"* was answered **1 time in 20**. The other answerable case — where the answer is a
  numeral, `11,000` — was answered **20/20**. **n=2 shapes, so the pattern is a hypothesis, not a
  finding**: it may answer when the answer is a numeral and decline when it is words. Cheap to test
  and untested.

  **Read with V95, the two advisor slots are both largely mute.** Retrieval fires **0 of 5** on
  paraphrases at the shipped threshold; the generative slot misses **19 of 20** on an answerable
  question. **R30** asks the operator to judge whether this slot is worth having, and the honest
  summary is that the danger is smaller than **V94** implied and the *silence* is much larger.

  **Limits.** One model, one prompt, seven hand-written cases, one endpoint. The rates are rates *for
  these cases*, and the case that fails is one of two numeric-absent shapes tried, so 3% and 14% are
  properties of this mix rather than of meetings.

- **V100 — V95 reproduced exactly on an independent run.** 2026-08-20, same probe, fresh temporary
  index: **0 of 5 cues fired, 0 of 5 false positives**. The shipped `SERVE_THRESHOLD` of 0.65 sitting
  above every attainable paraphrase score is therefore not a one-run artefact.

- **V107 — V99's digits-versus-words hypothesis is refuted. The advisor declines *"How long…?"*
  questions and answers everything else, and V99's 52% was an artefact of two cases.** Measured
  2026-08-20 with `tools/probe_advisor.py`, 20 calls per case, 11 cases then 13.

  **The hypothesis, refuted.** **V99** answered a numeral-valued question 20/20 and a word-valued one
  1/20, and offered "it may answer numerals and decline words" as a hypothesis rather than a finding.
  Four cases pairing the *same fact* in both forms say otherwise:

  | Case | Answer form | Correct |
  |---|---|---|
  | `240 milliseconds` | digits | **20/20** |
  | `a quarter of a second` | **words** | **20/20** |
  | `7 engineers` | digits | **20/20** |
  | `seven engineers` | **words** | **20/20** |

  **The real cause, isolated one variable at a time.** The failing case differed from the passing
  ones in two ways at once — a trailing clause unrelated to the question, and *"How long"* phrasing.
  Separating them:

  | Case | Trailing clause | Phrasing | Result |
  |---|---|---|---|
  | `duration-present` | present | *How long* | **17/20 missed** |
  | `how-long-no-trailing-clause` | **removed** | *How long* | **20/20 missed** |
  | `how-many-with-trailing-clause` | **present** | *How many* | **20/20 correct** |

  **The trailing clause is irrelevant; the question form decides it.** Removing the clause made it
  *worse* — a clean 20/20 miss — while keeping the clause and changing only the interrogative gave a
  clean 20/20 answer. **The advisor is blind to duration questions**, a form a hearing uses
  constantly: *how long did that take, how long was the delay, how long had you known*.

  🚨 **V99's "52% of answerable questions" must not be quoted.** It came from two answerable cases,
  one of them the pathological one, so the figure was one coin flip wide. Over eight answerable cases
  the rate is **123 of 160 — 77%** — and **every one of the 37 misses is a "how long" question**. The
  honest statement is not "it answers about half" but "it answers everything except one question
  form, which it never answers".

  ⚠️ **`docs/decisions/0014` cites the 52% in support of shipping the generative slot off, and that
  supporting figure is wrong.** Corrected here. **The decision itself is not disturbed**, because it
  rests on **V106** — the slot doubles ASR inference while answering — and that measurement is
  untouched. A slot answering 77% while halving the transcript's speed fails the same test as one
  answering 52%; the reason was never the hit rate.

  ⚠️ **The fabrication and prose-decline rates move between runs of an identical design.** Three runs
  of the same case: fabrication 3%, 1%, 3%; prose declines 14%, 11%, 11%; correct declines on the one
  failing unanswerable case 3/20, 8/20, 8/20. **Quote these as single digits, not to a decimal.**

- **V108 — 0.45 costs one false positive in 250 utterances of real, unauthored speech.** Measured
  2026-08-20 with `tools/probe_rag_cues.py`, extended so the negative set is **not written by
  whoever wrote the queries** — 250 transcribed turns from the ASCEND fixture's `reference` column,
  genuine code-switched conversation about family, study and food, none of it related to the invented
  programme notes and none of it authored here.

  **This addresses the specific weakness V95 and `docs/decisions/0014` both named.** Lowering the
  threshold makes false positives the risk that matters, and the five "obviously unrelated" lines
  that chose 0.45 were written by the same session as the queries.

  | | Value |
  |---|---|
  | Utterances scored | **250** |
  | Median score | 0.105 |
  | 95th percentile | 0.259 |
  | Maximum | 0.589 |
  | **False positives at 0.45** | **1 of 250 — 0.4%** |

  | Threshold | False positives on real speech | True cues fired (V95's set) |
  |---|---|---|
  | 0.35 | 4 | 5/5 |
  | 0.40 | 1 | 4/5 |
  | **0.45 (shipped)** | **1** | **4/5** |
  | 0.55 | 1 | 2/5 |
  | 0.65 | **0** | **0/5** |

  **The one false positive is defensible rather than absurd.** *"three to four minutes"*, scoring
  0.589, against an indexed note whose subject is *"Recovery time objective is now fifteen minutes,
  down from four hours"*. A duration phrase matching a duration note is retrieval working on a line
  that happens not to be about the programme — which is what a **0.4%** rate on unrelated
  conversation looks like from the inside.

  **What this settles and what it does not.** It settles that 0.45 does not flood a real meeting: the
  95th percentile of genuine conversation sits at 0.259, well clear of the gate. It does **not**
  settle the positive side — the five paraphrases that produce "4 of 5" are still written here, and a
  hit rate measured against self-authored positives remains the weak half. **The negative half is now
  the strong half, which is the reverse of the position V95 was in.**

- **V109 — Repeated, the speaker-leak metric cannot support the precision it has been quoted at: the
  median spans 0.32 to 0.70 across ten runs.** Measured 2026-08-20 by repeating the 3/10/60-minute
  ladder, which is what **V87** asked for when it concluded that a single run of this metric cannot
  be quoted. Ten runs now exist, all rescored with the median that **V96** installed.

  | Run | Buckets | **Median** | Mean | Buckets over 1.0 |
  |---|---|---|---|---|
  | 08-18, 3 / 10 min | 3 / 10 | 0.4095 / 0.4082 | 0.3871 / 0.3892 | none |
  | 08-19 2121, 3 / 10 min | 3 / 10 | 0.3276 / 0.5582 | 0.3097 / **0.9467** | — / 2 |
  | 08-19 2230, 3 / 10 / 60 min | 3 / 10 / 44 | 0.3202 / 0.3780 / 0.4096 | 0.4055 / 0.3874 / **0.8388** | — / — / 3 |
  | **08-20, 3 / 10 / 60 min** | 3 / 10 / 44 | **0.7045** / 0.4803 / **0.6008** | **2.4065** / 0.4735 / **2.1490** | 1 / — / **8** |

  | | Range | Spread |
  |---|---|---|
  | **Median** | 0.320 – 0.705 | 0.384 |
  | Mean | 0.310 – 2.406 | 2.097 (**5.5x wider**) |

  🚨 **So V87's "~0.39" and V96's "~0.41 by median" are single-run figures and must not be quoted to
  two decimals.** The honest statement is **roughly 0.3 to 0.7**, and the metric as built cannot do
  better. Tonight's hour read 0.6008 against last night's 0.4096 for the same measurement, with 769
  microphone lines against 487.

  ✅ **The qualitative conclusion survives easily and is unaffected.** Anywhere in 0.3-0.7 the leak
  is legible-but-degraded, whole phrases intact, all labelled as the operator. **Headphones remain a
  precondition** (**V70**, **V87**). What changed is the confidence attachable to the number, not the
  direction.

  **The mechanism, now settled by the full set.** Buckets above 1.0 appear at **n=3, n=10 and n=44** —
  both 44-bucket runs, two of four 10-bucket runs, one of four 3-bucket runs. So **bucket count
  raises the probability** of containing one (**V96**'s original claim) while **short reference text
  in a bucket is the cause** (its correction). Both halves were needed and each alone was wrong: a
  3-bucket run scored 6.15, and a 10-bucket run scored clean twice.

  **The next test is named rather than left implied.** A micro-average — total edit distance divided
  by total reference characters across buckets — avoids both the single-string alignment problem
  **V87** rejected and the small-denominator explosion its replacement introduced. The tool records
  only per-bucket ratios, so this needs per-bucket edit counts and reference lengths first. Until
  that exists, quote a range and not a figure.

- **V101 — Gated, the segmentation table can choose again, and it chooses what V66 already chose.**
  Measured 2026-08-20, `tools/measure_segmentation.py` run twice on the same fixture in the same
  session, one variable changed: `--gate`.

  | Strategy | Median segment | Ungated **R37** | Gated **R37** | CER ungated | CER gated |
  |---|---|---|---|---|---|
  | **flush=0.4 (production)** | **3.03 s** | 178/186 · 96% | **60/186 · 32%** | 0.754 | **0.353** |
  | flush=0.8 | 6.76 s | 108/114 · 95% | 43/114 · 38% | 0.316 | 0.317 |
  | flush=1.5 | 15.0 s | 79/82 · 96% | 29/82 · 35% | 0.405 | 0.406 |
  | window=8s | 8.0 s | 102/104 · 98% | **23/104 · 22%** | 0.331 | 0.342 |

  **The saturation V89 reported is an artefact of not gating.** Ungated, the column spans **three
  points** (95-98%) and cannot rank anything — which is what **V89** correctly concluded and wrongly
  attributed to segmentation. Gated it spans **sixteen** (22-38%), because what is left is the
  non-speech each strategy actually hands to the decoder rather than the model's willingness to
  invent from anything.

  **And the choice it now supports is the one already shipped.** `window=8s` wins R37 at 22%, but its
  median segment is **8 s** against production's **3.03 s**, and a speaker waits for a segment to
  close before seeing anything (**V66**, **R9**). Production's `flush=0.4` sits **10 points** behind
  the best on R37 while closing segments **2.6x sooner**. Under **R9** that is not a close call.
  **V66**'s 0.4 s therefore survives, and for the first time for a measured reason rather than
  because the deciding column was flat.

  **A second effect, not predicted, and it corroborates V96.** Gating moved the production row's CER
  **0.754 -> 0.353** while every other row moved by **0.011 or less**. The shortest flush produces the
  most non-speech segments; ungated, their invented text inflates CER through insertions, which is
  exactly the unbounded-insertion pathology **V96** found in the leakage metric. **The gate repairs
  the CER column as a side effect** — and the corollary is sharper: **any CER measured on an ungated
  short-flush strategy in this repository is suspect**, because it is partly counting hallucinations.

  ⚠️ **The gated arm ran in 14 minutes against the ungated arm's 32.** Fewer decodes, as designed.
  Recorded because it is the cheapest confirmation available that the gate was genuinely in the path,
  independent of the log line that says so.

- **V102 — V92's unexplained 239 was run-to-run variation, not the environment: both venvs read
  253/253 on the same night.** Measured 2026-08-20, `tools/probe_nonspeech_real.py` ungated, same
  corpus, same night, one variable changed — the interpreter and its weight cache.

  | Run | Environment | Non-speech producing text |
  |---|---|---|
  | **V84**, 2026-08-18 | `.venv-bakeoff` / `.hf_cache-bakeoff` | 252/253 |
  | **V92**, 2026-08-19 | product venv / product `HF_HOME` | **239/253** |
  | tonight | **product** | **253/253** |
  | tonight | **bake-off** | **253/253** |

  **The two arms agree exactly**, group by group: `control-speech` 10/10, `new-derived` 239/239,
  `new-real` 186/186, `new-synth` 32/32. **So the environment is cleared.** **V92** recorded the gap
  as unexplained and forbade any cross-run subtraction against **V84**'s 252 until it was; that
  restriction is now lifted, because the environments do not differ.

  **What remains is variation between runs of the same thing**, and 239 is the outlier: 252, 253 and
  253 sit at the ceiling while one run read 239. `mlx_whisper` falls back through rising temperatures
  when its own thresholds trip, which is a sufficient mechanism for a swing of this size and has not
  been isolated. **Not attributed further than that** — a plausible mechanism is not a measurement.

  **The stronger statement this licenses:** ungated, the shipped model invents an utterance from
  **essentially every real non-speech segment** — 253 of 253, twice, in two environments. The gate's
  88/253 (**V84**, **V92**) is therefore a reduction from 100%, not from 94.5%.

  ⚠️ **It also partly explains V92's wall-clock mystery.** Each arm took ~14-15 minutes tonight
  against V92's 46 for identical work. V92 recorded 88% of its wall clock as unaccounted; the machine
  was running other things during it and is idle now. **That is an explanation for the discrepancy,
  not a retraction of the caution** — V92's per-input figures remain the quotable ones.

- **V103 — The dual-track cost at conversational pace, on the shipped model: 1.32x, and the last
  figure carrying the removed model is retired.** Measured 2026-08-20 over the same one-hour
  two-track ASCEND fixture as **V67**, `whisper-large-v3-turbo`, lock held, feed paced in real time.
  **V67**'s arm was `Qwen/Qwen3-ASR-0.6B`, removed on **R50**; this replaces it.

  | Arm | n | median | p95 | max |
  |---|---|---|---|---|
  | all lines | 932 | **652 ms** | 1311 | **10368** |
  | solo — no other-track inference in flight | 752 | 648 ms | 769 | 4278 |
  | contended — competing for `NPU_LOCK` | 180 | **856 ms** | 2533 | 10368 |
  | — `Participant`, contended | 87 | 740 ms | 2109 | **10368** |
  | — `Speaker (You)`, contended | 93 | 908 ms | 2923 | 3740 |

  **contended / solo = 1.32x.** 180 of 932 lines (19.3%) were contended, against 16.8% simultaneous
  speech in the fixture.

  **Where that sits among this repo's three figures.** **V56** measured **2.00x** with both tracks
  saturated and called it an upper bound. **V67** reported **1.47x** and then withdrew it: a
  permutation test put the null at **1.20x** with the observed value inside its 90% interval.
  **1.32x here is an independent measurement on a different model, and it lands between the
  withdrawn value and that null** — so the effect is real, and smaller than 1.47x.

  **The pacing objection that damaged V67 does not apply.** 3600 s of audio in 3611 s awake =
  **0.997x**, against V67's 0.920x, and above the 0.888x ceiling a flat `sleep(0.03)` per frame
  imposes. Contention is not under-represented here.

  🚨 **The tail is 10.4 seconds and it lands on `Participant`.** `max 10368 ms` on a contended
  far-party line, against a 652 ms median. **V88** found the whole lock penalty falling on
  `Participant`; this is the same asymmetry at the tail, on the track whose question the product
  exists to deliver in time (**R9**). One line in an hour, and it is the line a person notices.

  **Completeness bounds only, not recall:** 552 lines against 676 reference turns on A (0.82),
  380 against 454 on B (0.84). Segments group turns, so a ratio under 1 mixes merged turns with
  dropped ones. **CER 0.458 (A) and 0.281 (B).**

  **R2's falsification attempt fails to falsify, as it must here:** foreign 5-grams appear at 0.4-0.5%
  across tracks. Separate WAVs and separate `Transcriber` instances leave no acoustic path, so this
  confirms the plumbing and says nothing about **V60**'s mixed-audio cross-talk.

- **V104 — Simplified output is 81% on a current, larger sample, and V90's 88% came from a stage that
  could not produce a new number.** Counted 2026-08-20 with `looks_traditional_chinese` over the
  night's own outputs: **121 lines carrying Chinese — 98 Simplified, 23 Traditional**.

  | Sample | Lines with Chinese | Simplified | Share |
  |---|---|---|---|
  | **V90**, 2026-08-18 | 76 | 67 | **88%** |
  | this run, 2026-08-20 | **121** | 98 | **81%** |

  **The direction is unchanged and the figure moves.** **R10** wants Traditional for the Taiwan
  context, is explicitly subject to **R9**, and this remains a post-processing concern (**R49**)
  rather than a model defect.

  🚨 **Why V90's number was frozen.** The stage that produces it globbed a **hardcoded**
  `fixtures/asr/results/20260817-model-swap/E*.jsonl`, so it recounted the same stored dataset on
  every run and **could only ever reproduce 67/9, whatever had just been measured**. It looked like a
  measurement in the output and was a replay. Fixed 2026-08-20 to score the current run's outputs
  first, with the old directory as a fallback.

  **The general form is worth more than the correction.** A stage whose result cannot change is not a
  measurement, and it is invisible precisely because its output is well-formed and plausible — the
  same shape as **V91**'s fail-open gate, the preconditions that matched their own shell, and the
  guard broken by `grep -c` exiting 1. **Four instances of one pattern in two days: a check or a
  measurement that cannot fail reads exactly like one that is passing.**

- **V105 — Speaker separation runs on audio the product recorded, and its speaker count is not stable
  across capture paths at ten minutes.** Measured 2026-08-20 with `tools/run_overnight_extra.sh` over
  the four files the retention stage wrote (**V98**) — the first time this feature has met anything but
  a fixture clip since it was built on 2026-08-17. No Hugging Face token, offline, via the pinned venv
  (**V93**).

  | Session | Track | Turns | Speakers | Speech detected | Shortest turn |
  |---|---|---|---|---|---|
  | 3 min | tap (`system`) | 41 | **2** | 59 s | 0.24 s |
  | 3 min | microphone | 41 | **2** | 55 s | 0.19 s |
  | 10 min | tap (`system`) | **164** | **3** | 253 s | **0.02 s** |
  | 10 min | microphone | **142** | **2** | 228 s | **0.02 s** |

  **The two tracks of one session are recordings of the same played audio** — the tap takes it
  digitally, the microphone takes it through the air. They should therefore agree about how many people
  are speaking.

  ✅ **At three minutes they agree exactly:** 41 turns each, 2 clusters each, speech within 4 s.

  🚨 **At ten minutes they do not: three clusters against two, and 164 turns against 142 (15%).** At
  most one of those is right, and **speaker count is not a detail here — it is the output**, for a
  feature whose entire purpose is attributing lines to people. Nothing establishes which track is
  wrong; what is established is that the answer depends on which microphone heard it.

  🚨 **Both ten-minute runs emit a 0.02 s turn.** No speech is twenty milliseconds long, so these are
  degenerate turns. The summary line that reports this was written to flag *"a floor of exactly 0"*,
  and 0.02 s slips under it — **my own check, with the threshold set to the wrong side of the
  problem**, which is the fifth instance in three days of a check that cannot fail for the reason the
  thing actually breaks.

  **What this does and does not close.** It closes *"has speaker separation ever run on real recorded
  audio"* — yes, and it produces plausible output in seconds per minute of audio. It does **not**
  establish accuracy: there is no ground-truth speaker labelling for these recordings, so nothing here
  says whether 2 or 3 is correct, or which lines were attributed rightly. **Attribution accuracy
  remains unmeasured**, and the operator's real meeting is where a wrong count first has a cost.

- **V106 — The generative advisor doubles ASR inference time while it is answering.** Measured
  2026-08-20 against the operator's stated criterion — *significant improvement, and what it costs in
  resources*. `tools/probe_nonspeech_real.py` re-run with `mlx_lm.server` **generating continuously**
  rather than idling, because an idle server holds its weights but not the accelerator, and only the
  answering state exists during a meeting.

  **A paired comparison, not two medians.** The control is this night's own `baseline_product` arm —
  the same inputs in the same order — so each input is compared against itself:

  | | Median per input |
  |---|---|
  | Control, no LLM resident | **649 ms** |
  | Under continuous generation | **1308 ms** |
  | **Per-input ratio** | **median 2.01x** (min 0.44x, max 4.47x) |

  Worst cases are the long segments: a 6.0 s input went 6005 -> 26830 ms (**4.5x**). Throughput fell
  from ~33 inputs/minute to ~2-13.

  **Why 23 paired inputs is enough here.** The claim is directional — *does the generative slot tax the
  transcription path* — and a paired design with a median of 2.01x answers it. Running the remaining
  444 inputs would have cost about four hours of accelerator time to add decimal places to a number
  whose sign is not in doubt. **Stopped deliberately on that reasoning**, and the sample size is stated
  rather than hidden.

  **What this settles against the criterion.** The generative slot answers **52%** of answerable
  questions (**V99**), fabricates on 3% of unanswerable ones, puts noise on screen for 14% — and while
  it does that, it **halves the speed of the transcript**, which is the thing **R9** is a promise about.
  It shares one Metal accelerator with Whisper, and `NPU_LOCK` serialises callers *inside* a process
  and does nothing across processes. **This is the number the "is the generative advisor worth having"
  decision turns on, and it was the last one missing.**

  ⚠️ **Not measured: the same question with the LLM answering at meeting frequency.** This drove it
  flat out; a real meeting calls it once per Participant utterance, so the duty cycle is lower and the
  average penalty is smaller than 2.01x. **The peak is not** — a generation overlapping a long segment
  is exactly the 4.5x case, and it lands on the tail **V103** already found on `Participant`.

- **V74 — Whisper's `initial_prompt` recovers rare proper nouns better than the mechanism it
  replaces, and without the failure that made the old one dangerous.** Measured 2026-08-17 with
  `tools/measure_biasing.py`: five synthesized sentences carrying Taiwanese place names, an
  organisation and a person's name; ten prompt terms, five decoys present in no clip.

  | Arm | Rare terms recovered | CER | **R38** language flips | Decoys inserted |
  |---|---|---|---|---|
  | no prompt | 4 / 11 | 0.0358 | 0 / 5 | — |
  | **vocabulary as a bare list** | **10 / 11** | **0.0062** | **0 / 5** | **none** |
  | the same terms in a sentence | 10 / 11 | 0.0062 | 0 / 5 | none |
  | list plus five decoys | 10 / 11 | 0.0062 | 0 / 5 | **none** |

  **The capability transfers, and the danger does not.** **V59** measured the previous backend's
  `context=` taking rare terms from 1 of 11 to 9 of 11 **while flipping an English sentence into
  mixed Chinese**, breaching **R38** — which is why biasing was confined to the re-listening pass.
  `initial_prompt` reaches 10 of 11 with **zero** flips, and **improves** CER by 5.8x rather than
  costing 0.04 as `context=` did. On this fixture it is better on every axis.

  **Two hypotheses of my own, both refuted, recorded because they would otherwise be proposed
  again:**

  - **Prompt *shape* does not matter.** The list and sentence arms are identical to four decimals.
    This was expected to matter because `initial_prompt` is prepended text the decoder continues
    from, and a bare comma-separated list had been observed stripping punctuation from Chinese
    output during the swap. That observation does **not** reproduce here — but the clips here are
    English, so "shape never matters" is not established either; what is established is that it
    does not matter on this material.
  - **Decoys are not copied out.** A vocabulary harvested from a whole meeting is mostly
    irrelevant to any one segment, and the fear was that the decoder would emit prompt terms that
    were never spoken. Five decoys, five clips, four arms: **zero insertions**.

  ⚠️ **Synthesized speech (`say`), for the reason V59 gives** — the effect needs rare proper nouns
  no available corpus contains. The mechanism and its failure modes are verified; the magnitudes
  are not product numbers. These are **not V59's sentences**, which lived in a scratch directory
  that no longer exists, so the counts are not comparable with **V59**'s — only the directions are.

- **V59 — Qwen's `context=` prompt recovers rare proper nouns dramatically and can flip an
  utterance into the wrong language.**

  ⚠️ **The argument this measures no longer exists (2026-08-17, `docs/decisions/0012`).** The
  package was removed with the model, and Whisper's nearest equivalent — `initial_prompt` — is a
  *different mechanism*: `context=` conditioned the decoder on a vocabulary, while `initial_prompt`
  is prepended text the decoder continues from, so it carries **style as well as vocabulary** and
  can be copied out verbatim. **The numbers below do not transfer and must not be quoted for the
  shipping product.** What does transfer is the shape of the finding — biasing is a strong lever
  with a language-stability failure mode — which is why the re-listening pass still uses it and the
  live path still does not. `tools/measure_biasing.py` re-measures it on the new mechanism, with an
  arm for prompt shape that the old mechanism could not have had.

  Measured 2026-08-11 (**V40**, and measurement item 4 of the
  ASR item, which had never been run). The port exposes it as `mlx_qwen3_asr.transcribe(...,
  context=...)`, so the capability **V40** read from the model card is real in this build.

  Two probes, because the first measured the fixture rather than the feature:

  **On conversational ASCEND clips: no effect.** 25 mixed clips, vocabulary of 20 terms drawn from
  the references plus 20 decoys — CER 0.0785 against 0.0783, a 0.02 pp difference. Biasing helps
  where the model is uncertain, and a corpus of casual speech contains nothing it is uncertain
  about. **That result says nothing about the feature.**

  **On sentences built around rare proper nouns: both effects at once.** Five synthesized sentences
  carrying Taiwanese place names, company names and a legislator's name; vocabulary of 11 present
  terms plus 5 decoys:

  | | without `context` | with `context` |
  |---|---|---|
  | Rare terms recovered | **1 of 11** | **9 of 11** |
  | CER | 0.1086 | **0.1506** |

  The aggregate hides what happened, and the per-sentence output shows it:

  - `Kaoshan Chongtun ... anti-black coating` becomes `Kaohsiung Chungtan ... Vantablack coating`.
    This is the capability working, and it is the case a hearing needs — company names, place
    names, the name of the person asking the question.
  - `Legislator Wang Juchen questioned the Taiyuan gishen procurement` becomes
    `立法者 Wan-Ju Chen 质问 Taoyuan 派出所 procurement。` — an English sentence rendered in mixed
    Chinese, with one place name hallucinated into an unrelated word. **That is not an accuracy
    regression, it breaches R38**, which forbids anything in the pipeline translating or
    normalising content.
  - A vocabulary term also migrated to the wrong slot: `Hsueh`, which belonged to a name the model
    still got wrong, appeared inside a different phrase.

  **So it is not a yes/no.** The lever exists and it is strong, but enabling it unconditionally
  trades a requirement for accuracy. Any use of it needs the vocabulary scoped to terms plausibly
  in *this* meeting rather than a whole glossary, and needs the language-stability failure measured
  before it ships.

  ⚠️ Synthesized speech (`say`), chosen because the effect needed rare terms that no available
  corpus contains. It verifies the mechanism and its failure mode; the magnitudes are not product
  numbers, and TTS pronunciation of Chinese proper nouns may aggravate the language flip.

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
- **V37 — `is_local` already exists and fails open on two paths.** `app.py:59-71` derives it from
  the Host header and currently uses it only to skip the PIN gate. Local is granted when the host
  contains `localhost` or `127.0.0.1`, when the host is **empty** (`or not host`), and when any
  exception escapes the `try` (`except: is_local = True`). Re-read from source on 2026-08-10; both
  non-localhost branches silently grant local privileges.

## The advisor seam already exists, and so does its gate

- **V22 — The cosine threshold *is* the intent judgement.** `local_advisor.py` computes a
  similarity score and returns a hint only when `best_score >= THRESHOLD` (0.65), plus a
  `< 10` character filter and a repeat-suppression check on `last_matched_idx`. So the current
  design already sends every Participant utterance to RAG unconditionally and lets the score
  decide. **No separate intent model exists or is needed** for the RAG path.
  **Acted on 2026-08-13.** The threshold now lives in `advisors.py` as `SERVE_THRESHOLD` —
  one number, shared by the backend that serves on it and the router that gates on it — and
  `analyze_dialogue` returns the score rather than discarding it below the bar. Whether either
  band edge should be adjustable, and from where, is closed in `docs/decisions/0010`.
- **V23 — A generative model has no equivalent threshold.** RAG returns `None` below 0.65; an
  LLM produces output for any input, because that is what generative models do. Any gate on
  the LLM path has to be built.
- **V24 — There is one advice slot, so two backends overwrite each other.**
  `dialogue_buffer.set_advice()` assigns a single `self.advice` string and `app.py` renders one
  value. Local RAG returns in milliseconds, a remote LLM in seconds — so an LLM reply would
  reliably replace an already-displayed RAG hint a beat later. Worse than showing nothing: the
  speaker reads a safe pre-written answer, and it is swapped for generated text mid-glance.
  **Fixed 2026-08-13.** The buffer keeps one slot per kind (`advice_slots`), the renderer shows
  all of them as separately styled cards, and the merge policy is that they do not merge.
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
  **Made deliberate 2026-08-13.** The remote call moved to `AdvisorPipeline`'s own thread behind
  a one-slot mailbox, so the poll loop no longer stalls and the coalescing is stated policy with
  a test rather than a side effect of being synchronous.
- **V34 — The RAG path fails silently, end to end.** `local_advisor.py:30-32` logs a warning and
  **returns** when the index is missing — no exception. `self.model` and
  `self.knowledge_embeddings` stay `None`, so the guard at `:53-54` returns `None` on every
  subsequent call, forever. `_local_rag_worker_loop` does nothing with `None`, and `app.py`
  surfaces no advisor state at all — grep finds only the `.advisor-box` CSS rule and the render
  line. The operator sees an armed toggle and a defence that will never fire. Two variants
  present identically: a missing index, and a **stale** one built before today's material was
  added.
  **Surfaced 2026-08-13.** `analyze_dialogue` returns `ok=False` with the reason, the pipeline
  carries it into `status()`, and the running view renders it — so "the index never loaded" and
  "nothing matched" no longer look the same. The **stale** variant is still not detected.
- **V35 — The liveness signal already exists, but only reaches the log.**
  `local_advisor.py:84` computes and logs the similarity score **unconditionally for every
  utterance**, including below-threshold and repeat-suppressed cases. Surfacing the most recent
  score is what distinguishes "working, nothing matched" from "dead" (**R36**).
  **Surfaced 2026-08-13** on the running view, beside an equivalent state line for the
  generative slot, which has no score of its own.
- **V36 — The pickle currently prevents a query/build model mismatch; Qdrant would not.**
  `build_index.py` writes `model_name` into the bundle and `local_advisor.py:40` loads exactly
  that model, so querying with a different model is impossible today. Qdrant validates vector
  dimensionality but **not** model provenance, so the migration **introduces** this failure mode
  rather than inheriting it — and it too returns confident nonsense rather than an error.
  **Guarded 2026-08-13, and the failure did not land.** `knowledge_store.py` writes the
  embedding model's name into every point's payload and `local_advisor` loads *that* model
  rather than the one `EMBEDDING_MODEL` names — so the mismatch stays impossible rather than
  merely detectable. A disagreement between the collection and the setting is reported on the
  pre-flight panel, where the operator decides whether to rebuild. The distance metric is pinned
  to `COSINE` at creation and verified at every read, closing the other silent trap in the same
  migration. Both are tested against a real embedded Qdrant, not a stub.

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

## An unmerged branch already contradicts several constraints above

- **V49 — `origin/feat/streaming-transcriber` applies cleanly and disagrees with `main`.** Measured
  2026-08-10: the branch tip is `467a442` (10 commits, 2026-07-02), it forks from `201eeea`, it is
  **not** an ancestor of `main`, and `git diff 201eeea..main -- src/` is **empty** — so `main`'s source
  is byte-identical to the fork point and the branch still applies without conflict.

  What it changes: Silero VAD sliding-window streaming replacing the webrtcvad fragment pipeline;
  `whisper-large-v3-turbo` as the default with a bilingual zh/en `initial_prompt`; a bounded ring
  buffer replacing the unbounded `inference_queue`; per-track lossless WAV capture at **16 kHz** into
  `recordings/<session_id>/` via a writer thread; `src/retranscribe.py` for offline re-transcription
  and per-track merge; `src/summarizer.py` for a local `mlx-lm` summary; and a hallucination filter
  changed from substring to whole-utterance matching.

  **Run in an isolated worktree on 2026-08-10**, which corrected four of the claims above — all four
  had been read from its commit messages rather than executed:

  - **Its suite is 60 tests and all 60 pass**, not the "roughly 29" previously recorded (`main` has 8).
    A branch that passes its own suite is a source of code, not only of ideas.
  - **It ships a second live ASR model that the commit messages do not advertise.**
    `resolve_default_model()` auto-selects `whisper-medium-mlx` on fanless Macs by `system_profiler`
    marketing name, keeps `large-v3-turbo` elsewhere, and its offline path hardcodes `large-v3-turbo`
    regardless — so the default is conditional on chassis and code path, not the single value recorded
    before.
  - **It reads five environment keys, not three**: `WHISPER_MODEL`, `WHISPER_LANGUAGE`,
    `TRANSCRIBE_MODE`, `SUMMARY_MODEL`, `AUTO_SUMMARIZE_ON_EXIT`. Only the first three reached its
    `.env.example`.
  - **It does not fix capture-before-authentication and worsens it.** The auto-start in `app.py` is
    untouched (**V18**), so loading the URL now also opens two WAV files on disk. **R25** is breached
    further than on `main`.

  Two measurements it reports remain *reported only*, and neither becomes a constraint here: **≈0.3%
  of decode for Silero VAD** — which its own notes attach to a *rejected* incremental-VAD
  optimisation, not to the VAD as shipped — and **`NPU_LOCK` kept deliberately** for want of any
  parallelism gain on a single GPU. Its fanless model comparison was measured on short, clean TTS
  clips by its author's own admission.

  Its own notes say why it never merged: **live audio run pending**, throughput under thermal
  throttling untuned. Running its suite does not change that: no claim about false triggers, code
  switching or sustained throughput can be settled without audio fixtures. Disposition per piece is
  in `docs/decisions/0006`.

## The live transcript path is already lossy

- **V48 — Verified from `transcriber.py` on 2026-08-10.** Before any line reaches
  `DialogueBuffer`, the pipeline discards (a) frames `webrtcvad` marks non-speech, (b) segments
  shorter than 0.3 s, (c) empty / single-character ASR output, and (d) strings on the
  anti-hallucination blacklist. None of that material appears in `history/Meeting_*.md`. So a
  session with retention off has **no** recoverable record of what the filters dropped — which is
  why **R45** exists, and why **R3** was rewritten on 2026-08-12: the transcript is not complete, it
  was never going to be, and a requirement claiming otherwise made this measurement look like a bug
  rather than the design.

---

# ✅ Decided and closed

Recorded so they are not relitigated. Reopening any of these means revisiting the stance or
requirement it follows from.

| Rejected | Why | Follows from |
|---|---|---|
| Per-app audio capture via `bundleIDs` | Cannot isolate a meeting running in a browser tab, and a bundle-ID allowlist is unmaintainable. Also costs the 14.2 → 26.0 OS floor. | R1, R5, V8 |
| **ScreenCaptureKit as the capture mechanism** — **rejected 2026-08-12 by the operator** | **There is no audio-only SCK stream.** `SCStream`'s sole initializer requires a non-optional `SCContentFilter`, so audio is obtained by constructing a *screen* capture and enabling `capturesAudio`, and enumerating capturable content is itself what prompts for consent. A product whose proposition is 100% offline with zero telemetry cannot open by asking to record the operator's screen; *"we only take the audio"* is not a rebuttal the operator has to accept on the product's behalf. It also raises the OS floor 14.2 → 15.0, undoing what the row above deliberately bought, and replaces a helper already measured working (**V7**, **V9**, **V10**) with one that is not. **Closed, not deferred** — the one confirming run (does the runtime enforce consent for a stream that never reads a video frame?) was dropped, because a *yes* changes nothing and a *no* still leaves the floor and the rewrite. | R1, R5, R6, R7, R15, V6, V7, V9, V10, V11 |
| Browser-side capture (`getUserMedia`, as Zoom/Meet web do) | Impossible, not merely awkward — the remote device cannot reach the API, and no browser reliably yields system audio on macOS. | V13, V14 |
| ASR-side speaker diarization (pyannote / sherpa-onnx / embeddings) | Live transcription never needs speaker identity; the RAG worker triggers on `role == "Participant"` only. Deleting this removes the roadmap's highest-risk item rather than deferring it. | R12, R13 |
| OpenCC in the live path | Simplified/Traditional ambiguities need surrounding context, which only the post-processing pass has. | R9, R10, V5 |
| Persisting *enumerable* selections (a `.aegis_settings.json` for the microphone) | Meet and Zoom web persist nothing: default plus override is sufficient, and storing a device reference only creates a stale name-or-index problem. Typed values are a different case — see R32/R33. | R26, R33 |
| Archiving audio *in order to* diarize | The cleanup pass works from text. Audio retention stands on corroboration instead. | R14, R16 |
| Archiving at 48 kHz to match what the hardware produces | **Reversed 2026-08-11** — this row previously rejected 16 kHz. Sample rate buys the transcriber nothing (**V51**, **V58**: cost is set by Whisper's fixed 30 s window, not the input), keeping both rates needs a second resample path that was never built and cost 3426 ms against 660 ms when exercised (**V56**), and the disk is 2.1 GB against 690 MB. What it gives up is acoustic detail for non-ASR uses — see `docs/decisions/0001`. | R3, R16, R45, V7, V51, V56, V58 |
| Deleting `.env` outright | The cache directory must stay user-choosable; large weights may not belong on the internal drive. `.env` survives as a machine-written form snapshot. | R18, R19, R32 |
| A separate local intent model to gate the LLM | The RAG score is already an intent judgement and costs microseconds; a second model would contend for the NPU that `201eeea` exists to unblock. | V22, V23 |
| RAG backends other than Qdrant | Retrieval-as-a-service has no standard interface — Qdrant, Weaviate, Pinecone and Chroma each have their own API. One vendor beats an abstraction over four. | R28, R31 |
| Gemma 4 in the live ASR path | Audio is silently dropped on the Python MLX path this project runs on, BF16 needs ~24 GB and quantization degrades it, and no WER was ever published. Its diarization is attractive but belongs to the offline cleanup pass, not the live path. | R11, V38 |
| Parakeet TDT v3 | Fastest open model measured, and it does not support Chinese. | R8, V43 |
| Choosing the ASR model from published benchmarks | Every leaderboard measures word error on speech; none measures whether music becomes an utterance, which is the failure this product cannot absorb. | R11, R37, V41 |
| The LLM system prompt as an editable settings field | It carries the instruction that permits returning nothing (**V23**), so an edit that removes that clause converts the advisor into a flooder — a safety boundary, not a preference. **R31** also caps per-backend configuration at a host and a credential. Domain vocabulary belongs in the knowledge base instead. | R17, R31, V23 |
| Reset deleting weights or recordings as well as `.env` | Weights are reproducible and recordings are not, so they must not share a button. Deletion is the file owner's call (**R4**), and both directories are operator-supplied strings — a recursive delete against a typed path is unacceptable. Reset lists what it orphans instead. | R4, R22, R47, V47 |
| Relying on a context-overflow error code | Ollama truncates silently and does not forward `num_ctx`; vLLM errors where the spec says truncate. Own the bound locally instead. | V26, V32 |
| macOS Keychain for credentials | Plaintext `.env` plus UI masking is consistent with a product that already stores full meeting transcripts in plaintext under `history/` — the credential is not the weakest link, and a platform binding buys little. Masking still earns its place against shoulder-surfing and screen sharing. | R32 |
| Three-state sentinel handling for masked credential fields | Unnecessary once the settings form renders **only locally** (**R34**): the field always carries the real value, so writing it back is idempotent. There is no way to save a row of asterisks over a real key. | R32, R34 |
| ASR model choice as a pre-flight control | It would grey out Start for minutes (**V33**), and once the default model is multilingual there is no per-meeting reason to switch — it detects language per VAD segment (**V4**). It belongs in the persisted layer. | R11, R24, V4, V33 |
| Splitting `MULTILINGUAL_MODE` into two settings | It can be **deleted** instead: `turbo` is multilingual unconditionally, and the embedding-model choice becomes a `build_index.py` argument recorded in the Qdrant collection. | V2, V3, V4 |
