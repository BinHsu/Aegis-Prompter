import os
import glob
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

def build_knowledge_index():
    """
    Knowledge Compiler: Compiles md/txt files into a vector index using sentence-transformers.
    This creates `context/knowledge_index.pkl` for fast runtime lookup.
    """
    print("🚀 Starting Knowledge Base Compilation...")
    
    # 1. Determine the Model
    is_multilingual = os.environ.get("MULTILINGUAL_MODE", "false").lower() == "true"
    model_name = "paraphrase-multilingual-MiniLM-L12-v2" if is_multilingual else "all-MiniLM-L6-v2"
    print(f"📦 Loading Embedding Model: {model_name}")
    
    # Load model (downloads if not locally cached in HF_HOME)
    model = SentenceTransformer(model_name)
    
    # 2. Gather Document Chunks
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context", "docs")
    if not os.path.exists(docs_dir):
        os.makedirs(docs_dir)
        print(f"⚠️ Created empty docs directory at {docs_dir}. Please place .txt/.md files there.")
        return
        
    md_files = glob.glob(os.path.join(docs_dir, "*.md")) + glob.glob(os.path.join(docs_dir, "*.txt"))
    
    if not md_files:
        print("⚠️ No documents found in `context/docs/`. Skipping compilation.")
        return
        
    chunks = []
    print("\n📄 Parsing Files:")
    for filepath in md_files:
        filename = os.path.basename(filepath)
        print(f"  - {filename}")
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Simple heuristic chunking: Split by double newlines (paragraphs/headers)
            raw_chunks = [c.strip() for c in content.split("\n\n") if len(c.strip()) > 10]
            for block in raw_chunks:
                chunks.append({
                    "source": filename,
                    "text": block
                })

    if not chunks:
        print("⚠️ No valid text chunks extracted.")
        return
        
    print(f"\n🧠 Generating vectors for {len(chunks)} chunks...")
    texts = [c["text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    
    # 3. Save as serialized pickle package
    export_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context", "knowledge_index.pkl")
    bundle = {
        "model_name": model_name,
        "texts": texts,
        "embeddings": embeddings,
        "metadata": [{"source": c["source"]} for c in chunks]
    }
    
    with open(export_path, 'wb') as f:
        pickle.dump(bundle, f)
        
    print(f"✅ Compilation Complete! Index saved to: {export_path}")
    print(f"   Bundle size: {os.path.getsize(export_path) / 1024:.2f} KB")

if __name__ == "__main__":
    build_knowledge_index()
