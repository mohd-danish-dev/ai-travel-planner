"""
Loads the FAISS index built by scripts/ingest.py and exposes a simple
retrieval function for the orchestrator.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

INDEX_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "vector_store"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_vectorstore: FAISS | None = None


def load_index() -> FAISS:
    """Loads the FAISS index once and caches it for the process lifetime."""
    global _vectorstore
    if _vectorstore is None:
        if not (INDEX_DIR / "index.faiss").exists():
            raise RuntimeError(
                f"No FAISS index found at {INDEX_DIR}. Run scripts/ingest.py first."
            )
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        _vectorstore = FAISS.load_local(
            str(INDEX_DIR), embeddings, allow_dangerous_deserialization=True
        )
    return _vectorstore


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Returns the top-k chunks for a query as {text, title, source_url} dicts."""
    vectorstore = load_index()
    results = vectorstore.similarity_search(query, k=k)
    return [
        {
            "text": doc.page_content,
            "title": doc.metadata.get("title"),
            "source_url": doc.metadata.get("source_url"),
        }
        for doc in results
    ]
