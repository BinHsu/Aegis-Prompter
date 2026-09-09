"""The retrieval backend: what it scores, what it serves, and what it says when it cannot.

Against a **real** Qdrant collection in local mode under `tmp_path` — an embedded database, no
server, no network. Only the embedding model is stubbed, because downloading a sentence
transformer to assert a threshold would be the one part of this that proves nothing.

`local_advisor` imports its siblings bare, the way every runtime module does, so `src/` goes on
the path here rather than the repo root — the idiom `test_transcriber_feed_wav.py` and
`test_rag_gate.py` already use.
"""
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import advisors  # noqa: E402
import knowledge_store as ks  # noqa: E402
import local_advisor as la  # noqa: E402
from local_advisor import LocalAdvisor  # noqa: E402

pytest.importorskip("qdrant_client")

DIM = 8
TEST_QA_CHUNK = "If the server crashes, reboot the AWS instance."
OTHER_CHUNK = "Budget questions go to the finance office."

# Two orthogonal unit vectors, so the cosine scores are exactly 1.0 and 0.0 and the assertions
# below are about the threshold rather than about floating point.
MATCHING = np.eye(DIM, dtype=np.float32)[0]
ORTHOGONAL = np.eye(DIM, dtype=np.float32)[1]


class _StubEmbedder:
    """Returns whatever vector the test set. Stands in for SentenceTransformer."""

    vector = MATCHING

    def __init__(self, name):
        self.name = name

    def encode(self, texts, convert_to_numpy=True):
        return np.array([_StubEmbedder.vector], dtype=np.float32)


@pytest.fixture
def local_index(tmp_path, monkeypatch):
    """A real local collection holding one chunk at `MATCHING`, plus a stubbed embedder."""
    monkeypatch.setattr(ks, "LOCAL_DIR", str(tmp_path / "qdrant"))
    monkeypatch.setattr(ks, "LEGACY_PICKLE", str(tmp_path / "knowledge_index.pkl"))
    monkeypatch.setattr(la, "SentenceTransformer", _StubEmbedder)
    _StubEmbedder.vector = MATCHING
    yield {}
    _StubEmbedder.vector = MATCHING


def _build(settings, texts=(TEST_QA_CHUNK,), vectors=(MATCHING,), model="stub-embedder"):
    count, error = ks.write_index(settings, list(texts), ["notes.md"] * len(texts),
                                  list(vectors), model)
    assert error == "", error
    return count


def test_the_advisor_loads_the_model_the_collection_names(local_index):
    """V36: not the model the settings name. Qdrant validates dimensionality and nothing else,
    so taking the model from the collection is what keeps a mismatch impossible."""
    _build(local_index, model="the-model-that-built-this")
    advisor = LocalAdvisor(settings=local_index)
    try:
        assert advisor.load_error == ""
        assert advisor.model_name == "the-model-that-built-this"
        assert advisor.chunks == 1
    finally:
        advisor.close()


def test_a_match_above_the_threshold_is_served(local_index):
    _build(local_index)
    advisor = LocalAdvisor(settings=local_index)
    try:
        result = advisor.analyze_dialogue("The server has crashed.")
        assert result.ok
        assert result.hint == TEST_QA_CHUNK
        assert result.score == pytest.approx(1.0, abs=1e-4)
    finally:
        advisor.close()


def test_a_below_threshold_query_still_returns_its_score(local_index):
    """The whole point of the return type. The old `str | None` returned nothing below the
    threshold, so a working index that matched nothing and one that never loaded were the same
    value — and the liveness line has no way back from that (V34, V35)."""
    _build(local_index)
    _StubEmbedder.vector = ORTHOGONAL
    advisor = LocalAdvisor(settings=local_index)
    try:
        result = advisor.analyze_dialogue("Something completely unrelated to the notes.")
        assert result.ok
        assert result.hint is None
        assert result.score == pytest.approx(0.0, abs=1e-4)
    finally:
        advisor.close()


def test_a_repeated_match_is_suppressed_for_display_but_still_scored(local_index):
    """Repeat suppression is a display decision. It must not read as a dead index (V35, R36)."""
    _build(local_index)
    advisor = LocalAdvisor(settings=local_index)
    try:
        first = advisor.analyze_dialogue("The server has crashed.")
        second = advisor.analyze_dialogue("The server has crashed again.")
        assert first.hint == TEST_QA_CHUNK
        assert second.hint is None
        assert second.score == pytest.approx(1.0, abs=1e-4)
    finally:
        advisor.close()


def test_a_missing_index_reports_why_rather_than_returning_nothing(local_index):
    """V34: the old path logged once and then returned None forever, looking exactly like
    'nothing matched'. The operator saw an armed toggle and a defence that would never fire."""
    advisor = LocalAdvisor(settings=local_index)
    try:
        result = advisor.analyze_dialogue("A line long enough to be embedded.")
        assert result.ok is False
        assert result.score is None
        assert "build_index" in result.error
    finally:
        advisor.close()


def test_a_collection_with_the_wrong_distance_metric_refuses_to_serve(local_index):
    """The failure that produces plausible numbers rather than none: the threshold is a cosine
    similarity, and under any other metric the score it is compared against means nothing."""
    from qdrant_client import QdrantClient, models

    os.makedirs(ks.LOCAL_DIR, exist_ok=True)
    client = QdrantClient(path=ks.LOCAL_DIR)
    client.create_collection(
        collection_name=ks.COLLECTION,
        vectors_config=models.VectorParams(size=DIM, distance=models.Distance.DOT),
    )
    client.upsert(collection_name=ks.COLLECTION, points=[models.PointStruct(
        id=0, vector=[float(v) for v in MATCHING],
        payload={"text": TEST_QA_CHUNK, "source": "s", "model": "m", "built": "now"})],
        wait=True)
    client.close()

    advisor = LocalAdvisor(settings=local_index)
    try:
        result = advisor.analyze_dialogue("The server has crashed.")
        assert result.ok is False
        assert "COSINE" in result.error
    finally:
        advisor.close()


def test_an_empty_collection_says_it_is_empty_rather_than_missing(local_index):
    """A built-but-empty index and a never-built one are different operator problems."""
    from qdrant_client import QdrantClient, models

    os.makedirs(ks.LOCAL_DIR, exist_ok=True)
    client = QdrantClient(path=ks.LOCAL_DIR)
    client.create_collection(
        collection_name=ks.COLLECTION,
        vectors_config=models.VectorParams(size=DIM, distance=models.Distance.COSINE),
    )
    client.close()

    advisor = LocalAdvisor(settings=local_index)
    try:
        assert "empty" in advisor.load_error
    finally:
        advisor.close()


def test_filler_shorter_than_ten_characters_is_not_scored(local_index):
    _build(local_index)
    advisor = LocalAdvisor(settings=local_index)
    try:
        result = advisor.analyze_dialogue("yes")
        # `ok` because the backend is alive; `score is None` because it formed no judgement. The
        # two together are what the liveness line reads.
        assert result.ok is True
        assert result.score is None
        assert result.hint is None
    finally:
        advisor.close()


def test_closing_releases_the_lock_and_reopening_keeps_the_loaded_model(local_index):
    """The lock is held for a session, not for a process — otherwise the pre-flight panel cannot
    read its own chunk count after the first meeting, and rebuilding means quitting the app."""
    _build(local_index)
    advisor = LocalAdvisor(settings=local_index)
    loaded = advisor.model
    advisor.close()

    other, error = ks.open_client(local_index)
    assert other is not None and error == ""
    ks._close(other)

    advisor.open()
    try:
        assert advisor.load_error == ""
        assert advisor.model is loaded, "reopening must not pay for the embedding model again"
    finally:
        advisor.close()


def test_the_serve_threshold_is_the_one_the_router_uses():
    """One number, one home. A second copy in `local_advisor` is how the served band and the
    routed band drift apart without either file looking wrong."""
    assert la.SERVE_THRESHOLD is advisors.SERVE_THRESHOLD


# ===== The filler floor, and why it is script-aware =====

def test_a_short_chinese_question_is_not_filler():
    """**Found 2026-08-17 by running the real index for the first time.** The floor was a flat
    `len(...) < 10`, so `這筆預算是誰核的？` (9 characters) and `請問第三條規定` (7) were dropped
    before they ever reached retrieval — complete questions, in the script R10 names as the
    target, in a product built to catch questions at a Taiwan hearing.

    It is also the opposite of what the operator decided about the adjacent filter: V64 kept short
    utterances in the transcript because `是。` and `不。` are the shortest answers and a hearing
    turns on them."""
    assert la.is_worth_embedding("這筆預算是誰核的？")
    assert la.is_worth_embedding("請問第三條規定")
    assert la.is_worth_embedding("今天午餐要吃什麼？")


def test_genuine_filler_is_still_dropped_in_both_scripts():
    for filler in ("嗯", "是。", "對", "yes", "ok", "no"):
        assert not la.is_worth_embedding(filler), filler


def test_latin_behaviour_is_unchanged():
    """The threshold stayed at 10 so nothing about English moved — only CJK was mis-weighted."""
    assert not la.is_worth_embedding("I don't")          # 7
    assert la.is_worth_embedding("I don't know")         # 12


def test_the_weighting_is_declared_a_heuristic_not_a_measurement():
    """What was measured is that the old rule was wrong, not that 2 is right. A comment claiming
    otherwise is how an invented number acquires authority."""
    import inspect
    source = inspect.getsource(la)
    assert "heuristic, not a measurement" in source


# ===== Up to three cues, and the invariants that keep them honest (0016) =====

def test_the_cue_cap_is_three_and_is_the_number_the_operator_chose():
    """`MAX_CUES` is a product decision (0016), not a tuning constant. Pinned so a change has to
    confront the record: gated recall gains only ~3 points from three to five while the reading
    roughly doubles, and the cost of more cues is entirely R9."""
    assert advisors.MAX_CUES == 3


def test_retrieval_defaults_keep_every_existing_reader_working():
    """`hints`/`scores` were added beside `hint`, not instead of it. A `Retrieval` built the old
    way must still be valid, or every caller and test predating 0016 breaks."""
    old_style = advisors.Retrieval(ok=True, score=0.7, hint="a note")
    assert old_style.hints == ()
    assert old_style.scores == ()
    assert old_style.hint == "a note"
