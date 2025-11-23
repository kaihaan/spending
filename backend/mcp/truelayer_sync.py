"""
TrueLayer Transaction Sync Module

Handles periodic syncing of transactions from TrueLayer API,
deduplication, and integration with the app's transaction database.
"""

import database_init as database
from .truelayer_client import TrueLayerClient
from datetime import datetime


def sync_account_transactions(
    connection_id: int,
    truelayer_account_id: str,
    db_account_id: int,
    access_token: str,
    days_back: int = 90,
    use_incremental: bool = True
) -> dict:
    """
    Sync transactions from TrueLayer for a specific account.

    Args:
        connection_id: Database connection ID
        truelayer_account_id: TrueLayer account ID (string)
        db_account_id: Database account ID (foreign key to truelayer_accounts.id)
        access_token: Valid OAuth access token
        days_back: Number of days to fetch (fallback if no last_synced_at)
        use_incremental: Use incremental sync based on last_synced_at

    Returns:
        Dictionary with sync results
    """
    try:
        print(f"🔄 Syncing account {truelayer_account_id}...")

        client = TrueLayerClient(access_token)

        # Determine the sync window
        sync_days = days_back
        if use_incremental:
            # Get the connection's last sync timestamp
            connection = database.get_connection(connection_id)
            if connection and connection.get('last_synced_at'):
                last_sync = datetime.fromisoformat(connection['last_synced_at'])
                # Calculate days since last sync
                days_since_sync = (datetime.utcnow() - last_sync).days
                # Only sync new data since last sync (add buffer of 1 day for safety)
                sync_days = max(1, days_since_sync + 1)
                print(f"   📅 Incremental sync: last synced {days_since_sync} days ago, fetching {sync_days} days")
            else:
                print(f"   📅 No previous sync found, fetching full {days_back} days")

        # Fetch transactions from TrueLayer
        transactions = client.fetch_all_transactions(truelayer_account_id, sync_days)

        synced_count = 0
        duplicate_count = 0
        error_count = 0

        if transactions:
            # Insert/update transactions in database
            for txn in transactions:
                try:
                    # Check if transaction already exists (using normalised_provider_id)
                    existing = database.get_truelayer_transaction_by_id(
                        txn.get('normalised_provider_id')
                    )

                    if existing:
                        duplicate_count += 1
                        continue

                    # Insert new transaction
                    txn_id = database.insert_truelayer_transaction(
                        account_id=db_account_id,
                        transaction_id=txn.get('transaction_id'),
                        normalised_provider_id=txn.get('normalised_provider_id'),
                        timestamp=txn.get('date'),
                        description=txn.get('description'),
                        amount=txn.get('amount'),
                        currency=txn.get('currency', 'GBP'),
                        transaction_type=txn.get('transaction_type'),
                        transaction_category=txn.get('category'),
                        merchant_name=txn.get('merchant_name'),
                        running_balance=txn.get('running_balance'),
                        metadata=txn.get('metadata', {})
                    )

                    if txn_id:
                        synced_count += 1
                    else:
                        error_count += 1

                except Exception as e:
                    print(f"❌ Error inserting transaction: {e}")
                    error_count += 1
        else:
            print(f"⚠️  No transactions found for account {truelayer_account_id}")

        # Update account-level sync timestamp (independent of connection status)
        database.update_account_last_synced(db_account_id, datetime.utcnow().isoformat())

        # Also update connection-level timestamp to track overall sync status
        database.update_connection_last_synced(connection_id, datetime.utcnow().isoformat())

        result = {
            'account_id': truelayer_account_id,
            'synced': synced_count,
            'duplicates': duplicate_count,
            'errors': error_count,
            'total_processed': synced_count + duplicate_count,
        }

        print(f"✅ Sync complete: {synced_count} synced, {duplicate_count} duplicates, {error_count} errors")
        return result

    except Exception as e:
        print(f"❌ Sync failed for account {truelayer_account_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'account_id': truelayer_account_id,
            'synced': 0,
            'duplicates': 0,
            'errors': 1,
            'error_message': str(e),
        }


def sync_all_accounts(user_id: int) -> dict:
    """
    Sync transactions for all connected accounts of a user.

    Args:
        user_id: User ID

    Returns:
        Dictionary with aggregate sync results
    """
    print(f"🔄 Starting sync for user {user_id}...")

    # Get all active connections for user
    connections = database.get_user_connections(user_id)

    if not connections:
        print(f"⚠️  No active connections found for user {user_id}")
        return {
            'user_id': user_id,
            'total_accounts': 0,
            'total_synced': 0,
            'accounts': []
        }

    account_results = []

    for connection in connections:
        connection_id = connection.get('id')
        user_id = connection.get('user_id')

        # Get accounts for this connection
        accounts = database.get_connection_accounts(connection_id)

        for account in accounts:
            truelayer_account_id = account.get('account_id')
            db_account_id = account.get('id')  # Database ID
            access_token = decrypt_token(connection.get('access_token'))

            result = sync_account_transactions(
                connection_id=connection_id,
                truelayer_account_id=truelayer_account_id,
                db_account_id=db_account_id,
                access_token=access_token,
            )
            account_results.append(result)

    # Aggregate results
    total_synced = sum(r.get('synced', 0) for r in account_results)
    total_duplicates = sum(r.get('duplicates', 0) for r in account_results)
    total_errors = sum(r.get('errors', 0) for r in account_results)

    return {
        'user_id': user_id,
        'total_accounts': len(account_results),
        'total_synced': total_synced,
        'total_duplicates': total_duplicates,
        'total_errors': total_errors,
        'accounts': account_results,
    }


def handle_webhook_event(event_payload: dict) -> dict:
    """
    Handle incoming TrueLayer webhook event.

    Args:
        event_payload: Webhook event payload

    Returns:
        Dictionary with processing result
    """
    try:
        event_id = event_payload.get('event_id')
        event_type = event_payload.get('event_type')

        print(f"📬 Processing webhook: {event_type} ({event_id})")

        # Store webhook event in database for audit trail
        database.insert_webhook_event(
            event_id=event_id,
            event_type=event_type,
            payload=event_payload,
            signature=None,
            processed=False
        )

        # Handle specific event types
        if event_type == 'transactions_available':
            # Trigger sync for affected account
            connection_id = event_payload.get('connection_id')
            truelayer_account_id = event_payload.get('account_id')

            # Fetch and sync transactions
            connection = database.get_connection(connection_id)
            access_token = decrypt_token(connection.get('access_token'))

            # Look up database account ID
            account = database.get_account_by_truelayer_id(truelayer_account_id)
            if not account:
                print(f"❌ Account not found: {truelayer_account_id}")
                return {
                    'event_id': event_id,
                    'status': 'failed',
                    'error': 'Account not found'
                }

            db_account_id = account.get('id')

            result = sync_account_transactions(
                connection_id=connection_id,
                truelayer_account_id=truelayer_account_id,
                db_account_id=db_account_id,
                access_token=access_token,
            )

            # Mark webhook as processed
            database.mark_webhook_processed(event_id)

            return {
                'event_id': event_id,
                'status': 'processed',
                'sync_result': result
            }

        elif event_type == 'balance_updated':
            # Capture balance snapshot
            connection_id = event_payload.get('connection_id')
            account_id = event_payload.get('account_id')
            balance = event_payload.get('balance')
            currency = event_payload.get('currency', 'GBP')

            database.insert_balance_snapshot(
                account_id=account_id,
                current_balance=balance,
                currency=currency,
                snapshot_at=datetime.utcnow().isoformat()
            )

            database.mark_webhook_processed(event_id)

            return {
                'event_id': event_id,
                'status': 'processed',
                'balance': balance
            }

        else:
            print(f"⚠️  Unknown event type: {event_type}")
            return {
                'event_id': event_id,
                'status': 'unknown_type',
                'event_type': event_type
            }

    except Exception as e:
        print(f"❌ Error processing webhook: {e}")
        return {
            'event_id': event_payload.get('event_id'),
            'status': 'error',
            'error': str(e)
        }


def get_sync_status(user_id: int) -> dict:
    """
    Get sync status for all accounts of a user.

    Args:
        user_id: User ID

    Returns:
        Dictionary with sync status information
    """
    connections = database.get_user_connections(user_id)

    accounts_status = []
    for connection in connections:
        connection_id = connection.get('id')
        accounts = database.get_connection_accounts(connection_id)

        for account in accounts:
            accounts_status.append({
                'account_id': account.get('account_id'),
                'display_name': account.get('display_name'),
                'last_synced_at': connection.get('last_synced_at'),
                'connection_status': connection.get('connection_status'),
            })

    return {
        'user_id': user_id,
        'total_accounts': len(accounts_status),
        'accounts': accounts_status,
    }


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt stored token."""
    from .truelayer_auth import decrypt_token as decrypt
    return decrypt(encrypted_token)
