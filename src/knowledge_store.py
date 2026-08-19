"""The knowledge index, in Qdrant. One API for the local collection and a remote one (V29).

Retrieval was named as Qdrant from the outset; this module is where that lands. It replaces a
pickle of numpy vectors, and the swap is **not** a performance win -- a dot product over a few
hundred 384-dimensional vectors was already microseconds. What it buys is that
`QdrantClient(path=...)` and `QdrantClient(url=..., api_key=...)` are the same object with the
same methods, which is what makes R31 -- the operator supplies a host and a credential, and
nothing else -- implementable without a second code path.

**Two migration traps, both of which fail silently, are guarded here rather than left to the
caller.** They are the entire reason this file exists instead of two `QdrantClient` calls
inlined into `local_advisor.py` and `build_index.py`:

1. **The distance metric is pinned to `COSINE` at creation, and verified at read.** The
   threshold that decides whether a cue is served is a cosine similarity. Under `DOT` or
   `EUCLID` the returned number means something else entirely, is not on the same scale, and
   **no error is raised** -- the advisor simply stops matching, or matches everything.
2. **The embedding model's identity is stored in the collection and read back.** Qdrant
   validates vector dimensionality and nothing else, so two different 384-dimensional models
   are interchangeable as far as it is concerned, and querying with the wrong one returns
   confident nonsense (V36). The pickle carried `model_name` and made this impossible; dropping
   it would have *introduced* the failure. So the query side loads the model the collection
   names rather than the model the settings name, and any disagreement between the two is
   reported rather than resolved silently.

**Embedding always happens on this machine, never through Qdrant Cloud Inference.** Cloud
Inference would work and would need no extra setting, but it changes what leaves the machine:
the raw utterance instead of a vector of it. For a product whose premise is that meeting audio
stays put, that is a different decision from "the operator pointed retrieval at a remote host",
and it is not one this file makes on their behalf.
"""
import datetime
import logging
import os

logger = logging.getLogger("KnowledgeStore")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

COLLECTION = "aegis_knowledge"

# The local collection sits beside the documents it is compiled from, not under the storage root
# (R48). The storage root exists for things that are large and re-downloadable -- model weights,
# retained audio -- and this is neither: it is a few hundred vectors derived from `context/docs`,
# and keeping it there is what makes "delete `context/` and the knowledge base is gone" true.
LOCAL_DIR = os.path.join(REPO_ROOT, "context", "qdrant")

# The pickle this replaced. Detected only so its presence can be reported as "rebuild me"
# rather than as a missing index -- an operator with a working index yesterday deserves better
# than a screen that says nothing was ever built.
LEGACY_PICKLE = os.path.join(REPO_ROOT, "context", "knowledge_index.pkl")


def describe_target(settings):
    """Where retrieval will read from, as a phrase for the operator. Never raises."""
    url = (settings.get("QDRANT_URL") or "").strip()
    return url if url else f"local collection at {LOCAL_DIR}"


def open_client(settings, create_local=False):
    """Connect to the configured Qdrant. Returns `(client, error)`; never raises.

    Remote when `QDRANT_URL` is set, local otherwise -- the same class either way (V29). The
    local form is an embedded database on disk with **an exclusive lock**, so the running app
    holding it open is why rebuilding the index needs the app stopped. That is reported as
    itself rather than as a generic failure.
    """
    from qdrant_client import QdrantClient

    url = (settings.get("QDRANT_URL") or "").strip()
    try:
        if url:
            key = (settings.get("QDRANT_API_KEY") or "").strip() or None
            return QdrantClient(url=url, api_key=key), ""
        if create_local:
            os.makedirs(LOCAL_DIR, exist_ok=True)
        elif not os.path.isdir(LOCAL_DIR):
            return None, "index missing -- run `python src/build_index.py`"
        return QdrantClient(path=LOCAL_DIR), ""
    except Exception as exc:
        message = str(exc)
        if "lock" in message.lower() or "already accessed" in message.lower():
            return None, ("the local index is locked by another process -- stop Aegis Prompter "
                          "before rebuilding the index")
        return None, f"{type(exc).__name__}: {exc}"


def write_index(settings, texts, sources, embeddings, model_name):
    """Replace the collection with these chunks. Returns `(count, error)`.

    Replace, not append: a rebuild after deleting a document must not leave that document's
    vectors answering queries. The collection is dropped and recreated, which is also the only
    moment the distance metric can be chosen.
    """
    from qdrant_client import models

    client, error = open_client(settings, create_local=True)
    if client is None:
        return 0, error

    dimension = int(len(embeddings[0]))
    built = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
        client.create_collection(
            collection_name=COLLECTION,
            # Pinned here and nowhere else. `local_advisor`'s threshold is a cosine similarity;
            # under any other metric the number it compares against means nothing and says so
            # with no error at all.
            vectors_config=models.VectorParams(size=dimension,
                                               distance=models.Distance.COSINE),
        )
        points = [
            models.PointStruct(
                id=index,
                vector=[float(value) for value in vector],
                # `model` rides on every point rather than on a manifest point of its own: a
                # manifest would need a vector, and any vector in a cosine collection is a
                # search result waiting to be returned as a cue.
                payload={"text": text, "source": source, "model": model_name, "built": built},
            )
            for index, (text, source, vector) in enumerate(zip(texts, sources, embeddings))
        ]
        client.upsert(collection_name=COLLECTION, points=points, wait=True)
    except Exception as exc:
        return 0, f"{type(exc).__name__}: {exc}"
    finally:
        _close(client)
    return len(points), ""


def read_manifest(client):
    """What the collection says about itself: chunk count, build date, model, distance metric.

    Returns a dict with an `error` key. The distance metric is read back rather than assumed --
    a collection created by anything other than `write_index`, which a remote Qdrant may well
    have been, carries whatever metric its creator chose.
    """
    empty = {"chunks": 0, "model": "", "built": "", "distance": "", "error": ""}
    try:
        if not client.collection_exists(COLLECTION):
            return dict(empty, error="index missing -- run `python src/build_index.py`")
        info = client.get_collection(COLLECTION)
        count = client.count(COLLECTION, exact=True).count
        params = info.config.params.vectors
        distance = str(getattr(params, "distance", "") or "")
        model = ""
        built = ""
        if count:
            points, _next = client.scroll(COLLECTION, limit=1, with_payload=True,
                                          with_vectors=False)
            if points:
                payload = points[0].payload or {}
                model = payload.get("model", "")
                built = payload.get("built", "")
        return {"chunks": count, "model": model, "built": built, "distance": distance,
                "error": ""}
    except Exception as exc:
        return dict(empty, error=f"index unreadable: {type(exc).__name__}: {exc}")


def cosine_pinned(distance):
    """Whether a collection's metric is the one the threshold is expressed in."""
    return str(distance).strip().lower() == "cosine"


def status(settings):
    """Chunk count, build date, model and metric, or why there is none. Never raises.

    Shaped for the pre-flight readiness line, which is the one place an unbuilt or mis-built
    index can still be caught while the operator can act on it (R36, V34).
    """
    result = {"present": False, "chunks": 0, "built": "", "model": "", "error": "",
              "target": describe_target(settings), "collection": COLLECTION}
    client, error = open_client(settings)
    if client is None:
        if error.startswith("index missing") and os.path.exists(LEGACY_PICKLE):
            error = ("an older pickle index is present but is no longer read -- run "
                     "`python src/build_index.py` to rebuild it into Qdrant")
        return dict(result, error=error)
    try:
        manifest = read_manifest(client)
    finally:
        _close(client)

    if manifest["error"]:
        if manifest["error"].startswith("index missing") and os.path.exists(LEGACY_PICKLE):
            manifest["error"] = ("an older pickle index is present but is no longer read -- run "
                                 "`python src/build_index.py` to rebuild it into Qdrant")
        return dict(result, error=manifest["error"])
    if manifest["chunks"] and not cosine_pinned(manifest["distance"]):
        # Silent in every other way: queries succeed and return numbers on a different scale.
        return dict(result, present=True, chunks=manifest["chunks"],
                    error=f"collection uses {manifest['distance']} distance, not COSINE -- the "
                          f"match threshold is a cosine similarity and means nothing here; "
                          f"rebuild the index")
    return dict(result, present=True, chunks=manifest["chunks"], built=manifest["built"],
                model=manifest["model"])


def _close(client):
    """Release the local database's lock. A no-op against a remote host."""
    try:
        client.close()
    except Exception:
        pass
