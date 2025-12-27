"""
MinIO S3-compatible object storage client for PDF receipt attachments.

Provides functions to store, retrieve, and manage PDF attachments in MinIO.
Designed for graceful degradation - if MinIO is unavailable, operations fail
silently and the rest of the sync continues.
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta
from io import BytesIO

logger = logging.getLogger(__name__)

# MinIO configuration from environment
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "receipts")

# Lazy-loaded client
_client = None


def _get_client():
    """Get or create MinIO client (lazy initialization)."""
    global _client
    if _client is None:
        try:
            from minio import Minio

            _client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ACCESS_KEY,
                secret_key=MINIO_SECRET_KEY,
                secure=MINIO_SECURE,
            )
        except ImportError:
            logger.warning("minio package not installed")
            return None
        except Exception as e:
            logger.error(f"Failed to create MinIO client: {e}")
            return None
    return _client


def is_available() -> bool:
    """Check if MinIO is available and the bucket exists."""
    try:
        client = _get_client()
        if client is None:
            return False

        # Check if bucket exists, create if not
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
            logger.info(f"Created MinIO bucket: {MINIO_BUCKET}")

        return True
    except Exception as e:
        logger.debug(f"MinIO not available: {e}")
        return False


def compute_pdf_hash(pdf_bytes: bytes) -> str:
    """Compute SHA256 hash of PDF content for deduplication."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def generate_object_key(
    message_id: str, filename: str, received_date: datetime | None = None
) -> str:
    """
    Generate S3 object key with date-based organization.

    Format: receipts/YYYY/MM/DD/{message_id}/{filename}
    """
    if received_date is None:
        received_date = datetime.now()

    # Sanitize filename (remove path separators)
    safe_filename = filename.replace("/", "_").replace("\\", "_")

    # Sanitize message_id (some may have special chars)
    safe_message_id = message_id.replace("/", "_").replace("\\", "_")

    return f"{received_date.year}/{received_date.month:02d}/{received_date.day:02d}/{safe_message_id}/{safe_filename}"


def store_pdf(
    pdf_bytes: bytes,
    message_id: str,
    filename: str,
    received_date: datetime | None = None,
    metadata: dict | None = None,
) -> dict | None:
    """
    Store a PDF in MinIO.

    Args:
        pdf_bytes: Raw PDF content
        message_id: Gmail message ID
        filename: Original filename
        received_date: Date for organizing in bucket
        metadata: Optional metadata dict (merchant name, etc.)

    Returns:
        Dict with object_key, content_hash, size_bytes, etag if successful.
        None if storage failed.
    """
    try:
        client = _get_client()
        if client is None:
            return None

        # Ensure bucket exists
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)

        # Generate object key
        object_key = generate_object_key(message_id, filename, received_date)

        # Compute hash for deduplication
        content_hash = compute_pdf_hash(pdf_bytes)

        # Prepare metadata
        minio_metadata = {
            "message-id": message_id,
            "content-hash": content_hash,
            "original-filename": filename,
        }
        if metadata:
            for key, value in metadata.items():
                if value:
                    # MinIO metadata keys must be lowercase
                    minio_metadata[key.lower().replace("_", "-")] = str(value)

        # Upload to MinIO
        data = BytesIO(pdf_bytes)
        result = client.put_object(
            bucket_name=MINIO_BUCKET,
            object_name=object_key,
            data=data,
            length=len(pdf_bytes),
            content_type="application/pdf",
            metadata=minio_metadata,
        )

        logger.info(f"Stored PDF in MinIO: {object_key} ({len(pdf_bytes)} bytes)")

        return {
            "bucket_name": MINIO_BUCKET,
            "object_key": object_key,
            "content_hash": content_hash,
            "size_bytes": len(pdf_bytes),
            "etag": result.etag,
            "filename": filename,
        }

    except Exception as e:
        logger.error(f"Failed to store PDF in MinIO: {e}")
        return None


def get_pdf(object_key: str) -> bytes | None:
    """
    Retrieve a PDF from MinIO.

    Args:
        object_key: S3 object key

    Returns:
        PDF bytes if successful, None otherwise.
    """
    try:
        client = _get_client()
        if client is None:
            return None

        response = client.get_object(MINIO_BUCKET, object_key)
        pdf_bytes = response.read()
        response.close()
        response.release_conn()

        return pdf_bytes

    except Exception as e:
        logger.error(f"Failed to get PDF from MinIO: {e}")
        return None


def get_presigned_url(object_key: str, expires_hours: int = 1) -> str | None:
    """
    Generate a presigned URL for temporary access to a PDF.

    Args:
        object_key: S3 object key
        expires_hours: URL validity in hours (default 1)

    Returns:
        Presigned URL string if successful, None otherwise.
    """
    try:
        client = _get_client()
        if client is None:
            return None

        url = client.presigned_get_object(
            bucket_name=MINIO_BUCKET,
            object_name=object_key,
            expires=timedelta(hours=expires_hours),
        )

        return url

    except Exception as e:
        logger.error(f"Failed to generate presigned URL: {e}")
        return None


def check_exists_by_hash(content_hash: str) -> str | None:
    """
    Check if a PDF with the given content hash already exists.

    This is used for deduplication - if we already have this exact PDF,
    we can skip uploading and just reference the existing one.

    Note: This requires a database lookup, not MinIO. Returns None here
    as the database check is done in database_postgres.py.
    """
    # Deduplication is handled at the database level
    return None


def delete_pdf(object_key: str) -> bool:
    """
    Delete a PDF from MinIO.

    Args:
        object_key: S3 object key

    Returns:
        True if deleted successfully, False otherwise.
    """
    try:
        client = _get_client()
        if client is None:
            return False

        client.remove_object(MINIO_BUCKET, object_key)
        logger.info(f"Deleted PDF from MinIO: {object_key}")
        return True

    except Exception as e:
        logger.error(f"Failed to delete PDF from MinIO: {e}")
        return False


def get_storage_stats() -> dict | None:
    """
    Get storage statistics for the receipts bucket.

    Returns:
        Dict with object_count and total_size_bytes if successful.
    """
    try:
        client = _get_client()
        if client is None:
            return None

        objects = client.list_objects(MINIO_BUCKET, recursive=True)

        count = 0
        total_size = 0

        for obj in objects:
            count += 1
            total_size += obj.size

        return {
            "object_count": count,
            "total_size_bytes": total_size,
            "bucket_name": MINIO_BUCKET,
        }

    except Exception as e:
        logger.error(f"Failed to get storage stats: {e}")
        return None
