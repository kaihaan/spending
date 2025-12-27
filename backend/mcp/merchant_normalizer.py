"""
Merchant Name Normalizer
Standardizes merchant names by removing order IDs, transaction references, and
applying merchant-specific mappings to group related transactions.
Includes account number detection for friendly payment names.
"""

import re

# Merchant-specific mappings for better normalization
MERCHANT_MAPPINGS: dict[str, str] = {
    "amznmktplace": "Amazon Marketplace",
    "amazon marketplace": "Amazon Marketplace",
    "www.amazon.*": "Amazon",
    "amazon.co.uk": "Amazon.co.uk",
    "amazon.com": "Amazon.com",
    "amazon.de": "Amazon.de",
    "amazon.fr": "Amazon.fr",
    "amazon prime": "Amazon Prime",
    "ebay": "eBay",
    "paypal": "PayPal",
}


def detect_account_pattern(text: str) -> tuple[str, str] | None:
    """
    Detect bank account details (sort code + account number) in text.

    Patterns:
    - ACCOUNT 090129 30458079
    - ACCOUNT SAVING R27077663
    - TO ACCOUNT 123456 78901234

    Args:
        text: Text to search for account details

    Returns:
        Tuple of (sort_code, account_number) or None if not found
    """
    # Pattern 1: ACCOUNT [6 digits] [8 digits]
    # Example: "ACCOUNT 090129 30458079"
    pattern1 = r"ACCOUNT\s+(\d{6})\s+(\d{8})"
    match = re.search(pattern1, text, re.IGNORECASE)
    if match:
        return (match.group(1), match.group(2))

    # Pattern 2: Could also check for variations
    # Add more patterns here if needed based on actual transaction formats

    return None


def apply_account_mappings(merchant: str, description: str = "") -> str:
    """
    Replace account details with friendly name if mapping exists.

    Args:
        merchant: Current merchant name
        description: Original transaction description (for context)

    Returns:
        Merchant name with account mapping applied, or original if no mapping found
    """
    # Try to detect account pattern in both merchant and description
    account_info = detect_account_pattern(merchant)
    if not account_info:
        account_info = detect_account_pattern(description)

    if not account_info:
        return merchant

    sort_code, account_number = account_info

    # Look up mapping from database
    try:
        import database

        mapping = database.get_account_mapping_by_details(sort_code, account_number)
        if mapping:
            # Replace with friendly name
            return f"Payment to {mapping['friendly_name']}"
    except Exception:
        # If database lookup fails, just return original
        pass

    return merchant


def normalize_merchant_name(merchant: str, description: str = "") -> str:
    """
    Normalize merchant name by removing order IDs and applying standardization.

    Handles common patterns:
    - Amazon.co.uk*6Q22J0R25 -> Amazon.co.uk
    - AMZNMktplace*E25645GE5 -> Amazon Marketplace
    - eBay O*08-12045-48091 -> eBay
    - CREDIT FROM AMZNMktplace -> Amazon Marketplace
    - WWW.AMAZON.* TH2TK7EM4 -> Amazon
    - ACCOUNT 090129 30458079 -> Payment to [Friendly Name] (if mapped)

    Args:
        merchant: Raw merchant name from transaction
        description: Original transaction description (for account detection)

    Returns:
        Normalized merchant name
    """
    if not merchant or not merchant.strip():
        return merchant

    original = merchant
    cleaned = merchant.strip()

    # First, check for account mappings (highest priority)
    mapped_merchant = apply_account_mappings(cleaned, description)
    if mapped_merchant != cleaned:
        return mapped_merchant

    # Remove "CREDIT FROM" prefix
    cleaned = re.sub(r"^CREDIT FROM\s+", "", cleaned, flags=re.IGNORECASE)

    # Remove "REFUND FROM" prefix
    cleaned = re.sub(r"^REFUND FROM\s+", "", cleaned, flags=re.IGNORECASE)

    # eBay specific patterns
    # "eBay O*08-12045-48091" -> "eBay"
    if re.match(r"ebay\s+O\*\d+", cleaned, flags=re.IGNORECASE):
        cleaned = "eBay"

    # Remove asterisk and everything after (order IDs)
    # "Amazon.co.uk*6Q22J0R25" -> "Amazon.co.uk"
    # "AMZNMktplace*E25645GE5" -> "AMZNMktplace"
    cleaned = re.sub(r"\*[A-Z0-9]+\d+$", "", cleaned, flags=re.IGNORECASE)

    # Remove space followed by long alphanumeric code (order IDs)
    # "WWW.AMAZON.* TH2TK7EM4" -> "WWW.AMAZON.*"
    cleaned = re.sub(r"\s+[A-Z0-9]{8,}$", "", cleaned, flags=re.IGNORECASE)

    # Remove trailing asterisk if present
    cleaned = re.sub(r"\*+$", "", cleaned)

    # Remove trailing dots if present
    cleaned = cleaned.rstrip(".")

    # Trim whitespace
    cleaned = cleaned.strip()

    # Apply merchant-specific mappings
    cleaned_lower = cleaned.lower()
    for pattern, standard_name in MERCHANT_MAPPINGS.items():
        if cleaned_lower == pattern or cleaned_lower.startswith(pattern):
            cleaned = standard_name
            break

    # If normalization resulted in empty string, return original
    if not cleaned:
        return original

    return cleaned


def get_merchant_group(merchant: str) -> str:
    """
    Get the merchant group for analytics.
    Groups related merchants together (e.g., all Amazon domains).

    Args:
        merchant: Normalized merchant name

    Returns:
        Merchant group name
    """
    merchant_lower = merchant.lower()

    # Amazon group
    if "amazon" in merchant_lower:
        if "marketplace" in merchant_lower:
            return "Amazon Marketplace"
        if "prime" in merchant_lower:
            return "Amazon Prime"
        return "Amazon"

    # eBay group
    if "ebay" in merchant_lower:
        return "eBay"

    # PayPal group
    if "paypal" in merchant_lower:
        return "PayPal"

    # Default: use the merchant name itself
    return merchant


def batch_normalize_merchants(merchants: list) -> dict[str, str]:
    """
    Normalize a batch of merchant names.

    Args:
        merchants: List of raw merchant names

    Returns:
        Dictionary mapping original merchant names to normalized names
    """
    result = {}
    for merchant in merchants:
        if merchant:
            result[merchant] = normalize_merchant_name(merchant)
    return result


def get_normalization_stats(transactions: list) -> dict:
    """
    Analyze how many transactions would be affected by normalization.

    Args:
        transactions: List of transaction dictionaries with 'merchant' field

    Returns:
        Dictionary with normalization statistics
    """
    original_merchants = set()
    normalized_merchants = set()
    changes = []

    for txn in transactions:
        merchant = txn.get("merchant")
        if merchant:
            normalized = normalize_merchant_name(merchant)
            original_merchants.add(merchant)
            normalized_merchants.add(normalized)

            if merchant != normalized:
                changes.append(
                    {
                        "original": merchant,
                        "normalized": normalized,
                        "transaction_id": txn.get("id"),
                    }
                )

    return {
        "original_merchant_count": len(original_merchants),
        "normalized_merchant_count": len(normalized_merchants),
        "merchants_reduced_by": len(original_merchants) - len(normalized_merchants),
        "transactions_affected": len(changes),
        "sample_changes": changes[:10],  # Show first 10 examples
    }
