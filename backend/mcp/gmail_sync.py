"""
Gmail Sync Module

Handles synchronization of receipt emails from Gmail.
Supports full sync (initial) and incremental sync (subsequent).
"""

import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional, Generator

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


# Sync configuration
DEFAULT_SYNC_MONTHS = 12  # Default to last 12 months
MAX_MESSAGES_PER_SYNC = 5000  # Safety limit
BATCH_SIZE = 50  # Messages to process before updating progress


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
    job_id: int = None
) -> Generator[dict, None, dict]:
    """
    Full sync of all receipt emails.

    Yields progress updates and returns final results.

    Args:
        connection_id: Database connection ID
        from_date: Optional start date (defaults to 12 months ago)
        to_date: Optional end date (defaults to today)

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
    print(f"📧 Starting full Gmail sync: job={job_id}, connection={connection_id}")

    try:
        # Get valid credentials (access and refresh tokens)
        access_token, refresh_token = get_gmail_credentials(connection_id)

        # Build Gmail service with both tokens for auto-refresh support
        service = build_gmail_service(access_token, refresh_token)

        # Get user profile for history ID
        profile = get_user_profile(service)
        latest_history_id = profile.get('history_id')
        print(f"   📬 Gmail profile: {profile['email_address']}, history_id={latest_history_id}")

        # Set date range
        if from_date is None:
            # Use stored sync_from_date or default to 12 months
            if connection.get('sync_from_date'):
                from_date = datetime.fromisoformat(str(connection['sync_from_date']))
            else:
                from_date = datetime.utcnow() - timedelta(days=DEFAULT_SYNC_MONTHS * 30)

        # Build search query with date range
        query = build_receipt_query(from_date=from_date, to_date=to_date)
        print(f"   🔍 Search query: {query[:100]}...")

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
            print(f"   📄 Page {page_count}: {len(messages)} messages (total: {len(all_message_ids)})")

            # Safety limit
            if len(all_message_ids) >= MAX_MESSAGES_PER_SYNC:
                print(f"   ⚠️  Hit message limit ({MAX_MESSAGES_PER_SYNC})")
                break

            page_token = result.get('nextPageToken')
            if not page_token:
                break

        total_messages = len(all_message_ids)
        print(f"   📊 Found {total_messages} potential receipt messages")

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

        for i in range(0, total_messages, BATCH_SIZE):
            batch_ids = all_message_ids[i:i + BATCH_SIZE]

            for msg_id in batch_ids:
                try:
                    # Fetch message content
                    msg = get_message_content(service, msg_id)

                    # Store as pending receipt (parsing happens separately)
                    result = store_pending_receipt(connection_id, msg, service)

                    if result.get('stored'):
                        parsed += 1
                    elif result.get('duplicate'):
                        duplicates += 1
                    elif result.get('filtered'):
                        filtered += 1

                    processed += 1

                except Exception as e:
                    print(f"   ⚠️  Failed to process message {msg_id}: {e}")
                    failed += 1
                    processed += 1

            # Update progress
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

        print(f"   ✅ Sync completed: {parsed} receipts stored, {duplicates} duplicates, {failed} failed")

        yield final_result
        return final_result

    except Exception as e:
        print(f"   ❌ Sync failed: {e}")
        database.complete_gmail_sync_job(job_id, 'failed', str(e))
        raise


def sync_receipts_incremental(connection_id: int, job_id: int = None) -> dict:
    """
    Incremental sync using Gmail history API.

    Only fetches messages added since last sync.

    Args:
        connection_id: Database connection ID

    Returns:
        Results dictionary
    """
    # Get connection details
    connection = database.get_gmail_connection_by_id(connection_id)
    if not connection:
        raise ValueError(f"Gmail connection {connection_id} not found")

    history_id = connection.get('history_id')
    if not history_id:
        print("   ⚠️  No history ID, falling back to full sync")
        # Convert generator to final result
        result = None
        for progress in sync_receipts_full(connection_id):
            result = progress
        return result

    # Create sync job only if not provided (avoids duplicate job creation)
    if job_id is None:
        job_id = database.create_gmail_sync_job(connection_id, job_type='incremental')
    print(f"📧 Starting incremental Gmail sync: job={job_id}, history_id={history_id}")

    try:
        # Get valid credentials (access and refresh tokens)
        access_token, refresh_token = get_gmail_credentials(connection_id)

        # Build Gmail service with both tokens for auto-refresh support
        service = build_gmail_service(access_token, refresh_token)

        # Get changes since last sync
        changes = get_history_changes(service, history_id)

        if changes.get('full_sync_required'):
            print("   ⚠️  History expired, falling back to full sync")
            database.complete_gmail_sync_job(job_id, status='cancelled')
            result = None
            for progress in sync_receipts_full(connection_id):
                result = progress
            return result

        new_message_ids = changes.get('new_message_ids', [])
        latest_history_id = changes.get('latest_history_id')

        print(f"   📬 Found {len(new_message_ids)} new messages since last sync")

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
                result = store_pending_receipt(connection_id, msg, service)

                if result.get('stored'):
                    parsed += 1
                elif result.get('duplicate'):
                    duplicates += 1
                elif result.get('filtered'):
                    filtered += 1

            except Exception as e:
                print(f"   ⚠️  Failed to process message {msg_id}: {e}")
                failed += 1

        # Update history ID
        if latest_history_id:
            database.update_gmail_history_id(connection_id, latest_history_id)

        # Update connection status
        database.update_gmail_connection_status(connection_id, 'active')

        # Complete job
        database.complete_gmail_sync_job(job_id, 'completed')

        print(f"   ✅ Incremental sync completed: {parsed} new receipts, {filtered} filtered")

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
        print(f"   ❌ Incremental sync failed: {e}")
        database.complete_gmail_sync_job(job_id, 'failed', str(e))
        raise


def store_parsed_receipt(connection_id: int, message: dict, service=None) -> dict:
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
        print(f"   ⚠️ Failed to store email content: {e}")

    # DEV FLAG: Set to True to re-parse all emails (bypass duplicate check)
    SKIP_DUPLICATE_CHECK_DEV = False  # Set to True for re-parsing during development

    # Check for duplicate by message_id
    if not SKIP_DUPLICATE_CHECK_DEV:
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
        skip_llm=True  # Faster sync, no LLM cost
    )

    # Don't store emails rejected by pre-filter (marketing, non-receipts, etc.)
    if parsed_data.get('parse_method') == 'pre_filter':
        return {
            'filtered': True,
            'reason': parsed_data.get('parsing_error', 'Pre-filtered'),
            'message_id': message_id
        }

    # For PDF-based receipts (e.g., Charles Tyrwhitt, Google Cloud, Xero, Atlassian, Suffolk Latch), parse PDF attachment
    pdf_domains = ('ctshirts.com', 'google.com', 'post.xero.com', 'am.atlassian.com', 'atlassian.com', 'suffolklatchcompany.co.uk')
    pdfs_to_store = []  # Track PDFs for MinIO storage
    if sender_domain in pdf_domains and service:
        attachments = message.get('attachments', [])
        if attachments:
            from .gmail_client import get_pdf_attachments
            from .gmail_pdf_parser import parse_receipt_pdf

            pdf_contents = get_pdf_attachments(service, message_id, attachments)
            for pdf in pdf_contents:
                pdf_result = parse_receipt_pdf(pdf['content'], sender_domain, pdf.get('filename'))
                # Use 'is not None' to allow £0.00 amounts (common for Google Cloud free tier)
                if pdf_result and pdf_result.get('total_amount') is not None:
                    # Use PDF-extracted data
                    parsed_data = pdf_result
                    parsed_data['parsing_status'] = 'parsed'
                    # Queue PDF for MinIO storage
                    pdfs_to_store.append({
                        'content': pdf['content'],
                        'filename': pdf.get('filename', 'receipt.pdf')
                    })
                    break

    # For Translink, extract PDF link from email body and download
    if sender_domain == 'translink.co.uk':
        html_body = message.get('body_html', '')
        # Look for receipt link pattern
        link_match = re.search(r'href="([^"]+)"[^>]*>\s*Click here to view your receipt', html_body, re.IGNORECASE)
        if link_match:
            receipt_url = link_match.group(1)
            try:
                import requests
                response = requests.get(receipt_url, timeout=30)
                if response.status_code == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'pdf' in content_type:
                        from .gmail_pdf_parser import parse_generic_receipt_pdf
                        pdf_result = parse_generic_receipt_pdf(response.content, 'Translink')
                        if pdf_result and pdf_result.get('total_amount') is not None:
                            parsed_data = pdf_result
                            parsed_data['parsing_status'] = 'parsed'
                            parsed_data['parse_method'] = 'vendor_translink_pdf'
                            # Queue PDF for MinIO storage
                            pdfs_to_store.append({
                                'content': response.content,
                                'filename': 'translink_receipt.pdf'
                            })
            except Exception as e:
                print(f"   ⚠️ Failed to download Translink PDF: {e}")

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

    # Store parsed receipt
    receipt_id = database.save_gmail_receipt(connection_id, message_id, receipt_data)

    # Store PDFs in MinIO (if available and we have PDFs)
    pdfs_stored = 0
    if pdfs_to_store and receipt_id:
        try:
            from .minio_client import is_available, store_pdf
            if is_available():
                received_date = message.get('received_at')
                if isinstance(received_date, str):
                    from datetime import datetime
                    try:
                        received_date = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
                    except:
                        received_date = None

                for pdf_item in pdfs_to_store:
                    minio_result = store_pdf(
                        pdf_bytes=pdf_item['content'],
                        message_id=message_id,
                        filename=pdf_item['filename'],
                        received_date=received_date,
                        metadata={'merchant': parsed_data.get('merchant_name')}
                    )
                    if minio_result:
                        # Save PDF attachment record in database
                        database.save_pdf_attachment(
                            gmail_receipt_id=receipt_id,
                            message_id=message_id,
                            bucket_name=minio_result['bucket_name'],
                            object_key=minio_result['object_key'],
                            filename=minio_result['filename'],
                            content_hash=minio_result['content_hash'],
                            size_bytes=minio_result['size_bytes'],
                            etag=minio_result['etag']
                        )
                        pdfs_stored += 1
        except Exception as e:
            # Don't fail sync if MinIO storage fails
            print(f"   ⚠️ MinIO storage error (non-fatal): {e}")

    return {
        'stored': True,
        'receipt_id': receipt_id,
        'message_id': message_id,
        'parsing_status': receipt_data['parsing_status'],
        'pdfs_stored': pdfs_stored
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

    print(f"📧 Starting {sync_type} sync for connection {connection_id}")

    if sync_type == 'incremental':
        return sync_receipts_incremental(connection_id)
    else:
        # Full sync - run as generator and return final result
        result = None
        for progress in sync_receipts_full(connection_id, from_date=from_date, to_date=to_date):
            result = progress
        return result
