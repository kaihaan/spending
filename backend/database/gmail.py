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

import contextlib
import json
import re
from datetime import datetime

from sqlalchemy import case, func, or_, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from .base import get_session
from .models.category import NormalizedCategory, NormalizedSubcategory
from .models.enrichment import TransactionEnrichmentSource
from .models.gmail import (
    GmailConnection,
    GmailEmailContent,
    GmailMatch,
    GmailOAuthState,
    GmailParseStatistic,
    GmailReceipt,
    GmailSenderPattern,
    GmailSyncJob,
    MatchingJob,
    PdfAttachment,
)
from .models.truelayer import TrueLayerTransaction
from .models.user import User

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
    with get_session() as session:
        stmt = insert(GmailConnection).values(
            user_id=user_id,
            email_address=email_address,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            scopes=scopes,
            connection_status="active",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "email_address"],
            set_={
                "access_token": stmt.excluded.access_token,
                "refresh_token": stmt.excluded.refresh_token,
                "token_expires_at": stmt.excluded.token_expires_at,
                "scopes": stmt.excluded.scopes,
                "connection_status": "active",
                "error_count": 0,
                "last_error": None,
                "updated_at": func.now(),
            },
        ).returning(GmailConnection.id)

        result = session.execute(stmt)
        connection_id = result.scalar_one()
        session.commit()
        return connection_id


def get_gmail_connection(user_id: int) -> dict:
    """Get Gmail connection for a user."""
    with get_session() as session:
        connection = (
            session.query(GmailConnection)
            .filter(
                GmailConnection.user_id == user_id,
                GmailConnection.connection_status == "active",
            )
            .order_by(GmailConnection.created_at.desc())
            .first()
        )

        if not connection:
            return None

        return {
            "id": connection.id,
            "user_id": connection.user_id,
            "email_address": connection.email_address,
            "access_token": connection.access_token,
            "refresh_token": connection.refresh_token,
            "token_expires_at": connection.token_expires_at,
            "scopes": connection.scopes,
            "connection_status": connection.connection_status,
            "history_id": connection.history_id,
            "last_synced_at": connection.last_synced_at,
            "sync_from_date": connection.sync_from_date,
            "error_count": connection.error_count,
            "last_error": connection.last_error,
            "created_at": connection.created_at,
            "updated_at": connection.updated_at,
        }


def get_gmail_connection_by_id(connection_id: int) -> dict:
    """Get Gmail connection by ID."""
    with get_session() as session:
        connection = session.get(GmailConnection, connection_id)

        if not connection:
            return None

        return {
            "id": connection.id,
            "user_id": connection.user_id,
            "email_address": connection.email_address,
            "access_token": connection.access_token,
            "refresh_token": connection.refresh_token,
            "token_expires_at": connection.token_expires_at,
            "scopes": connection.scopes,
            "connection_status": connection.connection_status,
            "history_id": connection.history_id,
            "last_synced_at": connection.last_synced_at,
            "sync_from_date": connection.sync_from_date,
            "error_count": connection.error_count,
            "last_error": connection.last_error,
            "created_at": connection.created_at,
            "updated_at": connection.updated_at,
        }


def update_gmail_tokens(
    connection_id: int, access_token: str, refresh_token: str, token_expires_at: str
) -> bool:
    """Update Gmail tokens after refresh."""
    with get_session() as session:
        connection = session.get(GmailConnection, connection_id)

        if not connection:
            return False

        connection.access_token = access_token
        connection.refresh_token = refresh_token
        connection.token_expires_at = token_expires_at
        connection.connection_status = "active"
        connection.error_count = 0
        connection.updated_at = datetime.now()

        session.commit()
        return True


def update_gmail_connection_status(
    connection_id: int, status: str, error: str = None
) -> bool:
    """Update Gmail connection status and error info."""
    with get_session() as session:
        connection = session.get(GmailConnection, connection_id)

        if not connection:
            return False

        connection.connection_status = status
        connection.updated_at = datetime.now()

        if error:
            connection.error_count = connection.error_count + 1
            connection.last_error = error

        session.commit()
        return True


def update_gmail_history_id(connection_id: int, history_id: str) -> bool:
    """Update Gmail historyId for incremental sync."""
    with get_session() as session:
        connection = session.get(GmailConnection, connection_id)

        if not connection:
            return False

        connection.history_id = history_id
        connection.last_synced_at = datetime.now()
        connection.updated_at = datetime.now()

        session.commit()
        return True


def delete_gmail_connection(connection_id: int) -> bool:
    """Delete Gmail connection (cascades to receipts and matches)."""
    with get_session() as session:
        connection = session.get(GmailConnection, connection_id)

        if not connection:
            return False

        session.delete(connection)
        session.commit()
        return True


# Gmail OAuth State functions
def store_gmail_oauth_state(user_id: int, state: str, code_verifier: str) -> bool:
    """Store OAuth state for CSRF protection (10-minute expiration)."""
    with get_session() as session:
        stmt = insert(GmailOAuthState).values(
            user_id=user_id,
            state=state,
            code_verifier=code_verifier,
            expires_at=text("NOW() + INTERVAL '10 minutes'"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["state"],
            set_={
                "user_id": stmt.excluded.user_id,
                "code_verifier": stmt.excluded.code_verifier,
                "expires_at": stmt.excluded.expires_at,
            },
        )
        session.execute(stmt)
        session.commit()
        return True


def get_gmail_oauth_state(state: str) -> dict:
    """Get OAuth state by state parameter."""
    with get_session() as session:
        oauth_state = (
            session.query(GmailOAuthState)
            .filter(
                GmailOAuthState.state == state,
                GmailOAuthState.expires_at > func.now(),
            )
            .first()
        )

        if not oauth_state:
            return None

        return {
            "user_id": oauth_state.user_id,
            "state": oauth_state.state,
            "code_verifier": oauth_state.code_verifier,
            "expires_at": oauth_state.expires_at,
        }


def delete_gmail_oauth_state(state: str) -> bool:
    """Delete OAuth state after use."""
    with get_session() as session:
        result = (
            session.query(GmailOAuthState)
            .filter(GmailOAuthState.state == state)
            .delete()
        )
        session.commit()
        return result > 0


def cleanup_expired_gmail_oauth_states() -> int:
    """Clean up expired OAuth states."""
    with get_session() as session:
        result = (
            session.query(GmailOAuthState)
            .filter(GmailOAuthState.expires_at < func.now())
            .delete()
        )
        session.commit()
        return result


# Gmail Receipts functions
def save_gmail_receipt(connection_id: int, message_id: str, receipt_data: dict) -> int:
    """Save a parsed Gmail receipt."""
    with get_session() as session:
        stmt = insert(GmailReceipt).values(
            connection_id=connection_id,
            message_id=message_id,
            thread_id=receipt_data.get("thread_id"),
            sender_email=receipt_data.get("sender_email"),
            sender_name=receipt_data.get("sender_name"),
            subject=receipt_data.get("subject"),
            received_at=receipt_data.get("received_at"),
            merchant_name=receipt_data.get("merchant_name"),
            merchant_name_normalized=receipt_data.get("merchant_name_normalized"),
            merchant_domain=receipt_data.get("merchant_domain"),
            order_id=receipt_data.get("order_id"),
            total_amount=receipt_data.get("total_amount"),
            currency_code=receipt_data.get("currency_code", "GBP"),
            receipt_date=receipt_data.get("receipt_date"),
            line_items=json.dumps(receipt_data.get("line_items")),
            receipt_hash=receipt_data.get("receipt_hash"),
            parse_method=receipt_data.get("parse_method"),
            parse_confidence=receipt_data.get("parse_confidence"),
            raw_schema_data=json.dumps(receipt_data.get("raw_schema_data")),
            llm_cost_cents=receipt_data.get("llm_cost_cents"),
            parsing_status=receipt_data.get("parsing_status", "parsed"),
            pdf_processing_status=receipt_data.get("pdf_processing_status", "none"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id"],
            set_={
                "merchant_name": stmt.excluded.merchant_name,
                "merchant_name_normalized": stmt.excluded.merchant_name_normalized,
                "total_amount": stmt.excluded.total_amount,
                "parse_method": stmt.excluded.parse_method,
                "parse_confidence": stmt.excluded.parse_confidence,
                "parsing_status": stmt.excluded.parsing_status,
                "pdf_processing_status": stmt.excluded.pdf_processing_status,
                "updated_at": func.now(),
            },
        ).returning(GmailReceipt.id)

        result = session.execute(stmt)
        receipt_id = result.scalar_one()
        session.commit()
        return receipt_id


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

    # Prepare data list
    data = []
    for connection_id, message_id, receipt_data in receipts:
        data.append(
            {
                "connection_id": connection_id,
                "message_id": message_id,
                "thread_id": receipt_data.get("thread_id"),
                "sender_email": receipt_data.get("sender_email"),
                "sender_name": receipt_data.get("sender_name"),
                "subject": receipt_data.get("subject"),
                "received_at": receipt_data.get("received_at"),
                "merchant_name": receipt_data.get("merchant_name"),
                "merchant_name_normalized": receipt_data.get(
                    "merchant_name_normalized"
                ),
                "merchant_domain": receipt_data.get("merchant_domain"),
                "order_id": receipt_data.get("order_id"),
                "total_amount": receipt_data.get("total_amount"),
                "currency_code": receipt_data.get("currency_code", "GBP"),
                "receipt_date": receipt_data.get("receipt_date"),
                "line_items": json.dumps(receipt_data.get("line_items")),
                "receipt_hash": receipt_data.get("receipt_hash"),
                "parse_method": receipt_data.get("parse_method"),
                "parse_confidence": receipt_data.get("parse_confidence"),
                "raw_schema_data": json.dumps(receipt_data.get("raw_schema_data")),
                "llm_cost_cents": receipt_data.get("llm_cost_cents"),
                "parsing_status": receipt_data.get("parsing_status", "parsed"),
                "pdf_processing_status": receipt_data.get(
                    "pdf_processing_status", "none"
                ),
            }
        )

    with get_session() as session:
        stmt = insert(GmailReceipt).values(data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id"],
            set_={
                "merchant_name": stmt.excluded.merchant_name,
                "merchant_name_normalized": stmt.excluded.merchant_name_normalized,
                "total_amount": stmt.excluded.total_amount,
                "parse_method": stmt.excluded.parse_method,
                "parse_confidence": stmt.excluded.parse_confidence,
                "parsing_status": stmt.excluded.parsing_status,
                "pdf_processing_status": stmt.excluded.pdf_processing_status,
                "updated_at": func.now(),
            },
        ).returning(GmailReceipt.id, GmailReceipt.message_id)

        results = session.execute(stmt).fetchall()
        session.commit()

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
    with get_session() as session:
        stmt = insert(GmailEmailContent).values(
            message_id=message.get("message_id"),
            thread_id=message.get("thread_id"),
            subject=message.get("subject"),
            from_header=message.get("from"),
            to_header=message.get("to"),
            date_header=message.get("date"),
            list_unsubscribe=message.get("list_unsubscribe"),
            x_mailer=message.get("x_mailer"),
            body_html=message.get("body_html"),
            body_text=message.get("body_text"),
            snippet=message.get("snippet"),
            attachments=json.dumps(message.get("attachments", [])),
            size_estimate=message.get("size_estimate"),
            received_at=message.get("received_at"),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id"],
            set_={
                "body_html": stmt.excluded.body_html,
                "body_text": stmt.excluded.body_text,
                "attachments": stmt.excluded.attachments,
                "fetched_at": func.now(),
            },
        ).returning(GmailEmailContent.id)

        result = session.execute(stmt)
        content_id = result.scalar_one()
        session.commit()
        return content_id


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

    # Prepare data list
    data = []
    for msg in messages:
        data.append(
            {
                "message_id": msg.get("message_id"),
                "thread_id": msg.get("thread_id"),
                "subject": msg.get("subject"),
                "from_header": msg.get("from"),
                "to_header": msg.get("to"),
                "date_header": msg.get("date"),
                "list_unsubscribe": msg.get("list_unsubscribe"),
                "x_mailer": msg.get("x_mailer"),
                "body_html": msg.get("body_html"),
                "body_text": msg.get("body_text"),
                "snippet": msg.get("snippet"),
                "attachments": json.dumps(msg.get("attachments", [])),
                "size_estimate": msg.get("size_estimate"),
                "received_at": msg.get("received_at"),
            }
        )

    with get_session() as session:
        stmt = insert(GmailEmailContent).values(data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["message_id"],
            set_={
                "body_html": stmt.excluded.body_html,
                "body_text": stmt.excluded.body_text,
                "attachments": stmt.excluded.attachments,
                "fetched_at": func.now(),
            },
        )

        result = session.execute(stmt)
        session.commit()
        return {"inserted": result.rowcount, "failed": []}


def get_gmail_email_content(message_id: str) -> dict:
    """Get stored email content by message_id for parser development."""
    with get_session() as session:
        content = (
            session.query(GmailEmailContent)
            .filter(GmailEmailContent.message_id == message_id)
            .first()
        )

        if not content:
            return None

        return {
            "id": content.id,
            "message_id": content.message_id,
            "thread_id": content.thread_id,
            "subject": content.subject,
            "from_header": content.from_header,
            "to_header": content.to_header,
            "date_header": content.date_header,
            "list_unsubscribe": content.list_unsubscribe,
            "x_mailer": content.x_mailer,
            "body_html": content.body_html,
            "body_text": content.body_text,
            "snippet": content.snippet,
            "attachments": content.attachments,
            "size_estimate": content.size_estimate,
            "received_at": content.received_at,
            "fetched_at": content.fetched_at,
            "created_at": content.created_at,
        }


def get_receipt_with_email_content(receipt_id: int) -> dict:
    """
    Get receipt with full email content for parser development.
    Joins gmail_receipts with gmail_email_content.
    """
    with get_session() as session:
        result = (
            session.query(
                GmailReceipt,
                GmailEmailContent.body_html,
                GmailEmailContent.body_text,
                GmailEmailContent.from_header,
                GmailEmailContent.to_header,
                GmailEmailContent.date_header,
                GmailEmailContent.attachments.label("email_attachments"),
            )
            .outerjoin(
                GmailEmailContent,
                GmailReceipt.message_id == GmailEmailContent.message_id,
            )
            .filter(
                GmailReceipt.id == receipt_id,
                GmailReceipt.deleted_at.is_(None),
            )
            .first()
        )

        if not result:
            return None

        receipt = result[0]
        return {
            **{col: getattr(receipt, col) for col in receipt.__table__.columns},
            "body_html": result[1],
            "body_text": result[2],
            "from_header": result[3],
            "to_header": result[4],
            "date_header": result[5],
            "email_attachments": result[6],
        }


def get_receipts_by_domain_with_content(domain: str, limit: int = 10) -> list:
    """
    Get receipts for a domain with full email content.
    Useful for developing vendor parsers.
    """
    with get_session() as session:
        results = (
            session.query(
                GmailReceipt.id,
                GmailReceipt.message_id,
                GmailReceipt.subject,
                GmailReceipt.merchant_name,
                GmailReceipt.merchant_domain,
                GmailReceipt.total_amount,
                GmailReceipt.line_items,
                GmailReceipt.parse_method,
                GmailReceipt.parsing_status,
                GmailEmailContent.body_html,
                GmailEmailContent.body_text,
            )
            .outerjoin(
                GmailEmailContent,
                GmailReceipt.message_id == GmailEmailContent.message_id,
            )
            .filter(
                GmailReceipt.merchant_domain.like(f"%{domain}%"),
                GmailReceipt.deleted_at.is_(None),
            )
            .order_by(GmailReceipt.received_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": r[0],
                "message_id": r[1],
                "subject": r[2],
                "merchant_name": r[3],
                "merchant_domain": r[4],
                "total_amount": r[5],
                "line_items": r[6],
                "parse_method": r[7],
                "parsing_status": r[8],
                "body_html": r[9],
                "body_text": r[10],
            }
            for r in results
        ]


def get_gmail_receipts(
    connection_id: int, limit: int = 50, offset: int = 0, status: str = None
) -> list:
    """Get Gmail receipts for a connection."""
    with get_session() as session:
        query = session.query(GmailReceipt).filter(
            GmailReceipt.connection_id == connection_id,
            GmailReceipt.deleted_at.is_(None),
        )

        if status:
            query = query.filter(GmailReceipt.parsing_status == status)

        receipts = (
            query.order_by(GmailReceipt.received_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        return [
            {
                "id": r.id,
                "connection_id": r.connection_id,
                "message_id": r.message_id,
                "sender_email": r.sender_email,
                "sender_name": r.sender_name,
                "subject": r.subject,
                "received_at": r.received_at,
                "merchant_name": r.merchant_name,
                "order_id": r.order_id,
                "total_amount": r.total_amount,
                "currency_code": r.currency_code,
                "receipt_date": r.receipt_date,
                "line_items": r.line_items,
                "parse_method": r.parse_method,
                "parse_confidence": r.parse_confidence,
                "parsing_status": r.parsing_status,
                "created_at": r.created_at,
            }
            for r in receipts
        ]


def get_gmail_receipt_by_id(receipt_id: int) -> dict:
    """Get a single Gmail receipt by ID with transaction match details."""
    with get_session() as session:
        result = (
            session.query(
                GmailReceipt,
                GmailConnection.user_id,
                GmailConnection.email_address,
                GmailMatch.id.label("match_id"),
                GmailMatch.match_confidence,
                TrueLayerTransaction.id.label("transaction_id"),
                TrueLayerTransaction.description.label("transaction_description"),
                TrueLayerTransaction.amount.label("transaction_amount"),
            )
            .join(GmailConnection, GmailReceipt.connection_id == GmailConnection.id)
            .outerjoin(GmailMatch, GmailReceipt.id == GmailMatch.gmail_receipt_id)
            .outerjoin(
                TrueLayerTransaction,
                GmailMatch.truelayer_transaction_id == TrueLayerTransaction.id,
            )
            .filter(
                GmailReceipt.id == receipt_id,
                GmailReceipt.deleted_at.is_(None),
            )
            .first()
        )

        if not result:
            return None

        receipt_obj = result[0]
        receipt = {
            col: getattr(receipt_obj, col) for col in receipt_obj.__table__.columns
        }
        receipt.update(
            {
                "user_id": result[1],
                "email_address": result[2],
                "match_id": result[3],
                "match_confidence": result[4],
                "transaction_id": result[5],
                "transaction_description": result[6],
                "transaction_amount": result[7],
            }
        )

        # Ensure line_items is always a list
        if isinstance(receipt.get("line_items"), str):
            try:
                receipt["line_items"] = json.loads(receipt["line_items"])
            except Exception:
                receipt["line_items"] = []

        if receipt.get("line_items") is None:
            receipt["line_items"] = []

        return receipt


def get_gmail_receipt_by_message_id(message_id: str) -> dict:
    """Get a Gmail receipt by its Gmail message ID (for deduplication)."""
    with get_session() as session:
        receipt = (
            session.query(GmailReceipt)
            .filter(
                GmailReceipt.message_id == message_id,
                GmailReceipt.deleted_at.is_(None),
            )
            .first()
        )

        if not receipt:
            return None

        return {
            "id": receipt.id,
            "message_id": receipt.message_id,
            "parsing_status": receipt.parsing_status,
        }


def get_unmatched_gmail_receipts(user_id: int, limit: int = 100) -> list:
    """Get receipts not yet matched to transactions."""
    with get_session() as session:
        receipts = (
            session.query(GmailReceipt)
            .join(GmailConnection, GmailReceipt.connection_id == GmailConnection.id)
            .outerjoin(GmailMatch, GmailReceipt.id == GmailMatch.gmail_receipt_id)
            .filter(
                GmailConnection.user_id == user_id,
                GmailReceipt.parsing_status == "parsed",
                GmailReceipt.deleted_at.is_(None),
                GmailMatch.id.is_(None),
            )
            .order_by(GmailReceipt.receipt_date.desc())
            .limit(limit)
            .all()
        )

        return [{col: getattr(r, col) for col in r.__table__.columns} for r in receipts]


def soft_delete_gmail_receipt(receipt_id: int) -> bool:
    """Soft delete a Gmail receipt (GDPR compliance)."""
    with get_session() as session:
        receipt = session.get(GmailReceipt, receipt_id)

        if not receipt:
            return False

        receipt.deleted_at = datetime.now()
        receipt.updated_at = datetime.now()

        session.commit()
        return True


# Gmail Match functions
def save_gmail_match(
    truelayer_transaction_id: int,
    gmail_receipt_id: int,
    confidence: int,
    match_method: str = None,
    match_type: str = "standard",
    currency_converted: bool = False,
    conversion_rate: float = None,
) -> int:
    """Save a match between a TrueLayer transaction and Gmail receipt."""
    with get_session() as session:
        # Insert/update match record
        stmt = insert(GmailMatch).values(
            truelayer_transaction_id=truelayer_transaction_id,
            gmail_receipt_id=gmail_receipt_id,
            match_confidence=confidence,
            match_method=match_method,
            match_type=match_type,
            currency_converted=currency_converted,
            conversion_rate=conversion_rate,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["truelayer_transaction_id", "gmail_receipt_id"],
            set_={
                "match_confidence": stmt.excluded.match_confidence,
                "match_method": stmt.excluded.match_method,
                "currency_converted": stmt.excluded.currency_converted,
                "conversion_rate": stmt.excluded.conversion_rate,
                "matched_at": func.now(),
            },
        ).returning(GmailMatch.id)

        result = session.execute(stmt)
        match_id = result.scalar_one()
        session.commit()

        # Get Gmail receipt details for enrichment source
        receipt = session.get(GmailReceipt, gmail_receipt_id)

        if receipt:
            merchant_name = receipt.merchant_name
            order_id = receipt.order_id
            line_items = json.loads(receipt.line_items) if receipt.line_items else None

            # Build description from merchant + line items
            description_parts = []
            if merchant_name:
                description_parts.append(merchant_name)

            # Add line item names (more valuable than just order ID)
            if line_items and isinstance(line_items, list) and len(line_items) > 0:
                item_names = [
                    item.get("name", "") for item in line_items if item.get("name")
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
            has_higher_priority = (
                session.query(TransactionEnrichmentSource)
                .filter(
                    TransactionEnrichmentSource.truelayer_transaction_id
                    == truelayer_transaction_id,
                    TransactionEnrichmentSource.source_type.in_(
                        ["amazon", "amazon_business", "apple"]
                    ),
                    TransactionEnrichmentSource.is_primary.is_(True),
                )
                .first()
            ) is not None

            # Add Gmail enrichment source (primary only if no Amazon/Apple)
            enrichment_stmt = insert(TransactionEnrichmentSource).values(
                truelayer_transaction_id=truelayer_transaction_id,
                source_type="gmail",
                source_id=gmail_receipt_id,
                description=description,
                order_id=order_id,
                line_items=json.dumps(line_items) if line_items else None,
                match_confidence=confidence,
                match_method=match_method,
                is_primary=not has_higher_priority,
            )
            enrichment_stmt = enrichment_stmt.on_conflict_do_update(
                index_elements=["truelayer_transaction_id", "source_type", "source_id"],
                set_={
                    "description": enrichment_stmt.excluded.description,
                    "order_id": enrichment_stmt.excluded.order_id,
                    "line_items": enrichment_stmt.excluded.line_items,
                    "match_confidence": enrichment_stmt.excluded.match_confidence,
                    "match_method": enrichment_stmt.excluded.match_method,
                    "updated_at": func.now(),
                },
            )
            session.execute(enrichment_stmt)
            session.commit()

        # Update pre_enrichment_status
        session.query(TrueLayerTransaction).filter(
            TrueLayerTransaction.id == truelayer_transaction_id,
            or_(
                TrueLayerTransaction.pre_enrichment_status.is_(None),
                TrueLayerTransaction.pre_enrichment_status == "None",
            ),
        ).update(
            {"pre_enrichment_status": "Gmail"},
            synchronize_session=False,
        )
        session.commit()

        return match_id


def get_gmail_matches_for_transaction(transaction_id: int) -> list:
    """Get all Gmail receipt matches for a specific transaction."""
    with get_session() as session:
        results = (
            session.query(
                GmailMatch.id.label("match_id"),
                GmailMatch.match_confidence,
                GmailMatch.match_method,
                GmailMatch.user_confirmed,
                GmailMatch.matched_at,
                GmailReceipt.id.label("gmail_receipt_id"),
                GmailReceipt.merchant_name,
                GmailReceipt.order_id,
                GmailReceipt.total_amount,
                GmailReceipt.receipt_date,
                GmailReceipt.line_items,
                GmailReceipt.parse_method,
                GmailReceipt.parse_confidence,
            )
            .join(GmailReceipt, GmailMatch.gmail_receipt_id == GmailReceipt.id)
            .filter(GmailMatch.truelayer_transaction_id == transaction_id)
            .order_by(GmailMatch.match_confidence.desc())
            .all()
        )

        return [
            {
                "match_id": r[0],
                "match_confidence": r[1],
                "match_method": r[2],
                "user_confirmed": r[3],
                "matched_at": r[4],
                "gmail_receipt_id": r[5],
                "merchant_name": r[6],
                "order_id": r[7],
                "total_amount": r[8],
                "receipt_date": r[9],
                "line_items": r[10],
                "parse_method": r[11],
                "parse_confidence": r[12],
            }
            for r in results
        ]


def get_amazon_order_for_transaction(transaction_id: int) -> dict:
    """Get Amazon order matched to a transaction."""
    with get_session() as session:
        from .models.amazon import AmazonOrder, TrueLayerAmazonTransactionMatch

        result = (
            session.query(
                AmazonOrder.id,
                AmazonOrder.order_id,
                AmazonOrder.order_date,
                AmazonOrder.product_names,
                AmazonOrder.total_owed.label("total_amount"),
                AmazonOrder.website,
                TrueLayerAmazonTransactionMatch.match_confidence,
            )
            .join(
                TrueLayerAmazonTransactionMatch,
                TrueLayerAmazonTransactionMatch.amazon_order_id == AmazonOrder.id,
            )
            .filter(
                TrueLayerAmazonTransactionMatch.truelayer_transaction_id
                == transaction_id
            )
            .first()
        )

        if not result:
            return None

        return {
            "id": result[0],
            "order_id": result[1],
            "order_date": result[2],
            "product_names": result[3],
            "total_amount": result[4],
            "website": result[5],
            "match_confidence": result[6],
        }


def get_apple_transaction_for_match(transaction_id: int) -> dict:
    """Get Apple transaction matched to a TrueLayer transaction."""
    with get_session() as session:
        from .models.apple import AppleTransaction, TrueLayerAppleTransactionMatch

        result = (
            session.query(
                AppleTransaction.id,
                AppleTransaction.order_id,
                AppleTransaction.order_date.label("transaction_date"),
                AppleTransaction.app_names,
                AppleTransaction.total_amount,
                TrueLayerAppleTransactionMatch.match_confidence,
            )
            .join(
                TrueLayerAppleTransactionMatch,
                TrueLayerAppleTransactionMatch.apple_transaction_id
                == AppleTransaction.id,
            )
            .filter(
                TrueLayerAppleTransactionMatch.truelayer_transaction_id
                == transaction_id
            )
            .first()
        )

        if not result:
            return None

        return {
            "id": result[0],
            "order_id": result[1],
            "transaction_date": result[2],
            "app_names": result[3],
            "total_amount": result[4],
            "match_confidence": result[5],
        }


def get_gmail_matches(user_id: int, limit: int = 50, offset: int = 0) -> list:
    """Get Gmail matches for a user with receipt and transaction details."""
    with get_session() as session:
        results = (
            session.query(
                GmailMatch.id,
                GmailMatch.match_confidence,
                GmailMatch.match_method,
                GmailMatch.match_type,
                GmailMatch.user_confirmed,
                GmailMatch.matched_at,
                GmailReceipt.id.label("receipt_id"),
                GmailReceipt.merchant_name,
                GmailReceipt.total_amount.label("receipt_amount"),
                GmailReceipt.receipt_date,
                GmailReceipt.order_id,
                TrueLayerTransaction.id.label("transaction_id"),
                TrueLayerTransaction.description,
                TrueLayerTransaction.amount.label("transaction_amount"),
                TrueLayerTransaction.timestamp.label("transaction_date"),
            )
            .join(GmailReceipt, GmailMatch.gmail_receipt_id == GmailReceipt.id)
            .join(
                TrueLayerTransaction,
                GmailMatch.truelayer_transaction_id == TrueLayerTransaction.id,
            )
            .join(GmailConnection, GmailReceipt.connection_id == GmailConnection.id)
            .filter(GmailConnection.user_id == user_id)
            .order_by(GmailMatch.matched_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        return [
            {
                "id": r[0],
                "match_confidence": r[1],
                "match_method": r[2],
                "match_type": r[3],
                "user_confirmed": r[4],
                "matched_at": r[5],
                "receipt_id": r[6],
                "merchant_name": r[7],
                "receipt_amount": r[8],
                "receipt_date": r[9],
                "order_id": r[10],
                "transaction_id": r[11],
                "description": r[12],
                "transaction_amount": r[13],
                "transaction_date": r[14],
            }
            for r in results
        ]


def confirm_gmail_match(match_id: int) -> bool:
    """Mark a match as user-confirmed."""
    with get_session() as session:
        match = session.get(GmailMatch, match_id)

        if not match:
            return False

        match.user_confirmed = True
        session.commit()
        return True


def delete_gmail_match(match_id: int) -> bool:
    """Delete a Gmail match."""
    with get_session() as session:
        match = session.get(GmailMatch, match_id)

        if not match:
            return False

        gmail_receipt_id = match.gmail_receipt_id

        session.delete(match)
        session.commit()

        # Reset receipt status to parsed
        receipt = session.get(GmailReceipt, gmail_receipt_id)
        if receipt:
            receipt.parsing_status = "parsed"
            receipt.updated_at = datetime.now()
            session.commit()

        return True


# Gmail Sync Job functions
def create_gmail_sync_job(connection_id: int, job_type: str = "full") -> int:
    """Create a new sync job."""
    with get_session() as session:
        stmt = (
            insert(GmailSyncJob)
            .values(
                connection_id=connection_id,
                job_type=job_type,
                status="queued",
            )
            .returning(GmailSyncJob.id)
        )

        result = session.execute(stmt)
        job_id = result.scalar_one()
        session.commit()
        return job_id


def update_gmail_sync_job_progress(
    job_id: int, total: int, processed: int, parsed: int, failed: int
) -> bool:
    """Update sync job progress."""
    with get_session() as session:
        job = session.get(GmailSyncJob, job_id)

        if not job:
            return False

        job.total_messages = total
        job.processed_messages = processed
        job.parsed_receipts = parsed
        job.failed_messages = failed
        job.status = "running"
        if job.started_at is None:
            job.started_at = datetime.now()

        session.commit()
        return True


def update_gmail_sync_job_dates(job_id: int, from_date: str, to_date: str) -> bool:
    """Update sync job date range."""
    with get_session() as session:
        job = session.get(GmailSyncJob, job_id)

        if not job:
            return False

        job.sync_from_date = from_date
        job.sync_to_date = to_date

        session.commit()
        return True


def complete_gmail_sync_job(
    job_id: int, status: str = "completed", error: str = None
) -> bool:
    """Mark sync job as completed or failed."""
    with get_session() as session:
        job = session.get(GmailSyncJob, job_id)

        if not job:
            return False

        job.status = status
        job.error_message = error
        job.completed_at = datetime.now()

        session.commit()
        return True


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
    with get_session() as session:
        # Use raw SQL for interval comparisons
        result = session.execute(
            text("""
                UPDATE gmail_sync_jobs
                SET status = 'failed',
                    error_message = 'Job timed out - no progress detected',
                    completed_at = NOW()
                WHERE (
                    (status = 'queued' AND created_at < NOW() - INTERVAL ':queued_timeout minutes')
                    OR (status = 'running' AND
                        COALESCE(started_at, created_at) < NOW() - INTERVAL ':running_timeout minutes')
                )
            """),
            {
                "queued_timeout": queued_timeout_minutes,
                "running_timeout": running_timeout_minutes,
            },
        )
        session.commit()
        return result.rowcount


def get_gmail_sync_job(job_id: int) -> dict:
    """Get sync job status with progress details including LLM cost."""
    with get_session() as session:
        job = session.get(GmailSyncJob, job_id)

        if not job:
            return None

        job_dict = {
            "id": job.id,
            "connection_id": job.connection_id,
            "status": job.status,
            "job_type": job.job_type,
            "total_messages": job.total_messages,
            "processed_messages": job.processed_messages,
            "parsed_receipts": job.parsed_receipts,
            "failed_messages": job.failed_messages,
            "sync_from_date": job.sync_from_date,
            "sync_to_date": job.sync_to_date,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
        }

        # Calculate progress percentage
        total = job_dict.get("total_messages", 0) or 0
        processed = job_dict.get("processed_messages", 0) or 0
        job_dict["progress_percentage"] = round(
            (processed / total * 100) if total > 0 else 0
        )

        # Get LLM cost for receipts processed during this job
        if job.started_at:
            llm_cost = (
                session.query(func.coalesce(func.sum(GmailReceipt.llm_cost_cents), 0))
                .filter(
                    GmailReceipt.connection_id == job.connection_id,
                    GmailReceipt.created_at >= job.started_at,
                    GmailReceipt.created_at <= (job.completed_at or datetime.now()),
                    GmailReceipt.llm_cost_cents.is_not(None),
                )
                .scalar()
            ) or 0
            job_dict["llm_cost_cents"] = llm_cost
        else:
            job_dict["llm_cost_cents"] = 0

        return job_dict


def get_latest_gmail_sync_job(connection_id: int) -> dict:
    """Get the latest sync job for a connection."""
    with get_session() as session:
        job = (
            session.query(GmailSyncJob)
            .filter(GmailSyncJob.connection_id == connection_id)
            .order_by(GmailSyncJob.created_at.desc())
            .first()
        )

        if not job:
            return None

        return {
            "id": job.id,
            "connection_id": job.connection_id,
            "status": job.status,
            "job_type": job.job_type,
            "total_messages": job.total_messages,
            "processed_messages": job.processed_messages,
            "parsed_receipts": job.parsed_receipts,
            "failed_messages": job.failed_messages,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
        }


def get_latest_active_gmail_sync_job(user_id: int) -> dict:
    """Get the latest active (queued/running) Gmail sync job for a user."""
    with get_session() as session:
        job = (
            session.query(GmailSyncJob)
            .join(GmailConnection, GmailSyncJob.connection_id == GmailConnection.id)
            .filter(
                GmailConnection.user_id == user_id,
                GmailSyncJob.status.in_(["queued", "running"]),
            )
            .order_by(GmailSyncJob.created_at.desc())
            .first()
        )

        if not job:
            return None

        job_dict = {
            "id": job.id,
            "connection_id": job.connection_id,
            "status": job.status,
            "job_type": job.job_type,
            "total_messages": job.total_messages,
            "processed_messages": job.processed_messages,
            "parsed_receipts": job.parsed_receipts,
            "failed_messages": job.failed_messages,
            "sync_from_date": job.sync_from_date,
            "sync_to_date": job.sync_to_date,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
        }

        # Calculate progress percentage
        total = job_dict.get("total_messages", 0) or 0
        processed = job_dict.get("processed_messages", 0) or 0
        job_dict["progress_percentage"] = round(
            (processed / total * 100) if total > 0 else 0
        )

        return job_dict


def get_gmail_statistics(user_id: int) -> dict:
    """Get Gmail integration statistics for a user."""
    from sqlalchemy import distinct

    with get_session() as session:
        result = (
            session.query(
                func.sum(case((GmailReceipt.deleted_at.is_(None), 1), else_=0)).label(
                    "total_receipts"
                ),
                func.sum(
                    case(
                        (
                            (GmailReceipt.parsing_status == "parsed")
                            & (GmailReceipt.deleted_at.is_(None)),
                            1,
                        ),
                        else_=0,
                    )
                ).label("parsed_receipts"),
                func.sum(
                    case(
                        (
                            (GmailReceipt.parsing_status == "pending")
                            & (GmailReceipt.deleted_at.is_(None)),
                            1,
                        ),
                        else_=0,
                    )
                ).label("pending_receipts"),
                func.sum(
                    case(
                        (
                            (GmailReceipt.parsing_status == "failed")
                            & (GmailReceipt.deleted_at.is_(None)),
                            1,
                        ),
                        else_=0,
                    )
                ).label("failed_receipts"),
                func.count(distinct(GmailMatch.gmail_receipt_id)).label(
                    "matched_receipts"
                ),
                func.min(GmailReceipt.receipt_date).label("min_receipt_date"),
                func.max(GmailReceipt.receipt_date).label("max_receipt_date"),
                func.sum(GmailReceipt.llm_cost_cents).label("total_llm_cost_cents"),
            )
            .select_from(GmailConnection)
            .outerjoin(GmailReceipt, GmailConnection.id == GmailReceipt.connection_id)
            .outerjoin(GmailMatch, GmailReceipt.id == GmailMatch.gmail_receipt_id)
            .filter(
                GmailConnection.user_id == user_id,
                GmailConnection.connection_status == "active",
            )
            .one_or_none()
        )

        if result:
            return {
                "total_receipts": int(result.total_receipts or 0),
                "parsed_receipts": int(result.parsed_receipts or 0),
                "pending_receipts": int(result.pending_receipts or 0),
                "failed_receipts": int(result.failed_receipts or 0),
                "matched_receipts": int(result.matched_receipts or 0),
                "min_receipt_date": result.min_receipt_date,
                "max_receipt_date": result.max_receipt_date,
                "total_llm_cost_cents": int(result.total_llm_cost_cents or 0),
            }

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
    from datetime import timedelta

    from .models.amazon import AmazonOrder
    from .models.apple import AppleTransaction

    with get_session() as session:
        # Get max bank transaction date
        bank_result = session.query(
            func.max(func.cast(TrueLayerTransaction.timestamp, text("date"))).label(
                "max_date"
            ),
            func.min(func.cast(TrueLayerTransaction.timestamp, text("date"))).label(
                "min_date"
            ),
            func.count().label("count"),
        ).one_or_none()

        bank_max = bank_result.max_date if bank_result else None
        bank_min = bank_result.min_date if bank_result else None
        bank_count = int(bank_result.count or 0) if bank_result else 0

        # Get max Amazon order date
        amazon_result = session.query(
            func.max(AmazonOrder.order_date).label("max_date"),
            func.min(AmazonOrder.order_date).label("min_date"),
            func.count().label("count"),
        ).one_or_none()

        amazon_max = amazon_result.max_date if amazon_result else None
        amazon_min = amazon_result.min_date if amazon_result else None
        amazon_count = int(amazon_result.count or 0) if amazon_result else 0

        # Get max Apple transaction date
        apple_result = session.query(
            func.max(AppleTransaction.order_date).label("max_date"),
            func.min(AppleTransaction.order_date).label("min_date"),
            func.count().label("count"),
        ).one_or_none()

        apple_max = apple_result.max_date if apple_result else None
        apple_min = apple_result.min_date if apple_result else None
        apple_count = int(apple_result.count or 0) if apple_result else 0

        # Get max Gmail receipt date
        gmail_result = (
            session.query(
                func.max(GmailReceipt.receipt_date).label("max_date"),
                func.min(GmailReceipt.receipt_date).label("min_date"),
                func.count().label("count"),
            )
            .join(GmailConnection, GmailReceipt.connection_id == GmailConnection.id)
            .filter(
                GmailConnection.user_id == user_id,
                GmailReceipt.deleted_at.is_(None),
            )
            .one_or_none()
        )

        gmail_max = gmail_result.max_date if gmail_result else None
        gmail_min = gmail_result.min_date if gmail_result else None
        gmail_count = int(gmail_result.count or 0) if gmail_result else 0

        # Determine which sources are stale (> 7 days behind bank data)
        stale_sources = []
        stale_threshold_days = 7

        if bank_max:
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
    with get_session() as session:
        pattern = (
            session.query(GmailSenderPattern)
            .filter(
                GmailSenderPattern.sender_domain == sender_domain,
                GmailSenderPattern.is_active.is_(True),
            )
            .first()
        )

        # Update usage count if found
        if pattern:
            pattern.usage_count = pattern.usage_count + 1
            pattern.last_used_at = datetime.now()
            session.commit()

            return {
                "merchant_name": pattern.merchant_name,
                "normalized_name": pattern.normalized_name,
                "parse_type": pattern.parse_type,
                "pattern_config": pattern.pattern_config,
                "date_tolerance_days": pattern.date_tolerance_days,
            }

        return None


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
    with get_session() as session:
        receipt = session.get(GmailReceipt, receipt_id)

        if not receipt:
            return False

        receipt.merchant_name = merchant_name
        receipt.merchant_name_normalized = merchant_name_normalized
        receipt.order_id = order_id
        receipt.total_amount = total_amount
        receipt.currency_code = currency_code
        receipt.receipt_date = receipt_date
        receipt.line_items = json.dumps(line_items) if line_items else None
        receipt.receipt_hash = receipt_hash
        receipt.parse_method = parse_method
        receipt.parse_confidence = parse_confidence
        receipt.parsing_status = parsing_status
        if llm_cost_cents is not None:
            receipt.llm_cost_cents = llm_cost_cents
        receipt.updated_at = datetime.now()

        session.commit()
        return True


def update_gmail_receipt_status(
    receipt_id: int, parsing_status: str, parsing_error: str = None
) -> bool:
    """Update receipt parsing status."""
    with get_session() as session:
        receipt = session.get(GmailReceipt, receipt_id)

        if not receipt:
            return False

        receipt.parsing_status = parsing_status
        receipt.parsing_error = parsing_error
        receipt.retry_count = receipt.retry_count + 1
        receipt.updated_at = datetime.now()

        session.commit()
        return True


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
    with get_session() as session:
        receipt = session.get(GmailReceipt, receipt_id)
        if not receipt:
            return False

        receipt.pdf_processing_status = pdf_status
        if error:
            receipt.pdf_retry_count = GmailReceipt.pdf_retry_count + 1
            receipt.pdf_last_error = error

        session.commit()
        return True


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

    with get_session() as session:
        receipt = session.get(GmailReceipt, receipt_id)
        if not receipt:
            return False

        # Property-based updates for fields present in pdf_data
        if "merchant_name" in pdf_data and pdf_data["merchant_name"]:
            receipt.merchant_name = pdf_data["merchant_name"]
            receipt.merchant_name_normalized = pdf_data["merchant_name"].lower()

        if "total_amount" in pdf_data and pdf_data["total_amount"] is not None:
            receipt.total_amount = float(pdf_data["total_amount"])

        if "currency_code" in pdf_data and pdf_data["currency_code"]:
            receipt.currency_code = pdf_data["currency_code"]

        if "receipt_date" in pdf_data and pdf_data["receipt_date"]:
            receipt.receipt_date = pdf_data["receipt_date"]

        if "order_id" in pdf_data and pdf_data["order_id"]:
            receipt.order_id = pdf_data["order_id"]

        if "line_items" in pdf_data and pdf_data["line_items"]:
            receipt.line_items = pdf_data["line_items"]

        if "parse_method" in pdf_data and pdf_data["parse_method"]:
            receipt.parse_method = pdf_data["parse_method"]

        if "parse_confidence" in pdf_data and pdf_data["parse_confidence"] is not None:
            receipt.parse_confidence = int(pdf_data["parse_confidence"])

        # Always update parsing status to 'parsed' if we got data
        receipt.parsing_status = "parsed"

        session.commit()
        return True


def get_pending_gmail_receipts(connection_id: int, limit: int = 100) -> list:
    """Get receipts pending parsing."""
    with get_session() as session:
        receipts = (
            session.query(GmailReceipt)
            .filter(
                GmailReceipt.connection_id == connection_id,
                GmailReceipt.parsing_status == "pending",
                GmailReceipt.deleted_at.is_(None),
                GmailReceipt.retry_count < 3,
            )
            .order_by(GmailReceipt.received_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": r.id,
                "message_id": r.message_id,
                "sender_email": r.sender_email,
                "sender_name": r.sender_name,
                "subject": r.subject,
                "received_at": r.received_at,
                "merchant_domain": r.merchant_domain,
                "raw_schema_data": r.raw_schema_data,
            }
            for r in receipts
        ]


def get_gmail_merchant_alias(merchant_name: str) -> dict:
    """Get merchant alias mapping for matching."""
    with get_session() as session:
        # Use text() for the query since gmail_merchant_aliases table has no model
        result = session.execute(
            text("""
                SELECT bank_name, receipt_name, normalized_name
                FROM gmail_merchant_aliases
                WHERE (LOWER(receipt_name) = LOWER(:merchant_name)
                   OR LOWER(normalized_name) = LOWER(:merchant_name))
                   AND is_active = TRUE
                LIMIT 1
            """),
            {"merchant_name": merchant_name},
        ).fetchone()

        if not result:
            return None

        return {
            "bank_name": result[0],
            "receipt_name": result[1],
            "normalized_name": result[2],
        }


def delete_old_unmatched_gmail_receipts(cutoff_date) -> int:
    """
    Delete old Gmail receipts that are:
    - Older than cutoff_date
    - Not matched to any transaction
    - Have parsing_status of 'unparseable'

    Returns count of deleted receipts.
    """
    with get_session() as session:
        # Subquery to find unmatched receipt IDs
        unmatched_ids = (
            session.query(GmailReceipt.id)
            .outerjoin(GmailMatch, GmailReceipt.id == GmailMatch.gmail_receipt_id)
            .filter(
                GmailReceipt.created_at < cutoff_date,
                GmailMatch.id.is_(None),
                GmailReceipt.parsing_status == "unparseable",
                GmailReceipt.is_deleted.is_(False),
            )
            .subquery()
        )

        deleted = (
            session.query(GmailReceipt)
            .filter(GmailReceipt.id.in_(unmatched_ids))
            .delete(synchronize_session=False)
        )
        session.commit()
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
    with get_session() as session:
        query = (
            session.query(GmailReceipt, GmailConnection.id.label("connection_id"))
            .join(GmailConnection, GmailReceipt.connection_id == GmailConnection.id)
            .filter(
                GmailReceipt.parsing_status == "unparseable",
                GmailReceipt.deleted_at.is_(None),
                or_(
                    GmailReceipt.llm_parse_status.is_(None),
                    GmailReceipt.llm_parse_status == "failed",
                ),
            )
        )

        if connection_id:
            query = query.filter(GmailReceipt.connection_id == connection_id)

        results = query.order_by(GmailReceipt.received_at.desc()).limit(limit).all()

        receipts = []
        for receipt, conn_id in results:
            receipts.append(
                {
                    "id": receipt.id,
                    "message_id": receipt.message_id,
                    "subject": receipt.subject,
                    "sender_email": receipt.sender_email,
                    "sender_name": receipt.sender_name,
                    "merchant_domain": receipt.merchant_domain,
                    "received_at": receipt.received_at,
                    "snippet": receipt.raw_schema_data.get("snippet")
                    if receipt.raw_schema_data
                    else None,
                    "parsing_error": receipt.parsing_error,
                    "llm_parse_status": receipt.llm_parse_status,
                    "llm_estimated_cost_cents": receipt.llm_estimated_cost_cents,
                    "llm_actual_cost_cents": receipt.llm_actual_cost_cents,
                    "connection_id": conn_id,
                }
            )

        return receipts


def get_llm_queue_summary(connection_id: int = None) -> dict:
    """
    Get summary statistics for the LLM parsing queue.

    Returns:
        Dict with count, total_estimated_cost_cents
    """

    with get_session() as session:
        # Build COUNT FILTER equivalents using CASE expressions
        query = session.query(
            func.count().label("total_count"),
            func.sum(case((GmailReceipt.llm_parse_status.is_(None), 1), else_=0)).label(
                "available_count"
            ),
            func.sum(
                case((GmailReceipt.llm_parse_status == "pending", 1), else_=0)
            ).label("pending_count"),
            func.sum(
                case((GmailReceipt.llm_parse_status == "processing", 1), else_=0)
            ).label("processing_count"),
            func.sum(
                case((GmailReceipt.llm_parse_status == "completed", 1), else_=0)
            ).label("completed_count"),
            func.sum(
                case((GmailReceipt.llm_parse_status == "failed", 1), else_=0)
            ).label("failed_count"),
            func.coalesce(func.sum(GmailReceipt.llm_estimated_cost_cents), 0).label(
                "total_estimated_cost_cents"
            ),
            func.coalesce(func.sum(GmailReceipt.llm_actual_cost_cents), 0).label(
                "total_actual_cost_cents"
            ),
        ).filter(
            GmailReceipt.parsing_status == "unparseable",
            GmailReceipt.deleted_at.is_(None),
        )

        if connection_id:
            query = query.filter(GmailReceipt.connection_id == connection_id)

        result = query.one_or_none()

        if result:
            return {
                "total_count": int(result.total_count or 0),
                "available_count": int(result.available_count or 0),
                "pending_count": int(result.pending_count or 0),
                "processing_count": int(result.processing_count or 0),
                "completed_count": int(result.completed_count or 0),
                "failed_count": int(result.failed_count or 0),
                "total_estimated_cost_cents": int(
                    result.total_estimated_cost_cents or 0
                ),
                "total_actual_cost_cents": int(result.total_actual_cost_cents or 0),
            }

        return {
            "total_count": 0,
            "available_count": 0,
            "pending_count": 0,
            "processing_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "total_estimated_cost_cents": 0,
            "total_actual_cost_cents": 0,
        }


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
    with get_session() as session:
        receipt = session.get(GmailReceipt, receipt_id)

        if not receipt:
            return False

        # Update LLM status
        receipt.llm_parse_status = status

        if estimated_cost is not None:
            receipt.llm_estimated_cost_cents = estimated_cost

        if actual_cost is not None:
            receipt.llm_actual_cost_cents = actual_cost

        if status == "completed":
            receipt.llm_parsed_at = func.now()

            # Update parsed data if provided
            if parsed_data:
                if parsed_data.get("merchant_name"):
                    receipt.merchant_name = parsed_data["merchant_name"]
                if parsed_data.get("merchant_name_normalized"):
                    receipt.merchant_name_normalized = parsed_data[
                        "merchant_name_normalized"
                    ]
                if parsed_data.get("total_amount"):
                    receipt.total_amount = parsed_data["total_amount"]
                if parsed_data.get("currency_code"):
                    receipt.currency_code = parsed_data["currency_code"]
                if parsed_data.get("order_id"):
                    receipt.order_id = parsed_data["order_id"]
                if parsed_data.get("receipt_date"):
                    receipt.receipt_date = parsed_data["receipt_date"]
                if parsed_data.get("line_items"):
                    receipt.line_items = parsed_data["line_items"]

                # Update parsing status to parsed
                receipt.parsing_status = "parsed"
                receipt.parse_method = parsed_data.get("parse_method", "llm")
                receipt.parse_confidence = parsed_data.get("parse_confidence", 70)

        session.commit()
        return True


def get_receipt_for_llm_processing(receipt_id: int) -> dict:
    """
    Get receipt details needed for LLM processing.

    Returns:
        Dict with receipt info including message_id for re-fetching from Gmail
    """
    with get_session() as session:
        result = (
            session.query(
                GmailReceipt.id,
                GmailReceipt.message_id,
                GmailReceipt.subject,
                GmailReceipt.sender_email,
                GmailReceipt.merchant_domain,
                GmailReceipt.connection_id.label("gmail_connection_id"),
                GmailConnection.email_address.label("connection_email"),
            )
            .join(GmailConnection, GmailReceipt.connection_id == GmailConnection.id)
            .filter(GmailReceipt.id == receipt_id)
            .one_or_none()
        )

        if result:
            return {
                "id": result.id,
                "message_id": result.message_id,
                "subject": result.subject,
                "sender_email": result.sender_email,
                "merchant_domain": result.merchant_domain,
                "gmail_connection_id": result.gmail_connection_id,
                "connection_email": result.connection_email,
            }

        return None


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
    with get_session() as session:
        # Main aggregation query using PostgreSQL-specific features
        merchants_result = session.execute(
            text("""
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
                        SUM(COALESCE(r.total_amount, 0)) as total_amount,
                        COUNT(*) FILTER (WHERE r.parse_method LIKE 'vendor_%') as vendor_parsed_count,
                        COUNT(*) FILTER (WHERE r.parse_method = 'schema_org') as schema_parsed_count,
                        COUNT(*) FILTER (WHERE r.parse_method = 'pattern') as pattern_parsed_count,
                        COUNT(*) FILTER (WHERE r.parse_method = 'llm') as llm_parsed_count
                    FROM gmail_receipts r
                    LEFT JOIN gmail_transaction_matches m ON r.id = m.gmail_receipt_id
                    JOIN gmail_connections c ON r.connection_id = c.id
                    WHERE c.user_id = :user_id
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
            """),
            {"user_id": user_id},
        ).fetchall()

        merchants_raw = [
            {
                "merchant_normalized": row[0],
                "merchant_domain": row[1],
                "merchant_name": row[2],
                "receipt_count": row[3],
                "parsed_count": row[4],
                "matched_count": row[5],
                "pending_count": row[6],
                "failed_count": row[7],
                "earliest_receipt": row[8],
                "latest_receipt": row[9],
                "llm_cost_cents": row[10],
                "total_amount": row[11],
                "template_type": row[12],
                "has_template": row[13],
                "has_vendor_parser": row[14],
                "schema_parsed_count": row[15],
                "pattern_parsed_count": row[16],
                "llm_parsed_count": row[17],
            }
            for row in merchants_result
        ]

        # For each merchant, find potential transaction matches and alternative source coverage
        merchants = []
        for m in merchants_raw:
            normalized = m.get("merchant_normalized")
            domain = m.get("merchant_domain")
            if not normalized and not domain:
                continue

            match_term = normalized or (domain.split(".")[0].lower() if domain else "")

            # Count potential matches
            potential_result = session.execute(
                text("""
                    SELECT COUNT(*) as count
                    FROM truelayer_transactions t
                    JOIN truelayer_accounts a ON t.account_id = a.id
                    JOIN bank_connections c ON a.connection_id = c.id
                    LEFT JOIN gmail_transaction_matches gm ON gm.truelayer_transaction_id = t.id
                    WHERE c.user_id = :user_id
                      AND t.transaction_type = 'DEBIT'
                      AND gm.id IS NULL
                      AND (
                          LOWER(t.merchant_name) LIKE :match_term
                          OR LOWER(t.description) LIKE :match_term
                      )
                """),
                {"user_id": user_id, "match_term": f"%{match_term}%"},
            ).fetchone()
            m["potential_transaction_matches"] = (
                potential_result[0] if potential_result else 0
            )

            # Count alternative source coverage
            alt_results = session.execute(
                text("""
                    SELECT
                        source_type,
                        COUNT(*) as count
                    FROM transaction_enrichment_sources tes
                    JOIN truelayer_transactions t ON tes.truelayer_transaction_id = t.id
                    JOIN truelayer_accounts a ON t.account_id = a.id
                    JOIN bank_connections c ON a.connection_id = c.id
                    WHERE c.user_id = :user_id
                      AND tes.source_type IN ('amazon', 'amazon_business', 'amazon_fresh', 'apple')
                      AND (
                          LOWER(t.merchant_name) LIKE :match_term
                          OR LOWER(t.description) LIKE :match_term
                      )
                    GROUP BY tes.source_type
                """),
                {"user_id": user_id, "match_term": f"%{match_term}%"},
            ).fetchall()

            alt_sources = {row[0]: row[1] for row in alt_results}
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
            "with_vendor_parser": sum(1 for m in merchants if m["has_vendor_parser"]),
            "total_receipts": sum(m["receipt_count"] for m in merchants),
            "total_parsed": sum(m["parsed_count"] for m in merchants),
            "total_matched": sum(m["matched_count"] for m in merchants),
            "total_pending": sum(m["pending_count"] for m in merchants),
            "total_failed": sum(m["failed_count"] for m in merchants),
            "total_llm_cost_cents": sum(m["llm_cost_cents"] or 0 for m in merchants),
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
    import json

    with get_session() as session:
        # Build query with optional filters
        where_clauses = [
            "c.user_id = :user_id",
            "c.connection_status = 'active'",
            "r.deleted_at IS NULL",
        ]
        params = {"user_id": user_id, "limit": limit, "offset": offset}

        # Filter by normalized name (preferred) or domain
        if merchant_normalized:
            where_clauses.append(
                """LOWER(COALESCE(r.merchant_name_normalized,
                    LOWER(SPLIT_PART(COALESCE(r.merchant_domain,
                        SUBSTRING(r.sender_email FROM '@(.+)$')), '.', 1)))) = LOWER(:merchant_normalized)"""
            )
            params["merchant_normalized"] = merchant_normalized
            identifier = merchant_normalized
        elif merchant_domain:
            where_clauses.append(
                """(LOWER(r.merchant_domain) = LOWER(:merchant_domain)
                    OR LOWER(SUBSTRING(r.sender_email FROM '@(.+)$')) = LOWER(:merchant_domain))"""
            )
            params["merchant_domain"] = merchant_domain
            identifier = merchant_domain
        else:
            return {"receipts": [], "total": 0, "identifier": None}

        if status:
            where_clauses.append("r.parsing_status = :status")
            params["status"] = status

        where_sql = " AND ".join(where_clauses)

        # Get total count
        total_result = session.execute(
            text(f"""
                SELECT COUNT(*) as total
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                WHERE {where_sql}
            """),
            params,
        ).fetchone()
        total = total_result[0] if total_result else 0

        # Get paginated results
        receipts_result = session.execute(
            text(f"""
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
                WHERE {where_sql}
                ORDER BY r.received_at DESC
                LIMIT :limit OFFSET :offset
            """),
            params,
        ).fetchall()

        receipts = []
        for row in receipts_result:
            receipt = {
                "id": row[0],
                "message_id": row[1],
                "sender_email": row[2],
                "sender_name": row[3],
                "subject": row[4],
                "received_at": row[5].isoformat() if row[5] else None,
                "merchant_name": row[6],
                "merchant_name_normalized": row[7],
                "merchant_domain": row[8],
                "order_id": row[9],
                "total_amount": row[10],
                "currency_code": row[11],
                "receipt_date": row[12].isoformat()
                if row[12] and hasattr(row[12], "isoformat")
                else (str(row[12]) if row[12] else None),
                "line_items": row[13] if row[13] else [],
                "parse_method": row[14],
                "parse_confidence": row[15],
                "parsing_status": row[16],
                "parsing_error": row[17],
                "llm_cost_cents": row[18],
                "match_id": row[19],
                "match_confidence": row[20],
                "transaction_id": row[21],
                "transaction_description": row[22],
                "transaction_amount": row[23],
            }

            # CRITICAL: Ensure line_items is always a list for frontend
            if isinstance(receipt.get("line_items"), str):
                try:
                    receipt["line_items"] = json.loads(receipt["line_items"])
                except Exception:
                    receipt["line_items"] = []

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
    with get_session() as session:
        patterns_query = session.query(GmailSenderPattern).order_by(
            GmailSenderPattern.usage_count.desc(),
            GmailSenderPattern.merchant_name.asc(),
        )

        patterns = []
        for pattern in patterns_query.all():
            pattern_dict = {
                "id": pattern.id,
                "sender_domain": pattern.sender_domain,
                "sender_pattern": pattern.sender_pattern,
                "merchant_name": pattern.merchant_name,
                "normalized_name": pattern.normalized_name,
                "parse_type": pattern.parse_type,
                "pattern_config": pattern.pattern_config,
                "date_tolerance_days": pattern.date_tolerance_days,
                "is_active": pattern.is_active,
                "usage_count": pattern.usage_count,
                "last_used_at": pattern.last_used_at.isoformat()
                if pattern.last_used_at
                else None,
                "created_at": pattern.created_at.isoformat()
                if pattern.created_at
                else None,
            }
            patterns.append(pattern_dict)

        return patterns


def get_transactions_for_matching(
    user_id: int, from_date=None, to_date=None, limit: int = 1000
) -> list:
    """Get TrueLayer transactions for matching with receipts."""
    with get_session() as session:
        from .models.truelayer import BankConnection, TrueLayerAccount

        query = (
            session.query(
                TrueLayerTransaction.id,
                TrueLayerTransaction.transaction_id,
                TrueLayerTransaction.amount,
                TrueLayerTransaction.currency,
                TrueLayerTransaction.description,
                TrueLayerTransaction.merchant_name,
                TrueLayerTransaction.timestamp.label("date"),
                TrueLayerAccount.display_name.label("account_name"),
            )
            .join(
                TrueLayerAccount, TrueLayerTransaction.account_id == TrueLayerAccount.id
            )
            .join(BankConnection, TrueLayerAccount.connection_id == BankConnection.id)
            .filter(
                BankConnection.user_id == user_id,
                TrueLayerTransaction.transaction_type == "DEBIT",
            )
        )

        if from_date:
            query = query.filter(TrueLayerTransaction.timestamp >= from_date)

        if to_date:
            query = query.filter(TrueLayerTransaction.timestamp <= to_date)

        results = (
            query.order_by(TrueLayerTransaction.timestamp.desc()).limit(limit).all()
        )

        return [
            {
                "id": r[0],
                "transaction_id": r[1],
                "amount": r[2],
                "currency": r[3],
                "description": r[4],
                "merchant_name": r[5],
                "date": r[6],
                "account_name": r[7],
            }
            for r in results
        ]


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
    with get_session() as session:
        stmt = (
            insert(MatchingJob)
            .values(
                user_id=user_id,
                job_type=job_type,
                celery_task_id=celery_task_id,
                status="queued",
            )
            .returning(MatchingJob.id)
        )
        result = session.execute(stmt)
        job_id = result.scalar_one()
        session.commit()
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
    with get_session() as session:
        job = session.get(MatchingJob, job_id)

        if not job:
            return False

        job.status = status

        if status == "running":
            job.started_at = func.now()
        elif status in ("completed", "failed"):
            job.completed_at = func.now()
            if error_message:
                job.error_message = error_message

        session.commit()
        return True


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
    with get_session() as session:
        job = session.get(MatchingJob, job_id)

        if not job:
            return False

        # Update only provided fields
        if total_items is not None:
            job.total_items = total_items
        if processed_items is not None:
            job.processed_items = processed_items
        if matched_items is not None:
            job.matched_items = matched_items
        if failed_items is not None:
            job.failed_items = failed_items

        session.commit()
        return True


def get_matching_job(job_id: int) -> dict:
    """
    Get matching job by ID.

    Args:
        job_id: Job ID

    Returns:
        Job dictionary or None
    """
    with get_session() as session:
        job = session.get(MatchingJob, job_id)

        if not job:
            return None

        job_dict = {
            "id": job.id,
            "user_id": job.user_id,
            "job_type": job.job_type,
            "celery_task_id": job.celery_task_id,
            "status": job.status,
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "matched_items": job.matched_items,
            "failed_items": job.failed_items,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
        }

        # Calculate progress percentage
        total = job_dict.get("total_items", 0) or 0
        processed = job_dict.get("processed_items", 0) or 0
        job_dict["progress_percentage"] = round(
            (processed / total * 100) if total > 0 else 0
        )

        return job_dict


def get_active_matching_jobs(user_id: int) -> list:
    """
    Get all active (queued/running) matching jobs for a user.

    Args:
        user_id: User ID

    Returns:
        List of active job dictionaries
    """
    with get_session() as session:
        results = (
            session.query(MatchingJob)
            .filter(
                MatchingJob.user_id == user_id,
                MatchingJob.status.in_(["queued", "running"]),
            )
            .order_by(MatchingJob.created_at.desc())
            .all()
        )

        jobs = []
        for job in results:
            job_dict = {
                "id": job.id,
                "user_id": job.user_id,
                "job_type": job.job_type,
                "celery_task_id": job.celery_task_id,
                "status": job.status,
                "total_items": job.total_items,
                "processed_items": job.processed_items,
                "matched_items": job.matched_items,
                "failed_items": job.failed_items,
                "error_message": job.error_message,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "created_at": job.created_at,
            }

            # Calculate progress percentage
            total = job_dict.get("total_items", 0) or 0
            processed = job_dict.get("processed_items", 0) or 0
            job_dict["progress_percentage"] = round(
                (processed / total * 100) if total > 0 else 0
            )

            jobs.append(job_dict)

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
    with get_session() as session:
        # Find stale jobs using text() for interval arithmetic
        interval_expr = text(f"NOW() - INTERVAL '{stale_threshold_minutes} minutes'")

        stale_jobs = (
            session.query(MatchingJob)
            .filter(
                MatchingJob.status.in_(["queued", "running"]),
                or_(
                    # Queued jobs that never started
                    (
                        (MatchingJob.status == "queued")
                        & (MatchingJob.created_at < interval_expr)
                    ),
                    # Running jobs that hung
                    (
                        (MatchingJob.status == "running")
                        & (MatchingJob.started_at < interval_expr)
                    ),
                ),
            )
            .all()
        )

        if not stale_jobs:
            return {"cleaned_up": 0, "job_ids": []}

        job_ids = [job.id for job in stale_jobs]

        # Mark as failed
        for job in stale_jobs:
            job.status = "failed"
            job.error_message = "Job stalled - automatically cleaned up after timeout"
            job.completed_at = func.now()

        session.commit()

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
    from mcp.pattern_extractor import (
        extract_direct_debit_payee_fallback,
        extract_variables,
    )

    from .models.categories import MerchantNormalization

    with get_session() as session:
        # Get all direct debit transactions
        transactions = (
            session.query(
                TrueLayerTransaction.id,
                TrueLayerTransaction.description,
                TrueLayerTransaction.metadata,
            )
            .filter(TrueLayerTransaction.description.like("DIRECT DEBIT PAYMENT TO%"))
            .order_by(TrueLayerTransaction.timestamp.desc())
            .all()
        )

        # Group by extracted payee
        payee_data = {}
        for txn in transactions:
            # Extract enrichment from metadata JSONB
            metadata = txn.metadata or {}
            enrichment = metadata.get("enrichment", {})
            category = enrichment.get("primary_category")
            subcategory = enrichment.get("subcategory")
            enrichment.get("merchant_clean_name")

            extracted = extract_variables(txn.description)
            payee = extracted.get("payee")

            # Fallback extraction if strict pattern fails
            if not payee:
                extracted = extract_direct_debit_payee_fallback(txn.description)
                payee = extracted.get("payee")

            if payee:
                payee_upper = payee.upper().strip()
                if payee_upper not in payee_data:
                    payee_data[payee_upper] = {
                        "payee": payee.strip(),
                        "transaction_count": 0,
                        "sample_description": txn.description,
                        "categories": {},
                        "subcategories": {},
                    }
                payee_data[payee_upper]["transaction_count"] += 1

                # Track category frequency
                cat = category or "Uncategorized"
                payee_data[payee_upper]["categories"][cat] = (
                    payee_data[payee_upper]["categories"].get(cat, 0) + 1
                )

                subcat = subcategory or "None"
                payee_data[payee_upper]["subcategories"][subcat] = (
                    payee_data[payee_upper]["subcategories"].get(subcat, 0) + 1
                )

        # Find existing mappings for these payees
        mappings_query = (
            session.query(MerchantNormalization)
            .filter(MerchantNormalization.source == "direct_debit")
            .order_by(MerchantNormalization.priority.desc())
            .all()
        )
        mappings = {
            m.pattern.upper(): {
                "id": m.id,
                "pattern": m.pattern,
                "normalized_name": m.normalized_name,
                "default_category": m.default_category,
                "merchant_type": m.merchant_type,
            }
            for m in mappings_query
        }

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
    from .models.categories import MerchantNormalization

    with get_session() as session:
        results = (
            session.query(MerchantNormalization)
            .filter(MerchantNormalization.source == "direct_debit")
            .order_by(
                MerchantNormalization.priority.desc(),
                MerchantNormalization.pattern.asc(),
            )
            .all()
        )

        return [
            {
                "id": m.id,
                "pattern": m.pattern,
                "pattern_type": m.pattern_type,
                "normalized_name": m.normalized_name,
                "merchant_type": m.merchant_type,
                "default_category": m.default_category,
                "priority": m.priority,
                "source": m.source,
                "usage_count": m.usage_count,
                "created_at": m.created_at,
                "updated_at": m.updated_at,
            }
            for m in results
        ]


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
    from .models.categories import MerchantNormalization

    with get_session() as session:
        stmt = (
            insert(MerchantNormalization)
            .values(
                pattern=payee_pattern.upper(),
                pattern_type="exact",
                normalized_name=normalized_name,
                merchant_type=merchant_type,
                default_category=category,
                priority=100,
                source="direct_debit",
            )
            .on_conflict_do_update(
                index_elements=["pattern", "pattern_type"],
                set_={
                    "normalized_name": normalized_name,
                    "merchant_type": merchant_type,
                    "default_category": category,
                    "priority": 100,
                    "source": "direct_debit",
                    "updated_at": func.now(),
                },
            )
            .returning(MerchantNormalization.id)
        )
        result = session.execute(stmt)
        mapping_id = result.scalar_one()
        session.commit()
        return mapping_id


def delete_direct_debit_mapping(mapping_id: int) -> bool:
    """
    Delete a direct debit mapping.

    Args:
        mapping_id: ID of the mapping to delete

    Returns:
        True if deleted successfully
    """
    from .models.categories import MerchantNormalization

    with get_session() as session:
        result = (
            session.query(MerchantNormalization)
            .filter(
                MerchantNormalization.id == mapping_id,
                MerchantNormalization.source == "direct_debit",
            )
            .delete()
        )
        session.commit()
        return result > 0


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

    from .models.categories import MerchantNormalization

    with get_session() as session:
        # Get all direct debit mappings
        mappings_query = (
            session.query(MerchantNormalization)
            .filter(MerchantNormalization.source == "direct_debit")
            .all()
        )
        mappings = {
            m.pattern.upper(): {
                "id": m.id,
                "pattern": m.pattern,
                "normalized_name": m.normalized_name,
                "merchant_type": m.merchant_type,
                "default_category": m.default_category,
            }
            for m in mappings_query
        }

        if not mappings:
            return {"updated_count": 0, "transactions": []}

        # Get direct debit transactions
        transactions = (
            session.query(
                TrueLayerTransaction.id,
                TrueLayerTransaction.description,
                TrueLayerTransaction.metadata,
            )
            .filter(TrueLayerTransaction.description.like("DIRECT DEBIT PAYMENT TO%"))
            .all()
        )

        updated_ids = []
        for txn in transactions:
            extracted = extract_variables(txn.description)
            payee = extracted.get("payee")

            # Fallback extraction if strict pattern fails
            if not payee:
                extracted = extract_direct_debit_payee_fallback(txn.description)
                payee = extracted.get("payee")

            if payee and payee.upper() in mappings:
                mapping = mappings[payee.upper()]

                # Get transaction object for update
                txn_obj = session.get(TrueLayerTransaction, txn.id)

                # Build enrichment data
                metadata = txn_obj.metadata or {}
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
                txn_obj.metadata = metadata
                updated_ids.append(txn.id)

        session.commit()
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

    from .models.categories import MerchantNormalization

    with get_session() as session:
        # Get all mapped payees
        mapped_results = (
            session.query(MerchantNormalization.pattern)
            .filter(MerchantNormalization.source == "direct_debit")
            .all()
        )
        mapped_payees = {row[0].upper() for row in mapped_results}

        # Get all direct debit transactions
        transactions = (
            session.query(
                TrueLayerTransaction.description,
                TrueLayerTransaction.timestamp,
            )
            .filter(TrueLayerTransaction.description.like("DIRECT DEBIT PAYMENT TO%"))
            .order_by(TrueLayerTransaction.timestamp.asc())
            .all()
        )

        # Track payees and their mandates
        payee_info = {}  # payee -> {first_seen, mandates: set(), count}

        for txn in transactions:
            extracted = extract_variables(txn.description)
            if not extracted.get("payee"):
                extracted = extract_direct_debit_payee_fallback(txn.description)

            payee = extracted.get("payee")
            if not payee:
                continue

            payee_upper = payee.upper().strip()
            mandate = extracted.get("mandate_number")

            if payee_upper not in payee_info:
                payee_info[payee_upper] = {
                    "payee": payee.strip(),
                    "first_seen": txn.timestamp,
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

    with get_session() as session:
        # Get all transactions
        transactions = (
            session.query(
                TrueLayerTransaction.id,
                TrueLayerTransaction.description,
                TrueLayerTransaction.amount,
                TrueLayerTransaction.timestamp.label("date"),
            )
            .order_by(TrueLayerTransaction.timestamp.desc())
            .all()
        )

        matches = []
        pattern_upper = pattern.upper()

        for txn in transactions:
            description = txn.description.upper() if txn.description else ""

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
                        re.search(pattern, txn.description or "", re.IGNORECASE)
                    )
                except re.error:
                    matched = False

            if matched:
                matches.append(
                    {
                        "id": txn.id,
                        "description": txn.description,
                        "amount": float(txn.amount) if txn.amount else 0,
                        "date": txn.date.isoformat() if txn.date else None,
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
    from .models.categories import CategoryRule, MerchantNormalization

    with get_session() as session:
        # Count category rules
        category_rules_count = (
            session.query(func.count())
            .select_from(CategoryRule)
            .filter(CategoryRule.is_active.is_(True))
            .scalar()
        )

        # Count merchant normalizations
        merchant_rules_count = (
            session.query(func.count()).select_from(MerchantNormalization).scalar()
        )

        # Get total usage from category rules
        category_usage = session.query(
            func.coalesce(func.sum(CategoryRule.usage_count), 0)
        ).scalar()

        # Get total usage from merchant normalizations
        merchant_usage = session.query(
            func.coalesce(func.sum(MerchantNormalization.usage_count), 0)
        ).scalar()

        total_usage = (category_usage or 0) + (merchant_usage or 0)

        # Get coverage: count transactions with rule-based enrichment
        total_transactions = (
            session.query(func.count()).select_from(TrueLayerTransaction).scalar()
        )

        # Count transactions where metadata->enrichment->enrichment_source = 'rule'
        covered_transactions = (
            session.query(func.count())
            .select_from(TrueLayerTransaction)
            .filter(
                TrueLayerTransaction.metadata["enrichment"]["enrichment_source"].astext
                == "rule"
            )
            .scalar()
        )

        coverage_percentage = (
            (covered_transactions / total_transactions * 100)
            if total_transactions > 0
            else 0
        )

        # Rules by category
        category_results = (
            session.query(CategoryRule.category, func.count().label("count"))
            .filter(CategoryRule.is_active.is_(True))
            .group_by(CategoryRule.category)
            .order_by(text("count DESC"))
            .all()
        )
        rules_by_category = {row.category: row.count for row in category_results}

        # Rules by source (combine both tables with UNION ALL)
        # We need to use a raw query for UNION ALL
        source_results = session.execute(
            text("""
                SELECT source, COUNT(*) as count
                FROM (
                    SELECT source FROM category_rules WHERE is_active = true
                    UNION ALL
                    SELECT source FROM merchant_normalizations
                ) combined
                GROUP BY source
                ORDER BY count DESC
            """)
        ).fetchall()
        rules_by_source = {row[0]: row[1] for row in source_results}

        # Top used rules (combine category rules and merchant normalizations)
        top_results = session.execute(
            text("""
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
        ).fetchall()
        top_used_rules = [
            {"name": row[0], "count": row[1], "type": row[2]} for row in top_results
        ]

        # Unused rules
        unused_results = session.execute(
            text("""
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
        ).fetchall()
        unused_rules = [{"name": row[0], "type": row[1]} for row in unused_results]

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
    from collections import defaultdict

    from .models.categories import CategoryRule, MerchantNormalization

    with get_session() as session:
        # Get all active category rules
        category_rules = (
            session.query(CategoryRule)
            .filter(CategoryRule.is_active.is_(True))
            .order_by(CategoryRule.priority.desc())
            .all()
        )

        # Get all merchant normalizations
        merchant_rules = (
            session.query(MerchantNormalization)
            .order_by(MerchantNormalization.priority.desc())
            .all()
        )

        # Get all transactions
        transactions = session.query(
            TrueLayerTransaction.id,
            TrueLayerTransaction.description,
        ).all()

        # Track matches
        rule_matches = defaultdict(list)  # rule_id -> [txn_ids]
        txn_matches = defaultdict(list)  # txn_id -> [rule_ids]
        category_coverage = defaultdict(int)  # category -> count

        for txn in transactions:
            desc = txn.description.upper() if txn.description else ""

            # Check category rules
            for rule in category_rules:
                pattern = rule.description_pattern.upper()
                pattern_type = rule.pattern_type

                matched = False
                if pattern_type == "contains":
                    matched = pattern in desc
                elif pattern_type == "starts_with":
                    matched = desc.startswith(pattern)
                elif pattern_type == "exact":
                    matched = desc == pattern
                elif pattern_type == "regex":
                    with contextlib.suppress(re.error):
                        matched = bool(
                            re.search(
                                rule.description_pattern,
                                txn.description or "",
                                re.IGNORECASE,
                            )
                        )

                if matched:
                    rule_key = f"cat_{rule.id}"
                    rule_matches[rule_key].append(txn.id)
                    txn_matches[txn.id].append(rule_key)
                    category_coverage[rule.category] += 1

            # Check merchant rules
            for rule in merchant_rules:
                pattern = rule.pattern.upper()
                pattern_type = rule.pattern_type

                matched = False
                if pattern_type == "contains":
                    matched = pattern in desc
                elif pattern_type == "starts_with":
                    matched = desc.startswith(pattern)
                elif pattern_type == "exact":
                    matched = desc == pattern
                elif pattern_type == "regex":
                    with contextlib.suppress(re.error):
                        matched = bool(
                            re.search(
                                rule.pattern,
                                txn.description or "",
                                re.IGNORECASE,
                            )
                        )

                if matched:
                    rule_key = f"mer_{rule.id}"
                    rule_matches[rule_key].append(txn.id)
                    txn_matches[txn.id].append(rule_key)
                    if rule.default_category:
                        category_coverage[rule.default_category] += 1

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
            r for r in category_rules if f"cat_{r.id}" not in rule_matches
        ]
        unused_merchant_rules = [
            r for r in merchant_rules if f"mer_{r.id}" not in rule_matches
        ]

        # Find potential conflicts (transactions matching multiple rules)
        conflicts = []
        for txn_id, rules in txn_matches.items():
            if len(rules) > 1:
                conflicts.append({"transaction_id": txn_id, "matching_rules": rules})

        return {
            "total_transactions": total_transactions,
            "covered_transactions": covered_transactions,
            "coverage_percentage": round(coverage_percentage, 1),
            "category_coverage": dict(category_coverage),
            "unused_category_rules": [
                {
                    "id": r.id,
                    "name": r.rule_name,
                    "pattern": r.description_pattern,
                }
                for r in unused_category_rules
            ],
            "unused_merchant_rules": [
                {
                    "id": r.id,
                    "pattern": r.pattern,
                    "name": r.normalized_name,
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

    from .models.categories import CategoryRule, MerchantNormalization

    with get_session() as session:
        # Get all rules
        category_rules = (
            session.query(CategoryRule)
            .filter(CategoryRule.is_active.is_(True))
            .order_by(CategoryRule.priority.desc())
            .all()
        )

        merchant_normalizations = (
            session.query(MerchantNormalization)
            .order_by(MerchantNormalization.priority.desc())
            .all()
        )

        # Convert to dicts for consistency engine
        category_rules_dicts = [
            {col: getattr(r, col) for col in r.__table__.columns}
            for r in category_rules
        ]
        merchant_norm_dicts = [
            {col: getattr(m, col) for col in m.__table__.columns}
            for m in merchant_normalizations
        ]

        # Get all transactions
        transactions = session.query(TrueLayerTransaction).all()

        updated_count = 0
        rule_hits = {}

        for txn in transactions:
            txn_dict = {
                "id": txn.id,
                "description": txn.description,
                "amount": txn.amount,
                "transaction_type": txn.transaction_type,
                "timestamp": txn.timestamp,
                "metadata": txn.metadata,
            }

            result = apply_rules_to_transaction(
                txn_dict, category_rules_dicts, merchant_norm_dicts
            )

            if result and result.get("primary_category"):
                # Update the transaction with rule-based enrichment
                metadata = txn.metadata or {}
                metadata["enrichment"] = result

                txn.metadata = metadata
                updated_count += 1

                # Track rule hits
                matched_rule = result.get("matched_rule", "unknown")
                rule_hits[matched_rule] = rule_hits.get(matched_rule, 0) + 1

        session.commit()

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
    with get_session() as session:
        if include_counts:
            # Use subqueries for counts

            result = session.execute(
                text("""
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
                    WHERE (:active_only = FALSE OR nc.is_active = TRUE)
                    ORDER BY nc.display_order, nc.name
                """),
                {"active_only": active_only},
            ).fetchall()
            return [dict(row._mapping) for row in result]
        query = session.query(NormalizedCategory)
        if active_only:
            query = query.filter(NormalizedCategory.is_active.is_(True))
        results = query.order_by(
            NormalizedCategory.display_order,
            NormalizedCategory.name,
        ).all()
        return [{col: getattr(r, col) for col in r.__table__.columns} for r in results]


def get_normalized_category_by_id(category_id: int):
    """Get a single normalized category by ID with subcategories."""
    with get_session() as session:
        # Get category with transaction count using text() for subquery
        result = session.execute(
            text("""
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
                WHERE nc.id = :category_id
            """),
            {"category_id": category_id},
        ).fetchone()

        if not result:
            return None

        category = dict(result._mapping)

        # Get subcategories
        subcats_result = session.execute(
            text("""
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
                WHERE ns.category_id = :category_id
                ORDER BY ns.display_order, ns.name
            """),
            {"category_id": category_id},
        ).fetchall()

        category["subcategories"] = [dict(row._mapping) for row in subcats_result]

        return category


def get_normalized_category_by_name(name: str):
    """Get a normalized category by name."""
    with get_session() as session:
        category = (
            session.query(NormalizedCategory)
            .filter(NormalizedCategory.name == name)
            .one_or_none()
        )

        if category:
            return {col: getattr(category, col) for col in category.__table__.columns}
        return None


def create_normalized_category(
    name: str, description: str = None, is_essential: bool = False, color: str = None
):
    """Create a new normalized category.

    Returns:
        The created category dict, or None if name already exists
    """
    with get_session() as session:
        try:
            # Get next display order
            max_order = session.query(
                func.coalesce(func.max(NormalizedCategory.display_order), 0)
            ).scalar()
            next_order = max_order + 1

            stmt = (
                insert(NormalizedCategory)
                .values(
                    name=name,
                    description=description,
                    is_system=False,
                    is_essential=is_essential,
                    display_order=next_order,
                    color=color,
                )
                .returning(NormalizedCategory)
            )
            result = session.execute(stmt)
            new_category = result.fetchone()[0]
            session.commit()

            return {
                col: getattr(new_category, col)
                for col in new_category.__table__.columns
            }
        except IntegrityError:
            session.rollback()
            return None


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
    with get_session() as session:
        # Get current category
        current = session.get(NormalizedCategory, category_id)
        if not current:
            return None

        old_name = current.name
        new_name = name if name is not None else old_name

        # Update fields
        if name is not None:
            current.name = name
        if description is not None:
            current.description = description
        if is_active is not None:
            current.is_active = is_active
        if is_essential is not None:
            current.is_essential = is_essential
        if color is not None:
            current.color = color

        if (
            name is None
            and description is None
            and is_active is None
            and is_essential is None
            and color is None
        ):
            return {
                "category": {
                    col: getattr(current, col) for col in current.__table__.columns
                },
                "transactions_updated": 0,
                "rules_updated": 0,
            }

        transactions_updated = 0
        rules_updated = 0

        # If name changed, cascade updates
        if name is not None and name != old_name:
            from .models.categories import CategoryRule

            # Update transaction_category VARCHAR (for backwards compatibility)
            transactions_updated = (
                session.query(TrueLayerTransaction)
                .filter(TrueLayerTransaction.category_id == category_id)
                .update({"transaction_category": new_name})
            )

            # Update JSONB metadata using raw SQL
            session.execute(
                text("""
                    UPDATE truelayer_transactions
                    SET metadata = jsonb_set(
                        metadata,
                        '{enrichment,primary_category}',
                        :new_name::jsonb
                    )
                    WHERE category_id = :category_id
                      AND metadata->'enrichment' IS NOT NULL
                """),
                {"new_name": json.dumps(new_name), "category_id": category_id},
            )

            # Update category_rules VARCHAR
            rules_updated = (
                session.query(CategoryRule)
                .filter(CategoryRule.category_id == category_id)
                .update({"category": new_name})
            )

        session.commit()

        # Invalidate cache
        try:
            from cache_manager import cache_invalidate_transactions

            cache_invalidate_transactions()
        except ImportError:
            pass

        return {
            "category": {
                col: getattr(current, col) for col in current.__table__.columns
            },
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
    with get_session() as session:
        # Check if category exists and is not system
        category = session.get(NormalizedCategory, category_id)

        if not category:
            return None
        if category.is_system:
            return {"error": "Cannot delete system category"}

        # Find reassignment target (default to 'Other')
        if reassign_to_category_id:
            target_id = reassign_to_category_id
        else:
            other = (
                session.query(NormalizedCategory.id)
                .filter(NormalizedCategory.name == "Other")
                .one_or_none()
            )
            target_id = other[0] if other else None

        # Reassign transactions
        transactions_reassigned = 0
        if target_id:
            transactions_reassigned = (
                session.query(TrueLayerTransaction)
                .filter(TrueLayerTransaction.category_id == category_id)
                .update(
                    {
                        "category_id": target_id,
                        "subcategory_id": None,
                    }
                )
            )

        # Delete the category (subcategories cascade)
        session.delete(category)
        session.commit()

        return {
            "deleted_category": category.name,
            "transactions_reassigned": transactions_reassigned,
            "reassigned_to_category_id": target_id,
        }


def get_normalized_subcategories(category_id: int = None, include_counts: bool = False):
    """Get normalized subcategories, optionally filtered by category.

    Args:
        category_id: If provided, only return subcategories for this category
        include_counts: If True, include transaction counts
    """
    with get_session() as session:
        if include_counts:
            # Use text() for complex subquery
            if category_id:
                result = session.execute(
                    text("""
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
                        WHERE ns.category_id = :category_id
                        ORDER BY ns.display_order, ns.name
                    """),
                    {"category_id": category_id},
                ).fetchall()
            else:
                result = session.execute(
                    text("""
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
                ).fetchall()
            return [dict(row._mapping) for row in result]
        query = session.query(
            NormalizedSubcategory,
            NormalizedCategory.name.label("category_name"),
        ).join(
            NormalizedCategory,
            NormalizedSubcategory.category_id == NormalizedCategory.id,
        )

        if category_id:
            query = query.filter(NormalizedSubcategory.category_id == category_id)
            query = query.order_by(
                NormalizedSubcategory.display_order, NormalizedSubcategory.name
            )
        else:
            query = query.order_by(
                NormalizedCategory.name,
                NormalizedSubcategory.display_order,
                NormalizedSubcategory.name,
            )

        results = query.all()
        return [
            {
                **{col: getattr(subcat, col) for col in subcat.__table__.columns},
                "category_name": cat_name,
            }
            for subcat, cat_name in results
        ]


def get_normalized_subcategory_by_id(subcategory_id: int):
    """Get a single normalized subcategory by ID."""
    with get_session() as session:
        result = session.execute(
            text("""
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
                WHERE ns.id = :subcategory_id
            """),
            {"subcategory_id": subcategory_id},
        ).fetchone()

        if result:
            return dict(result._mapping)
        return None


def create_normalized_subcategory(category_id: int, name: str, description: str = None):
    """Create a new normalized subcategory.

    Returns:
        The created subcategory dict, or None if already exists
    """
    with get_session() as session:
        try:
            # Get next display order for this category
            max_order = (
                session.query(
                    func.coalesce(func.max(NormalizedSubcategory.display_order), 0)
                )
                .filter(NormalizedSubcategory.category_id == category_id)
                .scalar()
            )
            next_order = max_order + 1

            stmt = (
                insert(NormalizedSubcategory)
                .values(
                    category_id=category_id,
                    name=name,
                    description=description,
                    display_order=next_order,
                )
                .returning(NormalizedSubcategory)
            )
            result = session.execute(stmt)
            new_subcat = result.fetchone()[0]
            session.commit()

            # Get category name
            category = session.get(NormalizedCategory, category_id)

            subcat_dict = {
                col: getattr(new_subcat, col) for col in new_subcat.__table__.columns
            }
            subcat_dict["category_name"] = category.name if category else None

            return subcat_dict
        except IntegrityError:
            session.rollback()
            return None


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
    with get_session() as session:
        # Get current subcategory with category name
        result = (
            session.query(
                NormalizedSubcategory,
                NormalizedCategory.name.label("category_name"),
            )
            .join(
                NormalizedCategory,
                NormalizedSubcategory.category_id == NormalizedCategory.id,
            )
            .filter(NormalizedSubcategory.id == subcategory_id)
            .one_or_none()
        )

        if not result:
            return None

        current, old_category_name = result
        old_name = current.name
        new_name = name if name is not None else old_name

        # Update fields
        if name is not None:
            current.name = name
        if description is not None:
            current.description = description
        if is_active is not None:
            current.is_active = is_active
        if category_id is not None:
            current.category_id = category_id

        if (
            name is None
            and description is None
            and is_active is None
            and category_id is None
        ):
            return {
                "subcategory": {
                    **{col: getattr(current, col) for col in current.__table__.columns},
                    "category_name": old_category_name,
                },
                "transactions_updated": 0,
            }

        # Get new category name
        new_category = session.get(NormalizedCategory, current.category_id)
        new_category_name = new_category.name if new_category else None

        transactions_updated = 0

        # If name changed, cascade updates to JSONB metadata
        if name is not None and name != old_name:
            session.execute(
                text("""
                    UPDATE truelayer_transactions
                    SET metadata = jsonb_set(
                        metadata,
                        '{enrichment,subcategory}',
                        :new_name::jsonb
                    )
                    WHERE subcategory_id = :subcategory_id
                      AND metadata->'enrichment' IS NOT NULL
                """),
                {"new_name": json.dumps(new_name), "subcategory_id": subcategory_id},
            )
            transactions_updated = session.execute(
                text(
                    "SELECT COUNT(*) FROM truelayer_transactions WHERE subcategory_id = :subcategory_id"
                ),
                {"subcategory_id": subcategory_id},
            ).scalar()

        session.commit()

        # Invalidate cache
        try:
            from cache_manager import cache_invalidate_transactions

            cache_invalidate_transactions()
        except ImportError:
            pass

        return {
            "subcategory": {
                **{col: getattr(current, col) for col in current.__table__.columns},
                "category_name": new_category_name,
            },
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
    with get_session() as session:
        # Get subcategory with category name
        result = (
            session.query(
                NormalizedSubcategory,
                NormalizedCategory.name.label("category_name"),
            )
            .join(
                NormalizedCategory,
                NormalizedSubcategory.category_id == NormalizedCategory.id,
            )
            .filter(NormalizedSubcategory.id == subcategory_id)
            .one_or_none()
        )

        if not result:
            return None

        subcategory, category_name = result

        # Clear subcategory_id from transactions
        transactions_cleared = (
            session.query(TrueLayerTransaction)
            .filter(TrueLayerTransaction.subcategory_id == subcategory_id)
            .update({"subcategory_id": None})
        )

        # Delete the subcategory
        session.delete(subcategory)
        session.commit()

        return {
            "deleted_subcategory": subcategory.name,
            "category_name": category_name,
            "transactions_cleared": transactions_cleared,
        }


def get_essential_category_names():
    """Get list of category names that are marked as essential.

    Used by consistency engine for Essential/Discretionary classification.
    """
    with get_session() as session:
        results = (
            session.query(NormalizedCategory.name)
            .filter(
                NormalizedCategory.is_essential.is_(True),
                NormalizedCategory.is_active.is_(True),
            )
            .all()
        )
        return {row[0] for row in results}


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
    from sqlalchemy.dialects.postgresql import insert

    with get_session() as session:
        stmt = (
            insert(PdfAttachment)
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
            .returning(PdfAttachment.id)
        )
        result = session.execute(stmt)
        attachment_id = result.scalar_one()
        session.commit()
        return attachment_id


def get_pdf_attachment_by_hash(content_hash: str) -> dict:
    """Check if a PDF with this content hash already exists (for deduplication)."""
    with get_session() as session:
        attachment = (
            session.query(PdfAttachment)
            .filter(PdfAttachment.content_hash == content_hash)
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
            session.query(PdfAttachment)
            .filter(PdfAttachment.gmail_receipt_id == gmail_receipt_id)
            .order_by(PdfAttachment.created_at)
            .all()
        )

        return [
            {
                "id": a.id,
                "bucket_name": a.bucket_name,
                "object_key": a.object_key,
                "filename": a.filename,
                "content_hash": a.content_hash,
                "size_bytes": a.size_bytes,
                "mime_type": a.mime_type,
                "created_at": a.created_at,
            }
            for a in attachments
        ]


def get_pdf_attachment_by_id(attachment_id: int) -> dict:
    """Get a single PDF attachment by ID."""
    with get_session() as session:
        result = (
            session.query(
                PdfAttachment, GmailReceipt.merchant_name, GmailReceipt.receipt_date
            )
            .outerjoin(GmailReceipt, PdfAttachment.gmail_receipt_id == GmailReceipt.id)
            .filter(PdfAttachment.id == attachment_id)
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
            func.count().label("total_attachments"),
            func.coalesce(func.sum(PdfAttachment.size_bytes), 0).label(
                "total_size_bytes"
            ),
            func.count(func.distinct(PdfAttachment.content_hash)).label("unique_pdfs"),
            func.count(func.distinct(PdfAttachment.gmail_receipt_id)).label(
                "receipts_with_pdfs"
            ),
        ).one_or_none()

        if result:
            return {
                "total_attachments": int(result.total_attachments or 0),
                "total_size_bytes": int(result.total_size_bytes or 0),
                "unique_pdfs": int(result.unique_pdfs or 0),
                "receipts_with_pdfs": int(result.receipts_with_pdfs or 0),
            }

        return {
            "total_attachments": 0,
            "total_size_bytes": 0,
            "unique_pdfs": 0,
            "receipts_with_pdfs": 0,
        }


def delete_pdf_attachment(attachment_id: int) -> bool:
    """Delete a PDF attachment record (MinIO object should be deleted separately)."""
    with get_session() as session:
        attachment = session.get(PdfAttachment, attachment_id)
        if not attachment:
            return False

        session.delete(attachment)
        session.commit()
        return True


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
    with get_session() as session:
        stmt = (
            insert(User)
            .values(
                username=username,
                email=email,
                password_hash=password_hash,
                is_admin=is_admin,
                is_active=True,
            )
            .returning(User.id)
        )
        result = session.execute(stmt)
        user_id = result.scalar_one()
        session.commit()
        return user_id


def get_user_by_id(user_id: int) -> dict:
    """Get user by ID (for Flask-Login user_loader).

    Args:
        user_id: User ID to lookup

    Returns:
        Dictionary with user data or None if not found
    """
    with get_session() as session:
        user = (
            session.query(User)
            .filter(User.id == user_id, User.is_active.is_(True))
            .first()
        )

        if not user:
            return None

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "password_hash": user.password_hash,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }


def get_user_by_username(username: str) -> dict:
    """Get user by username (for login).

    Args:
        username: Username to lookup

    Returns:
        Dictionary with user data or None if not found
    """
    with get_session() as session:
        user = session.query(User).filter(User.username == username).first()

        if not user:
            return None

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "password_hash": user.password_hash,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }


def get_user_by_email(email: str) -> dict:
    """Get user by email.

    Args:
        email: Email address to lookup

    Returns:
        Dictionary with user data or None if not found
    """
    with get_session() as session:
        user = session.query(User).filter(User.email == email).first()

        if not user:
            return None

        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "password_hash": user.password_hash,
            "is_admin": user.is_admin,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }


def update_user_last_login(user_id: int, timestamp: datetime) -> bool:
    """Update user's last login timestamp.

    Args:
        user_id: User ID
        timestamp: Login timestamp

    Returns:
        True if updated successfully
    """
    with get_session() as session:
        user = session.get(User, user_id)
        if not user:
            return False

        user.last_login_at = timestamp
        session.commit()
        return True


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

    with get_session() as session:
        result = session.execute(
            text("""
                INSERT INTO security_audit_log
                (user_id, event_type, success, ip_address, user_agent, metadata)
                VALUES (:user_id, :event_type, :success, :ip_address, :user_agent, :metadata::jsonb)
                RETURNING id
            """),
            {
                "user_id": user_id,
                "event_type": event_type,
                "success": success,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "metadata": json.dumps(metadata or {}),
            },
        )
        log_id = result.scalar_one()
        session.commit()
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

    with get_session() as session:
        result = session.execute(
            text("""
                INSERT INTO gmail_processing_errors
                (connection_id, sync_job_id, message_id, receipt_id,
                 error_stage, error_type, error_message, stack_trace,
                 error_context, is_retryable)
                VALUES (:connection_id, :sync_job_id, :message_id, :receipt_id,
                        :error_stage, :error_type, :error_message, :stack_trace,
                        :error_context::jsonb, :is_retryable)
                RETURNING id
            """),
            {
                "connection_id": connection_id,
                "sync_job_id": sync_job_id,
                "message_id": message_id,
                "receipt_id": receipt_id,
                "error_stage": error_stage,
                "error_type": error_type,
                "error_message": error_message,
                "stack_trace": stack_trace,
                "error_context": json.dumps(error_context or {}),
                "is_retryable": is_retryable,
            },
        )
        error_id = result.scalar_one()
        session.commit()
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
    with get_session() as session:
        stmt = (
            insert(GmailParseStatistic)
            .values(
                connection_id=connection_id,
                sync_job_id=sync_job_id,
                message_id=message_id,
                sender_domain=sender_domain,
                merchant_normalized=merchant_normalized,
                parse_method=parse_method,
                merchant_extracted=merchant_extracted,
                brand_extracted=brand_extracted,
                amount_extracted=amount_extracted,
                date_extracted=date_extracted,
                order_id_extracted=order_id_extracted,
                line_items_extracted=line_items_extracted,
                match_attempted=match_attempted,
                match_success=match_success,
                match_confidence=match_confidence,
                parse_duration_ms=parse_duration_ms,
                llm_cost_cents=llm_cost_cents,
                parsing_status=parsing_status,
                parsing_error=parsing_error,
            )
            .returning(GmailParseStatistic.id)
        )
        result = session.execute(stmt)
        stat_id = result.scalar_one()
        session.commit()
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
    with get_session() as session:
        job = session.get(GmailSyncJob, sync_job_id)

        if not job:
            return False

        job.stats = json.dumps(stats)

        session.commit()
        return True


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

    with get_session() as session:
        cutoff = datetime.now() - timedelta(days=days)

        # Build WHERE clause dynamically
        where_clauses = ["occurred_at >= :cutoff"]
        params = {"cutoff": cutoff}

        if connection_id:
            where_clauses.append("connection_id = :connection_id")
            params["connection_id"] = connection_id

        if sync_job_id:
            where_clauses.append("sync_job_id = :sync_job_id")
            params["sync_job_id"] = sync_job_id

        where_sql = " AND ".join(where_clauses)

        # Get total count
        total_result = session.execute(
            text(f"""
                SELECT COUNT(*) as total
                FROM gmail_processing_errors
                WHERE {where_sql}
            """),
            params,
        ).fetchone()
        total = total_result[0] if total_result else 0

        # Get errors by stage
        by_stage_results = session.execute(
            text(f"""
                SELECT error_stage, COUNT(*) as count
                FROM gmail_processing_errors
                WHERE {where_sql}
                GROUP BY error_stage
                ORDER BY count DESC
            """),
            params,
        ).fetchall()
        by_stage = {row[0]: row[1] for row in by_stage_results}

        # Get errors by type
        by_type_results = session.execute(
            text(f"""
                SELECT error_type, COUNT(*) as count
                FROM gmail_processing_errors
                WHERE {where_sql}
                GROUP BY error_type
                ORDER BY count DESC
            """),
            params,
        ).fetchall()
        by_type = {row[0]: row[1] for row in by_type_results}

        # Get retryable count
        retryable_result = session.execute(
            text(f"""
                SELECT COUNT(*) as count
                FROM gmail_processing_errors
                WHERE {where_sql} AND is_retryable = TRUE
            """),
            params,
        ).fetchone()
        retryable_count = retryable_result[0] if retryable_result else 0

        # Get recent errors
        recent_results = session.execute(
            text(f"""
                SELECT id, error_stage, error_type, error_message,
                       message_id, occurred_at, is_retryable
                FROM gmail_processing_errors
                WHERE {where_sql}
                ORDER BY occurred_at DESC
                LIMIT 20
            """),
            params,
        ).fetchall()

        recent_errors = []
        for row in recent_results:
            error = {
                "id": row[0],
                "error_stage": row[1],
                "error_type": row[2],
                "error_message": row[3],
                "message_id": row[4],
                "occurred_at": row[5].isoformat() if row[5] else None,
                "is_retryable": row[6],
            }
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

    cutoff = datetime.now() - timedelta(days=days)

    with get_session() as session:
        # Build query with dynamic filters
        query = session.query(
            GmailParseStatistic.merchant_normalized,
            GmailParseStatistic.sender_domain,
            GmailParseStatistic.parse_method,
            func.count().label("total_attempts"),
            func.sum(
                case((GmailParseStatistic.parsing_status == "parsed", 1), else_=0)
            ).label("parsed_count"),
            func.sum(
                case((GmailParseStatistic.parsing_status != "parsed", 1), else_=0)
            ).label("failed_count"),
            func.sum(
                case((GmailParseStatistic.merchant_extracted.is_(True), 1), else_=0)
            ).label("merchant_extracted_count"),
            func.sum(
                case((GmailParseStatistic.brand_extracted.is_(True), 1), else_=0)
            ).label("brand_extracted_count"),
            func.sum(
                case((GmailParseStatistic.amount_extracted.is_(True), 1), else_=0)
            ).label("amount_extracted_count"),
            func.sum(
                case((GmailParseStatistic.date_extracted.is_(True), 1), else_=0)
            ).label("date_extracted_count"),
            func.sum(
                case((GmailParseStatistic.order_id_extracted.is_(True), 1), else_=0)
            ).label("order_id_extracted_count"),
            func.sum(
                case((GmailParseStatistic.line_items_extracted.is_(True), 1), else_=0)
            ).label("line_items_extracted_count"),
            func.sum(
                case((GmailParseStatistic.match_attempted.is_(True), 1), else_=0)
            ).label("match_attempted_count"),
            func.sum(
                case((GmailParseStatistic.match_success.is_(True), 1), else_=0)
            ).label("match_success_count"),
            func.avg(GmailParseStatistic.match_confidence).label(
                "avg_match_confidence"
            ),
            func.avg(GmailParseStatistic.parse_duration_ms).label(
                "avg_parse_duration_ms"
            ),
            func.sum(func.coalesce(GmailParseStatistic.llm_cost_cents, 0)).label(
                "total_llm_cost_cents"
            ),
        ).filter(GmailParseStatistic.created_at >= cutoff)

        # Apply optional filters
        if connection_id:
            query = query.filter(GmailParseStatistic.connection_id == connection_id)

        if merchant:
            query = query.filter(GmailParseStatistic.merchant_normalized == merchant)

        if parse_method:
            query = query.filter(GmailParseStatistic.parse_method == parse_method)

        # Group and order
        results = (
            query.group_by(
                GmailParseStatistic.merchant_normalized,
                GmailParseStatistic.sender_domain,
                GmailParseStatistic.parse_method,
            )
            .order_by(text("total_attempts DESC"))
            .all()
        )

        stats = []
        for row in results:
            stat = {
                "merchant_normalized": row.merchant_normalized,
                "sender_domain": row.sender_domain,
                "parse_method": row.parse_method,
                "total_attempts": int(row.total_attempts or 0),
                "parsed_count": int(row.parsed_count or 0),
                "failed_count": int(row.failed_count or 0),
                "merchant_extracted_count": int(row.merchant_extracted_count or 0),
                "brand_extracted_count": int(row.brand_extracted_count or 0),
                "amount_extracted_count": int(row.amount_extracted_count or 0),
                "date_extracted_count": int(row.date_extracted_count or 0),
                "order_id_extracted_count": int(row.order_id_extracted_count or 0),
                "line_items_extracted_count": int(row.line_items_extracted_count or 0),
                "match_attempted_count": int(row.match_attempted_count or 0),
                "match_success_count": int(row.match_success_count or 0),
                "avg_match_confidence": row.avg_match_confidence,
                "avg_parse_duration_ms": row.avg_parse_duration_ms,
                "total_llm_cost_cents": int(row.total_llm_cost_cents or 0),
            }

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
