import pytest
import os
import shutil
from src.dialogue_buffer import DialogueBuffer

def test_buffer_initialization():
    """Verifies the initial state of the buffer."""
    buffer = DialogueBuffer(max_history=5)
    assert buffer.max_history == 5
    assert len(buffer.dialogue) == 0
    assert buffer.advice == "Awaiting dialogue..."
    assert buffer.is_thinking is False

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
    """Verifies the clear logic resets dialogue and advice state."""
    buffer = DialogueBuffer()
    buffer.add_entry("User", "Secret")
    buffer.set_advice("Some advice", is_thinking=True)

    buffer.clear()
    assert len(buffer.dialogue) == 0
    assert buffer.advice == "Awaiting dialogue..."
    assert buffer.is_thinking is False

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
    buffer.set_advice("Strategic Tip", is_thinking=False)
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
