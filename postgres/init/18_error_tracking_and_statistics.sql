-- Gmail Workflow Error Tracking & Statistics System
-- Migration: Add error tracking and statistics tables
-- Created: 2025-12-26

-- ============================================================
-- 1. Error Tracking Table
-- ============================================================
CREATE TABLE IF NOT EXISTS gmail_processing_errors (
    id SERIAL PRIMARY KEY,

    -- Context linking
    connection_id INTEGER REFERENCES gmail_connections(id) ON DELETE CASCADE,
    sync_job_id INTEGER REFERENCES gmail_sync_jobs(id) ON DELETE SET NULL,
    message_id VARCHAR(255),
    receipt_id INTEGER REFERENCES gmail_receipts(id) ON DELETE CASCADE,

    -- Error classification
    error_stage VARCHAR(30) NOT NULL
        CHECK(error_stage IN (
            'fetch', 'parse', 'vendor_parse', 'schema_parse', 'pattern_parse',
            'llm_parse', 'pdf_parse', 'storage', 'match', 'validation'
        )),
    error_type VARCHAR(30) NOT NULL
        CHECK(error_type IN (
            'api_error', 'timeout', 'parse_error', 'validation', 'db_error',
            'network', 'rate_limit', 'auth_error', 'unknown'
        )),

    -- Error details
    error_message TEXT NOT NULL,
    stack_trace TEXT,
    error_context JSONB,  -- {sender_domain, subject, parse_method, etc.}

    -- Retry tracking
    is_retryable BOOLEAN DEFAULT FALSE,
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,

    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for error tracking queries
CREATE INDEX IF NOT EXISTS idx_errors_connection ON gmail_processing_errors(connection_id);
CREATE INDEX IF NOT EXISTS idx_errors_job ON gmail_processing_errors(sync_job_id);
CREATE INDEX IF NOT EXISTS idx_errors_stage ON gmail_processing_errors(error_stage);
CREATE INDEX IF NOT EXISTS idx_errors_type ON gmail_processing_errors(error_type);
CREATE INDEX IF NOT EXISTS idx_errors_occurred ON gmail_processing_errors(occurred_at);

-- ============================================================
-- 2. Parse Statistics Table (Message-level tracking)
-- ============================================================
CREATE TABLE IF NOT EXISTS gmail_parse_statistics (
    id SERIAL PRIMARY KEY,

    -- Context
    connection_id INTEGER NOT NULL REFERENCES gmail_connections(id) ON DELETE CASCADE,
    sync_job_id INTEGER REFERENCES gmail_sync_jobs(id) ON DELETE SET NULL,
    message_id VARCHAR(255) NOT NULL,

    -- Merchant identification
    sender_domain VARCHAR(255) NOT NULL,
    merchant_normalized VARCHAR(255),

    -- Parse method tracking
    parse_method VARCHAR(30) CHECK(parse_method IN (
        'vendor_amazon', 'vendor_uber', 'vendor_apple', 'vendor_paypal',
        'vendor_deliveroo', 'vendor_google', 'schema_org', 'pattern',
        'llm', 'pdf_fallback', 'pre_filter', 'unknown'
    )),

    -- Datapoint extraction success (user requirement)
    merchant_extracted BOOLEAN,
    brand_extracted BOOLEAN,
    amount_extracted BOOLEAN,
    date_extracted BOOLEAN,
    order_id_extracted BOOLEAN,
    line_items_extracted BOOLEAN,

    -- Matching outcome
    match_attempted BOOLEAN DEFAULT FALSE,
    match_success BOOLEAN,
    match_confidence INTEGER,

    -- Performance
    parse_duration_ms INTEGER,
    llm_cost_cents INTEGER,

    -- Result
    parsing_status VARCHAR(20) NOT NULL
        CHECK(parsing_status IN ('parsed', 'unparseable', 'filtered', 'failed')),
    parsing_error TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for statistics queries
CREATE INDEX IF NOT EXISTS idx_parse_stats_merchant ON gmail_parse_statistics(merchant_normalized);
CREATE INDEX IF NOT EXISTS idx_parse_stats_sender ON gmail_parse_statistics(sender_domain);
CREATE INDEX IF NOT EXISTS idx_parse_stats_method ON gmail_parse_statistics(parse_method);
CREATE INDEX IF NOT EXISTS idx_parse_stats_merchant_method ON gmail_parse_statistics(merchant_normalized, parse_method);
CREATE INDEX IF NOT EXISTS idx_parse_stats_job ON gmail_parse_statistics(sync_job_id);

-- ============================================================
-- 3. Aggregated Merchant Statistics (Rollup table)
-- ============================================================
CREATE TABLE IF NOT EXISTS gmail_merchant_statistics (
    id SERIAL PRIMARY KEY,

    -- Grouping dimensions
    connection_id INTEGER REFERENCES gmail_connections(id) ON DELETE CASCADE,
    sender_domain VARCHAR(255) NOT NULL,
    merchant_normalized VARCHAR(255),
    parse_method VARCHAR(30),

    -- Time window for aggregation
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,

    -- Parse statistics (enables rollup)
    total_attempts INTEGER NOT NULL DEFAULT 0,
    parsed_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,

    -- Datapoint extraction rates (user requirement)
    merchant_extracted_count INTEGER NOT NULL DEFAULT 0,
    brand_extracted_count INTEGER NOT NULL DEFAULT 0,
    amount_extracted_count INTEGER NOT NULL DEFAULT 0,
    date_extracted_count INTEGER NOT NULL DEFAULT 0,
    order_id_extracted_count INTEGER NOT NULL DEFAULT 0,
    line_items_extracted_count INTEGER NOT NULL DEFAULT 0,

    -- Matching statistics
    match_attempted_count INTEGER NOT NULL DEFAULT 0,
    match_success_count INTEGER NOT NULL DEFAULT 0,
    avg_match_confidence NUMERIC(5,2),

    -- Performance metrics
    avg_parse_duration_ms INTEGER,
    total_llm_cost_cents INTEGER NOT NULL DEFAULT 0,

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Unique constraint to prevent duplicate aggregations
    CONSTRAINT unique_merchant_stats UNIQUE (
        connection_id, sender_domain, merchant_normalized, parse_method, period_start
    )
);

-- Indexes for merchant statistics queries
CREATE INDEX IF NOT EXISTS idx_merchant_stats_connection ON gmail_merchant_statistics(connection_id);
CREATE INDEX IF NOT EXISTS idx_merchant_stats_merchant ON gmail_merchant_statistics(merchant_normalized);
CREATE INDEX IF NOT EXISTS idx_merchant_stats_method ON gmail_merchant_statistics(parse_method);
CREATE INDEX IF NOT EXISTS idx_merchant_stats_period ON gmail_merchant_statistics(period_start, period_end);

-- ============================================================
-- 4. Enhance Sync Job Table with Statistics
-- ============================================================
-- Add stats JSONB column to existing gmail_sync_jobs table
ALTER TABLE gmail_sync_jobs
ADD COLUMN IF NOT EXISTS stats JSONB DEFAULT '{}'::jsonb;

-- Comment explaining the stats structure
COMMENT ON COLUMN gmail_sync_jobs.stats IS 'Aggregated statistics JSON: {
  "by_parse_method": {"vendor_amazon": {"parsed": 45, "failed": 2}},
  "by_merchant": {"amazon.co.uk": {"parsed": 45, "failed": 2}},
  "datapoint_extraction": {
    "merchant": {"attempted": 100, "success": 95},
    "amount": {"attempted": 100, "success": 88}
  },
  "errors": {"api_error": 3, "parse_error": 5}
}';

-- ============================================================
-- Summary
-- ============================================================
-- This migration creates:
-- 1. gmail_processing_errors: Tracks all errors with classification and retry info
-- 2. gmail_parse_statistics: Message-level parsing metrics with datapoint extraction tracking
-- 3. gmail_merchant_statistics: Pre-aggregated rollup for fast dashboard queries
-- 4. gmail_sync_jobs.stats: Per-sync aggregated statistics in JSONB format
