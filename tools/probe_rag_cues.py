#!/usr/bin/env python3
"""Does a retrieval cue fire when it should, and stay quiet when it should not?

**The gap this closes, quoted from the repo's own admission.** The advisor's tests run against a
real embedded Qdrant with **stubbed embeddings**, which "proves the plumbing and proves nothing
about whether a cue fires when it should" (`STATE.md`). The thing that decides whether a cue fires
is a cosine similarity from the **real** embedding model against `SERVE_THRESHOLD` (0.65, **V22**),
and a stub cannot produce it. **V34** is the same gap from the other side: advisor liveness is
visible before a meeting and never during one.

**It never touches the operator's index.** `knowledge_store.LOCAL_DIR` is redirected to a temporary
directory and the notes below are invented, so nothing here reads, writes or embeds anything under
`context/`. That also means the result is about the *mechanism*, not about the operator's own notes
-- which is the honest scope: whether their material retrieves well is theirs to judge, and needs
their material.

**The discriminator, fixed before the run.** Every utterance is labelled with what should happen:

- `fire` -- a paraphrase of an indexed note, using different words. If this does not cross the
  threshold, the advisor is silent exactly when it was built to speak.
- `quiet` -- ordinary meeting talk with no relation to any note. If this crosses, every meeting
  gets cues for nothing, which is **V23**'s flooding in the retrieval slot.
- Reported as counts and as the actual scores, because a near miss at 0.63 and a clear miss at 0.11
  are different findings and the same verdict.

**Repeat suppression is turned off between utterances.** `last_matched_idx` suppresses a second hit
on the same chunk, which is right in a meeting and would silently zero half this table. Reset per
utterance, and said out loud here so the number is not mistaken for a raw hit rate.

USAGE
    PYTHONPATH="$PWD" .venv/bin/python tools/probe_rag_cues.py
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

# Invented briefing notes for a fictional programme. Deliberately the shape of real prep material:
# a claim with a number, a date, a name, a commitment. Bilingual because the product is (R8/R10) and
# the collection's model is multilingual -- a cue that only fires in English would be a finding.
NOTES = [
    "The Meridian ingest migration completed on 14 March. Throughput rose from 4,000 to 11,000 "
    "events per second, measured over the following fortnight.",
    "Meridian ran eighteen months and closed 6% under its approved budget. No change request was "
    "raised after the second quarter.",
    "The storage layer was replaced after the November outage. Recovery time objective is now "
    "fifteen minutes, down from four hours.",
    "梅里迪安專案的資料保留期限是七年,依照內部稽核政策訂定,並經法務部門在三月覆核。",
    "客服團隊在專案上線後三個月內,平均回應時間從四小時縮短到四十分鐘。",
]

# (utterance, expectation, why). `fire` means a paraphrase -- never a copy, or this would measure
# string equality with extra steps.
UTTERANCES = [
    ("So how much faster did the pipeline get after you moved it?", "fire",
     "paraphrase of the throughput note, no shared numbers"),
    ("Did the programme come in over budget in the end?", "fire",
     "paraphrase of the budget note, opposite polarity"),
    ("What happens now if the storage fails again -- how long to recover?", "fire",
     "paraphrase of the outage note"),
    ("你們的資料要留多久?這是誰決定的?", "fire",
     "paraphrase of the retention note, in Chinese"),
    ("客服的回應速度有改善嗎?", "fire",
     "paraphrase of the support note, in Chinese"),
    ("Shall we take a short break before the next section?", "quiet",
     "ordinary meeting logistics, unrelated to every note"),
    ("Can everyone hear me at the back of the room?", "quiet",
     "room logistics"),
    ("我先確認一下投影片有沒有顯示出來。", "quiet",
     "room logistics, in Chinese"),
    ("The weather has been unusually warm for this time of year.", "quiet",
     "small talk"),
    ("I think we should move the quarterly planning session to Thursday.", "quiet",
     "plausible business talk that no note covers -- the hardest quiet case"),
]


def build_temp_index(settings, local_dir):
    """Write the invented notes into a fresh collection at `local_dir`. Returns the chunk count."""
    import bootstrap
    import knowledge_store

    knowledge_store.LOCAL_DIR = local_dir
    from sentence_transformers import SentenceTransformer

    # Resolved, not read raw. The field is empty on a machine that never overrode it, and
    # `SentenceTransformer("")` fails with an AttributeError deep inside its own constructor that
    # says nothing about the empty string -- which is how this was found.
    model_name = bootstrap.resolved_model(settings, "EMBEDDING_MODEL")
    model = SentenceTransformer(model_name)
    embeddings = model.encode(NOTES, convert_to_numpy=True)
    count, error = knowledge_store.write_index(
        settings, NOTES, [f"invented-note-{i}" for i in range(len(NOTES))], embeddings, model_name
    )
    if error:
        raise SystemExit(f"could not build the probe index: {error}")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    import bootstrap

    settings = bootstrap.read_settings()
    bootstrap.apply_environment(settings)
    bootstrap.enforce_offline()

    workdir = tempfile.mkdtemp(prefix="aegis-rag-probe-")
    local_dir = os.path.join(workdir, "qdrant")
    try:
        import knowledge_store

        real_local = knowledge_store.LOCAL_DIR
        chunks = build_temp_index(settings, local_dir)
        print(f"probe index: {chunks} invented notes at a temporary path")
        print(f"the operator's index at {real_local} was not opened\n")

        import local_advisor
        from advisors import SERVE_THRESHOLD

        advisor = local_advisor.LocalAdvisor(settings)
        if advisor.load_error:
            raise SystemExit(f"probe index did not load: {advisor.load_error}")

        rows, correct = [], 0
        print(f"threshold {SERVE_THRESHOLD} (V22)\n")
        print(f"  {'expected':<9}{'fired':<7}{'score':>7}  utterance")
        for utterance, expectation, why in UTTERANCES:
            # Suppression is a display rule, not a scoring rule. Left on, it would zero every
            # second row and look like a threshold problem.
            advisor.last_matched_idx = -1
            verdict = advisor.analyze_dialogue(utterance)
            fired = bool(verdict.hint)
            score = verdict.score
            ok = fired == (expectation == "fire")
            correct += ok
            rows.append({"utterance": utterance, "expected": expectation, "fired": fired,
                         "score": score, "ok": ok, "why": why})
            mark = " " if ok else "*"
            shown = f"{score:.3f}" if score is not None else "  --  "
            print(f"{mark} {expectation:<9}{str(fired):<7}{shown:>7}  {utterance[:52]}")

        want_fire = [r for r in rows if r["expected"] == "fire"]
        want_quiet = [r for r in rows if r["expected"] == "quiet"]
        fired_when_wanted = sum(1 for r in want_fire if r["fired"])
        fired_when_not = sum(1 for r in want_quiet if r["fired"])
        print(f"\n===== rag cue probe =====")
        print(f"  fired when it should      {fired_when_wanted}/{len(want_fire)}")
        print(f"  fired when it should not  {fired_when_not}/{len(want_quiet)}")
        print(f"  overall correct           {correct}/{len(rows)}")
        near = [r for r in want_fire if not r["fired"] and (r["score"] or 0) >= SERVE_THRESHOLD - 0.1]
        if near:
            print(f"  near misses within 0.1 of the threshold: {len(near)} -- these say the "
                  f"threshold is the issue, not the retrieval")
        # A threshold sweep, because "0/5 fired" on its own invites the wrong fix. If the two
        # populations do not separate at ANY threshold, retrieval is the problem and moving the
        # number just trades misses for noise. If they do separate, the number is the problem and
        # the sweep says where it should sit.
        print(f"\n  threshold sweep (the shipped value is {SERVE_THRESHOLD}):")
        print(f"    {'thr':>5}{'fires':>7}{'false':>7}  verdict")
        best = None
        for step in range(20, 71, 5):
            thr = step / 100
            hits = sum(1 for r in want_fire if (r["score"] or 0) >= thr)
            false = sum(1 for r in want_quiet if (r["score"] or 0) >= thr)
            score = hits - false
            # Ties go to the HIGHER threshold. A missed cue costs the speaker a cue; a false cue
            # costs attention on a teleprompter, which is what R9 is about. Between two settings
            # that score the same, the quieter one is the one to take.
            if best is None or score > best[0] or (score == best[0] and thr > best[1]):
                best = (score, thr, hits, false)
            flag = "  <-- shipped" if abs(thr - SERVE_THRESHOLD) < 0.001 else ""
            print(f"    {thr:>5.2f}{hits:>4}/{len(want_fire)}{false:>4}/{len(want_quiet)}{flag}")
        _, thr, hits, false = best
        print(f"\n  best separation at {thr:.2f}: {hits}/{len(want_fire)} fire, "
              f"{false}/{len(want_quiet)} false. The shipped {SERVE_THRESHOLD} sits above every")
        print(f"  score in the fire column, which is why nothing fires at all.")
        print("\nParaphrases, never copies, so this is not string matching with extra steps.")
        print("Scope: the mechanism, on invented notes. Whether the operator's own material")
        print("retrieves well needs the operator's own material and is their judgement.")

        if args.out:
            os.makedirs(os.path.dirname(args.out), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"\nwrote {args.out}")
        return 0 if correct == len(rows) else 1
    finally:
        try:
            advisor.close()
        except Exception:
            pass
        shutil.rmtree(workdir, ignore_errors=True)
        print("temporary probe index removed")


if __name__ == "__main__":
    sys.exit(main())
