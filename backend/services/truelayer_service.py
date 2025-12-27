"""
TrueLayer Service - Business Logic

Orchestrates TrueLayer bank integration including OAuth, account discovery,
transaction sync, and import job management.
"""

from database import truelayer
from mcp import truelayer_auth, truelayer_sync
import cache_manager


def sync_transactions(user_id: int = None, connection_id: int = None) -> dict:
    """
    Trigger manual sync of TrueLayer transactions.

    Args:
        user_id: User ID (optional)
        connection_id: Connection ID (optional)

    Returns:
        Sync result with summary statistics

    Raises:
        ValueError: If neither user_id nor connection_id provided
    """
    # If connection_id provided, get user_id from connection
    if connection_id and not user_id:
        connection = truelayer.get_connection(connection_id)
        if connection:
            user_id = connection.get('user_id')
            print(f"   📍 Found user_id {user_id} from connection {connection_id}")

    # Default to user 1 if still not found
    if not user_id:
        user_id = 1
        print(f"   📍 Using default user_id: {user_id}")

    print(f"🔄 Starting TrueLayer sync for user {user_id}...")

    # Sync all accounts for user
    result = truelayer_sync.sync_all_accounts(user_id)

    # Calculate totals
    total_synced = sum(acc.get('synced', 0) for acc in result.get('accounts', []))
    total_duplicates = sum(acc.get('duplicates', 0) for acc in result.get('accounts', []))
    total_errors = sum(acc.get('errors', 0) for acc in result.get('accounts', []))

    print(f"✅ Sync completed: {total_synced} synced, {total_duplicates} duplicates, {total_errors} errors")

    # Invalidate transaction caches (new transactions imported)
    cache_manager.cache_invalidate_transactions()

    return {
        'status': 'completed',
        'summary': {
            'total_accounts': result.get('total_accounts', 0),
            'total_synced': total_synced,
            'total_duplicates': total_duplicates,
            'total_errors': total_errors,
        },
        'result': result
    }


def get_sync_status(user_id: int = 1) -> dict:
    """
    Get sync status for all accounts.

    Args:
        user_id: User ID

    Returns:
        Sync status dict
    """
    return truelayer_sync.get_sync_status(user_id)


def disconnect(user_id: int = 1) -> dict:
    """
    Disconnect TrueLayer bank connection.

    Args:
        user_id: User ID

    Returns:
        Success message dict
    """
    connections = truelayer.get_user_connections(user_id)

    for connection in connections:
        truelayer.update_connection_status(connection['id'], 'disconnected')

    return {'message': f'Disconnected {len(connections)} connection(s)'}


def clear_transactions(user_id: int = 1, account_id: int = None) -> dict:
    """
    Clear all TrueLayer transactions for testing.

    Args:
        user_id: User ID
        account_id: Specific account ID (optional)

    Returns:
        Result with count of deleted transactions
    """
    from database import execute_query

    if account_id:
        result = execute_query(
            "DELETE FROM truelayer_transactions WHERE account_id = %s",
            (account_id,),
            commit=True
        )
        message = f'Cleared transactions for account {account_id}'
    else:
        # Get all accounts for user
        connections = truelayer.get_user_connections(user_id)
        account_ids = []
        for conn in connections:
            accounts = truelayer.get_connection_accounts(conn['id'])
            account_ids.extend([acc['id'] for acc in accounts])

        if account_ids:
            placeholders = ','.join(['%s'] * len(account_ids))
            execute_query(
                f"DELETE FROM truelayer_transactions WHERE account_id IN ({placeholders})",
                tuple(account_ids),
                commit=True
            )

        message = f'Cleared transactions for {len(account_ids)} account(s)'

    # Invalidate caches
    cache_manager.cache_invalidate_transactions()

    return {'message': message}


def get_accounts(user_id: int = 1) -> list:
    """
    Get all accounts for a user.

    Args:
        user_id: User ID

    Returns:
        List of account dicts with connection details
    """
    connections = truelayer.get_user_connections(user_id)
    all_accounts = []

    for connection in connections:
        accounts = truelayer.get_connection_accounts(connection['id'])
        for account in accounts:
            account['connection'] = connection
        all_accounts.extend(accounts)

    return all_accounts


def get_cards(user_id: int = 1) -> list:
    """
    Get all cards for a user.

    Args:
        user_id: User ID

    Returns:
        List of card dicts with connection details
    """
    connections = truelayer.get_user_connections(user_id)
    all_cards = []

    for connection in connections:
        cards = truelayer.get_connection_cards(connection['id'])
        for card in cards:
            card['connection'] = connection
        all_cards.extend(cards)

    return all_cards


def discover_accounts(user_id: int = 1) -> dict:
    """
    Discover and save new accounts from TrueLayer API.

    Args:
        user_id: User ID

    Returns:
        Result with discovered accounts count
    """
    from mcp.truelayer_client import TrueLayerClient

    connections = truelayer.get_user_connections(user_id)
    if not connections:
        raise ValueError('No TrueLayer connection found')

    total_discovered = 0

    for connection in connections:
        client = TrueLayerClient(
            access_token=connection['access_token'],
            refresh_token=connection['refresh_token']
        )

        # Fetch accounts from API
        accounts = client.get_accounts()

        # Save to database
        for account in accounts:
            truelayer.save_connection_account(
                connection_id=connection['id'],
                account_data=account
            )
            total_discovered += 1

    return {
        'message': f'Discovered {total_discovered} account(s)',
        'count': total_discovered
    }


def fetch_accounts(connection_id: int) -> dict:
    """
    Fetch accounts from TrueLayer API for a specific connection.

    Args:
        connection_id: Connection ID

    Returns:
        Result with fetched accounts
    """
    from mcp.truelayer_client import TrueLayerClient

    connection = truelayer.get_connection(connection_id)
    if not connection:
        raise ValueError('Connection not found')

    client = TrueLayerClient(
        access_token=connection['access_token'],
        refresh_token=connection['refresh_token']
    )

    accounts = client.get_accounts()

    # Save to database
    for account in accounts:
        truelayer.save_connection_account(
            connection_id=connection_id,
            account_data=account
        )

    return {
        'message': f'Fetched {len(accounts)} account(s)',
        'accounts': accounts
    }


def fetch_cards(connection_id: int) -> dict:
    """
    Fetch cards from TrueLayer API for a specific connection.

    Args:
        connection_id: Connection ID

    Returns:
        Result with fetched cards
    """
    from mcp.truelayer_client import TrueLayerClient

    connection = truelayer.get_connection(connection_id)
    if not connection:
        raise ValueError('Connection not found')

    client = TrueLayerClient(
        access_token=connection['access_token'],
        refresh_token=connection['refresh_token']
    )

    cards = client.get_cards()

    # Save to database
    for card in cards:
        truelayer.save_connection_card(
            connection_id=connection_id,
            card_data=card
        )

    return {
        'message': f'Fetched {len(cards)} card(s)',
        'cards': cards
    }


def fetch_transactions(account_id: int, from_date: str = None, to_date: str = None) -> dict:
    """
    Fetch transactions from TrueLayer API for a specific account.

    Args:
        account_id: Account ID
        from_date: ISO format date (YYYY-MM-DD)
        to_date: ISO format date (YYYY-MM-DD)

    Returns:
        Result with fetched transactions
    """
    from mcp.truelayer_sync import sync_account_transactions

    result = sync_account_transactions(
        account_id=account_id,
        from_date=from_date,
        to_date=to_date
    )

    # Invalidate caches
    cache_manager.cache_invalidate_transactions()

    return result


def plan_import(user_id: int = 1, from_date: str = None, to_date: str = None) -> dict:
    """
    Plan a batch import job without executing it.

    Args:
        user_id: User ID
        from_date: ISO format date (YYYY-MM-DD)
        to_date: ISO format date (YYYY-MM-DD)

    Returns:
        Import plan with estimated transaction count
    """
    accounts = get_accounts(user_id)

    plan = {
        'user_id': user_id,
        'from_date': from_date,
        'to_date': to_date,
        'accounts': len(accounts),
        'estimated_transactions': len(accounts) * 1000,  # Rough estimate
    }

    return plan


def start_import(user_id: int = 1, from_date: str = None, to_date: str = None) -> dict:
    """
    Start a batch import job.

    Args:
        user_id: User ID
        from_date: ISO format date (YYYY-MM-DD)
        to_date: ISO format date (YYYY-MM-DD)

    Returns:
        Job details with job_id
    """
    job_id = truelayer.create_import_job(
        user_id=user_id,
        from_date=from_date,
        to_date=to_date
    )

    # TODO: Dispatch async task

    return {
        'job_id': job_id,
        'status': 'started',
        'from_date': from_date,
        'to_date': to_date
    }


def get_import_status(job_id: int) -> dict:
    """
    Get import job status.

    Args:
        job_id: Job ID

    Returns:
        Job status dict
    """
    job = truelayer.get_import_job(job_id)
    if not job:
        raise ValueError('Import job not found')

    return job


def get_import_history(user_id: int = 1) -> list:
    """
    Get import job history for a user.

    Args:
        user_id: User ID

    Returns:
        List of import jobs
    """
    return truelayer.get_user_import_history(user_id)


def handle_webhook(event_id: str, event_type: str, payload: dict, signature: str = None) -> dict:
    """
    Handle TrueLayer webhook event.

    Args:
        event_id: Unique event ID
        event_type: Event type (e.g., 'transaction.created')
        payload: Event payload
        signature: Webhook signature for verification

    Returns:
        Success message
    """
    # Store webhook event
    truelayer.insert_webhook_event(
        event_id=event_id,
        event_type=event_type,
        payload=payload,
        signature=signature,
        processed=False
    )

    # TODO: Process webhook asynchronously

    return {'message': 'Webhook received'}
