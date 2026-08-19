#!/usr/bin/env python3
"""Would a neural VAD in front of the decoder stop the false lines? The stage nobody searched.

**V73 and V77 declared the audio side exhausted, and that was wrong in a specific way.** They
swept what the *decoder* does — temperature, `no_speech_threshold`, `logprob_threshold`,
`compression_ratio_threshold` — and compared checkpoints. Neither touched the stage *before* the
decoder. This product gates with `webrtcvad` at aggressiveness 3, a 2011 energy/GMM detector, and
**the 253 non-speech segments in V72 are precisely what survived it**. Every one of them was handed
to Whisper because WebRTC called it speech.

That is also what the field does about this problem. `faster-whisper` and WhisperX both put a
**neural** VAD in front of Whisper, and the published work on non-speech hallucination reports the
same thing: the reliable fix is not to decode the segment at all.

- Calm-Whisper, Interspeech 2025 — https://arxiv.org/html/2505.12969v1
- Investigation of Whisper ASR Hallucinations Induced by Non-Speech Audio —
  https://arxiv.org/html/2501.11378v1
- openai/whisper discussion #1606 — https://github.com/openai/whisper/discussions/1606

**It is also, structurally, what the removed model was doing internally** — which is why its
silence was free (**V77**): it declined to emit rather than being talked out of emitting.

**The measurement is the same two columns as everything else**, so the result is directly
comparable with **V77**'s audio-side exchange rate and **V78**'s text-side one:

- `nonspeech` — 253 segments of genuine non-speech. A neural VAD rejecting them is the win.
- `degraded-speech` — 204 segments of *real* speech, attenuated or obscured. Rejecting them is the
  cost, and **V64** says this cost is the larger one.
- `control` — clean real speech. Rejecting any is disqualifying.

**What would refute it:** rejection rates on the two populations that are close together. That
would mean a neural VAD separates them no better than a threshold did, and the stage is not the
answer after all.

⚠️ **Provenance is an open question for anything that ships, and this tool does not settle it.**
Silero VAD is MIT-licensed and Russian-authored; `pyannote` is French and **already a project
dependency**, installed on demand by `src/diarize.py`. **R50** as written bars PRC origin only, so
neither is excluded by it — but R50 exists because provenance is a procurement question here, so a
shipping choice needs that asked explicitly rather than inherited from whichever was easiest to
measure. This measures Silero because `torch` was already in the disposable venv.

Run:
    PYTHONPATH="$PWD" .venv-bakeoff/bin/python tools/measure_vad_gate.py
"""

import argparse
import collections
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

import asr_bakeoff as harness  # noqa: E402
from asr_eval import iter_fixture_wavs, load_wav_mono_float32  # noqa: E402
from probe_nonspeech_real import DEGRADED_SPEECH_PREFIXES  # noqa: E402

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
TARGET_SR = 16000


def bucket_for(rel):
    """Same split as `probe_nonspeech_real`, applied to a path rather than a scored row."""
    parts = rel.split(os.sep)
    if parts[0] == "real":
        return "control"
    if parts[0] == "nonspeech":
        return "old-synthetic"
    name = os.path.basename(rel)
    if "derived" in parts and name.startswith(DEGRADED_SPEECH_PREFIXES):
        return "degraded-speech"
    return "nonspeech"


def segments():
    """Every segment the product's own VAD lets through, with its bucket. The denominator here is
    deliberately *what WebRTC passed*, because that is what reaches the decoder today."""
    import numpy as np

    out = []
    for subdir in ("real/mixed", "nonspeech", "nonspeech_real"):
        for path in iter_fixture_wavs(FIXTURE_ROOT, subdir):
            rel = os.path.relpath(path, FIXTURE_ROOT)
            if rel.startswith("real" + os.sep) and len(out) > 400:
                continue
            samples, _sr = load_wav_mono_float32(path)
            audio = np.asarray(samples, dtype=np.float32)
            if rel.startswith("real" + os.sep):
                out.append((bucket_for(rel), rel, audio))
                continue
            for idx, chunk in enumerate(harness.vad_speech_segments(audio)):
                out.append((bucket_for(rel), f"{rel}#{idx}", chunk))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="silero", choices=("silero", "pyannote"),
                        help="Which detector to gate with. `pyannote` is the operator's choice "
                             "(2026-08-18) on provenance -- French, and already a project "
                             "dependency -- accepting that it pulls 47 packages including a "
                             "telemetry framework and a cloud SDK, which `diarize.py` had "
                             "deliberately kept to an on-demand install")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Silero speech probability above which a segment is kept")
    parser.add_argument("--min-speech", type=float, default=0.25,
                        help="pyannote: seconds of detected speech a segment needs to be kept. "
                             "Not cosmetic -- with no floor the detector calls a 0.24 s chime "
                             "transient speech, while real speech fills the window. The product's "
                             "own minimum segment is 0.3 s")
    parser.add_argument("--segmentation", default="ivrit-ai/pyannote-segmentation-3.0",
                        help="pyannote segmentation weights. The default is the ungated re-host "
                             "`diarize.py` already verified; pyannote's own is gated")
    parser.add_argument("--control-limit", type=int, default=10)
    parser.add_argument("--out", default=os.path.join(FIXTURE_ROOT, "results", "vad_gate.json"))
    args = parser.parse_args()

    import torch

    if args.backend == "silero":
        from silero_vad import load_silero_vad, get_speech_timestamps
        model = load_silero_vad()
        print(f"backend=silero threshold={args.threshold}")

        def has_speech(audio):
            return bool(get_speech_timestamps(torch.from_numpy(audio), model,
                                              threshold=args.threshold, sampling_rate=TARGET_SR))
    else:
        from pyannote.audio import Model
        from pyannote.audio.pipelines import VoiceActivityDetection
        seg = Model.from_pretrained(args.segmentation)
        pipeline = VoiceActivityDetection(segmentation=seg)
        pipeline.instantiate({"min_duration_on": 0.0, "min_duration_off": 0.0})
        print(f"backend=pyannote segmentation={args.segmentation} "
              f"min_speech={args.min_speech}s")

        def has_speech(audio):
            out = pipeline({"waveform": torch.from_numpy(audio).unsqueeze(0),
                            "sample_rate": TARGET_SR})
            return sum(s.duration for s in out.get_timeline()) >= args.min_speech

    rows = segments()
    controls = [r for r in rows if r[0] == "control"][: args.control_limit]
    rows = [r for r in rows if r[0] != "control"] + controls
    counts = collections.defaultdict(lambda: [0, 0])
    examples = collections.defaultdict(list)

    for bucket, label, audio in rows:
        kept = has_speech(audio)
        counts[bucket][1] += 1
        if kept:
            counts[bucket][0] += 1
        elif bucket in ("degraded-speech", "control") and len(examples[bucket]) < 6:
            examples[bucket].append(label)

    print(f"\n| Population | reaches the decoder | rejected by {args.backend} |")
    print("|---|---|---|")
    for bucket in ("nonspeech", "degraded-speech", "control", "old-synthetic"):
        kept, total = counts[bucket]
        if total:
            print(f"| {bucket} | {kept}/{total} ({100*kept/total:.0f}%) | "
                  f"**{total-kept}** ({100*(total-kept)/total:.0f}%) |")
    print("\nRejecting `nonspeech` is the win; rejecting `degraded-speech` is the cost, and V64")
    print("says the cost is the larger one. Rejecting `control` at all is disqualifying.")
    for bucket, items in examples.items():
        if items:
            print(f"\n  real speech {args.backend} would drop ({bucket}):")
            for label in items:
                print(f"    {label}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"backend": args.backend, "threshold": args.threshold,
                   "min_speech": args.min_speech,
                   "counts": {k: v for k, v in counts.items()}}, handle, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
