#!/usr/bin/env python3
"""What two tracks cost at the pace people actually speak, and what overlap does to it.

**The gap this closes.** Every dual-track figure in `REQUIREMENTS.md` was measured with a
*saturating* feed: **V56** (2.00x), **V57** and **V58** (one hour, three arms each). All four say so
themselves -- V56 calls its number "an upper bound, not the expected cost", V57 adds "this is not
the realistic turn-taking figure", and `fixtures/asr/NPU_LOCK_TRIAL.md` lists it under *left undone
deliberately*, pointing at `--realtime`. A saturating feed keeps an inference in flight on both
tracks at all times, which deletes the one property that makes real conversation cheaper: **people
mostly take turns**, so the other track is usually silent and its VAD sends nothing.

This scorer reads one realtime arm and separates the two costs that the saturating runs had welded
together -- what an inference costs when it runs alone, and what it costs when the other track is
competing for the same accelerator.

**Correcting a claim in `STATE.md`, which is why this fixture needed no rebuilding.** The handoff
said `build_conversation_fixture.py` "lays them out *without* overlap, because the source has
none", and asked for a deliberately colliding variant. Both halves are wrong, and the repo already
contained the refutation: **V57** cites "1130 turns, 480 cross-track overlaps" in this very
fixture, and the builder preserves ASCEND's published offsets exactly -- it shifts only a speaker
overlapping *themselves*, and prints the cross-track count on every build. Measured here from
`turns.tsv`: **480 overlapping pairs, 606.5 s of simultaneous speech, 16.8% of the hour.** The
fixture that exists is the overlap fixture.

**What this run cannot test, stated so the result is not over-read.** The two tracks are separate
WAV files fed to separate `Transcriber` instances. There is no acoustic path between them, so
**V60**'s 2-talker cross-talk -- fluent invented text from *mixed* audio -- cannot occur here and a
clean result is not evidence against it. Under **R2** that is the point: separation is structural,
not something the pipeline has to achieve at runtime. The place cross-talk does reach this product
is the microphone hearing the room, which is **V62**, a different mechanism already measured. The
contamination check below is therefore a falsification attempt against a structural guarantee, not
the headline.

**The latency quantity.** `elapsed_ms` in `transcriber.py` starts before `with NPU_LOCK`, so it is
lock wait *plus* inference -- which is precisely why V56's dual arm read 2.00x. It excludes time
spent in `inference_queue` before the worker picked the segment up, so it is not end-to-end
speech-to-screen. It is the same quantity V51, V52, V55, V56, V57 and V58 report, which is what
makes those tables comparable to this one.

Produce the arm this reads (about 65 minutes -- the feed sleeps in real time):

    .venv-bakeoff/bin/python tools/npu_lock_trial.py --child \\
        --model mlx-community/whisper-large-v3-turbo --hf-home "$PWD/.hf_cache-bakeoff" \\
        --realtime > fixtures/asr/results/overlap_realtime.jsonl

Then score it:

    .venv-bakeoff/bin/python tools/measure_overlap_turns.py
"""

import argparse
import json
import os
import statistics
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

CONV_ROOT = os.path.join(REPO_ROOT, "fixtures", "asr", "conversation")
TURNS = os.path.join(CONV_ROOT, "turns.tsv")
# Named without a model in it since 2026-08-17: the file was `overlap_realtime_qwen.jsonl` and
# the model changed (`docs/decisions/0012`), which would have left a correct measurement sitting
# under a filename asserting the wrong thing.
EVENTS = os.path.join(REPO_ROOT, "fixtures", "asr", "results", "overlap_realtime.jsonl")

# transcriber.py assigns these two roles to the two tracks; npu_lock_trial.py wires A -> Speaker.
TRACK_OF_ROLE = {"Speaker (You)": "A", "Participant": "B"}


def load_turns(path):
    rows = []
    with open(path, encoding="utf-8") as handle:
        header = handle.readline().rstrip("\n").split("\t")
        for line in handle:
            row = dict(zip(header, line.rstrip("\n").split("\t")))
            row["start_s"] = float(row["start_s"])
            row["end_s"] = float(row["end_s"])
            rows.append(row)
    return rows


def load_events(path):
    events = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if raw.startswith("{"):
                try:
                    events.append(json.loads(raw))
                except json.JSONDecodeError:
                    continue
    return events


def merge(intervals):
    """Union of speech intervals on one track, so overlap is measured against sound not turns."""
    out = []
    for start, end in sorted(intervals):
        if out and start <= out[-1][1]:
            out[-1][1] = max(out[-1][1], end)
        else:
            out.append([start, end])
    return out


def intersect(left, right):
    """Regions where both tracks carry speech. Two pointers over two sorted unions."""
    out = []
    i = j = 0
    while i < len(left) and j < len(right):
        lo = max(left[i][0], right[j][0])
        hi = min(left[i][1], right[j][1])
        if lo < hi:
            out.append([lo, hi])
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return out


def describe_fixture(turns):
    """What the fixture actually contains. Reported every run because STATE.md got it wrong."""
    unions = {}
    for track in sorted({t["track"] for t in turns}):
        unions[track] = merge([[t["start_s"], t["end_s"]] for t in turns if t["track"] == track])
    both = intersect(unions["A"], unions["B"]) if len(unions) > 1 else []
    span = max(t["end_s"] for t in turns)
    pairs = sum(
        1 for a in turns for b in turns
        if a["track"] != b["track"] and a["start_s"] < b["end_s"] and b["start_s"] < a["end_s"]
    ) // 2
    return {
        "span_s": span,
        "turns": len(turns),
        "per_track": {k: sum(1 for t in turns if t["track"] == k) for k in unions},
        "speech_s": {k: round(sum(e - s for s, e in v), 1) for k, v in unions.items()},
        "overlap_pairs": pairs,
        "overlap_s": round(sum(e - s for s, e in both), 1),
        "overlap_pct_of_span": round(100.0 * sum(e - s for s, e in both) / span, 1),
    }


def label_contention(lines):
    """Mark each line whose inference window collided with the other track's.

    A line logged at `t` having taken `ms` occupied `[t - ms/1000, t]` waiting for and then holding
    `NPU_LOCK`. If a line on the *other* role occupied an intersecting window, one of the two spent
    part of its latency queued behind the other. That is V56's 2x, observed rather than induced --
    and it needs no mapping from wall clock back to fixture time, so feed drift cannot corrupt it.
    """
    windows = []
    for line in lines:
        windows.append({
            "line": line,
            "role": line["role"],
            "start": line["t"] - line["ms"] / 1000.0,
            "end": line["t"],
        })
    windows.sort(key=lambda w: w["start"])
    for w in windows:
        w["contended"] = False
    for i, a in enumerate(windows):
        for b in windows[i + 1:]:
            if b["start"] >= a["end"]:
                break
            if b["role"] != a["role"]:
                a["contended"] = True
                b["contended"] = True
    return windows


def stats(values):
    if not values:
        return None
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[max(0, int(len(ordered) * 0.95) - 1)],
        "max": ordered[-1],
    }


def row(label, s):
    if not s:
        return f"| {label} | 0 | — | — | — |"
    return (f"| {label} | {s['n']} | {s['median']:.0f} | {s['p95']:.0f} | {s['max']:.0f} |")


def contamination(lines, turns):
    """Falsification attempt against R2: does a track's transcript carry the other's words?

    Character 5-grams from the other track's reference that appear **nowhere** in this track's own
    reference. Both tracks are the same two people on the same topics, so shared vocabulary is
    expected and only the exclusive n-grams can carry evidence.

    Reported with a control, because a hit rate alone is unreadable: the same count computed
    against this track's *own* exclusive n-grams is the ceiling a perfect transcript would reach,
    and the gap between them is what "leaked" would have to beat. With separate WAV files a
    non-zero foreign rate means coincidence -- shared idiom, filler, a common name -- not leakage.
    """
    from score_real_fixtures import normalise

    ref_of = {}
    for track in sorted({t["track"] for t in turns}):
        ref_of[track] = normalise(" ".join(t["reference"] for t in turns if t["track"] == track))

    def grams(text, n=5):
        return {text[i:i + n] for i in range(max(0, len(text) - n + 1))}

    out = {}
    for role, track in TRACK_OF_ROLE.items():
        other = "B" if track == "A" else "A"
        if track not in ref_of or other not in ref_of:
            continue
        hyp = normalise(" ".join(l["text"] for l in sorted(
            (l for l in lines if l["role"] == role), key=lambda l: l["t"])))
        hyp_grams = grams(hyp)
        own = grams(ref_of[track])
        foreign = grams(ref_of[other])
        own_only = own - foreign
        foreign_only = foreign - own
        out[track] = {
            "own_only_total": len(own_only),
            "own_only_hit": len(own_only & hyp_grams),
            "foreign_only_total": len(foreign_only),
            "foreign_only_hit": len(foreign_only & hyp_grams),
        }
        out[track]["own_rate"] = (100.0 * out[track]["own_only_hit"] / len(own_only)) if own_only else None
        out[track]["foreign_rate"] = (100.0 * out[track]["foreign_only_hit"] / len(foreign_only)) if foreign_only else None
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--events", default=EVENTS)
    parser.add_argument("--turns", default=TURNS)
    parser.add_argument("--sleep-seconds", type=float, default=0.0,
                        help="Seconds the machine was asleep during the run, subtracted before "
                             "computing pace. Get it from `pmset -g log | grep -E "
                             "'Clamshell|Wake from'`. A closed lid once turned a near-realtime "
                             "feed into an apparent 2.3x slowdown here")
    args = parser.parse_args()

    if not os.path.exists(args.events):
        print(f"No events at {args.events} — run the arm first (see the module docstring).",
              file=sys.stderr)
        return 1

    turns = load_turns(args.turns)
    events = load_events(args.events)
    lines = [e for e in events if e.get("event") == "line"]
    if not lines:
        print("The arm produced no transcribed lines; nothing to score.", file=sys.stderr)
        return 1

    fixture = describe_fixture(turns)
    warm = next((e["t"] for e in events if e.get("event") == "warm"), 0.0)
    done = next((e["t"] for e in reversed(events) if e.get("event") == "done"), None)
    last = max(l["t"] for l in lines)
    complete = any(e.get("event") == "done" for e in events)

    print("## The fixture, measured rather than described\n")
    print(f"- span **{fixture['span_s'] / 60:.1f} min**, **{fixture['turns']} turns** "
          f"{fixture['per_track']}")
    print(f"- speech per track (union of turns): {fixture['speech_s']} s")
    print(f"- **cross-track overlap: {fixture['overlap_pairs']} turn pairs, "
          f"{fixture['overlap_s']} s, {fixture['overlap_pct_of_span']}% of the span**")
    print("\nSTATE.md's handoff said this fixture carries no overlap and asked for a colliding "
          "variant. It collides already; V57 recorded the same 480 pairs.")

    print("\n## Pace — was this actually realtime?\n")
    # `t` is WALL CLOCK since the child started, not a position in the fixture. Confirmed against
    # `ps` ELAPSED. Reading it as fixture position is the mistake this section used to make, and it
    # flatters a slow feed: a run at a third of real time looks "a third done" instead of "3x slow".
    print(f"- warm at **{warm:.1f} s**; last line at wall **{last:.1f} s**"
          + (f"; child finished at wall **{done:.1f} s**" if done else " (child still running)"))
    if complete:
        wall = done or last
        # Elapsed includes any time the machine was ASLEEP, which is not the feed running slowly.
        # A closed lid produced an 80-minute stall in the first run of this measurement and made a
        # near-realtime feed read as 2.3x slow. Subtract it; `--sleep-seconds` comes from
        #   pmset -g log | grep -E "Clamshell|Wake from"
        awake = max(1e-9, wall - max(0.0, args.sleep_seconds))
        pace = fixture["span_s"] / awake
        if args.sleep_seconds:
            print(f"- wall {wall:.0f} s minus **{args.sleep_seconds:.0f} s asleep** = "
                  f"**{awake:.0f} s awake**")
        print(f"- {fixture['span_s']:.0f} s of audio in {awake:.0f} s awake = **{pace:.3f}x**")
        # 0.888x is this machine's measured ceiling for a flat sleep(0.03) per 30 ms frame, so a
        # feed sitting there is as fast as the current loop can go, not a feed in trouble.
        if pace >= 0.85:
            print(f"- ✅ at or near the **0.888x** ceiling a flat `sleep(0.03)` per frame imposes "
                  f"(measured standalone on this machine). Contention is under-represented by "
                  f"roughly {(1.0 / pace - 1) * 100:.0f}%, not by a factor.")
        else:
            print(f"- ⚠️ **{1.0 / pace:.1f}x slower than realtime even excluding sleep.** Both "
                  f"tracks slow equally so the overlap structure survives, but inference duration "
                  f"does not slow — the accelerator gets that much more slack per unit of audio "
                  f"than reality, so segments that would collide in real time have room here. "
                  f"**Check `pmset -g log` for sleep before reading this as feed behaviour.** CER "
                  f"and completeness are unaffected either way.")
    else:
        print(f"- **still running — {last:.0f} s of wall clock so far.** How far into the fixture "
              f"that is cannot be read off `t`; match a recent line's text against `turns.tsv` to "
              f"find the true position, then divide by wall to get the pace.")
        print("\n⚠️ **Partial log.** Latency and contention below hold for what has run — both are "
              "computed per line and need no completed timeline. **Completeness and CER are "
              "withheld**, because a partial transcript against the full hour's reference reports "
              "a number that looks like accuracy and is not.")

    print("\n## What overlap costs — latency by observed contention\n")
    windows = label_contention(lines)
    print("| Arm | n | median ms | p95 | max |")
    print("|---|---|---|---|---|")
    print(row("**all lines**", stats([w["line"]["ms"] for w in windows])))
    print(row("solo (no other-track inference in flight)",
              stats([w["line"]["ms"] for w in windows if not w["contended"]])))
    print(row("contended (competing for NPU_LOCK)",
              stats([w["line"]["ms"] for w in windows if w["contended"]])))
    for role in sorted({w["role"] for w in windows}):
        print(row(f"— {role}, solo",
                  stats([w["line"]["ms"] for w in windows if w["role"] == role and not w["contended"]])))
        print(row(f"— {role}, contended",
                  stats([w["line"]["ms"] for w in windows if w["role"] == role and w["contended"]])))

    contended = sum(1 for w in windows if w["contended"])
    print(f"\n- **{contended} of {len(windows)} lines ({100.0 * contended / len(windows):.1f}%) "
          f"were contended.** The fixture is {fixture['overlap_pct_of_span']}% simultaneous speech.")
    solo = stats([w["line"]["ms"] for w in windows if not w["contended"]])
    both = stats([w["line"]["ms"] for w in windows if w["contended"]])
    if solo and both and solo["median"]:
        print(f"- contended / solo median = **{both['median'] / solo['median']:.2f}x** "
              f"(V56 measured **2.00x** with both tracks saturated)")

    if not complete:
        print("\n## Completeness (R3) and accuracy\n")
        print("Withheld until the arm finishes — see the warning above.")
        return 0

    print("\n## Completeness (R3)\n")
    print("| Track | reference turns | lines emitted | lines/turn |")
    print("|---|---|---|---|")
    for role, track in sorted(TRACK_OF_ROLE.items(), key=lambda kv: kv[1]):
        n_turns = fixture["per_track"].get(track, 0)
        n_lines = sum(1 for l in lines if l["role"] == role)
        ratio = f"{n_lines / n_turns:.2f}" if n_turns else "—"
        print(f"| {track} ({role}) | {n_turns} | {n_lines} | {ratio} |")
    print("\nSegments group turns, so this is not a per-turn recall — a ratio below 1 mixes "
          "merged turns with dropped ones and only bounds the loss.")

    print("\n## Accuracy against the fixture's own reference\n")
    from npu_lock_trial import score_against_reference
    scored = score_against_reference(lines, turns)
    print("| Track | CER vs reference |")
    print("|---|---|")
    for track in sorted(scored):
        print(f"| {track} | {scored[track]:.3f} |")

    print("\n## R2 falsification attempt — cross-track contamination\n")
    print("| Track | own-only 5-grams recalled | other track's exclusive 5-grams present |")
    print("|---|---|---|")
    for track, c in sorted(contamination(lines, turns).items()):
        own = f"{c['own_only_hit']}/{c['own_only_total']} ({c['own_rate']:.1f}%)" if c["own_rate"] is not None else "—"
        foreign = f"{c['foreign_only_hit']}/{c['foreign_only_total']} ({c['foreign_rate']:.1f}%)" if c["foreign_rate"] is not None else "—"
        print(f"| {track} | {own} | {foreign} |")
    print("\nSeparate WAV files and separate `Transcriber` instances leave no acoustic path, so a "
          "low foreign rate confirms the plumbing and says nothing about V60's mixed-audio "
          "cross-talk. See the module docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
