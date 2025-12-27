"""
Gmail Integration - Database Operations

Handles all database operations for Gmail receipt parsing and matching.

Modules:
- Connection management (save_gmail_connection, get_gmail_connection, etc.)
- OAuth state management (store_gmail_oauth_state, get_gmail_oauth_state, etc.)
- Receipt operations (save_gmail_receipt, get_gmail_receipts, etc.)
- Email content storage (save_gmail_email_content, get_gmail_email_content, etc.)
- Transaction matching (save_gmail_match, get_gmail_matches_for_transaction, etc.)
- Sync job tracking (create_gmail_sync_job, update_gmail_sync_job_progress, etc.)
- Statistics and aggregation (get_gmail_statistics, get_gmail_merchants_summary, etc.)
- LLM queue management (get_unparseable_receipts_for_llm_queue, update_receipt_llm_status, etc.)
- PDF attachment tracking (save_pdf_attachment, get_pdf_attachments_for_receipt, etc.)
- Error tracking (save_gmail_error, get_gmail_error_summary, etc.)
"""

import json
from datetime import datetime

from psycopg2.extras import RealDictCursor

from .base import get_db

# ============================================================================
# GMAIL INTEGRATION FUNCTIONS
# ============================================================================


def save_gmail_connection(
    user_id: int,
    email_address: str,
    access_token: str,
    refresh_token: str,
    token_expires_at: str,
    scopes: str = None,
) -> int:
    """
    Save or update a Gmail connection.

    Args:
        user_id: User ID
        email_address: Connected Gmail address
        access_token: Encrypted access token
        refresh_token: Encrypted refresh token
        token_expires_at: ISO format expiration timestamp
        scopes: OAuth scopes granted

    Returns:
        Connection ID
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO gmail_connections
                (user_id, email_address, access_token, refresh_token,
                 token_expires_at, scopes, connection_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'active')
                ON CONFLICT (user_id, email_address) DO UPDATE
                SET access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    token_expires_at = EXCLUDED.token_expires_at,
                    scopes = EXCLUDED.scopes,
                    connection_status = 'active',
                    error_count = 0,
                    last_error = NULL,
                    updated_at = NOW()
                RETURNING id
            """,
            (
                user_id,
                email_address,
                access_token,
                refresh_token,
                token_expires_at,
                scopes,
            ),
        )
        result = cursor.fetchone()
        conn.commit()
        return result[0] if result else None


def get_gmail_connection(user_id: int) -> dict:
    """Get Gmail connection for a user."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, user_id, email_address, access_token, refresh_token,
                       token_expires_at, scopes, connection_status, history_id,
                       last_synced_at, sync_from_date, error_count, last_error,
                       created_at, updated_at
                FROM gmail_connections
                WHERE user_id = %s AND connection_status = 'active'
                ORDER BY created_at DESC
                LIMIT 1
            """,
            (user_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_gmail_connection_by_id(connection_id: int) -> dict:
    """Get Gmail connection by ID."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, user_id, email_address, access_token, refresh_token,
                       token_expires_at, scopes, connection_status, history_id,
                       last_synced_at, sync_from_date, error_count, last_error,
                       created_at, updated_at
                FROM gmail_connections
                WHERE id = %s
            """,
            (connection_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def update_gmail_tokens(
    connection_id: int, access_token: str, refresh_token: str, token_expires_at: str
) -> bool:
    """Update Gmail tokens after refresh."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_connections
                SET access_token = %s,
                    refresh_token = %s,
                    token_expires_at = %s,
                    connection_status = 'active',
                    error_count = 0,
                    updated_at = NOW()
                WHERE id = %s
            """,
            (access_token, refresh_token, token_expires_at, connection_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def update_gmail_connection_status(
    connection_id: int, status: str, error: str = None
) -> bool:
    """Update Gmail connection status and error info."""
    with get_db() as conn, conn.cursor() as cursor:
        if error:
            cursor.execute(
                """
                    UPDATE gmail_connections
                    SET connection_status = %s,
                        error_count = error_count + 1,
                        last_error = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """,
                (status, error, connection_id),
            )
        else:
            cursor.execute(
                """
                    UPDATE gmail_connections
                    SET connection_status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """,
                (status, connection_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def update_gmail_history_id(connection_id: int, history_id: str) -> bool:
    """Update Gmail historyId for incremental sync."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_connections
                SET history_id = %s,
                    last_synced_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """,
            (history_id, connection_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_gmail_connection(connection_id: int) -> bool:
    """Delete Gmail connection (cascades to receipts and matches)."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                DELETE FROM gmail_connections WHERE id = %s
            """,
            (connection_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


# Gmail OAuth State functions
def store_gmail_oauth_state(user_id: int, state: str, code_verifier: str) -> bool:
    """Store OAuth state for CSRF protection (10-minute expiration)."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gmail_oauth_state (user_id, state, code_verifier, expires_at)
                VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')
                ON CONFLICT (state) DO UPDATE
                SET user_id = EXCLUDED.user_id,
                    code_verifier = EXCLUDED.code_verifier,
                    expires_at = EXCLUDED.expires_at
            """,
                (user_id, state, code_verifier),
            )
            conn.commit()
            return True


def get_gmail_oauth_state(state: str) -> dict:
    """Get OAuth state by state parameter."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT user_id, state, code_verifier, expires_at
                FROM gmail_oauth_state
                WHERE state = %s AND expires_at > NOW()
            """,
            (state,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def delete_gmail_oauth_state(state: str) -> bool:
    """Delete OAuth state after use."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                DELETE FROM gmail_oauth_state WHERE state = %s
            """,
            (state,),
        )
        conn.commit()
        return cursor.rowcount > 0


def cleanup_expired_gmail_oauth_states() -> int:
    """Clean up expired OAuth states."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("""
                DELETE FROM gmail_oauth_state WHERE expires_at < NOW()
            """)
        conn.commit()
        return cursor.rowcount


# Gmail Receipts functions
def save_gmail_receipt(connection_id: int, message_id: str, receipt_data: dict) -> int:
    """Save a parsed Gmail receipt."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO gmail_receipts
                (connection_id, message_id, thread_id, sender_email, sender_name,
                 subject, received_at, merchant_name, merchant_name_normalized,
                 merchant_domain, order_id, total_amount, currency_code, receipt_date,
                 line_items, receipt_hash, parse_method, parse_confidence,
                 raw_schema_data, llm_cost_cents, parsing_status, pdf_processing_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE
                SET merchant_name = EXCLUDED.merchant_name,
                    merchant_name_normalized = EXCLUDED.merchant_name_normalized,
                    total_amount = EXCLUDED.total_amount,
                    parse_method = EXCLUDED.parse_method,
                    parse_confidence = EXCLUDED.parse_confidence,
                    parsing_status = EXCLUDED.parsing_status,
                    pdf_processing_status = EXCLUDED.pdf_processing_status,
                    updated_at = NOW()
                RETURNING id
            """,
            (
                connection_id,
                message_id,
                receipt_data.get("thread_id"),
                receipt_data.get("sender_email"),
                receipt_data.get("sender_name"),
                receipt_data.get("subject"),
                receipt_data.get("received_at"),
                receipt_data.get("merchant_name"),
                receipt_data.get("merchant_name_normalized"),
                receipt_data.get("merchant_domain"),
                receipt_data.get("order_id"),
                receipt_data.get("total_amount"),
                receipt_data.get("currency_code", "GBP"),
                receipt_data.get("receipt_date"),
                json.dumps(receipt_data.get("line_items")),
                receipt_data.get("receipt_hash"),
                receipt_data.get("parse_method"),
                receipt_data.get("parse_confidence"),
                json.dumps(receipt_data.get("raw_schema_data")),
                receipt_data.get("llm_cost_cents"),
                receipt_data.get("parsing_status", "parsed"),
                receipt_data.get("pdf_processing_status", "none"),
            ),
        )
        result = cursor.fetchone()
        conn.commit()
        return result[0] if result else None


def save_gmail_receipt_bulk(receipts: list) -> dict:
    """
    Bulk insert Gmail receipts (Phase 3 Optimization).

    Args:
        receipts: List of tuples (connection_id, message_id, receipt_data)

    Returns:
        dict with 'inserted' count, 'receipt_ids' list, 'message_to_id' mapping
    """
    if not receipts:
        return {"inserted": 0, "receipt_ids": [], "message_to_id": {}}

    # Prepare data tuples
    data = []
    message_ids_order = []
    for connection_id, message_id, receipt_data in receipts:
        message_ids_order.append(message_id)
        data.append(
            (
                connection_id,
                message_id,
                receipt_data.get("thread_id"),
                receipt_data.get("sender_email"),
                receipt_data.get("sender_name"),
                receipt_data.get("subject"),
                receipt_data.get("received_at"),
                receipt_data.get("merchant_name"),
                receipt_data.get("merchant_name_normalized"),
                receipt_data.get("merchant_domain"),
                receipt_data.get("order_id"),
                receipt_data.get("total_amount"),
                receipt_data.get("currency_code", "GBP"),
                receipt_data.get("receipt_date"),
                json.dumps(receipt_data.get("line_items")),
                receipt_data.get("receipt_hash"),
                receipt_data.get("parse_method"),
                receipt_data.get("parse_confidence"),
                json.dumps(receipt_data.get("raw_schema_data")),
                receipt_data.get("llm_cost_cents"),
                receipt_data.get("parsing_status", "parsed"),
                receipt_data.get("pdf_processing_status", "none"),
            )
        )

    with get_db() as conn, conn.cursor() as cursor:
        # Use execute_values for efficient bulk insert with RETURNING
        from psycopg2.extras import execute_values

        results = execute_values(
            cursor,
            """
                INSERT INTO gmail_receipts
                (connection_id, message_id, thread_id, sender_email, sender_name,
                 subject, received_at, merchant_name, merchant_name_normalized,
                 merchant_domain, order_id, total_amount, currency_code, receipt_date,
                 line_items, receipt_hash, parse_method, parse_confidence,
                 raw_schema_data, llm_cost_cents, parsing_status, pdf_processing_status)
                VALUES %s
                ON CONFLICT (message_id) DO UPDATE
                SET merchant_name = EXCLUDED.merchant_name,
                    merchant_name_normalized = EXCLUDED.merchant_name_normalized,
                    total_amount = EXCLUDED.total_amount,
                    parse_method = EXCLUDED.parse_method,
                    parse_confidence = EXCLUDED.parse_confidence,
                    parsing_status = EXCLUDED.parsing_status,
                    pdf_processing_status = EXCLUDED.pdf_processing_status,
                    updated_at = NOW()
                RETURNING id, message_id
                """,
            data,
            fetch=True,
        )
        conn.commit()

        # Build message_id -> receipt_id mapping
        receipt_ids = [row[0] for row in results]
        message_to_id = {row[1]: row[0] for row in results}

        return {
            "inserted": len(results),
            "receipt_ids": receipt_ids,
            "message_to_id": message_to_id,
        }


def save_gmail_email_content(message: dict) -> int:
    """
    Store full email content for development/debugging.

    Args:
        message: Message dict from gmail_client.get_message_content()

    Returns:
        ID of stored content record
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO gmail_email_content
                (message_id, thread_id, subject, from_header, to_header, date_header,
                 list_unsubscribe, x_mailer, body_html, body_text, snippet,
                 attachments, size_estimate, received_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO UPDATE
                SET body_html = EXCLUDED.body_html,
                    body_text = EXCLUDED.body_text,
                    attachments = EXCLUDED.attachments,
                    fetched_at = NOW()
                RETURNING id
            """,
            (
                message.get("message_id"),
                message.get("thread_id"),
                message.get("subject"),
                message.get("from"),
                message.get("to"),
                message.get("date"),
                message.get("list_unsubscribe"),
                message.get("x_mailer"),
                message.get("body_html"),
                message.get("body_text"),
                message.get("snippet"),
                json.dumps(message.get("attachments", [])),
                message.get("size_estimate"),
                message.get("received_at"),
            ),
        )
        result = cursor.fetchone()
        conn.commit()
        return result[0] if result else None


def save_gmail_email_content_bulk(messages: list) -> dict:
    """
    Bulk insert email content (Phase 3 Optimization).

    Args:
        messages: List of message dicts from gmail_client.get_message_content()

    Returns:
        dict with 'inserted' count and 'failed' list of message_ids
    """
    if not messages:
        return {"inserted": 0, "failed": []}

    # Prepare data tuples
    data = []
    for msg in messages:
        data.append(
            (
                msg.get("message_id"),
                msg.get("thread_id"),
                msg.get("subject"),
                msg.get("from"),
                msg.get("to"),
                msg.get("date"),
                msg.get("list_unsubscribe"),
                msg.get("x_mailer"),
                msg.get("body_html"),
                msg.get("body_text"),
                msg.get("snippet"),
                json.dumps(msg.get("attachments", [])),
                msg.get("size_estimate"),
                msg.get("received_at"),
            )
        )

    with get_db() as conn, conn.cursor() as cursor:
        # Use execute_values for efficient bulk insert
        from psycopg2.extras import execute_values

        execute_values(
            cursor,
            """
                INSERT INTO gmail_email_content
                (message_id, thread_id, subject, from_header, to_header, date_header,
                 list_unsubscribe, x_mailer, body_html, body_text, snippet,
                 attachments, size_estimate, received_at)
                VALUES %s
                ON CONFLICT (message_id) DO UPDATE
                SET body_html = EXCLUDED.body_html,
                    body_text = EXCLUDED.body_text,
                    attachments = EXCLUDED.attachments,
                    fetched_at = NOW()
                """,
            data,
        )
        conn.commit()
        return {"inserted": cursor.rowcount, "failed": []}


def get_gmail_email_content(message_id: str) -> dict:
    """Get stored email content by message_id for parser development."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT * FROM gmail_email_content WHERE message_id = %s
            """,
            (message_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_receipt_with_email_content(receipt_id: int) -> dict:
    """
    Get receipt with full email content for parser development.
    Joins gmail_receipts with gmail_email_content.
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT
                    r.*,
                    e.body_html,
                    e.body_text,
                    e.from_header,
                    e.to_header,
                    e.date_header,
                    e.attachments as email_attachments
                FROM gmail_receipts r
                LEFT JOIN gmail_email_content e ON r.message_id = e.message_id
                WHERE r.id = %s AND r.deleted_at IS NULL
            """,
            (receipt_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_receipts_by_domain_with_content(domain: str, limit: int = 10) -> list:
    """
    Get receipts for a domain with full email content.
    Useful for developing vendor parsers.
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT
                    r.id, r.message_id, r.subject, r.merchant_name, r.merchant_domain,
                    r.total_amount, r.line_items, r.parse_method, r.parsing_status,
                    e.body_html,
                    e.body_text
                FROM gmail_receipts r
                LEFT JOIN gmail_email_content e ON r.message_id = e.message_id
                WHERE r.merchant_domain LIKE %s AND r.deleted_at IS NULL
                ORDER BY r.received_at DESC
                LIMIT %s
            """,
            (f"%{domain}%", limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_gmail_receipts(
    connection_id: int, limit: int = 50, offset: int = 0, status: str = None
) -> list:
    """Get Gmail receipts for a connection."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        query = """
                SELECT id, connection_id, message_id, sender_email, sender_name,
                       subject, received_at, merchant_name, order_id, total_amount,
                       currency_code, receipt_date, line_items, parse_method,
                       parse_confidence, parsing_status, created_at
                FROM gmail_receipts
                WHERE connection_id = %s AND deleted_at IS NULL
            """
        params = [connection_id]

        if status:
            query += " AND parsing_status = %s"
            params.append(status)

        query += " ORDER BY received_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_gmail_receipt_by_id(receipt_id: int) -> dict:
    """Get a single Gmail receipt by ID with transaction match details."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    r.*,
                    c.user_id,
                    c.email_address,
                    gtm.id as match_id,
                    gtm.match_confidence,
                    t.id as transaction_id,
                    t.description as transaction_description,
                    t.amount as transaction_amount
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                LEFT JOIN gmail_transaction_matches gtm ON r.id = gtm.gmail_receipt_id
                LEFT JOIN truelayer_transactions t ON gtm.truelayer_transaction_id = t.id
                WHERE r.id = %s AND r.deleted_at IS NULL
            """,
                (receipt_id,),
            )
            result = cursor.fetchone()
            if not result:
                return None

            receipt = dict(result)

            # Ensure line_items is always a list
            if isinstance(receipt.get("line_items"), str):
                import json

                try:
                    receipt["line_items"] = json.loads(receipt["line_items"])
                except Exception:  # Fixed: was bare except
                    receipt["line_items"] = []

            if receipt.get("line_items") is None:
                receipt["line_items"] = []

            return receipt


def get_gmail_receipt_by_message_id(message_id: str) -> dict:
    """Get a Gmail receipt by its Gmail message ID (for deduplication)."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, message_id, parsing_status
                FROM gmail_receipts
                WHERE message_id = %s AND deleted_at IS NULL
            """,
            (message_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_unmatched_gmail_receipts(user_id: int, limit: int = 100) -> list:
    """Get receipts not yet matched to transactions."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT r.*
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                LEFT JOIN gmail_transaction_matches m ON r.id = m.gmail_receipt_id
                WHERE c.user_id = %s
                  AND r.parsing_status = 'parsed'
                  AND r.deleted_at IS NULL
                  AND m.id IS NULL
                ORDER BY r.receipt_date DESC
                LIMIT %s
            """,
            (user_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def soft_delete_gmail_receipt(receipt_id: int) -> bool:
    """Soft delete a Gmail receipt (GDPR compliance)."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_receipts
                SET deleted_at = NOW(), updated_at = NOW()
                WHERE id = %s
            """,
            (receipt_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


# Gmail Match functions
def save_gmail_match(
    truelayer_transaction_id: int,
    gmail_receipt_id: int,
    confidence: int,
    match_method: str = None,
    match_type: str = "standard",
) -> int:
    """Save a match between a TrueLayer transaction and Gmail receipt."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gmail_transaction_matches
                (truelayer_transaction_id, gmail_receipt_id, match_confidence,
                 match_method, match_type)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (truelayer_transaction_id, gmail_receipt_id) DO UPDATE
                SET match_confidence = EXCLUDED.match_confidence,
                    match_method = EXCLUDED.match_method,
                    matched_at = NOW()
                RETURNING id
            """,
                (
                    truelayer_transaction_id,
                    gmail_receipt_id,
                    confidence,
                    match_method,
                    match_type,
                ),
            )
            result = cursor.fetchone()
            conn.commit()

            # Match is now recorded in gmail_transaction_matches table
            # parsing_status remains 'parsed' - matching is an independent dimension
            if result:
                # --- Add to multi-source enrichment table ---
                # Get Gmail receipt details for enrichment source
                cursor.execute(
                    """
                    SELECT merchant_name, order_id, line_items
                    FROM gmail_receipts WHERE id = %s
                """,
                    (gmail_receipt_id,),
                )
                gmail_data = cursor.fetchone()

                if gmail_data:
                    merchant_name, order_id, line_items = gmail_data

                    # Build description from merchant + line items (if available)
                    description_parts = []
                    if merchant_name:
                        description_parts.append(merchant_name)

                    # Add line item names (more valuable than just order ID)
                    if (
                        line_items
                        and isinstance(line_items, list)
                        and len(line_items) > 0
                    ):
                        item_names = [
                            item.get("name", "")
                            for item in line_items
                            if item.get("name")
                        ]
                        if item_names:
                            description_parts.append(
                                ": " + ", ".join(item_names[:5])
                            )  # Limit to 5 items
                    elif order_id:
                        # Fallback to order ID if no line items
                        description_parts.append(f" #{order_id}")

                    description = (
                        "".join(description_parts)
                        if description_parts
                        else f"Receipt #{gmail_receipt_id}"
                    )

                    # Check if Amazon or Apple already has primary for this transaction
                    cursor.execute(
                        """
                        SELECT 1 FROM transaction_enrichment_sources
                        WHERE truelayer_transaction_id = %s
                        AND source_type IN ('amazon', 'amazon_business', 'apple')
                        AND is_primary = TRUE
                        LIMIT 1
                    """,
                        (truelayer_transaction_id,),
                    )
                    has_higher_priority = cursor.fetchone() is not None

                    # Add Gmail enrichment source (primary only if no Amazon/Apple)
                    cursor.execute(
                        """
                        INSERT INTO transaction_enrichment_sources
                        (truelayer_transaction_id, source_type, source_id, description,
                         order_id, line_items, match_confidence, match_method, is_primary)
                        VALUES (%s, 'gmail', %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (truelayer_transaction_id, source_type, source_id) DO UPDATE
                        SET description = EXCLUDED.description,
                            order_id = EXCLUDED.order_id,
                            line_items = EXCLUDED.line_items,
                            match_confidence = EXCLUDED.match_confidence,
                            match_method = EXCLUDED.match_method,
                            updated_at = NOW()
                    """,
                        (
                            truelayer_transaction_id,
                            gmail_receipt_id,
                            description,
                            order_id,
                            json.dumps(line_items) if line_items else None,
                            confidence,
                            match_method,
                            not has_higher_priority,  # is_primary
                        ),
                    )
                    conn.commit()

                # Update pre_enrichment_status
                cursor.execute(
                    """
                    UPDATE truelayer_transactions
                    SET pre_enrichment_status = 'Gmail'
                    WHERE id = %s
                    AND (pre_enrichment_status IS NULL OR pre_enrichment_status = 'None')
                """,
                    (truelayer_transaction_id,),
                )
                conn.commit()

            return result[0] if result else None


def get_gmail_matches_for_transaction(transaction_id: int) -> list:
    """Get all Gmail receipt matches for a specific transaction."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT m.id as match_id, m.match_confidence, m.match_method,
                       m.user_confirmed, m.matched_at,
                       r.id as gmail_receipt_id, r.merchant_name, r.order_id,
                       r.total_amount, r.receipt_date, r.line_items,
                       r.parse_method, r.parse_confidence
                FROM gmail_transaction_matches m
                JOIN gmail_receipts r ON m.gmail_receipt_id = r.id
                WHERE m.truelayer_transaction_id = %s
                ORDER BY m.match_confidence DESC
            """,
            (transaction_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_amazon_order_for_transaction(transaction_id: int) -> dict:
    """Get Amazon order matched to a transaction."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT ao.id, ao.order_id, ao.order_date, ao.product_names,
                       ao.total_owed as total_amount, ao.website,
                       m.match_confidence
                FROM truelayer_amazon_transaction_matches m
                JOIN amazon_orders ao ON m.amazon_order_id = ao.id
                WHERE m.truelayer_transaction_id = %s
            """,
            (transaction_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def get_apple_transaction_for_match(transaction_id: int) -> dict:
    """Get Apple transaction matched to a TrueLayer transaction."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT at.id, at.order_id, at.order_date as transaction_date, at.app_names,
                       at.total_amount,
                       m.match_confidence
                FROM truelayer_apple_transaction_matches m
                JOIN apple_transactions at ON m.apple_transaction_id = at.id
                WHERE m.truelayer_transaction_id = %s
            """,
                (transaction_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None


def get_gmail_matches(user_id: int, limit: int = 50, offset: int = 0) -> list:
    """Get Gmail matches for a user with receipt and transaction details."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT m.id, m.match_confidence, m.match_method, m.match_type,
                       m.user_confirmed, m.matched_at,
                       r.id as receipt_id, r.merchant_name, r.total_amount as receipt_amount,
                       r.receipt_date, r.order_id,
                       t.id as transaction_id, t.description, t.amount as transaction_amount,
                       t.timestamp as transaction_date
                FROM gmail_transaction_matches m
                JOIN gmail_receipts r ON m.gmail_receipt_id = r.id
                JOIN truelayer_transactions t ON m.truelayer_transaction_id = t.id
                JOIN gmail_connections c ON r.connection_id = c.id
                WHERE c.user_id = %s
                ORDER BY m.matched_at DESC
                LIMIT %s OFFSET %s
            """,
                (user_id, limit, offset),
            )
            return [dict(row) for row in cursor.fetchall()]


def confirm_gmail_match(match_id: int) -> bool:
    """Mark a match as user-confirmed."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_transaction_matches
                SET user_confirmed = TRUE
                WHERE id = %s
            """,
            (match_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def delete_gmail_match(match_id: int) -> bool:
    """Delete a Gmail match."""
    with get_db() as conn, conn.cursor() as cursor:
        # Get receipt ID to update status
        cursor.execute(
            """
                SELECT gmail_receipt_id FROM gmail_transaction_matches WHERE id = %s
            """,
            (match_id,),
        )
        result = cursor.fetchone()

        cursor.execute(
            """
                DELETE FROM gmail_transaction_matches WHERE id = %s
            """,
            (match_id,),
        )
        conn.commit()

        # Reset receipt status to parsed
        if result:
            cursor.execute(
                """
                    UPDATE gmail_receipts
                    SET parsing_status = 'parsed', updated_at = NOW()
                    WHERE id = %s
                """,
                (result[0],),
            )
            conn.commit()

        return cursor.rowcount > 0


# Gmail Sync Job functions
def create_gmail_sync_job(connection_id: int, job_type: str = "full") -> int:
    """Create a new sync job."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO gmail_sync_jobs (connection_id, job_type, status)
                VALUES (%s, %s, 'queued')
                RETURNING id
            """,
            (connection_id, job_type),
        )
        result = cursor.fetchone()
        conn.commit()
        return result[0] if result else None


def update_gmail_sync_job_progress(
    job_id: int, total: int, processed: int, parsed: int, failed: int
) -> bool:
    """Update sync job progress."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_sync_jobs
                SET total_messages = %s,
                    processed_messages = %s,
                    parsed_receipts = %s,
                    failed_messages = %s,
                    status = 'running',
                    started_at = COALESCE(started_at, NOW())
                WHERE id = %s
            """,
            (total, processed, parsed, failed, job_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def update_gmail_sync_job_dates(job_id: int, from_date: str, to_date: str) -> bool:
    """Update sync job date range."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_sync_jobs
                SET sync_from_date = %s,
                    sync_to_date = %s
                WHERE id = %s
            """,
            (from_date, to_date, job_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def complete_gmail_sync_job(
    job_id: int, status: str = "completed", error: str = None
) -> bool:
    """Mark sync job as completed or failed."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_sync_jobs
                SET status = %s,
                    error_message = %s,
                    completed_at = NOW()
                WHERE id = %s
            """,
            (status, error, job_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def cleanup_stale_gmail_jobs(
    queued_timeout_minutes: int = 5, running_timeout_minutes: int = 10
) -> int:
    """
    Mark stale Gmail sync jobs as failed.

    A job is considered stale if:
    - Status is 'queued' for longer than queued_timeout_minutes
    - Status is 'running' but no progress for longer than running_timeout_minutes

    Returns the number of jobs marked as failed.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE gmail_sync_jobs
                SET status = 'failed',
                    error_message = 'Job timed out - no progress detected',
                    completed_at = NOW()
                WHERE (
                    (status = 'queued' AND created_at < NOW() - INTERVAL '%s minutes')
                    OR (status = 'running' AND
                        COALESCE(started_at, created_at) < NOW() - INTERVAL '%s minutes')
                )
            """,
                (queued_timeout_minutes, running_timeout_minutes),
            )
            count = cursor.rowcount
            conn.commit()
            return count


def get_gmail_sync_job(job_id: int) -> dict:
    """Get sync job status with progress details including LLM cost."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, connection_id, status, job_type, total_messages,
                       processed_messages, parsed_receipts, failed_messages,
                       sync_from_date, sync_to_date,
                       error_message, started_at, completed_at, created_at
                FROM gmail_sync_jobs
                WHERE id = %s
            """,
            (job_id,),
        )
        result = cursor.fetchone()
        if not result:
            return None

        job = dict(result)
        # Calculate progress percentage
        total = job.get("total_messages", 0) or 0
        processed = job.get("processed_messages", 0) or 0
        job["progress_percentage"] = round(
            (processed / total * 100) if total > 0 else 0
        )

        # Get LLM cost for receipts processed during this job
        if job.get("started_at"):
            cursor.execute(
                """
                    SELECT COALESCE(SUM(llm_cost_cents), 0) as llm_cost_cents
                    FROM gmail_receipts
                    WHERE connection_id = %s
                      AND created_at >= %s
                      AND created_at <= COALESCE(%s, NOW())
                      AND llm_cost_cents IS NOT NULL
                """,
                (job["connection_id"], job["started_at"], job.get("completed_at")),
            )
            cost_result = cursor.fetchone()
            job["llm_cost_cents"] = cost_result["llm_cost_cents"] if cost_result else 0
        else:
            job["llm_cost_cents"] = 0

        return job


def get_latest_gmail_sync_job(connection_id: int) -> dict:
    """Get the latest sync job for a connection."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, connection_id, status, job_type, total_messages,
                       processed_messages, parsed_receipts, failed_messages,
                       error_message, started_at, completed_at, created_at
                FROM gmail_sync_jobs
                WHERE connection_id = %s
                ORDER BY created_at DESC
                LIMIT 1
            """,
            (connection_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_latest_active_gmail_sync_job(user_id: int) -> dict:
    """Get the latest active (queued/running) Gmail sync job for a user."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT j.id, j.connection_id, j.status, j.job_type, j.total_messages,
                       j.processed_messages, j.parsed_receipts, j.failed_messages,
                       j.sync_from_date, j.sync_to_date,
                       j.error_message, j.started_at, j.completed_at, j.created_at
                FROM gmail_sync_jobs j
                JOIN gmail_connections c ON j.connection_id = c.id
                WHERE c.user_id = %s
                  AND j.status IN ('queued', 'running')
                ORDER BY j.created_at DESC
                LIMIT 1
            """,
            (user_id,),
        )
        result = cursor.fetchone()
        if result:
            job = dict(result)
            # Calculate progress percentage
            total = job.get("total_messages", 0) or 0
            processed = job.get("processed_messages", 0) or 0
            job["progress_percentage"] = round(
                (processed / total * 100) if total > 0 else 0
            )
            return job
        return None


def get_gmail_statistics(user_id: int) -> dict:
    """Get Gmail integration statistics for a user."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(DISTINCT r.id) FILTER (WHERE r.deleted_at IS NULL) as total_receipts,
                    COUNT(DISTINCT r.id) FILTER (WHERE r.parsing_status = 'parsed' AND r.deleted_at IS NULL) as parsed_receipts,
                    COUNT(DISTINCT r.id) FILTER (WHERE r.parsing_status = 'pending' AND r.deleted_at IS NULL) as pending_receipts,
                    COUNT(DISTINCT r.id) FILTER (WHERE r.parsing_status = 'failed' AND r.deleted_at IS NULL) as failed_receipts,
                    COUNT(DISTINCT m.gmail_receipt_id) as matched_receipts,
                    MIN(r.receipt_date) as min_receipt_date,
                    MAX(r.receipt_date) as max_receipt_date,
                    SUM(r.llm_cost_cents) as total_llm_cost_cents
                FROM gmail_connections c
                LEFT JOIN gmail_receipts r ON c.id = r.connection_id
                LEFT JOIN gmail_transaction_matches m ON r.id = m.gmail_receipt_id
                WHERE c.user_id = %s AND c.connection_status = 'active'
            """,
                (user_id,),
            )
            result = cursor.fetchone()
            if result:
                return dict(result)
            return {
                "total_receipts": 0,
                "parsed_receipts": 0,
                "pending_receipts": 0,
                "failed_receipts": 0,
                "matched_receipts": 0,
                "min_receipt_date": None,
                "max_receipt_date": None,
                "total_llm_cost_cents": 0,
            }


# ============================================================================
# UNIFIED MATCHING - SOURCE COVERAGE DETECTION
# ============================================================================


def get_source_coverage_dates(user_id: int = 1) -> dict:
    """
    Get the max date coverage for each enrichment source vs bank transactions.

    Used to detect when source data is stale (bank transactions are newer
    than the last synced source data).

    Returns:
        dict with date ranges and list of stale sources needing refresh
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get max bank transaction date
        cursor.execute("""
                SELECT MAX(timestamp::date) as max_date,
                       MIN(timestamp::date) as min_date,
                       COUNT(*) as count
                FROM truelayer_transactions
            """)
        bank_result = cursor.fetchone()
        bank_max = bank_result["max_date"] if bank_result else None
        bank_min = bank_result["min_date"] if bank_result else None
        bank_count = bank_result["count"] if bank_result else 0

        # Get max Amazon order date
        cursor.execute("""
                SELECT MAX(order_date) as max_date,
                       MIN(order_date) as min_date,
                       COUNT(*) as count
                FROM amazon_orders
            """)
        amazon_result = cursor.fetchone()
        amazon_max = amazon_result["max_date"] if amazon_result else None
        amazon_min = amazon_result["min_date"] if amazon_result else None
        amazon_count = amazon_result["count"] if amazon_result else 0

        # Get max Apple transaction date
        cursor.execute("""
                SELECT MAX(order_date) as max_date,
                       MIN(order_date) as min_date,
                       COUNT(*) as count
                FROM apple_transactions
            """)
        apple_result = cursor.fetchone()
        apple_max = apple_result["max_date"] if apple_result else None
        apple_min = apple_result["min_date"] if apple_result else None
        apple_count = apple_result["count"] if apple_result else 0

        # Get max Gmail receipt date
        cursor.execute(
            """
                SELECT MAX(receipt_date) as max_date,
                       MIN(receipt_date) as min_date,
                       COUNT(*) as count
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                WHERE c.user_id = %s AND r.deleted_at IS NULL
            """,
            (user_id,),
        )
        gmail_result = cursor.fetchone()
        gmail_max = gmail_result["max_date"] if gmail_result else None
        gmail_min = gmail_result["min_date"] if gmail_result else None
        gmail_count = gmail_result["count"] if gmail_result else 0

        # Determine which sources are stale (> 7 days behind bank data)
        stale_sources = []
        stale_threshold_days = 7

        if bank_max:
            from datetime import timedelta

            threshold_date = bank_max - timedelta(days=stale_threshold_days)

            if amazon_count > 0 and amazon_max and amazon_max < threshold_date:
                stale_sources.append("amazon")
            if apple_count > 0 and apple_max and apple_max < threshold_date:
                stale_sources.append("apple")
            if gmail_count > 0 and gmail_max and gmail_max < threshold_date:
                stale_sources.append("gmail")

        # Convert dates to strings for JSON serialization
        def date_to_str(d):
            return d.isoformat() if d else None

        return {
            "bank_transactions": {
                "max_date": date_to_str(bank_max),
                "min_date": date_to_str(bank_min),
                "count": bank_count,
            },
            "amazon": {
                "max_date": date_to_str(amazon_max),
                "min_date": date_to_str(amazon_min),
                "count": amazon_count,
                "is_stale": "amazon" in stale_sources,
            },
            "apple": {
                "max_date": date_to_str(apple_max),
                "min_date": date_to_str(apple_min),
                "count": apple_count,
                "is_stale": "apple" in stale_sources,
            },
            "gmail": {
                "max_date": date_to_str(gmail_max),
                "min_date": date_to_str(gmail_min),
                "count": gmail_count,
                "is_stale": "gmail" in stale_sources,
            },
            "stale_sources": stale_sources,
            "stale_threshold_days": stale_threshold_days,
        }


def get_gmail_sender_pattern(sender_domain: str) -> dict:
    """Get sender-specific parsing pattern."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT merchant_name, normalized_name, parse_type, pattern_config,
                       date_tolerance_days
                FROM gmail_sender_patterns
                WHERE sender_domain = %s AND is_active = TRUE
            """,
            (sender_domain,),
        )
        result = cursor.fetchone()

        # Update usage count if found
        if result:
            cursor.execute(
                """
                    UPDATE gmail_sender_patterns
                    SET usage_count = usage_count + 1,
                        last_used_at = NOW()
                    WHERE sender_domain = %s
                """,
                (sender_domain,),
            )
            conn.commit()

        return dict(result) if result else None


def update_gmail_receipt_parsed(
    receipt_id: int,
    merchant_name: str,
    merchant_name_normalized: str,
    order_id: str,
    total_amount: float,
    currency_code: str,
    receipt_date: str,
    line_items: list,
    receipt_hash: str,
    parse_method: str,
    parse_confidence: int,
    parsing_status: str = "parsed",
    llm_cost_cents: int = None,
) -> bool:
    """Update receipt with parsed data."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_receipts
                SET merchant_name = %s,
                    merchant_name_normalized = %s,
                    order_id = %s,
                    total_amount = %s,
                    currency_code = %s,
                    receipt_date = %s,
                    line_items = %s,
                    receipt_hash = %s,
                    parse_method = %s,
                    parse_confidence = %s,
                    parsing_status = %s,
                    llm_cost_cents = COALESCE(%s, llm_cost_cents),
                    updated_at = NOW()
                WHERE id = %s
            """,
            (
                merchant_name,
                merchant_name_normalized,
                order_id,
                total_amount,
                currency_code,
                receipt_date,
                json.dumps(line_items) if line_items else None,
                receipt_hash,
                parse_method,
                parse_confidence,
                parsing_status,
                llm_cost_cents,
                receipt_id,
            ),
        )
        conn.commit()
        return cursor.rowcount > 0


def update_gmail_receipt_status(
    receipt_id: int, parsing_status: str, parsing_error: str = None
) -> bool:
    """Update receipt parsing status."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_receipts
                SET parsing_status = %s,
                    parsing_error = %s,
                    retry_count = retry_count + 1,
                    updated_at = NOW()
                WHERE id = %s
            """,
            (parsing_status, parsing_error, receipt_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def update_gmail_receipt_pdf_status(
    receipt_id: int, pdf_status: str, error: str = None
) -> bool:
    """
    Update PDF processing status for a Gmail receipt.

    Args:
        receipt_id: Receipt ID
        pdf_status: Status ('none', 'pending', 'processing', 'completed', 'failed')
        error: Error message if failed (optional)

    Returns:
        bool: True if update succeeded
    """
    with get_db() as conn, conn.cursor() as cursor:
        if error:
            cursor.execute(
                """
                    UPDATE gmail_receipts
                    SET pdf_processing_status = %s,
                        pdf_retry_count = pdf_retry_count + 1,
                        pdf_last_error = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """,
                (pdf_status, error, receipt_id),
            )
        else:
            cursor.execute(
                """
                    UPDATE gmail_receipts
                    SET pdf_processing_status = %s,
                        updated_at = NOW()
                    WHERE id = %s
                """,
                (pdf_status, receipt_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def update_gmail_receipt_from_pdf(
    receipt_id: int, pdf_data: dict, minio_object_key: str = None
) -> bool:
    """
    Update receipt with data parsed from PDF.

    Args:
        receipt_id: Receipt ID
        pdf_data: Parsed data from PDF (merchant_name, total_amount, etc.)
        minio_object_key: MinIO object key for the stored PDF (optional)

    Returns:
        bool: True if update succeeded
    """
    with get_db() as conn, conn.cursor() as cursor:
        # Build UPDATE statement dynamically based on available PDF data
        updates = []
        params = []

        if "merchant_name" in pdf_data and pdf_data["merchant_name"]:
            updates.append("merchant_name = %s")
            params.append(pdf_data["merchant_name"])
            # Also set normalized name
            updates.append("merchant_name_normalized = LOWER(%s)")
            params.append(pdf_data["merchant_name"])

        if "total_amount" in pdf_data and pdf_data["total_amount"] is not None:
            updates.append("total_amount = %s")
            params.append(float(pdf_data["total_amount"]))

        if "currency_code" in pdf_data and pdf_data["currency_code"]:
            updates.append("currency_code = %s")
            params.append(pdf_data["currency_code"])

        if "receipt_date" in pdf_data and pdf_data["receipt_date"]:
            updates.append("receipt_date = %s")
            params.append(pdf_data["receipt_date"])

        if "order_id" in pdf_data and pdf_data["order_id"]:
            updates.append("order_id = %s")
            params.append(pdf_data["order_id"])

        if "line_items" in pdf_data and pdf_data["line_items"]:
            import json

            updates.append("line_items = %s::jsonb")
            params.append(json.dumps(pdf_data["line_items"]))

        if "parse_method" in pdf_data and pdf_data["parse_method"]:
            updates.append("parse_method = %s")
            params.append(pdf_data["parse_method"])

        if "parse_confidence" in pdf_data and pdf_data["parse_confidence"] is not None:
            updates.append("parse_confidence = %s")
            params.append(int(pdf_data["parse_confidence"]))

        # Always update parsing status to 'parsed' if we got data
        updates.append("parsing_status = %s")
        params.append("parsed")

        # Always update timestamp
        updates.append("updated_at = NOW()")

        # Add receipt_id for WHERE clause
        params.append(receipt_id)

        if updates:
            query = f"""
                    UPDATE gmail_receipts
                    SET {", ".join(updates)}
                    WHERE id = %s
                """
            cursor.execute(query, params)
            conn.commit()
            return cursor.rowcount > 0

        return False


def get_pending_gmail_receipts(connection_id: int, limit: int = 100) -> list:
    """Get receipts pending parsing."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, message_id, sender_email, sender_name, subject,
                       received_at, merchant_domain, raw_schema_data
                FROM gmail_receipts
                WHERE connection_id = %s
                  AND parsing_status = 'pending'
                  AND deleted_at IS NULL
                  AND retry_count < 3
                ORDER BY received_at DESC
                LIMIT %s
            """,
            (connection_id, limit),
        )
        return [dict(row) for row in cursor.fetchall()]


def get_gmail_merchant_alias(merchant_name: str) -> dict:
    """Get merchant alias mapping for matching."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT bank_name, receipt_name, normalized_name
                FROM gmail_merchant_aliases
                WHERE LOWER(receipt_name) = LOWER(%s)
                   OR LOWER(normalized_name) = LOWER(%s)
                   AND is_active = TRUE
                LIMIT 1
            """,
            (merchant_name, merchant_name),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def delete_old_unmatched_gmail_receipts(cutoff_date) -> int:
    """
    Delete old Gmail receipts that are:
    - Older than cutoff_date
    - Not matched to any transaction
    - Have parsing_status of 'unparseable'

    Returns count of deleted receipts.
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                DELETE FROM gmail_receipts
                WHERE id IN (
                    SELECT r.id FROM gmail_receipts r
                    LEFT JOIN gmail_transaction_matches m ON r.id = m.gmail_receipt_id
                    WHERE r.created_at < %s
                      AND m.id IS NULL
                      AND r.parsing_status = 'unparseable'
                      AND r.is_deleted = FALSE
                )
            """,
            (cutoff_date,),
        )
        deleted = cursor.rowcount
        conn.commit()
        return deleted


# ============================================================================
# GMAIL LLM QUEUE FUNCTIONS
# ============================================================================


def get_unparseable_receipts_for_llm_queue(
    connection_id: int = None, limit: int = 100
) -> list:
    """
    Get unparseable Gmail receipts that can be queued for LLM parsing.

    Args:
        connection_id: Optional filter by connection
        limit: Maximum receipts to return

    Returns:
        List of receipt dicts with id, message_id, subject, sender, received_at, snippet
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        query = """
                SELECT
                    r.id,
                    r.message_id,
                    r.subject,
                    r.sender_email,
                    r.sender_name,
                    r.merchant_domain,
                    r.received_at,
                    r.raw_schema_data->>'snippet' as snippet,
                    r.parsing_error,
                    r.llm_parse_status,
                    r.llm_estimated_cost_cents,
                    r.llm_actual_cost_cents,
                    c.id as connection_id
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                WHERE r.parsing_status = 'unparseable'
                  AND r.deleted_at IS NULL
                  AND (r.llm_parse_status IS NULL OR r.llm_parse_status = 'failed')
            """
        params = []

        if connection_id:
            query += " AND r.connection_id = %s"
            params.append(connection_id)

        query += " ORDER BY r.received_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_llm_queue_summary(connection_id: int = None) -> dict:
    """
    Get summary statistics for the LLM parsing queue.

    Returns:
        Dict with count, total_estimated_cost_cents
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """
                SELECT
                    COUNT(*) as total_count,
                    COUNT(*) FILTER (WHERE llm_parse_status IS NULL) as available_count,
                    COUNT(*) FILTER (WHERE llm_parse_status = 'pending') as pending_count,
                    COUNT(*) FILTER (WHERE llm_parse_status = 'processing') as processing_count,
                    COUNT(*) FILTER (WHERE llm_parse_status = 'completed') as completed_count,
                    COUNT(*) FILTER (WHERE llm_parse_status = 'failed') as failed_count,
                    COALESCE(SUM(llm_estimated_cost_cents), 0) as total_estimated_cost_cents,
                    COALESCE(SUM(llm_actual_cost_cents), 0) as total_actual_cost_cents
                FROM gmail_receipts
                WHERE parsing_status = 'unparseable'
                  AND deleted_at IS NULL
            """
            params = []

            if connection_id:
                query = query.replace("WHERE", "WHERE connection_id = %s AND")
                params.append(connection_id)

            cursor.execute(query, params)
            row = cursor.fetchone()
            return (
                dict(row)
                if row
                else {
                    "total_count": 0,
                    "available_count": 0,
                    "pending_count": 0,
                    "processing_count": 0,
                    "completed_count": 0,
                    "failed_count": 0,
                    "total_estimated_cost_cents": 0,
                    "total_actual_cost_cents": 0,
                }
            )


def update_receipt_llm_status(
    receipt_id: int,
    status: str,
    estimated_cost: int = None,
    actual_cost: int = None,
    parsed_data: dict = None,
) -> bool:
    """
    Update LLM parsing status and costs for a receipt.

    Args:
        receipt_id: Receipt ID
        status: 'pending', 'processing', 'completed', or 'failed'
        estimated_cost: Estimated cost in cents
        actual_cost: Actual cost in cents (after processing)
        parsed_data: Optional parsed data to update receipt with

    Returns:
        True if updated successfully
    """
    with get_db() as conn, conn.cursor() as cursor:
        updates = ["llm_parse_status = %s"]
        params = [status]

        if estimated_cost is not None:
            updates.append("llm_estimated_cost_cents = %s")
            params.append(estimated_cost)

        if actual_cost is not None:
            updates.append("llm_actual_cost_cents = %s")
            params.append(actual_cost)

        if status == "completed":
            updates.append("llm_parsed_at = NOW()")

            # Update parsed data if provided
            if parsed_data:
                if parsed_data.get("merchant_name"):
                    updates.append("merchant_name = %s")
                    params.append(parsed_data["merchant_name"])
                if parsed_data.get("merchant_name_normalized"):
                    updates.append("merchant_name_normalized = %s")
                    params.append(parsed_data["merchant_name_normalized"])
                if parsed_data.get("total_amount"):
                    updates.append("total_amount = %s")
                    params.append(parsed_data["total_amount"])
                if parsed_data.get("currency_code"):
                    updates.append("currency_code = %s")
                    params.append(parsed_data["currency_code"])
                if parsed_data.get("order_id"):
                    updates.append("order_id = %s")
                    params.append(parsed_data["order_id"])
                if parsed_data.get("receipt_date"):
                    updates.append("receipt_date = %s")
                    params.append(parsed_data["receipt_date"])
                if parsed_data.get("line_items"):
                    updates.append("line_items = %s")
                    params.append(json.dumps(parsed_data["line_items"]))

                # Update parsing status to parsed
                updates.append("parsing_status = %s")
                params.append("parsed")
                updates.append("parse_method = %s")
                params.append(parsed_data.get("parse_method", "llm"))
                updates.append("parse_confidence = %s")
                params.append(parsed_data.get("parse_confidence", 70))

        params.append(receipt_id)

        cursor.execute(
            f"UPDATE gmail_receipts SET {', '.join(updates)} WHERE id = %s", params
        )
        conn.commit()
        return cursor.rowcount > 0


def get_receipt_for_llm_processing(receipt_id: int) -> dict:
    """
    Get receipt details needed for LLM processing.

    Returns:
        Dict with receipt info including message_id for re-fetching from Gmail
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT
                    r.id,
                    r.message_id,
                    r.subject,
                    r.sender_email,
                    r.merchant_domain,
                    r.connection_id as gmail_connection_id,
                    c.email_address as connection_email
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                WHERE r.id = %s
            """,
            (receipt_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None


# ============================================================================
# GMAIL MERCHANTS AGGREGATION
# ============================================================================


def get_gmail_merchants_summary(user_id: int = 1) -> dict:
    """
    Aggregate Gmail receipts by normalized merchant name with parsing/matching statistics.

    Groups by merchant_name_normalized to show separate entries for variants
    like Amazon, Amazon Business, Amazon Fresh (all share amazon.co.uk domain).

    Returns dict with:
        - merchants: List of merchant summaries
        - summary: Overall statistics
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Main aggregation query: receipts grouped by merchant_name_normalized
            # This ensures Amazon, Amazon Business, Amazon Fresh appear as separate rows
            cursor.execute(
                """
                WITH receipt_stats AS (
                    SELECT
                        COALESCE(r.merchant_name_normalized,
                            LOWER(SPLIT_PART(COALESCE(r.merchant_domain,
                                SUBSTRING(r.sender_email FROM '@(.+)$')), '.', 1))) as normalized_name,
                        COALESCE(r.merchant_domain,
                            SUBSTRING(r.sender_email FROM '@(.+)$')) as domain,
                        COALESCE(r.merchant_name, r.sender_name,
                            SUBSTRING(r.sender_email FROM '@(.+)$')) as display_name,
                        COUNT(*) as receipt_count,
                        COUNT(*) FILTER (WHERE r.parsing_status = 'parsed') as parsed_count,
                        COUNT(DISTINCT m.id) as matched_count,
                        COUNT(*) FILTER (WHERE r.parsing_status = 'pending') as pending_count,
                        COUNT(*) FILTER (WHERE r.parsing_status IN ('failed', 'unparseable')) as failed_count,
                        MIN(r.received_at) as earliest_receipt,
                        MAX(r.received_at) as latest_receipt,
                        SUM(COALESCE(r.llm_cost_cents, 0)) as llm_cost_cents,
                        -- Sum of receipt amounts (for totals display)
                        SUM(COALESCE(r.total_amount, 0)) as total_amount,
                        -- Track parse methods used
                        COUNT(*) FILTER (WHERE r.parse_method LIKE 'vendor_%%') as vendor_parsed_count,
                        COUNT(*) FILTER (WHERE r.parse_method = 'schema_org') as schema_parsed_count,
                        COUNT(*) FILTER (WHERE r.parse_method = 'pattern') as pattern_parsed_count,
                        COUNT(*) FILTER (WHERE r.parse_method = 'llm') as llm_parsed_count
                    FROM gmail_receipts r
                    LEFT JOIN gmail_transaction_matches m ON r.id = m.gmail_receipt_id
                    JOIN gmail_connections c ON r.connection_id = c.id
                    WHERE c.user_id = %s
                      AND c.connection_status = 'active'
                      AND r.deleted_at IS NULL
                    GROUP BY
                        COALESCE(r.merchant_name_normalized,
                            LOWER(SPLIT_PART(COALESCE(r.merchant_domain,
                                SUBSTRING(r.sender_email FROM '@(.+)$')), '.', 1))),
                        COALESCE(r.merchant_domain, SUBSTRING(r.sender_email FROM '@(.+)$')),
                        COALESCE(r.merchant_name, r.sender_name, SUBSTRING(r.sender_email FROM '@(.+)$'))
                ),
                template_info AS (
                    SELECT
                        LOWER(sender_domain) as domain,
                        merchant_name,
                        parse_type,
                        is_active
                    FROM gmail_sender_patterns
                    WHERE is_active = TRUE
                )
                SELECT
                    rs.normalized_name as merchant_normalized,
                    rs.domain as merchant_domain,
                    rs.display_name as merchant_name,
                    rs.receipt_count,
                    rs.parsed_count,
                    rs.matched_count,
                    rs.pending_count,
                    rs.failed_count,
                    rs.earliest_receipt,
                    rs.latest_receipt,
                    rs.llm_cost_cents,
                    rs.total_amount,
                    COALESCE(ti.parse_type, 'none') as template_type,
                    ti.is_active IS NOT NULL as has_template,
                    rs.vendor_parsed_count > 0 as has_vendor_parser,
                    rs.schema_parsed_count,
                    rs.pattern_parsed_count,
                    rs.llm_parsed_count
                FROM receipt_stats rs
                LEFT JOIN template_info ti ON LOWER(ti.domain) = LOWER(rs.domain)
                ORDER BY rs.receipt_count DESC
            """,
                (user_id,),
            )

            merchants_raw = [dict(row) for row in cursor.fetchall()]

            # For each merchant, find potential transaction matches
            # and alternative source coverage
            merchants = []
            for m in merchants_raw:
                normalized = m.get("merchant_normalized")
                domain = m.get("merchant_domain")
                if not normalized and not domain:
                    continue

                # Use normalized name for matching (e.g., 'amazon', 'amazon_business', 'amazon_fresh')
                # This is more accurate than extracting domain prefix
                match_term = normalized or (
                    domain.split(".")[0].lower() if domain else ""
                )

                # Count potential matches: unmatched DEBIT transactions with similar merchant
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM truelayer_transactions t
                    JOIN truelayer_accounts a ON t.account_id = a.id
                    JOIN bank_connections c ON a.connection_id = c.id
                    LEFT JOIN gmail_transaction_matches gm ON gm.truelayer_transaction_id = t.id
                    WHERE c.user_id = %s
                      AND t.transaction_type = 'DEBIT'
                      AND gm.id IS NULL
                      AND (
                          LOWER(t.merchant_name) LIKE %s
                          OR LOWER(t.description) LIKE %s
                      )
                """,
                    (user_id, f"%{match_term}%", f"%{match_term}%"),
                )
                potential_result = cursor.fetchone()
                m["potential_transaction_matches"] = (
                    potential_result["count"] if potential_result else 0
                )

                # Count alternative source coverage (Amazon variants and Apple)
                cursor.execute(
                    """
                    SELECT
                        source_type,
                        COUNT(*) as count
                    FROM transaction_enrichment_sources tes
                    JOIN truelayer_transactions t ON tes.truelayer_transaction_id = t.id
                    JOIN truelayer_accounts a ON t.account_id = a.id
                    JOIN bank_connections c ON a.connection_id = c.id
                    WHERE c.user_id = %s
                      AND tes.source_type IN ('amazon', 'amazon_business', 'amazon_fresh', 'apple')
                      AND (
                          LOWER(t.merchant_name) LIKE %s
                          OR LOWER(t.description) LIKE %s
                      )
                    GROUP BY tes.source_type
                """,
                    (user_id, f"%{match_term}%", f"%{match_term}%"),
                )
                alt_sources = {
                    row["source_type"]: row["count"] for row in cursor.fetchall()
                }
                m["amazon_coverage"] = alt_sources.get("amazon", 0)
                m["amazon_business_coverage"] = alt_sources.get("amazon_business", 0)
                m["amazon_fresh_coverage"] = alt_sources.get("amazon_fresh", 0)
                m["apple_coverage"] = alt_sources.get("apple", 0)

                # Convert timestamps to ISO strings
                if m["earliest_receipt"]:
                    m["earliest_receipt"] = m["earliest_receipt"].isoformat()
                if m["latest_receipt"]:
                    m["latest_receipt"] = m["latest_receipt"].isoformat()

                merchants.append(m)

            # Calculate summary statistics
            summary = {
                "total_merchants": len(merchants),
                "with_template": sum(1 for m in merchants if m["has_template"]),
                "without_template": sum(1 for m in merchants if not m["has_template"]),
                "with_vendor_parser": sum(
                    1 for m in merchants if m["has_vendor_parser"]
                ),
                "total_receipts": sum(m["receipt_count"] for m in merchants),
                "total_parsed": sum(m["parsed_count"] for m in merchants),
                "total_matched": sum(m["matched_count"] for m in merchants),
                "total_pending": sum(m["pending_count"] for m in merchants),
                "total_failed": sum(m["failed_count"] for m in merchants),
                "total_llm_cost_cents": sum(
                    m["llm_cost_cents"] or 0 for m in merchants
                ),
                "total_potential_matches": sum(
                    m["potential_transaction_matches"] for m in merchants
                ),
                "total_amount": sum(float(m["total_amount"] or 0) for m in merchants),
            }

            return {"merchants": merchants, "summary": summary}


def get_receipts_by_domain(
    merchant_domain: str = None,
    merchant_normalized: str = None,
    user_id: int = 1,
    limit: int = 50,
    offset: int = 0,
    status: str = None,
) -> dict:
    """
    Get all receipts for a specific merchant by domain or normalized name.

    Args:
        merchant_domain: The sender domain to filter by (e.g., 'amazon.co.uk')
        merchant_normalized: The normalized merchant name (e.g., 'amazon_business')
        user_id: User ID
        limit: Max receipts to return
        offset: Pagination offset
        status: Optional filter by parsing_status

    Note: If both merchant_domain and merchant_normalized are provided,
          merchant_normalized takes precedence.

    Returns:
        dict with receipts list and total count
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Build query with optional status filter
            query = """
                SELECT
                    r.id,
                    r.message_id,
                    r.sender_email,
                    r.sender_name,
                    r.subject,
                    r.received_at,
                    r.merchant_name,
                    r.merchant_name_normalized,
                    r.merchant_domain,
                    r.order_id,
                    r.total_amount,
                    r.currency_code,
                    r.receipt_date,
                    r.line_items,
                    r.parse_method,
                    r.parse_confidence,
                    r.parsing_status,
                    r.parsing_error,
                    r.llm_cost_cents,
                    gm.id as match_id,
                    gm.match_confidence,
                    t.id as transaction_id,
                    t.description as transaction_description,
                    t.amount as transaction_amount
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                LEFT JOIN gmail_transaction_matches gm ON r.id = gm.gmail_receipt_id
                LEFT JOIN truelayer_transactions t ON gm.truelayer_transaction_id = t.id
                WHERE c.user_id = %s
                  AND c.connection_status = 'active'
                  AND r.deleted_at IS NULL
            """
            params = [user_id]

            # Filter by normalized name (preferred) or domain
            # Use same COALESCE logic as summary query to match computed normalized names
            if merchant_normalized:
                query += """
                  AND LOWER(COALESCE(r.merchant_name_normalized,
                      LOWER(SPLIT_PART(COALESCE(r.merchant_domain,
                          SUBSTRING(r.sender_email FROM '@(.+)$')), '.', 1)))) = LOWER(%s)
                """
                params.append(merchant_normalized)
                identifier = merchant_normalized
            elif merchant_domain:
                query += """
                  AND (
                      LOWER(r.merchant_domain) = LOWER(%s)
                      OR LOWER(SUBSTRING(r.sender_email FROM '@(.+)$')) = LOWER(%s)
                  )
                """
                params.extend([merchant_domain, merchant_domain])
                identifier = merchant_domain
            else:
                return {"receipts": [], "total": 0, "identifier": None}

            if status:
                query += " AND r.parsing_status = %s"
                params.append(status)

            # Get total count
            count_query = f"""
                SELECT COUNT(*) as total
                FROM ({query}) sub
            """
            cursor.execute(count_query, params)
            total = cursor.fetchone()["total"]

            # Get paginated results
            query += " ORDER BY r.received_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])

            cursor.execute(query, params)
            receipts = []
            for row in cursor.fetchall():
                receipt = dict(row)
                # Convert timestamps
                if receipt["received_at"]:
                    receipt["received_at"] = receipt["received_at"].isoformat()
                if receipt["receipt_date"]:
                    receipt["receipt_date"] = (
                        receipt["receipt_date"].isoformat()
                        if hasattr(receipt["receipt_date"], "isoformat")
                        else str(receipt["receipt_date"])
                    )

                # CRITICAL: Ensure line_items is always a list for frontend
                # (psycopg2 with RealDictCursor returns JSONB as dict/list automatically,
                # but add safety checks for edge cases)
                if isinstance(receipt.get("line_items"), str):
                    import json

                    try:
                        receipt["line_items"] = json.loads(receipt["line_items"])
                    except Exception:  # Fixed: was bare except
                        receipt["line_items"] = []

                # Ensure line_items is never None
                if receipt.get("line_items") is None:
                    receipt["line_items"] = []

                receipts.append(receipt)

            return {
                "receipts": receipts,
                "total": total,
                "identifier": identifier,
                "merchant_normalized": merchant_normalized,
                "merchant_domain": merchant_domain,
            }


def get_gmail_sender_patterns_list(include_usage: bool = True) -> list:
    """
    Get all registered sender patterns (templates).

    Returns list of pattern configurations with optional usage stats.
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
                SELECT
                    id,
                    sender_domain,
                    sender_pattern,
                    merchant_name,
                    normalized_name,
                    parse_type,
                    pattern_config,
                    date_tolerance_days,
                    is_active,
                    usage_count,
                    last_used_at,
                    created_at
                FROM gmail_sender_patterns
                ORDER BY usage_count DESC, merchant_name ASC
            """)

        patterns = []
        for row in cursor.fetchall():
            pattern = dict(row)
            if pattern["last_used_at"]:
                pattern["last_used_at"] = pattern["last_used_at"].isoformat()
            if pattern["created_at"]:
                pattern["created_at"] = pattern["created_at"].isoformat()
            patterns.append(pattern)

        return patterns


def get_transactions_for_matching(
    user_id: int, from_date=None, to_date=None, limit: int = 1000
) -> list:
    """Get TrueLayer transactions for matching with receipts."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        query = """
                SELECT t.id, t.transaction_id, t.amount, t.currency,
                       t.description, t.merchant_name, t.timestamp as date,
                       a.display_name as account_name
                FROM truelayer_transactions t
                JOIN truelayer_accounts a ON t.account_id = a.id
                JOIN bank_connections c ON a.connection_id = c.id
                WHERE c.user_id = %s
                  AND t.transaction_type = 'DEBIT'
            """
        params = [user_id]

        if from_date:
            query += " AND t.timestamp >= %s"
            params.append(from_date)

        if to_date:
            query += " AND t.timestamp <= %s"
            params.append(to_date)

        query += " ORDER BY t.timestamp DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# MATCHING JOBS FUNCTIONS
# ============================================================================


def create_matching_job(user_id: int, job_type: str, celery_task_id: str = None) -> int:
    """
    Create a new matching job entry.

    Args:
        user_id: User ID
        job_type: Type of matching job ('amazon', 'apple', 'returns')
        celery_task_id: Optional Celery task ID

    Returns:
        Job ID
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO matching_jobs (user_id, job_type, celery_task_id, status)
                VALUES (%s, %s, %s, 'queued')
                RETURNING id
            """,
            (user_id, job_type, celery_task_id),
        )
        job_id = cursor.fetchone()[0]
        conn.commit()
        return job_id


def update_matching_job_status(
    job_id: int, status: str, error_message: str = None
) -> bool:
    """
    Update matching job status.

    Args:
        job_id: Job ID
        status: New status ('queued', 'running', 'completed', 'failed')
        error_message: Optional error message for failed jobs

    Returns:
        True if updated successfully
    """
    with get_db() as conn, conn.cursor() as cursor:
        if status == "running":
            cursor.execute(
                """
                    UPDATE matching_jobs
                    SET status = %s, started_at = NOW()
                    WHERE id = %s
                """,
                (status, job_id),
            )
        elif status in ("completed", "failed"):
            cursor.execute(
                """
                    UPDATE matching_jobs
                    SET status = %s, completed_at = NOW(), error_message = %s
                    WHERE id = %s
                """,
                (status, error_message, job_id),
            )
        else:
            cursor.execute(
                """
                    UPDATE matching_jobs
                    SET status = %s
                    WHERE id = %s
                """,
                (status, job_id),
            )
        conn.commit()
        return cursor.rowcount > 0


def update_matching_job_progress(
    job_id: int,
    total_items: int = None,
    processed_items: int = None,
    matched_items: int = None,
    failed_items: int = None,
) -> bool:
    """
    Update matching job progress counters.

    Args:
        job_id: Job ID
        total_items: Total items to process
        processed_items: Items processed so far
        matched_items: Items successfully matched
        failed_items: Items that failed

    Returns:
        True if updated successfully
    """
    with get_db() as conn, conn.cursor() as cursor:
        updates = []
        params = []

        if total_items is not None:
            updates.append("total_items = %s")
            params.append(total_items)
        if processed_items is not None:
            updates.append("processed_items = %s")
            params.append(processed_items)
        if matched_items is not None:
            updates.append("matched_items = %s")
            params.append(matched_items)
        if failed_items is not None:
            updates.append("failed_items = %s")
            params.append(failed_items)

        if not updates:
            return False

        params.append(job_id)
        cursor.execute(
            f"""
                UPDATE matching_jobs
                SET {", ".join(updates)}
                WHERE id = %s
            """,
            params,
        )
        conn.commit()
        return cursor.rowcount > 0


def get_matching_job(job_id: int) -> dict:
    """
    Get matching job by ID.

    Args:
        job_id: Job ID

    Returns:
        Job dictionary or None
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, user_id, job_type, celery_task_id, status,
                       total_items, processed_items, matched_items, failed_items,
                       error_message, started_at, completed_at, created_at
                FROM matching_jobs
                WHERE id = %s
            """,
            (job_id,),
        )
        result = cursor.fetchone()
        if result:
            job = dict(result)
            # Calculate progress percentage
            total = job.get("total_items", 0) or 0
            processed = job.get("processed_items", 0) or 0
            job["progress_percentage"] = round(
                (processed / total * 100) if total > 0 else 0
            )
            return job
        return None


def get_active_matching_jobs(user_id: int) -> list:
    """
    Get all active (queued/running) matching jobs for a user.

    Args:
        user_id: User ID

    Returns:
        List of active job dictionaries
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, user_id, job_type, celery_task_id, status,
                       total_items, processed_items, matched_items, failed_items,
                       error_message, started_at, completed_at, created_at
                FROM matching_jobs
                WHERE user_id = %s AND status IN ('queued', 'running')
                ORDER BY created_at DESC
            """,
            (user_id,),
        )
        jobs = []
        for row in cursor.fetchall():
            job = dict(row)
            total = job.get("total_items", 0) or 0
            processed = job.get("processed_items", 0) or 0
            job["progress_percentage"] = round(
                (processed / total * 100) if total > 0 else 0
            )
            jobs.append(job)
        return jobs


def cleanup_stale_matching_jobs(stale_threshold_minutes: int = 30) -> dict:
    """
    Mark stale matching jobs as failed.

    A job is considered stale if:
    - status='queued' and created_at > threshold (task never started)
    - status='running' and started_at > threshold (task hung)

    Args:
        stale_threshold_minutes: Minutes after which a job is considered stale

    Returns:
        {'cleaned_up': count, 'job_ids': [...]}
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Find stale jobs
            cursor.execute(
                """
                SELECT id, job_type, status, created_at, started_at
                FROM matching_jobs
                WHERE status IN ('queued', 'running')
                  AND (
                    (status = 'queued' AND created_at < NOW() - INTERVAL '%s minutes')
                    OR
                    (status = 'running' AND started_at < NOW() - INTERVAL '%s minutes')
                  )
            """,
                (stale_threshold_minutes, stale_threshold_minutes),
            )
            stale_jobs = cursor.fetchall()

            if not stale_jobs:
                return {"cleaned_up": 0, "job_ids": []}

            job_ids = [job["id"] for job in stale_jobs]

            # Mark as failed
            cursor.execute(
                """
                UPDATE matching_jobs
                SET status = 'failed',
                    error_message = 'Job stalled - automatically cleaned up after timeout',
                    completed_at = NOW()
                WHERE id = ANY(%s)
            """,
                (job_ids,),
            )
            conn.commit()

            return {"cleaned_up": len(job_ids), "job_ids": job_ids}


# ============================================================================
# DIRECT DEBIT MAPPING FUNCTIONS
# ============================================================================


def get_direct_debit_payees() -> list:
    """
    Extract unique payees from DIRECT DEBIT transactions.

    Uses the pattern extractor to parse payee names from transaction descriptions.
    Groups by payee and includes transaction counts and current enrichment status.

    Returns:
        List of payee dictionaries with:
        - payee: Extracted payee name
        - transaction_count: Number of transactions
        - sample_description: Example transaction description
        - current_category: Most common category for this payee
        - current_subcategory: Most common subcategory for this payee
        - mapping_id: ID of existing mapping if configured
    """
    # Import pattern extractor here to avoid circular imports
    from mcp.pattern_extractor import (
        extract_direct_debit_payee_fallback,
        extract_variables,
    )

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get all direct debit transactions
        cursor.execute("""
                SELECT id, description,
                       metadata->'enrichment'->>'primary_category' as category,
                       metadata->'enrichment'->>'subcategory' as subcategory,
                       metadata->'enrichment'->>'merchant_clean_name' as merchant
                FROM truelayer_transactions
                WHERE description LIKE 'DIRECT DEBIT PAYMENT TO%'
                ORDER BY timestamp DESC
            """)
        transactions = cursor.fetchall()

        # Group by extracted payee
        payee_data = {}
        for txn in transactions:
            extracted = extract_variables(txn["description"])
            payee = extracted.get("payee")

            # Fallback extraction if strict pattern fails
            if not payee:
                extracted = extract_direct_debit_payee_fallback(txn["description"])
                payee = extracted.get("payee")

            if payee:
                payee_upper = payee.upper().strip()
                if payee_upper not in payee_data:
                    payee_data[payee_upper] = {
                        "payee": payee.strip(),
                        "transaction_count": 0,
                        "sample_description": txn["description"],
                        "categories": {},
                        "subcategories": {},
                    }
                payee_data[payee_upper]["transaction_count"] += 1

                # Track category frequency
                cat = txn["category"] or "Uncategorized"
                payee_data[payee_upper]["categories"][cat] = (
                    payee_data[payee_upper]["categories"].get(cat, 0) + 1
                )

                subcat = txn["subcategory"] or "None"
                payee_data[payee_upper]["subcategories"][subcat] = (
                    payee_data[payee_upper]["subcategories"].get(subcat, 0) + 1
                )

        # Find existing mappings for these payees
        cursor.execute("""
                SELECT id, pattern, normalized_name, default_category, merchant_type
                FROM merchant_normalizations
                WHERE source = 'direct_debit'
                ORDER BY priority DESC
            """)
        mappings = {row["pattern"].upper(): dict(row) for row in cursor.fetchall()}

        # Build result list
        result = []
        for payee_upper, data in payee_data.items():
            # Find most common category/subcategory
            most_common_cat = max(
                data["categories"].keys(), key=lambda k: data["categories"][k]
            )
            most_common_subcat = max(
                data["subcategories"].keys(), key=lambda k: data["subcategories"][k]
            )

            payee_info = {
                "payee": data["payee"],
                "transaction_count": data["transaction_count"],
                "sample_description": data["sample_description"],
                "current_category": most_common_cat
                if most_common_cat != "Uncategorized"
                else None,
                "current_subcategory": most_common_subcat
                if most_common_subcat != "None"
                else None,
                "mapping_id": None,
                "mapped_name": None,
                "mapped_category": None,
                "mapped_subcategory": None,
            }

            # Check if there's an existing mapping
            if payee_upper in mappings:
                mapping = mappings[payee_upper]
                payee_info["mapping_id"] = mapping["id"]
                payee_info["mapped_name"] = mapping["normalized_name"]
                payee_info["mapped_category"] = mapping["default_category"]
                payee_info["mapped_subcategory"] = mapping[
                    "normalized_name"
                ]  # Subcategory = normalized name

            result.append(payee_info)

        # Sort alphabetically by payee name
        result.sort(key=lambda x: x["payee"].upper())
        return result


def get_direct_debit_mappings() -> list:
    """
    Fetch merchant normalizations configured for direct debit payees.

    Returns:
        List of mapping dictionaries
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
                SELECT id, pattern, pattern_type, normalized_name, merchant_type,
                       default_category, priority, source, usage_count,
                       created_at, updated_at
                FROM merchant_normalizations
                WHERE source = 'direct_debit'
                ORDER BY priority DESC, pattern ASC
            """)
        return [dict(row) for row in cursor.fetchall()]


def save_direct_debit_mapping(
    payee_pattern: str,
    normalized_name: str,
    category: str,
    subcategory: str = None,
    merchant_type: str = None,
) -> int:
    """
    Save a direct debit payee mapping.

    Creates or updates a merchant_normalization entry with source='direct_debit'.

    Args:
        payee_pattern: Pattern to match (the extracted payee name)
        normalized_name: Clean merchant name
        category: Category to assign
        subcategory: Optional subcategory (stored in metadata)
        merchant_type: Optional merchant type

    Returns:
        ID of the created/updated mapping
    """
    with get_db() as conn, conn.cursor() as cursor:
        # Use upsert to create or update
        cursor.execute(
            """
                INSERT INTO merchant_normalizations
                (pattern, pattern_type, normalized_name, merchant_type,
                 default_category, priority, source)
                VALUES (%s, 'exact', %s, %s, %s, 100, 'direct_debit')
                ON CONFLICT (pattern, pattern_type) DO UPDATE SET
                    normalized_name = EXCLUDED.normalized_name,
                    merchant_type = EXCLUDED.merchant_type,
                    default_category = EXCLUDED.default_category,
                    priority = EXCLUDED.priority,
                    source = 'direct_debit',
                    updated_at = NOW()
                RETURNING id
            """,
            (payee_pattern.upper(), normalized_name, merchant_type, category),
        )
        mapping_id = cursor.fetchone()[0]
        conn.commit()
        return mapping_id


def delete_direct_debit_mapping(mapping_id: int) -> bool:
    """
    Delete a direct debit mapping.

    Args:
        mapping_id: ID of the mapping to delete

    Returns:
        True if deleted successfully
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                DELETE FROM merchant_normalizations
                WHERE id = %s AND source = 'direct_debit'
            """,
            (mapping_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def apply_direct_debit_mappings() -> dict:
    """
    Re-enrich all direct debit transactions using current mappings.

    For each direct debit transaction:
    1. Extract payee using pattern extractor
    2. Match against merchant_normalizations with source='direct_debit'
    3. Apply enrichment data to matching transactions

    Returns:
        Dict with: updated_count, transactions (list of updated IDs)
    """
    from mcp.pattern_extractor import (
        extract_direct_debit_payee_fallback,
        extract_variables,
    )

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get all direct debit mappings
        cursor.execute("""
                SELECT id, pattern, normalized_name, merchant_type, default_category
                FROM merchant_normalizations
                WHERE source = 'direct_debit'
            """)
        mappings = {row["pattern"].upper(): dict(row) for row in cursor.fetchall()}

        if not mappings:
            return {"updated_count": 0, "transactions": []}

        # Get direct debit transactions
        cursor.execute("""
                SELECT id, description, metadata
                FROM truelayer_transactions
                WHERE description LIKE 'DIRECT DEBIT PAYMENT TO%'
            """)
        transactions = cursor.fetchall()

        updated_ids = []
        for txn in transactions:
            extracted = extract_variables(txn["description"])
            payee = extracted.get("payee")

            # Fallback extraction if strict pattern fails
            if not payee:
                extracted = extract_direct_debit_payee_fallback(txn["description"])
                payee = extracted.get("payee")

            if payee and payee.upper() in mappings:
                mapping = mappings[payee.upper()]

                # Build enrichment data
                metadata = txn["metadata"] or {}
                enrichment = metadata.get("enrichment", {})
                enrichment.update(
                    {
                        "primary_category": mapping["default_category"],
                        "subcategory": mapping[
                            "normalized_name"
                        ],  # Use merchant as subcategory
                        "merchant_clean_name": mapping["normalized_name"],
                        "merchant_type": mapping.get("merchant_type"),
                        "confidence_score": 1.0,
                        "llm_model": "direct_debit_rule",
                        "enrichment_source": "rule",
                    }
                )
                metadata["enrichment"] = enrichment

                # Update transaction
                cursor.execute(
                    """
                        UPDATE truelayer_transactions
                        SET metadata = %s
                        WHERE id = %s
                    """,
                    (json.dumps(metadata), txn["id"]),
                )
                updated_ids.append(txn["id"])

        conn.commit()
        return {"updated_count": len(updated_ids), "transactions": updated_ids}


def detect_new_direct_debits() -> dict:
    """
    Detect new direct debit payees that haven't been mapped yet.

    Returns:
        {
            'new_payees': [{'payee': str, 'first_seen': str, 'transaction_count': int, 'mandate_numbers': list}],
            'total_unmapped': int
        }
    """
    from mcp.pattern_extractor import (
        extract_direct_debit_payee_fallback,
        extract_variables,
    )

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get all mapped payees
        cursor.execute("""
                SELECT UPPER(pattern) as pattern FROM merchant_normalizations
                WHERE source = 'direct_debit'
            """)
        mapped_payees = {row["pattern"] for row in cursor.fetchall()}

        # Get all direct debit transactions
        cursor.execute("""
                SELECT description, timestamp
                FROM truelayer_transactions
                WHERE description LIKE 'DIRECT DEBIT PAYMENT TO%'
                ORDER BY timestamp ASC
            """)

        # Track payees and their mandates
        payee_info = {}  # payee -> {first_seen, mandates: set(), count}

        for txn in cursor.fetchall():
            extracted = extract_variables(txn["description"])
            if not extracted.get("payee"):
                extracted = extract_direct_debit_payee_fallback(txn["description"])

            payee = extracted.get("payee")
            if not payee:
                continue

            payee_upper = payee.upper().strip()
            mandate = extracted.get("mandate_number")

            if payee_upper not in payee_info:
                payee_info[payee_upper] = {
                    "payee": payee.strip(),
                    "first_seen": txn["timestamp"],
                    "mandates": set(),
                    "count": 0,
                }

            payee_info[payee_upper]["count"] += 1
            if mandate:
                payee_info[payee_upper]["mandates"].add(mandate)

        # Find unmapped payees
        new_payees = []
        for payee_upper, info in payee_info.items():
            if payee_upper not in mapped_payees:
                new_payees.append(
                    {
                        "payee": info["payee"],
                        "first_seen": info["first_seen"].isoformat()
                        if info["first_seen"]
                        else None,
                        "transaction_count": info["count"],
                        "mandate_numbers": list(info["mandates"]),
                    }
                )

        return {
            "new_payees": sorted(new_payees, key=lambda x: x["payee"].upper()),
            "total_unmapped": len(new_payees),
        }


# ============================================================================
# RULES TESTING AND STATISTICS
# ============================================================================


def test_rule_pattern(pattern: str, pattern_type: str, limit: int = 10) -> dict:
    """
    Test a pattern against all transactions to see what would match.

    Args:
        pattern: The pattern to test
        pattern_type: Type of pattern (contains, starts_with, exact, regex)
        limit: Maximum number of sample transactions to return

    Returns:
        Dict with: match_count, sample_transactions
    """
    import re

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get all transactions
        cursor.execute("""
                SELECT id, description, amount, timestamp as date
                FROM truelayer_transactions
                ORDER BY timestamp DESC
            """)
        transactions = cursor.fetchall()

        matches = []
        pattern_upper = pattern.upper()

        for txn in transactions:
            description = txn["description"].upper() if txn["description"] else ""

            matched = False
            if pattern_type == "contains":
                matched = pattern_upper in description
            elif pattern_type == "starts_with":
                matched = description.startswith(pattern_upper)
            elif pattern_type == "exact":
                matched = description == pattern_upper
            elif pattern_type == "regex":
                try:
                    matched = bool(
                        re.search(pattern, txn["description"] or "", re.IGNORECASE)
                    )
                except re.error:
                    matched = False

            if matched:
                matches.append(
                    {
                        "id": txn["id"],
                        "description": txn["description"],
                        "amount": float(txn["amount"]) if txn["amount"] else 0,
                        "date": txn["date"].isoformat() if txn["date"] else None,
                    }
                )

        return {"match_count": len(matches), "sample_transactions": matches[:limit]}


def get_rules_statistics() -> dict:
    """
    Get comprehensive rule usage statistics and coverage metrics.

    Returns:
        Dict with:
            - category_rules_count: Total category rules
            - merchant_rules_count: Total merchant normalizations
            - total_usage: Sum of all rule usage counts
            - coverage_percentage: Percent of transactions with rule-based enrichment
            - rules_by_category: Dict mapping category to rule count
            - rules_by_source: Dict mapping source to rule count
            - top_used_rules: List of top 10 most used rules
            - unused_rules: List of rules with usage_count = 0
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Count category rules
        cursor.execute(
            "SELECT COUNT(*) as count FROM category_rules WHERE is_active = true"
        )
        category_rules_count = cursor.fetchone()["count"]

        # Count merchant normalizations
        cursor.execute("SELECT COUNT(*) as count FROM merchant_normalizations")
        merchant_rules_count = cursor.fetchone()["count"]

        # Get total usage
        cursor.execute(
            "SELECT COALESCE(SUM(usage_count), 0) as total FROM category_rules"
        )
        category_usage = cursor.fetchone()["total"]
        cursor.execute(
            "SELECT COALESCE(SUM(usage_count), 0) as total FROM merchant_normalizations"
        )
        merchant_usage = cursor.fetchone()["total"]
        total_usage = category_usage + merchant_usage

        # Get coverage: count transactions with rule-based enrichment
        cursor.execute("""
                SELECT COUNT(*) as total FROM truelayer_transactions
            """)
        total_transactions = cursor.fetchone()["total"]

        cursor.execute("""
                SELECT COUNT(*) as covered FROM truelayer_transactions
                WHERE metadata->'enrichment'->>'enrichment_source' = 'rule'
            """)
        covered_transactions = cursor.fetchone()["covered"]

        coverage_percentage = (
            (covered_transactions / total_transactions * 100)
            if total_transactions > 0
            else 0
        )

        # Rules by category
        cursor.execute("""
                SELECT category, COUNT(*) as count
                FROM category_rules
                WHERE is_active = true
                GROUP BY category
                ORDER BY count DESC
            """)
        rules_by_category = {row["category"]: row["count"] for row in cursor.fetchall()}

        # Rules by source (combine both tables)
        cursor.execute("""
                SELECT source, COUNT(*) as count
                FROM (
                    SELECT source FROM category_rules WHERE is_active = true
                    UNION ALL
                    SELECT source FROM merchant_normalizations
                ) combined
                GROUP BY source
                ORDER BY count DESC
            """)
        rules_by_source = {row["source"]: row["count"] for row in cursor.fetchall()}

        # Top used rules (combine category rules and merchant normalizations)
        cursor.execute("""
                SELECT name, usage_count, type FROM (
                    SELECT rule_name as name, usage_count, 'category' as type
                    FROM category_rules
                    WHERE is_active = true
                    UNION ALL
                    SELECT pattern as name, usage_count, 'merchant' as type
                    FROM merchant_normalizations
                ) combined
                ORDER BY usage_count DESC
                LIMIT 10
            """)
        top_used_rules = [
            {"name": row["name"], "count": row["usage_count"], "type": row["type"]}
            for row in cursor.fetchall()
        ]

        # Unused rules
        cursor.execute("""
                SELECT name, type FROM (
                    SELECT rule_name as name, 'category' as type
                    FROM category_rules
                    WHERE is_active = true AND usage_count = 0
                    UNION ALL
                    SELECT pattern as name, 'merchant' as type
                    FROM merchant_normalizations
                    WHERE usage_count = 0
                ) combined
            """)
        unused_rules = [
            {"name": row["name"], "type": row["type"]} for row in cursor.fetchall()
        ]

        return {
            "category_rules_count": category_rules_count,
            "merchant_rules_count": merchant_rules_count,
            "total_usage": total_usage,
            "total_transactions": total_transactions,
            "covered_transactions": covered_transactions,
            "coverage_percentage": round(coverage_percentage, 1),
            "rules_by_category": rules_by_category,
            "rules_by_source": rules_by_source,
            "top_used_rules": top_used_rules,
            "unused_rules": unused_rules,
            "unused_rules_count": len(unused_rules),
        }


def test_all_rules() -> dict:
    """
    Evaluate all rules against all transactions and return a coverage report.

    Returns detailed breakdown by category, identifies conflicts, and unused rules.
    """
    import re
    from collections import defaultdict

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all active category rules
            cursor.execute("""
                SELECT id, rule_name, description_pattern, pattern_type, category, subcategory
                FROM category_rules
                WHERE is_active = true
                ORDER BY priority DESC
            """)
            category_rules = cursor.fetchall()

            # Get all merchant normalizations
            cursor.execute("""
                SELECT id, pattern, pattern_type, normalized_name, default_category
                FROM merchant_normalizations
                ORDER BY priority DESC
            """)
            merchant_rules = cursor.fetchall()

            # Get all transactions
            cursor.execute("""
                SELECT id, description
                FROM truelayer_transactions
            """)
            transactions = cursor.fetchall()

            # Track matches
            rule_matches = defaultdict(list)  # rule_id -> [txn_ids]
            txn_matches = defaultdict(list)  # txn_id -> [rule_ids]
            category_coverage = defaultdict(int)  # category -> count

            for txn in transactions:
                desc = txn["description"].upper() if txn["description"] else ""
                matched_any = False

                # Check category rules
                for rule in category_rules:
                    pattern = rule["description_pattern"].upper()
                    pattern_type = rule["pattern_type"]

                    matched = False
                    if pattern_type == "contains":
                        matched = pattern in desc
                    elif pattern_type == "starts_with":
                        matched = desc.startswith(pattern)
                    elif pattern_type == "exact":
                        matched = desc == pattern
                    elif pattern_type == "regex":
                        try:
                            matched = bool(
                                re.search(
                                    rule["description_pattern"],
                                    txn["description"] or "",
                                    re.IGNORECASE,
                                )
                            )
                        except re.error:
                            pass

                    if matched:
                        rule_key = f"cat_{rule['id']}"
                        rule_matches[rule_key].append(txn["id"])
                        txn_matches[txn["id"]].append(rule_key)
                        category_coverage[rule["category"]] += 1
                        matched_any = True

                # Check merchant rules
                for rule in merchant_rules:
                    pattern = rule["pattern"].upper()
                    pattern_type = rule["pattern_type"]

                    matched = False
                    if pattern_type == "contains":
                        matched = pattern in desc
                    elif pattern_type == "starts_with":
                        matched = desc.startswith(pattern)
                    elif pattern_type == "exact":
                        matched = desc == pattern
                    elif pattern_type == "regex":
                        try:
                            matched = bool(
                                re.search(
                                    rule["pattern"],
                                    txn["description"] or "",
                                    re.IGNORECASE,
                                )
                            )
                        except re.error:
                            pass

                    if matched:
                        rule_key = f"mer_{rule['id']}"
                        rule_matches[rule_key].append(txn["id"])
                        txn_matches[txn["id"]].append(rule_key)
                        if rule["default_category"]:
                            category_coverage[rule["default_category"]] += 1
                        matched_any = True

            # Calculate statistics
            total_transactions = len(transactions)
            covered_transactions = len([t for t in txn_matches if txn_matches[t]])
            coverage_percentage = (
                (covered_transactions / total_transactions * 100)
                if total_transactions > 0
                else 0
            )

            # Find unused rules
            unused_category_rules = [
                r for r in category_rules if f"cat_{r['id']}" not in rule_matches
            ]
            unused_merchant_rules = [
                r for r in merchant_rules if f"mer_{r['id']}" not in rule_matches
            ]

            # Find potential conflicts (transactions matching multiple rules)
            conflicts = []
            for txn_id, rules in txn_matches.items():
                if len(rules) > 1:
                    conflicts.append(
                        {"transaction_id": txn_id, "matching_rules": rules}
                    )

            return {
                "total_transactions": total_transactions,
                "covered_transactions": covered_transactions,
                "coverage_percentage": round(coverage_percentage, 1),
                "category_coverage": dict(category_coverage),
                "unused_category_rules": [
                    {
                        "id": r["id"],
                        "name": r["rule_name"],
                        "pattern": r["description_pattern"],
                    }
                    for r in unused_category_rules
                ],
                "unused_merchant_rules": [
                    {
                        "id": r["id"],
                        "pattern": r["pattern"],
                        "name": r["normalized_name"],
                    }
                    for r in unused_merchant_rules
                ],
                "potential_conflicts_count": len(conflicts),
                "sample_conflicts": conflicts[:10],  # Limit to 10 examples
            }


def apply_all_rules_to_transactions() -> dict:
    """
    Re-enrich all transactions using current category rules and merchant normalizations.

    This applies the consistency engine to all transactions, updating enrichment data
    for transactions that match rules.

    Returns:
        Dict with: updated_count, rule_hits (dict of rule_name -> count)
    """
    from mcp.consistency_engine import apply_rules_to_transaction

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get all rules
        cursor.execute("""
                SELECT * FROM category_rules
                WHERE is_active = true
                ORDER BY priority DESC
            """)
        category_rules = cursor.fetchall()

        cursor.execute("""
                SELECT * FROM merchant_normalizations
                ORDER BY priority DESC
            """)
        merchant_normalizations = cursor.fetchall()

        # Get all transactions
        cursor.execute("""
                SELECT id, description, amount, transaction_type, timestamp, metadata
                FROM truelayer_transactions
            """)
        transactions = cursor.fetchall()

        updated_count = 0
        rule_hits = {}

        for txn in transactions:
            txn_dict = dict(txn)
            result = apply_rules_to_transaction(
                txn_dict, category_rules, merchant_normalizations
            )

            if result and result.get("primary_category"):
                # Update the transaction with rule-based enrichment
                metadata = txn["metadata"] or {}
                metadata["enrichment"] = result

                cursor.execute(
                    """
                        UPDATE truelayer_transactions
                        SET metadata = %s
                        WHERE id = %s
                    """,
                    (json.dumps(metadata), txn["id"]),
                )

                updated_count += 1

                # Track rule hits
                matched_rule = result.get("matched_rule", "unknown")
                rule_hits[matched_rule] = rule_hits.get(matched_rule, 0) + 1

        conn.commit()

        return {
            "updated_count": updated_count,
            "total_transactions": len(transactions),
            "rule_hits": rule_hits,
        }


# ============================================================================
# Normalized Categories & Subcategories Functions
# ============================================================================


def get_normalized_categories(active_only: bool = False, include_counts: bool = False):
    """Get all normalized categories.

    Args:
        active_only: If True, only return categories where is_active=TRUE
        include_counts: If True, include transaction and subcategory counts

    Returns:
        List of category dictionaries
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if include_counts:
            cursor.execute(
                """
                    SELECT
                        nc.*,
                        COALESCE(txn_counts.transaction_count, 0) as transaction_count,
                        COALESCE(sub_counts.subcategory_count, 0) as subcategory_count
                    FROM normalized_categories nc
                    LEFT JOIN (
                        SELECT category_id, COUNT(*) as transaction_count
                        FROM truelayer_transactions
                        WHERE category_id IS NOT NULL
                        GROUP BY category_id
                    ) txn_counts ON nc.id = txn_counts.category_id
                    LEFT JOIN (
                        SELECT category_id, COUNT(*) as subcategory_count
                        FROM normalized_subcategories
                        GROUP BY category_id
                    ) sub_counts ON nc.id = sub_counts.category_id
                    WHERE (%s = FALSE OR nc.is_active = TRUE)
                    ORDER BY nc.display_order, nc.name
                """,
                (active_only,),
            )
        else:
            cursor.execute(
                """
                    SELECT * FROM normalized_categories
                    WHERE (%s = FALSE OR is_active = TRUE)
                    ORDER BY display_order, name
                """,
                (active_only,),
            )
        return cursor.fetchall()


def get_normalized_category_by_id(category_id: int):
    """Get a single normalized category by ID with subcategories."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get category
        cursor.execute(
            """
                SELECT
                    nc.*,
                    COALESCE(txn_counts.transaction_count, 0) as transaction_count
                FROM normalized_categories nc
                LEFT JOIN (
                    SELECT category_id, COUNT(*) as transaction_count
                    FROM truelayer_transactions
                    WHERE category_id IS NOT NULL
                    GROUP BY category_id
                ) txn_counts ON nc.id = txn_counts.category_id
                WHERE nc.id = %s
            """,
            (category_id,),
        )
        category = cursor.fetchone()

        if not category:
            return None

        # Get subcategories
        cursor.execute(
            """
                SELECT
                    ns.*,
                    COALESCE(txn_counts.transaction_count, 0) as transaction_count
                FROM normalized_subcategories ns
                LEFT JOIN (
                    SELECT subcategory_id, COUNT(*) as transaction_count
                    FROM truelayer_transactions
                    WHERE subcategory_id IS NOT NULL
                    GROUP BY subcategory_id
                ) txn_counts ON ns.id = txn_counts.subcategory_id
                WHERE ns.category_id = %s
                ORDER BY ns.display_order, ns.name
            """,
            (category_id,),
        )
        category["subcategories"] = cursor.fetchall()

        return category


def get_normalized_category_by_name(name: str):
    """Get a normalized category by name."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT * FROM normalized_categories WHERE name = %s
            """,
            (name,),
        )
        return cursor.fetchone()


def create_normalized_category(
    name: str, description: str = None, is_essential: bool = False, color: str = None
):
    """Create a new normalized category.

    Returns:
        The created category dict, or None if name already exists
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                # Get next display order
                cursor.execute(
                    "SELECT COALESCE(MAX(display_order), 0) + 1 FROM normalized_categories"
                )
                next_order = cursor.fetchone()["coalesce"]

                cursor.execute(
                    """
                    INSERT INTO normalized_categories (name, description, is_system, is_essential, display_order, color)
                    VALUES (%s, %s, FALSE, %s, %s, %s)
                    RETURNING *
                """,
                    (name, description, is_essential, next_order, color),
                )
                conn.commit()
                return cursor.fetchone()
            except Exception as e:
                conn.rollback()
                if "unique constraint" in str(e).lower():
                    return None
                raise


def update_normalized_category(
    category_id: int,
    name: str = None,
    description: str = None,
    is_active: bool = None,
    is_essential: bool = None,
    color: str = None,
):
    """Update a normalized category and cascade changes if name changed.

    Returns:
        Dict with category and update counts, or None if not found
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get current category
        cursor.execute(
            "SELECT * FROM normalized_categories WHERE id = %s", (category_id,)
        )
        current = cursor.fetchone()
        if not current:
            return None

        old_name = current["name"]
        new_name = name if name is not None else old_name

        # Build update query dynamically
        updates = []
        params = []

        if name is not None:
            updates.append("name = %s")
            params.append(name)
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)
        if is_essential is not None:
            updates.append("is_essential = %s")
            params.append(is_essential)
        if color is not None:
            updates.append("color = %s")
            params.append(color)

        if not updates:
            return {
                "category": current,
                "transactions_updated": 0,
                "rules_updated": 0,
            }

        params.append(category_id)
        cursor.execute(
            f"""
                UPDATE normalized_categories
                SET {", ".join(updates)}
                WHERE id = %s
                RETURNING *
            """,
            params,
        )
        updated_category = cursor.fetchone()

        transactions_updated = 0
        rules_updated = 0

        # If name changed, cascade updates
        if name is not None and name != old_name:
            # Update transaction_category VARCHAR (for backwards compatibility)
            cursor.execute(
                """
                    UPDATE truelayer_transactions
                    SET transaction_category = %s
                    WHERE category_id = %s
                """,
                (new_name, category_id),
            )
            transactions_updated = cursor.rowcount

            # Update JSONB metadata
            cursor.execute(
                """
                    UPDATE truelayer_transactions
                    SET metadata = jsonb_set(
                        metadata,
                        '{enrichment,primary_category}',
                        %s::jsonb
                    )
                    WHERE category_id = %s
                      AND metadata->'enrichment' IS NOT NULL
                """,
                (json.dumps(new_name), category_id),
            )

            # Update category_rules VARCHAR
            cursor.execute(
                """
                    UPDATE category_rules
                    SET category = %s
                    WHERE category_id = %s
                """,
                (new_name, category_id),
            )
            rules_updated = cursor.rowcount

        conn.commit()

        # Invalidate cache
        try:
            from cache_manager import cache_invalidate_transactions

            cache_invalidate_transactions()
        except ImportError:
            pass

        return {
            "category": updated_category,
            "transactions_updated": transactions_updated,
            "rules_updated": rules_updated,
            "old_name": old_name,
            "new_name": new_name,
        }


def delete_normalized_category(category_id: int, reassign_to_category_id: int = None):
    """Delete a normalized category.

    System categories cannot be deleted. Transactions are reassigned to 'Other' or specified category.

    Returns:
        Dict with deletion result, or None if not found or is system category
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Check if category exists and is not system
        cursor.execute(
            "SELECT * FROM normalized_categories WHERE id = %s", (category_id,)
        )
        category = cursor.fetchone()

        if not category:
            return None
        if category["is_system"]:
            return {"error": "Cannot delete system category"}

        # Find reassignment target (default to 'Other')
        if reassign_to_category_id:
            target_id = reassign_to_category_id
        else:
            cursor.execute("SELECT id FROM normalized_categories WHERE name = 'Other'")
            other = cursor.fetchone()
            target_id = other["id"] if other else None

        # Reassign transactions
        transactions_reassigned = 0
        if target_id:
            cursor.execute(
                """
                    UPDATE truelayer_transactions
                    SET category_id = %s, subcategory_id = NULL
                    WHERE category_id = %s
                """,
                (target_id, category_id),
            )
            transactions_reassigned = cursor.rowcount

        # Delete the category (subcategories cascade)
        cursor.execute(
            "DELETE FROM normalized_categories WHERE id = %s", (category_id,)
        )

        conn.commit()

        return {
            "deleted_category": category["name"],
            "transactions_reassigned": transactions_reassigned,
            "reassigned_to_category_id": target_id,
        }


def get_normalized_subcategories(category_id: int = None, include_counts: bool = False):
    """Get normalized subcategories, optionally filtered by category.

    Args:
        category_id: If provided, only return subcategories for this category
        include_counts: If True, include transaction counts
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if include_counts:
                if category_id:
                    cursor.execute(
                        """
                        SELECT
                            ns.*,
                            nc.name as category_name,
                            COALESCE(txn_counts.transaction_count, 0) as transaction_count
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        LEFT JOIN (
                            SELECT subcategory_id, COUNT(*) as transaction_count
                            FROM truelayer_transactions
                            WHERE subcategory_id IS NOT NULL
                            GROUP BY subcategory_id
                        ) txn_counts ON ns.id = txn_counts.subcategory_id
                        WHERE ns.category_id = %s
                        ORDER BY ns.display_order, ns.name
                    """,
                        (category_id,),
                    )
                else:
                    cursor.execute("""
                        SELECT
                            ns.*,
                            nc.name as category_name,
                            COALESCE(txn_counts.transaction_count, 0) as transaction_count
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        LEFT JOIN (
                            SELECT subcategory_id, COUNT(*) as transaction_count
                            FROM truelayer_transactions
                            WHERE subcategory_id IS NOT NULL
                            GROUP BY subcategory_id
                        ) txn_counts ON ns.id = txn_counts.subcategory_id
                        ORDER BY nc.name, ns.display_order, ns.name
                    """)
            else:
                if category_id:
                    cursor.execute(
                        """
                        SELECT ns.*, nc.name as category_name
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        WHERE ns.category_id = %s
                        ORDER BY ns.display_order, ns.name
                    """,
                        (category_id,),
                    )
                else:
                    cursor.execute("""
                        SELECT ns.*, nc.name as category_name
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        ORDER BY nc.name, ns.display_order, ns.name
                    """)
            return cursor.fetchall()


def get_normalized_subcategory_by_id(subcategory_id: int):
    """Get a single normalized subcategory by ID."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT
                    ns.*,
                    nc.name as category_name,
                    COALESCE(txn_counts.transaction_count, 0) as transaction_count
                FROM normalized_subcategories ns
                JOIN normalized_categories nc ON ns.category_id = nc.id
                LEFT JOIN (
                    SELECT subcategory_id, COUNT(*) as transaction_count
                    FROM truelayer_transactions
                    WHERE subcategory_id IS NOT NULL
                    GROUP BY subcategory_id
                ) txn_counts ON ns.id = txn_counts.subcategory_id
                WHERE ns.id = %s
            """,
            (subcategory_id,),
        )
        return cursor.fetchone()


def create_normalized_subcategory(category_id: int, name: str, description: str = None):
    """Create a new normalized subcategory.

    Returns:
        The created subcategory dict, or None if already exists
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                # Get next display order for this category
                cursor.execute(
                    """
                    SELECT COALESCE(MAX(display_order), 0) + 1
                    FROM normalized_subcategories WHERE category_id = %s
                """,
                    (category_id,),
                )
                next_order = cursor.fetchone()["coalesce"]

                cursor.execute(
                    """
                    INSERT INTO normalized_subcategories (category_id, name, description, display_order)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                """,
                    (category_id, name, description, next_order),
                )
                conn.commit()

                subcategory = cursor.fetchone()

                # Get category name
                cursor.execute(
                    "SELECT name FROM normalized_categories WHERE id = %s",
                    (category_id,),
                )
                cat = cursor.fetchone()
                subcategory["category_name"] = cat["name"] if cat else None

                return subcategory
            except Exception as e:
                conn.rollback()
                if "unique constraint" in str(e).lower():
                    return None
                raise


def update_normalized_subcategory(
    subcategory_id: int,
    name: str = None,
    description: str = None,
    is_active: bool = None,
    category_id: int = None,
):
    """Update a normalized subcategory and cascade changes if name changed.

    Returns:
        Dict with subcategory and update counts, or None if not found
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get current subcategory
        cursor.execute(
            """
                SELECT ns.*, nc.name as category_name
                FROM normalized_subcategories ns
                JOIN normalized_categories nc ON ns.category_id = nc.id
                WHERE ns.id = %s
            """,
            (subcategory_id,),
        )
        current = cursor.fetchone()
        if not current:
            return None

        old_name = current["name"]
        old_category_id = current["category_id"]
        new_name = name if name is not None else old_name

        # Build update query dynamically
        updates = []
        params = []

        if name is not None:
            updates.append("name = %s")
            params.append(name)
        if description is not None:
            updates.append("description = %s")
            params.append(description)
        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)
        if category_id is not None:
            updates.append("category_id = %s")
            params.append(category_id)

        if not updates:
            return {"subcategory": current, "transactions_updated": 0}

        params.append(subcategory_id)
        cursor.execute(
            f"""
                UPDATE normalized_subcategories
                SET {", ".join(updates)}
                WHERE id = %s
                RETURNING *
            """,
            params,
        )
        updated_subcategory = cursor.fetchone()

        # Get new category name
        cursor.execute(
            "SELECT name FROM normalized_categories WHERE id = %s",
            (updated_subcategory["category_id"],),
        )
        cat = cursor.fetchone()
        updated_subcategory["category_name"] = cat["name"] if cat else None

        transactions_updated = 0

        # If name changed, cascade updates to JSONB metadata
        if name is not None and name != old_name:
            cursor.execute(
                """
                    UPDATE truelayer_transactions
                    SET metadata = jsonb_set(
                        metadata,
                        '{enrichment,subcategory}',
                        %s::jsonb
                    )
                    WHERE subcategory_id = %s
                      AND metadata->'enrichment' IS NOT NULL
                """,
                (json.dumps(new_name), subcategory_id),
            )
            transactions_updated = cursor.rowcount

        conn.commit()

        # Invalidate cache
        try:
            from cache_manager import cache_invalidate_transactions

            cache_invalidate_transactions()
        except ImportError:
            pass

        return {
            "subcategory": updated_subcategory,
            "transactions_updated": transactions_updated,
            "old_name": old_name,
            "new_name": new_name,
        }


def delete_normalized_subcategory(subcategory_id: int):
    """Delete a normalized subcategory.

    Transactions will have their subcategory_id set to NULL.

    Returns:
        Dict with deletion result, or None if not found
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Get subcategory
        cursor.execute(
            """
                SELECT ns.*, nc.name as category_name
                FROM normalized_subcategories ns
                JOIN normalized_categories nc ON ns.category_id = nc.id
                WHERE ns.id = %s
            """,
            (subcategory_id,),
        )
        subcategory = cursor.fetchone()

        if not subcategory:
            return None

        # Clear subcategory_id from transactions
        cursor.execute(
            """
                UPDATE truelayer_transactions
                SET subcategory_id = NULL
                WHERE subcategory_id = %s
            """,
            (subcategory_id,),
        )
        transactions_cleared = cursor.rowcount

        # Delete the subcategory
        cursor.execute(
            "DELETE FROM normalized_subcategories WHERE id = %s", (subcategory_id,)
        )

        conn.commit()

        return {
            "deleted_subcategory": subcategory["name"],
            "category_name": subcategory["category_name"],
            "transactions_cleared": transactions_cleared,
        }


def get_essential_category_names():
    """Get list of category names that are marked as essential.

    Used by consistency engine for Essential/Discretionary classification.
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("""
                SELECT name FROM normalized_categories
                WHERE is_essential = TRUE AND is_active = TRUE
            """)
        return {row["name"] for row in cursor.fetchall()}


# =============================================================================
# PDF Attachment Functions (MinIO storage)
# =============================================================================


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
# USER AUTHENTICATION FUNCTIONS
# ============================================================================


def insert_user(
    username: str, email: str, password_hash: str, is_admin: bool = False
) -> int:
    """Create a new user account.

    Args:
        username: Unique username for login
        email: Unique email address
        password_hash: Hashed password (pbkdf2:sha256:600000)
        is_admin: Admin privilege flag (default False)

    Returns:
        User ID of created user

    Raises:
        Exception: If username or email already exists
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO users (username, email, password_hash, is_admin, is_active)
                VALUES (%s, %s, %s, %s, TRUE)
                RETURNING id
            """,
            (username, email, password_hash, is_admin),
        )
        user_id = cursor.fetchone()[0]
        conn.commit()
        return user_id


def get_user_by_id(user_id: int) -> dict:
    """Get user by ID (for Flask-Login user_loader).

    Args:
        user_id: User ID to lookup

    Returns:
        Dictionary with user data or None if not found
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, username, email, password_hash, is_admin, is_active,
                       last_login_at, created_at, updated_at
                FROM users
                WHERE id = %s AND is_active = TRUE
            """,
            (user_id,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_user_by_username(username: str) -> dict:
    """Get user by username (for login).

    Args:
        username: Username to lookup

    Returns:
        Dictionary with user data or None if not found
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, username, email, password_hash, is_admin, is_active,
                       last_login_at, created_at, updated_at
                FROM users
                WHERE username = %s
            """,
            (username,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def get_user_by_email(email: str) -> dict:
    """Get user by email.

    Args:
        email: Email address to lookup

    Returns:
        Dictionary with user data or None if not found
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, username, email, password_hash, is_admin, is_active,
                       last_login_at, created_at, updated_at
                FROM users
                WHERE email = %s
            """,
            (email,),
        )
        result = cursor.fetchone()
        return dict(result) if result else None


def update_user_last_login(user_id: int, timestamp: datetime) -> bool:
    """Update user's last login timestamp.

    Args:
        user_id: User ID
        timestamp: Login timestamp

    Returns:
        True if updated successfully
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE users
                SET last_login_at = %s
                WHERE id = %s
            """,
            (timestamp, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def log_security_event(
    user_id: int,
    event_type: str,
    success: bool,
    ip_address: str = None,
    user_agent: str = None,
    metadata: dict = None,
) -> int:
    """Log security-related event to audit table.

    Args:
        user_id: User ID (can be None for anonymous events)
        event_type: Event type (login_success, login_failed, rate_limit_exceeded, etc.)
        success: Whether event was successful
        ip_address: Client IP address (optional)
        user_agent: Client user agent (optional)
        metadata: Additional context as JSON (optional)

    Returns:
        Audit log entry ID
    """
    import json

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO security_audit_log
                (user_id, event_type, success, ip_address, user_agent, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
            (
                user_id,
                event_type,
                success,
                ip_address,
                user_agent,
                json.dumps(metadata or {}),
            ),
        )
        log_id = cursor.fetchone()[0]
        conn.commit()
        return log_id


# =============================================================================
# GMAIL ERROR TRACKING & STATISTICS
# =============================================================================


def save_gmail_error(
    connection_id: int = None,
    sync_job_id: int = None,
    message_id: str = None,
    receipt_id: int = None,
    error_stage: str = None,
    error_type: str = None,
    error_message: str = None,
    stack_trace: str = None,
    error_context: dict = None,
    is_retryable: bool = False,
) -> int:
    """Save Gmail processing error to database.

    Args:
        connection_id: Gmail connection ID (optional)
        sync_job_id: Sync job ID (optional)
        message_id: Gmail message ID where error occurred (optional)
        receipt_id: Receipt ID where error occurred (optional)
        error_stage: Error stage (fetch, parse, vendor_parse, etc.)
        error_type: Error type (api_error, timeout, parse_error, etc.)
        error_message: Human-readable error message
        stack_trace: Full exception stack trace (optional)
        error_context: Additional context as dict (sender_domain, etc.)
        is_retryable: Whether error is retryable

    Returns:
        Error record ID
    """
    import json

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO gmail_processing_errors
                (connection_id, sync_job_id, message_id, receipt_id,
                 error_stage, error_type, error_message, stack_trace,
                 error_context, is_retryable)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
            (
                connection_id,
                sync_job_id,
                message_id,
                receipt_id,
                error_stage,
                error_type,
                error_message,
                stack_trace,
                json.dumps(error_context or {}),
                is_retryable,
            ),
        )
        error_id = cursor.fetchone()[0]
        conn.commit()
        return error_id


def save_gmail_parse_statistic(
    connection_id: int,
    sync_job_id: int = None,
    message_id: str = None,
    sender_domain: str = None,
    merchant_normalized: str = None,
    parse_method: str = None,
    merchant_extracted: bool = None,
    brand_extracted: bool = None,
    amount_extracted: bool = None,
    date_extracted: bool = None,
    order_id_extracted: bool = None,
    line_items_extracted: bool = None,
    match_attempted: bool = False,
    match_success: bool = None,
    match_confidence: int = None,
    parse_duration_ms: int = None,
    llm_cost_cents: int = None,
    parsing_status: str = "unparseable",
    parsing_error: str = None,
) -> int:
    """Save parse statistics for a single message.

    Args:
        connection_id: Gmail connection ID (required)
        sync_job_id: Sync job ID (optional)
        message_id: Gmail message ID
        sender_domain: Email sender domain
        merchant_normalized: Normalized merchant name
        parse_method: Parse method used (vendor_amazon, schema_org, etc.)
        merchant_extracted: Whether merchant name was extracted
        brand_extracted: Whether brand was extracted
        amount_extracted: Whether amount was extracted
        date_extracted: Whether date was extracted
        order_id_extracted: Whether order ID was extracted
        line_items_extracted: Whether line items were extracted
        match_attempted: Whether transaction matching was attempted
        match_success: Whether matching succeeded
        match_confidence: Match confidence score (0-100)
        parse_duration_ms: Parse duration in milliseconds
        llm_cost_cents: LLM cost in cents (if LLM used)
        parsing_status: Status (parsed, unparseable, filtered, failed)
        parsing_error: Error message if parsing failed

    Returns:
        Statistics record ID
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO gmail_parse_statistics
                (connection_id, sync_job_id, message_id, sender_domain,
                 merchant_normalized, parse_method,
                 merchant_extracted, brand_extracted, amount_extracted,
                 date_extracted, order_id_extracted, line_items_extracted,
                 match_attempted, match_success, match_confidence,
                 parse_duration_ms, llm_cost_cents,
                 parsing_status, parsing_error)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """,
                (
                    connection_id,
                    sync_job_id,
                    message_id,
                    sender_domain,
                    merchant_normalized,
                    parse_method,
                    merchant_extracted,
                    brand_extracted,
                    amount_extracted,
                    date_extracted,
                    order_id_extracted,
                    line_items_extracted,
                    match_attempted,
                    match_success,
                    match_confidence,
                    parse_duration_ms,
                    llm_cost_cents,
                    parsing_status,
                    parsing_error,
                ),
            )
            stat_id = cursor.fetchone()[0]
            conn.commit()
            return stat_id


def update_gmail_sync_job_stats(sync_job_id: int, stats: dict) -> bool:
    """Update sync job with aggregated statistics.

    Args:
        sync_job_id: Sync job ID
        stats: Statistics dict with structure:
            {
                "by_parse_method": {"vendor_amazon": {"parsed": 45, "failed": 2}},
                "by_merchant": {"amazon.co.uk": {"parsed": 45, "failed": 2}},
                "datapoint_extraction": {
                    "merchant": {"attempted": 100, "success": 95}
                },
                "errors": {"api_error": 3, "parse_error": 5}
            }

    Returns:
        True if updated successfully
    """
    import json

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE gmail_sync_jobs
                SET stats = %s
                WHERE id = %s
            """,
            (json.dumps(stats), sync_job_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_gmail_error_summary(
    connection_id: int = None, sync_job_id: int = None, days: int = 7
) -> dict:
    """Get error summary for dashboard.

    Args:
        connection_id: Filter by connection ID (optional)
        sync_job_id: Filter by sync job ID (optional)
        days: Look back N days (default 7)

    Returns:
        Dictionary with error statistics:
        {
            "total_errors": 150,
            "by_stage": {"vendor_parse": 45, "fetch": 30, ...},
            "by_type": {"parse_error": 60, "timeout": 20, ...},
            "retryable_count": 50,
            "recent_errors": [...]
        }
    """
    from datetime import datetime, timedelta

    from psycopg2.extras import RealDictCursor

    cutoff = datetime.now() - timedelta(days=days)

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        # Build WHERE clause
        where_clauses = ["occurred_at >= %s"]
        params = [cutoff]

        if connection_id:
            where_clauses.append("connection_id = %s")
            params.append(connection_id)

        if sync_job_id:
            where_clauses.append("sync_job_id = %s")
            params.append(sync_job_id)

        where_sql = " AND ".join(where_clauses)

        # Get total count
        cursor.execute(
            f"""
                SELECT COUNT(*) as total
                FROM gmail_processing_errors
                WHERE {where_sql}
            """,
            params,
        )
        total = cursor.fetchone()["total"]

        # Get errors by stage
        cursor.execute(
            f"""
                SELECT error_stage, COUNT(*) as count
                FROM gmail_processing_errors
                WHERE {where_sql}
                GROUP BY error_stage
                ORDER BY count DESC
            """,
            params,
        )
        by_stage = {row["error_stage"]: row["count"] for row in cursor.fetchall()}

        # Get errors by type
        cursor.execute(
            f"""
                SELECT error_type, COUNT(*) as count
                FROM gmail_processing_errors
                WHERE {where_sql}
                GROUP BY error_type
                ORDER BY count DESC
            """,
            params,
        )
        by_type = {row["error_type"]: row["count"] for row in cursor.fetchall()}

        # Get retryable count
        cursor.execute(
            f"""
                SELECT COUNT(*) as count
                FROM gmail_processing_errors
                WHERE {where_sql} AND is_retryable = TRUE
            """,
            params,
        )
        retryable_count = cursor.fetchone()["count"]

        # Get recent errors
        cursor.execute(
            f"""
                SELECT id, error_stage, error_type, error_message,
                       message_id, occurred_at, is_retryable
                FROM gmail_processing_errors
                WHERE {where_sql}
                ORDER BY occurred_at DESC
                LIMIT 20
            """,
            params,
        )
        recent_errors = []
        for row in cursor.fetchall():
            error = dict(row)
            if error["occurred_at"]:
                error["occurred_at"] = error["occurred_at"].isoformat()
            recent_errors.append(error)

        return {
            "total_errors": total,
            "by_stage": by_stage,
            "by_type": by_type,
            "retryable_count": retryable_count,
            "recent_errors": recent_errors,
        }


def get_gmail_merchant_statistics(
    connection_id: int = None,
    merchant: str = None,
    parse_method: str = None,
    days: int = 30,
) -> list:
    """Get merchant parsing statistics.

    Args:
        connection_id: Filter by connection ID (optional)
        merchant: Filter by merchant normalized name (optional)
        parse_method: Filter by parse method (optional)
        days: Look back N days (default 30)

    Returns:
        List of merchant statistics dictionaries
    """
    from datetime import datetime, timedelta

    from psycopg2.extras import RealDictCursor

    cutoff = datetime.now() - timedelta(days=days)

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Build WHERE clause
            where_clauses = ["created_at >= %s"]
            params = [cutoff]

            if connection_id:
                where_clauses.append("connection_id = %s")
                params.append(connection_id)

            if merchant:
                where_clauses.append("merchant_normalized = %s")
                params.append(merchant)

            if parse_method:
                where_clauses.append("parse_method = %s")
                params.append(parse_method)

            where_sql = " AND ".join(where_clauses)

            # Aggregate statistics by merchant and parse method
            cursor.execute(
                f"""
                SELECT
                    merchant_normalized,
                    sender_domain,
                    parse_method,
                    COUNT(*) as total_attempts,
                    SUM(CASE WHEN parsing_status = 'parsed' THEN 1 ELSE 0 END) as parsed_count,
                    SUM(CASE WHEN parsing_status != 'parsed' THEN 1 ELSE 0 END) as failed_count,
                    SUM(CASE WHEN merchant_extracted THEN 1 ELSE 0 END) as merchant_extracted_count,
                    SUM(CASE WHEN brand_extracted THEN 1 ELSE 0 END) as brand_extracted_count,
                    SUM(CASE WHEN amount_extracted THEN 1 ELSE 0 END) as amount_extracted_count,
                    SUM(CASE WHEN date_extracted THEN 1 ELSE 0 END) as date_extracted_count,
                    SUM(CASE WHEN order_id_extracted THEN 1 ELSE 0 END) as order_id_extracted_count,
                    SUM(CASE WHEN line_items_extracted THEN 1 ELSE 0 END) as line_items_extracted_count,
                    SUM(CASE WHEN match_attempted THEN 1 ELSE 0 END) as match_attempted_count,
                    SUM(CASE WHEN match_success THEN 1 ELSE 0 END) as match_success_count,
                    AVG(match_confidence) as avg_match_confidence,
                    AVG(parse_duration_ms) as avg_parse_duration_ms,
                    SUM(COALESCE(llm_cost_cents, 0)) as total_llm_cost_cents
                FROM gmail_parse_statistics
                WHERE {where_sql}
                GROUP BY merchant_normalized, sender_domain, parse_method
                ORDER BY total_attempts DESC
            """,
                params,
            )

            stats = []
            for row in cursor.fetchall():
                stat = dict(row)
                # Calculate success rates
                total = stat["total_attempts"]
                if total > 0:
                    stat["success_rate"] = round(stat["parsed_count"] / total * 100, 1)
                    stat["merchant_extraction_rate"] = round(
                        stat["merchant_extracted_count"] / total * 100, 1
                    )
                    stat["amount_extraction_rate"] = round(
                        stat["amount_extracted_count"] / total * 100, 1
                    )
                stats.append(stat)

            return stats
