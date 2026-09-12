"""
Sanity-check retrieval against the FAISS index built by scripts/ingest.py,
before wiring it into the full app.

Usage:
    python scripts/query.py
    python scripts/query.py --k 6
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv()

INDEX_DIR = Path(__file__).resolve().parent.parent / "data" / "vector_store"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def main():
    parser = argparse.ArgumentParser(description="Query the FAISS knowledge base")
    parser.add_argument("--k", type=int, default=4, help="Number of chunks to retrieve (default: 4)")
    args = parser.parse_args()

    if not (INDEX_DIR / "index.faiss").exists():
        raise SystemExit(f"No index found at {INDEX_DIR}. Run scripts/ingest.py first.")

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectorstore = FAISS.load_local(
        str(INDEX_DIR), embeddings, allow_dangerous_deserialization=True
    )

    print(f"Loaded index. Type a question (or 'exit' to quit), retrieving top-{args.k} chunks.\n")

    while True:
        try:
            query = input("Query: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if query.lower() in {"exit", "quit"}:
            break
        if not query:
            continue

        results = vectorstore.similarity_search_with_score(query, k=args.k)
        for rank, (doc, score) in enumerate(results, start=1):
            print(f"\n--- #{rank} | score={score:.4f} | {doc.metadata.get('title')} ---")
            print(f"Source: {doc.metadata.get('source_url')}")
            preview = doc.page_content.strip().replace("\n", " ")
            print(preview[:300] + ("..." if len(preview) > 300 else ""))
        print()


if __name__ == "__main__":
    main()
