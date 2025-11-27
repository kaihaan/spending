"""
Amazon Transaction Matcher MCP Component
Fuzzy matching algorithm to match bank transactions with Amazon order history.
Uses exact amount matching, date proximity (±3 days), and merchant name detection.
"""

from datetime import datetime, timedelta
import database


def match_all_amazon_transactions():
    """
    Run fuzzy matching on all unmatched Amazon transactions.
    Finds matches in the Amazon orders database and populates lookup descriptions.

    Returns:
        Dictionary with matching statistics
    """
    # Get all unmatched Amazon transactions
    unmatched_transactions = database.get_unmatched_amazon_transactions()

    if not unmatched_transactions:
        return {
            'total_processed': 0,
            'matched': 0,
            'unmatched': 0,
            'matches': []
        }

    # Get all Amazon orders for matching
    all_orders = database.get_amazon_orders()

    matched_count = 0
    matches_details = []

    for transaction in unmatched_transactions:
        # Try to find a match
        match = find_best_match(transaction, all_orders)

        if match:
            # Record the match in database
            success = database.match_amazon_transaction(
                transaction['id'],
                match['order_db_id'],
                match['confidence']
            )

            if success:
                # Populate lookup_description with product names (keep original description)
                database.update_transaction_lookup_description(
                    transaction['id'],
                    match['product_names']
                )

                matched_count += 1
                matches_details.append({
                    'transaction_id': transaction['id'],
                    'order_id': match['order_id'],
                    'confidence': match['confidence'],
                    'original_description': transaction['description'],
                    'product_names': match['product_names']
                })

    return {
        'total_processed': len(unmatched_transactions),
        'matched': matched_count,
        'unmatched': len(unmatched_transactions) - matched_count,
        'matches': matches_details
    }


def find_best_match(transaction, orders):
    """
    Find the best matching Amazon order for a transaction.
    Uses exact amount match, date proximity (±3 days), and merchant name detection.

    Args:
        transaction: Transaction dictionary
        orders: List of Amazon order dictionaries

    Returns:
        Best match dictionary or None if no good match found
    """
    if not orders:
        return None

    # Parse transaction date
    try:
        txn_date = datetime.strptime(transaction['date'], '%Y-%m-%d')
    except:
        return None

    # Get transaction amount (convert negative expenses to positive for comparison)
    txn_amount = abs(transaction['amount'])

    # Check if this is an Amazon transaction
    if not is_amazon_transaction(transaction):
        return None

    # Find candidate matches
    candidates = []

    for order in orders:
        # Parse order date
        try:
            order_date = datetime.strptime(order['order_date'], '%Y-%m-%d')
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

        candidates.append({
            'order_db_id': order['id'],
            'order_id': order['order_id'],
            'product_names': order['product_names'],
            'confidence': confidence,
            'date_diff': date_diff_days,
            'order_date': order['order_date']
        })

    # No candidates found
    if not candidates:
        return None

    # Sort by confidence (highest first) and date proximity (closest first)
    candidates.sort(key=lambda x: (-x['confidence'], x['date_diff']))

    # Return best match if confidence is high enough
    best_match = candidates[0]

    if best_match['confidence'] >= 70:  # Minimum confidence threshold
        return best_match

    return None


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
    Re-run matching for a specific transaction.
    Useful when new Amazon data is added.

    Args:
        transaction_id: ID of the transaction to rematch

    Returns:
        Match result dictionary or None
    """
    # Get the transaction
    transaction = database.get_transaction_by_id(transaction_id)

    if not transaction:
        return None

    # Get all Amazon orders
    all_orders = database.get_amazon_orders()

    # Find best match
    match = find_best_match(transaction, all_orders)

    if match:
        # Update match in database
        database.match_amazon_transaction(
            transaction_id,
            match['order_db_id'],
            match['confidence']
        )

        # Populate lookup_description with product names (keep original description)
        database.update_transaction_lookup_description(
            transaction_id,
            match['product_names']
        )

        return {
            'success': True,
            'match': match
        }

    return {
        'success': False,
        'reason': 'No suitable match found'
    }


def get_match_preview(transaction_id):
    """
    Preview potential matches for a transaction without applying them.

    Args:
        transaction_id: ID of the transaction

    Returns:
        List of potential matches with confidence scores
    """
    transaction = database.get_transaction_by_id(transaction_id)

    if not transaction:
        return []

    # Get all Amazon orders
    all_orders = database.get_amazon_orders()

    # Parse transaction date
    try:
        txn_date = datetime.strptime(transaction['date'], '%Y-%m-%d')
    except:
        return []

    txn_amount = abs(transaction['amount'])

    # Find all potential candidates (with lower threshold)
    candidates = []

    for order in orders:
        try:
            order_date = datetime.strptime(order['order_date'], '%Y-%m-%d')
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
