"""
Amazon Transaction Matcher MCP Component
Fuzzy matching algorithm to match bank transactions with Amazon order history.
Uses exact amount matching, date proximity (±3 days), and merchant name detection.
"""

from datetime import datetime, timedelta
import database_postgres as database


def match_all_amazon_transactions():
    """
    Run fuzzy matching on all unmatched Amazon transactions (TrueLayer only).
    Finds ALL matches (not just best) and stores them in transaction_enrichment_sources.
    Best match is also stored in legacy table for backward compatibility.

    Returns:
        Dictionary with matching statistics
    """
    # Get all unmatched TrueLayer Amazon transactions
    unmatched_transactions = database.get_unmatched_truelayer_amazon_transactions()

    if not unmatched_transactions:
        return {
            'total_processed': 0,
            'matched': 0,
            'unmatched': 0,
            'total_sources_added': 0,
            'matches': [],
            'note': 'No unmatched Amazon transactions found in TrueLayer data'
        }

    # Get all Amazon orders for matching
    all_orders = database.get_amazon_orders()

    matched_count = 0
    total_sources_added = 0
    matches_details = []

    for transaction in unmatched_transactions:
        # Find ALL matching orders above threshold
        all_matches = find_all_matches(transaction, all_orders)

        if all_matches:
            best_match = all_matches[0]

            # Store BEST match in legacy table (for backward compatibility)
            success = database.match_truelayer_amazon_transaction(
                transaction['id'],
                best_match['order_db_id'],
                best_match['confidence']
            )

            if success:
                # Update pre-enrichment status to 'Matched'
                database.update_pre_enrichment_status(transaction['id'], 'Matched')
                matched_count += 1

                # Store ALL matches in transaction_enrichment_sources
                for i, match in enumerate(all_matches):
                    is_primary = (i == 0)  # First match (highest confidence) is primary
                    database.add_enrichment_source(
                        transaction_id=transaction['id'],
                        source_type='amazon',
                        source_id=match['order_db_id'],
                        description=match['product_names'],
                        order_id=match['order_id'],
                        confidence=match['confidence'],
                        match_method='amount_date_match',
                        is_primary=is_primary
                    )
                    total_sources_added += 1

                matches_details.append({
                    'transaction_id': transaction['id'],
                    'order_id': best_match['order_id'],
                    'confidence': best_match['confidence'],
                    'original_description': transaction['description'],
                    'product_names': best_match['product_names'],
                    'amount': transaction['amount'],
                    'date': transaction['date'],
                    'total_matches': len(all_matches)
                })

    return {
        'total_processed': len(unmatched_transactions),
        'matched': matched_count,
        'unmatched': len(unmatched_transactions) - matched_count,
        'total_sources_added': total_sources_added,
        'matches': matches_details,
        'note': 'Matching TrueLayer transactions. ALL matches stored in transaction_enrichment_sources.'
    }


def find_all_matches(transaction, orders, min_confidence=70):
    """
    Find ALL matching Amazon orders for a transaction above the confidence threshold.
    Uses exact amount match, date proximity (±3 days), and merchant name detection.

    Args:
        transaction: Transaction dictionary
        orders: List of Amazon order dictionaries
        min_confidence: Minimum confidence threshold (default 70)

    Returns:
        List of match dictionaries sorted by confidence (highest first), or empty list
    """
    if not orders:
        return []

    # Parse transaction date - handle both date-only and full timestamp formats
    try:
        date_str = str(transaction['date']).strip()
        # Try to parse as full timestamp first (with time component)
        if ' ' in date_str or 'T' in date_str:
            # PostgreSQL format: "2025-03-28 00:00:00+00" or ISO: "2025-03-28T00:00:00+00:00"
            # Remove timezone info and parse just the date part
            date_part = date_str.split(' ')[0] if ' ' in date_str else date_str.split('T')[0]
            txn_date = datetime.strptime(date_part, '%Y-%m-%d')
        else:
            # Parse as date-only format (legacy)
            txn_date = datetime.strptime(date_str, '%Y-%m-%d')
    except Exception as e:
        return []

    # Get transaction amount (convert negative expenses to positive for comparison)
    txn_amount = abs(transaction['amount'])

    # Check if this is an Amazon transaction
    if not is_amazon_transaction(transaction):
        return []

    # Find candidate matches
    candidates = []

    for order in orders:
        # Parse order date - handle both string and date object formats
        try:
            order_date_val = order['order_date']
            if isinstance(order_date_val, datetime):
                order_date = order_date_val
            elif isinstance(order_date_val, type(datetime.now().date())):  # datetime.date type
                order_date = datetime.combine(order_date_val, datetime.min.time())
            else:
                order_date = datetime.strptime(str(order_date_val), '%Y-%m-%d')
        except:
            continue

        # Check date proximity (±3 days)
        date_diff_days = abs((txn_date - order_date).days)
        if date_diff_days > 3:
            continue

        # Check amount match (exact match only)
        order_amount = abs(order['total_owed'])
        if not amounts_match(txn_amount, order_amount):
            continue

        # Calculate confidence score
        confidence = calculate_confidence(txn_date, order_date, txn_amount, order_amount)

        # Only include matches above threshold
        if confidence >= min_confidence:
            candidates.append({
                'order_db_id': order['id'],
                'order_id': order['order_id'],
                'product_names': order['product_names'],
                'confidence': confidence,
                'date_diff': date_diff_days,
                'order_date': order['order_date']
            })

    # Sort by confidence (highest first) and date proximity (closest first)
    candidates.sort(key=lambda x: (-x['confidence'], x['date_diff']))

    return candidates


def find_best_match(transaction, orders):
    """
    Find the best matching Amazon order for a transaction.
    Wrapper around find_all_matches for backward compatibility.

    Args:
        transaction: Transaction dictionary
        orders: List of Amazon order dictionaries

    Returns:
        Best match dictionary or None if no good match found
    """
    matches = find_all_matches(transaction, orders)
    return matches[0] if matches else None


def is_amazon_transaction(transaction):
    """
    Check if a transaction is an Amazon purchase based on merchant/description.

    Args:
        transaction: Transaction dictionary

    Returns:
        Boolean indicating if this is an Amazon transaction
    """
    merchant = (transaction.get('merchant') or '').upper()
    description = (transaction.get('description') or '').upper()

    amazon_keywords = ['AMAZON', 'AMZN', 'AMZ']

    for keyword in amazon_keywords:
        if keyword in merchant or keyword in description:
            return True

    return False


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
    return abs(amount1 - amount2) < tolerance


def calculate_confidence(txn_date, order_date, txn_amount, order_amount):
    """
    Calculate confidence score for a match.

    Args:
        txn_date: Transaction datetime
        order_date: Order datetime
        txn_amount: Transaction amount
        order_amount: Order amount

    Returns:
        Confidence score (0-100)
    """
    confidence = 0

    # Amount match (50 points for exact match)
    if amounts_match(txn_amount, order_amount):
        confidence += 50

    # Date proximity (50 points max)
    date_diff_days = abs((txn_date - order_date).days)

    if date_diff_days == 0:
        confidence += 50  # Same day
    elif date_diff_days == 1:
        confidence += 45  # 1 day difference
    elif date_diff_days == 2:
        confidence += 35  # 2 days difference
    elif date_diff_days == 3:
        confidence += 25  # 3 days difference

    return confidence


def rematch_transaction(transaction_id):
    """
    Re-run matching for a specific TrueLayer transaction.
    Useful when new Amazon data is added.

    Args:
        transaction_id: ID of the TrueLayer transaction to rematch

    Returns:
        Match result dictionary or None
    """
    # Get the transaction from TrueLayer
    transaction = database.get_truelayer_transaction_for_matching(transaction_id)

    if not transaction:
        return {
            'success': False,
            'reason': f'Transaction {transaction_id} not found'
        }

    # Get all Amazon orders
    all_orders = database.get_amazon_orders()

    # Find best match
    match = find_best_match(transaction, all_orders)

    if match:
        return {
            'success': True,
            'match': {
                'transaction_id': transaction_id,
                'order_id': match['order_id'],
                'confidence': match['confidence'],
                'original_description': transaction['description'],
                'product_names': match['product_names'],
                'amount': transaction['amount'],
                'date': transaction['date']
            },
            'note': 'Match result for reference (not persisted)'
        }

    return {
        'success': False,
        'reason': 'No suitable match found'
    }


def get_match_preview(transaction_id):
    """
    Preview potential matches for a TrueLayer transaction without applying them.

    Args:
        transaction_id: ID of the TrueLayer transaction

    Returns:
        List of potential matches with confidence scores
    """
    transaction = database.get_truelayer_transaction_for_matching(transaction_id)

    if not transaction:
        return []

    # Get all Amazon orders
    all_orders = database.get_amazon_orders()

    # Parse transaction date - handle both date-only and full timestamp formats
    try:
        date_str = str(transaction['date']).strip()
        # Try to parse as full timestamp first (with time component)
        if ' ' in date_str or 'T' in date_str:
            # PostgreSQL format: "2025-03-28 00:00:00+00" or ISO: "2025-03-28T00:00:00+00:00"
            # Remove timezone info and parse just the date part
            date_part = date_str.split(' ')[0] if ' ' in date_str else date_str.split('T')[0]
            txn_date = datetime.strptime(date_part, '%Y-%m-%d')
        else:
            # Parse as date-only format (legacy)
            txn_date = datetime.strptime(date_str, '%Y-%m-%d')
    except:
        return []

    txn_amount = abs(transaction['amount'])

    # Find all potential candidates (with lower threshold)
    candidates = []

    for order in all_orders:
        try:
            order_date_val = order['order_date']
            if isinstance(order_date_val, datetime):
                order_date = order_date_val
            elif isinstance(order_date_val, type(datetime.now().date())):  # datetime.date type
                order_date = datetime.combine(order_date_val, datetime.min.time())
            else:
                order_date = datetime.strptime(str(order_date_val), '%Y-%m-%d')
        except:
            continue

        # Check date proximity
        date_diff_days = abs((txn_date - order_date).days)
        if date_diff_days > 3:
            continue

        # Check amount match
        order_amount = abs(order['total_owed'])
        if not amounts_match(txn_amount, order_amount):
            continue

        # Calculate confidence
        confidence = calculate_confidence(txn_date, order_date, txn_amount, order_amount)

        candidates.append({
            'order_id': order['order_id'],
            'product_names': order['product_names'],
            'confidence': confidence,
            'date_diff': date_diff_days,
            'order_date': order['order_date'],
            'amount': order['total_owed']
        })

    # Sort by confidence
    candidates.sort(key=lambda x: (-x['confidence'], x['date_diff']))

    return candidates[:5]  # Return top 5 candidates
