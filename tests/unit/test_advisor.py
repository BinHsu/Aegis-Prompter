import pytest
import os
import pickle
import numpy as np
from src.local_advisor import LocalAdvisor

TEST_QA_CHUNK = "If the server crashes, reboot the AWS instance."

@pytest.fixture
def mock_knowledge_index(tmp_path):
    """
    Fixture: Creates a dummy knowledge index pickle file.
    """
    context_dir = tmp_path / "context"
    context_dir.mkdir()
    
    index_path = context_dir / "knowledge_index.pkl"
    
    # We create a dummy vector (length 384 for all-MiniLM)
    dummy_embedding = np.random.rand(1, 384).astype(np.float32)
    
    bundle = {
        "model_name": "all-MiniLM-L6-v2",
        "texts": [TEST_QA_CHUNK],
        "embeddings": dummy_embedding,
        "metadata": [{"source": "test.txt"}]
    }
    
    with open(index_path, 'wb') as f:
        pickle.dump(bundle, f)
        
    return str(context_dir)

def test_local_advisor_loading(mock_knowledge_index, monkeypatch):
    """Verify that the LocalAdvisor safely loads pickle dumps."""
    
    # Monkeypatch the advisor's target dir so it looks at our tmp_path
    monkeypatch.setattr("src.local_advisor.os.path.dirname", lambda x: mock_knowledge_index)
    
    # Needs to mock the SentenceTransformer to avoid downloading model during tests
    class MockModel:
        def __init__(self, name):
            pass
        def encode(self, texts, convert_to_numpy=True):
            return np.random.rand(1, 384).astype(np.float32)
            
    monkeypatch.setattr("src.local_advisor.SentenceTransformer", MockModel)
    
    advisor = LocalAdvisor()
    advisor.index_path = os.path.join(mock_knowledge_index, "knowledge_index.pkl")
    advisor.load_index()
    
    assert len(advisor.knowledge_texts) == 1
    assert advisor.knowledge_texts[0] == TEST_QA_CHUNK

def test_local_advisor_matching(mock_knowledge_index, monkeypatch):
    """Verify math works: Cosine similarity triggering."""
    monkeypatch.setattr("src.local_advisor.os.path.dirname", lambda x: mock_knowledge_index)
    
    # Mocking exact match embedding 
    class MockModelMatch:
        def __init__(self, name):
            pass
        def encode(self, texts, convert_to_numpy=True):
            # Return same vector as dummy
            return np.ones((1, 384)).astype(np.float32)
            
    monkeypatch.setattr("src.local_advisor.SentenceTransformer", MockModelMatch)
    
    advisor = LocalAdvisor()
    advisor.index_path = os.path.join(mock_knowledge_index, "knowledge_index.pkl")
    # Hack the bundle injection
    advisor.knowledge_texts = [TEST_QA_CHUNK]
    advisor.knowledge_embeddings = np.ones((1, 384)).astype(np.float32)
    advisor.model = MockModelMatch("mock")
    
    # Should perfect match (score=1.0) >= 0.65 threshold
    hint = advisor.analyze_dialogue("The server has crashed.")
    assert hint == TEST_QA_CHUNK
