#!/bin/bash
# Auto-fix code quality issues
# This will automatically fix import sorting, formatting, and some linting issues

set -e  # Exit on error

cd "$(dirname "$0")/.."  # Navigate to project root

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔧 Auto-fixing Python Code Quality Issues"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Activate virtual environment
source backend/venv/bin/activate

cd backend

echo "🎨 Formatting code with ruff..."
ruff format .
echo ""

echo "🔧 Auto-fixing linting issues..."
ruff check . --fix --show-fixes
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Auto-fix complete!"
echo ""
echo "💡 Run './scripts/check-code-quality.sh' to verify"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
