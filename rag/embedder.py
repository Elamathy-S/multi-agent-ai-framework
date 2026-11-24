"""
rag/embedder.py — RAG retrieval backed by ChromaDB, with Ollama embeddings.

Pipeline
    index time : each policy document is embedded with Ollama (nomic-embed-text)
                 and stored in a persistent ChromaDB collection (cosine space).
                 A TF-IDF index is also built and saved as an offline fallback.
    query time : the query is embedded with the same model, ChromaDB returns the
                 nearest documents (optionally filtered by category), and results
                 below a relevance threshold are dropped.
    fallback   : if Ollama embeddings or ChromaDB are unavailable at query time,
                 retrieval falls back to an in-memory TF-IDF index (built on
                 first use, nothing is persisted) so agents still get context.
    chunking   : documents are split into sections (rag/chunking.py); each
                 section is one retrievable passage.

Pull the embedding model once:
    ollama pull nomic-embed-text
"""

import os
import re
import requests
import numpy as np
from pathlib import Path

BASE_DIR   = Path(__file__).parent
CHROMA_DIR = Path(os.getenv("RAG_CHROMA_DIR", BASE_DIR / "chroma_db"))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

COLLECTION_NAME = "policy_documents"
MIN_SIMILARITY  = 0.3      # drop semantic matches weaker than this


# ── Try to use Ollama embeddings ──────────────────────────────────────────
def _ollama_embed(texts: list[str]) -> list[list[float]] | None:
    """Get embeddings from Ollama. Returns None if unavailable."""
    try:
        embeddings = []
        for text in texts:
            resp = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=30,
            )
            if resp.status_code == 200:
                embeddings.append(resp.json()["embedding"])
            else:
                return None
        return embeddings
    except Exception:
        return None


def _cosine_similarity(a: list, b: list) -> float:
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


# ── TF-IDF fallback ───────────────────────────────────────────────────────
def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$]+", text.lower())


def _tfidf_index(documents: list[dict]) -> dict:
    """Build a simple TF-IDF index — no model download needed."""
    import math
    from collections import Counter

    corpus = [_tokens(f"{d['title']} {d['content']}") for d in documents]

    # Term frequency per document
    tf = []
    for words in corpus:
        counts = Counter(words)
        total  = len(words)
        tf.append({w: c / total for w, c in counts.items()})

    # Inverse document frequency
    all_words = set(w for doc in corpus for w in doc)
    idf = {}
    N = len(corpus)
    for word in all_words:
        df = sum(1 for doc in corpus if word in doc)
        idf[word] = math.log(1 + N / df)

    # TF-IDF vectors
    vectors = []
    for tf_doc in tf:
        vec = {w: tf_doc.get(w, 0) * idf.get(w, 0) for w in all_words}
        vectors.append(vec)

    return {"corpus": corpus, "vectors": vectors, "idf": idf,
            "documents": documents, "all_words": list(all_words)}


def _tfidf_query(index: dict, query: str, n: int) -> list[dict]:
    """Score query against TF-IDF index using cosine similarity."""
    import math
    from collections import Counter

    words = _tokens(query)
    if not words:
        return []
    counts = Counter(words)
    total  = len(words)
    all_words = set(index["all_words"])
    idf = index["idf"]

    q_vec = {w: (counts[w] / total) * idf.get(w, 0) for w in words if w in all_words}

    scores = []
    for i, doc_vec in enumerate(index["vectors"]):
        common = set(q_vec.keys()) & set(doc_vec.keys())
        dot = sum(q_vec[w] * doc_vec[w] for w in common)
        q_norm  = math.sqrt(sum(v**2 for v in q_vec.values()))
        d_norm  = math.sqrt(sum(v**2 for v in doc_vec.values()))
        sim = dot / (q_norm * d_norm) if q_norm * d_norm > 0 else 0
        scores.append((i, sim))

    scores.sort(key=lambda x: -x[1])
    results = []
    for i, score in scores[:n]:
        if score > 0.01:
            doc = index["documents"][i]
            results.append({**doc, "score": round(score, 3)})
    return results


# ── ChromaDB helpers ──────────────────────────────────────────────────────
def _get_collection(create: bool = False, reset: bool = False):
    """Return the Chroma collection, or None if chromadb is unavailable."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        if reset:
            try:
                client.delete_collection(COLLECTION_NAME)
            except Exception:
                pass
        if create or reset:
            return client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},   # distance = 1 - cosine similarity
            )
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        return None


def _chroma_count() -> int:
    col = _get_collection()
    try:
        return col.count() if col is not None else 0
    except Exception:
        return 0


# ── TF-IDF fallback index (in memory) ───────────────────────────────────────────────────────────────────────────
_index = None
_category_cache: dict[str, dict] = {}  # category → cached TF-IDF index


def _load_index():
    """Build the TF-IDF index in memory on first use (the corpus is small)."""
    global _index
    if _index is None:
        from rag.chunking import chunk_documents
        from rag.documents import DOCUMENTS
        _index = _tfidf_index(chunk_documents(DOCUMENTS))
    return _index


def _tfidf_retrieve(query: str, n_results: int, category: str | None) -> list[dict]:
    idx = _load_index()
    if not idx:
        return []
    if category:
        if category not in _category_cache:
            docs = [d for d in idx["documents"] if d.get("category") == category]
            if not docs:
                return []
            _category_cache[category] = _tfidf_index(docs)
        return _tfidf_query(_category_cache[category], query, n_results)
    return _tfidf_query(idx, query, n_results)


# ── Public API ────────────────────────────────────────────────────────────
def build_index(documents: list[dict], force: bool = False) -> int:
    """Chunk the documents and build the ChromaDB collection from them."""
    global _index
    from rag.chunking import chunk_documents

    _category_cache.clear()
    chunks = chunk_documents(documents)
    _index = _tfidf_index(chunks)          # keep the in-memory fallback fresh

    if not force and _chroma_count() == len(chunks):
        print(f"Index up to date — {len(chunks)} chunks already indexed.")
        return 0

    print(f"Building index: {len(documents)} documents -> {len(chunks)} chunks...")
    documents = chunks

    texts = [f"{d['title']}\n{d['content'].strip()}" for d in documents]
    embeddings = _ollama_embed(texts)
    if not embeddings:
        # Drop any stale collection so retrieval uses the fresh TF-IDF index
        # instead of serving outdated vectors.
        _get_collection(reset=True)
        print("⚠️  Ollama embeddings unavailable — retrieval will use TF-IDF only")
        return len(documents)

    col = _get_collection(reset=True)
    if col is None:
        print("⚠️  chromadb unavailable — retrieval will use TF-IDF only")
        return len(documents)

    col.add(
        ids=[d["id"] for d in documents],
        embeddings=embeddings,
        documents=[d["content"].strip() for d in documents],
        metadatas=[{"category": d.get("category", ""), "title": d["title"], "doc_id": d["doc_id"]} for d in documents],
    )
    print(f"✅ ChromaDB collection '{COLLECTION_NAME}' built with {EMBED_MODEL}")
    print(f"   Location:  {CHROMA_DIR}")
    print(f"   Documents: {col.count()}")
    return len(documents)


def _chroma_retrieve(query: str, n_results: int, category: str | None):
    """Semantic search in ChromaDB. Returns None if it cannot be used."""
    col = _get_collection()
    if col is None:
        return None
    q_emb = _ollama_embed([query])
    if not q_emb:
        return None
    try:
        total = col.count()
        if total == 0:
            return None
        res = col.query(
            query_embeddings=q_emb,
            n_results=min(n_results, total),
            where={"category": category} if category else None,
        )
    except Exception:
        return None

    results = []
    for doc_id, content, meta, dist in zip(
        res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
    ):
        score = 1.0 - dist                      # cosine distance → similarity
        if score > MIN_SIMILARITY:
            results.append({
                "id": doc_id,
                "category": meta.get("category", ""),
                "title": meta.get("title", ""),
                "content": content,
                "score": round(score, 3),
            })
    results.sort(key=lambda r: -r["score"])
    return results


def retrieve(query: str, n_results: int = 3, category: str = None) -> list[dict]:
    """Find the most relevant policy documents for a query.

    Uses ChromaDB (semantic search). If embeddings or ChromaDB are unavailable,
    falls back to the TF-IDF index.
    """
    results = _chroma_retrieve(query, n_results, category)
    if results is not None:
        return results
    return _tfidf_retrieve(query, n_results, category)


def index_count() -> int:
    """Return number of documents indexed (ChromaDB, else TF-IDF fallback)."""
    count = _chroma_count()
    if count:
        return count
    idx = _load_index()
    return len(idx.get("documents", [])) if idx else 0