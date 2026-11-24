"""tests/test_rag.py — Chunking and retrieval (offline TF-IDF path)."""

import pytest

from rag.chunking import chunk_document, chunk_documents
from rag.documents import DOCUMENTS
from rag.embedder import _tfidf_retrieve, _tokens


class TestChunking:

    def test_every_document_yields_multiple_chunks(self):
        assert all(len(chunk_document(d)) >= 2 for d in DOCUMENTS)

    def test_chunk_ids_are_unique_and_traceable(self):
        ids = [c["id"] for c in chunk_documents(DOCUMENTS)]
        assert len(ids) == len(set(ids))
        assert all("#" in i for i in ids)

    def test_chunks_keep_category_and_title(self):
        for c in chunk_documents(DOCUMENTS):
            assert c["category"] and c["title"] and c["content"].strip()

    def test_no_text_is_lost(self):
        for d in DOCUMENTS:
            joined = " ".join(c["content"] for c in chunk_document(d))
            assert _tokens(joined) == _tokens(d["content"])


class TestRetrieval:

    @pytest.mark.parametrize("query,category,expected_doc", [
        ("what actions are required for a high risk customer", "risk", "risk_policy_002"),
        ("when does a loan need escalation to the branch manager", "loan", "loan_policy_003"),
        ("how many transactions in one hour trigger a fraud flag", "fraud", "fraud_policy_001"),
    ])
    def test_top_result_comes_from_the_right_policy(self, query, category, expected_doc):
        hits = _tfidf_retrieve(query, 3, category)
        assert hits and hits[0]["id"].startswith(expected_doc)

    def test_category_filter_is_respected(self):
        assert all(h["category"] == "loan" for h in _tfidf_retrieve("interest rate", 5, "loan"))

    def test_nonsense_query_returns_nothing(self):
        assert _tfidf_retrieve("zzqx plmk", 3, None) == []
