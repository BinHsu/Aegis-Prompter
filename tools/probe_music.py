#!/usr/bin/env python3
"""Does music — especially music with a voice in it — become an utterance? The V41 question.

**V41 has been open since 2026-08-11 and was never tested.** The model shipping at the time
advertised singing and music-with-backing-track as *supported input*, which is the opposite of
what this product wants: **R37** says non-speech must not become an utterance, and **REQUIREMENTS**
names the concrete failure — *"a Spotify track becomes lyrics attributed to `Participant`"*. The
operator decided on 2026-08-11 not to test real music, and that was recorded as **an accepted risk,
not evidence of safety**.

Two things changed on 2026-08-17 and together they reopen it:

- The ASR model was replaced on supply-chain grounds (`docs/decisions/0012`), so whatever was
  assumed about the old model's music behaviour describes nothing that ships.
- **V72** measured the replacement producing text on 252 of 253 real non-speech segments. A model
  that invents an utterance from room tone is not going to stay silent through a song.

**Why the existing fixtures cannot answer this.** `fixtures/asr/nonspeech/music/` is
`layered_tones.wav` and `noise_bed.wav` — programmatic sine stacks from `gen_asr_fixtures.py`.
They contain no instrument, no rhythm and no voice. **V60** already established that this model
family treats programmatic audio as a different world from a room, so a clean run there is not
evidence about a song. Real recorded music is the only material that answers it.

**Corpus:** MUSAN (`openslr.org/resources/17`), music subset. Its `ANNOTATIONS` files carry a
per-track **vocals** flag, which is the split that matters here: an instrumental piece becoming
text is bad, and a *sung* line becoming text attributed to a participant is the failure the
product cannot absorb. The flag is parsed rather than assumed — the parse is printed so it can be
checked against the file.

**What would refute the concern:** text on few or no music segments, and in particular no
*lyrics-shaped* output from the vocal tracks. Stated before the run so the result cannot be
narrated either way afterwards.

⚠️ **Level is a confound and is not controlled here.** MUSAN tracks arrive at their own
loudness, and how loudly a track reaches the tap depends on the far end's volume, the meeting
app's processing, and **V62**'s leakage path. This measures *whether the model invents speech from
music*, not *how likely that is in your room*.

Run (after `rm -rf .corpora-bakeoff` to discard the corpus):
    PYTHONPATH="$PWD" .venv/bin/python tools/probe_music.py --musan .corpora-bakeoff/musan
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
from asr_eval import load_wav_mono_float32  # noqa: E402

FIXTURE_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr")


# Read from the corpus on 2026-08-17, not from memory. The layout is
#     <track id> <genre[,subgenre]> <Y|N vocals> <source> [<composer>]
# e.g. `music-fma-0026 blues Y Cullah` and
#      `music-hd-0039 westernart,romantic N Kevin_MacLoad Erik_Satie`.
#
# **The first version of this looked for a column that was exactly `0` or `1`** -- a guess, written
# before the corpus finished downloading. It would have matched nothing, marked every track
# `unknown`, collapsed the vocal/instrumental split, and produced a table that answered a different
# question than V41 asks while looking entirely well-formed. Checked against the file before the
# run rather than after it: the archive stores `music/` first, so the annotations were readable
# from a partial download.
VOCALS_TOKENS = {"Y": True, "N": False, "1": True, "0": False}


def parse_annotations(music_root):
    """`{track id: has_vocals}` from MUSAN's per-directory ANNOTATIONS files.

    A line that does not carry exactly one recognisable flag yields `None` -- `unknown` -- rather
    than being guessed into a bucket. A wrong split would put sung tracks in the instrumental
    column, which is the one error this probe could not detect from its own output.
    """
    vocals = {}
    for dirpath, _dirnames, filenames in os.walk(music_root):
        if "ANNOTATIONS" not in filenames:
            continue
        with open(os.path.join(dirpath, "ANNOTATIONS"), encoding="utf-8",
                  errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 2:
                    continue
                flags = [p for p in parts[1:] if p in VOCALS_TOKENS]
                vocals[parts[0]] = VOCALS_TOKENS[flags[0]] if len(flags) == 1 else None
    return vocals


def collect_clips(music_root, vocals, per_class, seconds):
    """Deterministic pick, **stratified across MUSAN's five sources**.

    Deterministic because a fixed sort is auditable and these scripts cannot seed randomness
    reproducibly. Stratified because the obvious version -- sorted order, first `per_class` --
    drew all 25 instrumentals from `fma` alone, and MUSAN's sources are not interchangeable:
    `hd-classical` is high-definition orchestral, `rfm` is production library, `jamendo` is
    self-released pop. A single-source sample would answer "does the model hallucinate over *this
    label's* recordings", which is not the question. Round-robin over directories, then truncate.
    """
    buckets = collections.defaultdict(lambda: collections.defaultdict(list))
    for dirpath, _dirnames, filenames in os.walk(music_root):
        source = os.path.basename(dirpath)
        for name in sorted(filenames):
            if not name.endswith(".wav"):
                continue
            track = os.path.splitext(name)[0]
            flag = vocals.get(track)
            label = {True: "vocal", False: "instrumental"}.get(flag, "unknown")
            buckets[label][source].append((track, os.path.join(dirpath, name)))

    picked = []
    totals = {}
    for label in sorted(buckets):
        sources = sorted(buckets[label])
        totals[label] = sum(len(buckets[label][s]) for s in sources)
        taken, index = [], 0
        while len(taken) < per_class and any(index < len(buckets[label][s]) for s in sources):
            for source in sources:
                if index < len(buckets[label][source]) and len(taken) < per_class:
                    taken.append(buckets[label][source][index])
            index += 1
        picked.extend((label, track, path, seconds) for track, path in taken)
    return picked, totals


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--musan", default=os.path.join(REPO_ROOT, ".corpora-bakeoff", "musan"),
                        help="Extracted MUSAN root (the directory containing `music/`)")
    parser.add_argument("--model", default="mlx-community/whisper-large-v3-turbo")
    parser.add_argument("--per-class", type=int, default=25,
                        help="Tracks per class. 25 vocal + 25 instrumental is enough to separate "
                             "'never' from 'routinely', which is the question")
    parser.add_argument("--seconds", type=float, default=30.0,
                        help="Seconds taken from the start of each track")
    parser.add_argument("--hf-home", default=os.path.join(REPO_ROOT, ".hf_cache-bakeoff"))
    parser.add_argument("--out", default=os.path.join(FIXTURE_ROOT, "results", "music_probe.json"))
    args = parser.parse_args()

    music_root = os.path.join(args.musan, "music")
    if not os.path.isdir(music_root):
        print(f"No music corpus at {music_root}. Fetch MUSAN first:\n"
              f"  curl -L -o .corpora-bakeoff/musan.tar.gz "
              f"https://openslr.org/resources/17/musan.tar.gz\n"
              f"  tar -xzf .corpora-bakeoff/musan.tar.gz -C .corpora-bakeoff", file=sys.stderr)
        return 2

    vocals = parse_annotations(music_root)
    known = sum(1 for v in vocals.values() if v is not None)
    print(f"annotations: {len(vocals)} tracks, {known} with a usable vocals flag")

    clips, totals = collect_clips(music_root, vocals, args.per_class, args.seconds)
    print(f"corpus by class: {totals}")
    print(f"scoring {len(clips)} clips x {args.seconds:g}s")

    harness._boot_hf_home(args.hf_home, offline=True)
    import numpy as np

    kind = harness.backend_kind_for(args.model)
    transcribe = harness.make_transcribe_fn(kind, args.model, harness.resolve_qwen_backend())
    from text_filters import is_acceptable

    per_class = collections.defaultdict(lambda: {"segments": 0, "text": 0, "buffer": 0})
    rows = []
    for label, track, path, seconds in clips:
        try:
            samples, rate = load_wav_mono_float32(path)
        except Exception as exc:
            print(f"  !! unreadable {track}: {type(exc).__name__}", file=sys.stderr)
            continue
        audio = np.asarray(samples, dtype=np.float32)[: int(16000 * seconds)]
        for index, chunk in enumerate(harness.vad_speech_segments(audio)):
            text = transcribe(chunk)
            stats = per_class[label]
            stats["segments"] += 1
            if text:
                stats["text"] += 1
                kept = is_acceptable(text)
                if kept:
                    stats["buffer"] += 1
                rows.append({"class": label, "track": track, "segment": index,
                             "text": text, "reaches_buffer": kept})
                print(f"  [{label:<12}] {track}#{index}: {text!r}", flush=True)

    print(f"\n| Class | VAD segments | produced text | reached the buffer |")
    print("|---|---|---|---|")
    for label in sorted(per_class):
        s = per_class[label]
        print(f"| {label} | {s['segments']} | {s['text']} | {s['buffer']} |")
    print("\nA sung line reaching the buffer is attributed to `Participant` and can fire a "
          "defensive cue. That is the R37 failure REQUIREMENTS names explicitly.")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"model": args.model, "seconds": args.seconds,
                   "per_class": dict(per_class), "lines": rows}, handle,
                  ensure_ascii=False, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
