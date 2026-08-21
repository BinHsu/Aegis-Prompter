#!/usr/bin/env python3
"""The positive half of the retrieval threshold, on questions nobody here wrote.

**The gap this closes.** **V95** chose `SERVE_THRESHOLD = 0.45` against ten utterances written by the
same session that wrote the queries. **V108** replaced the *negative* half with 250 real transcribed
utterances and, in doing so, reversed which half was weak: false positives are now measured on
unauthored speech, while "4 of 5 cues fired" still rests on five paraphrases written here.

**Why not ASCEND.** The obvious source was the fixture already in the repo. Measured before building
anything: **0 of its 1130 references contain any punctuation**, the median turn is **12 characters**,
and the whole corpus is one loose topic — so there are no real questions to use as queries and
conversational adjacency would not separate a related note from an unrelated one.

**DRCD instead.** 台達閱讀理解資料集, Traditional Chinese compiled from Wikipedia, CC BY-SA 3.0, from
Delta Electronics in Taiwan — which is **R10**'s target locale rather than a translation of an English
set. 1000 paragraphs, 3524 questions, each question attached to the paragraph that answers it. The
relationship is the dataset's, not a judgement made here.

**Fidelity to production, checked rather than assumed.** `build_index.py` chunks notes on double
newlines and keeps blocks over 10 characters, so a production chunk *is* a paragraph. DRCD paragraphs
run a median of 421 characters, which is briefing-note sized. The mapping is therefore direct.

**What this measures, and what it cannot.** It measures whether a genuine question retrieves its own
note above the gate — the product's cue-firing behaviour — over a thousand competing notes. It does
**not** measure spoken input: DRCD questions are written, punctuated and monolingual, while the live
path receives unpunctuated code-switched fragments. **That gap is why ASCEND was attractive despite
failing, and it remains open.**

USAGE
    PYTHONPATH="$PWD" .venv/bin/python tools/probe_rag_positives.py --questions 400
"""
import argparse
import json
import os
import random
import shutil
import statistics
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "src"))

CORPUS = os.path.join(REPO, ".corpora-qa", "DRCD_dev.json")
URL = "https://raw.githubusercontent.com/DRCKnowledgeTeam/DRCD/master/DRCD_dev.json"


def load_corpus():
    """`(paragraphs, [(question, paragraph_index)])`, or exit with the fetch command."""
    if not os.path.exists(CORPUS):
        sys.exit(f"corpus missing. Fetch it with curl -- huggingface_hub cannot reach the network on\n"
                 f"this machine (V93):\n  mkdir -p {os.path.dirname(CORPUS)}\n"
                 f"  curl -sSL -o {CORPUS} {URL}")
    data = json.load(open(CORPUS, encoding="utf-8"))
    paragraphs, pairs = [], []
    for article in data["data"]:
        for para in article["paragraphs"]:
            index = len(paragraphs)
            paragraphs.append(para["context"])
            for qa in para["qas"]:
                pairs.append((qa["question"], index))
    return paragraphs, pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=int, default=400,
                        help="How many questions to sample. Every paragraph is indexed regardless, "
                             "so a question always competes against the full thousand.")
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--notes", type=int, default=0,
                        help="Index only this many paragraphs, so precision can be read against the "
                             "size of a realistic note set. A real operator's index held 4 chunks; "
                             "picking one paragraph correctly out of 1000 is a far harder task than "
                             "out of 20, and conflating the two would make the mechanism look worse "
                             "than the product's own conditions warrant. 0 indexes everything.")
    parser.add_argument("--topk", action="store_true",
                        help="Report recall@1/3/5/10 instead of the firing table.")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    paragraphs, pairs = load_corpus()
    if args.notes and args.notes < len(paragraphs):
        # Keep only questions whose own paragraph survives, so every sampled question still has a
        # correct answer present. Dropping that invariant would turn recall into a different metric
        # without saying so.
        keep = args.notes
        paragraphs = paragraphs[:keep]
        pairs = [(q, i) for q, i in pairs if i < keep]
    random.Random(args.seed).shuffle(pairs)
    sample = pairs[:args.questions]
    print(f"  corpus: {len(paragraphs)} paragraphs indexed, {len(pairs)} questions available, "
          f"{len(sample)} sampled (seed {args.seed})")

    import bootstrap
    import knowledge_store

    settings = bootstrap.read_settings()
    bootstrap.apply_environment(settings)
    bootstrap.enforce_offline()

    workdir = tempfile.mkdtemp(prefix="aegis-rag-pos-")
    real_local = knowledge_store.LOCAL_DIR
    knowledge_store.LOCAL_DIR = os.path.join(workdir, "qdrant")
    advisor = None
    try:
        from sentence_transformers import SentenceTransformer

        model_name = bootstrap.resolved_model(settings, "EMBEDDING_MODEL")
        model = SentenceTransformer(model_name)
        embeddings = model.encode(paragraphs, convert_to_numpy=True, batch_size=32,
                                  show_progress_bar=False)
        count, error = knowledge_store.write_index(
            settings, paragraphs, [f"drcd-{i}" for i in range(len(paragraphs))],
            embeddings, model_name)
        if error:
            sys.exit(f"could not build the probe index: {error}")
        print(f"  indexed {count} paragraphs with {model_name}")
        print(f"  the operator's index at {real_local} was not opened\n")

        import local_advisor
        from advisors import SERVE_THRESHOLD

        advisor = local_advisor.LocalAdvisor(settings)
        if advisor.load_error:
            sys.exit(f"probe index did not load: {advisor.load_error}")

        # **Is the right note near the top, or genuinely lost?** `analyze_dialogue` asks for one
        # point because that is what the product shows. If recall@3 or @5 is far above recall@1, the
        # ranking is nearly right and displaying a small number of candidates converts "wrong note"
        # into "right note among three" -- a change with no new model and no extra latency. If the
        # curve is flat, the embedding model itself is the lever. Measured before recommending either.
        if args.topk:
            import knowledge_store as ks
            hits_at = {k: 0 for k in (1, 3, 5, 10)}
            for question, want in sample:
                vec = advisor.model.encode([question], convert_to_numpy=True)[0]
                points = advisor.client.query_points(
                    collection_name=ks.COLLECTION, query=[float(v) for v in vec],
                    limit=10, with_payload=True).points
                texts = [(pt.payload or {}).get("text", "") for pt in points]
                for k in hits_at:
                    if any(t.strip() == paragraphs[want].strip() for t in texts[:k]):
                        hits_at[k] += 1
            n = len(sample)
            print(f"===== recall@k over {len(paragraphs)} notes, {n} questions =====")
            # **Gated recall is the number the product would actually deliver.** recall@k above
            # counts the right note being in the top k at ANY score; the shipped path only shows a
            # point that clears SERVE_THRESHOLD. If the recovered hits sit below the gate, showing
            # three changes nothing -- so this is measured before the display is changed, not after.
            from advisors import SERVE_THRESHOLD as THR
            gated = {k: 0 for k in (1, 3, 5)}
            shown = {k: 0 for k in (1, 3, 5)}
            for question, want in sample:
                vec = advisor.model.encode([question], convert_to_numpy=True)[0]
                points = advisor.client.query_points(
                    collection_name=ks.COLLECTION, query=[float(v) for v in vec],
                    limit=5, with_payload=True).points
                keep = [pt for pt in points if float(pt.score) >= THR]
                for k in gated:
                    top = keep[:k]
                    shown[k] += len(top)
                    if any((pt.payload or {}).get("text", "").strip()
                           == paragraphs[want].strip() for pt in top):
                        gated[k] += 1
            print(f"  --- gated at {THR}, which is what the product would show ---")
            for k in (1, 3, 5):
                print(f"    right note among the shown {k:<2} {gated[k]:>4}/{n}"
                      f"  ({100*gated[k]/n:.1f}%)   cues displayed per question avg "
                      f"{shown[k]/n:.2f}")
            for k in (1, 3, 5, 10):
                print(f"    recall@{k:<3} {hits_at[k]:>4}/{n}  ({100*hits_at[k]/n:.1f}%)")
            gain = hits_at[3] - hits_at[1]
            print(f"    showing three instead of one would recover {gain} of the "
                  f"{n - hits_at[1]} misses ({100*gain/max(n - hits_at[1],1):.0f}% of them)")
            return 0

        rows = []
        for question, want in sample:
            # Suppression is a display rule; left on it would zero every repeat hit.
            advisor.last_matched_idx = -1
            verdict = advisor.analyze_dialogue(question)
            if verdict.score is None:
                rows.append({"q": question, "score": None, "correct": None, "fired": False})
                continue
            # `hint` carries the matched chunk's text, which is how we learn WHICH note won.
            hit = (verdict.hint or "")
            correct = bool(hit) and hit.strip() == paragraphs[want].strip()
            rows.append({"q": question, "score": verdict.score, "correct": correct,
                         "fired": bool(verdict.hint), "want": want})

        scored = [r for r in rows if r["score"] is not None]
        fired = [r for r in scored if r["fired"]]
        right = [r for r in fired if r["correct"]]
        wrong = [r for r in fired if not r["correct"]]
        silent = [r for r in scored if not r["fired"]]

        print(f"===== rag positives, DRCD =====")
        print(f"  questions scored              {len(scored)}")
        print(f"  fired at {SERVE_THRESHOLD}                  {len(fired)}"
              f"  ({100 * len(fired) / max(len(scored), 1):.1f}%)")
        print(f"    ...on the RIGHT paragraph   {len(right)}"
              f"  ({100 * len(right) / max(len(scored), 1):.1f}% of all questions)")
        print(f"    ...on the WRONG paragraph   {len(wrong)}"
              f"  ({100 * len(wrong) / max(len(fired), 1):.1f}% of fires)")
        print(f"  silent (below the gate)       {len(silent)}"
              f"  ({100 * len(silent) / max(len(scored), 1):.1f}%)")
        if scored:
            vals = sorted(r["score"] for r in scored)
            print(f"  score distribution: median {vals[len(vals)//2]:.3f}  "
                  f"5th {vals[int(.05*len(vals))]:.3f}  95th {vals[int(.95*len(vals))]:.3f}")

        # A sweep, so the threshold choice can be read against the negative sweep in V108.
        print(f"\n  threshold sweep (shipped {SERVE_THRESHOLD}):")
        print(f"    {'thr':>5}{'fires':>8}{'right':>8}{'wrong':>8}")
        for step in range(25, 71, 5):
            thr = step / 100
            f = [r for r in scored if r["score"] >= thr]
            rt = sum(1 for r in f if r["correct"])
            mark = "   <-- shipped" if abs(thr - SERVE_THRESHOLD) < 1e-9 else ""
            print(f"    {thr:>5.2f}{len(f):>8}{rt:>8}{len(f) - rt:>8}{mark}")

        print("\n  Questions are DRCD's, paragraphs are DRCD's, and the pairing is DRCD's -- none of")
        print("  it authored here. It measures retrieval, not spoken input: these questions are")
        print("  written and punctuated, and the live path receives neither.")

        if args.out:
            os.makedirs(os.path.dirname(args.out), exist_ok=True)
            with open(args.out, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"\n  wrote {args.out}")
        return 0
    finally:
        try:
            if advisor is not None:
                advisor.close()
        except Exception:
            pass
        knowledge_store.LOCAL_DIR = real_local
        shutil.rmtree(workdir, ignore_errors=True)
        print("  temporary probe index removed")


if __name__ == "__main__":
    sys.exit(main())
