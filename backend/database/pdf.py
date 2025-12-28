"""
PDF Attachments - Database Operations

Handles PDF receipt attachment storage and retrieval using MinIO object storage.

Migrated to SQLAlchemy from psycopg2.
"""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from .base import get_session
from .models.gmail import GmailReceipt, PDFAttachment

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
    with get_session() as session:
        # Upsert using PostgreSQL INSERT ... ON CONFLICT
        stmt = (
            insert(PDFAttachment)
            .values(
                gmail_receipt_id=gmail_receipt_id,
                message_id=message_id,
                bucket_name=bucket_name,
                object_key=object_key,
                filename=filename,
                content_hash=content_hash,
                size_bytes=size_bytes,
                etag=etag,
            )
            .on_conflict_do_update(
                index_elements=["message_id", "filename"],
                set_={
                    "object_key": object_key,
                    "content_hash": content_hash,
                    "size_bytes": size_bytes,
                    "etag": etag,
                },
            )
            .returning(PDFAttachment.id)
        )
        result = session.execute(stmt)
        attachment_id = result.scalar_one()
        session.commit()
        return attachment_id


def get_pdf_attachment_by_hash(content_hash: str) -> dict | None:
    """Check if a PDF with this content hash already exists (for deduplication)."""
    with get_session() as session:
        attachment = (
            session.query(PDFAttachment)
            .filter(PDFAttachment.content_hash == content_hash)
            .first()
        )

        if not attachment:
            return None

        return {
            "id": attachment.id,
            "object_key": attachment.object_key,
            "bucket_name": attachment.bucket_name,
            "filename": attachment.filename,
            "size_bytes": attachment.size_bytes,
        }


def get_pdf_attachments_for_receipt(gmail_receipt_id: int) -> list:
    """Get all PDF attachments for a Gmail receipt."""
    with get_session() as session:
        attachments = (
            session.query(PDFAttachment)
            .filter(PDFAttachment.gmail_receipt_id == gmail_receipt_id)
            .order_by(PDFAttachment.created_at)
            .all()
        )

        return [
            {
                "id": att.id,
                "bucket_name": att.bucket_name,
                "object_key": att.object_key,
                "filename": att.filename,
                "content_hash": att.content_hash,
                "size_bytes": att.size_bytes,
                "mime_type": att.mime_type,
                "created_at": att.created_at,
            }
            for att in attachments
        ]


def get_pdf_attachment_by_id(attachment_id: int) -> dict | None:
    """Get a single PDF attachment by ID."""
    with get_session() as session:
        result = (
            session.query(
                PDFAttachment,
                GmailReceipt.merchant_name,
                GmailReceipt.receipt_date,
            )
            .outerjoin(GmailReceipt, PDFAttachment.gmail_receipt_id == GmailReceipt.id)
            .filter(PDFAttachment.id == attachment_id)
            .first()
        )

        if not result:
            return None

        attachment, merchant_name, receipt_date = result

        return {
            "id": attachment.id,
            "gmail_receipt_id": attachment.gmail_receipt_id,
            "message_id": attachment.message_id,
            "bucket_name": attachment.bucket_name,
            "object_key": attachment.object_key,
            "filename": attachment.filename,
            "content_hash": attachment.content_hash,
            "size_bytes": attachment.size_bytes,
            "mime_type": attachment.mime_type,
            "etag": attachment.etag,
            "created_at": attachment.created_at,
            "merchant_name": merchant_name,
            "receipt_date": receipt_date,
        }


def get_pdf_storage_stats() -> dict:
    """Get statistics about stored PDF attachments."""
    with get_session() as session:
        result = session.query(
            func.count(PDFAttachment.id).label("total_attachments"),
            func.coalesce(func.sum(PDFAttachment.size_bytes), 0).label(
                "total_size_bytes"
            ),
            func.count(func.distinct(PDFAttachment.content_hash)).label("unique_pdfs"),
            func.count(func.distinct(PDFAttachment.gmail_receipt_id)).label(
                "receipts_with_pdfs"
            ),
        ).first()

        return {
            "total_attachments": result.total_attachments,
            "total_size_bytes": result.total_size_bytes,
            "unique_pdfs": result.unique_pdfs,
            "receipts_with_pdfs": result.receipts_with_pdfs,
        }


def delete_pdf_attachment(attachment_id: int) -> bool:
    """Delete a PDF attachment record (MinIO object should be deleted separately)."""
    with get_session() as session:
        attachment = session.get(PDFAttachment, attachment_id)
        if attachment:
            session.delete(attachment)
            session.commit()
            return True
        return False


# ============================================================================
