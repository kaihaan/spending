-- Migration: Add account_type field to truelayer_transactions table
-- Purpose: Extend schema to support accounting best practices
-- Date: 2025-11-29

-- Add account_type column to truelayer_transactions
ALTER TABLE truelayer_transactions
ADD COLUMN IF NOT EXISTS account_type VARCHAR(20)
CHECK(account_type IN ('ASSET', 'LIABILITY', 'EQUITY', 'EXPENSE', 'INCOME'));

-- Set default values based on transaction_type
-- DEBITs are typically EXPENSE (money going out)
-- CREDITs are typically INCOME (money coming in)
UPDATE truelayer_transactions
SET account_type = CASE
    WHEN transaction_type = 'DEBIT' THEN 'EXPENSE'
    WHEN transaction_type = 'CREDIT' THEN 'INCOME'
    ELSE NULL
END
WHERE account_type IS NULL;

-- Create index for account_type lookups
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_account_type
ON truelayer_transactions(account_type);
