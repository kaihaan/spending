"""
Gmail Sync Module

Handles synchronization of receipt emails from Gmail.
Supports full sync (initial) and incremental sync (subsequent).
"""

import hashlib
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Generator

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

import database_postgres as database
from mcp.gmail_auth import get_valid_access_token, get_gmail_credentials, decrypt_token
from mcp.gmail_client import (
    build_gmail_service,
    build_receipt_query,
    list_receipt_messages,
    get_message_content,
    get_history_changes,
    get_user_profile,
    parse_sender_email,
    extract_sender_domain,
    get_attachment_content,
)
from mcp.gmail_parser import (
    is_amazon_receipt_email,
    is_ebay_receipt_email,
    is_etsy_receipt_email,
    is_uber_receipt_email,
    is_paypal_receipt_email,
    is_microsoft_receipt_email,
    is_apple_receipt_email,
    is_lyft_receipt_email,
    is_deliveroo_receipt_email,
    is_spotify_receipt_email,
    is_netflix_receipt_email,
    is_google_receipt_email,
    is_ocado_receipt_email,
    is_citizens_of_soil_receipt_email,
    is_figma_receipt_email,
    parse_receipt_content,
)
from mcp.gmail_pdf_parser import parse_receipt_pdf
from mcp.logging_config import get_logger

logger = get_logger(__name__)


# Sync configuration
DEFAULT_SYNC_MONTHS = 12  # Default to last 12 months
MAX_MESSAGES_PER_SYNC = 5000  # Safety limit
BATCH_SIZE = 50  # Messages to process before updating progress

# Performance tracking configuration
GMAIL_SYNC_WORKERS = int(os.getenv('GMAIL_SYNC_WORKERS', '5'))
GMAIL_PARALLEL_FETCH = os.getenv('GMAIL_PARALLEL_FETCH', 'true').lower() == 'true'


class SyncPerformanceTracker:
    """Track performance metrics during Gmail sync."""

    def __init__(self):
        self.api_calls = []
        self.db_writes = []
        self.parse_times = []
        self.start_time = time.time()
        self.start_memory = 0

        if PSUTIL_AVAILABLE:
            try:
                self.start_memory = psutil.Process().memory_info().rss / 1024 / 1024
            except Exception as e:
                logger.warning(f"Could not initialize psutil: {e}")
                # Disable psutil for this session
                globals()['PSUTIL_AVAILABLE'] = False

    def record_api_call(self, duration: float):
        self.api_calls.append(duration)

    def record_db_write(self, duration: float):
        self.db_writes.append(duration)

    def record_parse(self, duration: float):
        self.parse_times.append(duration)

    def report(self, message_count: int):
        """Log performance summary."""
        total_time = time.time() - self.start_time
        memory_used = 0

        if PSUTIL_AVAILABLE:
            try:
                memory_used = psutil.Process().memory_info().rss / 1024 / 1024 - self.start_memory
            except Exception:
                pass  # Silently skip memory reporting if psutil fails

        logger.info("=" * 80)
        logger.info(f"PERFORMANCE SUMMARY: {message_count} messages in {total_time:.1f}s")
        logger.info("=" * 80)
        logger.info(f"Throughput: {message_count / (total_time / 60):.1f} messages/min")

        if self.api_calls:
            logger.info(f"API calls: avg={sum(self.api_calls)/len(self.api_calls):.3f}s, max={max(self.api_calls):.3f}s")

        if self.db_writes:
            logger.info(f"DB writes: avg={sum(self.db_writes)/len(self.db_writes):.3f}s, max={max(self.db_writes):.3f}s")

        if self.parse_times:
            logger.info(f"Parsing: avg={sum(self.parse_times)/len(self.parse_times):.3f}s, max={max(self.parse_times):.3f}s")

        if PSUTIL_AVAILABLE:
            logger.info(f"Memory delta: {memory_used:.1f} MB")

        logger.info("=" * 80)


def should_import_email(subject: str, sender_email: str, body_text: str = None) -> tuple:
    """
    Check if email should be imported based on vendor-specific filters.

    This runs BEFORE storing emails to filter out known non-receipts
    (delivery notifications, marketing emails, account alerts, etc.)

    Args:
        subject: Email subject line
        sender_email: Full sender email address
        body_text: Email body text (optional, for body-based filtering)

    Returns:
        Tuple of (should_import: bool, reason: str)
    """
    # Reject personal email domains - these can never issue receipts
    # Forwarded receipts from these domains should not be stored
    PERSONAL_EMAIL_DOMAINS = {
        'gmail.com', 'googlemail.com',
        'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
        'yahoo.com', 'yahoo.co.uk',
        'icloud.com', 'me.com', 'mac.com',
        'aol.com', 'protonmail.com', 'proton.me',
    }
    sender_domain = sender_email.split('@')[-1].lower() if '@' in sender_email else ''
    if sender_domain in PERSONAL_EMAIL_DOMAINS:
        return (False, f'Personal email domain: {sender_domain}')

    # Reject shipping/delivery notifications (not receipts)
    subject_lower = subject.lower()
    SHIPPING_PATTERNS = [
        'your order is on the way',
        'your order has shipped',
        'your order has been shipped',
        'your order has been delivered',
        'your package is on its way',
        'out for delivery',
    ]
    for pattern in SHIPPING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Shipping notification: {pattern}')

    # Reject booking confirmations (not receipts)
    BOOKING_PATTERNS = [
        'booking confirmation for',
        'your reservation at',
        'reservation confirmed',
    ]
    for pattern in BOOKING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Booking confirmation: {pattern}')

    # Reject specific domains that only send shipping updates (but accept purchase receipts)
    SHIPPING_DOMAINS = {'woolrich.com'}
    if sender_domain in SHIPPING_DOMAINS:
        # Accept actual purchase confirmations
        if 'thank you for your purchase' in subject_lower or 'receipt' in subject_lower or 'invoice' in subject_lower:
            pass  # Allow through
        else:
            return (False, f'Shipping domain: {sender_domain}')

    # Amazon filter uses body content for accurate filtering
    amazon_result = is_amazon_receipt_email(subject, sender_email, body_text)
    if amazon_result[0] is not None:
        if amazon_result[0] is False:
            return (False, amazon_result[1])
        else:
            return (True, amazon_result[1])

    # Other vendor filters (subject/sender only)
    filters = [
        is_ebay_receipt_email,
        is_etsy_receipt_email,
        is_uber_receipt_email,
        is_paypal_receipt_email,
        is_microsoft_receipt_email,
        is_apple_receipt_email,
        is_lyft_receipt_email,
        is_deliveroo_receipt_email,
        is_spotify_receipt_email,
        is_netflix_receipt_email,
        is_google_receipt_email,
        is_ocado_receipt_email,
        is_citizens_of_soil_receipt_email,
        is_figma_receipt_email,
    ]

    for filter_func in filters:
        result = filter_func(subject, sender_email)
        if result[0] is not None:  # This vendor's filter applies
            if result[0] is False:  # Explicitly rejected
                return (False, result[1])
            else:  # Explicitly accepted
                return (True, result[1])

    # No vendor filter matched - allow import (generic receipt)
    return (True, 'No vendor filter matched')


def compute_receipt_hash(
    merchant_name: str,
    amount: float,
    receipt_date: str,
    order_id: str = None
) -> str:
    """
    Compute deduplication hash for a receipt.

    Args:
        merchant_name: Normalized merchant name
        amount: Total amount
        receipt_date: Date string (YYYY-MM-DD)
        order_id: Optional order ID

    Returns:
        SHA256 hash string
    """
    components = [
        (merchant_name or '').lower().strip(),
        f"{float(amount):.2f}" if amount else '',
        receipt_date or '',
        (order_id or '').strip(),
    ]
    hash_input = '|'.join(components)
    return hashlib.sha256(hash_input.encode()).hexdigest()


def sync_receipts_full(
    connection_id: int,
    from_date: datetime = None,
    to_date: datetime = None,
    job_id: int = None,
    force_reparse: bool = False
) -> Generator[dict, None, dict]:
    """
    Full sync of all receipt emails.

    Yields progress updates and returns final results.

    Args:
        connection_id: Database connection ID
        from_date: Optional start date (defaults to 12 months ago)
        to_date: Optional end date (defaults to today)
        job_id: Optional pre-created job ID for progress tracking
        force_reparse: If True, re-parse existing emails (bypass duplicate check)

    Yields:
        Progress dictionaries with count, status, etc.

    Returns:
        Final results dictionary
    """
    # Get connection details
    connection = database.get_gmail_connection_by_id(connection_id)
    if not connection:
        raise ValueError(f"Gmail connection {connection_id} not found")

    # Create sync job only if not provided (avoids duplicate job creation)
    if job_id is None:
        job_id = database.create_gmail_sync_job(connection_id, job_type='full')
    logger.info("Starting full Gmail sync", extra={'sync_job_id': job_id, 'connection_id': connection_id})

    # Initialize statistics tracker for this sync
    from mcp.statistics_tracker import GmailSyncStatistics
    stats = GmailSyncStatistics(connection_id=connection_id, sync_job_id=job_id)

    try:
        # Get valid credentials (access and refresh tokens)
        access_token, refresh_token = get_gmail_credentials(connection_id)

        # Build Gmail service for pagination and profile fetching only
        # Fresh services will be created per-batch during message processing
        service = build_gmail_service(access_token, refresh_token)

        # Get user profile for history ID
        profile = get_user_profile(service)
        latest_history_id = profile.get('history_id')
        logger.info(f"Gmail profile: {profile['email_address']}, history_id={latest_history_id}",
                   extra={'sync_job_id': job_id})

        # Set date range
        if from_date is None:
            # Use stored sync_from_date or default to 12 months
            if connection.get('sync_from_date'):
                from_date = datetime.fromisoformat(str(connection['sync_from_date']))
            else:
                from_date = datetime.utcnow() - timedelta(days=DEFAULT_SYNC_MONTHS * 30)

        # Build search query with date range
        query = build_receipt_query(from_date=from_date, to_date=to_date)
        logger.info(f"Search query: {query[:100]}...", extra={'sync_job_id': job_id})

        # Format dates for progress reporting
        from_date_str = from_date.strftime('%Y-%m-%d') if from_date else None
        to_date_str = to_date.strftime('%Y-%m-%d') if to_date else None

        # Initial yield - starting
        yield {
            'status': 'started',
            'job_id': job_id,
            'query': query,
            'from_date': from_date_str,
            'to_date': to_date_str,
        }

        # Paginate through results
        all_message_ids = []
        page_token = None
        page_count = 0

        while True:
            result = list_receipt_messages(
                service,
                query=query,
                page_token=page_token,
                max_results=100
            )

            messages = result.get('messages', [])
            all_message_ids.extend([m['id'] for m in messages])

            page_count += 1
            logger.info(f"Page {page_count}: {len(messages)} messages (total: {len(all_message_ids)})",
                       extra={'sync_job_id': job_id})

            # Safety limit
            if len(all_message_ids) >= MAX_MESSAGES_PER_SYNC:
                logger.warning(f"Hit message limit ({MAX_MESSAGES_PER_SYNC})", extra={'sync_job_id': job_id})
                break

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        total_messages = len(all_message_ids)
        logger.info(f"Found {total_messages} potential receipt messages", extra={'sync_job_id': job_id})

        # Update job with total
        database.update_gmail_sync_job_progress(
            job_id, total_messages, 0, 0, 0
        )

        yield {
            'status': 'scanning',
            'total_messages': total_messages,
            'processed': 0,
        }

        # Process messages in batches
        processed = 0
        parsed = 0
        failed = 0
        duplicates = 0
        filtered = 0

        # Initialize performance tracker
        perf = SyncPerformanceTracker()

        # Phase 3: Bulk database writes (feature flag)
        USE_BULK_WRITES = os.getenv('GMAIL_BULK_WRITES', 'true').lower() == 'true'

        for i in range(0, total_messages, BATCH_SIZE):
            batch_ids = all_message_ids[i:i + BATCH_SIZE]

            # Create fresh Gmail service for this batch to avoid TLS connection reuse
            # This prevents SSL errors from corrupted connection state
            access_token_batch, refresh_token_batch = get_gmail_credentials(connection_id)
            service = build_gmail_service(access_token_batch, refresh_token_batch)

            # Phase 3: Prepare batch accumulators for bulk operations
            if USE_BULK_WRITES:
                email_content_batch = []
                receipt_batch = []
                pdf_tasks_batch = []

            if GMAIL_PARALLEL_FETCH and len(batch_ids) > 1:
                # Parallel processing with ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=min(GMAIL_SYNC_WORKERS, len(batch_ids))) as executor:
                    # Submit all API calls in parallel
                    future_to_msg_id = {
                        executor.submit(get_message_content, service, msg_id): msg_id
                        for msg_id in batch_ids
                    }

                    # Process results as they complete
                    for future in as_completed(future_to_msg_id):
                        msg_id = future_to_msg_id[future]
                        try:
                            # Get message from future with timeout
                            api_start = time.time()
                            msg = future.result(timeout=30)
                            perf.record_api_call(time.time() - api_start)

                            if USE_BULK_WRITES:
                                # Phase 3: Prepare data for bulk insert
                                parse_start = time.time()
                                prepared = prepare_receipt_data(connection_id, msg, service, force_reparse=force_reparse)
                                parse_duration_ms = int((time.time() - parse_start) * 1000)
                                perf.record_parse(parse_duration_ms / 1000.0)

                                # Record statistics for this parse attempt (only for stored receipts)
                                if prepared.get('receipt_data'):
                                    stats.record_parse_attempt(
                                        message_id=prepared['message_id'],
                                        sender_domain=prepared['sender_domain'],
                                        parse_result=prepared['receipt_data'],
                                        duration_ms=parse_duration_ms,
                                        llm_cost_cents=prepared['receipt_data'].get('llm_cost_cents')
                                    )

                                # Accumulate for bulk insert
                                email_content_batch.append(prepared['message'])
                                if prepared['action'] == 'store':
                                    receipt_batch.append((prepared['connection_id'], prepared['message_id'], prepared['receipt_data']))
                                    if prepared.get('pdf_task_info'):
                                        pdf_tasks_batch.append(prepared)
                                elif prepared['action'] == 'duplicate':
                                    duplicates += 1
                                elif prepared['action'] == 'filtered':
                                    filtered += 1
                            else:
                                # Original: Individual inserts
                                db_start = time.time()
                                result = store_pending_receipt(connection_id, msg, service, force_reparse=force_reparse)
                                perf.record_db_write(time.time() - db_start)

                                # Record statistics for this parse attempt (non-bulk path)
                                if result.get('receipt_data'):
                                    stats.record_parse_attempt(
                                        message_id=result['message_id'],
                                        sender_domain=result['sender_domain'],
                                        parse_result=result['receipt_data'],
                                        llm_cost_cents=result['receipt_data'].get('llm_cost_cents')
                                    )

                                if result.get('stored'):
                                    parsed += 1
                                elif result.get('duplicate'):
                                    duplicates += 1
                                elif result.get('filtered'):
                                    filtered += 1

                            processed += 1

                        except Exception as e:
                            logger.warning(f"Failed to process message {msg_id}: {e}",
                                         extra={'sync_job_id': job_id, 'message_id': msg_id})
                            failed += 1
                            processed += 1
            else:
                # Sequential processing (fallback or single message)
                for msg_id in batch_ids:
                    retry_count = 0
                    max_retries = 3

                    while retry_count < max_retries:
                        try:
                            # Fetch message content
                            api_start = time.time()
                            msg = get_message_content(service, msg_id)
                            perf.record_api_call(time.time() - api_start)

                            if USE_BULK_WRITES:
                                # Phase 3: Prepare data for bulk insert
                                parse_start = time.time()
                                prepared = prepare_receipt_data(connection_id, msg, service, force_reparse=force_reparse)
                                perf.record_parse(time.time() - parse_start)

                                # Accumulate for bulk insert
                                email_content_batch.append(prepared['message'])
                                if prepared['action'] == 'store':
                                    receipt_batch.append((prepared['connection_id'], prepared['message_id'], prepared['receipt_data']))
                                    if prepared.get('pdf_task_info'):
                                        pdf_tasks_batch.append(prepared)
                                elif prepared['action'] == 'duplicate':
                                    duplicates += 1
                                elif prepared['action'] == 'filtered':
                                    filtered += 1
                            else:
                                # Original: Individual inserts
                                db_start = time.time()
                                result = store_pending_receipt(connection_id, msg, service, force_reparse=force_reparse)
                                perf.record_db_write(time.time() - db_start)

                                # Record statistics for this parse attempt (non-bulk path)
                                if result.get('receipt_data'):
                                    stats.record_parse_attempt(
                                        message_id=result['message_id'],
                                        sender_domain=result['sender_domain'],
                                        parse_result=result['receipt_data'],
                                        llm_cost_cents=result['receipt_data'].get('llm_cost_cents')
                                    )

                                if result.get('stored'):
                                    parsed += 1
                                elif result.get('duplicate'):
                                    duplicates += 1
                                elif result.get('filtered'):
                                    filtered += 1

                            processed += 1
                            break  # Success, exit retry loop

                        except Exception as e:
                            import traceback
                            logger.warning(f"Failed to process message {msg_id}: {e}",
                                         extra={'sync_job_id': job_id, 'message_id': msg_id},
                                         exc_info=(os.getenv('DEBUG_GMAIL_SYNC') == 'true'))
                            retry_count += 1
                            if retry_count >= max_retries:
                                failed += 1
                                processed += 1

            # Phase 3: Bulk database writes after batch processing
            if USE_BULK_WRITES and (email_content_batch or receipt_batch):
                db_start = time.time()
                try:
                    logger.info(f"Bulk inserting: {len(email_content_batch)} emails, {len(receipt_batch)} receipts",
                               extra={'sync_job_id': job_id})

                    # Bulk insert email content
                    if email_content_batch:
                        database.save_gmail_email_content_bulk(email_content_batch)

                    # Bulk insert receipts and get receipt IDs
                    receipt_id_mapping = {}
                    if receipt_batch:
                        result = database.save_gmail_receipt_bulk(receipt_batch)
                        receipt_id_mapping = result['message_to_id']
                        parsed += result['inserted']

                    perf.record_db_write(time.time() - db_start)

                    # Dispatch PDF tasks using receipt IDs from bulk insert
                    if pdf_tasks_batch and receipt_id_mapping:
                        from tasks.gmail_tasks import process_pdf_receipt_task
                        for prepared in pdf_tasks_batch:
                            message_id = prepared['message_id']
                            receipt_id = receipt_id_mapping.get(message_id)
                            if receipt_id:
                                try:
                                    process_pdf_receipt_task.delay(
                                        receipt_id=receipt_id,
                                        message_id=message_id,
                                        attachment_info=prepared['pdf_task_info'],
                                        sender_domain=prepared['sender_domain'],
                                        connection_id=connection_id,
                                        received_date=prepared['receipt_data'].get('received_at')
                                    )
                                except Exception as e:
                                    logger.warning(f"PDF task dispatch failed for receipt {receipt_id}: {e}",
                                                  extra={'sync_job_id': job_id, 'receipt_id': receipt_id})

                                    # CRITICAL FIX: Track PDF task dispatch failures
                                    try:
                                        from mcp.error_tracking import GmailError, ErrorStage, ErrorType
                                        error = GmailError(
                                            stage=ErrorStage.PDF_PARSE,
                                            error_type=ErrorType.UNKNOWN,
                                            message=f"PDF task dispatch failed: {e}",
                                            exception=e,
                                            context={'receipt_id': receipt_id, 'message_id': message_id},
                                            is_retryable=True
                                        )
                                        error.log(connection_id=connection_id, sync_job_id=job_id)
                                    except:
                                        pass  # Don't let error tracking crash sync

                except Exception as e:
                    logger.warning(f"Bulk insert failed, falling back to individual inserts: {e}",
                                  extra={'sync_job_id': job_id},
                                  exc_info=(os.getenv('DEBUG_GMAIL_SYNC') == 'true'))
                    import traceback

                    # Fallback: insert individually
                    # CRITICAL FIX: Track failures in fallback mode
                    from mcp.error_tracking import GmailError, ErrorStage

                    for msg in email_content_batch:
                        try:
                            database.save_gmail_email_content(msg)
                        except Exception as e2:
                            failed += 1  # CRITICAL: Increment failed counter
                            logger.warning(f"Failed to save email content for {msg.get('message_id')}: {e2}",
                                          extra={'sync_job_id': job_id, 'message_id': msg.get('message_id')})

                            # Track error for statistics
                            try:
                                error = GmailError.from_exception(
                                    e2, ErrorStage.STORAGE,
                                    context={'message_id': msg.get('message_id'), 'operation': 'save_email_content'}
                                )
                                error.log(connection_id=connection_id, sync_job_id=job_id)
                            except:
                                pass  # Don't let error tracking crash sync

                    for conn_id, msg_id, receipt_data in receipt_batch:
                        try:
                            database.save_gmail_receipt(conn_id, msg_id, receipt_data)
                            parsed += 1
                        except Exception as e2:
                            failed += 1  # CRITICAL: Increment failed counter
                            logger.warning(f"Failed to save receipt for {msg_id}: {e2}",
                                          extra={'sync_job_id': job_id, 'message_id': msg_id})

                            # Track error for statistics
                            try:
                                error = GmailError.from_exception(
                                    e2, ErrorStage.STORAGE,
                                    context={'message_id': msg_id, 'operation': 'save_receipt'}
                                )
                                error.log(connection_id=connection_id, sync_job_id=job_id)
                            except:
                                pass  # Don't let error tracking crash sync

            # Update progress after each batch
            database.update_gmail_sync_job_progress(
                job_id, total_messages, processed, parsed, failed
            )

            yield {
                'status': 'processing',
                'total_messages': total_messages,
                'processed': processed,
                'parsed': parsed,
                'failed': failed,
                'filtered': filtered,
                'duplicates': duplicates,
            }

        # Update history ID for incremental syncs
        if latest_history_id:
            database.update_gmail_history_id(connection_id, latest_history_id)

        # Update connection status
        database.update_gmail_connection_status(connection_id, 'active')

        # Complete job
        database.complete_gmail_sync_job(job_id, 'completed')

        final_result = {
            'status': 'completed',
            'job_id': job_id,
            'total_messages': total_messages,
            'processed': processed,
            'parsed': parsed,
            'failed': failed,
            'duplicates': duplicates,
            'history_id': latest_history_id,
        }

        logger.info(f"Sync completed: {parsed} receipts stored, {duplicates} duplicates, {failed} failed",
                   extra={'sync_job_id': job_id})

        # Report performance metrics
        perf.report(processed)

        # Flush statistics to database
        stats.flush()
        logger.info(f"Statistics summary:\n{stats.get_summary()}", extra={'sync_job_id': job_id})

        yield final_result
        return final_result

    except Exception as e:
        logger.error(f"Sync failed: {e}", extra={'sync_job_id': job_id}, exc_info=True)
        database.complete_gmail_sync_job(job_id, 'failed', str(e))
        raise


def sync_receipts_incremental(connection_id: int, job_id: int = None, force_reparse: bool = False) -> dict:
    """
    Incremental sync using Gmail history API.

    Only fetches messages added since last sync.

    Args:
        connection_id: Database connection ID
        job_id: Optional pre-created job ID for progress tracking
        force_reparse: If True, re-parse existing emails (bypass duplicate check)

    Returns:
        Results dictionary
    """
    # Get connection details
    connection = database.get_gmail_connection_by_id(connection_id)
    if not connection:
        raise ValueError(f"Gmail connection {connection_id} not found")

    history_id = connection.get('history_id')
    if not history_id:
        logger.warning("No history ID, falling back to full sync", extra={'connection_id': connection_id})
        # Convert generator to final result
        result = None
        for progress in sync_receipts_full(connection_id, force_reparse=force_reparse):
            result = progress
        return result

    # Create sync job only if not provided (avoids duplicate job creation)
    if job_id is None:
        job_id = database.create_gmail_sync_job(connection_id, job_type='incremental')
    logger.info("Starting incremental Gmail sync",
               extra={'sync_job_id': job_id, 'history_id': history_id})

    try:
        # Get valid credentials (access and refresh tokens)
        access_token, refresh_token = get_gmail_credentials(connection_id)

        # Build Gmail service with both tokens for auto-refresh support
        service = build_gmail_service(access_token, refresh_token)

        # Get changes since last sync
        changes = get_history_changes(service, history_id)

        if changes.get('full_sync_required'):
            logger.warning("History expired, falling back to full sync", extra={'sync_job_id': job_id})
            database.complete_gmail_sync_job(job_id, status='cancelled')
            result = None
            for progress in sync_receipts_full(connection_id, force_reparse=force_reparse):
                result = progress
            return result

        new_message_ids = changes.get('new_message_ids', [])
        latest_history_id = changes.get('latest_history_id')

        logger.info(f"Found {len(new_message_ids)} new messages since last sync",
                   extra={'sync_job_id': job_id})

        if not new_message_ids:
            database.complete_gmail_sync_job(job_id, 'completed')
            database.update_gmail_history_id(connection_id, latest_history_id)
            return {
                'status': 'completed',
                'job_id': job_id,
                'new_messages': 0,
                'parsed': 0,
            }

        # Process new messages
        database.update_gmail_sync_job_progress(
            job_id, len(new_message_ids), 0, 0, 0
        )

        parsed = 0
        failed = 0
        duplicates = 0
        filtered = 0

        for msg_id in new_message_ids:
            try:
                msg = get_message_content(service, msg_id)
                result = store_pending_receipt(connection_id, msg, service, force_reparse=force_reparse)

                if result.get('stored'):
                    parsed += 1
                elif result.get('duplicate'):
                    duplicates += 1
                elif result.get('filtered'):
                    filtered += 1

            except Exception as e:
                logger.warning(f"Failed to process message {msg_id}: {e}",
                              extra={'sync_job_id': job_id, 'message_id': msg_id})
                failed += 1

        # Update history ID
        if latest_history_id:
            database.update_gmail_history_id(connection_id, latest_history_id)

        # Update connection status
        database.update_gmail_connection_status(connection_id, 'active')

        # Complete job
        database.complete_gmail_sync_job(job_id, 'completed')

        logger.info(f"Incremental sync completed: {parsed} new receipts, {filtered} filtered",
                   extra={'sync_job_id': job_id})

        return {
            'status': 'completed',
            'job_id': job_id,
            'new_messages': len(new_message_ids),
            'parsed': parsed,
            'failed': failed,
            'duplicates': duplicates,
            'filtered': filtered,
        }

    except Exception as e:
        logger.error(f"Incremental sync failed: {e}", extra={'sync_job_id': job_id}, exc_info=True)
        database.complete_gmail_sync_job(job_id, 'failed', str(e))
        raise


def store_parsed_receipt(connection_id: int, message: dict, service=None, force_reparse: bool = False) -> dict:
    """
    Parse email inline and store only extracted data (no raw body).

    This implements parse-on-sync workflow:
    1. Filter - reject non-receipts
    2. Parse - extract structured data while we have the content
    3. For PDF receipts (e.g., Charles Tyrwhitt), parse PDF attachment
    4. Store - save only extracted data, not raw bodies

    Args:
        connection_id: Database connection ID
        message: Parsed message dictionary from gmail_client
        service: Gmail API service (optional, for fetching PDF attachments)
        force_reparse: If True, re-parse existing emails (bypass duplicate check)

    Returns:
        Dictionary with 'stored', 'duplicate', or 'filtered' flag
    """
    message_id = message.get('message_id')

    # Parse sender
    sender_email, sender_name = parse_sender_email(message.get('from', ''))
    sender_domain = extract_sender_domain(sender_email)

    # Early filter: reject known non-receipt emails BEFORE parsing
    subject = message.get('subject', '')
    body_text = message.get('body_text') or message.get('body_html', '')
    should_import, filter_reason = should_import_email(subject, sender_email, body_text)
    if not should_import:
        return {'filtered': True, 'reason': filter_reason, 'message_id': message_id}

    # DEV: Store full email content for parser development (BEFORE duplicate check)
    # This stores body_html, body_text, and other fields for debugging
    # We store for ALL filtered emails, even duplicates, so we have content for parser dev
    try:
        database.save_gmail_email_content(message)
    except Exception as e:
        logger.warning(f"Failed to store email content: {e}", extra={'message_id': message_id})

    # Check for duplicate by message_id (skip if force_reparse is enabled)
    if not force_reparse:
        existing = database.get_gmail_receipt_by_message_id(message_id)
        if existing:
            return {'duplicate': True, 'message_id': message_id}

    # PARSE INLINE - extract structured data while we have the content
    parsed_data = parse_receipt_content(
        html_body=message.get('body_html'),
        text_body=message.get('body_text'),
        subject=subject,
        sender_email=sender_email,
        sender_domain=sender_domain,
        sender_name=sender_name,
        list_unsubscribe=message.get('list_unsubscribe', ''),
        skip_llm=True,  # Faster sync, no LLM cost
        received_at=message.get('received_at')  # Fallback date if parsing fails
    )

    # Don't store emails rejected by pre-filter (marketing, non-receipts, etc.)
    if parsed_data.get('parse_method') == 'pre_filter':
        return {
            'filtered': True,
            'reason': parsed_data.get('parsing_error', 'Pre-filtered'),
            'message_id': message_id
        }

    # PDF FALLBACK - If no amount extracted and PDF attachments exist, try parsing PDFs
    # This handles merchants like Bax Music where invoice details are only in PDF
    if not parsed_data.get('total_amount') and service and message.get('attachments'):
        attachments = message.get('attachments', [])
        # Look for invoice-like PDFs (filename contains invoice, INV, receipt, bill, etc.)
        invoice_keywords = ('invoice', 'inv-', 'inv_', 'receipt', 'bill', 'order', 'facture', 'rechnung')
        # Known PDF vendors that always have invoices in PDFs (even with UUID filenames)
        pdf_vendor_domains = ('ctshirts.com', 'ctshirts.co.uk', 'suffolklatchcompany.co.uk')
        # Check if subject mentions invoice/receipt (e.g., "Invoice has been created for your order")
        subject_mentions_invoice = any(keyword in subject.lower() for keyword in invoice_keywords) if subject else False

        for attachment in attachments:
            filename = attachment.get('filename', '').lower()
            is_pdf = attachment.get('mime_type', '').startswith('application/pdf')
            is_invoice_filename = any(keyword in filename for keyword in invoice_keywords)
            is_known_pdf_vendor = sender_domain in pdf_vendor_domains

            if is_pdf and (is_invoice_filename or is_known_pdf_vendor or subject_mentions_invoice):
                logger.info(f"Parsing PDF invoice: {attachment.get('filename')}",
                           extra={'message_id': message_id, 'merchant': sender_domain})
                try:
                    # Download PDF attachment
                    pdf_bytes = get_attachment_content(
                        service,
                        message_id,
                        attachment.get('attachment_id')
                    )

                    if pdf_bytes:
                        # Parse PDF to extract amount and other data
                        pdf_data = parse_receipt_pdf(
                            pdf_bytes,
                            sender_domain=sender_domain,
                            filename=attachment.get('filename')
                        )

                        if pdf_data and pdf_data.get('total_amount'):
                            # Merge PDF data into parsed_data (PDF takes precedence for amount)
                            parsed_data['total_amount'] = pdf_data['total_amount']
                            parsed_data['currency_code'] = pdf_data.get('currency_code', parsed_data.get('currency_code', 'GBP'))

                            # Also update order_id and date if PDF has better data
                            if pdf_data.get('order_id') and not parsed_data.get('order_id'):
                                parsed_data['order_id'] = pdf_data['order_id']
                            if pdf_data.get('receipt_date') and not parsed_data.get('receipt_date'):
                                parsed_data['receipt_date'] = pdf_data['receipt_date']
                            if pdf_data.get('line_items') and not parsed_data.get('line_items'):
                                parsed_data['line_items'] = pdf_data['line_items']

                            # Update parse method to indicate PDF was used
                            if parsed_data.get('parse_method'):
                                parsed_data['parse_method'] = f"{parsed_data['parse_method']}_pdf_fallback"
                            else:
                                parsed_data['parse_method'] = 'pdf_fallback'

                            logger.info(f"Extracted amount from PDF: {pdf_data.get('currency_code', 'GBP')} {pdf_data['total_amount']}",
                                       extra={'message_id': message_id, 'merchant': sender_domain})
                            break  # Found amount, stop checking other PDFs

                except Exception as e:
                    logger.warning(f"PDF parsing failed: {e}",
                                  extra={'message_id': message_id, 'merchant': sender_domain})
                    # Continue to next attachment or fall through

    # Track PDF tasks for async processing (Phase 2 Optimization)
    pdf_task_info = None  # Will contain task dispatch info if PDFs found

    # For PDF-based receipts (e.g., Charles Tyrwhitt, Google Cloud, Xero, Atlassian, Suffolk Latch)
    pdf_domains = ('ctshirts.com', 'ctshirts.co.uk', 'google.com', 'post.xero.com', 'am.atlassian.com', 'atlassian.com', 'suffolklatchcompany.co.uk')
    if sender_domain in pdf_domains and service:
        attachments = message.get('attachments', [])
        if attachments:
            # Queue PDF for async processing instead of processing inline
            # This eliminates 2-5s blocking per PDF receipt
            for attachment in attachments:
                if attachment.get('mime_type', '').startswith('application/pdf'):
                    pdf_task_info = {
                        'attachment_id': attachment.get('attachment_id'),
                        'filename': attachment.get('filename', 'receipt.pdf')
                    }
                    logger.info(f"PDF attachment queued for async processing: {pdf_task_info['filename']}",
                               extra={'message_id': message_id, 'merchant': sender_domain})
                    break

    # For Translink, extract PDF link from email body (async processing)
    if sender_domain == 'translink.co.uk' and not pdf_task_info:
        html_body = message.get('body_html', '')
        # Look for receipt link pattern
        link_match = re.search(r'href="([^"]+)"[^>]*>\s*Click here to view your receipt', html_body, re.IGNORECASE)
        if link_match:
            receipt_url = link_match.group(1)
            pdf_task_info = {
                'external_url': receipt_url,
                'filename': 'translink_receipt.pdf'
            }
            logger.info(f"Translink PDF queued for async processing: {receipt_url}",
                       extra={'message_id': message_id, 'merchant': sender_domain})

    # Build receipt data dictionary (with parsed data, NOT raw body)
    receipt_data = {
        'thread_id': message.get('thread_id'),
        'sender_email': sender_email,
        'sender_name': sender_name,
        'subject': subject,
        'received_at': message.get('received_at'),
        'merchant_domain': sender_domain,
        # Populated from parsed_data
        'merchant_name': parsed_data.get('merchant_name'),
        'merchant_name_normalized': parsed_data.get('merchant_name_normalized'),
        'total_amount': parsed_data.get('total_amount'),
        'currency_code': parsed_data.get('currency_code', 'GBP'),
        'receipt_date': parsed_data.get('receipt_date'),
        'order_id': parsed_data.get('order_id'),
        'line_items': parsed_data.get('line_items'),
        'receipt_hash': None,  # Will be computed if we have amount/merchant
        'parse_method': parsed_data.get('parse_method', 'unknown'),
        'parse_confidence': parsed_data.get('parse_confidence', 0),
        'parsing_status': parsed_data.get('parsing_status', 'unparseable'),
        'parsing_error': parsed_data.get('parsing_error'),
        'llm_cost_cents': parsed_data.get('llm_cost_cents'),
        # Store metadata only (NOT raw body)
        'raw_schema_data': {
            'snippet': message.get('snippet'),
            'attachments': message.get('attachments', []),
            'list_unsubscribe': message.get('list_unsubscribe', ''),
            'x_mailer': message.get('x_mailer', ''),
            # NO body_html or body_text - that's the point!
        }
    }

    # Compute receipt hash if we have key data
    if receipt_data.get('merchant_name') and receipt_data.get('total_amount'):
        receipt_data['receipt_hash'] = compute_receipt_hash(
            merchant_name=receipt_data['merchant_name'],
            amount=receipt_data['total_amount'],
            receipt_date=receipt_data.get('receipt_date'),
            order_id=receipt_data.get('order_id')
        )

    # Set PDF processing status if we have PDFs to process
    if pdf_task_info:
        receipt_data['pdf_processing_status'] = 'pending'

    # Store parsed receipt
    receipt_id = database.save_gmail_receipt(connection_id, message_id, receipt_data)

    # Dispatch PDF processing task asynchronously (Phase 2 Optimization)
    # This eliminates 2-5s blocking per PDF receipt
    pdf_task_queued = False
    if pdf_task_info and receipt_id:
        try:
            from tasks.gmail_tasks import process_pdf_receipt_task

            # Dispatch task to Celery (non-blocking, returns immediately)
            process_pdf_receipt_task.delay(
                receipt_id=receipt_id,
                message_id=message_id,
                attachment_info=pdf_task_info,
                sender_domain=sender_domain,
                connection_id=connection_id,
                received_date=message.get('received_at')
            )

            pdf_task_queued = True
            logger.info(f"PDF task queued for receipt {receipt_id}",
                       extra={'receipt_id': receipt_id, 'message_id': message_id})
        except Exception as e:
            # Don't fail sync if task dispatch fails
            logger.warning(f"PDF task dispatch failed (non-fatal): {e}",
                          extra={'receipt_id': receipt_id, 'message_id': message_id})
            # Reset status to 'failed' if task dispatch failed
            database.update_gmail_receipt_pdf_status(receipt_id, 'failed', error=str(e))

            # CRITICAL FIX: Track PDF task dispatch failures
            try:
                from mcp.error_tracking import GmailError, ErrorStage, ErrorType
                error = GmailError(
                    stage=ErrorStage.PDF_PARSE,
                    error_type=ErrorType.UNKNOWN,
                    message=f"PDF task dispatch failed: {e}",
                    exception=e,
                    context={'receipt_id': receipt_id, 'message_id': message_id},
                    is_retryable=True  # Task dispatch failures are often retryable
                )
                error.log(connection_id=connection_id)
            except:
                pass  # Don't let error tracking crash sync

    return {
        'stored': True,
        'receipt_id': receipt_id,
        'message_id': message_id,
        'parsing_status': receipt_data['parsing_status'],
        'pdf_task_queued': pdf_task_queued,
        # Include data for statistics tracking
        'sender_domain': sender_domain,
        'receipt_data': receipt_data
    }


def prepare_receipt_data(connection_id: int, message: dict, service=None, force_reparse: bool = False) -> dict:
    """
    Parse email and prepare data for bulk insert (Phase 3 Optimization).

    This is a non-writing version of store_parsed_receipt() that returns data
    to be bulk inserted later.

    Returns:
        dict with 'action', 'message', 'email_content', 'receipt_data', 'pdf_task_info'
        where action can be 'store', 'duplicate', or 'filtered'
    """
    message_id = message.get('message_id')

    # Parse sender
    sender_email, sender_name = parse_sender_email(message.get('from', ''))
    sender_domain = extract_sender_domain(sender_email)

    # Early filter: reject known non-receipt emails BEFORE parsing
    subject = message.get('subject', '')
    body_text = message.get('body_text') or message.get('body_html', '')
    should_import, filter_reason = should_import_email(subject, sender_email, body_text)
    if not should_import:
        return {
            'action': 'filtered',
            'reason': filter_reason,
            'message_id': message_id,
            'message': message,  # For email_content storage
            'sender_domain': sender_domain  # Required for statistics tracking
        }

    # Check for duplicate by message_id (skip if force_reparse is enabled)
    if not force_reparse:
        existing = database.get_gmail_receipt_by_message_id(message_id)
        if existing:
            return {
                'action': 'duplicate',
                'message_id': message_id,
                'message': message,  # For email_content storage
                'sender_domain': sender_domain  # Required for statistics tracking
            }

    # PARSE INLINE - extract structured data
    parsed_data = parse_receipt_content(
        html_body=message.get('body_html'),
        text_body=message.get('body_text'),
        subject=subject,
        sender_email=sender_email,
        sender_domain=sender_domain,
        sender_name=sender_name,
        list_unsubscribe=message.get('list_unsubscribe', ''),
        skip_llm=True,
        received_at=message.get('received_at')  # Fallback date if parsing fails
    )

    # Don't store emails rejected by pre-filter
    if parsed_data.get('parse_method') == 'pre_filter':
        return {
            'action': 'filtered',
            'reason': parsed_data.get('parsing_error', 'Pre-filtered'),
            'message_id': message_id,
            'message': message,
            'sender_domain': sender_domain  # Required for statistics tracking
        }

    # PDF FALLBACK - If no amount extracted and PDF attachments exist, try parsing PDFs
    # This handles merchants like Bax Music where invoice details are only in PDF
    if not parsed_data.get('total_amount') and service and message.get('attachments'):
        attachments = message.get('attachments', [])
        # Look for invoice-like PDFs (filename contains invoice, INV, receipt, bill, etc.)
        invoice_keywords = ('invoice', 'inv-', 'inv_', 'receipt', 'bill', 'order', 'facture', 'rechnung')
        # Known PDF vendors that always have invoices in PDFs (even with UUID filenames)
        pdf_vendor_domains = ('ctshirts.com', 'ctshirts.co.uk', 'suffolklatchcompany.co.uk')
        # Check if subject mentions invoice/receipt (e.g., "Invoice has been created for your order")
        subject_mentions_invoice = any(keyword in subject.lower() for keyword in invoice_keywords) if subject else False

        for attachment in attachments:
            filename = attachment.get('filename', '').lower()
            is_pdf = attachment.get('mime_type', '').startswith('application/pdf')
            is_invoice_filename = any(keyword in filename for keyword in invoice_keywords)
            is_known_pdf_vendor = sender_domain in pdf_vendor_domains

            if is_pdf and (is_invoice_filename or is_known_pdf_vendor or subject_mentions_invoice):
                logger.info(f"Parsing PDF invoice: {attachment.get('filename')}",
                           extra={'message_id': message_id, 'merchant': sender_domain})
                try:
                    # Download PDF attachment
                    pdf_bytes = get_attachment_content(
                        service,
                        message_id,
                        attachment.get('attachment_id')
                    )

                    if pdf_bytes:
                        # Parse PDF to extract amount and other data
                        pdf_data = parse_receipt_pdf(
                            pdf_bytes,
                            sender_domain=sender_domain,
                            filename=attachment.get('filename')
                        )

                        if pdf_data and pdf_data.get('total_amount'):
                            # Merge PDF data into parsed_data (PDF takes precedence for amount)
                            parsed_data['total_amount'] = pdf_data['total_amount']
                            parsed_data['currency_code'] = pdf_data.get('currency_code', parsed_data.get('currency_code', 'GBP'))

                            # Also update order_id and date if PDF has better data
                            if pdf_data.get('order_id') and not parsed_data.get('order_id'):
                                parsed_data['order_id'] = pdf_data['order_id']
                            if pdf_data.get('receipt_date') and not parsed_data.get('receipt_date'):
                                parsed_data['receipt_date'] = pdf_data['receipt_date']
                            if pdf_data.get('line_items') and not parsed_data.get('line_items'):
                                parsed_data['line_items'] = pdf_data['line_items']

                            # Update parse method to indicate PDF was used
                            if parsed_data.get('parse_method'):
                                parsed_data['parse_method'] = f"{parsed_data['parse_method']}_pdf_fallback"
                            else:
                                parsed_data['parse_method'] = 'pdf_fallback'

                            logger.info(f"Extracted amount from PDF: {pdf_data.get('currency_code', 'GBP')} {pdf_data['total_amount']}",
                                       extra={'message_id': message_id, 'merchant': sender_domain})
                            break  # Found amount, stop checking other PDFs

                except Exception as e:
                    logger.warning(f"PDF parsing failed: {e}",
                                  extra={'message_id': message_id, 'merchant': sender_domain})
                    # Continue to next attachment or fall through

    # Track PDF tasks for async processing
    pdf_task_info = None

    # For PDF-based receipts
    pdf_domains = ('ctshirts.com', 'ctshirts.co.uk', 'google.com', 'post.xero.com', 'am.atlassian.com', 'atlassian.com', 'suffolklatchcompany.co.uk')
    if sender_domain in pdf_domains and service:
        attachments = message.get('attachments', [])
        if attachments:
            for attachment in attachments:
                if attachment.get('mime_type', '').startswith('application/pdf'):
                    pdf_task_info = {
                        'attachment_id': attachment.get('attachment_id'),
                        'filename': attachment.get('filename', 'receipt.pdf')
                    }
                    break

    # For Translink, extract PDF link from email body
    if sender_domain == 'translink.co.uk' and not pdf_task_info:
        html_body = message.get('body_html', '')
        link_match = re.search(r'href="([^"]+)"[^>]*>\s*Click here to view your receipt', html_body, re.IGNORECASE)
        if link_match:
            receipt_url = link_match.group(1)
            pdf_task_info = {
                'external_url': receipt_url,
                'filename': 'translink_receipt.pdf'
            }

    # Build receipt data dictionary
    receipt_data = {
        'thread_id': message.get('thread_id'),
        'sender_email': sender_email,
        'sender_name': sender_name,
        'subject': subject,
        'received_at': message.get('received_at'),
        'merchant_domain': sender_domain,
        'merchant_name': parsed_data.get('merchant_name'),
        'merchant_name_normalized': parsed_data.get('merchant_name_normalized'),
        'total_amount': parsed_data.get('total_amount'),
        'currency_code': parsed_data.get('currency_code', 'GBP'),
        'receipt_date': parsed_data.get('receipt_date'),
        'order_id': parsed_data.get('order_id'),
        'line_items': parsed_data.get('line_items'),
        'receipt_hash': None,
        'parse_method': parsed_data.get('parse_method', 'unknown'),
        'parse_confidence': parsed_data.get('parse_confidence', 0),
        'parsing_status': parsed_data.get('parsing_status', 'unparseable'),
        'parsing_error': parsed_data.get('parsing_error'),
        'llm_cost_cents': parsed_data.get('llm_cost_cents'),
        'raw_schema_data': {
            'snippet': message.get('snippet'),
            'attachments': message.get('attachments', []),
            'list_unsubscribe': message.get('list_unsubscribe', ''),
            'x_mailer': message.get('x_mailer', ''),
        }
    }

    # Compute receipt hash if we have key data
    if receipt_data.get('merchant_name') and receipt_data.get('total_amount'):
        receipt_data['receipt_hash'] = compute_receipt_hash(
            merchant_name=receipt_data['merchant_name'],
            amount=receipt_data['total_amount'],
            receipt_date=receipt_data.get('receipt_date'),
            order_id=receipt_data.get('order_id')
        )

    # Set PDF processing status if we have PDFs to process
    if pdf_task_info:
        receipt_data['pdf_processing_status'] = 'pending'

    return {
        'action': 'store',
        'message_id': message_id,
        'message': message,  # For email_content storage
        'connection_id': connection_id,
        'receipt_data': receipt_data,
        'pdf_task_info': pdf_task_info,
        'sender_domain': sender_domain
    }


# Keep old name as alias for backwards compatibility during transition
store_pending_receipt = store_parsed_receipt


def get_sync_status(connection_id: int) -> dict:
    """
    Get current sync status for a connection.

    Args:
        connection_id: Database connection ID

    Returns:
        Status dictionary
    """
    connection = database.get_gmail_connection_by_id(connection_id)
    if not connection:
        return {'error': 'Connection not found'}

    # Get latest sync job
    job = database.get_latest_gmail_sync_job(connection_id)

    stats = database.get_gmail_statistics(connection.get('user_id', 1))

    return {
        'connection_id': connection_id,
        'email_address': connection.get('email_address'),
        'connection_status': connection.get('connection_status'),
        'last_synced_at': connection.get('last_synced_at'),
        'history_id': connection.get('history_id'),
        'latest_job': job,
        'statistics': stats,
    }


def start_sync(
    connection_id: int,
    sync_type: str = 'auto',
    from_date: datetime = None,
    to_date: datetime = None
) -> dict:
    """
    Start a sync job.

    Args:
        connection_id: Database connection ID
        sync_type: 'full', 'incremental', or 'auto'
        from_date: Optional start date for full sync
        to_date: Optional end date for full sync

    Returns:
        Initial job status
    """
    connection = database.get_gmail_connection_by_id(connection_id)
    if not connection:
        raise ValueError(f"Gmail connection {connection_id} not found")

    # Determine sync type
    if sync_type == 'auto':
        # Use incremental if we have a history ID
        if connection.get('history_id'):
            sync_type = 'incremental'
        else:
            sync_type = 'full'

    logger.info(f"Starting {sync_type} sync for connection {connection_id}",
               extra={'connection_id': connection_id, 'sync_type': sync_type})

    if sync_type == 'incremental':
        return sync_receipts_incremental(connection_id)
    else:
        # Full sync - run as generator and return final result
        result = None
        for progress in sync_receipts_full(connection_id, from_date=from_date, to_date=to_date):
            result = progress
        return result
