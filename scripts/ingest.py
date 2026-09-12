"""
Builds the FAISS knowledge-base index from the scraped docs.

Pipeline: read markdown -> split into overlapping chunks -> embed each
chunk -> store vectors + text + metadata in a FAISS index on disk.

Usage:
    python scripts/ingest.py
"""
import os
from pathlib import Path

import frontmatter
import tiktoken
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings

RAW_DOCS_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"
INDEX_DIR = Path(__file__).resolve().parent.parent / "data" / "vector_store"

load_dotenv()

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "500"))
CHUNK_OVERLAP_TOKENS = int(os.getenv("CHUNK_OVERLAP_TOKENS", "50"))

_encoding = tiktoken.get_encoding("cl100k_base")


def token_len(text: str) -> int:
    return len(_encoding.encode(text))


def load_documents() -> list[Document]:
    """Read every scraped .md file and split it into overlapping chunks.

    Each chunk becomes its own Document, tagged with the source title/URL
    so the final app can show "this fact came from X" citations.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE_TOKENS,
        chunk_overlap=CHUNK_OVERLAP_TOKENS,
        length_function=token_len,
    )

    all_chunks: list[Document] = []
    md_files = sorted(RAW_DOCS_DIR.glob("*.md"))
    if not md_files:
        raise SystemExit(f"No .md files found in {RAW_DOCS_DIR}. Run scripts/scrape.py first.")

    for path in md_files:
        post = frontmatter.load(path)
        title = post.get("title", path.stem)
        source_url = post.get("source_url", "")

        chunks = splitter.split_text(post.content)
        for i, chunk in enumerate(chunks):
            all_chunks.append(
                Document(
                    page_content=chunk,
                    metadata={"title": title, "source_url": source_url, "chunk_index": i},
                )
            )
        print(f"{path.name}: {len(chunks)} chunks")

    return all_chunks


def main():
    documents = load_documents()
    print(f"\nTotal chunks: {len(documents)}")

    print(f"Loading embedding model '{EMBEDDING_MODEL}' (first run downloads it, ~90MB)...")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    print("Embedding chunks and building FAISS index...")
    vectorstore = FAISS.from_documents(documents, embeddings)

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(INDEX_DIR))
    print(f"Saved FAISS index -> {INDEX_DIR}")


if __name__ == "__main__":
    main()
