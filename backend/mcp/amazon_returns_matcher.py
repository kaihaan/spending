"""
Amazon Returns Matcher MCP Component
Matches returns to original orders and transactions.
Updates transaction descriptions and marks items as returned.
"""

from datetime import datetime, timedelta
import database


def match_all_returns():
    """
    Match all unmatched returns to their original orders and transactions.

    Returns:
        Dictionary with matching statistics
    """
    # Get all returns that haven't been matched yet
    all_returns = database.get_amazon_returns()
    unmatched_returns = [r for r in all_returns if r['original_transaction_id'] is None]

    if not unmatched_returns:
        return {
            'total_processed': 0,
            'matched': 0,
            'unmatched': 0,
            'matches': []
        }

    matched_count = 0
    matches_details = []

    for ret in unmatched_returns:
        # Try to find matches
        match_result = match_single_return(ret)

        if match_result and match_result['success']:
            matched_count += 1
            matches_details.append({
                'return_id': ret['id'],
                'order_id': ret['order_id'],
                'amount_refunded': ret['amount_refunded'],
                'original_transaction_id': match_result['original_transaction_id'],
                'refund_transaction_id': match_result['refund_transaction_id']
            })

    return {
        'total_processed': len(unmatched_returns),
        'matched': matched_count,
        'unmatched': len(unmatched_returns) - matched_count,
        'matches': matches_details
    }


def match_single_return(ret):
    """
    Match a single return to its original order and transactions.

    Args:
        ret: Return dictionary

    Returns:
        Match result dictionary or None
    """
    # Step 1: Find the original Amazon order by order_id
    order = database.get_amazon_order_by_id(ret['order_id'])

    if not order:
        return {'success': False, 'reason': 'Order not found'}

    # Step 2: Find the original purchase transaction
    # Look for transaction matched to this order
    original_transaction = find_transaction_for_order(order['id'])

    if not original_transaction:
        return {'success': False, 'reason': 'Original transaction not found'}

    # Step 3: Find the refund transaction
    # Look for positive amount transaction near the refund date
    refund_transaction = find_refund_transaction(ret)

    if not refund_transaction:
        return {'success': False, 'reason': 'Refund transaction not found'}

    # Step 4: Update refund transaction description
    refund_desc = f"[REFUND] {order['product_names']}"
    database.update_transaction_description(refund_transaction['id'], refund_desc)

    # Step 5: Mark original transaction as returned
    database.mark_transaction_as_returned(original_transaction['id'])

    # Step 6: Link return to transactions
    database.link_return_to_transactions(
        ret['id'],
        original_transaction['id'],
        refund_transaction['id']
    )

    return {
        'success': True,
        'original_transaction_id': original_transaction['id'],
        'refund_transaction_id': refund_transaction['id']
    }


def find_transaction_for_order(order_db_id):
    """
    Find the bank transaction that was matched to a specific Amazon order.

    Args:
        order_db_id: Database ID of the Amazon order

    Returns:
        Transaction dictionary or None
    """
    # Query amazon_transaction_matches to find the linked transaction
    with database.get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT t.*
            FROM transactions t
            JOIN amazon_transaction_matches m ON t.id = m.transaction_id
            WHERE m.amazon_order_id = ?
        ''', (order_db_id,))
        row = c.fetchone()
        return dict(row) if row else None


def find_refund_transaction(ret):
    """
    Find the bank transaction representing the refund.
    Looks for positive amount (credit) near the refund completion date.

    Args:
        ret: Return dictionary

    Returns:
        Transaction dictionary or None
    """
    # Parse refund date
    try:
        refund_date = datetime.strptime(ret['refund_completion_date'], '%Y-%m-%d')
    except:
        return None

    amount_refunded = abs(ret['amount_refunded'])

    # Get all transactions
    all_transactions = database.get_all_transactions()

    # Find candidate refund transactions
    candidates = []

    for txn in all_transactions:
        # Must be a credit (positive amount)
        if txn['amount'] <= 0:
            continue

        # Must be an Amazon transaction
        merchant = (txn.get('merchant') or '').upper()
        description = (txn.get('description') or '').upper()

        if not ('AMAZON' in merchant or 'AMZN' in merchant or 'AMAZON' in description or 'AMZN' in description):
            continue

        # Parse transaction date
        try:
            txn_date = datetime.strptime(txn['date'], '%Y-%m-%d')
        except:
            continue

        # Check date proximity (within ±5 days)
        date_diff_days = abs((txn_date - refund_date).days)
        if date_diff_days > 5:
            continue

        # Check amount match (exact)
        if not amounts_match(txn['amount'], amount_refunded):
            continue

        candidates.append({
            'transaction': txn,
            'date_diff': date_diff_days
        })

    # No candidates found
    if not candidates:
        return None

    # Sort by date proximity (closest first)
    candidates.sort(key=lambda x: x['date_diff'])

    # Return best match
    return candidates[0]['transaction']


def amounts_match(amount1, amount2, tolerance=0.01):
    """
    Check if two amounts match (exact match with tiny tolerance for floating point).

    Args:
        amount1: First amount
        amount2: Second amount
        tolerance: Maximum difference allowed (default 0.01 for rounding)

    Returns:
        Boolean indicating if amounts match
    """
    return abs(abs(amount1) - abs(amount2)) < tolerance
