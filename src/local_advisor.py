import os
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
import logging
import time

logger = logging.getLogger("LocalAdvisor")

class LocalAdvisor:
    """
    Pure Local RAG Advisor.
    Loads the pre-compiled `knowledge_index.pkl` into memory and performs 
    ultra-fast cosine similarity matching against the latest transcribed dialogue.
    No network dependencies.
    """
    def __init__(self):
        self.index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context", "knowledge_index.pkl")
        self.model = None
        self.knowledge_texts = []
        self.knowledge_embeddings = None
        
        # We hold state to prevent repeatedly throwing the same hint
        self.last_matched_idx = -1
        
        self.load_index()

    def load_index(self):
        """Loads the compiled knowledge array and its corresponding model."""
        if not os.path.exists(self.index_path):
            logger.warning(f"⚠️ [LocalAdvisor] Knowledge index not found at {self.index_path}. Please run `build_index.py` first.")
            return

        try:
            with open(self.index_path, 'rb') as f:
                bundle = pickle.load(f)
            
            self.knowledge_texts = bundle["texts"]
            self.knowledge_embeddings = bundle["embeddings"]
            model_name = bundle["model_name"]
            
            logger.info(f"📦 [LocalAdvisor] Loading local embedding model: {model_name}...")
            self.model = SentenceTransformer(model_name)
            logger.info(f"✅ [LocalAdvisor] Ready! Loaded {len(self.knowledge_texts)} chunks into memory.")
        except Exception as e:
            logger.error(f"❌ [LocalAdvisor] Failed to load index: {e}")

    def analyze_dialogue(self, dialogue_chunk):
        """
        Embeds the incoming statement and checks if it closely matches any pre-written cue.
        Returns the matching cue text if similarity > threshold, else None.
        """
        if not self.model or self.knowledge_embeddings is None or not dialogue_chunk.strip():
            return None
            
        # Ignore extremely short filler statements
        if len(dialogue_chunk.strip()) < 10:
            return None

        # Generate embedding for the incoming sentence
        start_time = time.time()
        query_vec = self.model.encode([dialogue_chunk], convert_to_numpy=True)[0]
        
        # Calculate Cosine Similarity across the entire database instantly
        # Cosine similarity = dot(A, B) / (norm(A) * norm(B))
        # sentence-transformers outputs normalized vectors by default if configured, 
        # but let's calculate safely.
        norms_a = np.linalg.norm(query_vec)
        norms_b = np.linalg.norm(self.knowledge_embeddings, axis=1)
        
        if norms_a == 0:
            return None
            
        similarities = np.dot(self.knowledge_embeddings, query_vec) / (norms_a * norms_b)
        
        best_match_idx = np.argmax(similarities)
        best_score = similarities[best_match_idx]
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        THRESHOLD = 0.65  # 0.65 to 0.75 is typical for semantic matching in MTEB spaces
        
        if best_score >= THRESHOLD:
            logger.debug(f"[LocalAdvisor] RAG Similarity {best_score:.2f} calculated in {elapsed_ms:.1f}ms")
            if best_match_idx != self.last_matched_idx:
                self.last_matched_idx = best_match_idx
                return self.knowledge_texts[best_match_idx]
                
        return None
