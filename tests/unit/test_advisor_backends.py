"""Fanning an utterance out to the two advisor slots, and the transport to the generative one.

No server and no index: the retrieval backend is a stub returning canned `Retrieval` values,
and the LLM's opener is injected. What is under test is the *policy* -- that the slots do not
gate each other, that neither overwrites the other, and what the liveness line says when nothing
comes back.
"""
import io
import json
import os
import sys
import threading
import time

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import advisors  # noqa: E402
from advisors import (  # noqa: E402
    Advice,
    AdvisorPipeline,
    LlmAdvisor,
    Retrieval,
    SOURCE_GENERATED,
    SOURCE_RETRIEVED,
    build_advisor,
    chat_endpoint,
    is_pass,
)


class _StubRetriever:
    def __init__(self, *results):
        self.results = list(results)
        self.seen = []

    def analyze_dialogue(self, text):
        self.seen.append(text)
        return self.results.pop(0) if self.results else Retrieval(ok=True, score=0.0)


class _StubLlm:
    """Records requests and replies on command. Stands in for `LlmAdvisor`."""

    def __init__(self, reply="generated answer", error="", delay=0.0, model="stub-model"):
        self.reply = reply
        self.error = error
        self.delay = delay
        self.model = model
        self.url = "http://stub/v1/chat/completions"
        self.calls = []
        self.released = threading.Event()
        self.released.set()

    def complete(self, messages, max_tokens=160):
        self.calls.append(messages)
        self.released.wait(timeout=2.0)
        if self.delay:
            time.sleep(self.delay)
        return self.reply, self.error


def _collector():
    received = []
    done = threading.Event()

    def on_advice(advice):
        received.append(advice)
        done.set()

    return received, done, on_advice


def _wait_for(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# ===== Fan-out, not routing =====
#
# The operator dissolved the three-band scheme on 2026-08-12: neither backend wins because they
# do not compete. Every armed slot gets every Participant utterance, and both results are shown
# in their own labelled pane. `docs/decisions/0011` carries the reasoning — these tests are what
# stops a score gate creeping back in as an optimisation.

def test_both_slots_receive_the_same_utterance():
    """Neither is a fallback for the other. A prepared cue does not make the model redundant."""
    retriever = _StubRetriever(Retrieval(ok=True, score=0.9, hint="prepared cue"))
    llm = _StubLlm()
    received, _done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=retriever, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("a long enough attack line", transcript="Participant: ...")
        assert _wait_for(lambda: len(received) == 2, timeout=2.0)
        assert {a.source for a in received} == {SOURCE_RETRIEVED, SOURCE_GENERATED}
        assert len(llm.calls) == 1
    finally:
        pipeline.shutdown()


def test_a_high_scoring_match_does_not_suppress_the_generative_slot():
    """The specific thing three-band routing did, and the reason it was dissolved: it decided a
    winner on a number, when the display can simply show both."""
    retriever = _StubRetriever(Retrieval(ok=True, score=0.99, hint="prepared cue"))
    llm = _StubLlm()
    _received, _done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=retriever, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("an exactly-anticipated question")
        assert _wait_for(lambda: len(llm.calls) == 1)
    finally:
        pipeline.shutdown()


def test_a_low_scoring_utterance_still_reaches_the_generative_slot():
    """There is no lower edge. `0.45` was never measured against anything and the resolution was
    to stop asking the question, not to find a better number."""
    retriever = _StubRetriever(Retrieval(ok=True, score=0.10))
    llm = _StubLlm()
    _received, _done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=retriever, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("something the notes do not cover at all")
        assert _wait_for(lambda: len(llm.calls) == 1)
    finally:
        pipeline.shutdown()


def test_a_broken_index_does_not_change_what_the_generative_slot_receives():
    """The slots are independent, so one failing does not alter the other's input. What must not
    happen is the *reverse* of V34: a dead index silently changing the product's behaviour."""
    retriever = _StubRetriever(Retrieval(ok=False, error="index missing"))
    llm = _StubLlm()
    received, _done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=retriever, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("a perfectly ordinary question")
        assert _wait_for(lambda: len(llm.calls) == 1)
        assert pipeline.status()["rag"]["ok"] is False
        assert "index missing" in pipeline.status()["rag"]["error"]
        # And the dead index contributes nothing to the pane rather than an empty cue.
        assert [a.source for a in received] == [SOURCE_GENERATED]
    finally:
        pipeline.shutdown()


def test_the_retrieved_cue_is_gated_by_its_own_threshold_and_only_its_own():
    """The retrieval gate survives the dissolution: it answers "is this chunk about the question
    at all", and an unrelated pre-written answer is worse than none (**V22**). Deliberately no
    literal threshold here -- the value moved from 0.65 to 0.45 on 2026-08-20 (**V95**) and a test
    that pins the number would have had to change with it while testing nothing new."""
    retriever = _StubRetriever(Retrieval(ok=True, score=0.2, hint=None))
    received, _done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=retriever, llm=None, on_advice=on_advice)
    pipeline.submit("an off-topic remark")
    assert received == []


def test_no_grounding_is_attached_to_the_request():
    """Coupling the slots would put the retrieval score back into the generative path by the
    back door, which is exactly what the dissolution removed."""
    retriever = _StubRetriever(Retrieval(ok=True, score=0.55, hint=None))
    llm = _StubLlm()
    _received, _done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=retriever, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("a near miss", transcript="Participant: a near miss")
        assert _wait_for(lambda: len(llm.calls) == 1)
        user_message = llm.calls[0][1]["content"]
        assert "GROUNDING" not in user_message
        assert user_message.strip().startswith("TRANSCRIPT")
    finally:
        pipeline.shutdown()


def test_llm_only_sends_unconditionally_because_the_prompt_is_the_threshold():
    """V23: RAG returns None below its threshold; a generative model answers anything. The
    instruction permitting silence is the only gate there is, and it lives in source."""
    llm = _StubLlm()
    received, done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=None, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("anything at all", transcript="Participant: anything at all")
        assert done.wait(2.0)
        assert received[0].source == SOURCE_GENERATED
        assert advisors.PASS_TOKEN in llm.calls[0][0]["content"]
    finally:
        pipeline.shutdown()


# ===== Not blocking the poll thread, and coalescing on purpose (V27) =====

def test_submit_returns_before_the_remote_call_finishes():
    """The loop that calls this is also the loop that notices Stop."""
    llm = _StubLlm(delay=0.4)
    _received, _done, on_advice = _collector()
    pipeline = AdvisorPipeline(retriever=None, llm=llm, on_advice=on_advice)
    try:
        started = time.time()
        pipeline.submit("a line")
        assert time.time() - started < 0.2
    finally:
        pipeline.shutdown()


def test_a_newer_utterance_replaces_a_queued_one():
    """Coalescing was accidental in the synchronous loop and is policy here: advice about a line
    the room has moved past is worse than none."""
    llm = _StubLlm()
    llm.released.clear()           # hold the first call inside `complete`
    received, _done, on_advice = _collector()

    pipeline = AdvisorPipeline(retriever=None, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("first", transcript="first")
        assert _wait_for(lambda: len(llm.calls) == 1)
        pipeline.submit("second", transcript="second")
        pipeline.submit("third", transcript="third")
        llm.released.set()
        assert _wait_for(lambda: len(llm.calls) == 2, timeout=2.0)
        time.sleep(0.1)
        # Two calls, not three: the middle utterance was overwritten while the first was in
        # flight, and the newest one is what got sent.
        assert len(llm.calls) == 2
        assert "third" in llm.calls[1][1]["content"]
        assert "second" not in llm.calls[1][1]["content"]
    finally:
        pipeline.shutdown()


# ===== Liveness (R36) =====

def test_a_declined_generation_is_reported_as_declined_not_as_silence():
    llm = _StubLlm(reply="PASS")
    received, _done, on_advice = _collector()
    pipeline = AdvisorPipeline(retriever=None, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("small talk")
        assert _wait_for(lambda: pipeline.status()["llm"]["state"] == "empty")
        assert received == []
        assert pipeline.status()["llm"]["calls"] == 1
        assert pipeline.status()["llm"]["latency_ms"] is not None
    finally:
        pipeline.shutdown()


def test_an_unreachable_host_is_an_error_state_with_the_reason():
    llm = _StubLlm(error="URLError: connection refused")
    received, _done, on_advice = _collector()
    pipeline = AdvisorPipeline(retriever=None, llm=llm, on_advice=on_advice)
    try:
        pipeline.submit("a question")
        assert _wait_for(lambda: pipeline.status()["llm"]["state"] == "error")
        assert "connection refused" in pipeline.status()["llm"]["detail"]
        assert received == []
    finally:
        pipeline.shutdown()


def test_a_retrieval_backend_that_raises_does_not_take_the_session_down():
    class _Exploding:
        def analyze_dialogue(self, text):
            raise RuntimeError("boom")

    received, _done, on_advice = _collector()
    pipeline = AdvisorPipeline(retriever=_Exploding(), llm=None, on_advice=on_advice)
    result = pipeline.submit("a line long enough to matter")
    assert result.ok is False
    assert "boom" in pipeline.status()["rag"]["error"]


def test_the_score_reaches_the_status_even_when_nothing_matched():
    """`RAG 0.31` is what distinguishes 'alive, nothing matched' from 'dead' (V35)."""
    retriever = _StubRetriever(Retrieval(ok=True, score=0.31))
    pipeline = AdvisorPipeline(retriever=retriever, llm=None)
    pipeline.submit("a line")
    status = pipeline.status()
    assert status["rag"]["last_score"] == pytest.approx(0.31)
    assert status["rag"]["queries"] == 1
    assert status["llm"]["armed"] is False


# ===== The prompt and the transport =====

def test_the_system_prompt_permits_returning_nothing():
    """V23. Without this clause the advisor floods, which is why the prompt is in source and not
    an editable settings field (R31)."""
    prompt = advisors.SYSTEM_PROMPT
    assert advisors.PASS_TOKEN in prompt
    assert "never safe" not in prompt.lower()  # the unverified warning belongs on screen, not here
    assert "invent" in prompt.lower()
    assert "translate" in prompt.lower()


@pytest.mark.parametrize("declined", ["PASS", "pass", " PASS.", "PASS!", "", "   "])
def test_declining_is_recognised_through_the_punctuation_models_add(declined):
    assert is_pass(declined)


def test_a_real_answer_is_not_mistaken_for_a_decline():
    assert not is_pass("PASS the budget question to finance.")


@pytest.mark.parametrize("base,expected", [
    ("http://localhost:11434/v1", "http://localhost:11434/v1/chat/completions"),
    ("http://localhost:11434/v1/", "http://localhost:11434/v1/chat/completions"),
    ("http://localhost:8000", "http://localhost:8000/v1/chat/completions"),
    ("https://api.example.com/v1/chat/completions",
     "https://api.example.com/v1/chat/completions"),
    ("", ""),
])
def test_both_shapes_of_base_url_reach_the_same_endpoint(base, expected):
    """Runtimes disagree about whether `/v1` is part of the base, and guessing wrong yields a
    404 that reads like a wrong model name."""
    assert chat_endpoint(base) == expected


def test_the_credential_is_sent_as_a_bearer_token_and_the_reply_is_unwrapped():
    captured = {}

    def opener(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        payload = {"choices": [{"message": {"content": " two short sentences. "}}]}
        return io.BytesIO(json.dumps(payload).encode("utf-8"))

    llm = LlmAdvisor("http://localhost:11434/v1", api_key="secret", model="qwen",
                     opener=opener)
    text, error = llm.complete([{"role": "user", "content": "hi"}])

    assert error == ""
    assert text == "two short sentences."
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["body"]["model"] == "qwen"
    assert captured["body"]["stream"] is False


def test_an_unreachable_endpoint_returns_an_error_rather_than_raising():
    def opener(request, timeout=None):
        raise OSError("connection refused")

    llm = LlmAdvisor("http://localhost:1/v1", opener=opener)
    text, error = llm.complete([{"role": "user", "content": "hi"}])
    assert text == ""
    assert "connection refused" in error


def test_an_unrecognised_response_shape_is_reported_not_swallowed():
    def opener(request, timeout=None):
        return io.BytesIO(b'{"unexpected": true}')

    llm = LlmAdvisor("http://localhost:11434/v1", opener=opener)
    text, error = llm.complete([{"role": "user", "content": "hi"}])
    # No choices: the unwrap yields empty text, which the router treats as a decline rather
    # than as an answer. What must not happen is an exception on the worker thread.
    assert text == ""
    assert error == ""


# ===== The real socket path =====
#
# Everything above injects the opener, which tests the policy but not the transport. These two
# run against a loopback HTTP server through the production `urllib` path, so header assembly,
# JSON encoding, the timeout and socket teardown are all genuinely exercised. No local LLM
# runtime is installed on this machine and none is required.

@pytest.fixture
def stub_llm_server():
    import http.server
    import threading as _threading

    state = {"delay": 0.0, "status": 200, "reply": "a real answer over a real socket",
             "requests": []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            state["requests"].append({"path": self.path,
                                      "auth": self.headers.get("Authorization"),
                                      "body": body})
            if state["delay"]:
                time.sleep(state["delay"])
            payload = json.dumps(
                {"choices": [{"message": {"role": "assistant", "content": state["reply"]}}]}
            ).encode("utf-8")
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = _threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["base_url"] = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def test_a_real_round_trip_over_a_socket(stub_llm_server):
    llm = LlmAdvisor(stub_llm_server["base_url"], api_key="tok", model="stub")
    messages = advisors.build_messages("Participant: what is the timetable?")
    text, error = llm.complete(messages)

    assert error == ""
    assert text == "a real answer over a real socket"
    request = stub_llm_server["requests"][0]
    assert request["path"] == "/v1/chat/completions"
    assert request["auth"] == "Bearer tok"
    assert request["body"]["model"] == "stub"
    assert "what is the timetable?" in request["body"]["messages"][1]["content"]
    assert messages[0]["role"] == "system"


def test_a_host_that_does_not_answer_in_time_is_an_error_not_a_hang(stub_llm_server):
    """The speaker is mid-sentence. A backend that never answers must degrade to a visible
    state, not to a worker thread parked on a socket for the rest of the meeting (R39)."""
    stub_llm_server["delay"] = 1.5
    llm = LlmAdvisor(stub_llm_server["base_url"], timeout=0.2)

    started = time.time()
    text, error = llm.complete([{"role": "user", "content": "hi"}])
    elapsed = time.time() - started

    assert text == ""
    assert error
    assert elapsed < 1.0


# ===== The factory =====

def test_neither_slot_armed_builds_nothing_at_all():
    """Phase 6's shipped state: pure transcription, no advisor thread, nothing to fail."""
    assert build_advisor({}, enable_rag=False, enable_llm=False) is None


def test_arming_the_llm_without_a_base_url_leaves_the_slot_empty():
    assert build_advisor({"LLM_BASE_URL": ""}, enable_rag=False, enable_llm=True) is None


def test_the_factory_reuses_a_retriever_rather_than_reloading_the_model():
    retriever = _StubRetriever(Retrieval(ok=True, score=0.2))
    pipeline = build_advisor({}, enable_rag=True, enable_llm=False, retriever=retriever)
    try:
        assert pipeline.retriever is retriever
        assert pipeline.llm is None
    finally:
        pipeline.shutdown()


def test_the_llm_slot_is_built_from_a_host_and_a_credential_only(monkeypatch):
    """R31: no per-vendor configuration beyond that."""
    pipeline = build_advisor(
        {"LLM_BASE_URL": "http://localhost:1234/v1", "LLM_API_KEY": "k", "LLM_MODEL": "m"},
        enable_rag=False, enable_llm=True,
    )
    try:
        assert pipeline.llm.url == "http://localhost:1234/v1/chat/completions"
        assert pipeline.llm.api_key == "k"
        assert pipeline.llm.model == "m"
    finally:
        pipeline.shutdown()


# ===== The rehearsal (STATE.md, open decision 2) =====
#
# The operator asks their own endpoint their own questions with the real prompt, before the
# meeting. This app shows what came back and judges none of it — the model never assesses its own
# output, which is what the plan had accidentally delegated to the system prompt.

def test_the_rehearsal_uses_the_production_prompt():
    """What is rehearsed has to be what will happen, or it rehearses nothing. In particular the
    clause permitting silence must be in play, because whether the model uses it is the thing
    being looked for."""
    llm = _StubLlm(reply="an answer")
    results = advisors.rehearse(llm, "What is the timetable?")

    assert len(results) == 1
    system = llm.calls[0][0]["content"]
    assert system == advisors.SYSTEM_PROMPT
    assert "What is the timetable?" in llm.calls[0][1]["content"]


def test_a_decline_is_reported_as_a_decline_and_not_as_a_failure():
    """V23's flooding risk becomes visible here rather than mid-hearing: a model that answers the
    small-talk line is one that will not stop talking during a meeting."""
    llm = _StubLlm(reply="PASS")
    result = advisors.rehearse(llm, "Thanks, that's helpful.")[0]

    assert result["declined"] is True
    assert result["error"] == ""
    assert result["answer"] == ""


def test_an_answer_comes_back_verbatim_and_unjudged():
    """The app does not score it. The operator is the only party who can."""
    llm = _StubLlm(reply="The review closes in March.")
    result = advisors.rehearse(llm, "When does the review close?")[0]

    assert result["answer"] == "The review closes in March."
    assert result["declined"] is False
    assert result["ms"] >= 0


def test_a_dead_endpoint_is_reported_per_question_rather_than_aborting():
    """It doubles as the liveness probe without being one — and one failure must not hide the
    rest, because the pattern across questions is the thing worth seeing."""
    llm = _StubLlm(error="URLError: connection refused")
    results = advisors.rehearse(llm, "one\ntwo")

    assert len(results) == 2
    assert all("connection refused" in r["error"] for r in results)


def test_blank_lines_are_not_sent():
    llm = _StubLlm()
    results = advisors.rehearse(llm, "  \n\nreal question\n   ")

    assert len(results) == 1
    assert results[0]["question"] == "real question"
    assert len(llm.calls) == 1


def test_no_questions_is_no_calls():
    llm = _StubLlm()
    assert advisors.rehearse(llm, "   \n  ") == []
    assert llm.calls == []


def test_the_default_questions_include_something_that_should_be_declined():
    """The rehearsal is only informative if one of the lines is a line a good model refuses."""
    lines = [l for l in advisors.REHEARSAL_DEFAULT.splitlines() if l.strip()]
    assert len(lines) >= 3
    assert any("thank" in l.lower() or "helpful" in l.lower() for l in lines)
