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

from sqlalchemy import and_, cast, func, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, insert

from .base import get_session
from .models.category import NormalizedCategory, NormalizedSubcategory
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
        query = (
            session.query(
                TrueLayerTransaction,
                NormalizedCategory.name.label("category"),
                NormalizedSubcategory.name.label("subcategory"),
                # Extract enrichment fields from JSONB using text()
                text("metadata->'enrichment'->>'primary_category'").label(
                    "enrichment_primary_category"
                ),
                text("metadata->'enrichment'->>'subcategory'").label(
                    "enrichment_subcategory"
                ),
                text("metadata->'enrichment'->>'merchant_clean_name'").label(
                    "enrichment_merchant_clean_name"
                ),
                text("metadata->'enrichment'->>'merchant_type'").label(
                    "enrichment_merchant_type"
                ),
                text("metadata->'enrichment'->>'essential_discretionary'").label(
                    "enrichment_essential_discretionary"
                ),
                text("metadata->'enrichment'->>'payment_method'").label(
                    "enrichment_payment_method"
                ),
                text("metadata->'enrichment'->>'payment_method_subtype'").label(
                    "enrichment_payment_method_subtype"
                ),
                text("metadata->'enrichment'->>'confidence_score'").label(
                    "enrichment_confidence_score"
                ),
                text("metadata->'enrichment'->>'llm_provider'").label(
                    "enrichment_llm_provider"
                ),
                text("metadata->'enrichment'->>'llm_model'").label(
                    "enrichment_llm_model"
                ),
                cast(text("metadata->'enrichment'->>'enriched_at'"), TIMESTAMP).label(
                    "enrichment_enriched_at"
                ),
                text("metadata->>'huququllah_classification'").label(
                    "manual_huququllah_classification"
                ),
            )
            .outerjoin(
                NormalizedCategory,
                TrueLayerTransaction.category_id == NormalizedCategory.id,
            )
            .outerjoin(
                NormalizedSubcategory,
                TrueLayerTransaction.subcategory_id == NormalizedSubcategory.id,
            )
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
                "category": r.category,
                "subcategory": r.subcategory,
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


def insert_webhook_event(
    event_id, event_type, payload, signature=None, processed=False
):
    """Store an incoming TrueLayer webhook event for audit trail.

    TODO: Convert to SQLAlchemy after creating WebhookEvent model.
    """

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO truelayer_webhook_events
                (event_id, event_type, payload, signature, processed)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """,
            (event_id, event_type, str(payload), signature, processed),
        )
        webhook_id = cursor.fetchone()[0]
        conn.commit()
        return webhook_id


def mark_webhook_processed(event_id):
    """Mark a webhook event as processed.

    TODO: Convert to SQLAlchemy after creating WebhookEvent model.
    """
    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE truelayer_webhook_events
                SET processed = true, processed_at = NOW()
                WHERE event_id = %s
            """,
            (event_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_webhook_events(processed_only=False):
    """Get webhook events from database.

    TODO: Convert to SQLAlchemy after creating WebhookEvent model.
    """
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if processed_only:
            cursor.execute("""
                    SELECT id, event_id, event_type, payload, signature,
                           processed, created_at, processed_at
                    FROM truelayer_webhook_events
                    WHERE processed = true
                    ORDER BY created_at DESC
                    LIMIT 100
                """)
        else:
            cursor.execute("""
                    SELECT id, event_id, event_type, payload, signature,
                           processed, created_at, processed_at
                    FROM truelayer_webhook_events
                    ORDER BY created_at DESC
                    LIMIT 100
                """)
        return cursor.fetchall()


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
    connection_id, card_id, card_name, card_type, last_four=None, issuer=None
):
    """Save a card linked to a TrueLayer bank connection.

    TODO: Convert to SQLAlchemy after creating TrueLayerCard model.
    """

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO truelayer_cards
            (connection_id, card_id, card_name, card_type, last_four, issuer, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'active')
            ON CONFLICT (connection_id, card_id) DO UPDATE
            SET card_name = EXCLUDED.card_name, card_type = EXCLUDED.card_type, updated_at = NOW()
            RETURNING id
        """,
            (connection_id, card_id, card_name, card_type, last_four, issuer),
        )
        card_db_id = cursor.fetchone()[0]
        conn.commit()
        return card_db_id


def get_connection_cards(connection_id):
    """Get all cards linked to a TrueLayer bank connection.

    TODO: Convert to SQLAlchemy after creating TrueLayerCard model.
    """
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, connection_id, card_id, card_name, card_type,
                       last_four, issuer, status, last_synced_at, created_at
                FROM truelayer_cards
                WHERE connection_id = %s
                ORDER BY card_name
            """,
            (connection_id,),
        )
        return cursor.fetchall()


def get_card_by_truelayer_id(truelayer_card_id):
    """Get card from database by TrueLayer card ID."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, connection_id, card_id, card_name, card_type,
                       last_four, issuer, status, created_at
                FROM truelayer_cards
                WHERE card_id = %s
            """,
            (truelayer_card_id,),
        )
        return cursor.fetchone()


def update_card_last_synced(card_id, timestamp):
    """Update the last sync timestamp for a specific TrueLayer card."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE truelayer_cards
                SET last_synced_at = %s, updated_at = NOW()
                WHERE id = %s
            """,
            (timestamp, card_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_card_transaction_by_id(normalised_provider_id):
    """Check if a TrueLayer card transaction already exists (deduplication)."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT id, card_id, normalised_provider_id, timestamp,
                       description, amount, merchant_name, category
                FROM truelayer_card_transactions
                WHERE normalised_provider_id = %s
            """,
            (normalised_provider_id,),
        )
        return cursor.fetchone()


def insert_truelayer_card_transaction(
    card_id,
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
):
    """Insert a new card transaction from TrueLayer."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        try:
            cursor.execute(
                """
                    INSERT INTO truelayer_card_transactions
                    (card_id, transaction_id, normalised_provider_id, timestamp,
                     description, amount, currency, transaction_type, category,
                     merchant_name, running_balance, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """,
                (
                    card_id,
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
                    str(metadata),
                ),
            )
            txn_id = cursor.fetchone()[0]
            conn.commit()
            return txn_id
        except Exception as e:
            conn.rollback()
            print(f"Error inserting TrueLayer card transaction: {e}")
            return None


def get_all_truelayer_card_transactions(card_id=None):
    """Get all card transactions synced from TrueLayer."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if card_id:
            cursor.execute(
                """
                SELECT id, card_id, transaction_id, normalised_provider_id,
                       timestamp, description, amount, currency, transaction_type,
                       category, merchant_name, running_balance, metadata, created_at
                FROM truelayer_card_transactions
                WHERE card_id = %s
                ORDER BY timestamp DESC
            """,
                (card_id,),
            )
        else:
            cursor.execute("""
                    SELECT id, card_id, transaction_id, normalised_provider_id,
                           timestamp, description, amount, currency, transaction_type,
                           category, merchant_name, running_balance, metadata, created_at
                    FROM truelayer_card_transactions
                    ORDER BY timestamp DESC
                """)
        return cursor.fetchall()


def insert_card_balance_snapshot(card_id, current_balance, currency, snapshot_at):
    """Store a balance snapshot from TrueLayer card."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO truelayer_card_balance_snapshots
                (card_id, current_balance, currency, snapshot_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """,
            (card_id, current_balance, currency, snapshot_at),
        )
        snapshot_id = cursor.fetchone()[0]
        conn.commit()
        return snapshot_id


def get_latest_card_balance_snapshots(card_id=None, limit=10):
    """Get the latest balance snapshots for cards."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        if card_id:
            cursor.execute(
                """
                    SELECT id, card_id, current_balance, currency, snapshot_at
                    FROM truelayer_card_balance_snapshots
                    WHERE card_id = %s
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                """,
                (card_id, limit),
            )
        else:
            cursor.execute(
                """
                    SELECT id, card_id, current_balance, currency, snapshot_at
                    FROM truelayer_card_balance_snapshots
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                """,
                (limit,),
            )
        return cursor.fetchall()


# ============================================================================
# OAUTH STATE FUNCTIONS (NOT CONVERTED - REQUIRES MODEL CREATION)
# ============================================================================
# TODO: These functions reference 'oauth_state' table which has no corresponding
#       SQLAlchemy model. Create OAuthState model first, then convert.


def store_oauth_state(user_id, state, code_verifier):
    """Store OAuth state and code_verifier temporarily for callback verification.

    TODO: Convert to SQLAlchemy after creating OAuthState model.
    """

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO oauth_state (user_id, state, code_verifier, expires_at)
                VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')
                ON CONFLICT (state) DO UPDATE SET
                  code_verifier = EXCLUDED.code_verifier,
                  expires_at = EXCLUDED.expires_at
            """,
            (user_id, state, code_verifier),
        )
        conn.commit()


def get_oauth_state(state):
    """Retrieve stored OAuth state and code_verifier."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT user_id, state, code_verifier
                FROM oauth_state
                WHERE state = %s AND expires_at > NOW()
            """,
            (state,),
        )
        return cursor.fetchone()


def delete_oauth_state(state):
    """Delete OAuth state after use."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM oauth_state WHERE state = %s", (state,))
        conn.commit()


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
    """Create new import job and return job_id.

    TODO: Convert to SQLAlchemy after creating ImportJob model.

    Args:
        user_id: User ID
        connection_id: Bank connection ID
        job_type: 'date_range', 'incremental', or 'full_sync'
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        account_ids: List of account IDs to sync
        card_ids: List of card IDs to sync
        auto_enrich: Whether to auto-enrich after import
        batch_size: Transactions per batch

    Returns:
        job_id (int)
    """

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO truelayer_import_jobs
                (user_id, connection_id, job_type, from_date, to_date,
                 account_ids, card_ids, auto_enrich, batch_size, job_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                RETURNING id
            """,
            (
                user_id,
                connection_id,
                job_type,
                from_date,
                to_date,
                account_ids or [],
                card_ids or [],
                auto_enrich,
                batch_size,
            ),
        )
        job_id = cursor.fetchone()[0]
        conn.commit()
        return job_id


def get_import_job(job_id):
    """Get import job details by ID."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT * FROM truelayer_import_jobs WHERE id = %s
            """,
            (job_id,),
        )
        return cursor.fetchone()


def update_import_job_status(
    job_id, status, estimated_completion=None, error_message=None
):
    """
    Update job status.

    Args:
        job_id: Job ID
        status: 'pending', 'running', 'completed', 'failed', 'enriching'
        estimated_completion: ISO datetime string
        error_message: Error details if failed
    """

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        if status == "running":
            cursor.execute(
                """
                    UPDATE truelayer_import_jobs
                    SET job_status = %s, started_at = CURRENT_TIMESTAMP,
                        estimated_completion = %s
                    WHERE id = %s
                """,
                (status, estimated_completion, job_id),
            )
        elif status in ("completed", "failed"):
            cursor.execute(
                """
                    UPDATE truelayer_import_jobs
                    SET job_status = %s, completed_at = CURRENT_TIMESTAMP,
                        error_message = %s
                    WHERE id = %s
                """,
                (status, error_message, job_id),
            )
        else:
            cursor.execute(
                """
                    UPDATE truelayer_import_jobs
                    SET job_status = %s
                    WHERE id = %s
                """,
                (status, job_id),
            )
        conn.commit()


def add_import_progress(job_id, account_id, synced, duplicates, errors, error_msg=None):
    """Record per-account progress."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                INSERT INTO truelayer_import_progress
                (job_id, account_id, progress_status, synced_count, duplicates_count,
                 errors_count, error_message)
                VALUES (%s, %s, 'completed', %s, %s, %s, %s)
                ON CONFLICT (job_id, account_id) DO UPDATE SET
                  progress_status = 'completed',
                  synced_count = EXCLUDED.synced_count,
                  duplicates_count = EXCLUDED.duplicates_count,
                  errors_count = EXCLUDED.errors_count,
                  error_message = EXCLUDED.error_message,
                  completed_at = CURRENT_TIMESTAMP,
                  updated_at = CURRENT_TIMESTAMP
            """,
            (job_id, account_id, synced, duplicates, errors, error_msg),
        )
        conn.commit()


def get_import_progress(job_id):
    """Get all per-account progress for a job."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
                SELECT
                    p.*,
                    a.display_name,
                    a.account_id,
                    a.account_type,
                    a.currency
                FROM truelayer_import_progress p
                LEFT JOIN truelayer_accounts a ON p.account_id = a.id
                WHERE p.job_id = %s
                ORDER BY p.created_at
            """,
            (job_id,),
        )
        return cursor.fetchall()


def mark_job_completed(job_id, total_synced, total_duplicates, total_errors):
    """Mark job as completed with final counts."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                UPDATE truelayer_import_jobs
                SET job_status = 'completed',
                    completed_at = CURRENT_TIMESTAMP,
                    total_transactions_synced = %s,
                    total_transactions_duplicates = %s,
                    total_transactions_errors = %s
                WHERE id = %s
            """,
            (total_synced, total_duplicates, total_errors, job_id),
        )
        conn.commit()


def get_user_import_history(user_id, limit=50):
    """Get recent import jobs for user."""
    from psycopg2.extras import RealDictCursor

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(
            """
            SELECT
                j.*,
                COUNT(DISTINCT p.account_id) FILTER (WHERE p.progress_status = 'completed')
                    as completed_accounts,
                COUNT(DISTINCT p.account_id) as total_accounts
            FROM truelayer_import_jobs j
            LEFT JOIN truelayer_import_progress p ON p.job_id = j.id
            WHERE j.user_id = %s
            GROUP BY j.id
            ORDER BY j.created_at DESC
            LIMIT %s
        """,
            (user_id, limit),
        )
        return cursor.fetchall()


def get_job_transaction_ids(job_id):
    """Get all transaction IDs that were imported in a job."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                SELECT ARRAY_AGG(DISTINCT id)
                FROM truelayer_transactions
                WHERE import_job_id = %s
            """,
            (job_id,),
        )
        result = cursor.fetchone()
        return result[0] or [] if result else []


def create_enrichment_job(user_id, import_job_id=None, transaction_ids=None):
    """Create enrichment job and return job_id."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO truelayer_enrichment_jobs
            (user_id, import_job_id, transaction_ids, job_status, total_transactions)
            VALUES (%s, %s, %s, 'pending', %s)
            RETURNING id
        """,
            (
                user_id,
                import_job_id,
                transaction_ids or [],
                len(transaction_ids or []),
            ),
        )
        job_id = cursor.fetchone()[0]
        conn.commit()
        return job_id


def update_enrichment_job(
    job_id, status, successful=None, failed=None, cost=None, tokens=None
):
    """Update enrichment job progress."""

    from .base_psycopg2 import get_db

    with get_db() as conn, conn.cursor() as cursor:
        if status == "running":
            cursor.execute(
                """
                    UPDATE truelayer_enrichment_jobs
                    SET job_status = %s, started_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """,
                (status, job_id),
            )
        elif status in ("completed", "failed"):
            cursor.execute(
                """
                    UPDATE truelayer_enrichment_jobs
                    SET job_status = %s,
                        completed_at = CURRENT_TIMESTAMP,
                        successful_enrichments = %s,
                        failed_enrichments = %s,
                        total_cost = %s,
                        total_tokens = %s
                    WHERE id = %s
                """,
                (status, successful, failed, cost, tokens, job_id),
            )
        conn.commit()


def get_unenriched_truelayer_transactions():
    """Get all TrueLayer transactions without enrichment."""
    with get_session() as session:
        transactions = (
            session.query(TrueLayerTransaction)
            .filter(text("metadata->'enrichment' IS NULL"))
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
                text("metadata->'enrichment'->>'primary_category'").label(
                    "primary_category"
                ),
                text("metadata->'enrichment'->>'subcategory'").label("subcategory"),
                text("metadata->'enrichment'->>'merchant_clean_name'").label(
                    "merchant_clean_name"
                ),
                text("metadata->'enrichment'->>'merchant_type'").label("merchant_type"),
                text("metadata->'enrichment'->>'essential_discretionary'").label(
                    "essential_discretionary"
                ),
                text("metadata->'enrichment'->>'payment_method'").label(
                    "payment_method"
                ),
                text("metadata->'enrichment'->>'payment_method_subtype'").label(
                    "payment_method_subtype"
                ),
                text("metadata->'enrichment'->>'confidence_score'").label(
                    "confidence_score"
                ),
                text("metadata->'enrichment'->>'llm_provider'").label("llm_provider"),
                text("metadata->'enrichment'->>'llm_model'").label("llm_model"),
                cast(text("metadata->'enrichment'->>'enriched_at'"), TIMESTAMP).label(
                    "enriched_at"
                ),
            )
            .select_from(TrueLayerTransaction)
            .filter(
                and_(
                    TrueLayerTransaction.id == transaction_id,
                    text("metadata->>'enrichment' IS NOT NULL"),
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
            .filter(text("metadata->'enrichment' IS NOT NULL"))
            .scalar()
        )
        return count if count is not None else 0


# ============================================================================
