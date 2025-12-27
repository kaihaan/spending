#!/bin/bash
# Code quality check script for the spending app
# Run this before committing code

set -e  # Exit on error

cd "$(dirname "$0")/.."  # Navigate to project root

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔍 Running Python Code Quality Checks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Activate virtual environment
source backend/venv/bin/activate

echo "📦 Checking with ruff..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd backend
ruff check . --statistics
echo ""

echo "🎨 Checking formatting..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
ruff format --check .
echo ""

echo "📝 Running type checks with pyright..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
cd ..
pyright --stats 2>&1 | grep -E "(error|warning|information|Files analyzed|Execution time)" || true
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Code quality check complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
