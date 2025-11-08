"""
Apple Transactions Matcher MCP Component
Matches Apple/App Store transactions to bank transactions.
CRITICAL: Excludes Apple Pay payment method transactions.
"""

from datetime import datetime, timedelta
import database


def is_apple_transaction(description, merchant):
    """
    Check if transaction is from Apple/App Store, NOT Apple Pay.

    CRITICAL: This function must exclude "VIA APPLE PAY" transactions which
    are just payment methods for other merchants (e.g., "TESCO VIA APPLE PAY").

    Args:
        description: Transaction description
        merchant: Merchant name

    Returns:
        Boolean indicating if this is a genuine Apple transaction
    """
    # Combine description and merchant for checking
    text = ((description or '') + ' ' + (merchant or '')).upper()

    # CRITICAL: First check for Apple Pay - these must be EXCLUDED
    # These are payment methods, not actual Apple purchases
    if any(pattern in text for pattern in ['APPLE PAY', 'APPLEPAY', 'VIA APPLE PAY']):
        return False

    # Now check for genuine Apple/App Store merchants
    # These are actual purchases from Apple
    apple_patterns = [
        'APPLE.COM',
        'APPLE COM',
        'APP STORE',
        'APPSTORE',
        'ITUNES',
        'APPLE SERVICES',
        'APPLE BILL',
        # Standalone "APPLE" with space to avoid partial matches
        ' APPLE ',
    ]

    return any(pattern in text for pattern in apple_patterns)


def match_all_apple_transactions():
    """
    Match all unmatched Apple transactions to bank transactions.

    Returns:
        Dictionary with matching statistics
    """
    # Get all Apple transactions
    all_apple_transactions = database.get_apple_transactions()

    if not all_apple_transactions:
        return {
            'total_processed': 0,
            'matched': 0,
            'unmatched': 0,
            'matches': []
        }

    # Get all bank transactions
    all_bank_transactions = database.get_all_transactions()

    # Filter to only Apple-related transactions (excluding Apple Pay)
    apple_bank_transactions = [
        txn for txn in all_bank_transactions
        if is_apple_transaction(txn.get('description', ''), txn.get('merchant', ''))
    ]

    matched_count = 0
    matches_details = []

    for apple_txn in all_apple_transactions:
        # Try to find a match
        match_result = find_best_match(apple_txn, apple_bank_transactions)

        if match_result and match_result['confidence'] >= 70:
            # Record the match in database
            database.match_apple_transaction(
                match_result['transaction']['id'],
                apple_txn['id'],
                match_result['confidence']
            )

            # Update bank transaction description with app name
            new_description = apple_txn['app_names']
            if apple_txn.get('publishers'):
                new_description += f" ({apple_txn['publishers']})"

            database.update_transaction_description(
                match_result['transaction']['id'],
                new_description
            )

            matched_count += 1
            matches_details.append({
                'apple_transaction_id': apple_txn['id'],
                'bank_transaction_id': match_result['transaction']['id'],
                'confidence': match_result['confidence'],
                'app_names': apple_txn['app_names']
            })

    return {
        'total_processed': len(all_apple_transactions),
        'matched': matched_count,
        'unmatched': len(all_apple_transactions) - matched_count,
        'matches': matches_details
    }


def find_best_match(apple_txn, bank_transactions):
    """
    Find the best matching bank transaction for an Apple purchase.

    Args:
        apple_txn: Apple transaction dictionary
        bank_transactions: List of bank transaction dictionaries (pre-filtered for Apple)

    Returns:
        Match dictionary with transaction and confidence, or None
    """
    try:
        apple_date = datetime.strptime(apple_txn['order_date'], '%Y-%m-%d')
        apple_amount = abs(apple_txn['total_amount'])
    except:
        return None

    candidates = []

    for bank_txn in bank_transactions:
        try:
            txn_date = datetime.strptime(bank_txn['date'], '%Y-%m-%d')
            txn_amount = abs(bank_txn['amount'])
        except:
            continue

        # Check date proximity (±3 days)
        date_diff_days = abs((txn_date - apple_date).days)
        if date_diff_days > 3:
            continue

        # Check amount match (exact match with tiny tolerance for floating point)
        if not amounts_match(txn_amount, apple_amount):
            continue

        # Calculate confidence score
        confidence = calculate_confidence(txn_date, apple_date, txn_amount, apple_amount)

        candidates.append({
            'transaction': bank_txn,
            'confidence': confidence,
            'date_diff': date_diff_days
        })

    if not candidates:
        return None

    # Sort by confidence (highest first), then by date proximity (closest first)
    candidates.sort(key=lambda x: (x['confidence'], -x['date_diff']), reverse=True)

    # Return best match
    return candidates[0]


def calculate_confidence(txn_date, apple_date, txn_amount, apple_amount):
    """
    Calculate match confidence score.

    Args:
        txn_date: Bank transaction date
        apple_date: Apple order date
        txn_amount: Bank transaction amount
        apple_amount: Apple order amount

    Returns:
        Confidence percentage (0-100)
    """
    confidence = 0

    # Base score for being in the candidate set
    confidence += 50

    # Amount match (exact)
    if amounts_match(txn_amount, apple_amount):
        confidence += 50

    # Date proximity bonus (replaces base 50 if better)
    date_diff_days = abs((txn_date - apple_date).days)
    if date_diff_days == 0:
        confidence = max(confidence, 100)  # Perfect match
    elif date_diff_days == 1:
        confidence = max(confidence, 95)
    elif date_diff_days == 2:
        confidence = max(confidence, 85)
    elif date_diff_days == 3:
        confidence = max(confidence, 75)

    return min(confidence, 100)  # Cap at 100


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


def match_apple_transaction_on_import(bank_transaction):
    """
    Attempt to match a single newly imported bank transaction to Apple purchases.
    Called during bank statement import for auto-matching.

    Args:
        bank_transaction: Newly imported transaction dictionary

    Returns:
        Match result dictionary or None
    """
    # Check if this is an Apple transaction (excluding Apple Pay)
    if not is_apple_transaction(
        bank_transaction.get('description', ''),
        bank_transaction.get('merchant', '')
    ):
        return None

    # Get all Apple transactions
    all_apple_transactions = database.get_apple_transactions()

    if not all_apple_transactions:
        return None

    # Try to find a match
    match_result = find_best_match_for_single_transaction(bank_transaction, all_apple_transactions)

    if match_result and match_result['confidence'] >= 70:
        # Record the match
        database.match_apple_transaction(
            bank_transaction['id'],
            match_result['apple_txn']['id'],
            match_result['confidence']
        )

        # Update description
        apple_txn = match_result['apple_txn']
        new_description = apple_txn['app_names']
        if apple_txn.get('publishers'):
            new_description += f" ({apple_txn['publishers']})"

        database.update_transaction_description(bank_transaction['id'], new_description)

        return match_result

    return None


def find_best_match_for_single_transaction(bank_txn, apple_transactions):
    """
    Find the best matching Apple transaction for a single bank transaction.

    Args:
        bank_txn: Bank transaction dictionary
        apple_transactions: List of Apple transaction dictionaries

    Returns:
        Match dictionary with apple_txn and confidence, or None
    """
    try:
        txn_date = datetime.strptime(bank_txn['date'], '%Y-%m-%d')
        txn_amount = abs(bank_txn['amount'])
    except:
        return None

    candidates = []

    for apple_txn in apple_transactions:
        try:
            apple_date = datetime.strptime(apple_txn['order_date'], '%Y-%m-%d')
            apple_amount = abs(apple_txn['total_amount'])
        except:
            continue

        # Check date proximity (±3 days)
        date_diff_days = abs((txn_date - apple_date).days)
        if date_diff_days > 3:
            continue

        # Check amount match
        if not amounts_match(txn_amount, apple_amount):
            continue

        # Calculate confidence
        confidence = calculate_confidence(txn_date, apple_date, txn_amount, apple_amount)

        candidates.append({
            'apple_txn': apple_txn,
            'confidence': confidence,
            'date_diff': date_diff_days
        })

    if not candidates:
        return None

    # Sort by confidence and date proximity
    candidates.sort(key=lambda x: (x['confidence'], -x['date_diff']), reverse=True)

    return candidates[0]
