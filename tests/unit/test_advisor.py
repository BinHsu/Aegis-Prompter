import pytest
import os
from src.gemini_advisor import GeminiAdvisor

# 指向一個臨時的測試用 QA 銀行
TEST_QA_CONTENT = """
# 🛡️ Test QA Bank
## Q1. What is your favorite color?
* **標準答案：** "Architect blue."

## Q2. How to handle a crash?
* **標準答案：** "Stay calm and check the logs."
"""

@pytest.fixture
def advisor_with_mock_qa(tmp_path):
    """
    Fixture：建立一個帶有虛擬 QA 資料夾的 Advisor
    """
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    qa_file = context_dir / "qa.md"
    qa_file.write_text(TEST_QA_CONTENT, encoding="utf-8")
    
    # 建立 Advisor，並注入測試目錄
    advisor = GeminiAdvisor()
    advisor.qa_index = [] # 清空預設的
    advisor._index_qa_bank(str(context_dir))
    return advisor

def test_advisor_local_index_parsing(advisor_with_mock_qa):
    """驗證本地 QA 索引解析是否正確"""
    index = advisor_with_mock_qa.qa_index
    assert len(index) == 2
    assert "color" in index[0]["keywords"]
    assert "crash" in index[1]["keywords"]

def test_advisor_local_hint_matching(advisor_with_mock_qa):
    """驗證零延遲本地匹配邏輯"""
    # 測試命中 Q1
    header, answer = advisor_with_mock_qa.get_local_hint("Tell me your favorite color?")
    assert "Q1" in header
    assert "Architect blue" in answer
    
    # 測試命中 Q2
    header, answer = advisor_with_mock_qa.get_local_hint("There is a server crash!")
    assert "Q2" in header
    assert "Stay calm" in answer

    # 測試未命中
    assert advisor_with_mock_qa.get_local_hint("What's for dinner?") is None

def test_advisor_gemini_mocking(mocker, advisor_with_mock_qa):
    """
    🔥 重點測試：如何 Mock Gemini API
    """
    # 1. 模擬 GenerateContentResponse 型別
    mock_response = mocker.Mock()
    mock_response.text = "Mocked AI Strategy: Keep building."
    
    # 2. 攔截 generate_content 方法
    mock_client = mocker.patch("google.genai.Client")
    # 設定 return_value 鏈條：client.models.generate_content(...) -> mock_response
    # 注意：這裡如果是 sync 呼叫，直接攔截 analyze_dialogue_sync 呼叫下的內容
    mocker.patch.object(advisor_with_mock_qa.client.models, 'generate_content', return_value=mock_response)
    
    # 3. 呼叫同步分析
    result = advisor_with_mock_qa.analyze_dialogue_sync("Simulation start.")
    
    # 4. 驗證
    assert result == "Mocked AI Strategy: Keep building."
    # 驗證是否真的呼叫到了 Client (即便在 Mock 狀態下)
    advisor_with_mock_qa.client.models.generate_content.assert_called_once()
