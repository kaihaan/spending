"""
Pre-Enrichment Status Detector

Determines the pre_enrichment_status for transactions based on description/merchant patterns.
This helps identify transactions that should be matched with Apple/Amazon data before LLM enrichment.

Status values:
- 'None': Not from a matchable source (default for most transactions)
- 'Matched': Already matched with Apple/Amazon/Returns data
- 'Apple': Apple App Store transaction not yet matched
- 'AMZN': Amazon purchase not yet matched
- 'AMZN RTN': Amazon return not yet matched
"""

# Apple patterns (from apple_matcher.py)
# These identify genuine Apple merchant transactions
APPLE_PATTERNS = [
    "APPLE.COM",
    "APPLE COM",
    "APP STORE",
    "APPSTORE",
    "ITUNES",
    "APPLE SERVICES",
    "APPLE BILL",
]

# Amazon patterns (from amazon_matcher.py)
AMAZON_PATTERNS = ["AMAZON", "AMZN", "AMZ"]

# Patterns that indicate Apple Pay as a payment method (not Apple purchase)
# Only used to exclude non-Apple transactions using Apple Pay
APPLE_PAY_EXCLUSIONS = ["APPLE PAY", "APPLEPAY", "VIA APPLE PAY"]


def detect_pre_enrichment_status(
    description: str, merchant_name: str, transaction_type: str
) -> str:
    """
    Detect the pre_enrichment_status for a transaction based on description patterns.

    This analyzes the transaction description and merchant name to determine if it's
    from a matchable source (Apple, Amazon) and what type of transaction it is.

    Args:
        description: Transaction description from bank
        merchant_name: Merchant name from transaction (may be None)
        transaction_type: 'CREDIT' or 'DEBIT' from TrueLayer

    Returns:
        Status string:
        - 'None': Not from a matchable source
        - 'Apple': Apple App Store transaction (not yet matched)
        - 'AMZN': Amazon purchase (not yet matched)
        - 'AMZN RTN': Amazon return (not yet matched)
    """
    # Combine description and merchant for pattern matching
    text = ((description or "") + " " + (merchant_name or "")).upper()

    # Check for Apple purchase (genuine Apple merchant, not just Apple Pay payment method)
    is_apple_merchant = any(pattern in text for pattern in APPLE_PATTERNS)

    if is_apple_merchant:
        return "Apple"

    # If it's only Apple Pay as payment method (no Apple merchant), it's not matchable
    is_apple_pay_only = any(pattern in text for pattern in APPLE_PAY_EXCLUSIONS)
    if is_apple_pay_only:
        # This is "TESCO VIA APPLE PAY" type - not an Apple purchase
        pass  # Fall through to other checks

    # Check for Amazon patterns
    is_amazon = any(pattern in text for pattern in AMAZON_PATTERNS)

    if is_amazon:
        # Amazon return (CREDIT with Amazon keywords)
        if transaction_type == "CREDIT":
            return "AMZN RTN"
        return "AMZN"

    return "None"


def is_matchable_transaction(status: str) -> bool:
    """
    Check if a status indicates a transaction that can be matched.

    Args:
        status: Pre-enrichment status string

    Returns:
        True if the transaction is from a matchable source (Apple, Amazon)
    """
    return status in ("Apple", "AMZN", "AMZN RTN")


def get_status_display_name(status: str) -> str:
    """
    Get a user-friendly display name for a status.

    Args:
        status: Pre-enrichment status string

    Returns:
        Human-readable status name
    """
    names = {
        "None": "Not Matchable",
        "Matched": "Matched",
        "Apple": "Apple App Store",
        "AMZN": "Amazon Purchase",
        "AMZN RTN": "Amazon Return",
    }
    return names.get(status, status)
