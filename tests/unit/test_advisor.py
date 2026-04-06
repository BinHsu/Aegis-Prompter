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
def mock_context_dir(tmp_path):
    """
    Fixture：建立一個帶有虛擬 QA 資料夾的 Advisor
    """
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    qa_file = context_dir / "qa.md"
    qa_file.write_text(TEST_QA_CONTENT, encoding="utf-8")
    
    return str(context_dir)

@pytest.fixture
def advisor_with_mock_qa(mock_context_dir, mocker):
    """
    Fixture：建立一個帶有虛擬 QA 資料夾的 Advisor (關閉快取連線以避免網路延遲)
    """
    mock_client = mocker.patch("google.genai.Client")
    mock_client.return_value.caches.create.return_value.name = "cachedChunks/mock_123"
    advisor = GeminiAdvisor(context_dir=mock_context_dir)
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
    
def test_advisor_dynamic_knowledge_and_caching_fallback(tmp_path, mocker):
    """驗證當 knowledge.md 存在但快取建立失敗時，是否正確 Fallback 定義 external_context"""
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    
    # 建構一個 knowledge.md 指向另一個外部資料夾
    ext_knowledge_dir = tmp_path / "ext_knowledge"
    ext_knowledge_dir.mkdir()
    (ext_knowledge_dir / "design.md").write_text("Ext Design patterns context here", encoding="utf-8")
    
    knowledge_file = context_dir / "knowledge.md"
    knowledge_file.write_text(str(ext_knowledge_dir), encoding="utf-8")
    
    # 模擬快取失敗
    mock_client = mocker.patch("google.genai.Client")
    mock_instance = mock_client.return_value
    mock_instance.caches.create.side_effect = Exception("Mocked Cache Error")
    
    advisor = GeminiAdvisor(context_dir=str(context_dir))
    
    # 依據使用者需求，如果快取失敗，直接放棄知識庫，避免拖慢效能。
    assert advisor.cached_content_name is None
    assert "Ext Design patterns context here" not in advisor.system_instruction

def test_advisor_caching_success(tmp_path, mocker):
    """驗證當知識庫讀取成功且快取成功時，不進入 Fallback"""
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    
    ext_knowledge_dir = tmp_path / "ext_knowledge"
    ext_knowledge_dir.mkdir()
    (ext_knowledge_dir / "docs.txt").write_text("Huge text context...", encoding="utf-8")
    
    (context_dir / "knowledge.md").write_text(str(ext_knowledge_dir), encoding="utf-8")
    
    # 模擬快取成功
    mock_client = mocker.patch("google.genai.Client")
    mock_instance = mock_client.return_value
    mock_cache = mocker.Mock()
    mock_cache.name = "cachedChunks/mock_123"
    mock_instance.caches.create.return_value = mock_cache
    
    advisor = GeminiAdvisor(context_dir=str(context_dir))
    
    assert advisor.cached_content_name == "cachedChunks/mock_123"
    # Fallback 未觸發，所以 Huge text context 不會出現在 system_instruction 中
    assert "Huge text context..." not in advisor.system_instruction
