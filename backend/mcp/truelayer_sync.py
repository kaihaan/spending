"""
TrueLayer Transaction Sync Module

Handles periodic syncing of transactions from TrueLayer API,
deduplication, and integration with the app's transaction database.
"""

import database_postgres as database
from .truelayer_client import TrueLayerClient
from .truelayer_auth import decrypt_token, refresh_access_token, encrypt_token
from datetime import datetime, timezone


def identify_merchant(description: str, merchant_from_api: str = None) -> str:
    """
    Identify merchant from transaction description.

    Prefers TrueLayer API merchant name, falls back to extracting from description.

    Args:
        description: Transaction description text
        merchant_from_api: Merchant name from TrueLayer API (if available)

    Returns:
        Merchant name (or description if no merchant can be identified)
    """
    # If TrueLayer API already provided merchant name, use it
    if merchant_from_api and merchant_from_api.strip():
        return merchant_from_api.strip()

    # Otherwise, try to extract from description (usually first few words)
    # Most merchants appear at the start of the description
    if description:
        # Split by comma or space, take first meaningful part
        parts = description.split(',')
        merchant = parts[0].strip()

        # If merchant looks like a reference number (all digits), use full description
        if merchant and not merchant.isdigit():
            return merchant

    return description or 'Unknown Merchant'


def identify_transaction_merchant(txn: dict) -> dict:
    """
    Identify merchant from transaction data.

    Args:
        txn: Transaction dictionary from normalized data

    Returns:
        Transaction dictionary with updated merchant_name
    """
    # Identify merchant (will be enriched with category via LLM later)
    merchant = identify_merchant(
        txn.get('description', ''),
        txn.get('merchant_name')
    )
    txn['merchant_name'] = merchant
    # Set initial category to 'Other' - will be enriched by LLM
    txn['category'] = 'Other'

    return txn


def sync_account_transactions(
    connection_id: int,
    truelayer_account_id: str,
    db_account_id: int,
    access_token: str,
    days_back: int = 90,
    use_incremental: bool = True,
    from_date = None,
    to_date = None,
    import_job_id: int = None
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
        from_date: Start date for explicit date range (YYYY-MM-DD or date object)
        to_date: End date for explicit date range (YYYY-MM-DD or date object)
        import_job_id: Import job ID to track progress

    Returns:
        Dictionary with sync results
    """
    try:
        print(f"🔄 Syncing account {truelayer_account_id}...")

        client = TrueLayerClient(access_token)

        # Determine the sync window
        sync_days = days_back

        # If explicit date range provided (from Advanced Import), use that instead
        if from_date and to_date:
            from datetime import datetime as dt, date
            # Convert date objects to ISO strings if needed
            from_date_str = from_date.isoformat() if isinstance(from_date, date) else from_date
            to_date_str = to_date.isoformat() if isinstance(to_date, date) else to_date

            # Parse dates and calculate days
            from_dt = dt.strptime(from_date_str, '%Y-%m-%d')
            to_dt = dt.strptime(to_date_str, '%Y-%m-%d')
            days_span = (to_dt - from_dt).days
            sync_days = max(1, days_span)
            print(f"   📅 Explicit date range: {from_date_str} to {to_date_str} ({sync_days} days)")
        elif use_incremental:
            # Get the connection's last sync timestamp
            connection = database.get_connection(connection_id)
            last_synced_at = connection.get('last_synced_at') if connection else None

            try:
                if last_synced_at:
                    # Handle both string and datetime object formats
                    if isinstance(last_synced_at, str):
                        last_sync = datetime.fromisoformat(last_synced_at)
                    else:
                        # If it's already a datetime object, use it directly
                        last_sync = last_synced_at

                    # Ensure we're comparing timezone-aware datetimes
                    # If last_sync is naive, assume UTC
                    if last_sync.tzinfo is None:
                        last_sync = last_sync.replace(tzinfo=timezone.utc)

                    # Get current time in UTC for comparison
                    now_utc = datetime.now(timezone.utc)

                    # Calculate days since last sync
                    days_since_sync = (now_utc - last_sync).days
                    # Only sync new data since last sync (add buffer of 1 day for safety)
                    sync_days = max(1, days_since_sync + 1)
                    print(f"   📅 Incremental sync: last synced {days_since_sync} days ago, fetching {sync_days} days")
                else:
                    print(f"   📅 No previous sync found, fetching full {days_back} days")
            except Exception as e:
                print(f"   ⚠️  Error parsing last_synced_at ({type(last_synced_at).__name__}): {e}")
                print(f"   📅 Falling back to full {days_back} days sync")
                # Fall back to fetching all days

        # Fetch transactions from TrueLayer
        print(f"   📡 Fetching transactions from TrueLayer (last {sync_days} days)...")
        transactions = client.fetch_all_transactions(truelayer_account_id, sync_days)
        print(f"   📦 Received {len(transactions)} transactions from API")

        synced_count = 0
        duplicate_count = 0
        error_count = 0

        if transactions:
            print(f"   🔄 Processing {len(transactions)} transactions...")

            # Insert/update transactions in database
            for idx, txn in enumerate(transactions, 1):
                try:
                    # Check if transaction already exists (using normalised_provider_id)
                    normalised_id = txn.get('normalised_provider_id')
                    existing = database.get_truelayer_transaction_by_id(normalised_id)

                    if existing:
                        duplicate_count += 1
                        if idx <= 3:  # Log first few duplicates
                            print(f"     ⏭️  Transaction {idx}: Duplicate (id: {normalised_id})")
                        continue

                    # Identify merchant (categorization will be done by LLM enricher later)
                    try:
                        txn = identify_transaction_merchant(txn)
                        merchant_name = txn.get('merchant_name')
                        category = txn.get('category')
                        print(f"     📊 Transaction {idx}: {merchant_name} (awaiting LLM enrichment)")
                    except Exception as e:
                        print(f"     ⚠️  Could not identify merchant for transaction {idx}: {e}")
                        # Continue with original merchant/category if identification fails
                        merchant_name = txn.get('merchant_name', 'Unknown Merchant')
                        category = 'Other'

                    # Insert new transaction
                    txn_id = database.insert_truelayer_transaction(
                        account_id=db_account_id,
                        transaction_id=txn.get('transaction_id'),
                        normalised_provider_id=normalised_id,
                        timestamp=txn.get('date'),
                        description=txn.get('description'),
                        amount=txn.get('amount'),
                        currency=txn.get('currency', 'GBP'),
                        transaction_type=txn.get('transaction_type'),
                        transaction_category=category,
                        merchant_name=merchant_name,
                        running_balance=txn.get('running_balance'),
                        metadata=txn.get('metadata', {})
                    )

                    if txn_id:
                        synced_count += 1
                        if idx <= 3:  # Log first few insertions
                            print(f"     ✅ Transaction {idx}: Inserted (id: {normalised_id})")
                    else:
                        error_count += 1
                        print(f"     ❌ Transaction {idx}: Failed to insert (id: {normalised_id})")

                except Exception as e:
                    print(f"     ❌ Transaction {idx}: Error inserting: {e}")
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


def refresh_token_if_needed(connection_id: int, connection: dict) -> dict:
    """
    Check if token is expired and refresh if needed.

    Args:
        connection_id: Database connection ID
        connection: Connection dict with token info

    Returns:
        Updated connection dict with fresh token
    """
    try:
        token_expires_at = connection.get('token_expires_at')

        # Check if token is expired or about to expire (within 5 minutes)
        if token_expires_at:
            try:
                # Parse expiration time
                if isinstance(token_expires_at, str):
                    expires_dt = datetime.fromisoformat(token_expires_at)
                else:
                    expires_dt = token_expires_at

                # Ensure we're comparing timezone-aware datetimes
                # If expires_dt is naive, assume UTC
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)

                # Get current time in UTC
                now_utc = datetime.now(timezone.utc)

                time_until_expiry = (expires_dt - now_utc).total_seconds()

                # If expired or expiring within 5 minutes, refresh
                if time_until_expiry < 300:
                    print(f"   ⏰ Token expires in {time_until_expiry:.0f} seconds - refreshing...")

                    # Decrypt refresh token and refresh
                    encrypted_refresh_token = connection.get('refresh_token')
                    refresh_token = decrypt_token(encrypted_refresh_token)

                    # Call TrueLayer to refresh
                    new_tokens = refresh_access_token(refresh_token)
                    print(f"   ✅ Token refreshed successfully")

                    # Encrypt new tokens
                    new_access_token = encrypt_token(new_tokens['access_token'])
                    new_refresh_token = encrypt_token(new_tokens['refresh_token'])

                    # Update database
                    database.update_connection_tokens(
                        connection_id,
                        new_access_token,
                        new_refresh_token,
                        new_tokens['expires_at']
                    )

                    # Update connection dict
                    connection['access_token'] = new_access_token
                    connection['refresh_token'] = new_refresh_token
                    connection['token_expires_at'] = new_tokens['expires_at']

                    return connection
            except Exception as e:
                print(f"   ⚠️  Could not parse token expiry time: {e}")
                # Continue anyway, let the API call fail if token is actually invalid

        return connection

    except Exception as e:
        print(f"   ⚠️  Token refresh check failed: {e}")
        return connection


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
        user_id_from_conn = connection.get('user_id')
        conn_status = connection.get('connection_status')

        print(f"   📍 Connection {connection_id} - Status: {conn_status}")

        # Refresh token if expired
        connection = refresh_token_if_needed(connection_id, connection)

        # Get accounts for this connection
        accounts = database.get_connection_accounts(connection_id)
        print(f"   📊 Found {len(accounts)} accounts for connection {connection_id}")

        for account in accounts:
            truelayer_account_id = account.get('account_id')
            db_account_id = account.get('id')  # Database ID
            account_display_name = account.get('display_name', 'N/A')

            print(f"     🏦 Account: {account_display_name} (ID: {truelayer_account_id}, DB ID: {db_account_id})")

            try:
                # Decrypt access token
                encrypted_token = connection.get('access_token')
                if not encrypted_token:
                    print(f"     ❌ No access token found for connection {connection_id}")
                    account_results.append({
                        'account_id': truelayer_account_id,
                        'synced': 0,
                        'duplicates': 0,
                        'errors': 1,
                        'error_message': 'No access token found',
                    })
                    continue

                access_token = decrypt_token(encrypted_token)
                print(f"   ✅ Successfully decrypted access token for account {truelayer_account_id}")

                result = sync_account_transactions(
                    connection_id=connection_id,
                    truelayer_account_id=truelayer_account_id,
                    db_account_id=db_account_id,
                    access_token=access_token,
                )
                account_results.append(result)
            except Exception as e:
                print(f"❌ Error processing account {truelayer_account_id}: {e}")
                import traceback
                traceback.print_exc()
                account_results.append({
                    'account_id': truelayer_account_id,
                    'synced': 0,
                    'duplicates': 0,
                    'errors': 1,
                    'error_message': str(e),
                })

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


def sync_card_transactions(
    connection_id: int,
    truelayer_card_id: str,
    db_card_id: int,
    access_token: str,
    days_back: int = 90,
    use_incremental: bool = True
) -> dict:
    """
    Sync transactions from TrueLayer for a specific card.

    Args:
        connection_id: Database connection ID
        truelayer_card_id: TrueLayer card ID (string)
        db_card_id: Database card ID (foreign key to truelayer_cards.id)
        access_token: Valid OAuth access token
        days_back: Number of days to fetch (fallback if no last_synced_at)
        use_incremental: Use incremental sync based on last_synced_at

    Returns:
        Dictionary with sync results
    """
    try:
        print(f"🔄 Syncing card {truelayer_card_id}...")

        client = TrueLayerClient(access_token)

        # Determine the sync window
        sync_days = days_back
        if use_incremental:
            # Get the card's last sync timestamp
            card = database.get_connection_cards(connection_id)
            # Find this specific card in the list
            card_record = next((c for c in card if c.get('id') == db_card_id), None)
            if card_record and card_record.get('last_synced_at'):
                last_sync = datetime.fromisoformat(card_record['last_synced_at'])
                days_since_sync = (datetime.utcnow() - last_sync).days
                sync_days = max(1, days_since_sync + 1)
                print(f"   📅 Incremental sync: last synced {days_since_sync} days ago, fetching {sync_days} days")
            else:
                print(f"   📅 No previous sync found, fetching full {days_back} days")

        # Fetch transactions from TrueLayer
        transactions = client.fetch_all_card_transactions(truelayer_card_id, sync_days)

        synced_count = 0
        duplicate_count = 0
        error_count = 0

        if transactions:
            # Insert/update transactions in database
            for txn in transactions:
                try:
                    # Check if transaction already exists (using normalised_provider_id)
                    existing = database.get_card_transaction_by_id(
                        txn.get('normalised_provider_id')
                    )

                    if existing:
                        duplicate_count += 1
                        continue

                    # Insert new card transaction
                    txn_id = database.insert_truelayer_card_transaction(
                        card_id=db_card_id,
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
                    print(f"❌ Error inserting card transaction: {e}")
                    error_count += 1
        else:
            print(f"⚠️  No transactions found for card {truelayer_card_id}")

        # Update card-level sync timestamp
        database.update_card_last_synced(db_card_id, datetime.utcnow().isoformat())

        result = {
            'card_id': truelayer_card_id,
            'synced': synced_count,
            'duplicates': duplicate_count,
            'errors': error_count,
            'total_processed': synced_count + duplicate_count,
        }

        print(f"✅ Card sync complete: {synced_count} synced, {duplicate_count} duplicates, {error_count} errors")
        return result

    except Exception as e:
        print(f"❌ Sync failed for card {truelayer_card_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'card_id': truelayer_card_id,
            'synced': 0,
            'duplicates': 0,
            'errors': 1,
            'error_message': str(e),
        }


def sync_all_cards(user_id: int) -> dict:
    """
    Discover and sync transactions for all cards of a user.

    Args:
        user_id: User ID

    Returns:
        Dictionary with aggregate sync results
    """
    print(f"🔄 Starting card sync for user {user_id}...")

    # Get all active connections for user
    connections = database.get_user_connections(user_id)

    if not connections:
        print(f"⚠️  No active connections found for user {user_id}")
        return {
            'user_id': user_id,
            'total_cards': 0,
            'total_synced': 0,
            'cards': []
        }

    card_results = []

    for connection in connections:
        connection_id = connection.get('id')
        access_token = decrypt_token(connection.get('access_token'))

        try:
            client = TrueLayerClient(access_token)

            # Discover cards for this connection
            cards = client.get_cards()

            if not cards:
                print(f"⚠️  No cards found for connection {connection_id}")
                continue

            for card in cards:
                truelayer_card_id = card.get('id')
                card_name = card.get('display_name', card.get('name', 'Unknown Card'))
                card_type = card.get('type', 'UNKNOWN')
                last_four = card.get('partial_card_number', '')[-4:] if card.get('partial_card_number') else None
                issuer = card.get('card_issuer', None)

                # Save or update card in database
                db_card_id = database.save_connection_card(
                    connection_id=connection_id,
                    card_id=truelayer_card_id,
                    card_name=card_name,
                    card_type=card_type,
                    last_four=last_four,
                    issuer=issuer
                )

                # Sync transactions for this card
                result = sync_card_transactions(
                    connection_id=connection_id,
                    truelayer_card_id=truelayer_card_id,
                    db_card_id=db_card_id,
                    access_token=access_token,
                )
                card_results.append(result)

        except Exception as e:
            print(f"❌ Error syncing cards for connection {connection_id}: {e}")

    # Aggregate results
    total_synced = sum(r.get('synced', 0) for r in card_results)
    total_duplicates = sum(r.get('duplicates', 0) for r in card_results)
    total_errors = sum(r.get('errors', 0) for r in card_results)

    return {
        'user_id': user_id,
        'total_cards': len(card_results),
        'total_synced': total_synced,
        'total_duplicates': total_duplicates,
        'total_errors': total_errors,
        'cards': card_results,
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
