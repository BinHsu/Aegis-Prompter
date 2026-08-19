# Trial protocol — does `NPU_LOCK` still have to exist?

**Run 2026-08-11. Verdict: keep the lock — see V57.** No crash, no speed gain (0%), content
within baseline variability, no latency drift over the hour. The crash the invariant was written
for does not reproduce on Python 3.12 / `mlx` 0.32; the lock is kept because it costs nothing
measurable, which is a different reason and is now recorded as such in `AGENTS.md`.

Left undone deliberately: the run used a saturating feed, so it does **not** give the realistic
turn-taking cost — that needs `--realtime`, one hour per arm. A second run on
`Qwen/Qwen3-ASR-0.6B` follows, to get the product's own numbers and to exercise the new backend
against 1130 turns.

The protocol below is kept as written, because the decision rule it fixed in advance is what makes
the verdict above worth anything.

## The question

`AGENTS.md` carries this as an invariant: *"Serialize all NPU access. Concurrent Metal calls from
the two transcriber threads crash the process."* It was written from an observed crash, on an
older toolchain — the product ran Python 3.9 with `mlx` 0.29 until 2026-08-11 and the observation
predates even that. The runtime is now Python 3.12 / `mlx` 0.32.0 (**V53**), so the invariant is
due for re-measurement rather than re-assertion.

It matters because of **V56**: two tracks serializing on that lock cost exactly **2.00x** per call,
and every single-track latency in this repository doubles once the process tap supplies a second
source.

**But the lock may not be what costs the 2x.** There is one GPU. If a single inference already
saturates it, removing the lock moves the queue from a mutex to the Metal scheduler and buys
nothing. The trial is worth running because the opposite is plausible for a small model — Qwen
0.6B returns in 235 ms on short audio, which may leave the device idle in parts.

## The failure mode this protocol is built around

**A crash is the good outcome.** It is loud, it is attributable, and it settles the question in one
run.

The outcome to design against is **silent corruption**: concurrent Metal calls that do not crash
but return subtly wrong results. Nothing in the pipeline would notice — the transcript would simply
be worse, on a machine transcribing a hearing, in a way no test currently checks. So:

> **Every unlocked run is compared transcript-for-transcript against a locked baseline on the same
> audio. A difference is treated as corruption, not as noise, unless the locked baseline is itself
> shown to differ run to run (V54 says it can — so the baseline must be run twice first).**

That ordering is deliberate. Establish the locked run's own variability *before* attributing any
unlocked difference to concurrency.

## Decision rule — fixed now, before any data exists

Written in advance so a desirable result cannot be talked into existence afterwards.

| Observation | Verdict |
|---|---|
| Any crash, abort, or Metal error in any trial | **Invariant stands.** Stop. Record the signature. |
| No crash, but unlocked transcripts differ beyond the locked run's own variability | **Invariant stands** — silent corruption is worse than the 2x. |
| No crash, transcripts within baseline variability, wall clock improves **< 20%** | **Keep the lock.** It costs nothing that matters and it protects. |
| No crash, transcripts within variability, wall clock improves **>= 20%** | **Candidate only.** Requires a longer soak and a second machine before `transcriber.py` is touched. |

The lock is **not** removed from `src/transcriber.py` in this trial under any outcome.

## Method

**Blast radius.** Everything runs in `.venv-bakeoff` against `.hf_cache-bakeoff`. The harness
monkeypatches the lock at runtime inside a subprocess; product source is not edited.

**Every trial runs in its own subprocess.** A crash is a process abort, not a Python exception — if
the harness shares the process it dies with the trial and takes the evidence with it. The parent
records the exit code and signal. Trial output is flushed per line, because redirected stdout is
block-buffered and a crash loses whatever is still in the buffer (learned while measuring **V52**).

**Two levels, because they answer different questions:**

1. **Primitive** — two threads calling `mlx_whisper.transcribe` directly with no lock. Tests Metal,
   not the product.
2. **Pipeline** — two `Transcriber` instances with `NPU_LOCK` monkeypatched to a no-op, fed through
   `feed_wav` with `start(open_input_stream=False)`. Tests what the product would actually do.

**Arms.** For each level: `locked` (baseline, run twice) and `unlocked`. Same audio, same order.

## The audio

**One hour, two tracks, reconstructed from a real conversation.** Build from `CAiRE/ASCEND` test
(already cached), using its `session_id` and `original_speaker_id` to split one session's
utterances into two tracks by speaker, with silence on the other track while each speaker talks.

Why that shape rather than the same file twice:

- **V56 measured the worst case and should be read as an upper bound.** It fed identical audio to
  both tracks as fast as possible, so both were always mid-inference. A real hearing has one person
  talking at a time; the other track is silent and the VAD drops it, so much of the time only one
  inference is in flight. The realistic contention number is not yet known.
- Turn-taking audio measures that, and the saturating variant is still available for the worst case.

Concatenate to ~60 minutes. Deterministic from a recorded seed, written under
`fixtures/asr/real/` (gitignored, rebuildable, `rm -rf` to dispose).

**Why an hour.** A crash that happens once in several hundred calls will not show in a 30-segment
run. At roughly 5 s per utterance an hour gives ~700 inferences per track — enough for a rare
fault to appear, and enough to see thermal behaviour over a sustained load, which
`FORMAL_MEASURE.md` also asks for and no run so far has covered.

## What to record

- Exit code and signal per trial; the crash signature verbatim if there is one
- Per-call latency: median / p95 / max, per track, per arm
- Wall clock for the whole hour, per arm
- `mlx.core.get_peak_memory()` per arm — **not** RSS, which under-reported by 6.5 GB (**V55**)
- Transcript diff, unlocked vs locked baseline, as CER against the baseline text
- Thermal or throttling notes if the platform exposes them
- Toolchain block (**V53**) and fixture digests, as every other run in this repository carries

## Tools needed (to build tomorrow, before running)

1. `tools/build_conversation_fixture.py` — ASCEND session -> two one-hour track WAVs plus a
   `turns.tsv` recording who speaks when and the reference text per turn.
2. `tools/npu_lock_trial.py` — runs the four trials as subprocesses, applies the monkeypatch,
   captures exit codes, latencies, MLX peak memory and transcripts, and emits one report under
   `fixtures/asr/results/`.

Neither exists yet. Build them first and smoke-test each on a two-minute clip before committing an
hour of GPU time.

## Status 2026-08-11 — built and smoke-tested, **not ready to run**

Both tools exist and were smoke-tested on a 3-minute fixture rather than an hour, which is what
the protocol asks for and what saved the GPU time. The smoke test found three defects in the
harness and one that is still open.

**Fixed:**

1. The no-op lock implemented only the context manager. `Transcriber.stop()` calls
   `NPU_LOCK.acquire(timeout=...)`, so the unlocked arm raised there — and the parent scored it as
   *"concurrent Metal crashed"*. **That is the mirror of the corruption risk: a false confirmation
   of the invariant, from a bug in the harness, with a conclusion that matches expectation and is
   therefore harder to doubt.** The parent now separates a Python traceback in its own code from a
   runtime abort and reports `NO RESULT` for the former.
2. Content was compared line-by-line, which misaligns everything after the first split or merge.
   Now compared as one concatenated transcript per role.

**Also fixed (2026-08-11, after the entry above was written):**

3. The comparator reported CER **0.881** between two identical locked arms where a direct
   whole-transcript check gave **0.013**. Cause: the concatenation fix had not actually landed in
   the file when that smoke test ran, so it was still comparing line by line. Re-verified with the
   fix in place: Participant **0.000**, Speaker **0.027**, combined **0.013** — the comparator and
   the direct measurement now agree.

   Worth keeping in view rather than deleting: a text edit that silently fails to match leaves a
   tool that looks fixed and is not, and the number it produced was wrong in the direction that
   would have condemned concurrency. Assert that a replacement applied.

**Ready to run.** No known blocker remains.

**What the smoke test did show, and what it does not settle:** the unlocked arm ran to completion
without crashing on Python 3.12 / `mlx` 0.32, and was **2% slower**, not faster, with higher peak
MLX memory (2329 MB against 2088 MB). Three minutes is not the soak, and the content check was
broken, so this is a hint about where the answer lies rather than the answer. If it holds at an
hour, the decision rule already says: **keep the lock** — no crash but no gain either.

## Running it unattended

The run needs no intervention once started. Two machine settings do matter:

- **Locking the screen is fine.** It suspends nothing; the GPU keeps working.
- **Sleep is not.** Idle sleep, or closing the lid on battery, suspends the process mid-run and
  leaves a partial trial that looks like a stall. Wrap the command in `caffeinate -i` (or
  `caffeinate -is` if the lid will be closed) so idle sleep is blocked for the duration.
- **Stay on mains power.** On battery macOS throttles more aggressively, which would land directly
  on the thing this run is measuring — whether latency degrades over an hour. A throttled battery
  run would produce a drift curve that says more about the power source than about the code.
- **Nothing else on the GPU.** A Streamlit instance left running contaminates every number.

    caffeinate -i env PYTHONPATH="$PWD" .venv-bakeoff/bin/python tools/npu_lock_trial.py

## Prerequisite check before starting

- `.venv-bakeoff` and `.hf_cache-bakeoff` intact (`rm -rf` them and this all has to be refetched)
- Nothing else using the GPU — a Streamlit instance left running would contaminate every number
- Disk headroom for a one-hour stereo-equivalent fixture set (~110 MB at 16 kHz mono per track)
