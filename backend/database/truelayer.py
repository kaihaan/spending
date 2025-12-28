"""
TrueLayer Integration - Database Operations

Handles all database operations for TrueLayer bank connections, accounts,
cards, and transactions.

Modules:
- Bank connection management (save_bank_connection, get_bank_connection, etc.)
- Account operations (save_account, get_accounts, etc.)
- Card operations (save_card, get_cards, etc.)
- Transaction operations (insert_truelayer_transaction, get_all_truelayer_transactions, etc.)
- Import job tracking (create_import_job, update_import_job_status, etc.)

NOTE: Some functions reference tables without models (cards, webhooks, oauth_state, import_jobs).
      These functions are marked with TODO and require model creation before conversion.
"""

from datetime import UTC

from sqlalchemy import and_, cast, func, literal_column
from sqlalchemy.dialects.postgresql import TIMESTAMP, insert

from .base import get_session
from .models.truelayer import (
    BankConnection,
    TrueLayerAccount,
    TrueLayerBalance,
    TrueLayerTransaction,
)

# ============================================================================
# TRUELAYER BANK CONNECTION FUNCTIONS
# ============================================================================


def get_user_connections(user_id):
    """Get all active TrueLayer bank connections for a user."""
    with get_session() as session:
        connections = (
            session.query(BankConnection)
            .filter(
                and_(
                    BankConnection.user_id == user_id,
                    BankConnection.connection_status == "active",
                )
            )
            .order_by(BankConnection.created_at.desc())
            .all()
        )
        return [
            {
                "id": c.id,
                "user_id": c.user_id,
                "provider_id": c.provider_id,
                "provider_name": c.provider_name,
                "access_token": c.access_token,
                "refresh_token": c.refresh_token,
                "token_expires_at": c.token_expires_at,
                "connection_status": c.connection_status,
                "last_synced_at": c.last_synced_at,
                "created_at": c.created_at,
            }
            for c in connections
        ]


def get_connection(connection_id):
    """Get a specific TrueLayer bank connection."""
    with get_session() as session:
        connection = session.get(BankConnection, connection_id)
        if not connection:
            return None
        return {
            "id": connection.id,
            "user_id": connection.user_id,
            "provider_id": connection.provider_id,
            "access_token": connection.access_token,
            "refresh_token": connection.refresh_token,
            "token_expires_at": connection.token_expires_at,
            "connection_status": connection.connection_status,
            "last_synced_at": connection.last_synced_at,
            "created_at": connection.created_at,
        }


def get_connection_accounts(connection_id):
    """Get all accounts linked to a TrueLayer bank connection."""
    with get_session() as session:
        accounts = (
            session.query(TrueLayerAccount)
            .filter(TrueLayerAccount.connection_id == connection_id)
            .order_by(TrueLayerAccount.display_name)
            .all()
        )
        return [
            {
                "id": a.id,
                "connection_id": a.connection_id,
                "account_id": a.account_id,
                "display_name": a.display_name,
                "account_type": a.account_type,
                "currency": a.currency,
                "last_synced_at": a.last_synced_at,
                "created_at": a.created_at,
            }
            for a in accounts
        ]


def get_account_by_truelayer_id(truelayer_account_id):
    """Get account from database by TrueLayer account ID."""
    with get_session() as session:
        account = (
            session.query(TrueLayerAccount)
            .filter(TrueLayerAccount.account_id == truelayer_account_id)
            .first()
        )
        if not account:
            return None
        return {
            "id": account.id,
            "connection_id": account.connection_id,
            "account_id": account.account_id,
            "display_name": account.display_name,
            "account_type": account.account_type,
            "currency": account.currency,
            "created_at": account.created_at,
        }


def save_bank_connection(user_id, provider_id, access_token, refresh_token, expires_at):
    """Save a TrueLayer bank connection (create or update)."""
    # Format provider_id as a friendly name (e.g., "santander_uk" -> "Santander Uk")
    provider_name = (
        (provider_id or "").replace("_", " ").title() if provider_id else "Unknown Bank"
    )

    with get_session() as session:
        # Use PostgreSQL INSERT ... ON CONFLICT for upsert
        stmt = insert(BankConnection).values(
            user_id=user_id,
            provider_id=provider_id,
            provider_name=provider_name,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
            connection_status="active",
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id", "provider_id"],
            set_={
                "access_token": stmt.excluded.access_token,
                "refresh_token": stmt.excluded.refresh_token,
                "token_expires_at": stmt.excluded.token_expires_at,
                "provider_name": stmt.excluded.provider_name,
                "connection_status": "active",
                "updated_at": func.now(),
            },
        ).returning(BankConnection.id)

        result = session.execute(stmt)
        connection_id = result.scalar_one()
        session.commit()
        return connection_id


def update_connection_status(connection_id, status):
    """Update the status of a TrueLayer bank connection."""
    with get_session() as session:
        connection = session.get(BankConnection, connection_id)
        if not connection:
            return False
        connection.connection_status = status
        session.commit()
        return True


def update_connection_provider_name(connection_id, provider_name):
    """Update the provider_name for a bank connection (e.g., 'Santander UK')."""
    with get_session() as session:
        connection = session.get(BankConnection, connection_id)
        if not connection:
            return False
        connection.provider_name = provider_name
        session.commit()
        return True


def update_connection_provider(connection_id, provider_id=None, provider_name=None):
    """Update provider_id and/or provider_name for a bank connection."""
    if not provider_id and not provider_name:
        return False

    with get_session() as session:
        connection = session.get(BankConnection, connection_id)
        if not connection:
            return False

        if provider_id:
            connection.provider_id = provider_id
        if provider_name:
            connection.provider_name = provider_name

        session.commit()
        return True


def update_connection_last_synced(connection_id, timestamp):
    """Update the last sync timestamp for a TrueLayer bank connection."""
    with get_session() as session:
        connection = session.get(BankConnection, connection_id)
        if not connection:
            return False
        connection.last_synced_at = timestamp
        session.commit()
        return True


def update_connection_tokens(connection_id, access_token, refresh_token, expires_at):
    """Update tokens for a TrueLayer bank connection (after refresh)."""
    with get_session() as session:
        connection = session.get(BankConnection, connection_id)
        if not connection:
            return False
        connection.access_token = access_token
        connection.refresh_token = refresh_token
        connection.token_expires_at = expires_at
        session.commit()
        return True


def update_account_last_synced(account_id, timestamp):
    """Update the last sync timestamp for a specific TrueLayer account."""
    with get_session() as session:
        account = session.get(TrueLayerAccount, account_id)
        if not account:
            return False
        account.last_synced_at = timestamp
        session.commit()
        return True


def save_connection_account(
    connection_id,
    account_id,
    display_name,
    account_type,
    account_subtype=None,
    currency=None,
):
    """Save an account linked to a TrueLayer bank connection."""
    with get_session() as session:
        # Use PostgreSQL INSERT ... ON CONFLICT for upsert
        stmt = insert(TrueLayerAccount).values(
            connection_id=connection_id,
            account_id=account_id,
            display_name=display_name,
            account_type=account_type,
            currency=currency,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["connection_id", "account_id"],
            set_={
                "display_name": stmt.excluded.display_name,
                "account_type": stmt.excluded.account_type,
                "updated_at": func.now(),
            },
        ).returning(TrueLayerAccount.id)

        result = session.execute(stmt)
        account_db_id = result.scalar_one()
        session.commit()
        return account_db_id


def get_truelayer_transaction_by_id(normalised_provider_id):
    """Check if a TrueLayer transaction already exists (deduplication)."""
    with get_session() as session:
        transaction = (
            session.query(TrueLayerTransaction)
            .filter(
                TrueLayerTransaction.normalised_provider_transaction_id
                == str(normalised_provider_id)
            )
            .first()
        )
        if not transaction:
            return None
        return {
            "id": transaction.id,
            "account_id": transaction.account_id,
            "normalised_provider_transaction_id": transaction.normalised_provider_transaction_id,
            "timestamp": transaction.timestamp,
            "description": transaction.description,
            "amount": transaction.amount,
            "merchant_name": transaction.merchant_name,
            "transaction_category": transaction.transaction_category,
        }


def get_truelayer_transaction_by_pk(transaction_id):
    """Get a TrueLayer transaction by primary key (id column)."""
    with get_session() as session:
        transaction = session.get(TrueLayerTransaction, transaction_id)
        if not transaction:
            return None
        return {
            "id": transaction.id,
            "account_id": transaction.account_id,
            "transaction_id": transaction.transaction_id,
            "normalised_provider_transaction_id": transaction.normalised_provider_transaction_id,
            "timestamp": transaction.timestamp,
            "description": transaction.description,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "transaction_type": transaction.transaction_type,
            "transaction_category": transaction.transaction_category,
            "merchant_name": transaction.merchant_name,
            "running_balance": transaction.running_balance,
            "pre_enrichment_status": transaction.pre_enrichment_status,
            "metadata": transaction.metadata_,
            "created_at": transaction.created_at,
        }


def insert_truelayer_transaction(
    account_id,
    transaction_id,
    normalised_provider_id,
    timestamp,
    description,
    amount,
    currency,
    transaction_type,
    transaction_category,
    merchant_name,
    running_balance,
    metadata,
    pre_enrichment_status="None",
):
    """Insert a new transaction from TrueLayer.

    Args:
        pre_enrichment_status: Pre-enrichment matching status. One of:
            'None' (default), 'Matched', 'Apple', 'AMZN', 'AMZN RTN'
    """
    with get_session() as session:
        try:
            new_transaction = TrueLayerTransaction(
                account_id=account_id,
                transaction_id=transaction_id,
                normalised_provider_transaction_id=normalised_provider_id,
                timestamp=timestamp,
                description=description,
                amount=amount,
                currency=currency,
                transaction_type=transaction_type,
                transaction_category=transaction_category,
                merchant_name=merchant_name,
                running_balance=running_balance,
                metadata_=metadata,  # Note: metadata_ not metadata
                pre_enrichment_status=pre_enrichment_status,
            )
            session.add(new_transaction)
            session.flush()  # Flush to get the ID
            txn_id = new_transaction.id
            session.commit()
            return txn_id
        except Exception as e:
            session.rollback()
            print(f"Error inserting TrueLayer transaction: {e}")
            return None


def get_all_truelayer_transactions(account_id=None):
    """Get all transactions synced from TrueLayer."""
    with get_session() as session:
        query = session.query(TrueLayerTransaction)

        if account_id:
            query = query.filter(TrueLayerTransaction.account_id == account_id)

        transactions = query.order_by(TrueLayerTransaction.timestamp.desc()).all()

        return [
            {
                "id": t.id,
                "account_id": t.account_id,
                "transaction_id": t.transaction_id,
                "normalised_provider_transaction_id": t.normalised_provider_transaction_id,
                "timestamp": t.timestamp,
                "description": t.description,
                "amount": t.amount,
                "currency": t.currency,
                "transaction_type": t.transaction_type,
                "transaction_category": t.transaction_category,
                "merchant_name": t.merchant_name,
                "running_balance": t.running_balance,
                "pre_enrichment_status": t.pre_enrichment_status,
                "metadata": t.metadata_,
                "created_at": t.created_at,
            }
            for t in transactions
        ]


def get_all_truelayer_transactions_with_enrichment(account_id=None):
    """Get all transactions with enrichment in SINGLE query (eliminates N+1 problem)."""
    with get_session() as session:
        # Build query with JOINs and JSONB field extraction
        query = session.query(
            TrueLayerTransaction,
            # Extract enrichment fields from JSONB using text()
            literal_column("metadata->'enrichment'->>'primary_category'").label(
                "enrichment_primary_category"
            ),
            literal_column("metadata->'enrichment'->>'subcategory'").label(
                "enrichment_subcategory"
            ),
            literal_column("metadata->'enrichment'->>'merchant_clean_name'").label(
                "enrichment_merchant_clean_name"
            ),
            literal_column("metadata->'enrichment'->>'merchant_type'").label(
                "enrichment_merchant_type"
            ),
            literal_column("metadata->'enrichment'->>'essential_discretionary'").label(
                "enrichment_essential_discretionary"
            ),
            literal_column("metadata->'enrichment'->>'payment_method'").label(
                "enrichment_payment_method"
            ),
            literal_column("metadata->'enrichment'->>'payment_method_subtype'").label(
                "enrichment_payment_method_subtype"
            ),
            literal_column("metadata->'enrichment'->>'confidence_score'").label(
                "enrichment_confidence_score"
            ),
            literal_column("metadata->'enrichment'->>'llm_provider'").label(
                "enrichment_llm_provider"
            ),
            literal_column("metadata->'enrichment'->>'llm_model'").label(
                "enrichment_llm_model"
            ),
            cast(
                literal_column("metadata->'enrichment'->>'enriched_at'"), TIMESTAMP
            ).label("enrichment_enriched_at"),
            literal_column("metadata->>'huququllah_classification'").label(
                "manual_huququllah_classification"
            ),
        )

        if account_id:
            query = query.filter(TrueLayerTransaction.account_id == account_id)

        results = query.order_by(TrueLayerTransaction.timestamp.desc()).all()

        # Convert to dictionaries
        return [
            {
                "id": r.TrueLayerTransaction.id,
                "account_id": r.TrueLayerTransaction.account_id,
                "transaction_id": r.TrueLayerTransaction.transaction_id,
                "normalised_provider_transaction_id": r.TrueLayerTransaction.normalised_provider_transaction_id,
                "timestamp": r.TrueLayerTransaction.timestamp,
                "description": r.TrueLayerTransaction.description,
                "amount": r.TrueLayerTransaction.amount,
                "currency": r.TrueLayerTransaction.currency,
                "transaction_type": r.TrueLayerTransaction.transaction_type,
                "transaction_category": r.TrueLayerTransaction.transaction_category,
                "merchant_name": r.TrueLayerTransaction.merchant_name,
                "running_balance": r.TrueLayerTransaction.running_balance,
                "pre_enrichment_status": r.TrueLayerTransaction.pre_enrichment_status,
                "metadata": r.TrueLayerTransaction.metadata_,
                "created_at": r.TrueLayerTransaction.created_at,
                "enrichment_required": r.TrueLayerTransaction.enrichment_required
                if hasattr(r.TrueLayerTransaction, "enrichment_required")
                else None,
                "category": r.enrichment_primary_category,  # Use enrichment data
                "subcategory": r.enrichment_subcategory,  # Use enrichment data
                "enrichment_primary_category": r.enrichment_primary_category,
                "enrichment_subcategory": r.enrichment_subcategory,
                "enrichment_merchant_clean_name": r.enrichment_merchant_clean_name,
                "enrichment_merchant_type": r.enrichment_merchant_type,
                "enrichment_essential_discretionary": r.enrichment_essential_discretionary,
                "enrichment_payment_method": r.enrichment_payment_method,
                "enrichment_payment_method_subtype": r.enrichment_payment_method_subtype,
                "enrichment_confidence_score": r.enrichment_confidence_score,
                "enrichment_llm_provider": r.enrichment_llm_provider,
                "enrichment_llm_model": r.enrichment_llm_model,
                "enrichment_enriched_at": r.enrichment_enriched_at,
                "manual_huququllah_classification": r.manual_huququllah_classification,
            }
            for r in results
        ]


# ============================================================================
# WEBHOOK EVENT FUNCTIONS (NOT CONVERTED - REQUIRES MODEL CREATION)
# ============================================================================
# TODO: These functions reference 'truelayer_webhook_events' table which has no
#       corresponding SQLAlchemy model. Create WebhookEvent model first, then convert.


def insert_webhook_event(event_id, event_type, payload, signature, processed=False):
    """Insert a new TrueLayer webhook event.

    Converted to SQLAlchemy.
    """
    import json

    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import WebhookEvent

    with get_session() as session:
        stmt = (
            insert(WebhookEvent)
            .values(
                event_id=event_id,
                event_type=event_type,
                payload=payload if isinstance(payload, dict) else json.loads(payload),
                signature=signature,
                processed=processed,
            )
            .returning(WebhookEvent.id)
        )
        result = session.execute(stmt)
        webhook_id = result.scalar_one()
        session.commit()
        return webhook_id


def mark_webhook_processed(event_id):
    """Mark a webhook event as processed.

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from sqlalchemy import update

    from .base import get_session
    from .models.truelayer import WebhookEvent

    with get_session() as session:
        stmt = (
            update(WebhookEvent)
            .where(WebhookEvent.event_id == event_id)
            .values(processed=True, processed_at=datetime.now(UTC))
        )
        result = session.execute(stmt)
        session.commit()
        return result.rowcount > 0


def get_webhook_events(processed_only=False):
    """Get webhook events from database.

    Converted to SQLAlchemy.
    """
    from .base import get_session
    from .models.truelayer import WebhookEvent

    with get_session() as session:
        query = session.query(WebhookEvent)

        if processed_only:
            query = query.filter(WebhookEvent.processed.is_(True))

        # Order by created_at DESC, limit 100
        query = query.order_by(WebhookEvent.received_at.desc()).limit(100)

        events = query.all()

        # Convert to dicts
        return [
            {
                "id": e.id,
                "event_id": e.event_id,
                "event_type": e.event_type,
                "payload": e.payload,
                "signature": e.signature,
                "processed": e.processed,
                "received_at": e.received_at,
                "processed_at": e.processed_at,
            }
            for e in events
        ]


def insert_balance_snapshot(account_id, current_balance, currency, snapshot_at):
    """Store a balance snapshot from TrueLayer.

    NOTE: Uses TrueLayerBalance model (maps to truelayer_balances table).
    """
    with get_session() as session:
        new_snapshot = TrueLayerBalance(
            account_id=account_id,
            current_balance=current_balance,
            currency=currency,
            snapshot_at=snapshot_at,
        )
        session.add(new_snapshot)
        session.flush()  # Flush to get the ID
        snapshot_id = new_snapshot.id
        session.commit()
        return snapshot_id


def get_latest_balance_snapshots(account_id=None, limit=10):
    """Get the latest balance snapshots.

    NOTE: Uses TrueLayerBalance model (maps to truelayer_balances table).
    """
    with get_session() as session:
        query = session.query(TrueLayerBalance)

        if account_id:
            query = query.filter(TrueLayerBalance.account_id == account_id)

        snapshots = (
            query.order_by(TrueLayerBalance.snapshot_at.desc()).limit(limit).all()
        )

        return [
            {
                "id": s.id,
                "account_id": s.account_id,
                "current_balance": s.current_balance,
                "currency": s.currency,
                "snapshot_at": s.snapshot_at,
            }
            for s in snapshots
        ]


# ============================================================================
# CARD FUNCTIONS (NOT CONVERTED - REQUIRES MODEL CREATION)
# ============================================================================
# TODO: These functions reference 'truelayer_cards', 'truelayer_card_transactions',
#       and 'truelayer_card_balance_snapshots' tables which have no corresponding
#       SQLAlchemy models. Create Card models first, then convert.


def save_connection_card(
    connection_id, card_id, card_name, card_type, last_four, issuer
):
    """Save or update a TrueLayer card for a connection.

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import TrueLayerCard

    with get_session() as session:
        stmt = (
            insert(TrueLayerCard)
            .values(
                connection_id=connection_id,
                card_id=card_id,
                card_name=card_name,
                card_type=card_type,
                last_four=last_four,
                issuer=issuer,
                status="active",
            )
            .on_conflict_do_update(
                index_elements=["connection_id", "card_id"],
                set_={
                    "card_name": card_name,
                    "card_type": card_type,
                    "updated_at": datetime.now(UTC),
                },
            )
            .returning(TrueLayerCard.id)
        )
        result = session.execute(stmt)
        card_db_id = result.scalar_one()
        session.commit()
        return card_db_id


def get_connection_cards(connection_id):
    """Get all cards linked to a TrueLayer bank connection.

    Converted to SQLAlchemy.
    """
    from .base import get_session
    from .models.truelayer import TrueLayerCard

    with get_session() as session:
        cards = (
            session.query(TrueLayerCard)
            .filter(TrueLayerCard.connection_id == connection_id)
            .order_by(TrueLayerCard.card_name)
            .all()
        )

        return [
            {
                "id": c.id,
                "connection_id": c.connection_id,
                "card_id": c.card_id,
                "card_name": c.card_name,
                "card_type": c.card_type,
                "last_four": c.last_four,
                "issuer": c.issuer,
                "status": c.status,
                "last_synced_at": c.last_synced_at,
                "created_at": c.created_at,
            }
            for c in cards
        ]


def get_card_by_truelayer_id(truelayer_card_id):
    """Get card from database by TrueLayer card ID.

    Converted to SQLAlchemy.
    """
    from .base import get_session
    from .models.truelayer import TrueLayerCard

    with get_session() as session:
        card = (
            session.query(TrueLayerCard)
            .filter(TrueLayerCard.card_id == truelayer_card_id)
            .first()
        )

        if not card:
            return None

        return {
            "id": card.id,
            "connection_id": card.connection_id,
            "card_id": card.card_id,
            "card_name": card.card_name,
            "card_type": card.card_type,
            "last_four": card.last_four,
            "issuer": card.issuer,
            "status": card.status,
            "created_at": card.created_at,
        }


def update_card_last_synced(card_id, timestamp):
    """Update the last sync timestamp for a specific TrueLayer card.

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from .base import get_session
    from .models.truelayer import TrueLayerCard

    with get_session() as session:
        card = session.get(TrueLayerCard, card_id)
        if not card:
            return False

        card.last_synced_at = timestamp
        card.updated_at = datetime.now(UTC)
        session.commit()
        return True


def get_card_transaction_by_id(normalised_provider_id):
    """Check if a TrueLayer card transaction already exists (deduplication).

    Converted to SQLAlchemy.
    """
    from .base import get_session
    from .models.truelayer import TrueLayerCardTransaction

    with get_session() as session:
        txn = (
            session.query(TrueLayerCardTransaction)
            .filter(
                TrueLayerCardTransaction.normalised_provider_id
                == normalised_provider_id
            )
            .first()
        )

        if not txn:
            return None

        return {
            "id": txn.id,
            "card_id": txn.card_id,
            "normalised_provider_id": txn.normalised_provider_id,
            "timestamp": txn.timestamp,
            "description": txn.description,
            "amount": txn.amount,
            "merchant_name": txn.merchant_name,
            "category": txn.category,
        }


def insert_truelayer_card_transaction(
    card_id,
    transaction_id,
    normalised_provider_id,
    timestamp,
    description,
    amount,
    currency,
    transaction_type,
    category,
    merchant_name,
    running_balance,
    metadata,
):
    """Insert a new card transaction from TrueLayer.

    Converted to SQLAlchemy.
    """
    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import TrueLayerCardTransaction

    with get_session() as session:
        try:
            stmt = (
                insert(TrueLayerCardTransaction)
                .values(
                    card_id=card_id,
                    transaction_id=transaction_id,
                    normalised_provider_id=normalised_provider_id,
                    timestamp=timestamp,
                    description=description,
                    amount=amount,
                    currency=currency,
                    transaction_type=transaction_type,
                    category=category,
                    merchant_name=merchant_name,
                    running_balance=running_balance,
                    metadata=str(metadata)
                    if metadata
                    else None,  # Note: TEXT not JSONB
                )
                .returning(TrueLayerCardTransaction.id)
            )
            result = session.execute(stmt)
            txn_id = result.scalar_one()
            session.commit()
            return txn_id
        except Exception as e:
            session.rollback()
            print(f"Error inserting card transaction: {e}")
            return None


def get_all_truelayer_card_transactions(card_id=None):
    """Get TrueLayer card transactions (all or for specific card).

    Converted to SQLAlchemy.
    """
    from .base import get_session
    from .models.truelayer import TrueLayerCardTransaction

    with get_session() as session:
        query = session.query(TrueLayerCardTransaction)

        if card_id:
            query = query.filter(TrueLayerCardTransaction.card_id == card_id)

        query = query.order_by(TrueLayerCardTransaction.timestamp.desc())

        transactions = query.all()

        return [
            {
                "id": t.id,
                "card_id": t.card_id,
                "transaction_id": t.transaction_id,
                "normalised_provider_id": t.normalised_provider_id,
                "timestamp": t.timestamp,
                "description": t.description,
                "amount": t.amount,
                "currency": t.currency,
                "transaction_type": t.transaction_type,
                "category": t.category,
                "merchant_name": t.merchant_name,
                "running_balance": t.running_balance,
                "metadata": t.metadata,
                "created_at": t.created_at,
            }
            for t in transactions
        ]


def insert_card_balance_snapshot(card_id, current_balance, currency, snapshot_at):
    """Store a balance snapshot from TrueLayer card.

    Converted to SQLAlchemy.
    """
    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import TrueLayerCardBalanceSnapshot

    with get_session() as session:
        stmt = (
            insert(TrueLayerCardBalanceSnapshot)
            .values(
                card_id=card_id,
                current_balance=current_balance,
                currency=currency,
                snapshot_at=snapshot_at,
            )
            .returning(TrueLayerCardBalanceSnapshot.id)
        )
        result = session.execute(stmt)
        snapshot_id = result.scalar_one()
        session.commit()
        return snapshot_id


def get_latest_card_balance_snapshots(card_id=None, limit=10):
    """Get the latest balance snapshots for cards.

    Converted to SQLAlchemy.
    """
    from .base import get_session
    from .models.truelayer import TrueLayerCardBalanceSnapshot

    with get_session() as session:
        query = session.query(TrueLayerCardBalanceSnapshot)

        if card_id:
            query = query.filter(TrueLayerCardBalanceSnapshot.card_id == card_id)

        query = query.order_by(TrueLayerCardBalanceSnapshot.snapshot_at.desc()).limit(
            limit
        )

        snapshots = query.all()

        return [
            {
                "id": s.id,
                "card_id": s.card_id,
                "current_balance": s.current_balance,
                "currency": s.currency,
                "snapshot_at": s.snapshot_at,
            }
            for s in snapshots
        ]


# ============================================================================
# OAUTH STATE FUNCTIONS (NOT CONVERTED - REQUIRES MODEL CREATION)
# ============================================================================
# TODO: These functions reference 'oauth_state' table which has no corresponding
#       SQLAlchemy model. Create OAuthState model first, then convert.


def store_oauth_state(user_id, state, code_verifier):
    """Store OAuth state for CSRF protection (with 10-minute expiry).

    Converted to SQLAlchemy.
    """
    from datetime import datetime, timedelta

    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import OAuthState

    with get_session() as session:
        expires_at = datetime.now() + timedelta(minutes=10)

        stmt = (
            insert(OAuthState)
            .values(
                user_id=user_id,
                state=state,
                code_verifier=code_verifier,
                expires_at=expires_at,
            )
            .on_conflict_do_update(
                index_elements=["state"],
                set_={
                    "code_verifier": code_verifier,
                    "expires_at": expires_at,
                },
            )
        )
        session.execute(stmt)
        session.commit()


def get_oauth_state(state):
    """Retrieve stored OAuth state and code_verifier.

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from .base import get_session
    from .models.truelayer import OAuthState

    with get_session() as session:
        oauth_state = (
            session.query(OAuthState)
            .filter(
                OAuthState.state == state,
                OAuthState.expires_at > datetime.now(),  # Note: WITHOUT timezone
            )
            .first()
        )

        if not oauth_state:
            return None

        return {
            "user_id": oauth_state.user_id,
            "state": oauth_state.state,
            "code_verifier": oauth_state.code_verifier,
        }


def delete_oauth_state(state):
    """Delete OAuth state after use.

    Converted to SQLAlchemy.
    """
    from sqlalchemy import delete

    from .base import get_session
    from .models.truelayer import OAuthState

    with get_session() as session:
        stmt = delete(OAuthState).where(OAuthState.state == state)
        session.execute(stmt)
        session.commit()


# ============================================================================
# IMPORT JOB TRACKING FUNCTIONS (NOT CONVERTED - REQUIRES MODEL CREATION)
# ============================================================================
# TODO: These functions reference 'truelayer_import_jobs' and 'enrichment_jobs'
#       tables which have no corresponding SQLAlchemy models. Create ImportJob
#       and EnrichmentJob models first, then convert.


def create_import_job(
    user_id,
    connection_id=None,
    job_type="date_range",
    from_date=None,
    to_date=None,
    account_ids=None,
    card_ids=None,
    auto_enrich=True,
    batch_size=50,
):
    """Create a new TrueLayer import job.

    Args:
        user_id: User ID
        connection_id: Bank connection ID (optional)
        job_type: 'date_range', 'incremental', or 'full_sync'
        from_date: Start date for date_range imports
        to_date: End date for date_range imports
        account_ids: List of account IDs to sync (empty = all)
        card_ids: List of card IDs to sync (empty = all)
        auto_enrich: Whether to enrich after import
        batch_size: Transactions per batch

    Returns:
        int: Created job ID

    Converted to SQLAlchemy.
    """
    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import TrueLayerImportJob

    with get_session() as session:
        stmt = (
            insert(TrueLayerImportJob)
            .values(
                user_id=user_id,
                connection_id=connection_id,
                job_type=job_type,
                from_date=from_date,
                to_date=to_date,
                account_ids=account_ids or [],
                card_ids=card_ids or [],
                auto_enrich=auto_enrich,
                batch_size=batch_size,
                job_status="pending",
            )
            .returning(TrueLayerImportJob.id)
        )
        result = session.execute(stmt)
        job_id = result.scalar_one()
        session.commit()
        return job_id


def get_import_job(job_id):
    """Get import job by ID.

    Converted to SQLAlchemy.
    """
    from .base import get_session
    from .models.truelayer import TrueLayerImportJob

    with get_session() as session:
        job = session.get(TrueLayerImportJob, job_id)

        if not job:
            return None

        return {
            "id": job.id,
            "user_id": job.user_id,
            "connection_id": job.connection_id,
            "job_status": job.job_status,
            "job_type": job.job_type,
            "from_date": job.from_date,
            "to_date": job.to_date,
            "account_ids": job.account_ids,
            "card_ids": job.card_ids,
            "total_accounts": job.total_accounts,
            "total_transactions_synced": job.total_transactions_synced,
            "total_transactions_duplicates": job.total_transactions_duplicates,
            "total_transactions_errors": job.total_transactions_errors,
            "auto_enrich": job.auto_enrich,
            "enrich_after_completion": job.enrich_after_completion,
            "enrichment_job_id": job.enrichment_job_id,
            "batch_size": job.batch_size,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "estimated_completion": job.estimated_completion,
            "metadata": job.metadata_,
            "error_message": job.error_message,
        }


def update_import_job_status(
    job_id, status, estimated_completion=None, error_message=None
):
    """
    Update job status.

    Args:
        job_id: Job ID
        status: 'pending', 'running', 'completed', 'failed', 'enriching'
        estimated_completion: Estimated completion time
        error_message: Error message if failed

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from .base import get_session
    from .models.truelayer import TrueLayerImportJob

    with get_session() as session:
        job = session.get(TrueLayerImportJob, job_id)
        if not job:
            return

        job.job_status = status

        if status == "running":
            job.started_at = datetime.now(UTC)
            if estimated_completion:
                job.estimated_completion = estimated_completion
        elif status in ("completed", "failed"):
            job.completed_at = datetime.now(UTC)
            if error_message:
                job.error_message = error_message
        elif status == "enriching":
            # No additional fields to set
            pass

        session.commit()


def add_import_progress(job_id, account_id, synced, duplicates, errors, error_msg=None):
    """Record per-account progress.

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import TrueLayerImportProgress

    with get_session() as session:
        stmt = (
            insert(TrueLayerImportProgress)
            .values(
                job_id=job_id,
                account_id=account_id,
                progress_status="completed",
                synced_count=synced,
                duplicates_count=duplicates,
                errors_count=errors,
                error_message=error_msg,
            )
            .on_conflict_do_update(
                index_elements=["job_id", "account_id"],  # Need composite index
                set_={
                    "progress_status": "completed",
                    "synced_count": synced,
                    "duplicates_count": duplicates,
                    "errors_count": errors,
                    "error_message": error_msg,
                    "completed_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                },
            )
        )
        session.execute(stmt)
        session.commit()


def get_import_progress(job_id):
    """Get progress for all accounts in a job.

    Converted to SQLAlchemy.
    """

    from .base import get_session
    from .models.truelayer import TrueLayerAccount, TrueLayerImportProgress

    with get_session() as session:
        # LEFT JOIN with truelayer_accounts to get account info
        results = (
            session.query(
                TrueLayerImportProgress,
                TrueLayerAccount.display_name,
                TrueLayerAccount.account_id,
                TrueLayerAccount.account_type,
                TrueLayerAccount.currency,
            )
            .outerjoin(
                TrueLayerAccount,
                TrueLayerImportProgress.account_id == TrueLayerAccount.id,
            )
            .filter(TrueLayerImportProgress.job_id == job_id)
            .order_by(TrueLayerImportProgress.created_at)
            .all()
        )

        return [
            {
                "id": p.id,
                "job_id": p.job_id,
                "account_id": p.account_id,
                "progress_status": p.progress_status,
                "synced_count": p.synced_count,
                "duplicates_count": p.duplicates_count,
                "errors_count": p.errors_count,
                "started_at": p.started_at,
                "completed_at": p.completed_at,
                "error_message": p.error_message,
                "metadata": p.metadata_,
                "created_at": p.created_at,
                "updated_at": p.updated_at,
                # Account info from JOIN
                "display_name": display_name,
                "account_id_truelayer": account_id_tl,
                "account_type": account_type,
                "currency": currency,
            }
            for p, display_name, account_id_tl, account_type, currency in results
        ]


def mark_job_completed(job_id, total_synced, total_duplicates, total_errors):
    """Mark job as completed with final counts.

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from .base import get_session
    from .models.truelayer import TrueLayerImportJob

    with get_session() as session:
        job = session.get(TrueLayerImportJob, job_id)
        if not job:
            return

        job.job_status = "completed"
        job.completed_at = datetime.now(UTC)
        job.total_transactions_synced = total_synced
        job.total_transactions_duplicates = total_duplicates
        job.total_transactions_errors = total_errors

        session.commit()


def get_user_import_history(user_id, limit=50):
    """Get recent import jobs for user.

    Converted to SQLAlchemy.
    """
    from sqlalchemy import case, distinct, func

    from .base import get_session
    from .models.truelayer import TrueLayerImportJob, TrueLayerImportProgress

    with get_session() as session:
        # Complex aggregation query - using COUNT FILTER
        results = (
            session.query(
                TrueLayerImportJob,
                func.count(
                    distinct(
                        case(
                            (
                                TrueLayerImportProgress.progress_status == "completed",
                                TrueLayerImportProgress.account_id,
                            ),
                            else_=None,
                        )
                    )
                ).label("completed_accounts"),
                func.count(distinct(TrueLayerImportProgress.account_id)).label(
                    "total_accounts"
                ),
            )
            .outerjoin(
                TrueLayerImportProgress,
                TrueLayerImportProgress.job_id == TrueLayerImportJob.id,
            )
            .filter(TrueLayerImportJob.user_id == user_id)
            .group_by(TrueLayerImportJob.id)
            .order_by(TrueLayerImportJob.created_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": job.id,
                "user_id": job.user_id,
                "connection_id": job.connection_id,
                "job_status": job.job_status,
                "job_type": job.job_type,
                "from_date": job.from_date,
                "to_date": job.to_date,
                "account_ids": job.account_ids,
                "card_ids": job.card_ids,
                "total_accounts": job.total_accounts,
                "total_transactions_synced": job.total_transactions_synced,
                "total_transactions_duplicates": job.total_transactions_duplicates,
                "total_transactions_errors": job.total_transactions_errors,
                "auto_enrich": job.auto_enrich,
                "enrich_after_completion": job.enrich_after_completion,
                "enrichment_job_id": job.enrichment_job_id,
                "batch_size": job.batch_size,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "completed_at": job.completed_at,
                "estimated_completion": job.estimated_completion,
                "metadata": job.metadata_,
                "error_message": job.error_message,
                # Aggregated counts
                "completed_accounts": completed_accounts,
                "total_accounts_count": total_accounts_count,
            }
            for job, completed_accounts, total_accounts_count in results
        ]


def get_job_transaction_ids(job_id):
    """Get all transaction IDs that were imported in a job.

    Converted to SQLAlchemy.
    """
    from sqlalchemy import func

    from .base import get_session
    from .models.truelayer import TrueLayerTransaction

    with get_session() as session:
        # ARRAY_AGG to collect distinct IDs
        result = (
            session.query(func.array_agg(TrueLayerTransaction.id.distinct()))
            .filter(TrueLayerTransaction.import_job_id == job_id)
            .first()
        )

        if not result or not result[0]:
            return []

        return result[0]


def create_enrichment_job(user_id, import_job_id=None, transaction_ids=None):
    """Create enrichment job and return job_id.

    Converted to SQLAlchemy.
    """
    from sqlalchemy.dialects.postgresql import insert

    from .base import get_session
    from .models.truelayer import TrueLayerEnrichmentJob

    with get_session() as session:
        stmt = (
            insert(TrueLayerEnrichmentJob)
            .values(
                user_id=user_id,
                import_job_id=import_job_id,
                transaction_ids=transaction_ids or [],
                job_status="pending",
                total_transactions=len(transaction_ids or []),
            )
            .returning(TrueLayerEnrichmentJob.id)
        )
        result = session.execute(stmt)
        job_id = result.scalar_one()
        session.commit()
        return job_id


def update_enrichment_job(
    job_id,
    status=None,
    successful=None,
    failed=None,
    cached=None,
    cost=None,
    tokens=None,
    provider=None,
    model=None,
    error_message=None,
):
    """Update enrichment job progress.

    Converted to SQLAlchemy.
    """
    from datetime import datetime

    from .base import get_session
    from .models.truelayer import TrueLayerEnrichmentJob

    with get_session() as session:
        job = session.get(TrueLayerEnrichmentJob, job_id)
        if not job:
            return

        if status:
            job.job_status = status
            if status == "running":
                job.started_at = datetime.now(UTC)
            elif status in ("completed", "failed"):
                job.completed_at = datetime.now(UTC)

        if successful is not None:
            job.successful_enrichments = successful
        if failed is not None:
            job.failed_enrichments = failed
        if cached is not None:
            job.cached_hits = cached
        if cost is not None:
            job.total_cost = cost
        if tokens is not None:
            job.total_tokens = tokens
        if provider is not None:
            job.llm_provider = provider
        if model is not None:
            job.llm_model = model
        if error_message is not None:
            job.error_message = error_message

        session.commit()


def get_unenriched_truelayer_transactions():
    """Get all TrueLayer transactions without enrichment."""
    with get_session() as session:
        transactions = (
            session.query(TrueLayerTransaction)
            .filter(literal_column("metadata->'enrichment' IS NULL"))
            .order_by(TrueLayerTransaction.timestamp.desc())
            .all()
        )
        return [
            {
                "id": t.id,
                "account_id": t.account_id,
                "transaction_id": t.transaction_id,
                "normalised_provider_transaction_id": t.normalised_provider_transaction_id,
                "timestamp": t.timestamp,
                "description": t.description,
                "amount": t.amount,
                "currency": t.currency,
                "transaction_type": t.transaction_type,
                "transaction_category": t.transaction_category,
                "merchant_name": t.merchant_name,
                "running_balance": t.running_balance,
                "pre_enrichment_status": t.pre_enrichment_status,
                "metadata": t.metadata_,
                "created_at": t.created_at,
            }
            for t in transactions
        ]


def get_transaction_enrichment(transaction_id):
    """Get enrichment data for a specific transaction from TrueLayer metadata JSONB."""
    with get_session() as session:
        # Query with JSONB field extraction
        result = (
            session.query(
                literal_column("metadata->'enrichment'->>'primary_category'").label(
                    "primary_category"
                ),
                literal_column("metadata->'enrichment'->>'subcategory'").label(
                    "subcategory"
                ),
                literal_column("metadata->'enrichment'->>'merchant_clean_name'").label(
                    "merchant_clean_name"
                ),
                literal_column("metadata->'enrichment'->>'merchant_type'").label(
                    "merchant_type"
                ),
                literal_column(
                    "metadata->'enrichment'->>'essential_discretionary'"
                ).label("essential_discretionary"),
                literal_column("metadata->'enrichment'->>'payment_method'").label(
                    "payment_method"
                ),
                literal_column(
                    "metadata->'enrichment'->>'payment_method_subtype'"
                ).label("payment_method_subtype"),
                literal_column("metadata->'enrichment'->>'confidence_score'").label(
                    "confidence_score"
                ),
                literal_column("metadata->'enrichment'->>'llm_provider'").label(
                    "llm_provider"
                ),
                literal_column("metadata->'enrichment'->>'llm_model'").label(
                    "llm_model"
                ),
                cast(
                    literal_column("metadata->'enrichment'->>'enriched_at'"), TIMESTAMP
                ).label("enriched_at"),
            )
            .select_from(TrueLayerTransaction)
            .filter(
                and_(
                    TrueLayerTransaction.id == transaction_id,
                    literal_column("metadata->>'enrichment' IS NOT NULL"),
                )
            )
            .first()
        )

        if not result:
            return None

        enrichment_dict = {
            "primary_category": result.primary_category,
            "subcategory": result.subcategory,
            "merchant_clean_name": result.merchant_clean_name,
            "merchant_type": result.merchant_type,
            "essential_discretionary": result.essential_discretionary,
            "payment_method": result.payment_method,
            "payment_method_subtype": result.payment_method_subtype,
            "confidence_score": result.confidence_score,
            "llm_provider": result.llm_provider,
            "llm_model": result.llm_model,
            "enriched_at": result.enriched_at,
        }

        # Convert confidence_score to float if it exists
        if enrichment_dict.get("confidence_score"):
            try:
                enrichment_dict["confidence_score"] = float(
                    enrichment_dict["confidence_score"]
                )
            except (ValueError, TypeError):
                enrichment_dict["confidence_score"] = None

        return enrichment_dict


def count_enriched_truelayer_transactions():
    """Count TrueLayer transactions that have been enriched."""
    with get_session() as session:
        count = (
            session.query(func.count(TrueLayerTransaction.id))
            .filter(literal_column("metadata->'enrichment' IS NOT NULL"))
            .scalar()
        )
        return count if count is not None else 0


# ============================================================================
