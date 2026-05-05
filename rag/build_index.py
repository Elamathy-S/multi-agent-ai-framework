"""
rag/build_index.py — Build the ChromaDB vector index.

Run this once after installing dependencies, and again whenever
you add new documents to rag/documents.py.

Usage:
    cd "Masters Project/MCP "
    PYTHONPATH=. python3.12 rag/build_index.py

    # Force full rebuild:
    PYTHONPATH=. python3.12 rag/build_index.py --force
"""

import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description="Build the RAG policy index")
    parser.add_argument("--force", action="store_true", help="Rebuild from scratch")
    args = parser.parse_args()

    print("Finance MCP — RAG Index Builder")
    print("=" * 40)

    try:
        from rag.documents import DOCUMENTS
        from rag.embedder  import build_index

        print(f"Found {len(DOCUMENTS)} documents to index.")
        print(f"Categories: {list(set(d['category'] for d in DOCUMENTS))}")
        print()

        n = build_index(DOCUMENTS, force=args.force)
        print()
        print(f"✅ Done — {n} new documents indexed.")
        print()
        print("Test a query:")
        from rag.embedder import retrieve
        results = retrieve("what credit score do I need for a loan?", n_results=2)
        for r in results:
            print(f"  [{r['score']}] {r['title']}")

    except ImportError as e:
        print(f"❌ Missing dependency: {e}")
        print()
        print("Install with:")
        print("  pip install chromadb sentence-transformers")
        sys.exit(1)

if __name__ == "__main__":
    main()