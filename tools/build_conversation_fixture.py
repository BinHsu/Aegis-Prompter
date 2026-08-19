#!/usr/bin/env python3
"""Build a two-track conversation fixture with an exact reference timeline.

For the `NPU_LOCK` trial (`fixtures/asr/NPU_LOCK_TRIAL.md`) and for any later dual-track work.

CAiRE/ASCEND's test split is 55 minutes of real Mandarin-English conversation across four
sessions, three of which have two speakers. **The original timeline is recoverable**: every
filename carries `ses<N>_spk<N>_L<N>_<start>_<duration>.wav`, and those durations agree with the
`duration` column on all 1315 rows. So each utterance goes back where it actually happened, on the
track belonging to its speaker, with silence on the other.

That matters more than a tidy layout would. Session 1 alone has **274 speaker alternations and
genuine overlap** -- one speaker starting while the other is still talking. Two tracks carrying
real crosstalk is what the product faces once a second capture source exists, and it is what
**R2** (two tracks, never mixed) is actually about. It is also the case V56 did not measure: that
run fed identical audio to both tracks at saturation, which is an upper bound, not a conversation.

The reference timeline is exact because the corpus published it and we preserve it. `turns.tsv` records where every turn starts and ends and what was said, so a trial can
check three separate things instead of one:

  1. **content** -- what was transcribed, against the reference text
  2. **timing**  -- when the line appeared, against when the turn ended (end-to-end latency)
  3. **completeness** -- whether every turn produced a line at all (R3)

Output is gitignored and rebuilds from the recorded seed:

    rm -rf fixtures/asr/conversation

Runs entirely from the cached parquet: pass --offline (default) so a corporate TLS interception
cannot fail the build halfway through (observed 2026-08-11).
"""

import argparse
import io
import os
import sys
import wave

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")
OUT_ROOT = os.path.join(FIXTURE_ROOT, "conversation")
BAKEOFF_CACHE = os.path.join(REPO_ROOT, ".hf_cache-bakeoff")

DATASET = "CAiRE/ASCEND"
SPLIT_FILE = "main/test-00000-of-00001.parquet"
TARGET_SR = 16000


class TrackWriter:
    """Append audio or silence to one track, keeping memory flat over a one-hour file."""

    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.handle = wave.open(path, "wb")
        self.handle.setnchannels(1)
        self.handle.setsampwidth(2)
        self.handle.setframerate(TARGET_SR)
        self.samples = 0

    def append(self, pcm_int16):
        self.handle.writeframes(pcm_int16.tobytes())
        self.samples += len(pcm_int16)

    def append_silence(self, n):
        import numpy as np
        if n > 0:
            self.append(np.zeros(n, dtype="<i2"))

    def close(self):
        self.handle.close()


def _to_int16(samples, src_sr):
    import numpy as np

    audio = np.asarray(samples, dtype="float32")
    if getattr(audio, "ndim", 1) > 1:
        audio = audio.mean(axis=1)
    if src_sr != TARGET_SR:
        duration = len(audio) / float(src_sr)
        dst_n = int(round(duration * TARGET_SR))
        audio = np.interp(
            np.linspace(0.0, duration, dst_n, endpoint=False),
            np.linspace(0.0, duration, len(audio), endpoint=False),
            audio,
        ).astype("float32")
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")


def build(max_minutes, session_gap_s, offline):
    import re

    import soundfile as sf
    from huggingface_hub import hf_hub_download
    import pyarrow.parquet as pq

    if offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
    path = hf_hub_download(DATASET, SPLIT_FILE, repo_type="dataset", cache_dir=BAKEOFF_CACHE)
    table = pq.read_table(path).to_pydict()

    # ses1_spk17_L3818_9.3200_0.6400.wav -> session, speaker, original start, duration.
    pattern = re.compile(r"ses(\d+)_spk(\d+)_L\d+_(\d+\.\d+)_(\d+\.\d+)\.wav$")
    items = []
    for idx, raw in enumerate(table["path"]):
        match = pattern.search(str(raw))
        if not match:
            continue
        items.append({
            "idx": idx,
            "session": int(match.group(1)),
            "speaker": int(match.group(2)),
            "start": float(match.group(3)),
            "dur": float(match.group(4)),
        })
    if not items:
        print("No filenames carried a timeline; cannot place utterances.", file=sys.stderr)
        return []

    counts = {}
    for item in items:
        counts[item["speaker"]] = counts.get(item["speaker"], 0) + 1
    ranked = sorted(counts, key=lambda s: -counts[s])[:2]
    track_of = {ranked[0]: "A", ranked[1]: "B"} if len(ranked) > 1 else {ranked[0]: "A"}
    print(f"  speakers -> tracks: {track_of}")

    # Sessions are laid end to end; within a session the published offsets are preserved exactly.
    items.sort(key=lambda i: (i["session"], i["start"]))
    session_base = {}
    cursor = 0.0
    for session in sorted({i["session"] for i in items}):
        session_base[session] = cursor
        span = max(i["start"] + i["dur"] for i in items if i["session"] == session)
        cursor += span + session_gap_s

    limit_s = max_minutes * 60.0
    placed = []
    for item in items:
        if track_of.get(item["speaker"]) is None:
            continue
        absolute = session_base[item["session"]] + item["start"]
        if absolute >= limit_s:
            continue
        placed.append({**item, "abs_start": absolute})

    writers = {name: TrackWriter(os.path.join(OUT_ROOT, f"track_{name}.wav"))
               for name in sorted(set(track_of.values()))}
    shifted = 0
    turns = []
    for track in writers:
        speakers = [s for s, t in track_of.items() if t == track]
        mine = sorted((p for p in placed if p["speaker"] in speakers),
                      key=lambda p: p["abs_start"])
        for item in mine:
            blob = table["audio"][item["idx"]]["bytes"]
            samples, sr = sf.read(io.BytesIO(blob), dtype="float32", always_2d=False)
            pcm = _to_int16(samples, sr)
            start_n = int(round(item["abs_start"] * TARGET_SR))
            if start_n < writers[track].samples:
                # Same speaker overlapping themselves: shift rather than mix, and count it, so
                # the reference timeline stays true to what the WAV contains.
                shifted += 1
                start_n = writers[track].samples
            writers[track].append_silence(start_n - writers[track].samples)
            writers[track].append(pcm)
            turns.append({
                "turn": 0,
                "track": track,
                "speaker": item["speaker"],
                "start_s": round(start_n / TARGET_SR, 3),
                "end_s": round((start_n + len(pcm)) / TARGET_SR, 3),
                "language": table["language"][item["idx"]],
                "session": item["session"],
                "reference": (table["transcription"][item["idx"]] or "").strip(),
            })

    # Pad every track to the same length so the two files are a single timeline.
    longest = max(w.samples for w in writers.values())
    for writer in writers.values():
        writer.append_silence(longest - writer.samples)
        writer.close()

    turns.sort(key=lambda t: (t["start_s"], t["track"]))
    for n, turn in enumerate(turns):
        turn["turn"] = n

    overlaps = sum(
        1 for a in turns for b in turns
        if a["track"] != b["track"] and a["start_s"] < b["end_s"] and b["start_s"] < a["end_s"]
    ) // 2

    refs = os.path.join(OUT_ROOT, "turns.tsv")
    with open(refs, "w", encoding="utf-8") as handle:
        handle.write("turn\ttrack\tspeaker\tstart_s\tend_s\tlanguage\tsession\treference\n")
        for turn in turns:
            handle.write("\t".join(str(turn[k]) for k in
                                   ("turn", "track", "speaker", "start_s", "end_s",
                                    "language", "session", "reference")) + "\n")

    minutes = longest / TARGET_SR / 60.0
    per_track = {name: sum(1 for t in turns if t["track"] == name) for name in writers}
    print(f"  {len(turns)} turns over {minutes:.1f} min  {per_track}")
    print(f"  cross-track overlaps (both speaking): {overlaps}")
    if shifted:
        print(f"  same-speaker overlaps shifted rather than mixed: {shifted}")
    print(f"  -> {os.path.relpath(OUT_ROOT, REPO_ROOT)}/track_*.wav, turns.tsv")
    return turns


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=60.0,
                        help="stop once track A reaches this length")
    parser.add_argument("--session-gap-seconds", type=float, default=5.0,
                        help="silence inserted between sessions. Gaps *within* a session are the "
                             "corpus's own and are preserved, including overlaps")
    parser.add_argument("--allow-download", action="store_true",
                        help="off by default: TLS interception has failed mid-build here")
    args = parser.parse_args()

    print(f"Building from {DATASET} — original timeline preserved from filenames")
    build(args.minutes, args.session_gap_seconds, offline=not args.allow_download)


if __name__ == "__main__":
    main()
