import os
from sentence_transformers import SentenceTransformer
import logging
import time

import knowledge_store
from advisors import SERVE_THRESHOLD, Retrieval

logger = logging.getLogger("LocalAdvisor")

# How much text is worth embedding, weighted by script.
#
# **This was a flat `len(...) < 10` until 2026-08-17, and it silently discarded most of the
# questions this product exists to catch.** Measured against the real index that day:
# `這筆預算是誰核的？` is 9 characters, `請問第三條規定` is 7 — both complete questions, both
# dropped — while `I don't know` is 12 and passed. The floor was calibrated for Latin script in a
# product whose target script is Traditional Chinese (**R10**).
#
# It is also the opposite of what the operator decided about the adjacent filter: **V64** and open
# decision 0 kept short utterances *in* the transcript, because `是。` and `不。` are the shortest
# answers and a hearing turns on them. The same reasoning applies to a 7-character question.
#
# A CJK character carries roughly what an English word does, so it counts double. **That factor is
# a heuristic, not a measurement** — what is measured is that the old rule was wrong, not that 2 is
# right. The threshold is unchanged at 10 so Latin behaviour is exactly as before.
CJK_WEIGHT = 2
MIN_WEIGHT = 10


def is_worth_embedding(text):
    """Whether an utterance carries enough content to be worth a query. Pure; no model needed."""
    weight = 0
    for character in (text or "").strip():
        if character.isspace():
            weight += 1
        elif "\u4e00" <= character <= "\u9fff" or "\u3040" <= character <= "\u30ff":
            weight += CJK_WEIGHT
        else:
            weight += 1
    return weight >= MIN_WEIGHT

class LocalAdvisor:
    """
    Retrieval advisor over the Qdrant knowledge collection.
    Embeds the latest transcribed line locally and matches it by cosine similarity against the
    chunks compiled by `build_index.py`. With no `QDRANT_URL` configured the collection is an
    embedded database on this machine and nothing leaves it.
    """
    def __init__(self, settings=None):
        # `os.environ` in production -- `bootstrap.apply_environment` has already exported the
        # persisted settings by the time anything constructs this. A dict in tests.
        self.settings = settings if settings is not None else os.environ
        self.model = None
        self.model_name = ""
        self.client = None
        self.chunks = 0
        self.load_error = "index not loaded"

        # We hold state to prevent repeatedly throwing the same hint
        self.last_matched_idx = -1

        self.open()

    def open(self):
        """Open the collection and load **the embedding model the collection names**.

        Called at construction and again at the start of any later session, because `close()`
        releases the embedded database's exclusive lock between meetings -- see there for why.
        Reopening is cheap: the embedding model is what costs, and it is kept.

        Not the model the settings name. Qdrant validates vector dimensionality and nothing
        else, so two unrelated 384-dimensional models are interchangeable to it and querying
        with the wrong one returns confident nonsense with no error (V36). The pickle this
        replaced made that impossible by carrying `model_name`; taking the model from the
        collection's own payload keeps it impossible.

        A disagreement between the collection's model and `EMBEDDING_MODEL` is therefore not an
        error here -- retrieval still works, against the index as built. It is reported on the
        pre-flight readiness line, where the operator can decide to rebuild.
        """
        client, error = knowledge_store.open_client(self.settings)
        if client is None:
            logger.warning("⚠️ [LocalAdvisor] Knowledge index unavailable: %s", error)
            self.load_error = error
            return

        manifest = knowledge_store.read_manifest(client)
        if manifest["error"]:
            logger.warning("⚠️ [LocalAdvisor] %s", manifest["error"])
            self.load_error = manifest["error"]
            knowledge_store._close(client)
            return
        if not manifest["chunks"]:
            self.load_error = "index is empty -- put notes in `context/docs/` and rebuild"
            knowledge_store._close(client)
            return
        if not knowledge_store.cosine_pinned(manifest["distance"]):
            # The one failure that produces plausible numbers rather than none.
            self.load_error = (f"collection uses {manifest['distance']} distance, not COSINE -- "
                               f"the match threshold is a cosine similarity; rebuild the index")
            logger.error("❌ [LocalAdvisor] %s", self.load_error)
            knowledge_store._close(client)
            return

        try:
            if self.model is None or self.model_name != manifest["model"]:
                self.model_name = manifest["model"]
                logger.info(f"📦 [LocalAdvisor] Loading local embedding model: {self.model_name}...")
                self.model = SentenceTransformer(self.model_name)
            self.client = client
            self.chunks = manifest["chunks"]
            logger.info(f"✅ [LocalAdvisor] Ready! {self.chunks} chunks in "
                        f"{knowledge_store.describe_target(self.settings)}.")
            self.load_error = ""
        except Exception as e:
            logger.error(f"❌ [LocalAdvisor] Failed to load embedding model: {e}")
            self.load_error = f"embedding model {self.model_name!r} would not load: {e}"
            knowledge_store._close(client)

    def close(self):
        """Release the collection between sessions.

        The embedded database takes an **exclusive** lock on `context/qdrant/`. Holding it for
        the life of the process would mean the pre-flight panel could no longer read its own
        chunk count after the first meeting, and `build_index.py` could not run at all without
        quitting the app. So the lock is held for a session, not for a process.
        """
        if self.client is not None:
            knowledge_store._close(self.client)
            self.client = None
            self.load_error = "index not open"

    def analyze_dialogue(self, dialogue_chunk):
        """Score one utterance against the index and return the whole judgement, not just a hit.

        Returns a `Retrieval`. It carries three things the caller now needs and the old
        `str | None` threw away:

        - **the score**, because the liveness line reads it: a live index that matched nothing
          and a dead one are the same blank pane otherwise (V35, R36);
        - **whether the query ran at all**, which is the other half of that distinction (V34).

        `score=None` means no judgement was formed -- no index, or an utterance too short to be
        worth embedding. It is deliberately distinct from `score=0.0`, which means the query ran.
        """
        if not self.model or self.client is None:
            return Retrieval(ok=False, error=self.load_error or "index not loaded")

        # Ignore extremely short filler statements
        if not is_worth_embedding(dialogue_chunk):
            return Retrieval(ok=True)

        # Generate embedding for the incoming sentence
        start_time = time.time()
        try:
            query_vec = self.model.encode([dialogue_chunk], convert_to_numpy=True)[0]
            # Cosine is the collection's own metric, pinned at creation and verified at load,
            # so the score comes back on the scale SERVE_THRESHOLD is expressed in. Qdrant
            # normalises stored vectors for a cosine collection, which is why this matches the
            # `dot / norms` the pickle-era advisor computed by hand.
            hits = self.client.query_points(
                collection_name=knowledge_store.COLLECTION,
                query=[float(value) for value in query_vec],
                limit=1,
                with_payload=True,
            ).points
        except Exception as exc:
            # A remote collection can go away mid-meeting. That is a visible state, not a crash
            # on the poll thread (R39).
            logger.error("❌ [LocalAdvisor] Query failed: %s", exc)
            return Retrieval(ok=False, error=f"query failed: {type(exc).__name__}: {exc}")

        elapsed_ms = (time.time() - start_time) * 1000

        if not hits:
            logger.info(f"[LocalAdvisor] RAG returned no points in {elapsed_ms:.1f}ms")
            return Retrieval(ok=True, score=0.0)

        best = hits[0]
        best_score = float(best.score)

        # Log the score unconditionally for observability during tuning
        logger.info(f"[LocalAdvisor] RAG Similarity {best_score:.2f} (Threshold: {SERVE_THRESHOLD}) calculated in {elapsed_ms:.1f}ms for: '{dialogue_chunk}'")

        hint = None
        if best_score >= SERVE_THRESHOLD and best.id != self.last_matched_idx:
            # Repeat suppression is still a display decision, not a scoring one: the score is
            # returned either way, so a suppressed repeat no longer looks like a dead index.
            self.last_matched_idx = best.id
            hint = (best.payload or {}).get("text", "")

        return Retrieval(ok=True, score=best_score, hint=hint)
