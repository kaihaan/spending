-- Migration: Remove lookup_description column
-- Date: 2025-12-21
-- Description: Removes the deprecated lookup_description column from truelayer_transactions
--              and transactions tables. All data is now stored in transaction_enrichment_sources.

-- Step 1: Create backup table for rollback (preserves non-null values only)
CREATE TABLE IF NOT EXISTS _backup_lookup_description AS
SELECT id, lookup_description
FROM truelayer_transactions
WHERE lookup_description IS NOT NULL;

-- Step 2: Verify migration completeness (run manually before proceeding)
-- This query should return 0 if all lookup_description data has enrichment_sources entries:
--
-- SELECT COUNT(*) as orphaned_lookup_descriptions
-- FROM truelayer_transactions tt
-- WHERE tt.lookup_description IS NOT NULL
--   AND tt.id NOT IN (
--     SELECT DISTINCT truelayer_transaction_id
--     FROM transaction_enrichment_sources
--     WHERE truelayer_transaction_id IS NOT NULL
--   );

-- Step 3: Drop the column from truelayer_transactions
ALTER TABLE truelayer_transactions DROP COLUMN IF EXISTS lookup_description;

-- Step 4: Drop the column from legacy transactions table (if exists)
ALTER TABLE transactions DROP COLUMN IF EXISTS lookup_description;

-- Step 5: Drop any indexes on lookup_description (if they exist)
DROP INDEX IF EXISTS idx_truelayer_transactions_lookup;
DROP INDEX IF EXISTS idx_transactions_lookup_description;

-- Verification query (run after migration):
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'truelayer_transactions' AND column_name = 'lookup_description';
-- Should return 0 rows.

-- Rollback instructions (if needed):
-- 1. ALTER TABLE truelayer_transactions ADD COLUMN lookup_description TEXT;
-- 2. UPDATE truelayer_transactions t
--    SET lookup_description = b.lookup_description
--    FROM _backup_lookup_description b
--    WHERE t.id = b.id;
-- 3. DROP TABLE _backup_lookup_description;
