-- Migration: Add pre_enrichment_status column for tracking match source
-- Date: 2025-12-05
-- Purpose: Track whether transactions need Apple/Amazon matching before LLM enrichment
--
-- Status values:
--   'None'     - Not from a matchable source (default)
--   'Matched'  - Already matched with Apple/Amazon/Returns data
--   'Apple'    - Apple App Store transaction not yet matched
--   'AMZN'     - Amazon purchase not yet matched
--   'AMZN RTN' - Amazon return not yet matched

-- Add pre_enrichment_status column to truelayer_transactions
ALTER TABLE truelayer_transactions
ADD COLUMN IF NOT EXISTS pre_enrichment_status VARCHAR(20)
    CHECK (pre_enrichment_status IN ('None', 'Matched', 'Apple', 'AMZN', 'AMZN RTN'))
    DEFAULT 'None';

-- Create index for filtering by status (useful for finding unmatched transactions)
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_pre_enrichment_status
    ON truelayer_transactions(pre_enrichment_status);

-- Add comment for documentation
COMMENT ON COLUMN truelayer_transactions.pre_enrichment_status IS
    'Pre-enrichment matching status: None (not matchable), Matched (already matched), Apple (unmatched Apple), AMZN (unmatched Amazon), AMZN RTN (unmatched Amazon return)';
