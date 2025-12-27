"""
Amazon Service - Business Logic

Orchestrates Amazon integration including:
- Order CSV imports (consumer purchases)
- Returns/refunds CSV imports
- Amazon Business API (SP-API) integration for seller accounts
- Transaction matching across all Amazon sources

Separates business logic from HTTP routing concerns.
"""

from database import amazon
from mcp import amazon_parser, amazon_returns_parser, amazon_sp_auth
from mcp.amazon_matcher import match_all_amazon_transactions, rematch_transaction
from mcp.amazon_returns_matcher import match_all_returns
from mcp.amazon_business_matcher import match_all_amazon_business_transactions
from mcp.amazon_sp_client import AmazonBusinessClient
import cache_manager
import os


# ============================================================================
# Regular Amazon Orders (CSV Import)
# ============================================================================

def import_orders(csv_content: str = None, filename: str = None, website: str = 'Amazon.co.uk') -> dict:
    """
    Import Amazon order history from CSV file or content.

    Args:
        csv_content: CSV file content (preferred)
        filename: Legacy path to CSV file in sample folder
        website: Amazon website (default: Amazon.co.uk)

    Returns:
        Import result with counts and matching results

    Raises:
        ValueError: If neither csv_content nor filename provided
        FileNotFoundError: If filename path doesn't exist
    """
    # Parse CSV
    if csv_content:
        orders = amazon_parser.parse_amazon_csv_content(csv_content)
        source_name = filename or 'uploaded_file.csv'
    elif filename:
        file_path = os.path.join('..', 'sample', filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'File not found: {filename}')
        orders = amazon_parser.parse_amazon_csv(file_path)
        source_name = filename
    else:
        raise ValueError('Missing csv_content or filename')

    # Import to database
    imported, duplicates = amazon.import_amazon_orders(orders, source_name)

    # Run matching
    match_results = match_all_amazon_transactions()

    return {
        'success': True,
        'orders_imported': imported,
        'orders_duplicated': duplicates,
        'matching_results': match_results,
        'filename': source_name
    }


def get_orders(date_from: str = None, date_to: str = None, website: str = None) -> dict:
    """
    Get all Amazon orders with optional filters.

    Args:
        date_from: Start date filter (YYYY-MM-DD)
        date_to: End date filter (YYYY-MM-DD)
        website: Amazon website filter

    Returns:
        Orders list with count
    """
    orders = amazon.get_amazon_orders(date_from, date_to, website)

    return {
        'orders': orders,
        'count': len(orders)
    }


def get_statistics() -> dict:
    """
    Get Amazon import and matching statistics (cached).

    Returns:
        Statistics dict (cached 15 minutes)
    """
    cache_key = "amazon:statistics"
    cached_data = cache_manager.cache_get(cache_key)

    if cached_data is not None:
        return cached_data

    # Cache miss - fetch from database
    stats = amazon.get_amazon_statistics()

    # Cache the result (15 minute TTL)
    cache_manager.cache_set(cache_key, stats, ttl=900)

    return stats


def run_matching(async_mode: bool = True, user_id: int = 1) -> dict:
    """
    Run or re-run Amazon matching on existing transactions.

    Args:
        async_mode: If True, runs as Celery task and returns job_id
        user_id: User ID for job tracking

    Returns:
        Job details if async, or match results if sync
    """
    if async_mode:
        from tasks.matching_tasks import match_amazon_orders_task

        # Create job entry
        job_id = amazon.create_matching_job(user_id, 'amazon')

        # Dispatch Celery task
        task = match_amazon_orders_task.delay(job_id, user_id)

        # Update job status
        amazon.update_matching_job_status(job_id, 'queued')

        return {
            'success': True,
            'async': True,
            'job_id': job_id,
            'celery_task_id': task.id,
            'status': 'queued'
        }
    else:
        # Sync mode for backward compatibility
        results = match_all_amazon_transactions()

        # Invalidate Amazon caches
        cache_manager.cache_invalidate_amazon()

        return {
            'success': True,
            'async': False,
            'results': results
        }


def rematch_single(transaction_id: int) -> dict:
    """
    Re-match a specific transaction with Amazon orders.

    Args:
        transaction_id: Transaction ID to rematch

    Returns:
        Match result or error

    Raises:
        ValueError: If no suitable match found
    """
    result = rematch_transaction(transaction_id)

    if not result or not result.get('success'):
        raise ValueError('No suitable match found')

    return result


def check_coverage(date_from: str, date_to: str) -> dict:
    """
    Check if Amazon order data exists for a date range.

    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)

    Returns:
        Coverage status dict
    """
    return amazon.check_amazon_coverage(date_from, date_to)


def get_unmatched_transactions() -> dict:
    """
    Get all Amazon transactions that haven't been matched to orders.

    Returns:
        Unmatched transactions list with count
    """
    unmatched = amazon.get_unmatched_amazon_transactions()

    return {
        'transactions': unmatched,
        'count': len(unmatched)
    }


def clear_orders() -> dict:
    """
    Clear all Amazon orders and matches (for testing/reimporting).

    Returns:
        Deletion counts
    """
    orders_deleted, matches_deleted = amazon.clear_amazon_orders()

    return {
        'success': True,
        'orders_deleted': orders_deleted,
        'matches_deleted': matches_deleted,
        'message': f'Cleared {orders_deleted} orders and {matches_deleted} matches'
    }


def list_csv_files() -> dict:
    """
    List available Amazon CSV files in the sample folder.

    Returns:
        File list with count
    """
    files = amazon_parser.get_amazon_csv_files('../sample')

    # Get just the filenames
    file_list = [{'filename': os.path.basename(f), 'path': f} for f in files]

    return {
        'files': file_list,
        'count': len(file_list)
    }


def upload_csv_file(file) -> dict:
    """
    Upload an Amazon CSV file to sample folder.

    Args:
        file: Flask file object

    Returns:
        Upload result with filename

    Raises:
        ValueError: If file invalid or not CSV
    """
    if not file or file.filename == '':
        raise ValueError('No file selected')

    if not file.filename.lower().endswith('.csv'):
        raise ValueError('Only CSV files are allowed')

    # Save to sample folder
    sample_folder = os.path.join(os.path.dirname(__file__), '..', '..', 'sample')
    os.makedirs(sample_folder, exist_ok=True)

    # Sanitize filename
    filename = os.path.basename(file.filename)
    filepath = os.path.join(sample_folder, filename)

    # Save file
    file.save(filepath)

    return {
        'success': True,
        'message': f'File uploaded successfully: {filename}',
        'filename': filename
    }


# ============================================================================
# Amazon Returns (CSV Import)
# ============================================================================

def import_returns(csv_content: str = None, filename: str = None) -> dict:
    """
    Import Amazon returns/refunds from CSV file or content.

    Args:
        csv_content: CSV file content (preferred)
        filename: Legacy path to CSV file in sample folder

    Returns:
        Import result with counts and matching results

    Raises:
        ValueError: If neither csv_content nor filename provided
        FileNotFoundError: If filename path doesn't exist
    """
    # Parse CSV
    if csv_content:
        returns = amazon_returns_parser.parse_amazon_returns_csv_content(csv_content)
        source_name = filename or 'uploaded_file.csv'
    elif filename:
        file_path = os.path.join('..', 'sample', filename)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f'File not found: {filename}')
        returns = amazon_returns_parser.parse_amazon_returns_csv(file_path)
        source_name = filename
    else:
        raise ValueError('Missing csv_content or filename')

    # Import to database
    imported, duplicates = amazon.import_amazon_returns(returns, source_name)

    # Run matching
    match_results = match_all_returns()

    return {
        'success': True,
        'returns_imported': imported,
        'returns_duplicated': duplicates,
        'matching_results': match_results,
        'filename': source_name
    }


def get_returns() -> dict:
    """
    Get all Amazon returns.

    Returns:
        Returns list with count
    """
    returns = amazon.get_amazon_returns()

    return {
        'returns': returns,
        'count': len(returns)
    }


def get_returns_statistics() -> dict:
    """
    Get Amazon returns statistics (cached).

    Returns:
        Statistics dict (cached 15 minutes)
    """
    cache_key = "amazon:returns:statistics"
    cached_data = cache_manager.cache_get(cache_key)

    if cached_data is not None:
        return cached_data

    # Cache miss - fetch from database
    stats = amazon.get_returns_statistics()

    # Cache the result (15 minute TTL)
    cache_manager.cache_set(cache_key, stats, ttl=900)

    return stats


def run_returns_matching(async_mode: bool = True, user_id: int = 1) -> dict:
    """
    Run or re-run returns matching.

    Args:
        async_mode: If True, runs as Celery task and returns job_id
        user_id: User ID for job tracking

    Returns:
        Job details if async, or match results if sync
    """
    if async_mode:
        from tasks.matching_tasks import match_amazon_returns_task

        # Create job entry
        job_id = amazon.create_matching_job(user_id, 'returns')

        # Dispatch Celery task
        task = match_amazon_returns_task.delay(job_id, user_id)

        # Update job status
        amazon.update_matching_job_status(job_id, 'queued')

        return {
            'success': True,
            'async': True,
            'job_id': job_id,
            'celery_task_id': task.id,
            'status': 'queued'
        }
    else:
        # Sync mode for backward compatibility
        results = match_all_returns()

        # Invalidate Amazon caches
        cache_manager.cache_invalidate_amazon()

        return {
            'success': True,
            'async': False,
            'results': results
        }


def clear_returns() -> dict:
    """
    Clear all Amazon returns (for testing/reimporting).

    Returns:
        Deletion count
    """
    returns_deleted = amazon.clear_amazon_returns()

    return {
        'success': True,
        'returns_deleted': returns_deleted,
        'message': f'Cleared {returns_deleted} returns and removed [RETURNED] labels'
    }


def list_returns_files() -> dict:
    """
    List available Amazon returns CSV files in the sample folder.

    Returns:
        File list with count
    """
    files = amazon_returns_parser.get_amazon_returns_csv_files('../sample')

    # Get just the filenames
    file_list = [{'filename': os.path.basename(f), 'path': f} for f in files]

    return {
        'files': file_list,
        'count': len(file_list)
    }


# ============================================================================
# Amazon Business (SP-API)
# ============================================================================

def get_authorization_url() -> dict:
    """
    Start Amazon Business API OAuth flow.

    Returns:
        Authorization URL and state token

    Raises:
        ValueError: If credentials not configured
    """
    result = amazon_sp_auth.get_authorization_url()

    return {
        'success': True,
        'authorization_url': result['authorization_url'],
        'state': result['state']
    }


def handle_oauth_callback(code: str, region: str = 'UK') -> dict:
    """
    Handle Amazon Business API OAuth callback.

    Args:
        code: Authorization code from OAuth redirect
        region: Amazon region (default: UK)

    Returns:
        Connection details

    Raises:
        ValueError: If code missing or exchange fails
    """
    # Exchange code for tokens
    tokens = amazon_sp_auth.exchange_code_for_tokens(code)

    # Get environment configuration
    marketplace_id = None  # Not used by Amazon Business API
    is_sandbox = os.getenv('AMAZON_BUSINESS_ENVIRONMENT', 'sandbox') == 'sandbox'

    # Save connection to database
    connection_id = amazon.save_amazon_business_connection(
        access_token=tokens['access_token'],
        refresh_token=tokens['refresh_token'],
        expires_in=tokens['expires_in'],
        region=region,
        marketplace_id=marketplace_id,
        is_sandbox=is_sandbox
    )

    return {
        'success': True,
        'connection_id': connection_id,
        'environment': 'sandbox' if is_sandbox else 'production',
        'region': region,
        'message': 'Amazon Business API connected successfully'
    }


def get_connection_status() -> dict:
    """
    Get Amazon Business connection status.

    Returns:
        Connection details or not connected status
    """
    conn = amazon.get_amazon_business_connection()

    if conn:
        return {
            'connected': True,
            'connection_id': conn['id'],
            'region': conn['region'],
            'status': conn['status'],
            'created_at': conn['created_at'].isoformat() if conn['created_at'] else None
        }
    else:
        return {
            'connected': False,
            'status': None
        }


def disconnect() -> dict:
    """
    Disconnect Amazon Business account.

    Returns:
        Success status

    Raises:
        ValueError: If no connection found
    """
    conn = amazon.get_amazon_business_connection()

    if not conn:
        raise ValueError('No connection found')

    success = amazon.delete_amazon_business_connection(conn['id'])

    return {
        'success': success,
        'message': 'Amazon Business disconnected' if success else 'Failed to disconnect'
    }


def import_business_orders(start_date: str, end_date: str, run_matching: bool = True) -> dict:
    """
    Import buyer purchase orders from Amazon Business Reporting API.

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        run_matching: Whether to run matching after import (default: True)

    Returns:
        Import and matching results

    Raises:
        ValueError: If no connection found or dates invalid
    """
    # Get connection
    connection = amazon.get_amazon_business_connection()
    if not connection:
        raise ValueError('Not connected. Please connect Amazon Business API first')

    # Create API client
    client = AmazonBusinessClient(connection_id=connection['id'])

    # Fetch orders with line items
    orders = client.get_orders(start_date, end_date, include_line_items=True)

    imported = 0
    duplicates = 0
    items_imported = 0

    # Process each order
    for order in orders:
        # Normalize order to database format
        normalized_order = client._normalize_order(order)

        # Check for duplicate
        if amazon.get_amazon_business_order_by_id(normalized_order['order_id']):
            duplicates += 1
            continue

        # Insert order
        order_db_id = amazon.insert_amazon_business_order(normalized_order)
        if order_db_id:
            imported += 1

            # Import line items
            line_items = order.get('lineItems', [])
            for item in line_items:
                normalized_item = client._normalize_order_item(
                    item, normalized_order['order_id']
                )
                item_id = amazon.insert_amazon_business_line_item(normalized_item)
                if item_id:
                    items_imported += 1

    # Update product summaries
    summary_count = amazon.update_amazon_business_product_summaries()

    import_results = {
        'orders_fetched': len(orders),
        'orders_imported': imported,
        'orders_duplicates': duplicates,
        'line_items_imported': items_imported,
        'summaries_updated': summary_count
    }

    # Run matching if requested
    matching_results = None
    if run_matching and imported > 0:
        matching_results = match_all_amazon_business_transactions()

    return {
        'success': True,
        'import': import_results,
        'matching': matching_results
    }


def get_business_statistics() -> dict:
    """
    Get Amazon Business import and matching statistics.

    Returns:
        Statistics dict
    """
    return amazon.get_amazon_business_statistics()


def get_business_orders(date_from: str = None, date_to: str = None) -> list:
    """
    Get Amazon Business orders with optional date filtering.

    Args:
        date_from: Start date filter (YYYY-MM-DD)
        date_to: End date filter (YYYY-MM-DD)

    Returns:
        Orders list (Decimal values converted to float)
    """
    orders = amazon.get_amazon_business_orders(
        date_from=date_from,
        date_to=date_to
    )

    # Convert Decimal values for JSON serialization
    for order in orders:
        for key in ['subtotal', 'tax', 'shipping', 'net_total']:
            if order.get(key) is not None:
                order[key] = float(order[key])
        if order.get('order_date'):
            order['order_date'] = order['order_date'].isoformat()
        if order.get('created_at'):
            order['created_at'] = order['created_at'].isoformat()

    return orders


def run_business_matching() -> dict:
    """
    Run matching for Amazon Business transactions.

    Returns:
        Matching results
    """
    results = match_all_amazon_business_transactions()

    return {
        'success': True,
        'results': results
    }


def clear_business_data() -> dict:
    """
    Clear all Amazon Business data (for testing/reset).

    Returns:
        Deletion counts by table
    """
    results = amazon.clear_amazon_business_data()

    return {
        'success': True,
        'deleted': results
    }
