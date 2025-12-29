-- Migration: Fix gmail_transaction_matches.match_method column length
-- Date: 2025-12-27
-- Issue: Match method strings exceeded VARCHAR(30) limit causing 276 failed matches
-- Solution: Expand to VARCHAR(100) to accommodate longer method names like
--           "exact_amount_date_merchant_early_receipt" (40 chars)

-- Expand match_method column to prevent truncation
ALTER TABLE gmail_transaction_matches
ALTER COLUMN match_method TYPE VARCHAR(100);

-- Add comment documenting the change
COMMENT ON COLUMN gmail_transaction_matches.match_method IS
  'Match algorithm method used (max 100 chars, increased from 30 to support early_receipt suffix)';
