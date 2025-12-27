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
"""

from .base import get_db
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


# ============================================================================
# TRUELAYER BANK CONNECTION FUNCTIONS
# ============================================================================

def get_user_connections(user_id):
    """Get all active TrueLayer bank connections for a user."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, user_id, provider_id, provider_name, access_token, refresh_token,
                       token_expires_at, connection_status, last_synced_at, created_at
                FROM bank_connections
                WHERE user_id = %s AND connection_status = 'active'
                ORDER BY created_at DESC
            ''', (user_id,))
            return cursor.fetchall()


def get_connection(connection_id):
    """Get a specific TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, user_id, provider_id, access_token, refresh_token,
                       token_expires_at, connection_status, last_synced_at, created_at
                FROM bank_connections
                WHERE id = %s
            ''', (connection_id,))
            return cursor.fetchone()


def get_connection_accounts(connection_id):
    """Get all accounts linked to a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, connection_id, account_id, display_name, account_type,
                       currency, last_synced_at, created_at
                FROM truelayer_accounts
                WHERE connection_id = %s
                ORDER BY display_name
            ''', (connection_id,))
            return cursor.fetchall()


def get_account_by_truelayer_id(truelayer_account_id):
    """Get account from database by TrueLayer account ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, connection_id, account_id, display_name, account_type,
                       currency, created_at
                FROM truelayer_accounts
                WHERE account_id = %s
            ''', (truelayer_account_id,))
            return cursor.fetchone()


def save_bank_connection(user_id, provider_id, access_token, refresh_token, expires_at):
    """Save a TrueLayer bank connection (create or update)."""
    # Format provider_id as a friendly name (e.g., "santander_uk" -> "Santander Uk")
    provider_name = (provider_id or '').replace('_', ' ').title() if provider_id else 'Unknown Bank'

    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO bank_connections
                (user_id, provider_id, provider_name, access_token, refresh_token, token_expires_at, connection_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'active')
                ON CONFLICT (user_id, provider_id) DO UPDATE
                SET access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    token_expires_at = EXCLUDED.token_expires_at,
                    provider_name = EXCLUDED.provider_name,
                    connection_status = 'active',
                    updated_at = NOW()
                RETURNING id
            ''', (user_id, provider_id, provider_name, access_token, refresh_token, expires_at))
            connection_id = cursor.fetchone()[0]
            conn.commit()
            return connection_id


def update_connection_status(connection_id, status):
    """Update the status of a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bank_connections
                SET connection_status = %s
                WHERE id = %s
            ''', (status, connection_id))
            conn.commit()
            return cursor.rowcount > 0


def update_connection_provider_name(connection_id, provider_name):
    """Update the provider_name for a bank connection (e.g., 'Santander UK')."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bank_connections
                SET provider_name = %s, updated_at = NOW()
                WHERE id = %s
            ''', (provider_name, connection_id))
            conn.commit()
            return cursor.rowcount > 0


def update_connection_provider(connection_id, provider_id=None, provider_name=None):
    """Update provider_id and/or provider_name for a bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            updates = []
            params = []

            if provider_id:
                updates.append('provider_id = %s')
                params.append(provider_id)
            if provider_name:
                updates.append('provider_name = %s')
                params.append(provider_name)

            if not updates:
                return False

            updates.append('updated_at = NOW()')
            params.append(connection_id)

            cursor.execute(f'''
                UPDATE bank_connections
                SET {', '.join(updates)}
                WHERE id = %s
            ''', tuple(params))
            conn.commit()
            return cursor.rowcount > 0


def update_connection_last_synced(connection_id, timestamp):
    """Update the last sync timestamp for a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bank_connections
                SET last_synced_at = %s
                WHERE id = %s
            ''', (timestamp, connection_id))
            conn.commit()
            return cursor.rowcount > 0


def update_connection_tokens(connection_id, access_token, refresh_token, expires_at):
    """Update tokens for a TrueLayer bank connection (after refresh)."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bank_connections
                SET access_token = %s, refresh_token = %s, token_expires_at = %s
                WHERE id = %s
            ''', (access_token, refresh_token, expires_at, connection_id))
            conn.commit()
            return cursor.rowcount > 0


def update_account_last_synced(account_id, timestamp):
    """Update the last sync timestamp for a specific TrueLayer account."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_accounts
                SET last_synced_at = %s, updated_at = NOW()
                WHERE id = %s
            ''', (timestamp, account_id))
            conn.commit()
            return cursor.rowcount > 0


def save_connection_account(connection_id, account_id, display_name, account_type, account_subtype=None, currency=None):
    """Save an account linked to a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_accounts
                (connection_id, account_id, display_name, account_type, currency)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (connection_id, account_id) DO UPDATE
                SET display_name = EXCLUDED.display_name, account_type = EXCLUDED.account_type, updated_at = NOW()
                RETURNING id
            ''', (connection_id, account_id, display_name, account_type, currency))
            account_db_id = cursor.fetchone()[0]
            conn.commit()
            return account_db_id


def get_truelayer_transaction_by_id(normalised_provider_id):
    """Check if a TrueLayer transaction already exists (deduplication)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, account_id, normalised_provider_transaction_id, timestamp,
                       description, amount, merchant_name, transaction_category
                FROM truelayer_transactions
                WHERE normalised_provider_transaction_id = %s
            ''', (str(normalised_provider_id),))
            return cursor.fetchone()


def get_truelayer_transaction_by_pk(transaction_id):
    """Get a TrueLayer transaction by primary key (id column)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT * FROM truelayer_transactions WHERE id = %s
            ''', (transaction_id,))
            return cursor.fetchone()


def insert_truelayer_transaction(account_id, transaction_id, normalised_provider_id,
                                 timestamp, description, amount, currency, transaction_type,
                                 transaction_category, merchant_name, running_balance, metadata,
                                 pre_enrichment_status='None'):
    """Insert a new transaction from TrueLayer.

    Args:
        pre_enrichment_status: Pre-enrichment matching status. One of:
            'None' (default), 'Matched', 'Apple', 'AMZN', 'AMZN RTN'
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO truelayer_transactions
                    (account_id, transaction_id, normalised_provider_transaction_id, timestamp,
                     description, amount, currency, transaction_type, transaction_category,
                     merchant_name, running_balance, metadata, pre_enrichment_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (account_id, transaction_id, normalised_provider_id, timestamp,
                      description, amount, currency, transaction_type, transaction_category,
                      merchant_name, running_balance, json.dumps(metadata), pre_enrichment_status))
                txn_id = cursor.fetchone()[0]
                conn.commit()
                return txn_id
            except Exception as e:
                conn.rollback()
                print(f"Error inserting TrueLayer transaction: {e}")
                return None


def get_all_truelayer_transactions(account_id=None):
    """Get all transactions synced from TrueLayer."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if account_id:
                cursor.execute('''
                    SELECT id, account_id, transaction_id, normalised_provider_transaction_id,
                           timestamp, description, amount, currency, transaction_type,
                           transaction_category, merchant_name, running_balance,
                           pre_enrichment_status, metadata, created_at
                    FROM truelayer_transactions
                    WHERE account_id = %s
                    ORDER BY timestamp DESC
                ''', (account_id,))
            else:
                cursor.execute('''
                    SELECT id, account_id, transaction_id, normalised_provider_transaction_id,
                           timestamp, description, amount, currency, transaction_type,
                           transaction_category, merchant_name, running_balance,
                           pre_enrichment_status, metadata, created_at
                    FROM truelayer_transactions
                    ORDER BY timestamp DESC
                ''')
            return cursor.fetchall()


def get_all_truelayer_transactions_with_enrichment(account_id=None):
    """Get all transactions with enrichment in SINGLE query (eliminates N+1 problem)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = '''
                SELECT
                    id, account_id, transaction_id, normalised_provider_transaction_id,
                    timestamp, description, amount, currency, transaction_type,
                    transaction_category, merchant_name, running_balance,
                    pre_enrichment_status, metadata, created_at,
                    enrichment_required,
                    -- Extract enrichment from JSONB in single query
                    metadata->'enrichment'->>'primary_category' as enrichment_primary_category,
                    metadata->'enrichment'->>'subcategory' as enrichment_subcategory,
                    metadata->'enrichment'->>'merchant_clean_name' as enrichment_merchant_clean_name,
                    metadata->'enrichment'->>'merchant_type' as enrichment_merchant_type,
                    metadata->'enrichment'->>'essential_discretionary' as enrichment_essential_discretionary,
                    metadata->'enrichment'->>'payment_method' as enrichment_payment_method,
                    metadata->'enrichment'->>'payment_method_subtype' as enrichment_payment_method_subtype,
                    metadata->'enrichment'->>'confidence_score' as enrichment_confidence_score,
                    metadata->'enrichment'->>'llm_provider' as enrichment_llm_provider,
                    metadata->'enrichment'->>'llm_model' as enrichment_llm_model,
                    (metadata->'enrichment'->>'enriched_at')::timestamp as enrichment_enriched_at,
                    metadata->>'huququllah_classification' as manual_huququllah_classification
                FROM truelayer_transactions
            '''

            if account_id:
                cursor.execute(query + ' WHERE account_id = %s ORDER BY timestamp DESC', (account_id,))
            else:
                cursor.execute(query + ' ORDER BY timestamp DESC')

            return cursor.fetchall()


def insert_webhook_event(event_id, event_type, payload, signature=None, processed=False):
    """Store an incoming TrueLayer webhook event for audit trail."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_webhook_events
                (event_id, event_type, payload, signature, processed)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (event_id, event_type, str(payload), signature, processed))
            webhook_id = cursor.fetchone()[0]
            conn.commit()
            return webhook_id


def mark_webhook_processed(event_id):
    """Mark a webhook event as processed."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_webhook_events
                SET processed = true, processed_at = NOW()
                WHERE event_id = %s
            ''', (event_id,))
            conn.commit()
            return cursor.rowcount > 0


def get_webhook_events(processed_only=False):
    """Get webhook events from database."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if processed_only:
                cursor.execute('''
                    SELECT id, event_id, event_type, payload, signature,
                           processed, created_at, processed_at
                    FROM truelayer_webhook_events
                    WHERE processed = true
                    ORDER BY created_at DESC
                    LIMIT 100
                ''')
            else:
                cursor.execute('''
                    SELECT id, event_id, event_type, payload, signature,
                           processed, created_at, processed_at
                    FROM truelayer_webhook_events
                    ORDER BY created_at DESC
                    LIMIT 100
                ''')
            return cursor.fetchall()


def insert_balance_snapshot(account_id, current_balance, currency, snapshot_at):
    """Store a balance snapshot from TrueLayer."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_balance_snapshots
                (account_id, current_balance, currency, snapshot_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (account_id, current_balance, currency, snapshot_at))
            snapshot_id = cursor.fetchone()[0]
            conn.commit()
            return snapshot_id


def get_latest_balance_snapshots(account_id=None, limit=10):
    """Get the latest balance snapshots."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if account_id:
                cursor.execute('''
                    SELECT id, account_id, current_balance, currency, snapshot_at
                    FROM truelayer_balance_snapshots
                    WHERE account_id = %s
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                ''', (account_id, limit))
            else:
                cursor.execute('''
                    SELECT id, account_id, current_balance, currency, snapshot_at
                    FROM truelayer_balance_snapshots
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                ''', (limit,))
            return cursor.fetchall()


def save_connection_card(connection_id, card_id, card_name, card_type, last_four=None, issuer=None):
    """Save a card linked to a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_cards
                (connection_id, card_id, card_name, card_type, last_four, issuer, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'active')
                ON CONFLICT (connection_id, card_id) DO UPDATE
                SET card_name = EXCLUDED.card_name, card_type = EXCLUDED.card_type, updated_at = NOW()
                RETURNING id
            ''', (connection_id, card_id, card_name, card_type, last_four, issuer))
            card_db_id = cursor.fetchone()[0]
            conn.commit()
            return card_db_id


def get_connection_cards(connection_id):
    """Get all cards linked to a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, connection_id, card_id, card_name, card_type,
                       last_four, issuer, status, last_synced_at, created_at
                FROM truelayer_cards
                WHERE connection_id = %s
                ORDER BY card_name
            ''', (connection_id,))
            return cursor.fetchall()


def get_card_by_truelayer_id(truelayer_card_id):
    """Get card from database by TrueLayer card ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, connection_id, card_id, card_name, card_type,
                       last_four, issuer, status, created_at
                FROM truelayer_cards
                WHERE card_id = %s
            ''', (truelayer_card_id,))
            return cursor.fetchone()


def update_card_last_synced(card_id, timestamp):
    """Update the last sync timestamp for a specific TrueLayer card."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_cards
                SET last_synced_at = %s, updated_at = NOW()
                WHERE id = %s
            ''', (timestamp, card_id))
            conn.commit()
            return cursor.rowcount > 0


def get_card_transaction_by_id(normalised_provider_id):
    """Check if a TrueLayer card transaction already exists (deduplication)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, card_id, normalised_provider_id, timestamp,
                       description, amount, merchant_name, category
                FROM truelayer_card_transactions
                WHERE normalised_provider_id = %s
            ''', (normalised_provider_id,))
            return cursor.fetchone()


def insert_truelayer_card_transaction(card_id, transaction_id, normalised_provider_id,
                                      timestamp, description, amount, currency, transaction_type,
                                      transaction_category, merchant_name, running_balance, metadata):
    """Insert a new card transaction from TrueLayer."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO truelayer_card_transactions
                    (card_id, transaction_id, normalised_provider_id, timestamp,
                     description, amount, currency, transaction_type, category,
                     merchant_name, running_balance, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (card_id, transaction_id, normalised_provider_id, timestamp,
                      description, amount, currency, transaction_type, transaction_category,
                      merchant_name, running_balance, str(metadata)))
                txn_id = cursor.fetchone()[0]
                conn.commit()
                return txn_id
            except Exception as e:
                conn.rollback()
                print(f"Error inserting TrueLayer card transaction: {e}")
                return None


def get_all_truelayer_card_transactions(card_id=None):
    """Get all card transactions synced from TrueLayer."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if card_id:
                cursor.execute('''
                    SELECT id, card_id, transaction_id, normalised_provider_id,
                           timestamp, description, amount, currency, transaction_type,
                           category, merchant_name, running_balance, metadata, created_at
                    FROM truelayer_card_transactions
                    WHERE card_id = %s
                    ORDER BY timestamp DESC
                ''', (card_id,))
            else:
                cursor.execute('''
                    SELECT id, card_id, transaction_id, normalised_provider_id,
                           timestamp, description, amount, currency, transaction_type,
                           category, merchant_name, running_balance, metadata, created_at
                    FROM truelayer_card_transactions
                    ORDER BY timestamp DESC
                ''')
            return cursor.fetchall()


def insert_card_balance_snapshot(card_id, current_balance, currency, snapshot_at):
    """Store a balance snapshot from TrueLayer card."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_card_balance_snapshots
                (card_id, current_balance, currency, snapshot_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (card_id, current_balance, currency, snapshot_at))
            snapshot_id = cursor.fetchone()[0]
            conn.commit()
            return snapshot_id


def get_latest_card_balance_snapshots(card_id=None, limit=10):
    """Get the latest balance snapshots for cards."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if card_id:
                cursor.execute('''
                    SELECT id, card_id, current_balance, currency, snapshot_at
                    FROM truelayer_card_balance_snapshots
                    WHERE card_id = %s
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                ''', (card_id, limit))
            else:
                cursor.execute('''
                    SELECT id, card_id, current_balance, currency, snapshot_at
                    FROM truelayer_card_balance_snapshots
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                ''', (limit,))
            return cursor.fetchall()


def store_oauth_state(user_id, state, code_verifier):
    """Store OAuth state and code_verifier temporarily for callback verification."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO oauth_state (user_id, state, code_verifier, expires_at)
                VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')
                ON CONFLICT (state) DO UPDATE SET
                  code_verifier = EXCLUDED.code_verifier,
                  expires_at = EXCLUDED.expires_at
            ''', (user_id, state, code_verifier))
            conn.commit()


def get_oauth_state(state):
    """Retrieve stored OAuth state and code_verifier."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT user_id, state, code_verifier
                FROM oauth_state
                WHERE state = %s AND expires_at > NOW()
            ''', (state,))
            return cursor.fetchone()


def delete_oauth_state(state):
    """Delete OAuth state after use."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM oauth_state WHERE state = %s', (state,))
            conn.commit()


# ============================================================================
# TrueLayer Import Job Management Functions (Phase 1)
# ============================================================================

def create_import_job(user_id, connection_id=None, job_type='date_range',
                     from_date=None, to_date=None, account_ids=None,
                     card_ids=None, auto_enrich=True, batch_size=50):
    """
    Create new import job and return job_id.

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
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_import_jobs
                (user_id, connection_id, job_type, from_date, to_date,
                 account_ids, card_ids, auto_enrich, batch_size, job_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
                RETURNING id
            ''', (user_id, connection_id, job_type, from_date, to_date,
                  account_ids or [], card_ids or [], auto_enrich, batch_size))
            job_id = cursor.fetchone()[0]
            conn.commit()
            return job_id


def get_import_job(job_id):
    """Get import job details by ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT * FROM truelayer_import_jobs WHERE id = %s
            ''', (job_id,))
            return cursor.fetchone()


def update_import_job_status(job_id, status, estimated_completion=None, error_message=None):
    """
    Update job status.

    Args:
        job_id: Job ID
        status: 'pending', 'running', 'completed', 'failed', 'enriching'
        estimated_completion: ISO datetime string
        error_message: Error details if failed
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            if status == 'running':
                cursor.execute('''
                    UPDATE truelayer_import_jobs
                    SET job_status = %s, started_at = CURRENT_TIMESTAMP,
                        estimated_completion = %s
                    WHERE id = %s
                ''', (status, estimated_completion, job_id))
            elif status in ('completed', 'failed'):
                cursor.execute('''
                    UPDATE truelayer_import_jobs
                    SET job_status = %s, completed_at = CURRENT_TIMESTAMP,
                        error_message = %s
                    WHERE id = %s
                ''', (status, error_message, job_id))
            else:
                cursor.execute('''
                    UPDATE truelayer_import_jobs
                    SET job_status = %s
                    WHERE id = %s
                ''', (status, job_id))
            conn.commit()


def add_import_progress(job_id, account_id, synced, duplicates, errors, error_msg=None):
    """Record per-account progress."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
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
            ''', (job_id, account_id, synced, duplicates, errors, error_msg))
            conn.commit()


def get_import_progress(job_id):
    """Get all per-account progress for a job."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
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
            ''', (job_id,))
            return cursor.fetchall()


def mark_job_completed(job_id, total_synced, total_duplicates, total_errors):
    """Mark job as completed with final counts."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_import_jobs
                SET job_status = 'completed',
                    completed_at = CURRENT_TIMESTAMP,
                    total_transactions_synced = %s,
                    total_transactions_duplicates = %s,
                    total_transactions_errors = %s
                WHERE id = %s
            ''', (total_synced, total_duplicates, total_errors, job_id))
            conn.commit()


def get_user_import_history(user_id, limit=50):
    """Get recent import jobs for user."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
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
            ''', (user_id, limit))
            return cursor.fetchall()


def get_job_transaction_ids(job_id):
    """Get all transaction IDs that were imported in a job."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT ARRAY_AGG(DISTINCT id)
                FROM truelayer_transactions
                WHERE import_job_id = %s
            ''', (job_id,))
            result = cursor.fetchone()
            return result[0] or [] if result else []


def create_enrichment_job(user_id, import_job_id=None, transaction_ids=None):
    """Create enrichment job and return job_id."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_enrichment_jobs
                (user_id, import_job_id, transaction_ids, job_status, total_transactions)
                VALUES (%s, %s, %s, 'pending', %s)
                RETURNING id
            ''', (user_id, import_job_id, transaction_ids or [], len(transaction_ids or [])))
            job_id = cursor.fetchone()[0]
            conn.commit()
            return job_id


def update_enrichment_job(job_id, status, successful=None, failed=None, cost=None, tokens=None):
    """Update enrichment job progress."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            if status == 'running':
                cursor.execute('''
                    UPDATE truelayer_enrichment_jobs
                    SET job_status = %s, started_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (status, job_id))
            elif status in ('completed', 'failed'):
                cursor.execute('''
                    UPDATE truelayer_enrichment_jobs
                    SET job_status = %s,
                        completed_at = CURRENT_TIMESTAMP,
                        successful_enrichments = %s,
                        failed_enrichments = %s,
                        total_cost = %s,
                        total_tokens = %s
                    WHERE id = %s
                ''', (status, successful, failed, cost, tokens, job_id))
            conn.commit()


def get_unenriched_truelayer_transactions():
    """Get all TrueLayer transactions without enrichment."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT t.*
                FROM truelayer_transactions t
                WHERE metadata->'enrichment' IS NULL
                ORDER BY t.timestamp DESC
            ''')
            return cursor.fetchall()


def get_transaction_enrichment(transaction_id):
    """Get enrichment data for a specific transaction from TrueLayer metadata JSONB."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check TrueLayer transactions metadata JSONB
            cursor.execute('''
                SELECT
                    metadata->'enrichment'->>'primary_category' as primary_category,
                    metadata->'enrichment'->>'subcategory' as subcategory,
                    metadata->'enrichment'->>'merchant_clean_name' as merchant_clean_name,
                    metadata->'enrichment'->>'merchant_type' as merchant_type,
                    metadata->'enrichment'->>'essential_discretionary' as essential_discretionary,
                    metadata->'enrichment'->>'payment_method' as payment_method,
                    metadata->'enrichment'->>'payment_method_subtype' as payment_method_subtype,
                    metadata->'enrichment'->>'confidence_score' as confidence_score,
                    metadata->'enrichment'->>'llm_provider' as llm_provider,
                    metadata->'enrichment'->>'llm_model' as llm_model,
                    (metadata->'enrichment'->>'enriched_at')::timestamp as enriched_at
                FROM truelayer_transactions
                WHERE id = %s AND metadata->>'enrichment' IS NOT NULL
                LIMIT 1
            ''', (transaction_id,))
            result = cursor.fetchone()
            if result:
                # Convert confidence_score to numeric if it exists
                if result.get('confidence_score'):
                    try:
                        result['confidence_score'] = float(result['confidence_score'])
                    except (ValueError, TypeError):
                        result['confidence_score'] = None
            return result


def count_enriched_truelayer_transactions():
    """Count TrueLayer transactions that have been enriched."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM truelayer_transactions
                WHERE metadata->'enrichment' IS NOT NULL
            ''')
            result = cursor.fetchone()
            return result[0] if result else 0


# ============================================================================
