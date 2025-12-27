"""
Huququllah Classification Suggester

This module provides smart suggestions for classifying transactions as essential or discretionary
based on historical user classification patterns.
"""

from collections import Counter, defaultdict

import database_postgres as database


def get_suggestion_for_transaction(transaction_id):
    """
    Get a smart suggestion for classifying a transaction as essential or discretionary.
    Only provides suggestions for expenses (negative amounts), not income.

    The suggestion is based on:
    1. Previous classifications for the same merchant
    2. Previous classifications for the same category
    3. Amount patterns for similar transactions

    Args:
        transaction_id: ID of the transaction to classify

    Returns:
        Dictionary with:
        - suggested_classification: 'essential', 'discretionary', or None
        - confidence: float between 0 and 1
        - reason: explanation of why this was suggested
    """
    transaction = database.get_transaction_by_id(transaction_id)
    if not transaction:
        return {
            "suggested_classification": None,
            "confidence": 0.0,
            "reason": "Transaction not found",
        }

    # Only suggest for expenses, not income
    # TrueLayer uses transaction_type: DEBIT = expense, CREDIT = income
    if transaction.get("transaction_type") == "CREDIT":
        return {
            "suggested_classification": None,
            "confidence": 0.0,
            "reason": "Income transactions are not subject to Huququllah",
        }

    merchant = transaction["merchant"]
    category = transaction["category"]
    amount = abs(transaction["amount"])

    # Get all classified expense transactions for learning (only expenses, not income)
    # TrueLayer uses transaction_type: DEBIT = expense, CREDIT = income
    all_transactions = database.get_all_transactions()
    classified = [
        t
        for t in all_transactions
        if t["huququllah_classification"] is not None
        and t.get("transaction_type") == "DEBIT"
    ]

    if not classified:
        return {
            "suggested_classification": None,
            "confidence": 0.0,
            "reason": "No historical classifications to learn from",
        }

    # Strategy 1: Exact merchant match (highest confidence)
    if merchant:
        merchant_classifications = [
            t["huququllah_classification"]
            for t in classified
            if t["merchant"] == merchant
        ]

        if merchant_classifications:
            counter = Counter(merchant_classifications)
            most_common = counter.most_common(1)[0]
            classification, count = most_common
            confidence = count / len(merchant_classifications)

            return {
                "suggested_classification": classification,
                "confidence": round(confidence, 2),
                "reason": f"Based on {count} previous transaction(s) from this merchant",
            }

    # Strategy 2: Category-based suggestion (medium confidence)
    category_classifications = [
        t["huququllah_classification"] for t in classified if t["category"] == category
    ]

    if category_classifications:
        counter = Counter(category_classifications)
        most_common = counter.most_common(1)[0]
        classification, count = most_common
        confidence = (
            count / len(category_classifications)
        ) * 0.7  # Reduce confidence for category-only match

        return {
            "suggested_classification": classification,
            "confidence": round(confidence, 2),
            "reason": f"Based on {count} previous {category} transaction(s)",
        }

    # Strategy 3: Amount-based suggestion (lower confidence)
    # Group classified transactions by amount ranges
    amount_ranges = {
        "small": (0, 20),
        "medium": (20, 100),
        "large": (100, float("inf")),
    }

    # Determine amount range for current transaction
    current_range = "large"
    for range_name, (min_amount, max_amount) in amount_ranges.items():
        if min_amount <= amount < max_amount:
            current_range = range_name
            break

    # Get classifications for similar amounts
    range_classifications = []
    for t in classified:
        t_amount = abs(t["amount"])
        for range_name, (min_amount, max_amount) in amount_ranges.items():
            if min_amount <= t_amount < max_amount and range_name == current_range:
                range_classifications.append(t["huququllah_classification"])
                break

    if range_classifications:
        counter = Counter(range_classifications)
        most_common = counter.most_common(1)[0]
        classification, count = most_common
        confidence = (
            count / len(range_classifications)
        ) * 0.5  # Lower confidence for amount-only match

        return {
            "suggested_classification": classification,
            "confidence": round(confidence, 2),
            "reason": f"Based on {count} similar-sized transaction(s) (£{amount:.2f})",
        }

    # No strong pattern found
    return {
        "suggested_classification": None,
        "confidence": 0.0,
        "reason": "Not enough data to make a suggestion",
    }


def get_category_classification_patterns():
    """
    Get classification patterns for each category based on expense transactions only.

    Returns:
        Dictionary mapping category names to their classification statistics:
        {
            'Groceries': {
                'essential_count': 45,
                'discretionary_count': 5,
                'essential_percentage': 90,
                'discretionary_percentage': 10,
                'most_common': 'essential'
            },
            ...
        }
    """
    all_transactions = database.get_all_transactions()
    # Only include expense transactions, not income
    # TrueLayer uses transaction_type: DEBIT = expense, CREDIT = income
    classified = [
        t
        for t in all_transactions
        if t["huququllah_classification"] is not None
        and t.get("transaction_type") == "DEBIT"
    ]

    # Group by category
    category_stats = defaultdict(lambda: {"essential": 0, "discretionary": 0})

    for txn in classified:
        category = txn["category"]
        classification = txn["huququllah_classification"]
        category_stats[category][classification] += 1

    # Convert to percentage and determine most common
    result = {}
    for category, stats in category_stats.items():
        total = stats["essential"] + stats["discretionary"]
        if total > 0:
            essential_pct = round((stats["essential"] / total) * 100, 1)
            discretionary_pct = round((stats["discretionary"] / total) * 100, 1)
            most_common = (
                "essential"
                if stats["essential"] > stats["discretionary"]
                else "discretionary"
            )

            result[category] = {
                "essential_count": stats["essential"],
                "discretionary_count": stats["discretionary"],
                "essential_percentage": essential_pct,
                "discretionary_percentage": discretionary_pct,
                "most_common": most_common,
            }

    return result


def get_bulk_suggestions(transaction_ids):
    """
    Get suggestions for multiple transactions at once.

    Args:
        transaction_ids: List of transaction IDs

    Returns:
        Dictionary mapping transaction_id -> suggestion
    """
    suggestions = {}
    for txn_id in transaction_ids:
        suggestions[txn_id] = get_suggestion_for_transaction(txn_id)
    return suggestions
