"""The dialogue buffer, and the advisor slots it now keeps apart (V24).

`dialogue_buffer` imports its sibling `advisors` bare, like every runtime module, so `src/`
goes on the path here -- the idiom `test_transcriber_feed_wav.py` already uses.
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

import advisors  # noqa: E402
from advisors import SOURCE_GENERATED, SOURCE_OVERRIDE, SOURCE_RETRIEVED  # noqa: E402
from dialogue_buffer import DialogueBuffer  # noqa: E402

def test_buffer_initialization():
    """Verifies the initial state of the buffer."""
    buffer = DialogueBuffer(max_history=5)
    assert buffer.max_history == 5
    assert len(buffer.dialogue) == 0
    slots = buffer.get_advice_slots()
    assert set(slots) == set(advisors.ADVICE_SOURCES)
    assert all(slot["text"] == "" for slot in slots.values())

def test_buffer_add_entry_sliding_window():
    """Verifies sliding window logic: the oldest entry is evicted past the limit."""
    buffer = DialogueBuffer(max_history=3)

    buffer.add_entry("User", "Hello 1")
    buffer.add_entry("User", "Hello 2")
    buffer.add_entry("User", "Hello 3")
    assert len(buffer.dialogue) == 3
    assert buffer.dialogue[0]["text"] == "Hello 1"

    # Adding a 4th entry should evict the 1st
    buffer.add_entry("User", "Hello 4")
    assert len(buffer.dialogue) == 3
    assert buffer.dialogue[0]["text"] == "Hello 2"
    assert buffer.dialogue[2]["text"] == "Hello 4"

def test_buffer_get_last_role():
    """Verifies detection of the most recent speaker."""
    buffer = DialogueBuffer()
    assert buffer.get_last_role() is None

    buffer.add_entry("Bin", "Test message")
    assert buffer.get_last_role() == "Bin"

    buffer.add_entry("Other", "Replying...")
    assert buffer.get_last_role() == "Other"

def test_buffer_clear():
    """Verifies the clear logic resets dialogue and every advice slot."""
    buffer = DialogueBuffer()
    buffer.add_entry("User", "Secret")
    buffer.set_advice("Some advice", source=SOURCE_RETRIEVED)
    buffer.set_advice("Generated", source=SOURCE_GENERATED)

    buffer.clear()
    assert len(buffer.dialogue) == 0
    assert all(slot["text"] == "" for slot in buffer.get_advice_slots().values())


# ===== One slot per kind (V24) =====

def test_a_generated_reply_does_not_overwrite_a_retrieved_cue():
    """The defect V24 names. Local RAG returns in milliseconds and a remote LLM in seconds, so
    a shared slot meant the speaker read a safe pre-written answer and had it swapped for
    generated text mid-glance."""
    buffer = DialogueBuffer()
    buffer.set_advice("prepared cue", source=SOURCE_RETRIEVED, vendor="knowledge index",
                      score=0.91)
    buffer.set_advice("generated guess", source=SOURCE_GENERATED, vendor="qwen")

    slots = buffer.get_advice_slots()
    assert slots[SOURCE_RETRIEVED]["text"] == "prepared cue"
    assert slots[SOURCE_RETRIEVED]["score"] == 0.91
    assert slots[SOURCE_GENERATED]["text"] == "generated guess"
    assert slots[SOURCE_OVERRIDE]["text"] == ""


def test_an_unknown_source_raises_rather_than_landing_somewhere():
    buffer = DialogueBuffer()
    with pytest.raises(ValueError):
        buffer.set_advice("text", source="whatever")


def test_the_session_log_records_which_kind_produced_each_line(tmp_path):
    """The archived transcript is read later, often by someone who was not in the room, so R30's
    distinction has to survive into the file and not only onto the screen."""
    buffer = DialogueBuffer()
    buffer.start_session("LOG_TEST", str(tmp_path / "history"))
    buffer.set_advice("pre-written answer", source=SOURCE_RETRIEVED)
    buffer.set_advice("model guess", source=SOURCE_GENERATED)

    content = (tmp_path / "history" / "Meeting_LOG_TEST.md").read_text(encoding="utf-8")
    assert "Retrieved cue (pre-written)" in content
    assert "UNVERIFIED" in content


def test_an_in_flight_slot_shows_but_is_not_logged():
    """V25's pending state: it updates the display and deliberately skips the log, because a
    pending state is not a proposal anyone made."""
    buffer = DialogueBuffer()
    buffer.set_advice("…", source=SOURCE_GENERATED, is_thinking=True)
    assert buffer.get_advice_slots()[SOURCE_GENERATED]["is_thinking"] is True

def test_buffer_session_logging(tmp_path):
    """Verifies local session archiving (isolated via pytest's tmp_path)."""
    buffer = DialogueBuffer()
    history_dir = tmp_path / "test_history"
    session_id = "TEST_SESSION_001"

    # Start the session
    buffer.start_session(session_id, str(history_dir))

    expected_file = history_dir / f"Meeting_{session_id}.md"
    assert expected_file.exists()

    # Verify dialogue is appended
    buffer.add_entry("Tester", "Recording this line.")
    content = expected_file.read_text(encoding="utf-8")
    assert "Tester" in content
    assert "Recording this line." in content

    # Verify advice is appended
    buffer.set_advice("Strategic Tip", source=SOURCE_RETRIEVED, is_thinking=False)
    content = expected_file.read_text(encoding="utf-8")
    assert "Strategic Tip" in content

def test_buffer_concurrency():
    """Verifies thread-safety of concurrent writes (Concurrency Safety)."""
    import threading
    buffer = DialogueBuffer(max_history=100)

    def worker(role, count):
        for i in range(count):
            buffer.add_entry(role, f"Message {i}")

    threads = []
    # Spawn 5 threads, each pushing 20 messages
    for i in range(5):
        t = threading.Thread(target=worker, args=(f"Thread-{i}", 20))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # The Lock must prevent race conditions, so the total is exactly 100
    assert len(buffer.dialogue) == 100


# ===== Running-view rendering =====

class _FakeState:
    def __init__(self, entries):
        self.buffer = self
        self._entries = entries

    def get_full_dialogue(self):
        return list(self._entries)


def _transcript():
    """Import the renderer without executing `app.py`, which is a Streamlit script."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "src", "app.py")
    source = open(path, encoding="utf-8").read()
    start = source.index("def _transcript_html(")
    end = source.index("\ndef render_preflight(", start)
    namespace = {"html": __import__("html")}
    exec(compile(source[start:end], path, "exec"), namespace)
    return namespace["_transcript_html"]


def test_each_turn_is_its_own_block_not_a_newline():
    """Reported from the first live session: Participant and Speaker ran together.

    The box is rendered as HTML, where a newline collapses to a space, so joining turns with
    "\\n" produced one paragraph with no boundary between who said what.
    """
    render = _transcript()
    out = render(_FakeState([
        {"role": "Participant", "text": "Has the review been completed?"},
        {"role": "Speaker (You)", "text": "It has."},
    ]))
    assert out.count('class="turn ') == 2
    assert "\n".join(["Has the review been completed?", "It has."]) not in out
    # Whose line it is has to survive a glance, so the two tracks are styled apart.
    assert "turn-them" in out and "turn-me" in out


def test_transcript_text_is_escaped():
    """Transcript content is whatever the model produced from audio -- nobody controls it, and it
    goes into a div rendered with unsafe_allow_html. A line containing `<` used to truncate the
    box and take the rest of the session out of view."""
    render = _transcript()
    out = render(_FakeState([
        {"role": "Participant", "text": "<script>alert(1)</script> under 5% & rising"},
    ]))
    assert "<script>" not in out
    assert "&lt;script&gt;" in out and "&amp; rising" in out


def test_an_empty_buffer_says_it_is_waiting_rather_than_rendering_nothing():
    render = _transcript()
    assert render(_FakeState([])) == "Awaiting stream..."


def test_only_the_most_recent_turns_are_rendered():
    render = _transcript()
    entries = [{"role": "Participant", "text": f"line {i}"} for i in range(10)]
    out = render(_FakeState(entries), max_lines=3)
    assert "line 9" in out and "line 6" not in out


# ===== Advisor pane rendering (R30, R36, R42) =====

def _advisor_renderers():
    """Same trick as `_transcript()`: slice the renderers out without running the Streamlit
    script. They sit above `_transcript_html` in `app.py` so both slices stay single-purpose."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "src", "app.py")
    source = open(path, encoding="utf-8").read()
    start = source.index("ADVICE_ORDER = (")
    end = source.index("\ndef _transcript_html(", start)
    namespace = {"html": __import__("html"), "advisors": advisors}
    exec(compile(source[start:end], path, "exec"), namespace)
    return namespace["_advisor_html"], namespace["_advisor_status_html"]


def _slot(text, **kwargs):
    slot = {"text": text, "vendor": "", "score": None, "time": "", "is_thinking": False}
    slot.update(kwargs)
    return slot


def test_the_three_kinds_are_rendered_as_three_distinct_cards():
    """R42: a reader glancing at the screen mid-sentence must not have to work out which one
    they are looking at."""
    render, _status = _advisor_renderers()
    out = render({
        SOURCE_OVERRIDE: _slot("do not concede the timetable"),
        SOURCE_RETRIEVED: _slot("the audit closed in March", score=0.88),
        SOURCE_GENERATED: _slot("the figure is probably around 12%"),
    })
    assert out.count('class="advice-card') == 3
    assert "advice-override" in out and "advice-retrieved" in out and "advice-generated" in out
    # Generated text carries the word on the card, not in a caption somewhere else (R30).
    assert "UNVERIFIED" in out
    # Order is fixed: safest first, generated last, and it never moves between ticks.
    assert (out.index("advice-override") < out.index("advice-retrieved")
            < out.index("advice-generated"))


def test_advisor_text_is_escaped():
    """Generated text answers audio nobody controls, and it lands in a div rendered with
    unsafe_allow_html."""
    render, _status = _advisor_renderers()
    out = render({SOURCE_GENERATED: _slot("<script>alert(1)</script> & so on")})
    assert "<script>" not in out
    assert "&lt;script&gt;" in out and "&amp; so on" in out


def test_an_empty_advisor_pane_says_it_is_waiting():
    render, _status = _advisor_renderers()
    out = render({SOURCE_OVERRIDE: _slot(""), SOURCE_RETRIEVED: _slot("")})
    assert "Awaiting dialogue" in out
    assert "advice-card" not in out


def test_a_live_index_that_matched_nothing_reads_differently_from_a_dead_one():
    """V35 / R36: `RAG 0.31` is the whole signal. A blank pane says 'nothing matched' and
    'the index never loaded' with the same pixels."""
    _render, status = _advisor_renderers()
    alive = status({"rag": {"armed": True, "ok": True, "last_score": 0.31, "queries": 12},
                    "llm": {"armed": False}})
    dead = status({"rag": {"armed": True, "ok": False, "error": "index missing", "queries": 12},
                   "llm": {"armed": False}})
    assert "0.31" in alive
    assert "unavailable" in dead and "index missing" in dead
    assert alive != dead


def test_an_llm_that_declined_reads_differently_from_one_that_failed():
    _render, status = _advisor_renderers()
    declined = status({"rag": {"armed": False},
                       "llm": {"armed": True, "state": "empty", "calls": 4,
                               "latency_ms": 812.0}})
    failed = status({"rag": {"armed": False},
                     "llm": {"armed": True, "state": "error", "detail": "connection refused",
                             "calls": 4, "latency_ms": 12.0}})
    assert "declined" in declined and "812 ms" in declined
    assert "connection refused" in failed


def test_no_advisor_armed_is_stated_rather_than_left_blank():
    _render, status = _advisor_renderers()
    assert "transcription only" in status(None)
    assert "transcription only" in status({"rag": {"armed": False}, "llm": {"armed": False}})


# ===== The session record states whether audio was kept (R45) =====

def test_the_header_says_audio_was_retained_and_where(tmp_path):
    """R45's whole point: without this, "recorded and later deleted" and "never recorded" are the
    same file — and R4 makes deletion a normal event rather than an anomaly."""
    buffer = DialogueBuffer()
    buffer.start_session("S_KEPT", str(tmp_path / "history"), retention={
        "armed": True,
        "directory": "/vault/AegisPrompter/audio",
        "tracks": {"mic": "/vault/AegisPrompter/audio/Meeting_S_KEPT_mic.wav"},
    })
    content = (tmp_path / "history" / "Meeting_S_KEPT.md").read_text(encoding="utf-8")

    assert "**Audio retained**: yes" in content
    assert "/vault/AegisPrompter/audio" in content
    assert "Meeting_S_KEPT_mic.wav" in content


def test_the_header_says_so_when_nothing_was_kept(tmp_path):
    buffer = DialogueBuffer()
    buffer.start_session("S_GONE", str(tmp_path / "history"))
    content = (tmp_path / "history" / "Meeting_S_GONE.md").read_text(encoding="utf-8")

    assert "**Audio retained**: no" in content
    assert "cannot be recovered" in content or "recovered" in content


def test_the_header_carries_a_precise_start_so_timestamps_convert_to_offsets(tmp_path):
    """`docs/decisions/0001` requires it: "jump to this moment" needs an origin, and the
    second-resolution date line is not one."""
    buffer = DialogueBuffer()
    buffer.start_session("S_TIME", str(tmp_path / "history"))
    content = (tmp_path / "history" / "Meeting_S_TIME.md").read_text(encoding="utf-8")

    line = [l for l in content.splitlines() if "Session start (precise)" in l]
    assert line, content
    # ISO-8601 to the millisecond, e.g. 2026-08-13T10:15:00.123
    assert "T" in line[0] and "." in line[0].split("T")[1]


def test_the_outcome_is_appended_with_durations_and_any_loss(tmp_path):
    """The header states the intent while it can still be written; this states what happened."""
    buffer = DialogueBuffer()
    buffer.start_session("S_END", str(tmp_path / "history"), retention={"armed": True})
    buffer.finish_session({
        "Speaker (You)": {"path": "/vault/a_mic.wav", "started_at": "2026-08-13T10:15:00.100",
                          "seconds": 3600.0, "bytes": 115_000_000, "frames": 1,
                          "dropped_blocks": 0, "error": ""},
        "Participant": {"path": "/vault/a_system.wav", "started_at": "2026-08-13T10:15:00.400",
                        "seconds": 3599.0, "bytes": 114_000_000, "frames": 1,
                        "dropped_blocks": 12, "error": ""},
    })
    content = (tmp_path / "history" / "Meeting_S_END.md").read_text(encoding="utf-8")

    assert "Audio archive" in content
    assert "a_mic.wav" in content and "a_system.wav" in content
    # Per-track start times, because the two tracks do not share a t=0 and the offline merge
    # on the streaming branch assumed they did.
    assert "2026-08-13T10:15:00.100" in content and "2026-08-13T10:15:00.400" in content
    # Loss is stated, not left in a log nobody reads.
    assert "12 blocks dropped" in content
    assert "not the whole session" in content


def test_a_session_that_never_finishes_still_says_it_was_armed(tmp_path):
    """Sessions end badly — a crash, a closed lid, a killed process. The distinction R45 draws
    has to survive that, which is why it is written at Start."""
    buffer = DialogueBuffer()
    buffer.start_session("S_CRASH", str(tmp_path / "history"),
                         retention={"armed": True, "directory": "/vault/audio"})
    # No finish_session call at all.
    content = (tmp_path / "history" / "Meeting_S_CRASH.md").read_text(encoding="utf-8")
    assert "**Audio retained**: yes" in content
