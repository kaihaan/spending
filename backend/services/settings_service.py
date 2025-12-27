"""
Settings Service - Business Logic

Orchestrates user settings management including:
- Account mappings: Friendly names for bank accounts (sort code + account number)
- Account discovery: Automatic detection of unmapped accounts in transactions

Account Mapping Context:
UK transactions often include cryptic account numbers in descriptions.
Users can map these to friendly names (e.g., "20-12-34 12345678" → "Savings Account").

Separates business logic from HTTP routing concerns.
"""

import re

from database import transactions as db_transactions
from mcp.merchant_normalizer import detect_account_pattern

# ============================================================================
# Account Mappings
# ============================================================================


def get_account_mappings() -> list:
    """
    Get all account mappings.

    Returns:
        List of account mapping dicts with sort_code, account_number, friendly_name
    """
    mappings = db_transactions.get_all_account_mappings()
    return mappings


def create_account_mapping(
    sort_code: str, account_number: str, friendly_name: str
) -> dict:
    """
    Create a new account mapping.

    Args:
        sort_code: 6-digit sort code (will be normalized)
        account_number: 8-digit account number (will be normalized)
        friendly_name: Human-readable account name

    Returns:
        Dict with success and mapping id

    Raises:
        ValueError: If required fields missing or validation fails
    """
    if not sort_code or not account_number or not friendly_name:
        raise ValueError("Missing required fields")

    # Normalize format (remove hyphens and spaces)
    sort_code = str(sort_code).replace("-", "").replace(" ", "")
    account_number = str(account_number).replace(" ", "")

    # Validate format
    if not re.match(r"^\d{6}$", sort_code):
        raise ValueError("Sort code must be 6 digits")

    if not re.match(r"^\d{8}$", account_number):
        raise ValueError("Account number must be 8 digits")

    mapping_id = db_transactions.add_account_mapping(
        sort_code, account_number, friendly_name
    )

    if mapping_id is None:
        raise ValueError("Account mapping already exists")

    return {"success": True, "id": mapping_id}


def update_account_mapping(mapping_id: int, friendly_name: str) -> dict:
    """
    Update an existing account mapping.

    Args:
        mapping_id: Mapping ID to update
        friendly_name: New friendly name

    Returns:
        Success dict

    Raises:
        ValueError: If friendly_name missing or mapping not found
    """
    if not friendly_name:
        raise ValueError("Missing friendly_name")

    success = db_transactions.update_account_mapping(mapping_id, friendly_name)

    if not success:
        raise ValueError("Account mapping not found")

    return {"success": True}


def delete_account_mapping(mapping_id: int) -> dict:
    """
    Delete an account mapping.

    Args:
        mapping_id: Mapping ID to delete

    Returns:
        Success dict

    Raises:
        ValueError: If mapping not found
    """
    success = db_transactions.delete_account_mapping(mapping_id)

    if not success:
        raise ValueError("Account mapping not found")

    return {"success": True}


# ============================================================================
# Account Discovery
# ============================================================================


def discover_account_mappings() -> list:
    """
    Scan TrueLayer transactions for unmapped account patterns.

    Detects account numbers in transaction descriptions and returns
    unmapped accounts with usage counts and sample descriptions.

    Returns:
        List of discovered account dicts sorted by frequency:
        - sort_code: Detected sort code
        - account_number: Detected account number
        - count: Number of transactions
        - sample_description: Example transaction description
    """
    # Get all transactions
    transactions = db_transactions.get_all_truelayer_transactions()

    # Get existing mappings to filter them out
    existing_mappings = db_transactions.get_all_account_mappings()
    mapped_accounts = {(m["sort_code"], m["account_number"]) for m in existing_mappings}

    # Scan for account patterns
    discovered = {}  # key: (sort_code, account_number), value: {count, sample_description}

    for txn in transactions:
        description = txn.get("description", "") or ""
        merchant = txn.get("merchant_name", "") or ""

        # Try to detect account pattern in description or merchant
        account_info = detect_account_pattern(description)
        if not account_info:
            account_info = detect_account_pattern(merchant)

        if account_info:
            sort_code, account_number = account_info

            # Skip if already mapped
            if (sort_code, account_number) in mapped_accounts:
                continue

            key = (sort_code, account_number)
            if key not in discovered:
                discovered[key] = {
                    "sort_code": sort_code,
                    "account_number": account_number,
                    "sample_description": description[:100]
                    if description
                    else merchant[:100],
                    "count": 0,
                }
            discovered[key]["count"] += 1

    # Convert to list and sort by count descending
    result = sorted(discovered.values(), key=lambda x: x["count"], reverse=True)

    return result
