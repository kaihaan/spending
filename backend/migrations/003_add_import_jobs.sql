-- Migration: Add TrueLayer Import Job Management Tables
-- Purpose: Support batch imports with date ranges, multi-account selection, and progress tracking
-- Date: 2025-11-28

-- Track import jobs and history
CREATE TABLE IF NOT EXISTS truelayer_import_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    connection_id INTEGER REFERENCES bank_connections(id) ON DELETE SET NULL,

    -- Job status and type
    job_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: pending, running, completed, failed, enriching
    job_type VARCHAR(20) NOT NULL DEFAULT 'date_range',
    -- Values: date_range, incremental, full_sync

    -- Date range parameters
    from_date DATE,
    to_date DATE,

    -- Account and card selection (comma-separated IDs or JSON array)
    account_ids TEXT[] DEFAULT ARRAY[]::TEXT[],
    card_ids TEXT[] DEFAULT ARRAY[]::TEXT[],

    -- Results tracking
    total_accounts INTEGER DEFAULT 0,
    total_transactions_synced INTEGER DEFAULT 0,
    total_transactions_duplicates INTEGER DEFAULT 0,
    total_transactions_errors INTEGER DEFAULT 0,

    -- Enrichment settings
    auto_enrich BOOLEAN DEFAULT TRUE,
    enrich_after_completion BOOLEAN DEFAULT FALSE,
    enrichment_job_id INTEGER,

    -- Batch configuration
    batch_size INTEGER DEFAULT 50,

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    estimated_completion TIMESTAMP WITH TIME ZONE,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    error_message TEXT,

    -- Indexes
    CONSTRAINT valid_job_status CHECK (job_status IN ('pending', 'running', 'completed', 'failed', 'enriching')),
    CONSTRAINT valid_job_type CHECK (job_type IN ('date_range', 'incremental', 'full_sync')),
    CONSTRAINT valid_dates CHECK (from_date IS NULL OR to_date IS NULL OR from_date <= to_date)
);

CREATE INDEX idx_import_jobs_user_id ON truelayer_import_jobs(user_id);
CREATE INDEX idx_import_jobs_status ON truelayer_import_jobs(job_status);
CREATE INDEX idx_import_jobs_created_at ON truelayer_import_jobs(created_at DESC);
CREATE INDEX idx_import_jobs_connection_id ON truelayer_import_jobs(connection_id);

-- Track per-account import progress
CREATE TABLE IF NOT EXISTS truelayer_import_progress (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL REFERENCES truelayer_import_jobs(id) ON DELETE CASCADE,
    account_id INTEGER REFERENCES truelayer_accounts(id) ON DELETE SET NULL,

    -- Progress status
    progress_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: pending, syncing, completed, failed

    -- Counts
    synced_count INTEGER DEFAULT 0,
    duplicates_count INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,

    -- Timing
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Error tracking
    error_message TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_status CHECK (progress_status IN ('pending', 'syncing', 'completed', 'failed'))
);

CREATE INDEX idx_import_progress_job_id ON truelayer_import_progress(job_id);
CREATE INDEX idx_import_progress_status ON truelayer_import_progress(progress_status);
CREATE INDEX idx_import_progress_account_id ON truelayer_import_progress(account_id);

-- Track enrichment job history (referenced by import jobs)
CREATE TABLE IF NOT EXISTS truelayer_enrichment_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    import_job_id INTEGER REFERENCES truelayer_import_jobs(id) ON DELETE SET NULL,

    -- Job status
    job_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- Values: pending, running, completed, failed

    -- Transaction tracking
    transaction_ids INTEGER[] DEFAULT ARRAY[]::INTEGER[],

    -- Results
    total_transactions INTEGER DEFAULT 0,
    successful_enrichments INTEGER DEFAULT 0,
    failed_enrichments INTEGER DEFAULT 0,
    cached_hits INTEGER DEFAULT 0,

    -- Cost tracking
    total_cost NUMERIC(10, 4) DEFAULT 0.00,
    total_tokens INTEGER DEFAULT 0,
    llm_provider VARCHAR(50),
    llm_model VARCHAR(100),

    -- Timing
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,

    -- Metadata
    metadata JSONB DEFAULT '{}',
    error_message TEXT,

    CONSTRAINT valid_enrichment_status CHECK (job_status IN ('pending', 'running', 'completed', 'failed'))
);

CREATE INDEX idx_enrichment_jobs_user_id ON truelayer_enrichment_jobs(user_id);
CREATE INDEX idx_enrichment_jobs_status ON truelayer_enrichment_jobs(job_status);
CREATE INDEX idx_enrichment_jobs_import_job_id ON truelayer_enrichment_jobs(import_job_id);
CREATE INDEX idx_enrichment_jobs_created_at ON truelayer_enrichment_jobs(created_at DESC);

-- Add column to truelayer_transactions to link to import job (optional but useful)
ALTER TABLE truelayer_transactions ADD COLUMN IF NOT EXISTS import_job_id INTEGER REFERENCES truelayer_import_jobs(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_import_job ON truelayer_transactions(import_job_id);

-- Add column to track last sync per account (more accurate than connection-level)
ALTER TABLE truelayer_accounts ADD COLUMN IF NOT EXISTS last_synced_at_incremental TIMESTAMP WITH TIME ZONE;
CREATE INDEX IF NOT EXISTS idx_truelayer_accounts_last_synced ON truelayer_accounts(last_synced_at_incremental);

-- Create view for easy import job status checking
CREATE OR REPLACE VIEW v_import_job_status AS
SELECT
    j.id,
    j.user_id,
    j.job_status,
    j.job_type,
    j.from_date,
    j.to_date,
    j.created_at,
    j.started_at,
    j.estimated_completion,
    COUNT(DISTINCT p.account_id) FILTER (WHERE p.progress_status = 'completed') as completed_accounts,
    COUNT(DISTINCT p.account_id) as total_accounts,
    COALESCE(SUM(p.synced_count), 0) as total_synced,
    COALESCE(SUM(p.duplicates_count), 0) as total_duplicates,
    COALESCE(SUM(p.errors_count), 0) as total_errors,
    CASE
        WHEN j.job_status = 'running' THEN
            ROUND(100.0 * COUNT(DISTINCT p.account_id) FILTER (WHERE p.progress_status = 'completed') / NULLIF(COUNT(DISTINCT p.account_id), 0))
        WHEN j.job_status = 'completed' THEN 100
        ELSE 0
    END as progress_percent
FROM truelayer_import_jobs j
LEFT JOIN truelayer_import_progress p ON p.job_id = j.id
GROUP BY j.id, j.user_id, j.job_status, j.job_type, j.from_date, j.to_date, j.created_at, j.started_at, j.estimated_completion;

-- Add foreign key constraint from import_jobs to enrichment_jobs (after both tables are created)
ALTER TABLE truelayer_import_jobs
ADD CONSTRAINT fk_import_jobs_enrichment_jobs
FOREIGN KEY (enrichment_job_id) REFERENCES truelayer_enrichment_jobs(id) ON DELETE SET NULL;

-- Grant permissions (if using role-based access)
-- GRANT SELECT, INSERT, UPDATE ON truelayer_import_jobs TO app_user;
-- GRANT SELECT, INSERT, UPDATE ON truelayer_import_progress TO app_user;
-- GRANT SELECT, INSERT, UPDATE ON truelayer_enrichment_jobs TO app_user;
