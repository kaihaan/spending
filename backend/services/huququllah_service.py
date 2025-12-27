"""
Huququllah Service - Business Logic

Orchestrates Huququllah (Islamic wealth obligation) calculations:
- Essential vs discretionary classification
- 19% calculation on discretionary spending
- Smart suggestions for transaction classification
- Unclassified transaction tracking

Huququllah Context:
Members of the Baha'i Faith are required to pay 19% of their discretionary
income after essential expenses (Huququllah means "Right of God").

Separates business logic from HTTP routing concerns.
"""

from database import transactions as db_transactions
from mcp.huququllah_classifier import (
    get_suggestion_for_transaction as get_smart_suggestion,
)

# ============================================================================
# Huququllah Operations
# ============================================================================


def get_suggestion(transaction_id: int) -> dict:
    """
    Get a smart suggestion for classifying a transaction.

    Uses pattern matching and historical data to suggest whether
    a transaction should be classified as essential or discretionary.

    Args:
        transaction_id: Transaction ID to classify

    Returns:
        Suggestion dict with classification and confidence
    """
    suggestion = get_smart_suggestion(transaction_id)
    return suggestion


def get_summary(date_from: str = None, date_to: str = None) -> dict:
    """
    Get Huququllah summary with essential vs discretionary totals and 19% calculation.

    Args:
        date_from: Optional start date filter (YYYY-MM-DD)
        date_to: Optional end date filter (YYYY-MM-DD)

    Returns:
        Summary dict with:
        - total_essential: Total essential spending
        - total_discretionary: Total discretionary spending
        - huququllah_due: 19% of discretionary (amount owed)
        - unclassified_count: Number of unclassified transactions
        - unclassified_amount: Total amount of unclassified transactions
    """
    summary = db_transactions.get_huququllah_summary(date_from, date_to)
    return summary


def get_unclassified_transactions() -> list:
    """
    Get all transactions that haven't been classified yet.

    Returns transactions that have no manual classification and no
    LLM-based essential/discretionary classification.

    Returns:
        List of unclassified transaction dicts
    """
    transactions = db_transactions.get_unclassified_transactions()
    return transactions
