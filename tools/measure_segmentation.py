"""Does letting speech segments grow beat flushing them at 0.4 s of silence?

The last open question in the ASR item, inherited from the branch evaluation
(`docs/decisions/0006`) and never measured. The pipeline flushes a segment after **0.4 s of
silence**, which cuts natural speech mid-clause -- observed live 2026-08-12 (`"should I look into
the"`). Transcribing coherent windows instead would preserve sentence context. The cost is not
obvious in either direction, which is why this is measured rather than argued:

- **V51**: a call costs the same regardless of audio length, because Whisper pads to a fixed
  window. So fewer, longer segments are *cheaper in total*, not more expensive.
- But a longer segment cannot be transcribed until it closes, so the operator waits longer for the
  first word -- and **R9** is a claim about what reaches a speaker in time to be useful.
- And **R37** ranks above accuracy. A longer window swallows more non-speech alongside the speech,
  which is exactly the input **V60** measured the model inventing from.

What is compared, all mirroring `Transcriber._processing_thread` and differing in one parameter:

    flush=0.4   production today
    flush=0.8   twice as patient
    flush=1.5   patient enough to cross a breath
    window=8    fixed 8 s windows over VAD-detected speech, ignoring silence boundaries entirely

Nothing here touches the product. Segmentation is reimplemented against the same constants so a
strategy can be varied without editing `transcriber.py`, and the same backend transcribes all of
them.

CER is scored in **60-second buckets** rather than one alignment over the whole run: segment
boundaries differ between strategies, so hypotheses cannot be compared turn by turn, and a single
Levenshtein over ten thousand characters is both slow and dominated by one early insertion.

Run:  PYTHONPATH="$PWD" .venv/bin/python tools/measure_segmentation.py [--minutes 10]
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "tools"))

TARGET_SR = 16000
FRAME_S = 0.03
CONVERSATION = os.path.join(REPO, "fixtures", "asr", "conversation")
NONSPEECH = os.path.join(REPO, "fixtures", "asr", "nonspeech_real", "real")

TERMINAL_PUNCTUATION = "。！？.!?"


def load_samples(path, limit_s=None):
    """Mono float32 as a numpy array, and nothing else.

    `asr_eval.load_wav_mono_float32` returns `(samples, sample_rate)` and the samples are a plain
    list. Both facts cost a run: slicing the tuple and multiplying the list produced garbage that
    `webrtcvad` rejected, every strategy reported zero segments, and the exception handler below
    swallowed the reason. Converted once, here, so no caller repeats it.
    """
    import numpy as np
    from asr_eval import load_wav_mono_float32
    loaded = load_wav_mono_float32(path)
    samples = loaded[0] if isinstance(loaded, tuple) else loaded
    array = np.asarray(samples, dtype=np.float32)
    return array[: int(TARGET_SR * limit_s)] if limit_s else array


def segment_by_silence(samples, flush_s, min_s=0.3, max_s=15.0, aggressiveness=3):
    """Mirror `Transcriber._processing_thread`, with the silence threshold as a parameter.

    Returns `[(start_seconds, samples), ...]`. The 0.3 s minimum and 15 s cap are production's and
    are held fixed -- this measures the flush threshold, not three things at once.
    """
    import numpy as np
    import webrtcvad

    vad = webrtcvad.Vad(aggressiveness)
    frame = int(TARGET_SR * FRAME_S)
    flush_limit = int(flush_s / FRAME_S)
    min_samples = int(TARGET_SR * min_s)
    max_frames = int(max_s / FRAME_S)

    segments = []
    buffer = []
    silence = 0
    start_frame = 0
    for index in range(0, len(samples) - frame + 1, frame):
        chunk = samples[index:index + frame]
        pcm = (chunk * 32767).astype(np.int16)
        # Not swallowed. A VAD that rejects every frame is indistinguishable from silence, and
        # that is how this harness first reported zero segments for all four strategies.
        speech = vad.is_speech(pcm.tobytes(), TARGET_SR)
        if speech:
            if not buffer:
                start_frame = index
            buffer.append(chunk)
            silence = 0
        else:
            silence += 1
        if buffer and (silence >= flush_limit or len(buffer) >= max_frames):
            joined = np.concatenate(buffer)
            if len(joined) >= min_samples:
                segments.append((start_frame / TARGET_SR, joined))
            buffer, silence = [], 0
    if buffer:
        joined = np.concatenate(buffer)
        if len(joined) >= min_samples:
            segments.append((start_frame / TARGET_SR, joined))
    return segments


def segment_by_window(samples, window_s, min_s=0.3, aggressiveness=3):
    """Fixed windows, keeping only those with speech in them.

    The alternative the branch actually proposed: stop letting silence decide where a sentence
    ends. Silence still decides whether a window is worth transcribing at all -- a window of pure
    room tone is not sent, because **R37** outranks everything and **V60** measured what the model
    does with room tone.
    """
    import numpy as np
    import webrtcvad

    vad = webrtcvad.Vad(aggressiveness)
    frame = int(TARGET_SR * FRAME_S)
    window = int(TARGET_SR * window_s)
    segments = []
    for start in range(0, len(samples), window):
        chunk = samples[start:start + window]
        if len(chunk) < int(TARGET_SR * min_s):
            continue
        speech_frames = 0
        for index in range(0, len(chunk) - frame + 1, frame):
            pcm = (chunk[index:index + frame] * 32767).astype(np.int16)
            if vad.is_speech(pcm.tobytes(), TARGET_SR):
                speech_frames += 1
        if speech_frames * FRAME_S >= min_s:
            segments.append((start / TARGET_SR, chunk))
    return segments


STRATEGIES = [
    ("flush=0.4 (production)", lambda s: segment_by_silence(s, 0.4)),
    ("flush=0.8", lambda s: segment_by_silence(s, 0.8)),
    ("flush=1.5", lambda s: segment_by_silence(s, 1.5)),
    ("window=8s", lambda s: segment_by_window(s, 8.0)),
]


def reference_buckets(track, until_s, bucket_s=60.0):
    """Reference text per time bucket, from the fixture's ground-truth turns."""
    buckets = {}
    with open(os.path.join(CONVERSATION, "turns.tsv"), encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["track"] != track:
                continue
            start = float(row["start_s"])
            if start >= until_s:
                continue
            buckets.setdefault(int(start // bucket_s), []).append(row["reference"])
    return {k: " ".join(v) for k, v in buckets.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--track", default="B")
    parser.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    parser.add_argument("--hf-home", default="")
    parser.add_argument("--gate", action="store_true",
                        help="Screen every chunk through `src/voice_gate.py` before transcribing, "
                             "exactly as the live path does. **This is what makes the R37 column "
                             "able to choose again**: V89 found it saturated at 95-98%% for every "
                             "strategy, because ungated the model invents on almost any chunk and "
                             "the segmentation cannot be blamed for that. Gated, what is left is "
                             "the non-speech each strategy actually hands to the decoder.")
    args = parser.parse_args()

    from asr_bakeoff import (_boot_hf_home, backend_kind_for, make_transcribe_fn,
                             resolve_qwen_backend)
    from score_real_fixtures import cer
    from text_filters import is_acceptable

    _boot_hf_home(args.hf_home, offline=True)
    # Whatever the product ships today, not a literal: this comparison is only meaningful against
    # the model actually in the live path, and the id changed on 2026-08-17
    # (`docs/decisions/0012`) while this line still named the old one.
    model = args.model
    gate_reject = None
    if args.gate:
        import voice_gate
        if not voice_gate.is_live():
            raise SystemExit(
                "REFUSING: --gate was asked for and the gate is not live (V91). It fails open, so "
                "this run would transcribe every chunk and report itself as gated. Check that "
                "ivrit-ai/pyannote-segmentation-3.0 is under the HF_HOME this run uses."
            )
        gate_reject = lambda chunk: not voice_gate.has_speech(chunk, "", 0.25, TARGET_SR)
        print("gate: ON and verified live, floor 0.25s", flush=True)

    transcribe = make_transcribe_fn(backend_kind_for(model), model,
                                    resolve_qwen_backend())

    wav = os.path.join(CONVERSATION, f"track_{args.track}.wav")
    samples = load_samples(wav, args.minutes * 60)
    print(f"speech: {wav} first {args.minutes:g} min", flush=True)

    refs = reference_buckets(args.track, args.minutes * 60)
    nonspeech = sorted(f for f in os.listdir(NONSPEECH) if f.endswith(".wav"))
    print(f"non-speech: {len(nonspeech)} real recordings\n", flush=True)

    results = []
    for label, segmenter in STRATEGIES:
        print(f"--- {label}", flush=True)
        segments = segmenter(samples)
        if not segments:
            raise RuntimeError(
                f"{label}: no speech segments in {args.minutes:g} min of speech. That is a harness "
                f"fault, not a result -- it reported CER 1.0 for every strategy once already."
            )
        durations = [len(chunk) / TARGET_SR for _, chunk in segments]

        hypotheses, latencies = {}, []
        for start, chunk in segments:
            began = time.monotonic()
            text = "" if (gate_reject and gate_reject(chunk)) else transcribe(chunk)
            latencies.append((time.monotonic() - began) * 1000)
            if is_acceptable(text):
                hypotheses.setdefault(int(start // 60), []).append(text)

        scores = [cer(refs[b], " ".join(hypotheses.get(b, []))) for b in sorted(refs)]
        scores = [v for v in scores if v is not None]

        # A segment whose transcript does not end in terminal punctuation was probably cut
        # mid-clause. A proxy, and named as one -- the model's punctuation is its own judgement.
        flat = [t for texts in hypotheses.values() for t in texts]
        unterminated = sum(1 for t in flat if not t.rstrip().endswith(tuple(TERMINAL_PUNCTUATION)))

        # R37 on the same strategy: real non-speech through the same segmentation.
        false_lines = 0
        probed = 0
        for name in nonspeech:
            audio = load_samples(os.path.join(NONSPEECH, name))
            for _, chunk in segmenter(audio):
                probed += 1
                if gate_reject and gate_reject(chunk):
                    continue
                if is_acceptable(transcribe(chunk)):
                    false_lines += 1

        row = {
            "strategy": label,
            "segments": len(segments),
            "median_segment_s": round(statistics.median(durations), 2) if durations else 0,
            "total_audio_s": round(sum(durations), 1),
            "lines": len(flat),
            "cer": round(statistics.mean(scores), 4) if scores else None,
            "median_call_ms": round(statistics.median(latencies)) if latencies else None,
            "total_inference_s": round(sum(latencies) / 1000, 1),
            "unterminated_pct": round(100 * unterminated / len(flat), 1) if flat else None,
            "nonspeech_segments": probed,
            "nonspeech_false_lines": false_lines,
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    print("\n===== segmentation comparison =====")
    header = ("strategy", "segs", "med s", "lines", "CER", "med ms", "infer s", "cut %", "R37")
    print("  {:<24} {:>5} {:>6} {:>6} {:>7} {:>7} {:>8} {:>6} {:>10}".format(*header))
    for r in results:
        print("  {:<24} {:>5} {:>6} {:>6} {:>7} {:>7} {:>8} {:>6} {:>10}".format(
            r["strategy"], r["segments"], r["median_segment_s"], r["lines"],
            f"{r['cer']:.4f}" if r["cer"] is not None else "-",
            r["median_call_ms"] or "-", r["total_inference_s"],
            f"{r['unterminated_pct']}" if r["unterminated_pct"] is not None else "-",
            f"{r['nonspeech_false_lines']}/{r['nonspeech_segments']}"))
    print("\n  CER lower is better. 'cut %' is segments not ending in terminal punctuation --")
    print("  a proxy for being cut mid-clause. R37 is false lines on real non-speech, and it")
    print("  outranks the rest: a strategy that wins CER and loses R37 has not won.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
