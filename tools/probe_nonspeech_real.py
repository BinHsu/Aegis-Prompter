#!/usr/bin/env python3
"""R37 on non-speech that is not a synthesized tone. The measurement behind V60, and now V71.

**Why this is a tracked tool and was not.** It ran as a scratch script under
`fixtures/asr/results/.probes/` — a gitignored path — and produced **V60**, the constraint that
says the shipped model does not satisfy **R37** on its own. When the ASR model was replaced on
2026-08-17 (`docs/decisions/0012`) that measurement had to be redone for the new model, and the
only copy of the method was one `rm -rf fixtures/asr/results` away from being gone. A measurement
a requirement leans on belongs where the requirement can find it.

The synthesized fixtures under `fixtures/asr/nonspeech/` are the *easy* case and every candidate
this repository has measured treats them as a separate world: the model that scored 0/63 there
scored 23/253 here. Read a clean synthetic run as a control, never as an **R37** verdict.

Scores through the product's own path: `tools/asr_bakeoff.vad_speech_segments` (webrtcvad
aggressiveness 3, 30 ms frames, 0.4 s flush, 15 s cap, 0.3 s floor — the same constants as
`transcriber.py`), one model call per segment, under `NPU_LOCK`, offline, one candidate per
process.

Three deliberate choices, carried over from the scratch original because each one caught
something:

- **A positive control runs in the same process.** A probe reporting "no text anywhere" is
  indistinguishable from a broken harness unless something in the same process is shown to
  produce text. Real ASCEND speech clips go through the identical call.
- **The old synthesized fixtures run as a control too**, so a result can be *compared* with the
  0/63 that chose an earlier default rather than merely set beside it.
- **`--passes` repeats everything.** **V54** recorded that a sampled decoder makes a single
  non-speech count uninterpretable, and Whisper *is* sampled — `mlx_whisper.transcribe` defaults
  to a temperature ladder and falls back up it when a segment fails its thresholds. Reporting one
  pass here would be reporting a draw from a distribution as though it were a constant.

Both counts are reported and they answer different questions. **Raw** is what the model produced
and is the number to compare models on (**R11**). **Reaching the buffer** additionally applies
`text_filters.is_acceptable`, and describes the pipeline as shipped.

Run:
    PYTHONPATH="$PWD" .venv/bin/python tools/probe_nonspeech_real.py \\
        --model mlx-community/whisper-large-v3-turbo --passes 3
"""

import argparse
import collections
import hashlib
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import asr_bakeoff as harness  # noqa: E402
import model_search  # noqa: E402
from asr_eval import TARGET_SR, iter_fixture_wavs, load_wav_mono_float32  # noqa: E402

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
DEFAULT_OUT = os.path.join(FIXTURE_ROOT, "results", "nonspeech_real_probe.jsonl")


def segments_for(subdir):
    """(label, float32 segment) for every VAD segment under fixtures/asr/<subdir>."""
    import numpy as np

    for path in iter_fixture_wavs(FIXTURE_ROOT, subdir):
        rel = os.path.relpath(path, FIXTURE_ROOT)
        samples, _sr = load_wav_mono_float32(path)
        audio = np.asarray(samples, dtype=np.float32)
        for idx, chunk in enumerate(harness.vad_speech_segments(audio)):
            yield f"{rel}#{idx}", chunk


def control_speech(limit=10):
    """Positive control: real recorded speech, whole clip, through the same call."""
    import numpy as np

    for path in iter_fixture_wavs(FIXTURE_ROOT, "real/mixed")[:limit]:
        rel = os.path.relpath(path, FIXTURE_ROOT)
        samples, _sr = load_wav_mono_float32(path)
        yield f"CONTROL {rel}", np.asarray(samples, dtype=np.float32)


def build_inputs(include_old):
    yield from control_speech()
    if include_old:
        for label, chunk in segments_for("nonspeech"):
            yield f"OLD {label}", chunk
    for label, chunk in segments_for("nonspeech_real"):
        yield f"NEW {label}", chunk


def group_of(label):
    """Reporting bucket: control / old-synthetic / real / derived / synth."""
    if label.startswith("CONTROL"):
        return "control-speech"
    if label.startswith("OLD "):
        return "old-synthetic"
    body = label.split(" ", 1)[1]
    return "new-" + body.split("/")[1]


# **`nonspeech_real/derived/` is not all non-speech, and counting it as though it were inflates
# the R37 denominator with material R37 is not about.** It holds room tone -- genuine silence, and
# what **V60** counted -- alongside `quiet_speech_*`, `babble_*`, `mumble_*`, `crosstalk_*` and
# `filled_pauses`, which are real speech attenuated, overlapped or obscured. A model producing text
# from attenuated speech is doing its job badly, not inventing an utterance out of nothing, and the
# two failures need different answers.
#
# Found 2026-08-17 while scoring the replacement model: a first pass reported "433 of 435 non-speech
# segments produced text" against **V60**'s "23 of 253", and neither the numerator nor the
# denominator was comparable -- the fixture set had grown since V60 was written. Buckets, not one
# total.
DEGRADED_SPEECH_PREFIXES = ("babble", "crosstalk", "filled_pauses", "mumble", "quiet_speech")


def bucket_of(row):
    """`nonspeech` | `degraded-speech` | `control` | `old-synthetic`. The R37 number is the first."""
    group = row["group"]
    if group == "control-speech":
        return "control"
    if group == "old-synthetic":
        return "old-synthetic"
    name = os.path.basename(row["input"].split(" ", 1)[1].split("#")[0])
    if group == "new-derived" and name.startswith(DEGRADED_SPEECH_PREFIXES):
        return "degraded-speech"
    return "nonspeech"


def summarise(rows):
    """Print the three tables the constraint text is written from. Pure reporting."""
    from text_filters import is_acceptable

    passes = sorted({r["pass"] for r in rows})
    print(f"\n{len(rows)} calls over passes {passes}")

    print("\n== per pass, per group: calls that produced any text ==")
    per = collections.defaultdict(lambda: [0, 0])
    for row in rows:
        key = (row["pass"], row["group"])
        per[key][1] += 1
        if row["text"]:
            per[key][0] += 1
    groups = sorted({g for _p, g in per})
    print(f"{'group':<20} " + " ".join(f"pass{p:<10}" for p in passes))
    for group in groups:
        cells = " ".join(f"{per[(p, group)][0]:>4}/{per[(p, group)][1]:<10}" for p in passes)
        print(f"{group:<20} {cells}")

    print("\n== by bucket, per pass — `nonspeech` is the R37 number ==")
    print(f"{'bucket':<16} {'pass':>4}  {'produced text':>16}  {'reached buffer':>16}")
    for bucket in ("nonspeech", "degraded-speech", "old-synthetic", "control"):
        for p in passes:
            raw = acc = total = 0
            for row in rows:
                if row["pass"] != p or bucket_of(row) != bucket:
                    continue
                total += 1
                if row["text"]:
                    raw += 1
                    if is_acceptable(row["text"]):
                        acc += 1
            if total:
                print(f"{bucket:<16} {p:>4}  {raw:>7}/{total:<8}  {acc:>7}/{total:<8}")
    print("  `degraded-speech` is attenuated, overlapped or obscured REAL speech — text there is"
          "\n  bad transcription, not an invented utterance, and R37 is not about it.")

    print("\n== per file (pass 0) ==")
    byfile = collections.defaultdict(lambda: [0, 0, 0])
    for row in rows:
        if row["pass"] != 0 or row["group"] == "control-speech":
            continue
        name = row["input"].split(" ", 1)[1].split("#")[0]
        byfile[name][2] += 1
        if row["text"]:
            byfile[name][0] += 1
            if is_acceptable(row["text"]):
                byfile[name][1] += 1
    for name in sorted(byfile):
        got, kept, segs = byfile[name]
        if got:
            print(f"  {name:<52} text {got:3d}/{segs:<3d}  reaches buffer {kept:3d}")

    print("\n== every distinct non-speech string, with the passes it appeared in ==")
    strings = collections.defaultdict(set)
    for row in rows:
        if row["group"] == "control-speech" or not row["text"]:
            continue
        strings[(row["input"], row["text"])].add(row["pass"])
    for (label, text), where in sorted(strings.items()):
        keep = "BUFFER" if is_acceptable(text) else "dropped"
        print(f"  [{keep:>7}] p{sorted(where)} {label}\n            {text!r}")

    diag = [r for r in rows if r.get("segments")]
    if diag:
        print("\n== can ANY threshold separate ghosts from speech? (--diagnostics) ==")
        print("Whisper skips only when `no_speech_prob > no_speech_threshold` AND")
        print("`avg_logprob <= logprob_threshold`. If the two distributions below overlap, no")
        print("setting of either separates them, and sweeping thresholds is wasted GPU time.")
        buckets = {}
        for row in diag:
            key = "REAL SPEECH" if bucket_of(row) == "control" else (
                "non-speech, produced text" if row["text"] else "non-speech, silent")
            for seg in row["segments"]:
                if seg.get("avg_logprob") is None:
                    continue
                buckets.setdefault(key, []).append(seg)
        print(f"\n{'population':<28}{'n':>6}{'avg_logprob p5/med/p95':>28}"
              f"{'no_speech_prob p5/med/p95':>30}")
        for key in sorted(buckets):
            segs = buckets[key]

            def band(field):
                values = sorted(s[field] for s in segs if s.get(field) is not None)
                if not values:
                    return "—"
                lo = values[max(0, int(len(values) * 0.05) - 1)]
                mid = values[len(values) // 2]
                hi = values[min(len(values) - 1, int(len(values) * 0.95))]
                return f"{lo:.3f} / {mid:.3f} / {hi:.3f}"

            print(f"{key:<28}{len(segs):>6}{band('avg_logprob'):>28}"
                  f"{band('no_speech_prob'):>30}")
        print("\nRead the `avg_logprob` column first: it is the veto. A ghost whose confidence sits")
        print("inside the real-speech band cannot be gated away without taking real speech with it.")

    print("\n== determinism (V54) ==")
    by_pass = {p: {r["input"]: r["text"] for r in rows if r["pass"] == p} for p in passes}
    base = by_pass[passes[0]]
    for p in passes[1:]:
        differing = [k for k in base if base[k] != by_pass[p].get(k)]
        print(f"  pass {passes[0]} vs {p}: {len(differing)} of {len(base)} inputs differ")
        for k in differing[:10]:
            print(f"     {k}\n       p{passes[0]}: {base[k]!r}\n       p{p}: {by_pass[p].get(k)!r}")
    digests = [hashlib.sha256(
        "\n".join(f"{k}\t{v}" for k, v in sorted(by_pass[p].items())).encode("utf-8")
    ).hexdigest()[:16] for p in passes]
    print("  per-pass transcript digest:", digests)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--skip-old", action="store_true",
                        help="Drop the synthesized-fixture control. Faster, and loses the only "
                             "figure that ties this run to the earlier ones.")
    parser.add_argument("--model-vad", default="",
                        help="Voice-activity model for --gate. Empty uses voice_gate's default.")
    parser.add_argument("--hf-home", default=os.path.join(REPO_ROOT, ".hf_cache-bakeoff"))
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--gate", action="store_true",
                        help="Screen each segment through `src/voice_gate.py` before transcribing "
                             "-- **the shipped module, not this tool's own pipeline**. That "
                             "difference is the point: V80 and V82 measured a detector, this "
                             "measures the product. A segment the gate rejects is recorded with "
                             "empty text, exactly as the live path would leave it.")
    parser.add_argument("--gate-min-speech", type=float, default=0.25,
                        help="Speech floor for --gate. 0.25 is the measured knee (V82).")
    parser.add_argument("--diagnostics", action="store_true",
                        help="Also record `avg_logprob`, `no_speech_prob` and `compression_ratio` "
                             "per segment. **This is the measurement that says whether any "
                             "threshold could work.** Whisper skips a segment only when "
                             "`no_speech_prob > no_speech_threshold` AND "
                             "`avg_logprob <= logprob_threshold` "
                             "(`mlx_whisper/transcribe.py:303-311`, whose own comment reads "
                             "*don't skip if the logprob is high enough, despite the "
                             "no_speech_prob*) — so a **confident** hallucination defeats the gate "
                             "by construction. Comparing the two distributions for ghosts against "
                             "real speech says directly whether they are separable at all, which "
                             "no amount of sweeping thresholds can establish")
    parser.add_argument("--decode", default="",
                        help="JSON of decoding overrides to score INSTEAD of the product's "
                             "current options, e.g. '{\"temperature\": [0.0], "
                             "\"logprob_threshold\": -0.5}'. `tools/measure_decode_thresholds.py` "
                             "compares arms against each other on one pooled corpus; this scores "
                             "one configuration on the same 253 segments V60 and V72 used, which "
                             "is the only denominator those two can be read against.")
    parser.add_argument("--summarise-only", default="",
                        help="Path to an existing JSONL; print the tables and exit without "
                             "running the model.")
    args = parser.parse_args()

    if args.summarise_only:
        with open(args.summarise_only, encoding="utf-8") as handle:
            summarise([json.loads(line) for line in handle])
        return 0

    harness._boot_hf_home(args.hf_home, offline=True)

    import numpy as np

    # No `NPU_LOCK` here, and that is not an omission. `harness.make_transcribe_fn` takes the lock
    # *inside* the callable it returns, and `NPU_LOCK` is a plain `threading.Lock` -- not an
    # `RLock` -- so a second acquire on the same thread deadlocks silently, with no traceback and
    # no output. The scratch original this replaces called the backend module directly and so
    # needed its own acquire; copying that line across cost one hung run on 2026-08-17.
    # `backend_kind_for`, not `model_search.family_for`: this harness must still be able to
    # score the family the product refuses (R50), or the comparison behind that refusal
    # cannot be reproduced.
    kind = harness.backend_kind_for(args.model)
    diagnose = None
    if args.decode or args.diagnostics:
        import mlx_whisper
        from transcriber import NPU_LOCK

        overrides = json.loads(args.decode) if args.decode else {}
        options = dict(fp16=True, no_speech_threshold=0.6, condition_on_previous_text=False)
        options.update(overrides)
        # `temperature` must be a tuple for `mlx_whisper`; JSON can only give a list.
        if isinstance(options.get("temperature"), list):
            options["temperature"] = tuple(options["temperature"])

        def call(audio):
            with NPU_LOCK:
                return mlx_whisper.transcribe(audio, path_or_hf_repo=args.model, **options)

        def transcribe(audio):
            return (call(audio).get("text") or "").strip()

        def diagnose(audio):
            """Text plus the two numbers the skip decision is actually made from.

            Reported per *decoded segment* rather than averaged, because the decision is made per
            segment: one confident segment inside a window is enough to put text in the buffer,
            and an average would hide it behind the quiet ones.
            """
            result = call(audio)
            segments = result.get("segments") or []
            return (result.get("text") or "").strip(), [
                {"avg_logprob": s.get("avg_logprob"),
                 "no_speech_prob": s.get("no_speech_prob"),
                 "compression_ratio": s.get("compression_ratio"),
                 "temperature": s.get("temperature")}
                for s in segments
            ]

        transcribe(np.zeros(16000, dtype=np.float32))  # warm, so the first scored call is not load
        if overrides:
            print(f"decoding overrides: {overrides}")
        if args.diagnostics:
            print("diagnostics: recording avg_logprob / no_speech_prob / compression_ratio")
    else:
        transcribe = harness.make_transcribe_fn(kind, args.model, harness.resolve_qwen_backend())

    inputs = list(build_inputs(not args.skip_old))
    print(f"model={args.model}  backend={kind}  inputs={len(inputs)}  passes={args.passes}")

    rows = []
    gated = 0
    if args.gate:
        import voice_gate
        print(f"gate: voice_gate.py, floor {args.gate_min_speech}s, model {args.model_vad!r}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    handle = open(args.out, "w", encoding="utf-8")
    for pass_no in range(args.passes):
        counts = {}
        started = time.time()
        for label, audio in inputs:
            arr = np.asarray(audio, dtype=np.float32)
            t0 = time.perf_counter()
            if args.gate and not voice_gate.has_speech(arr, args.model_vad,
                                                       args.gate_min_speech, TARGET_SR):
                # Rejected: the live path would never enqueue this, so it produces no line and
                # costs no decode. Recorded rather than skipped, so the denominator stays 253.
                text, segments = "", None
                gated += 1
            elif diagnose is not None and args.diagnostics:
                text, segments = diagnose(arr)
            else:
                text, segments = transcribe(arr), None
            ms = (time.perf_counter() - t0) * 1000.0
            group = group_of(label)
            hit, total = counts.get(group, (0, 0))
            counts[group] = (hit + (1 if text else 0), total + 1)
            row = {"pass": pass_no, "input": label, "group": group,
                   "seconds": round(len(arr) / TARGET_SR, 2), "ms": round(ms, 1), "text": text}
            if segments is not None:
                row["segments"] = segments
            rows.append(row)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            if text and group != "control-speech":
                print(f"  !! TEXT  {label}  ({len(arr) / TARGET_SR:.1f}s)  {text!r}", flush=True)
        print(f"pass {pass_no}: {time.time() - started:.0f}s", flush=True)
        for group in sorted(counts):
            hit, total = counts[group]
            print(f"    {group:<20} produced text on {hit}/{total}", flush=True)
    handle.close()

    if args.gate:
        print(f"\ngate rejected {gated} of {len(inputs) * args.passes} calls before the decoder")
    summarise(rows)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
