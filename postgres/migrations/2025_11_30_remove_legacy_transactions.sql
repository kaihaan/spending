-- Migration: Remove Legacy Santander Transaction Tables
-- Date: 2025-11-30
-- Purpose: Clean up legacy code and migrate to TrueLayer-only architecture

BEGIN;

-- ============================================================
-- STEP 1: Remove Foreign Key Constraints from amazon_returns
-- ============================================================
ALTER TABLE amazon_returns
  DROP CONSTRAINT IF EXISTS amazon_returns_original_transaction_id_fkey,
  DROP CONSTRAINT IF EXISTS amazon_returns_refund_transaction_id_fkey;

-- Make transaction ID columns nullable (since FKs are removed)
ALTER TABLE amazon_returns
  ALTER COLUMN original_transaction_id DROP NOT NULL,
  ALTER COLUMN refund_transaction_id DROP NOT NULL;

COMMENT ON COLUMN amazon_returns.original_transaction_id IS
  'Transaction ID (legacy only - TrueLayer returns update descriptions instead)';
COMMENT ON COLUMN amazon_returns.refund_transaction_id IS
  'Refund transaction ID (legacy only - TrueLayer returns update descriptions instead)';

-- ============================================================
-- STEP 2: Create TrueLayer Apple Transaction Matches Table
-- ============================================================
CREATE TABLE IF NOT EXISTS truelayer_apple_transaction_matches (
    id SERIAL PRIMARY KEY,
    truelayer_transaction_id INTEGER NOT NULL,
    apple_transaction_id INTEGER NOT NULL,
    match_confidence INTEGER NOT NULL CHECK (match_confidence >= 0 AND match_confidence <= 100),
    matched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT truelayer_apple_matches_transaction_fk
        FOREIGN KEY (truelayer_transaction_id)
        REFERENCES truelayer_transactions(id)
        ON DELETE CASCADE,

    CONSTRAINT truelayer_apple_matches_apple_fk
        FOREIGN KEY (apple_transaction_id)
        REFERENCES apple_transactions(id)
        ON DELETE CASCADE,

    CONSTRAINT truelayer_apple_matches_transaction_unique
        UNIQUE (truelayer_transaction_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_truelayer_apple_matches_transaction
    ON truelayer_apple_transaction_matches(truelayer_transaction_id);

CREATE INDEX IF NOT EXISTS idx_truelayer_apple_matches_apple
    ON truelayer_apple_transaction_matches(apple_transaction_id);

COMMENT ON TABLE truelayer_apple_transaction_matches IS
  'Links TrueLayer bank transactions to Apple Store purchases for enrichment';

-- ============================================================
-- STEP 3: Drop Legacy Enrichment Tables
-- ============================================================
DROP TABLE IF EXISTS llm_enrichment_failures CASCADE;
DROP TABLE IF EXISTS transaction_enrichments CASCADE;

-- ============================================================
-- STEP 4: Drop Legacy Matching Tables
-- ============================================================
DROP TABLE IF EXISTS apple_transaction_matches CASCADE;
DROP TABLE IF EXISTS amazon_transaction_matches CASCADE;

-- ============================================================
-- STEP 5: Drop Legacy Transactions Table
-- ============================================================
DROP TABLE IF EXISTS transactions CASCADE;

COMMIT;
