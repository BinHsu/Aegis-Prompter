import pytest
import os
import shutil
from src.dialogue_buffer import DialogueBuffer

def test_buffer_initialization():
    """驗證緩衝區初始化狀態"""
    buffer = DialogueBuffer(max_history=5)
    assert buffer.max_history == 5
    assert len(buffer.dialogue) == 0
    assert buffer.advice == "等待對話..."
    assert buffer.is_thinking is False

def test_buffer_add_entry_sliding_window():
    """驗證滑動窗口邏輯：超過上限時應彈出舊對話"""
    buffer = DialogueBuffer(max_history=3)
    
    buffer.add_entry("User", "Hello 1")
    buffer.add_entry("User", "Hello 2")
    buffer.add_entry("User", "Hello 3")
    assert len(buffer.dialogue) == 3
    assert buffer.dialogue[0]["text"] == "Hello 1"
    
    # 加入第 4 句，第 1 句應被彈出
    buffer.add_entry("User", "Hello 4")
    assert len(buffer.dialogue) == 3
    assert buffer.dialogue[0]["text"] == "Hello 2"
    assert buffer.dialogue[2]["text"] == "Hello 4"

def test_buffer_get_last_role():
    """驗證最後發言者偵測"""
    buffer = DialogueBuffer()
    assert buffer.get_last_role() is None
    
    buffer.add_entry("Bin", "Test message")
    assert buffer.get_last_role() == "Bin"
    
    buffer.add_entry("Other", "Replying...")
    assert buffer.get_last_role() == "Other"

def test_buffer_clear():
    """驗證清除邏輯"""
    buffer = DialogueBuffer()
    buffer.add_entry("User", "Secret")
    buffer.set_advice("Some advice", is_thinking=True)
    
    buffer.clear()
    assert len(buffer.dialogue) == 0
    assert buffer.advice == "等待對話..."
    assert buffer.is_thinking is False

def test_buffer_session_logging(tmp_path):
    """驗證本地存檔功能（使用 pytest 的 tmp_path 確保環境隔離）"""
    buffer = DialogueBuffer()
    history_dir = tmp_path / "test_history"
    session_id = "TEST_SESSION_001"
    
    # 啟動 Session
    buffer.start_session(session_id, str(history_dir))
    
    expected_file = history_dir / f"Meeting_{session_id}.md"
    assert expected_file.exists()
    
    # 測試對話追加
    buffer.add_entry("Tester", "Recording this line.")
    content = expected_file.read_text(encoding="utf-8")
    assert "Tester" in content
    assert "Recording this line." in content
    
    # 測試建議追加
    buffer.set_advice("Strategic Tip", is_thinking=False)
    content = expected_file.read_text(encoding="utf-8")
    assert "Strategic Tip" in content
