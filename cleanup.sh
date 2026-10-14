#!/bin/bash
# cleanup.sh — Run once from the project root.
# Keeps data files (DB, indexes) so the project runs immediately after clone.
# Only removes build artifacts and dead code.

set -e
echo "🧹 Cleaning up project..."

# 1. Remove __pycache__ from git tracking and disk
echo "  Removing __pycache__ directories..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
git rm -r --cached '*/__pycache__' 2>/dev/null || true
git rm -r --cached '__pycache__' 2>/dev/null || true

# 2. Remove .DS_Store
echo "  Removing .DS_Store files..."
find . -name ".DS_Store" -delete 2>/dev/null || true
git rm --cached .DS_Store 2>/dev/null || true
git rm --cached '*/.DS_Store' 2>/dev/null || true

# 3. Remove .pyc files
echo "  Removing .pyc files..."
find . -name "*.pyc" -delete 2>/dev/null || true

# 4. Remove duplicate llm_engine.py (client copy is dead code)
echo "  Removing duplicate client/llm/llm_engine.py..."
rm -f client/llm/llm_engine.py
git rm --cached client/llm/llm_engine.py 2>/dev/null || true

# 5. Remove broken test file
echo "  Removing broken server/tools/test_tools.py..."
rm -f server/tools/test_tools.py
git rm --cached server/tools/test_tools.py 2>/dev/null || true

# 6. Remove gutted executor (fully replaced by MCPClient)
echo "  Removing deprecated client/mcp/executor.py..."
rm -f client/mcp/executor.py
git rm --cached client/mcp/executor.py 2>/dev/null || true

echo ""
echo "✅ Done. Now run:"
echo "   git add -A"
echo "   git commit -m 'chore: remove build artifacts and dead code'"