#!/usr/bin/env python3
"""On speakers, how much of the far party lands in the Operator track — with ground truth this time.

**V70** measured this on 2026-08-12 and it is the reason the real-meeting validation is required
to run on headphones: on speakers, **61%** of microphone lines were the remote party's speech with
degraded wording, wearing the operator's label. **R2** is not violated — each line is correctly
attributed to the source that produced it — which is precisely what makes it dangerous: the label
is right and the content is wrong.

Two reasons to run it again on 2026-08-17:

- **The model changed** (`docs/decisions/0012`), and **V72** measured the replacement producing
  text on 252 of 253 real non-speech segments. A model that eager on noise will not be *less* eager
  on an attenuated, room-reflected copy of someone else's voice.
- **V70's method could not separate degradation from error.** It compared the microphone's
  transcript against the *tap's* transcript — two ASR outputs, neither of them ground truth — so
  "degraded wording" mixed leakage damage with whatever both sides got wrong anyway.

**This plays a fixture whose reference text is known**, so the comparison is against what was
actually said rather than against another transcript. `fixtures/asr/conversation/track_B.wav` is
the far-side track and `turns.tsv` is its ground truth.

**What would refute the concern:** the microphone produces few lines, or lines whose CER against
the played reference is so high they could not be mistaken for a record of the conversation.
A *low* CER is the bad outcome here — it means the far party's words are landing in the operator's
track legibly enough to be believed.

⚠️ **Uncontrolled, and named so nobody reads the number as a room-independent constant:** speaker
volume, room acoustics, mic AGC, the distance between the two, and whatever else is audible. This
answers *whether the mechanism reproduces on the new model and roughly how strongly*, not *what
your room will do*.

⚠️ **This records the room.** It writes only under `fixtures/asr/results/` (gitignored) and never
under `history/`, `context/` or `logs/`. Run it when the room is yours.

**Not a duplicate of `tools/soak_capture.py --microphone`, and the difference is the whole point.**
That tool plays audio and opens the microphone too, and it is the better tool for its own question:
**does the device path survive an hour**. It says so outright — *"expect a poor transcript on the
Speaker track, and do not treat that as the result"* — because a poor transcript answers durability
as well as a good one does. This asks the opposite question: **how legible is what leaked**, scored
against the reference text of what was actually played. A transcript that is poor *enough* is
harmless; **V70**'s finding is that it is not poor enough. Run the soak for durability, this for
**R2**'s meaning problem. If they are ever merged, the merged thing must keep both stopping rules,
because they stop for opposite reasons.

Run:
    PYTHONPATH="$PWD" .venv/bin/python tools/measure_speaker_leakage.py --minutes 3
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

CONV_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr", "conversation")
RESULTS = os.path.join(REPO_ROOT, "fixtures", "asr", "results")


class CollectingBuffer:
    """The only thing `Transcriber` needs from a buffer: somewhere to put a line.

    A stub rather than the real `DialogueBuffer` on purpose — the real one evaluates threats and
    holds locks, none of which is under test here, and importing it would drag advisor state into
    a measurement about acoustics.
    """

    def __init__(self):
        self.lines = []
        self._lock = threading.Lock()

    def add_entry(self, role, text):
        with self._lock:
            self.lines.append((time.monotonic(), role, text))


def bucket_reference(start_s, end_s, track="B"):
    """Ground truth for one time bucket, so a scoring error stays inside its own minute."""
    spoken = []
    with open(os.path.join(CONV_ROOT, "turns.tsv"), encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["track"] == track and start_s <= float(row["start_s"]) < end_s:
                spoken.append(row["reference"])
    return " ".join(spoken)


def reference_text(until_s, track="B"):
    """Ground truth for the portion of the fixture that was actually played."""
    spoken = []
    with open(os.path.join(CONV_ROOT, "turns.tsv"), encoding="utf-8") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["track"] == track and float(row["start_s"]) < until_s:
                spoken.append(row["reference"])
    return " ".join(spoken)


def set_volume(level):
    """Set output volume, returning the previous value so it can be put back.

    Restored in a `finally` — leaving someone's machine at a volume they did not choose is a
    side effect a measurement has no business having.
    """
    try:
        previous = subprocess.run(["osascript", "-e", "output volume of (get volume settings)"],
                                  capture_output=True, text=True, timeout=10).stdout.strip()
        subprocess.run(["osascript", "-e", f"set volume output volume {level}"], timeout=10)
        return int(previous) if previous.isdigit() else None
    except Exception as exc:
        print(f"  !! could not set volume ({type(exc).__name__}); using whatever is set",
              file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=3.0,
                        help="V70 used ten. Three is enough to separate 'a few stray lines' from "
                             "'most of the track', which is the question")
    parser.add_argument("--volume", type=int, default=50,
                        help="Output volume 0-100, restored afterwards")
    parser.add_argument("--model", default="")
    parser.add_argument("--out", default=os.path.join(RESULTS, "speaker_leakage.json"))
    args = parser.parse_args()

    wav = os.path.join(CONV_ROOT, "track_B.wav")
    if not os.path.exists(wav):
        print(f"No {wav}. Run tools/build_conversation_fixture.py first.", file=sys.stderr)
        return 2

    import bootstrap
    settings = bootstrap.read_settings()
    bootstrap.apply_environment(settings)
    bootstrap.enforce_offline()
    model = args.model or (settings.get("ASR_MODEL") or "").strip() \
        or bootstrap.FIELDS_BY_KEY["ASR_MODEL"].default

    import transcriber as tr
    from score_real_fixtures import cer

    seconds = args.minutes * 60
    buffer = CollectingBuffer()
    print(f"model={model}")
    print(f"playing {os.path.basename(wav)} through the speakers for {args.minutes:g} min, "
          f"capturing on the default input")

    index, name = tr.Transcriber.resolve_input_device(None)
    print(f"input: [{index}] {name}")

    capture = tr.Transcriber(index, "Speaker (You)", buffer, model_path=model, device_name=None)
    previous_volume = set_volume(args.volume)
    player = None
    started = time.monotonic()
    try:
        capture.start()
        started = time.monotonic()
        player = subprocess.Popen(["afplay", wav],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and player.poll() is None:
            time.sleep(1.0)
            done = len(buffer.lines)
            remaining = deadline - time.monotonic()
            print(f"\r  {remaining:5.0f}s left, {done:3d} lines captured", end="", flush=True)
        print()
    finally:
        if player is not None and player.poll() is None:
            player.terminate()
        capture.stop()
        if previous_volume is not None:
            set_volume(previous_volume)
            print(f"volume restored to {previous_volume}")

    # How long audio was actually playing, not how long it was asked to. `afplay` reaching the end
    # of the file, or being terminated early, both land here rather than in an assumed constant.
    played = time.monotonic() - started

    # **Scored in 60-second buckets, not as one string.** The first version concatenated the whole
    # run and took a single Levenshtein against the whole reference, and at ten minutes that
    # reported CER 0.57 against 0.27 at three -- an artefact, not a finding. `measure_segmentation`
    # already warned why: one alignment over ten thousand characters is "dominated by one early
    # insertion", so any drift between the played position and the reference window compounds
    # instead of staying local. Buckets keep a mistake inside its own minute.
    reference = reference_text(min(seconds, played))
    hypothesis = " ".join(text for _t, _role, text in buffer.lines)
    score = cer(reference, hypothesis)

    buckets = []
    for start in range(0, int(min(seconds, played)), 60):
        ref = bucket_reference(start, start + 60)
        hyp = " ".join(t for offset, _role, t in buffer.lines
                       if start <= offset - started < start + 60)
        value = cer(ref, hyp)
        if value is not None:
            buckets.append(round(value, 4))
    bucketed = round(sum(buckets) / len(buckets), 4) if buckets else None

    print(f"\nlines the microphone produced: {len(buffer.lines)}")
    print(f"CER, mean of 60s buckets (the figure to quote): "
          f"{bucketed}  from {len(buckets)} buckets")
    print(f"CER, whole run as one string (kept for comparison, degrades with length): "
          f"{score if score is None else round(score, 4)}")
    print("A LOW number here is the bad outcome: it means the far party's words are landing in "
          "the operator's track legibly enough to be believed (V70, R2).")
    for _t, role, text in buffer.lines[:12]:
        print(f"  [{role}] {text}")

    os.makedirs(RESULTS, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"model": model, "minutes": args.minutes, "volume": args.volume,
                   # Timestamps are kept. The first version stored only the text, so a run could
                   # not be re-scored in buckets afterwards -- the data to fix the metric had been
                   # collected and then thrown away.
                   "lines": [{"at": round(offset - started, 2), "role": role, "text": text}
                             for offset, role, text in buffer.lines],
                   "cer_bucketed_60s": bucketed,
                   "cer_buckets": buckets,
                   "cer_whole_run": score,
                   "reference_chars": len(reference), "played_seconds": played},
                  handle, ensure_ascii=False, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
