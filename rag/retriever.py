"""
rag/retriever.py — RAG retriever used by agents.

Provides a simple interface for agents to retrieve relevant policy context.
Handles the case where the index is not built yet (returns empty gracefully).
"""

from __future__ import annotations


def get_policy_context(query: str, category: str = None, n: int = 2) -> str:
    """
    Retrieve relevant policy documents for a query and format them
    as a context string ready to inject into an agent prompt.

    Args:
        query:    The agent's current question or reasoning step.
        category: Optional filter — 'loan', 'risk', 'fraud', 'trading'.
        n:        Number of documents to retrieve (default 2).

    Returns:
        Formatted string with relevant policy excerpts, or empty string
        if no relevant documents found or index not built.
    """
    try:
        from rag.embedder import retrieve
        docs = retrieve(query, n_results=n, category=category)
    except Exception as e:
        print(f"  [RAG] unavailable: {e}")
        return ""

    if not docs:
        print(f"  [RAG] no results for: {repr(query[:50])} category={category}")
        return ""

    print(f"  [RAG] retrieved {len(docs)} doc(s) for category={category}:")
    for doc in docs:
        print(f"        - {doc['title']} (score={doc['score']})")

    parts = ["Relevant policies from knowledge base:"]
    for doc in docs:
        text = doc["content"].strip()
        if len(text) > 600:
            text = text[:600] + "..."
        parts.append(f"\n[{doc['title']}] (relevance: {doc['score']})\n{text}")

    return "\n".join(parts)


def rag_available() -> bool:
    """Check if the RAG index is built and ready."""
    try:
        from rag.embedder import index_count
        return index_count() > 0
    except Exception:
        return False