-- MinIO PDF Storage Schema
-- Tracks PDF attachments stored in MinIO object storage

CREATE TABLE IF NOT EXISTS pdf_attachments (
    id SERIAL PRIMARY KEY,
    gmail_receipt_id INTEGER REFERENCES gmail_receipts(id) ON DELETE CASCADE,
    message_id VARCHAR(255) NOT NULL,
    bucket_name VARCHAR(100) DEFAULT 'receipts',
    object_key VARCHAR(500) NOT NULL UNIQUE,
    filename VARCHAR(255) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- SHA256 for deduplication
    size_bytes INTEGER NOT NULL,
    mime_type VARCHAR(100) DEFAULT 'application/pdf',
    etag VARCHAR(64),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for looking up attachments by receipt
CREATE INDEX IF NOT EXISTS idx_pdf_attachments_receipt ON pdf_attachments(gmail_receipt_id);

-- Index for deduplication by content hash
CREATE INDEX IF NOT EXISTS idx_pdf_attachments_hash ON pdf_attachments(content_hash);

-- Unique constraint to prevent duplicate attachments for same message
CREATE UNIQUE INDEX IF NOT EXISTS idx_pdf_attachments_unique ON pdf_attachments(message_id, filename);

COMMENT ON TABLE pdf_attachments IS 'PDF attachments stored in MinIO object storage';
COMMENT ON COLUMN pdf_attachments.object_key IS 'S3 object key in format: receipts/YYYY/MM/DD/{message_id}/{filename}';
COMMENT ON COLUMN pdf_attachments.content_hash IS 'SHA256 hash of PDF content for deduplication';
