#!/bin/bash
# cleanup_structure.sh — Remove dead files after structure simplification.
# Run from project root.

set -e
echo "🧹 Simplifying project structure..."

# 1. Delete gutted tool_registry.py
echo "  Removing server/tools/tool_registry.py (dead stub)..."
rm -f server/tools/tool_registry.py
git rm --cached server/tools/tool_registry.py 2>/dev/null || true

# 2. Delete client/llm/ directory (imports now go to server.llm directly)
echo "  Removing client/llm/ (was just a re-export)..."
rm -rf client/llm/
git rm -r --cached client/llm/ 2>/dev/null || true

# 3. Delete old permission_checker.py (merged into permissions.py)
echo "  Removing client/security/permission_checker.py (merged)..."
rm -f client/security/permission_checker.py
git rm --cached client/security/permission_checker.py 2>/dev/null || true

# 4. Delete this script
rm -f cleanup_structure.sh

echo ""
echo "✅ Done. Now run:"
echo "   git add -A"
echo "   git commit -m 'refactor: simplify project structure'"
echo "   git push"