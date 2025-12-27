"""
Direct Debit Service - Business Logic

Orchestrates direct debit management including:
- Payee detection and tracking
- Custom payee-to-merchant mappings
- Bulk application of mappings to transactions
- New payee discovery

Direct Debit Context:
UK bank transactions for direct debits often have cryptic payee names
(e.g., "DD EMMANUEL COLL 123456"). This service helps users create
readable merchant names and consistent categorization.

Separates business logic from HTTP routing concerns.
"""

from database import direct_debit as db_direct_debit
import cache_manager


# ============================================================================
# Direct Debit Operations
# ============================================================================

def get_payees() -> list:
    """
    Get unique direct debit payees from transactions.

    Returns list of payees with:
    - Transaction counts
    - Current enrichment status
    - Sample descriptions

    Returns:
        List of payee dicts
    """
    payees = db_direct_debit.get_direct_debit_payees()
    return payees


def get_mappings() -> list:
    """
    Get all configured direct debit mappings.

    Returns:
        List of mapping dicts with payee patterns and enrichment data
    """
    mappings = db_direct_debit.get_direct_debit_mappings()
    return mappings


def save_mapping(payee_pattern: str, normalized_name: str, category: str,
                  subcategory: str = None, merchant_type: str = None) -> dict:
    """
    Create or update a direct debit mapping.

    Args:
        payee_pattern: Pattern to match (e.g., "EMMANUEL COLL")
        normalized_name: Clean merchant name (e.g., "Emmanuel College")
        category: Category to assign
        subcategory: Optional subcategory
        merchant_type: Optional merchant type

    Returns:
        Success dict with mapping_id

    Raises:
        ValueError: If required fields missing
    """
    if not payee_pattern or not normalized_name or not category:
        raise ValueError('Missing required fields: payee_pattern, normalized_name, category')

    mapping_id = db_direct_debit.save_direct_debit_mapping(
        payee_pattern=payee_pattern,
        normalized_name=normalized_name,
        category=category,
        subcategory=subcategory,
        merchant_type=merchant_type
    )

    return {
        'success': True,
        'mapping_id': mapping_id,
        'message': f'Mapping saved for {payee_pattern}'
    }


def delete_mapping(mapping_id: int) -> dict:
    """
    Delete a direct debit mapping.

    Args:
        mapping_id: Mapping ID to delete

    Returns:
        Success dict

    Raises:
        ValueError: If mapping not found
    """
    deleted = db_direct_debit.delete_direct_debit_mapping(mapping_id)

    if not deleted:
        raise ValueError('Mapping not found')

    return {
        'success': True,
        'message': 'Mapping deleted'
    }


def apply_mappings() -> dict:
    """
    Apply all direct debit mappings to transactions.

    Re-enriches all direct debit transactions using the configured mappings.
    Invalidates transaction cache after application.

    Returns:
        Dict with updated_count and transactions list
    """
    result = db_direct_debit.apply_direct_debit_mappings()

    # Invalidate transaction cache
    cache_manager.cache_invalidate_transactions()

    return {
        'success': True,
        'updated_count': result['updated_count'],
        'transactions': result['transactions'],
        'message': f"Updated {result['updated_count']} transactions"
    }


def get_new_payees() -> dict:
    """
    Get newly detected direct debit payees that haven't been mapped.

    Returns list of unmapped payees with:
    - Transaction counts
    - Mandate numbers
    - Sample descriptions

    Returns:
        Dict with new payees list
    """
    result = db_direct_debit.detect_new_direct_debits()
    return result
