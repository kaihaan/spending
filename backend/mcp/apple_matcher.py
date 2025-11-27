"""
Apple Transactions Matcher MCP Component
Matches Apple/App Store transactions to bank transactions.
CRITICAL: Excludes Apple Pay payment method transactions.
"""

from datetime import datetime, timedelta
import database
import re


def is_apple_transaction(description, merchant):
    """
    Check if transaction is from Apple/App Store, NOT Apple Pay as a payment method.

    CRITICAL: This function must allow genuine Apple transactions (APPLE.COM/BILL,
    APPLE SERVICES, etc.) even if they mention VIA APPLE PAY as the payment method.
    It only rejects VIA APPLE PAY when it's a payment method for OTHER merchants
    (e.g., "TESCO VIA APPLE PAY").

    Args:
        description: Transaction description
        merchant: Merchant name

    Returns:
        Boolean indicating if this is a genuine Apple transaction
    """
    # Combine description and merchant for checking
    text = ((description or '') + ' ' + (merchant or '')).upper()

    # First check for genuine Apple/App Store merchants
    # These are actual purchases from Apple and should be matched regardless of VIA APPLE PAY
    apple_patterns = [
        'APPLE.COM',
        'APPLE COM',
        'APP STORE',
        'APPSTORE',
        'ITUNES',
        'APPLE SERVICES',
        'APPLE BILL',
    ]

    is_apple_merchant = any(pattern in text for pattern in apple_patterns)

    # If it's a genuine Apple merchant, accept it even if it mentions VIA APPLE PAY
    # (VIA APPLE PAY is just the payment method)
    if is_apple_merchant:
        return True

    # CRITICAL: Reject VIA APPLE PAY only for non-Apple merchants
    # These are payment methods for other merchants, not actual Apple purchases
    if any(pattern in text for pattern in ['APPLE PAY', 'APPLEPAY', 'VIA APPLE PAY']):
        return False

    return False


def extract_date_from_description(description):
    """
    Extract transaction date from description text.

    Looks for patterns like:
    - "ON 19-09-2025" (DD-MM-YYYY)
    - "ON 19/09/2025" (DD/MM/YYYY)
    - "19-09-2025" (DD-MM-YYYY without prefix)
    - "19/09/2025" (DD/MM/YYYY without prefix)

    Args:
        description: Transaction description text

    Returns:
        datetime object if date found, None otherwise
    """
    if not description:
        return None

    # Try patterns with "ON" prefix first
    patterns = [
        r'ON\s+(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # ON 19-09-2025 or ON 19/09/2025
        r'\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b',   # 19-09-2025 or 19/09/2025
    ]

    for pattern in patterns:
        match = re.search(pattern, description)
        if match:
            try:
                day, month, year = match.groups()
                return datetime.strptime(f"{day}-{month}-{year}", '%d-%m-%Y')
            except ValueError:
                # Invalid date values, continue to next pattern
                continue

    return None


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

            # Populate lookup_description with app name (keep original description)
            lookup_value = apple_txn['app_names']
            if apple_txn.get('publishers'):
                lookup_value += f" ({apple_txn['publishers']})"

            database.update_transaction_lookup_description(
                match_result['transaction']['id'],
                lookup_value
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

    For bank transactions with dates in their description (e.g., "ON 19-09-2025"),
    uses that extracted date for matching instead of the transaction date field.

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
            txn_amount = abs(bank_txn['amount'])
        except:
            continue

        # Try to extract date from description first (e.g., "ON 19-09-2025")
        description_date = extract_date_from_description(bank_txn.get('description', ''))
        if description_date:
            txn_date = description_date
        else:
            # Fall back to transaction date field
            try:
                txn_date = datetime.strptime(bank_txn['date'], '%Y-%m-%d')
            except:
                continue

        # Check date proximity (bank transaction must be 0-2 days AFTER Apple date)
        date_diff_days = (txn_date - apple_date).days
        if date_diff_days < 0 or date_diff_days > 2:
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
    Bank transaction must be 0-2 days AFTER Apple order date.

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

    # Date proximity bonus (only 0-2 days after are possible)
    date_diff_days = (txn_date - apple_date).days
    if date_diff_days == 0:
        confidence = max(confidence, 100)  # Perfect match (same day)
    elif date_diff_days == 1:
        confidence = max(confidence, 95)   # 1 day after
    elif date_diff_days == 2:
        confidence = max(confidence, 85)   # 2 days after

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

        # Populate lookup_description with app name (keep original description)
        apple_txn = match_result['apple_txn']
        lookup_value = apple_txn['app_names']
        if apple_txn.get('publishers'):
            lookup_value += f" ({apple_txn['publishers']})"

        database.update_transaction_lookup_description(bank_transaction['id'], lookup_value)

        return match_result

    return None


def find_best_match_for_single_transaction(bank_txn, apple_transactions):
    """
    Find the best matching Apple transaction for a single bank transaction.

    For bank transactions with dates in their description (e.g., "ON 19-09-2025"),
    uses that extracted date for matching instead of the transaction date field.

    Args:
        bank_txn: Bank transaction dictionary
        apple_transactions: List of Apple transaction dictionaries

    Returns:
        Match dictionary with apple_txn and confidence, or None
    """
    try:
        txn_amount = abs(bank_txn['amount'])
    except:
        return None

    # Try to extract date from description first (e.g., "ON 19-09-2025")
    description_date = extract_date_from_description(bank_txn.get('description', ''))
    if description_date:
        txn_date = description_date
    else:
        # Fall back to transaction date field
        try:
            txn_date = datetime.strptime(bank_txn['date'], '%Y-%m-%d')
        except:
            return None

    candidates = []

    for apple_txn in apple_transactions:
        try:
            apple_date = datetime.strptime(apple_txn['order_date'], '%Y-%m-%d')
            apple_amount = abs(apple_txn['total_amount'])
        except:
            continue

        # Check date proximity (bank transaction must be 0-2 days AFTER Apple date)
        date_diff_days = (txn_date - apple_date).days
        if date_diff_days < 0 or date_diff_days > 2:
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
