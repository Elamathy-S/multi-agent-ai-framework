"""
rag/embedder.py — RAG embedder using Ollama for embeddings.

Uses Ollama's embedding API (nomic-embed-text or any pulled model)
so no HuggingFace download is needed.
Falls back to TF-IDF if Ollama embeddings are unavailable.

Pull the embedding model once:
    ollama pull nomic-embed-text
"""

import os
import json
import pickle
import hashlib
import requests
import numpy as np
from pathlib import Path

BASE_DIR   = Path(__file__).parent
CHROMA_DIR = BASE_DIR / "chroma_db"
INDEX_FILE = BASE_DIR / "tfidf_index.pkl"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")


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
def _tfidf_index(documents: list[dict]) -> dict:
    """Build a simple TF-IDF index — no model download needed."""
    import math
    from collections import Counter

    corpus = [f"{d['title']} {d['content']}".lower() for d in documents]

    # Term frequency per document
    tf = []
    for doc in corpus:
        words = doc.split()
        counts = Counter(words)
        total  = len(words)
        tf.append({w: c / total for w, c in counts.items()})

    # Inverse document frequency
    all_words = set(w for doc in corpus for w in doc.split())
    idf = {}
    N = len(corpus)
    for word in all_words:
        df = sum(1 for doc in corpus if word in doc)
        idf[word] = math.log(N / (1 + df))

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

    words = query.lower().split()
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


# ── Public API ────────────────────────────────────────────────────────────
_index = None


def _load_index():
    global _index
    if _index is None and INDEX_FILE.exists():
        with open(INDEX_FILE, "rb") as f:
            _index = pickle.load(f)
    return _index


def build_index(documents: list[dict], force: bool = False) -> int:
    """Build and save the search index."""
    global _index

    if INDEX_FILE.exists() and not force:
        existing = _load_index()
        if existing and len(existing.get("documents", [])) == len(documents):
            print(f"Index up to date — {len(documents)} documents already indexed.")
            return 0

    print(f"Building index for {len(documents)} documents...")

    # Try Ollama embeddings first
    texts = [f"{d['title']}\n{d['content'].strip()}" for d in documents]
    embeddings = _ollama_embed(texts)

    if embeddings:
        print(f"✅ Using Ollama embeddings ({EMBED_MODEL})")
        _index = {
            "type": "ollama",
            "documents": documents,
            "embeddings": embeddings,
            "texts": texts,
        }
    else:
        print("⚠️  Ollama embeddings unavailable — using TF-IDF fallback")
        _index = _tfidf_index(documents)
        _index["type"] = "tfidf"

    with open(INDEX_FILE, "wb") as f:
        pickle.dump(_index, f)

    print(f"✅ Index saved to {INDEX_FILE}")
    print(f"   Type: {_index['type']}")
    print(f"   Documents: {len(documents)}")
    return len(documents)


def retrieve(query: str, n_results: int = 3, category: str = None) -> list[dict]:
    """Find most relevant policy documents for a query."""
    idx = _load_index()
    if not idx:
        return []

    # Filter by category first
    if category:
        docs = [d for d in idx["documents"] if d.get("category") == category]
        if not docs:
            return []

    if idx["type"] == "ollama":
        q_emb = _ollama_embed([query])
        if not q_emb:
            return []
        results = []
        for i, doc in enumerate(idx["documents"]):
            if category and doc.get("category") != category:
                continue
            score = _cosine_similarity(q_emb[0], idx["embeddings"][i])
            if score > 0.3:
                results.append({**doc, "score": round(score, 3)})
        results.sort(key=lambda x: -x["score"])
        return results[:n_results]

    else:  # tfidf
        if category:
            # Filter tfidf index by category
            filtered_idx = _tfidf_index(docs)
            results = _tfidf_query(filtered_idx, query, n_results)
            return results
        return _tfidf_query(idx, query, n_results)


def index_count() -> int:
    """Return number of documents indexed."""
    idx = _load_index()
    if not idx:
        return 0
    return len(idx.get("documents", []))