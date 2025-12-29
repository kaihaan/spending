-- ============================================================================
-- Migration: Add missing UNIQUE constraints from schema definition
-- ============================================================================
-- These constraints are defined in 01_schema.sql but missing from live database
-- This migration restores them to match the intended schema.
--
-- Missing constraints found:
-- 1. category_keywords - UNIQUE(category_name, keyword) [line 40]
-- 2. amazon_transaction_matches - UNIQUE(transaction_id) [line 75]
-- 3. amazon_returns - UNIQUE(reversal_id) [line 82]
-- ============================================================================

-- Add UNIQUE constraint to category_keywords
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'category_keywords'
        AND c.conname = 'category_keywords_category_name_keyword_key'
    ) THEN
        ALTER TABLE category_keywords
        ADD CONSTRAINT category_keywords_category_name_keyword_key
        UNIQUE (category_name, keyword);

        RAISE NOTICE 'Added UNIQUE constraint on (category_name, keyword) to category_keywords';
    ELSE
        RAISE NOTICE 'UNIQUE constraint already exists on category_keywords (category_name, keyword)';
    END IF;
END $$;

-- Add UNIQUE constraint to amazon_transaction_matches
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'amazon_transaction_matches'
        AND c.conname = 'amazon_transaction_matches_transaction_id_key'
    ) THEN
        ALTER TABLE amazon_transaction_matches
        ADD CONSTRAINT amazon_transaction_matches_transaction_id_key
        UNIQUE (transaction_id);

        RAISE NOTICE 'Added UNIQUE constraint on transaction_id to amazon_transaction_matches';
    ELSE
        RAISE NOTICE 'UNIQUE constraint already exists on amazon_transaction_matches (transaction_id)';
    END IF;
END $$;

-- Add UNIQUE constraint to amazon_returns
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON c.conrelid = t.oid
        WHERE t.relname = 'amazon_returns'
        AND c.conname = 'amazon_returns_reversal_id_key'
    ) THEN
        ALTER TABLE amazon_returns
        ADD CONSTRAINT amazon_returns_reversal_id_key
        UNIQUE (reversal_id);

        RAISE NOTICE 'Added UNIQUE constraint on reversal_id to amazon_returns';
    ELSE
        RAISE NOTICE 'UNIQUE constraint already exists on amazon_returns (reversal_id)';
    END IF;
END $$;
