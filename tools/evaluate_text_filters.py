#!/usr/bin/env python3
"""What does a text-side filter remove, and what does it destroy? Scored on already-collected data.

**V77 closed the audio side.** Every lever there — checkpoint, `no_speech_threshold`,
`logprob_threshold`, temperature — decides *whether to decode at all*, and the false-line and
real-speech populations overlap (**V76**), so they move together: reaching 39 of 253 on non-speech
cost **92 of 204** real degraded utterances. Under **V64** that is the wrong trade, because a
destroyed answer costs the record.

**A text-side filter is the only kind that can separate them**, because it reads what was produced
rather than deciding whether to produce it. This scores candidates against the corpora already
collected, so it needs **no GPU and no new inference** — the model has already spoken, and the
question is only what to do with what it said.

**Three populations, from a probe JSONL:**

- `nonspeech` — 253 segments of genuine non-speech. Text here is invented. **Removing it is the
  win.**
- `degraded-speech` — 204 segments of real speech, attenuated, overlapped or obscured. A quiet
  witness, a bad line, a gallery. **Removing it is the cost**, and **V64** says this cost is the
  larger one.
- `control` — clean real speech. **Removing any of it is a disqualifying failure**, not a cost.

**The candidates, and what each is betting on:**

| Filter | Bet |
|---|---|
| `shipping` | the length guard alone — today's behaviour, the baseline every other row is read against |
| `blacklist` | the emptied `HALLUCINATION_PHRASES` was right and its model came back (**V72**) |
| `script` | ghosts arrive in languages this deployment does not use — Cyrillic, Hangul, kana (**R8** draws that boundary) |
| `repetition` | `MMMMM…`, `Ha ha ha…`, `Cough, cough…` are a shape, not a vocabulary, so a rule reaches them where a list cannot |
| `script+repetition` | the two above compose without overlapping |
| `all` | everything at once, to see whether the costs add up or the wins do |

**What would refute the text-side hypothesis:** a filter that removes a useful share of `nonspeech`
while also removing `degraded-speech` at a comparable rate. That would mean text separates the
populations no better than audio did, and the search is over rather than merely moved.

Run:
    PYTHONPATH="$PWD" .venv/bin/python tools/evaluate_text_filters.py \\
        fixtures/asr/results/20260817-model-swap/E3_nonspeech_real_turbo.jsonl
"""

import argparse
import collections
import json
import os
import re
import sys
import unicodedata

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from probe_nonspeech_real import bucket_of  # noqa: E402

# The list as it stood before 2026-08-12, when it was emptied because the model then shipping
# produced none of these. `docs/decisions/0009` records the deletion; **V72** records that the
# model now shipping produces several of them routinely.
FORMER_BLACKLIST = ["字幕", "Subtitles", "Amara.org", "請訂閱", "Thank you.", "謝謝",
                    "I don't know.", "Bye."]

# **A denylist of scripts, not an allowlist** -- and that choice was forced by getting it wrong.
# The first version allowed `("LATIN", "HAN", …)` and checked `unicodedata.name(ch)`, but Chinese
# characters are named `CJK UNIFIED IDEOGRAPH-XXXX`, not `HAN…`. Every Chinese line was therefore
# judged foreign, and the filter destroyed **9 of 10 clean control clips** on its first run. An
# allowlist fails *closed* on anything it forgot to name, which for a bilingual product is the
# whole Chinese half; a denylist fails *open*, which for a filter whose job is discarding text is
# the safe direction. Caught 2026-08-18 by the clean-speech column, which exists to be
# disqualifying.
#
# These are the scripts appearing in the model's invented output (**V72**) and in no meeting this
# product is built for. **R8** scopes the product to Mandarin and English.
FOREIGN_SCRIPTS = ("CYRILLIC", "HANGUL", "HIRAGANA", "KATAKANA", "ARABIC", "HEBREW", "THAI",
                   "DEVANAGARI", "GREEK", "ARMENIAN", "GEORGIAN", "BENGALI", "TAMIL", "TELUGU",
                   "MYANMAR", "KHMER", "LAO", "ETHIOPIC")


def foreign_script_chars(text):
    """Characters belonging to a script this deployment does not use."""
    out = []
    for ch in text or "":
        if ch.isspace() or not ch.isalpha():
            continue
        try:
            name = unicodedata.name(ch)
        except ValueError:
            continue
        if any(name.startswith(s) for s in FOREIGN_SCRIPTS):
            out.append(ch)
    return out


def is_repetitive(text, min_len=24, ratio=0.34):
    """Whether a string is mostly one repeated unit.

    Two shapes, because the corpus contains both: a single character run (`MMMMM…`, `Rrrrr…`) and
    a repeated token or phrase (`Ha ha ha…`, `Cough, cough…`, `I'm going to go to bed.` x8). The
    threshold is on **distinct content over length**, which is the same idea as Whisper's own
    `compression_ratio_threshold` but applied to the text that survived rather than used to decide
    whether to emit it.
    """
    s = (text or "").strip()
    if len(s) < min_len:
        return False
    if len(set(s.replace(" ", ""))) <= 3:          # MMMMM…, ……, Rrrrr…
        return True
    words = re.findall(r"\w+", s.lower())
    if len(words) >= 6 and len(set(words)) / len(words) <= ratio:
        return True
    sentences = [x.strip() for x in re.split(r"(?<=[.!?。！？])\s*", s) if x.strip()]
    return len(sentences) >= 3 and len(set(sentences)) <= max(1, len(sentences) // 3)


def make_filters():
    """`{name: predicate(text) -> keep?}`. Every one includes the shipping length guard."""
    from text_filters import is_acceptable, normalize_phrase

    normalised_blacklist = {normalize_phrase(p) for p in FORMER_BLACKLIST}

    def shipping(t):
        return is_acceptable(t)

    def blacklist(t):
        return is_acceptable(t) and normalize_phrase(t) not in normalised_blacklist

    def script(t):
        return is_acceptable(t) and not foreign_script_chars(t)

    def repetition(t):
        return is_acceptable(t) and not is_repetitive(t)

    return {
        "shipping": shipping,
        "blacklist": blacklist,
        "script": script,
        "repetition": repetition,
        "script+repetition": lambda t: script(t) and repetition(t),
        "all": lambda t: blacklist(t) and script(t) and repetition(t),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", nargs="+", help="probe output(s) from probe_nonspeech_real.py")
    parser.add_argument("--pass-no", type=int, default=0)
    parser.add_argument("--show", type=int, default=6,
                        help="Examples of real speech each filter destroys — the column that "
                             "decides whether it may ship")
    args = parser.parse_args()

    for path in args.jsonl:
        rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
        rows = [r for r in rows if r["pass"] == args.pass_no and r.get("text")]
        pops = collections.defaultdict(list)
        for row in rows:
            pops[bucket_of(row)].append(row["text"])

        print(f"\n=== {os.path.basename(path)} (pass {args.pass_no}) ===")
        print(f"non-speech lines {len(pops['nonspeech'])}, "
              f"degraded real speech {len(pops['degraded-speech'])}, "
              f"clean speech {len(pops['control'])}")
        print(f"\n| Filter | ghosts removed | real degraded speech destroyed | clean speech "
              f"destroyed |")
        print("|---|---|---|---|")
        filters = make_filters()
        for name, keep in filters.items():
            ghosts = sum(1 for t in pops["nonspeech"] if not keep(t))
            degraded = sum(1 for t in pops["degraded-speech"] if not keep(t))
            clean = sum(1 for t in pops["control"] if not keep(t))
            g, d, c = len(pops["nonspeech"]), len(pops["degraded-speech"]), len(pops["control"])
            print(f"| {name} | {ghosts}/{g} ({100*ghosts/max(g,1):.0f}%) | "
                  f"{degraded}/{d} ({100*degraded/max(d,1):.0f}%) | {clean}/{max(c,1)} |")

        for name, keep in filters.items():
            destroyed = [t for t in pops["degraded-speech"] + pops["control"] if not keep(t)]
            if destroyed and name != "shipping":
                print(f"\n  {name} — real speech it would destroy ({len(destroyed)}):")
                for t in destroyed[: args.show]:
                    print(f"    {t[:100]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
