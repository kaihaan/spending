-- Migration: Add LLM queue support for Gmail receipts
-- Date: 2025-12-22
-- Purpose: Allow users to queue unparseable receipts for LLM parsing with cost tracking

-- Add LLM parsing status column (NULL = not queued, pending/processing/completed/failed)
ALTER TABLE gmail_receipts
  ADD COLUMN IF NOT EXISTS llm_parse_status VARCHAR(20) DEFAULT NULL;

-- Add constraint for valid status values
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'gmail_receipts_llm_parse_status_check'
    ) THEN
        ALTER TABLE gmail_receipts
          ADD CONSTRAINT gmail_receipts_llm_parse_status_check
          CHECK(llm_parse_status IS NULL OR llm_parse_status IN ('pending', 'processing', 'completed', 'failed'));
    END IF;
END $$;

-- Add cost tracking columns
ALTER TABLE gmail_receipts ADD COLUMN IF NOT EXISTS llm_estimated_cost_cents INTEGER;
ALTER TABLE gmail_receipts ADD COLUMN IF NOT EXISTS llm_actual_cost_cents INTEGER;
ALTER TABLE gmail_receipts ADD COLUMN IF NOT EXISTS llm_parsed_at TIMESTAMPTZ;

-- Add index for efficiently querying unparseable receipts
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_unparseable
  ON gmail_receipts(parsing_status) WHERE parsing_status = 'unparseable';

-- Add index for LLM queue queries
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_llm_queue
  ON gmail_receipts(llm_parse_status) WHERE llm_parse_status IS NOT NULL;

-- Comment on columns
COMMENT ON COLUMN gmail_receipts.llm_parse_status IS 'LLM parsing queue status: NULL (not queued), pending, processing, completed, failed';
COMMENT ON COLUMN gmail_receipts.llm_estimated_cost_cents IS 'Estimated cost in cents before LLM parsing';
COMMENT ON COLUMN gmail_receipts.llm_actual_cost_cents IS 'Actual cost in cents after LLM parsing';
COMMENT ON COLUMN gmail_receipts.llm_parsed_at IS 'Timestamp when LLM parsing completed';
