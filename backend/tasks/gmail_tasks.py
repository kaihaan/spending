"""Celery tasks for Gmail receipt processing."""

from datetime import datetime, timedelta

import database_postgres as db
from celery_app import celery_app


@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def sync_gmail_receipts_task(
    self,
    connection_id: int,
    sync_type: str = "auto",
    job_id: int = None,
    from_date_str: str = None,
    to_date_str: str = None,
    force_reparse: bool = False,
):
    """
    Celery task to sync Gmail receipts in the background.

    Args:
        connection_id: Gmail connection ID
        sync_type: 'full' or 'incremental' or 'auto'
        job_id: Optional pre-created job ID for progress tracking
        from_date_str: ISO format start date (YYYY-MM-DD)
        to_date_str: ISO format end date (YYYY-MM-DD)
        force_reparse: If True, re-parse existing emails (bypass duplicate check)

    Returns:
        dict: Sync statistics
    """
    try:
        from mcp.gmail_sync import sync_receipts_full, sync_receipts_incremental

        # Parse dates if provided
        from_date = datetime.fromisoformat(from_date_str) if from_date_str else None
        to_date = datetime.fromisoformat(to_date_str) if to_date_str else None

        self.update_state(
            state="STARTED",
            meta={
                "status": "initializing",
                "connection_id": connection_id,
                "job_id": job_id,
                "from_date": from_date_str,
                "to_date": to_date_str,
            },
        )

        # Get connection info
        connection = db.get_gmail_connection_by_id(connection_id)
        if not connection:
            return {"status": "failed", "error": "Connection not found"}

        # Determine sync type
        if sync_type == "auto":
            # Use incremental if we have a history ID
            if connection.get("history_id"):
                sync_type = "incremental"
            else:
                sync_type = "full"

        results = {
            "total_messages": 0,
            "processed": 0,
            "parsed": 0,
            "failed": 0,
            "duplicates": 0,
        }

        if sync_type == "incremental":
            self.update_state(
                state="PROGRESS",
                meta={
                    "status": "syncing",
                    "sync_type": "incremental",
                    "connection_id": connection_id,
                    "job_id": job_id,
                },
            )

            result = sync_receipts_incremental(
                connection_id, job_id=job_id, force_reparse=force_reparse
            )

            if result.get("error"):
                return {"status": "failed", "error": result["error"]}

            results = {
                "total_messages": result.get("new_messages", 0),
                "processed": result.get("new_messages", 0),
                "parsed": result.get("parsed", 0),
                "failed": result.get("failed", 0),
                "duplicates": result.get("duplicates", 0),
            }
            job_id = result.get("job_id", job_id)
        else:
            # Full sync with progress tracking
            for progress in sync_receipts_full(
                connection_id,
                from_date=from_date,
                to_date=to_date,
                job_id=job_id,
                force_reparse=force_reparse,
            ):
                status = progress.get("status")

                if status == "started":
                    job_id = progress.get("job_id", job_id)
                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "status": "started",
                            "sync_type": "full",
                            "job_id": job_id,
                            "from_date": progress.get("from_date"),
                            "to_date": progress.get("to_date"),
                            "connection_id": connection_id,
                        },
                    )

                elif status == "scanning":
                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "status": "scanning",
                            "sync_type": "full",
                            "job_id": job_id,
                            "total_messages": progress.get("total_messages", 0),
                            "processed": 0,
                            "connection_id": connection_id,
                        },
                    )

                elif status == "processing":
                    self.update_state(
                        state="PROGRESS",
                        meta={
                            "status": "processing",
                            "sync_type": "full",
                            "job_id": job_id,
                            "total_messages": progress.get("total_messages", 0),
                            "processed": progress.get("processed", 0),
                            "parsed": progress.get("parsed", 0),
                            "failed": progress.get("failed", 0),
                            "duplicates": progress.get("duplicates", 0),
                            "connection_id": connection_id,
                        },
                    )

                elif status == "completed":
                    results = {
                        "total_messages": progress.get("total_messages", 0),
                        "processed": progress.get("processed", 0),
                        "parsed": progress.get("parsed", 0),
                        "failed": progress.get("failed", 0),
                        "duplicates": progress.get("duplicates", 0),
                    }
                    job_id = progress.get("job_id", job_id)

        return {
            "status": "completed",
            "sync_type": sync_type,
            "job_id": job_id,
            "stats": results,
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "status": "failed",
            "error": str(e),
            "job_id": job_id,
        }


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def parse_gmail_receipts_task(self, connection_id: int, limit: int = 100):
    """
    DEPRECATED: Parsing now happens during sync (parse-on-sync workflow).

    This task is kept for backwards compatibility but will return immediately
    since there are no longer any 'pending' receipts to parse.

    Args:
        connection_id: Gmail connection ID
        limit: Maximum receipts to parse

    Returns:
        dict: Parse statistics (will show 0 parsed since parse-on-sync is active)
    """
    return {
        "status": "completed",
        "stats": {
            "total": 0,
            "parsed": 0,
            "failed": 0,
            "skipped": 0,
        },
        "message": "Parsing now happens during sync - no separate parse step needed",
        "completed_at": datetime.now().isoformat(),
    }


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def match_gmail_receipts_task(self, user_id: int = 1):
    """
    Celery task to match Gmail receipts to transactions.

    Args:
        user_id: User ID to match receipts for

    Returns:
        dict: Matching statistics
    """
    try:
        from mcp.gmail_matcher import match_all_gmail_receipts

        self.update_state(
            state="STARTED", meta={"status": "initializing", "user_id": user_id}
        )

        results = match_all_gmail_receipts(user_id)

        return {
            "status": "completed",
            "stats": {
                "total_receipts": results.get("total_receipts", 0),
                "matched": results.get("matched", 0),
                "unmatched": results.get("unmatched", 0),
                "auto_matched": results.get("auto_matched", 0),
                "needs_confirmation": results.get("needs_confirmation", 0),
            },
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}


@celery_app.task(bind=True, time_limit=300, soft_time_limit=280)
def cleanup_old_gmail_receipts_task(self, days: int = 90):
    """
    Celery task to clean up old Gmail receipts beyond retention period.

    Only deletes receipts that:
    - Are older than the specified days
    - Are NOT matched to a transaction
    - Have parsing_status of 'unparseable'

    Args:
        days: Number of days to retain (default 90)

    Returns:
        dict: Cleanup statistics
    """
    try:
        self.update_state(
            state="STARTED", meta={"status": "cleaning", "retention_days": days}
        )

        cutoff_date = datetime.now() - timedelta(days=days)

        # Delete old unparseable receipts that aren't matched
        deleted = db.delete_old_unmatched_gmail_receipts(cutoff_date)

        return {
            "status": "completed",
            "stats": {
                "deleted_count": deleted,
                "cutoff_date": cutoff_date.isoformat(),
                "retention_days": days,
            },
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}


@celery_app.task(bind=True, time_limit=900, soft_time_limit=850)
def full_gmail_pipeline_task(self, connection_id: int, user_id: int = 1):
    """
    Celery task to run the full Gmail processing pipeline:
    1. Sync receipts from Gmail (parsing happens inline during sync)
    2. Match receipts to transactions

    Note: Parsing is now done inline during sync (parse-on-sync workflow),
    so there's no separate parse step.

    Args:
        connection_id: Gmail connection ID
        user_id: User ID for matching

    Returns:
        dict: Combined statistics from all steps
    """
    try:
        from mcp.gmail_matcher import match_all_gmail_receipts
        from mcp.gmail_sync import sync_receipts_full, sync_receipts_incremental

        pipeline_results = {
            "sync": {},
            "match": {},
        }

        # Step 1: Sync (parsing happens inline)
        self.update_state(
            state="PROGRESS", meta={"status": "syncing", "step": 1, "total_steps": 2}
        )

        connection = db.get_gmail_connection_by_id(connection_id)
        if not connection:
            return {"status": "failed", "error": "Connection not found"}

        if connection.get("history_id"):
            sync_result = sync_receipts_incremental(connection_id)
            pipeline_results["sync"] = {
                "type": "incremental",
                "messages_found": sync_result.get("new_messages", 0),
                "stored": sync_result.get("parsed", 0),
                "filtered": sync_result.get("filtered", 0),
                "duplicates": sync_result.get("duplicates", 0),
            }
        else:
            sync_results = {"total": 0, "stored": 0}
            for progress in sync_receipts_full(connection_id):
                if progress.get("status") == "completed":
                    sync_results = {
                        "total": progress.get("total_messages", 0),
                        "stored": progress.get("parsed", 0),
                        "filtered": progress.get("filtered", 0),
                        "duplicates": progress.get("duplicates", 0),
                    }
            pipeline_results["sync"] = {
                "type": "full",
                "messages_found": sync_results["total"],
                "stored": sync_results.get("stored", 0),
                "filtered": sync_results.get("filtered", 0),
                "duplicates": sync_results.get("duplicates", 0),
            }

        # Step 2: Match
        self.update_state(
            state="PROGRESS", meta={"status": "matching", "step": 2, "total_steps": 2}
        )

        match_result = match_all_gmail_receipts(user_id)
        pipeline_results["match"] = {
            "total": match_result.get("total_receipts", 0),
            "matched": match_result.get("matched", 0),
            "unmatched": match_result.get("unmatched", 0),
        }

        return {
            "status": "completed",
            "pipeline": pipeline_results,
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        return {"status": "failed", "error": str(e)}


@celery_app.task(bind=True, time_limit=120, soft_time_limit=110, max_retries=3)
def process_pdf_receipt_task(
    self,
    receipt_id: int,
    message_id: str,
    attachment_info: dict,
    sender_domain: str,
    connection_id: int,
    received_date=None,
):
    """
    Process PDF receipt asynchronously (Phase 2 Optimization).

    Downloads PDF attachment, parses it, uploads to MinIO, and updates receipt.
    Runs in background to avoid blocking sync loop.

    Args:
        receipt_id: Gmail receipt ID
        message_id: Gmail message ID
        attachment_info: Dict with 'attachment_id', 'filename', or 'external_url'
        sender_domain: Email sender domain (for parser selection)
        connection_id: Gmail connection ID (for API access)
        received_date: Email received date (optional, for MinIO path)

    Returns:
        dict: Processing result with status and timing
    """
    import time

    from celery.utils.log import get_task_logger

    logger = get_task_logger(__name__)
    task_start = time.time()

    try:
        # Update status to 'processing'
        db.update_gmail_receipt_pdf_status(receipt_id, "processing")
        logger.info(f"[PDF] Starting processing for receipt {receipt_id}")

        # 1. Fetch PDF content
        fetch_start = time.time()
        pdf_bytes = None
        filename = attachment_info.get("filename", "receipt.pdf")

        if "external_url" in attachment_info:
            # Download from external URL (e.g., Translink)
            import requests

            url = attachment_info["external_url"]
            logger.info(f"[PDF] Downloading from external URL: {url}")
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                pdf_bytes = response.content
            else:
                raise Exception(f"Failed to download PDF: HTTP {response.status_code}")

        elif "attachment_id" in attachment_info:
            # Download from Gmail API
            from mcp.gmail_auth import get_gmail_credentials
            from mcp.gmail_client import build_gmail_service, get_pdf_attachments

            logger.info(
                f"[PDF] Downloading from Gmail attachment: {attachment_info['attachment_id']}"
            )

            # Get valid credentials (handles token refresh if needed)
            logger.info("[PDF] Refreshing access token if needed...")
            access_token, refresh_token = get_gmail_credentials(connection_id)
            logger.info("[PDF] Token refresh check complete")

            # Build Gmail service with fresh tokens
            service = build_gmail_service(access_token, refresh_token)

            # Download PDF
            attachments = [
                {
                    "attachment_id": attachment_info["attachment_id"],
                    "filename": filename,
                }
            ]
            pdf_contents = get_pdf_attachments(service, message_id, attachments)

            if pdf_contents and len(pdf_contents) > 0:
                pdf_bytes = pdf_contents[0]["content"]
            else:
                raise Exception("No PDF content retrieved from Gmail")
        else:
            raise Exception("No valid PDF source (attachment_id or external_url)")

        fetch_time = time.time() - fetch_start
        logger.info(f"[PERF] PDF fetch for receipt {receipt_id}: {fetch_time:.3f}s")

        if not pdf_bytes:
            raise Exception("PDF bytes are empty")

        # 2. Parse PDF with pdfplumber
        parse_start = time.time()
        from mcp.gmail_pdf_parser import parse_receipt_pdf

        pdf_result = parse_receipt_pdf(pdf_bytes, sender_domain, filename)
        parse_time = time.time() - parse_start
        logger.info(f"[PERF] PDF parse for receipt {receipt_id}: {parse_time:.3f}s")

        if not pdf_result or pdf_result.get("total_amount") is None:
            # Parsing failed but don't retry
            db.update_gmail_receipt_pdf_status(
                receipt_id, "failed", error="PDF parsing returned no data"
            )
            return {
                "status": "failed",
                "reason": "parse_failed",
                "duration": time.time() - task_start,
            }

        # 3. Upload to MinIO
        upload_start = time.time()
        minio_object_key = None

        try:
            from datetime import datetime

            from mcp.minio_client import is_available, store_pdf

            if is_available():
                # Convert received_date to datetime if it's a string
                minio_received_date = received_date
                if isinstance(received_date, str):
                    try:
                        minio_received_date = datetime.fromisoformat(
                            received_date.replace("Z", "+00:00")
                        )
                    except Exception:
                        minio_received_date = None

                minio_result = store_pdf(
                    pdf_bytes=pdf_bytes,
                    message_id=message_id,
                    filename=filename,
                    received_date=minio_received_date,
                    metadata={"merchant": pdf_result.get("merchant_name")},
                )

                if minio_result:
                    # Save PDF attachment record in database
                    db.save_pdf_attachment(
                        gmail_receipt_id=receipt_id,
                        message_id=message_id,
                        bucket_name=minio_result["bucket_name"],
                        object_key=minio_result["object_key"],
                        filename=minio_result["filename"],
                        content_hash=minio_result["content_hash"],
                        size_bytes=minio_result["size_bytes"],
                        etag=minio_result["etag"],
                    )
                    minio_object_key = minio_result["object_key"]
                    logger.info(f"[PDF] Stored to MinIO: {minio_object_key}")
        except Exception as e:
            # MinIO failure is non-fatal, continue with receipt update
            logger.warning(f"[PDF] MinIO storage failed (non-fatal): {e}")

        upload_time = time.time() - upload_start
        logger.info(f"[PERF] MinIO upload for receipt {receipt_id}: {upload_time:.3f}s")

        # 4. Update receipt with parsed data
        db.update_gmail_receipt_from_pdf(receipt_id, pdf_result, minio_object_key)

        # 5. Set status to 'completed'
        total_time = time.time() - task_start
        db.update_gmail_receipt_pdf_status(receipt_id, "completed")

        logger.info(
            f"[PERF] Total PDF processing for receipt {receipt_id}: {total_time:.3f}s"
        )
        return {
            "status": "completed",
            "duration": total_time,
            "fetch_time": fetch_time,
            "parse_time": parse_time,
            "upload_time": upload_time,
            "merchant": pdf_result.get("merchant_name"),
            "amount": pdf_result.get("total_amount"),
        }

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[PDF] Processing failed for receipt {receipt_id}: {error_msg}")
        db.update_gmail_receipt_pdf_status(receipt_id, "failed", error=error_msg)

        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            countdown = 2**self.request.retries  # 2, 4, 8 seconds
            logger.info(
                f"[PDF] Retrying in {countdown}s (attempt {self.request.retries + 1}/{self.max_retries})"
            )
            raise self.retry(exc=e, countdown=countdown)

        return {
            "status": "failed",
            "error": error_msg,
            "duration": time.time() - task_start,
        }
