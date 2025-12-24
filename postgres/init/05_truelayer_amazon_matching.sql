-- Migration: Add Amazon matching support for TrueLayer transactions
-- Date: 2025-11-30
-- Purpose: Enable Amazon order matching for TrueLayer transactions with proper relational structure

-- Add lookup_description column to legacy transactions table
ALTER TABLE transactions
ADD COLUMN IF NOT EXISTS lookup_description TEXT;

-- Add lookup_description column to TrueLayer transactions table
ALTER TABLE truelayer_transactions
ADD COLUMN IF NOT EXISTS lookup_description TEXT;

-- Create dedicated matching table for TrueLayer transactions
CREATE TABLE IF NOT EXISTS truelayer_amazon_transaction_matches (
    id SERIAL PRIMARY KEY,
    truelayer_transaction_id INTEGER NOT NULL,
    amazon_order_id INTEGER NOT NULL,
    match_confidence NUMERIC(5,2) NOT NULL,
    matched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT truelayer_amazon_matches_transaction_fk
        FOREIGN KEY (truelayer_transaction_id)
        REFERENCES truelayer_transactions(id)
        ON DELETE CASCADE,

    CONSTRAINT truelayer_amazon_matches_order_fk
        FOREIGN KEY (amazon_order_id)
        REFERENCES amazon_orders(id)
        ON DELETE CASCADE,

    CONSTRAINT truelayer_amazon_matches_transaction_unique
        UNIQUE (truelayer_transaction_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_transactions_lookup
    ON transactions(lookup_description);

CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_lookup
    ON truelayer_transactions(lookup_description);

CREATE INDEX IF NOT EXISTS idx_truelayer_amazon_matches_transaction
    ON truelayer_amazon_transaction_matches(truelayer_transaction_id);

CREATE INDEX IF NOT EXISTS idx_truelayer_amazon_matches_order
    ON truelayer_amazon_transaction_matches(amazon_order_id);
