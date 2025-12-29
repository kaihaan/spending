-- ============================================================================
-- Migration: Add missing unique constraints for TrueLayer OAuth upsert logic
-- ============================================================================
-- These constraints are required for ON CONFLICT upsert logic in:
-- 1. save_bank_connection - to handle re-authorization
-- 2. save_connection_account - to handle account discovery re-runs
--
-- Without these constraints, INSERT ... ON CONFLICT queries fail with:
-- "there is no unique or exclusion constraint matching the ON CONFLICT specification"
-- ============================================================================

-- Add unique constraint to bank_connections
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'bank_connections_user_id_provider_id_key'
    ) THEN
        ALTER TABLE bank_connections
        ADD CONSTRAINT bank_connections_user_id_provider_id_key
        UNIQUE (user_id, provider_id);

        RAISE NOTICE 'Added unique constraint on (user_id, provider_id) to bank_connections';
    ELSE
        RAISE NOTICE 'Unique constraint already exists on bank_connections (user_id, provider_id)';
    END IF;
END $$;

-- Add unique constraint to truelayer_accounts
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'truelayer_accounts_connection_id_account_id_key'
    ) THEN
        ALTER TABLE truelayer_accounts
        ADD CONSTRAINT truelayer_accounts_connection_id_account_id_key
        UNIQUE (connection_id, account_id);

        RAISE NOTICE 'Added unique constraint on (connection_id, account_id) to truelayer_accounts';
    ELSE
        RAISE NOTICE 'Unique constraint already exists on truelayer_accounts (connection_id, account_id)';
    END IF;
END $$;
