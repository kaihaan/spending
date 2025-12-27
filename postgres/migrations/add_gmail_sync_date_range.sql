-- Migration: Add date range columns to gmail_sync_jobs
-- Date: 2025-01-XX
-- Description: Track the date range being synced for Gmail receipts

ALTER TABLE gmail_sync_jobs ADD COLUMN IF NOT EXISTS sync_from_date DATE;
ALTER TABLE gmail_sync_jobs ADD COLUMN IF NOT EXISTS sync_to_date DATE;

COMMENT ON COLUMN gmail_sync_jobs.sync_from_date IS 'Start date for email search range';
COMMENT ON COLUMN gmail_sync_jobs.sync_to_date IS 'End date for email search range';
