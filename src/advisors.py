"""Advisor backends: retrieval, generation, and the routing between them.

Two independently configurable slots (R28). The operator may fill neither, either or both, and
this module is the transport -- it does not decide which backend is appropriate, only which one
gets a given utterance.

**Deliberately light on imports.** stdlib only, and the retrieval backend is imported lazily
inside `build_advisor`. `app.py` renders advisor labels and liveness before a storage root
exists, and pulling `sentence_transformers` in to do that would defeat the boot ordering
(V19, V20) for the same reason `text_filters.py` and `audio_devices.py` are split out.

**The HTTP call is `urllib.request`, not `requests`.** `requests` is present in the venv only
because Streamlit depends on it; using an undeclared transitive dependency for the one network
call this product makes is how a working install turns into a broken one after an unrelated
upgrade. stdlib has everything needed here -- a JSON POST with a timeout.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger("Advisors")

# The three kinds of advisor output. They are not interchangeable and must never share a slot
# (V24, R42): retrieved text is pre-written and safe to read aloud, generated text is not
# (R30), and an override is a human instruction from the staff officer.
SOURCE_RETRIEVED = "retrieved"
SOURCE_GENERATED = "generated"
SOURCE_OVERRIDE = "override"
ADVICE_SOURCES = (SOURCE_OVERRIDE, SOURCE_RETRIEVED, SOURCE_GENERATED)

# How many retrieved cues may be shown at once. **Three, chosen by the operator 2026-08-21** on the
# measurement in **V112**: the right note is in the top three far more often than it is first, and
# the query already computed the ranking. Above three the cost is **R9** -- a speaker scanning a
# list is not reading a line -- and gated recall gains only 3 points from three to five (75.3% to
# 78.7% at fifty notes) while the average number of cues on screen rises to three. See
# `docs/decisions/0016`.
MAX_CUES = 3

# ===== The retrieval gate, and the absence of any other =====
#
# This answers one question -- "is this retrieved chunk about what was just said at all" -- and
# showing an unrelated pre-written answer is worse than showing nothing. It is not a band edge.
#
# **0.45, lowered from the 0.65 that shipped from Phase 6 until 2026-08-20, because 0.65 fired on
# nothing.** `0.65` was never measured against anything; **V22** recorded that the threshold *is*
# the intent judgement, not that this value was right. Measured with the real embedding model
# (**V95**, reproduced independently in **V100**): five paraphrases of indexed notes scored
# 0.366-0.634, so **every one of them fell below 0.65 and the retrieval slot fired zero times**,
# while five unrelated utterances scored 0.033-0.380. The populations barely overlap, and a sweep
# separates them here: at 0.45, four of five paraphrases fire and none of the five unrelated ones do.
#
# **Ties in that sweep were broken toward the higher threshold, and this value is the conservative
# end of the band that works.** A missed cue costs the speaker a cue; a false cue costs attention
# on a teleprompter, and **R9** is a claim about attention. 0.35 fires all five but admits one
# false positive; 0.45 gives up one cue to admit none.
#
# ⚠️ **Measured on ten utterances against five invented notes** -- enough to prove 0.65 fires
# nothing, and thin for choosing a replacement. `tools/probe_rag_cues.py` re-runs it in seconds and
# is in the overnight queue precisely so this number stops being unexamined. See
# `docs/decisions/0014`.
#
# **There is still deliberately no second threshold.** A three-band scheme gating the generative
# slot on this score was drafted and the operator dissolved it on 2026-08-12: neither backend wins,
# because they do not compete -- both are sent to, both are shown, each labelled with what produced
# it. `docs/decisions/0011` supersedes `0010`. **This change moves one number and reintroduces no
# band**; that 0.45 was also the dissolved scheme's lower edge is a coincidence of arithmetic.
SERVE_THRESHOLD = 0.45

# The instruction that permits returning nothing. A generative model produces output for every
# input (V23), so without this clause the advisor floods. It lives in source because it is a
# safety boundary rather than a preference, and R31 caps per-backend configuration at a host and
# a credential -- see the rejected-options table in REQUIREMENTS.md.
PASS_TOKEN = "PASS"
SYSTEM_PROMPT = (
    "You are a silent staff officer seated beside a speaker during a live hearing. You are shown "
    "the recent transcript of the room. Your output is displayed on a teleprompter the speaker "
    "may read from mid-sentence.\n"
    "\n"
    f"Most of the time the correct response is nothing. Reply with the single word {PASS_TOKEN} "
    "-- no punctuation, no explanation -- whenever the last line is small talk, an incomplete "
    "thought, a procedural remark, something the speaker plainly already knows, or anything you "
    "would have to guess at. Saying nothing is never a failure.\n"
    "\n"
    "When you do answer: at most two short sentences, phrased so they can be spoken aloud "
    "as-is. No preamble, no bullet points, no meta-commentary about the transcript.\n"
    "\n"
    f"Never invent a figure, date, name, statute or citation. If you would have to, answer "
    f"{PASS_TOKEN}.\n"
    "\n"
    "Answer in the language the last Participant line is spoken in. Never translate the "
    "transcript and never normalise it."
)


@dataclass(frozen=True)
class Retrieval:
    """What one retrieval query found, whether or not it cleared the bar.

    `score` is `None` when nothing was scored -- no index, or an utterance too short to be worth
    embedding. That is distinct from a score of 0.0, which means the query ran and matched
    nothing, and the distinction is exactly what R36 asks the liveness line to preserve.
    """

    ok: bool
    score: float = None
    hint: str = None
    error: str = ""
    # **Up to three cues, not one** (`docs/decisions/0016`). `hint` stays the top-ranked one so
    # every existing reader keeps working; `hints` carries the full set that cleared the gate, top
    # first, and `scores` runs parallel to it. Measured reason: the store already ranks every note
    # and the product was asking for one -- gated recall of the right note rises from 57% to 75% at
    # fifty notes purely by showing what was already computed (**V112**).
    hints: tuple = ()
    scores: tuple = ()


@dataclass(frozen=True)
class Advice:
    """One piece of advisor output, labelled with what produced it (R29, R30, R42)."""

    source: str
    text: str
    vendor: str = ""
    score: float = None


class AdvisorBackend:
    """The seam `global_state` already had, written down.

    A retrieval backend implements `analyze_dialogue(text) -> Retrieval`. It must be cheap
    enough to run on the poll thread, and it must never raise: a backend that throws on the
    worker thread takes the whole advisor down for the session.

    **Measured 2026-08-17 against the real index, because "microseconds" was written here and was
    wrong**: embedding 8.8 ms, vector search 0.9 ms. V29's microseconds describe the *dot
    product*, which turns out to be a tenth of the total -- the same shape as the latency figures
    this repository already caught measuring the minority term. Ten milliseconds on a loop that
    sleeps 300 ms is still cheap, so the design holds; the claim did not.
    """

    def analyze_dialogue(self, dialogue_chunk):  # pragma: no cover - interface
        raise NotImplementedError


# ===== The generative slot =====

def chat_endpoint(base_url):
    """Turn an operator-typed base URL into the completions endpoint (V28).

    Operators type what their runtime prints, and the runtimes disagree about whether `/v1` is
    part of the base: Ollama and LM Studio print it, some gateways do not. Guessing wrong yields
    a 404 that reads like "the model is wrong", so both forms are accepted.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


class LlmAdvisor:
    """OpenAI-compatible chat completions over stdlib HTTP (V28).

    One API covers Ollama, LM Studio, vLLM, llama.cpp and every cloud provider; local and remote
    differ only by URL, which is what makes R31 -- a host and a credential, nothing else --
    implementable without a vendor adapter per backend.
    """

    def __init__(self, base_url, api_key="", model="", timeout=8.0, opener=None):
        self.url = chat_endpoint(base_url)
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout
        # Injected in tests so the transport can be exercised without a server. Production
        # leaves it None and gets `urllib.request.urlopen`.
        self._opener = opener

    def _post(self, payload):
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST")
        request.add_header("Content-Type", "application/json")
        if self.api_key:
            request.add_header("Authorization", f"Bearer {self.api_key}")
        opener = self._opener or urllib.request.urlopen
        with opener(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def complete(self, messages, max_tokens=160):
        """Return `(text, error)`. Never raises -- an unreachable host is a liveness state.

        `max_tokens` is small on purpose: the prompt asks for at most two spoken sentences, and
        a runaway generation costs the speaker the one thing the live path owes them (R9).
        """
        payload = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "stream": False,
        }
        if self.model:
            payload["model"] = self.model
        try:
            data = self._post(payload)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            return "", f"HTTP {exc.code}{': ' + detail if detail else ''}"
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"

        try:
            choice = (data.get("choices") or [{}])[0]
            text = ((choice.get("message") or {}).get("content") or "").strip()
        except Exception:
            return "", "unrecognised response shape"
        return text, ""


REHEARSAL_DEFAULT = (
    "What is the timetable for the review?\n"
    "Thanks, that's helpful.\n"
    "Can you confirm the figure from last quarter?"
)


def rehearse(llm, questions):
    """Ask the operator's own endpoint their own questions, with the real prompt. `[dict]`.

    **The app does not judge the answers.** It shows what came back, how long it took, and
    whether the model declined; the operator decides whether that is worth reading aloud, which
    is the only party able to (`STATE.md`, open decision 2). Anything else would be the system
    under assessment assessing itself.

    The prompt is the production one, so what is rehearsed is what will happen. That is what
    makes **V23**'s flooding risk visible *here* rather than mid-hearing — a model that answers
    all three of these instead of declining the second one is a model that will not stop talking
    during a meeting, and no liveness signal would ever have shown that.
    """
    results = []
    for question in [q.strip() for q in (questions or "").splitlines() if q.strip()]:
        started = time.time()
        text, error = llm.complete(build_messages(f"Participant: {question}"))
        declined = (not error) and is_pass(text)
        results.append({
            "question": question,
            # Blank on a decline: `PASS` is the sentinel the prompt asks for, not something the
            # operator should be shown as though the model said it.
            "answer": "" if (error or declined) else text,
            "declined": declined,
            "error": error,
            "ms": (time.time() - started) * 1000,
        })
    return results


def build_messages(transcript):
    """The request body's messages. Separated so a test can read the prompt without a server.

    The transcript and nothing else. Retrieved chunks are deliberately **not** attached as
    grounding: the two slots do not feed each other, and coupling them would put the retrieval
    score back in the generative path by the back door -- see `docs/decisions/0011`.
    """
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "TRANSCRIPT (oldest first):\n" + transcript},
    ]


def is_pass(text):
    """Whether the model declined. Tolerant of the punctuation models add unbidden."""
    stripped = (text or "").strip().strip(".!。 \t\r\n").upper()
    return stripped == PASS_TOKEN or not stripped


# ===== Routing =====

@dataclass
class _Liveness:
    """What the pre-flight and running views read. Never the source of any decision."""

    rag_armed: bool = False
    rag_ok: bool = False
    rag_error: str = ""
    rag_last_score: float = None
    rag_queries: int = 0
    llm_armed: bool = False
    llm_state: str = "idle"      # idle | waiting | ok | empty | error
    llm_detail: str = ""
    llm_latency_ms: float = None
    llm_calls: int = 0
    llm_endpoint: str = ""
    llm_model: str = ""


class AdvisorPipeline:
    """Fans one utterance out to whichever slots are armed, and never blocks the caller.

    **Neither backend wins, because they do not compete.** Every Participant utterance goes to
    every armed slot: retrieval serves a cue when its own `SERVE_THRESHOLD` gate is cleared, the generative
    slot is sent to unconditionally, and both results are displayed in their own labelled pane.
    A three-band scheme gating the model on the retrieval score was drafted and dissolved by the
    operator on 2026-08-12 -- routing existed to pick a winner, and separate labelled outputs
    remove the competition rather than arbitrating it. `docs/decisions/0011` carries the
    reasoning; do not reintroduce a score gate here without superseding it.

    The generative slot therefore has no numeric gate at all. **The prompt is the threshold**
    (V23) and the operator has already seen how their own endpoint behaves -- that is what the
    pre-flight probe is for, and what makes R30's "unverified" a statement they have tested
    rather than a disclaimer. The transcript is bounded by construction at `max_history` (V26);
    do not raise that bound for the model's benefit without measuring, because past ~4096 tokens
    an Ollama backend truncates silently and answers confidently from a transcript it never saw
    (V32).

    The remote call runs on this object's own thread with a one-slot mailbox (V27). The old
    worker loop coalesced to "the newest utterance at the moment the previous call returned" as
    an accident of being synchronous; here it is the stated policy -- a newer utterance replaces
    a queued one, because advice about a line the room has moved past is worse than none.
    """

    def __init__(self, retriever=None, llm=None, on_advice=None,
                 serve_threshold=SERVE_THRESHOLD):
        self.retriever = retriever
        self.llm = llm
        self.on_advice = on_advice
        self.serve_threshold = serve_threshold

        self.liveness = _Liveness(
            rag_armed=retriever is not None,
            rag_ok=retriever is not None,
            llm_armed=llm is not None,
            llm_endpoint=getattr(llm, "url", "") or "",
            llm_model=getattr(llm, "model", "") or "",
        )

        self._lock = threading.Lock()
        self._wake = threading.Condition(self._lock)
        self._pending = None
        self._stopping = False
        self._thread = None
        if self.llm is not None:
            self._thread = threading.Thread(target=self._llm_loop, daemon=True,
                                            name="advisor-llm")
            self._thread.start()

    # --- called from the poll thread ---

    def submit(self, utterance, transcript=None):
        """Fan one Participant utterance out. Returns the `Retrieval` for the caller to log.

        Runs the retrieval query inline -- ~10 ms and local, measured -- and hands anything
        remote to the worker thread. This must not block: it is called from the loop that also
        notices Stop.
        """
        transcript = transcript if transcript is not None else utterance
        retrieval = self._retrieve(utterance)

        # One `Advice` per cue, each labelled with its own score, so the speaker can see which is
        # the strong match rather than being handed a merged block with a single number on it.
        for text, score in zip(retrieval.hints or ([retrieval.hint] if retrieval.hint else []),
                               retrieval.scores or ((retrieval.score,) if retrieval.hint else ())):
            self._emit(Advice(source=SOURCE_RETRIEVED, text=text,
                              vendor="knowledge index", score=score))

        if self.llm is None:
            return retrieval

        # Unconditional. Whatever retrieval did or did not find has no bearing on this: a
        # retrieved cue does not make the model redundant, and a failed lookup is not a reason
        # to send more. They are two slots, not two candidates.
        with self._wake:
            self._pending = transcript
            self.liveness.llm_state = "waiting"
            self._wake.notify()
        return retrieval

    def _retrieve(self, utterance):
        if self.retriever is None:
            return Retrieval(ok=False, error="not armed")
        try:
            retrieval = self.retriever.analyze_dialogue(utterance)
        except Exception as exc:
            # A backend that throws must not take the session's advisor down with it (R39).
            logger.error("❌ [Advisor] Retrieval backend raised: %s", exc)
            retrieval = Retrieval(ok=False, error=f"{type(exc).__name__}: {exc}")
        self.liveness.rag_ok = retrieval.ok
        self.liveness.rag_error = retrieval.error
        self.liveness.rag_last_score = retrieval.score
        self.liveness.rag_queries += 1
        return retrieval

    # --- the worker thread ---

    def _llm_loop(self):
        while True:
            with self._wake:
                while self._pending is None and not self._stopping:
                    self._wake.wait()
                if self._stopping:
                    return
                transcript = self._pending
                self._pending = None
            self._run_one(transcript)

    def _run_one(self, transcript):
        started = time.time()
        text, error = self.llm.complete(build_messages(transcript))
        elapsed_ms = (time.time() - started) * 1000
        self.liveness.llm_latency_ms = elapsed_ms
        self.liveness.llm_calls += 1

        if error:
            self.liveness.llm_state = "error"
            self.liveness.llm_detail = error
            logger.warning("⚠️ [Advisor] LLM call failed after %.0f ms: %s", elapsed_ms, error)
            return
        if is_pass(text):
            # The expected outcome, not a fault. R36 exists so that "declined" and "dead" do
            # not present identically.
            self.liveness.llm_state = "empty"
            self.liveness.llm_detail = ""
            logger.info("[Advisor] LLM declined in %.0f ms", elapsed_ms)
            return

        self.liveness.llm_state = "ok"
        self.liveness.llm_detail = ""
        logger.info("[Advisor] LLM returned %d chars in %.0f ms", len(text), elapsed_ms)
        self._emit(Advice(source=SOURCE_GENERATED, text=text,
                          vendor=self.llm.model or "LLM"))

    def _emit(self, advice):
        if self.on_advice is None:
            return
        try:
            self.on_advice(advice)
        except Exception as exc:
            logger.error("❌ [Advisor] Publishing advice failed: %s", exc)

    def shutdown(self, timeout=2.0):
        """Stop the worker. Idempotent, and safe when there never was one."""
        with self._wake:
            self._stopping = True
            self._pending = None
            self._wake.notify_all()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def status(self):
        """A snapshot for the UI (R36, R42). Plain dict so the renderer stays dumb."""
        live = self.liveness
        return {
            "rag": {
                "armed": live.rag_armed,
                "ok": live.rag_ok,
                "error": live.rag_error,
                "last_score": live.rag_last_score,
                "queries": live.rag_queries,
            },
            "llm": {
                "armed": live.llm_armed,
                "state": live.llm_state,
                "detail": live.llm_detail,
                "latency_ms": live.llm_latency_ms,
                "calls": live.llm_calls,
                "endpoint": live.llm_endpoint,
                "model": live.llm_model,
            },
        }


def build_advisor(settings, enable_rag=False, enable_llm=False, on_advice=None,
                  retriever=None, timeout=8.0):
    """Construct the pipeline for one session from what the operator armed and configured.

    `settings` is any mapping with the persisted keys -- `os.environ` in production, a dict in
    tests. `retriever` lets the caller pass an already-loaded index so a second session does not
    pay the embedding model load again.

    Returns `None` when neither slot is armed, which is the state Phase 6 already shipped: pure
    transcription, no advisor thread, nothing to fail.
    """
    if enable_rag and retriever is None:
        # Imported here, not at module scope: this is the line that pulls in
        # `sentence_transformers`, and `app.py` imports this module to render labels long before
        # a storage root exists (V19, V20).
        from local_advisor import LocalAdvisor
        retriever = LocalAdvisor()
    if not enable_rag:
        retriever = None

    llm = None
    if enable_llm:
        base_url = (settings.get("LLM_BASE_URL") or "").strip()
        if base_url:
            llm = LlmAdvisor(base_url=base_url,
                             api_key=settings.get("LLM_API_KEY") or "",
                             model=settings.get("LLM_MODEL") or "",
                             timeout=timeout)
        else:
            logger.warning("⚠️ [Advisor] Generative advisor armed with no LLM base URL; "
                           "that slot stays empty.")

    if retriever is None and llm is None:
        return None
    return AdvisorPipeline(retriever=retriever, llm=llm, on_advice=on_advice)
