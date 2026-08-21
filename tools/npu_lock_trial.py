#!/usr/bin/env python3
"""Trial: does `NPU_LOCK` still have to exist? Protocol in `fixtures/asr/NPU_LOCK_TRIAL.md`.

Runs each arm in its **own subprocess**, because the failure being tested for is a process abort
rather than a Python exception -- a harness sharing the process dies with the trial and takes the
evidence with it. Child output is JSONL, flushed per line, so a crash still leaves everything up to
the moment it happened (redirected stdout is block-buffered; that cost a wrong diagnosis while
measuring V52).

Arms, in this order:

    locked-1, locked-2   baseline, run twice — decoding is not reproducible run to run (V54), so
                         the baseline's own variability must be known before any unlocked
                         difference can be attributed to concurrency
    unlocked-1           NPU_LOCK monkeypatched to a no-op, in the child only

**`src/transcriber.py` is never edited.** A positive result buys a candidate for a separate
change, not the change.

What is reported, and why each matters:

  crash        exit code and signal — the good outcome, loud and attributable
  content      CER per turn against `turns.tsv`; a difference beyond baseline variability is
               treated as silent corruption, which is worse than the 2x this trial exists to avoid
  drift        per-call latency by decile of the run — "it gets slower after an hour" is a finding
               worth catching before a hearing does it for us
  completeness turns that produced no line at all (R3)
  memory       mlx.core.get_peak_memory(), not RSS, which under-reported by 6.5 GB (V55)
"""

import argparse
import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

CONV_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr", "conversation")
TURNS = os.path.join(CONV_ROOT, "turns.tsv")


# ===== child: run one arm =====

def emit(record):
    sys.stdout.write(json.dumps(record, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def run_child(args):
    import logging
    import re
    import threading

    import bootstrap
    if args.hf_home:
        os.environ["HF_HOME"] = os.path.abspath(os.path.expanduser(args.hf_home))
    else:
        bootstrap.apply_environment(bootstrap.read_settings())
    bootstrap.enforce_offline()

    import transcriber as tmod
    from dialogue_buffer import DialogueBuffer

    if args.unlocked:
        class _NoLock:
            """Must mirror threading.Lock's full surface, not just the context manager.
            `Transcriber.stop()` calls `NPU_LOCK.acquire(timeout=...)`, and a partial stand-in
            raises there — which the parent would have scored as 'concurrent Metal crashed',
            confirming the invariant from a bug in the harness."""

            def acquire(self, blocking=True, timeout=-1):
                return True

            def release(self):
                return None

            def locked(self):
                return False

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        tmod.NPU_LOCK = _NoLock()
        emit({"event": "lock", "state": "disabled"})
    else:
        emit({"event": "lock", "state": "enabled"})

    started = time.time()
    pattern = re.compile(r"\[(?P<role>[^\]]+)\] Transcribed in\s+(?P<ms>[\d.]+)\s*ms:\s*(?P<text>.*)")

    class Sink(logging.Handler):
        def __init__(self):
            super().__init__(level=logging.INFO)
            self.lock_ = threading.Lock()

        def emit(self, record):
            match = pattern.search(record.getMessage())
            if not match:
                return
            with self.lock_:
                emit({"event": "line", "t": round(time.time() - started, 3),
                      "role": match.group("role"), "ms": float(match.group("ms")),
                      "text": match.group("text")})

    # Warnings must reach stderr, and a wasted run is what it took to notice they did not.
    # Attaching only `Sink` gave the "Transcriber" logger a handler, which stops
    # `logging.lastResort` from firing, while root had no handler because nothing calls
    # basicConfig -- so every `logger.warning` in the pipeline was offered to a Sink that ignores
    # anything but "Transcribed in" lines, and then dropped. `Audio queue full` is the single line
    # that explains a feed falling behind, and a 0-byte stderr read as "no problems" when it meant
    # "no reporting".
    #
    # The level goes on the **handler**, not on basicConfig. A logger's level only gates records
    # originating at that logger; once Transcriber (INFO) emits, propagation hands the record
    # straight to root's handlers and never consults root's level. basicConfig(level=WARNING) was
    # tried first and flooded stderr with every INFO line -- verified, not assumed.
    _warnings = logging.StreamHandler(sys.stderr)
    _warnings.setLevel(logging.WARNING)
    _warnings.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logging.getLogger().addHandler(_warnings)
    logging.getLogger("Transcriber").addHandler(Sink())
    logging.getLogger("Transcriber").setLevel(logging.INFO)

    buffer = DialogueBuffer(max_history=15)
    tracks = [("Speaker (You)", os.path.join(CONV_ROOT, "track_A.wav")),
              ("Participant", os.path.join(CONV_ROOT, "track_B.wav"))]
    instances = []
    for role, wav in tracks:
        instances.append((tmod.Transcriber(role=role, device_idx=None, buffer_instance=buffer,
                                           model_path=args.model), wav))
    emit({"event": "warm", "t": round(time.time() - started, 3)})

    for instance, _ in instances:
        instance.start(open_input_stream=False)
    threads = []
    for instance, wav in instances:
        thread = threading.Thread(target=instance.feed_wav, args=(wav,),
                                  kwargs={"realtime": args.realtime}, daemon=True)
        thread.start()
        threads.append(thread)
    for thread in threads:
        thread.join()

    deadline = time.time() + 600
    while time.time() < deadline:
        if all(i.inference_queue.empty() for i, _ in instances):
            break
        time.sleep(1.0)
    for instance, _ in instances:
        instance.stop()

    peak = 0.0
    try:
        import mlx.core as mx
        peak = mx.get_peak_memory() / (1024.0 * 1024.0)
    except Exception:
        pass
    emit({"event": "done", "t": round(time.time() - started, 3), "mlx_peak_mb": round(peak, 1)})
    return 0


# ===== parent: orchestrate, compare, report =====

def load_turns():
    rows = []
    with open(TURNS, encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        for line in handle:
            rows.append(dict(zip(header, line.rstrip("\n").split("\t"))))
    return rows


def run_arm(label, args, unlocked):
    cmd = [sys.executable, os.path.abspath(__file__), "--child",
           "--model", args.model, "--hf-home", args.hf_home]
    if unlocked:
        cmd.append("--unlocked")
    if args.realtime:
        cmd.append("--realtime")
    print(f"== {label} ==", flush=True)
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    events = []
    for raw in proc.stdout.splitlines():
        raw = raw.strip()
        if raw.startswith("{"):
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
    lines = [e for e in events if e.get("event") == "line"]
    result = {
        "label": label, "unlocked": unlocked,
        "returncode": proc.returncode,
        "crashed": proc.returncode not in (0,),
        "signal": -proc.returncode if proc.returncode < 0 else 0,
        "wall_s": round(time.time() - started, 1),
        "lines": lines,
        "mlx_peak_mb": next((e.get("mlx_peak_mb") for e in reversed(events)
                             if e.get("event") == "done"), 0.0),
        "stderr_tail": "\n".join(proc.stderr.splitlines()[-8:]),
    }
    # A Python traceback in our own code is a harness defect, not a trial result. Scoring it as
    # a crash would confirm the invariant from a bug — the mirror of the corruption risk, and
    # harder to notice because the conclusion matches the expectation.
    tail = result["stderr_tail"]
    result["harness_error"] = ("Traceback (most recent call last)" in tail
                               and "npu_lock_trial.py" in tail)
    if result["harness_error"]:
        result["crashed"] = False
    # Persist the raw lines. The parent held them in memory only, so an arm's transcript died with
    # the process — and the transcript is the accuracy sample, which is 10x the size of the 80-clip
    # set the model choice currently rests on.
    # ⚠️ **In parent mode the flush-per-line property this tool's docstring claims is lost.**
    # The child streams JSONL to stdout line by line, but the parent collects `lines` in memory and
    # writes them here only once the arm has ended. So across three one-hour arms there is **no
    # artefact that grows**, and a working run is indistinguishable from a wedged one until it
    # finishes -- the only continuous signal is the process's own CPU time. Found 2026-08-18 while
    # trying to arm a stall-watchdog against it and having nothing to watch. Worth fixing by
    # appending as the lines arrive; recorded here so the next person does not repeat the search.
    events_dir = os.path.join(REPO_ROOT, "fixtures", "asr", "results", "trial_events")
    os.makedirs(events_dir, exist_ok=True)
    slug = args.model.replace("/", "--")
    with open(os.path.join(events_dir, f"{slug}__{label}.jsonl"), "w", encoding="utf-8") as fh:
        for line in lines:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")

    status = ("HARNESS ERROR" if result["harness_error"]
              else ("CRASHED" if result["crashed"] else "ok"))
    print(f"   {status}  rc={proc.returncode}  lines={len(lines)}  "
          f"wall={result['wall_s']}s  peak={result['mlx_peak_mb']} MB", flush=True)
    if result["crashed"]:
        print(f"   --- stderr tail ---\n{result['stderr_tail']}", flush=True)
    return result


def decile_drift(lines):
    """Median call latency by tenth of the run. A rising series is the 'it gets slower after an
    hour' failure, which no aggregate median would show."""
    if not lines:
        return []
    ordered = sorted(lines, key=lambda l: l["t"])
    size = max(1, len(ordered) // 10)
    out = []
    for start in range(0, len(ordered), size):
        chunk = [l["ms"] for l in ordered[start:start + size]]
        if chunk:
            out.append(round(sorted(chunk)[len(chunk) // 2]))
    return out[:10]


def score_against_reference(lines, turns):
    """CER of an arm's transcript against the fixture's own reference text.

    The arms are also compared to each other, but that only detects corruption. This is the
    accuracy number, and it rests on ~1130 turns of real conversation rather than the 80 clips the
    model choice was made on. Compared per track as one concatenated string: segment boundaries do
    not line up with turn boundaries, and forcing an alignment would measure the alignment.
    """
    from score_real_fixtures import cer

    track_of_role = {"Speaker (You)": "A", "Participant": "B"}
    out = {}
    for role, track in track_of_role.items():
        hyp = " ".join(l["text"] for l in sorted((l for l in lines if l["role"] == role),
                                                 key=lambda l: l["t"]))
        ref = " ".join(t["reference"] for t in turns if t["track"] == track)
        value = cer(ref, hyp)
        if value is not None:
            out[track] = value
    return out


def compare_content(a, b):
    """CER between two arms, comparing each role's transcript as one concatenated string.

    Not line-by-line. Segment boundaries move between runs -- the VAD flush depends on timing a
    saturating feed does not reproduce exactly -- so zipping line N against line N misaligns the
    whole tail after the first split or merge and reports a difference that is an artefact of the
    matching, not of the runs. Measured: line-by-line gave 0.88 between two identical runs whose
    concatenated text differs by 0.013.
    """
    from score_real_fixtures import cer

    scores = []
    for role in {l["role"] for l in a} | {l["role"] for l in b}:
        left = " ".join(l["text"] for l in sorted((l for l in a if l["role"] == role),
                                                  key=lambda l: l["t"]))
        right = " ".join(l["text"] for l in sorted((l for l in b if l["role"] == role),
                                                   key=lambda l: l["t"]))
        value = cer(left, right)
        if value is not None:
            scores.append(value)
    return (sum(scores) / len(scores)) if scores else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--unlocked", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    parser.add_argument("--hf-home", default=os.path.join(REPO_ROOT, ".hf_cache-bakeoff"))
    parser.add_argument("--realtime", action="store_true",
                        help="Feed in real time. Needed for end-to-end latency; costs one hour "
                             "of wall clock per arm. Off by default: a saturating feed does more "
                             "inferences per minute, which is the better soak for a rare fault")
    args = parser.parse_args()

    if args.child:
        return run_child(args)

    if not os.path.exists(TURNS):
        print("No conversation fixture. Run tools/build_conversation_fixture.py first.",
              file=sys.stderr)
        return 2
    turns = load_turns()
    print(f"Fixture: {len(turns)} turns, "
          f"{max(float(t['end_s']) for t in turns) / 60:.1f} min, model={args.model}")

    arms = [run_arm("locked-1", args, False), run_arm("locked-2", args, False)]
    if any(a["crashed"] or a.get("harness_error") for a in arms):
        print("\nBaseline failed — fix that before drawing any conclusion.", file=sys.stderr)
        return 1
    arms.append(run_arm("unlocked-1", args, True))

    baseline_drift = compare_content(arms[0]["lines"], arms[1]["lines"])
    unlocked_drift = compare_content(arms[0]["lines"], arms[2]["lines"])

    print("\n| Arm | crashed | lines | wall (s) | peak MLX (MB) | latency deciles (ms) |")
    print("|---|---|---|---|---|---|")
    for arm in arms:
        print(f"| {arm['label']} | {'YES' if arm['crashed'] else 'no'} | {len(arm['lines'])} | "
              f"{arm['wall_s']} | {arm['mlx_peak_mb']} | "
              f"{' '.join(str(v) for v in decile_drift(arm['lines']))} |")

    print("\n| Arm | CER vs reference, track A | track B |")
    print("|---|---|---|")
    for arm in arms:
        scored = score_against_reference(arm["lines"], turns)
        print(f"| {arm['label']} | "
              + " | ".join(f"{scored.get(t, float('nan')):.3f}" for t in ("A", "B")) + " |")

    print(f"\nbaseline variability (locked-1 vs locked-2): CER {baseline_drift}")
    print(f"unlocked vs locked-1:                        CER {unlocked_drift}")
    if arms[2].get("harness_error"):
        verdict = "NO RESULT — the harness failed, not the runtime. Fix and re-run."
    elif arms[2]["crashed"]:
        verdict = "INVARIANT STANDS — unlocked arm crashed inside the runtime"
    elif baseline_drift is None or unlocked_drift is None:
        verdict = "INCONCLUSIVE — no comparable transcripts"
    elif unlocked_drift > max(baseline_drift * 2, baseline_drift + 0.02):
        verdict = "INVARIANT STANDS — unlocked transcripts drift beyond baseline variability"
    else:
        gain = 1.0 - (arms[2]["wall_s"] / max(arms[0]["wall_s"], 1e-9))
        verdict = (f"CANDIDATE — no crash, content within baseline, wall clock {gain * 100:.0f}% "
                   f"faster" if gain >= 0.20 else
                   f"KEEP THE LOCK — no crash but only {gain * 100:.0f}% faster")
    print(f"\nVERDICT: {verdict}")
    print("Decision rule and its rationale: fixtures/asr/NPU_LOCK_TRIAL.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
