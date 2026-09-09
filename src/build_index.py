import argparse
import os
import glob
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import bootstrap
import knowledge_store

# `HF_HOME` has to be exported before anything imports `huggingface_hub`, which freezes it at
# its own import time (V19). `sentence_transformers` pulls it in, so it is imported inside the
# function below rather than here -- the same ordering `app.py` relies on.
_SETTINGS = bootstrap.read_settings()
bootstrap.apply_environment(_SETTINGS)

DEFAULT_EMBEDDING_MODEL = bootstrap.FIELDS_BY_KEY["EMBEDDING_MODEL"].default


DEFAULT_DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "context", "docs")


def build_knowledge_index(model_name=None, docs_dir=None, settings=None):
    """
    Knowledge Compiler: Compiles md/txt files into the Qdrant knowledge collection using
    sentence-transformers. With no `QDRANT_URL` configured the collection is an embedded
    database under `context/qdrant/` and nothing leaves this machine.

    The embedding model is an argument, defaulting to the `EMBEDDING_MODEL` setting. It replaces
    the former `MULTILINGUAL_MODE` boolean, which never reached the ASR layer and only ever chose
    between two embedding models (V2, V3). The name chosen is recorded in the collection, which
    is what stops a query using a different model from returning confident nonsense (V36).
    """
    print("🚀 Starting Knowledge Base Compilation...")

    # 1. Determine the Model
    model_name = (model_name
                  or os.environ.get("EMBEDDING_MODEL", "").strip()
                  or DEFAULT_EMBEDDING_MODEL)
    print(f"📦 Loading Embedding Model: {model_name}")

    from sentence_transformers import SentenceTransformer

    # Load model (downloads if not locally cached in HF_HOME)
    model = SentenceTransformer(model_name)
    
    # 2. Gather Document Chunks. `docs_dir` and `settings` are arguments so this can be driven
    # against a throwaway directory in tests -- the real `context/` holds the operator's private
    # notes and is off limits to the suite.
    docs_dir = docs_dir or DEFAULT_DOCS_DIR
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
    sources = [c["source"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    # 3. Replace the collection. Replace rather than append: a rebuild after deleting a document
    # must not leave that document's vectors still answering questions.
    settings = settings if settings is not None else bootstrap.read_settings()
    target = knowledge_store.describe_target(settings)
    print(f"\n📤 Writing {len(texts)} chunks to {target}")
    count, error = knowledge_store.write_index(settings, texts, sources, embeddings, model_name)
    if error:
        print(f"❌ Compilation failed: {error}")
        return

    print(f"✅ Compilation Complete! {count} chunks in `{knowledge_store.COLLECTION}` "
          f"at {target}")
    print(f"   Distance metric: COSINE (pinned at creation — the match threshold is a cosine "
          f"similarity and means nothing under any other metric)")
    print(f"   Embedding model recorded in the collection: {model_name}")
    if os.path.exists(knowledge_store.LEGACY_PICKLE):
        # Left in place rather than deleted: it is the operator's data, and this script has no
        # business removing a file it no longer reads.
        print(f"\nℹ️ `{os.path.relpath(knowledge_store.LEGACY_PICKLE)}` is the old pickle index. "
              f"Nothing reads it any more; delete it when you are satisfied with this build.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compile context/docs into a vector index.")
    parser.add_argument(
        "--model", default=None,
        help=f"Embedding model to compile with. Defaults to the EMBEDDING_MODEL setting, "
             f"then to {DEFAULT_EMBEDDING_MODEL}.",
    )
    build_knowledge_index(parser.parse_args().model)
