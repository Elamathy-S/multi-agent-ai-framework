"""
rag/chunking.py — Split policy documents into retrievable passages.

Embedding a whole document into one vector blurs distinct rules together and
returns far more text than the question needs. Each blank-line-separated
section ("Risk Score Bands:", "Escalation Path:", ...) becomes its own chunk,
prefixed with the document title so it stays self-explanatory.
"""

from __future__ import annotations

import re


def chunk_document(doc: dict) -> list[dict]:
    blocks = [b.strip() for b in re.split(r"\n\s*\n", doc["content"].strip()) if b.strip()]
    if not blocks:
        return []

    # The first block is usually just the document heading; fold it into the next one.
    if len(blocks) > 1 and len(blocks[0].splitlines()) == 1:
        blocks = [f"{blocks[0]}\n{blocks[1]}"] + blocks[2:]

    chunks = []
    for i, block in enumerate(blocks):
        chunks.append({
            "id": f"{doc['id']}#{i}",
            "doc_id": doc["id"],
            "category": doc.get("category", ""),
            "title": doc["title"],
            "content": block,
        })
    return chunks


def chunk_documents(docs: list[dict]) -> list[dict]:
    return [c for d in docs for c in chunk_document(d)]
