"""The Qdrant knowledge collection, and the two migrations traps that fail silently.

These run against a **real** `QdrantClient` in local mode under `tmp_path` -- an embedded
database, no server, no network. That matters: both traps are properties of what Qdrant does and
does not validate, so stubbing the client would test the stub's opinion of them.
"""
import os
import sys

import numpy as np
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import knowledge_store as ks  # noqa: E402

pytest.importorskip("qdrant_client")

DIM = 8


def _vector(seed):
    rng = np.random.default_rng(seed)
    return rng.random(DIM).astype(np.float32)


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the local collection at `tmp_path`. The operator's real index is never touched."""
    local = tmp_path / "qdrant"
    monkeypatch.setattr(ks, "LOCAL_DIR", str(local))
    monkeypatch.setattr(ks, "LEGACY_PICKLE", str(tmp_path / "knowledge_index.pkl"))
    return {}          # empty settings == local mode


def _build(settings, texts=("chunk one", "chunk two"), model="model-a", seed=0):
    vectors = [_vector(seed + i) for i in range(len(texts))]
    count, error = ks.write_index(settings, list(texts), ["doc.md"] * len(texts), vectors, model)
    assert error == "", error
    return count, vectors


def test_a_built_collection_reports_its_chunks_model_and_metric(store):
    count, _vectors = _build(store)
    assert count == 2

    status = ks.status(store)
    assert status["present"] is True
    assert status["chunks"] == 2
    assert status["model"] == "model-a"
    assert status["built"]
    assert status["error"] == ""
    assert status["collection"] == ks.COLLECTION


def test_the_distance_metric_is_cosine_and_that_is_read_back_not_assumed(store):
    """Trap 1. The threshold that decides whether a cue is served is a cosine similarity; under
    DOT or EUCLID the returned number is on a different scale and **nothing raises**."""
    _build(store)
    client, error = ks.open_client(store)
    assert error == ""
    try:
        manifest = ks.read_manifest(client)
    finally:
        ks._close(client)

    assert ks.cosine_pinned(manifest["distance"])
    assert manifest["distance"].lower() == "cosine"


def test_a_collection_built_with_the_wrong_metric_is_refused_rather_than_scored(store):
    """A remote Qdrant may hold a collection this app did not create. Silent is the one thing
    this must not be."""
    from qdrant_client import QdrantClient, models

    os.makedirs(ks.LOCAL_DIR, exist_ok=True)
    client = QdrantClient(path=ks.LOCAL_DIR)
    client.create_collection(
        collection_name=ks.COLLECTION,
        vectors_config=models.VectorParams(size=DIM, distance=models.Distance.EUCLID),
    )
    client.upsert(collection_name=ks.COLLECTION, points=[models.PointStruct(
        id=0, vector=[float(v) for v in _vector(3)],
        payload={"text": "t", "source": "s", "model": "model-a", "built": "now"})], wait=True)
    client.close()

    status = ks.status(store)
    assert "Euclid" in status["error"] or "euclid" in status["error"].lower()
    assert "COSINE" in status["error"]


def test_the_embedding_model_is_stored_in_the_collection(store):
    """Trap 2 (V36). Qdrant validates dimensionality and nothing else, so two unrelated
    8-dimensional models are interchangeable to it and the wrong one returns confident nonsense.
    The pickle carried `model_name`; dropping it would have *introduced* this failure."""
    _build(store, model="paraphrase-multilingual-MiniLM-L12-v2")
    assert ks.status(store)["model"] == "paraphrase-multilingual-MiniLM-L12-v2"


def test_rebuilding_replaces_rather_than_appends(store):
    """A rebuild after deleting a document must not leave that document still answering."""
    _build(store, texts=("old one", "old two", "old three"))
    _build(store, texts=("only this one",), model="model-b")

    status = ks.status(store)
    assert status["chunks"] == 1
    assert status["model"] == "model-b"


def test_a_missing_index_says_how_to_build_one(store):
    status = ks.status(store)
    assert status["present"] is False
    assert "build_index" in status["error"]


def test_a_leftover_pickle_is_reported_as_rebuild_me_not_as_never_built(store, tmp_path):
    """An operator whose index worked yesterday deserves better than a screen implying they
    never compiled one."""
    (tmp_path / "knowledge_index.pkl").write_bytes(b"not really a pickle")
    status = ks.status(store)
    assert "older pickle index" in status["error"]
    assert "build_index" in status["error"]


def test_the_local_collection_lives_beside_the_documents_not_under_the_storage_root():
    """R48's layout is a tested contract and this is not part of it: the storage root exists for
    things that are large and re-downloadable, and a few hundred vectors are neither."""
    assert ks.LOCAL_DIR.endswith(os.path.join("context", "qdrant"))


def test_a_remote_url_selects_the_remote_client_without_a_second_code_path():
    """V29's whole reason for adopting Qdrant: one API, two targets. Constructing the client is
    enough to assert this -- `QdrantClient(url=...)` does not connect eagerly."""
    described = ks.describe_target({"QDRANT_URL": "https://qdrant.example.com:6333"})
    assert described == "https://qdrant.example.com:6333"
    assert "local" in ks.describe_target({})


def test_a_second_reader_is_told_the_index_is_locked_rather_than_a_generic_failure(store):
    """The embedded database takes an exclusive lock, so this is the error an operator hits when
    they rebuild while the app is running. It must name the cause."""
    _build(store)
    holder, error = ks.open_client(store)
    assert error == ""
    try:
        second, second_error = ks.open_client(store)
        assert second is None
        assert "locked by another process" in second_error
    finally:
        ks._close(holder)

    # And releasing it lets the next reader straight back in -- which is what `stop_recording`
    # calling `close()` between meetings is for.
    reopened, error = ks.open_client(store)
    assert reopened is not None and error == ""
    ks._close(reopened)


# ===== The compiler, end to end =====
#
# Against a throwaway docs directory, never `context/docs/` -- that holds the operator's private
# notes and the suite has no business reading it. Only the embedding model is stubbed; the
# chunking, the collection write and the read-back are the real code.

def test_the_compiler_writes_a_queryable_collection(store, tmp_path, monkeypatch):
    import build_index

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text(
        "# Heading that is long enough\n\n"
        "The audit closed in March and the finding was withdrawn.\n\n"
        "Budget questions go to the finance office.\n",
        encoding="utf-8",
    )
    (docs / "short.txt").write_text("tiny\n", encoding="utf-8")   # below the 10-char floor

    class _Embedder:
        def __init__(self, name):
            self.name = name

        def encode(self, texts, show_progress_bar=False, convert_to_numpy=True):
            return np.stack([_vector(i) for i in range(len(texts))])

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", _Embedder)

    build_index.build_knowledge_index(model_name="stub-embedder", docs_dir=str(docs),
                                      settings=store)

    status = ks.status(store)
    assert status["present"] is True
    assert status["chunks"] == 3          # two paragraphs plus the heading; "tiny" is dropped
    assert status["model"] == "stub-embedder"
    assert status["error"] == ""


def test_the_compiler_reports_a_locked_index_instead_of_failing_obscurely(store, tmp_path,
                                                                         monkeypatch, capsys):
    """The operator's realistic mistake: rebuild while a meeting is running."""
    import build_index

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text("A paragraph long enough to survive chunking.\n",
                                   encoding="utf-8")

    class _Embedder:
        def __init__(self, name):
            pass

        def encode(self, texts, show_progress_bar=False, convert_to_numpy=True):
            return np.stack([_vector(i) for i in range(len(texts))])

    import sentence_transformers
    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", _Embedder)

    _build(store)                                   # so the directory and its lock file exist
    holder, error = ks.open_client(store)
    assert error == ""
    try:
        build_index.build_knowledge_index(model_name="stub", docs_dir=str(docs), settings=store)
        out = capsys.readouterr().out
    finally:
        ks._close(holder)

    assert "locked by another process" in out
    assert "stop Aegis Prompter" in out
