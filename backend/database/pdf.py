"""
PDF Attachments - Database Operations

Handles PDF receipt attachment storage and retrieval using MinIO object storage.
"""

from psycopg2.extras import RealDictCursor

from .base_psycopg2 import get_db

# ============================================================================
# PDF ATTACHMENT FUNCTIONS (MinIO storage)
# ============================================================================


def save_pdf_attachment(
    gmail_receipt_id: int,
    message_id: str,
    bucket_name: str,
    object_key: str,
    filename: str,
    content_hash: str,
    size_bytes: int,
    etag: str = None,
) -> int:
    """Save a PDF attachment record linked to a Gmail receipt."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO pdf_attachments
                (gmail_receipt_id, message_id, bucket_name, object_key, filename,
                 content_hash, size_bytes, etag)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id, filename) DO UPDATE
                SET object_key = EXCLUDED.object_key,
                    content_hash = EXCLUDED.content_hash,
                    size_bytes = EXCLUDED.size_bytes,
                    etag = EXCLUDED.etag
                RETURNING id
            """,
            (
                gmail_receipt_id,
                message_id,
                bucket_name,
                object_key,
                filename,
                content_hash,
                size_bytes,
                etag,
            ),
        )
        result = cursor.fetchone()
        conn.commit()
        return result[0] if result else None


def get_pdf_attachment_by_hash(content_hash: str) -> dict:
    """Check if a PDF with this content hash already exists (for deduplication)."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, object_key, bucket_name, filename, size_bytes
                FROM pdf_attachments
                WHERE content_hash = %s
                LIMIT 1
            """,
            (content_hash,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_pdf_attachments_for_receipt(gmail_receipt_id: int) -> list:
    """Get all PDF attachments for a Gmail receipt."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, bucket_name, object_key, filename, content_hash,
                       size_bytes, mime_type, created_at
                FROM pdf_attachments
                WHERE gmail_receipt_id = %s
                ORDER BY created_at
            """,
            (gmail_receipt_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_pdf_attachment_by_id(attachment_id: int) -> dict:
    """Get a single PDF attachment by ID."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT pa.*, gr.merchant_name, gr.receipt_date
                FROM pdf_attachments pa
                LEFT JOIN gmail_receipts gr ON pa.gmail_receipt_id = gr.id
                WHERE pa.id = %s
            """,
            (attachment_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_pdf_storage_stats() -> dict:
    """Get statistics about stored PDF attachments."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
                SELECT
                    COUNT(*) as total_attachments,
                    COALESCE(SUM(size_bytes), 0) as total_size_bytes,
                    COUNT(DISTINCT content_hash) as unique_pdfs,
                    COUNT(DISTINCT gmail_receipt_id) as receipts_with_pdfs
                FROM pdf_attachments
            """)
        return dict(cursor.fetchone())


def delete_pdf_attachment(attachment_id: int) -> bool:
    """Delete a PDF attachment record (MinIO object should be deleted separately)."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM pdf_attachments WHERE id = %s", (attachment_id,))
        conn.commit()
        return cursor.rowcount > 0


# ============================================================================
