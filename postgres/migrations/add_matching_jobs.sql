-- Migration: Add matching_jobs table for Pre-AI async operations
-- Date: 2025-12-20
-- Purpose: Track async matching jobs (Amazon, Apple, Returns) with progress

-- Table for tracking matching job state
CREATE TABLE IF NOT EXISTS matching_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    job_type VARCHAR(50) NOT NULL,  -- 'amazon', 'apple', 'returns'
    celery_task_id VARCHAR(255),
    status VARCHAR(20) DEFAULT 'queued',  -- queued, running, completed, failed

    -- Progress tracking
    total_items INTEGER DEFAULT 0,
    processed_items INTEGER DEFAULT 0,
    matched_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,

    -- Error handling
    error_message TEXT,

    -- Timestamps
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for efficiently finding active jobs for a user
CREATE INDEX IF NOT EXISTS idx_matching_jobs_user_status
    ON matching_jobs(user_id, status);

-- Index for finding jobs by celery task ID (for task updates)
CREATE INDEX IF NOT EXISTS idx_matching_jobs_celery_task
    ON matching_jobs(celery_task_id);

-- Comment
COMMENT ON TABLE matching_jobs IS 'Tracks async matching jobs for Amazon, Apple, and Returns matching operations';
