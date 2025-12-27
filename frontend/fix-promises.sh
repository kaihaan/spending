#!/bin/bash
# Fix floating promises and misused promises

set -e
cd "$(dirname "$0")"

echo "🔧 Fixing promise-related errors..."

# Fix 1: Add void to floating promise calls
echo "1. Fixing floating promises..."
find src -type f \( -name "*.ts" -o -name "*.tsx" \) -exec sed -i -E '
  s/^(\s+)(fetchConnections|fetchAccounts|fetchData|fetchTransactions|fetchStatus|loadData|loadAccounts|syncAccounts|syncData|checkStatus|refreshData|handleRefresh)\(\);$/\1void \2();/g
' {} \;

# Fix 2: Fix misused promises in onClick handlers
echo "2. Fixing misused promises in event handlers..."
find src -type f -name "*.tsx" -exec perl -i -pe '
  s/onClick=\{(handle[A-Z][a-zA-Z]*)\}/onClick={() => void $1()}/g;
  s/onSubmit=\{(handle[A-Z][a-zA-Z]*)\}/onSubmit={() => void $1()}/g;
' {} \;

# Fix 3: Remove async from functions without await
echo "3. Fixing unnecessary async keywords..."
find src -type f \( -name "*.ts" -o -name "*.tsx" \) -exec sed -i -E '
  /async.*handleCallback/s/async //g
' {} \;

echo "✅ Applied automated fixes!"
echo ""
echo "Running lint check..."
npm run lint 2>&1 | tail -5
