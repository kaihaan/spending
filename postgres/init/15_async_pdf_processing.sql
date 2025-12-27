-- ============================================================================
-- Async PDF Processing Columns (Phase 2 Optimization)
-- ============================================================================
-- Adds columns to track PDF processing status when PDFs are processed
-- asynchronously via Celery background tasks

-- Add PDF processing status columns to gmail_receipts
ALTER TABLE gmail_receipts
ADD COLUMN IF NOT EXISTS pdf_processing_status VARCHAR(20) DEFAULT 'none'
    CHECK(pdf_processing_status IN ('none', 'pending', 'processing', 'completed', 'failed')),
ADD COLUMN IF NOT EXISTS pdf_retry_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS pdf_last_error TEXT;

-- Index for querying pending/processing PDFs (for monitoring and retry logic)
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_pdf_status
ON gmail_receipts(pdf_processing_status)
WHERE pdf_processing_status IN ('pending', 'processing');

-- Comments for documentation
COMMENT ON COLUMN gmail_receipts.pdf_processing_status IS 'Status of async PDF processing: none (no PDF), pending (queued), processing (in progress), completed (done), failed (error)';
COMMENT ON COLUMN gmail_receipts.pdf_retry_count IS 'Number of times PDF processing has been retried (for error tracking)';
COMMENT ON COLUMN gmail_receipts.pdf_last_error IS 'Last error message from PDF processing (if failed)';
