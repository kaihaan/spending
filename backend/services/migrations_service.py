"""
Migrations Service - Database Migration Utilities

Provides data migration operations for:
- Fixing merchant names in card payment transactions
- Adding schema columns to existing databases
- Reapplying account mappings to historical transactions

These are typically run once when updating the database schema or cleaning data.
"""

from database import transactions as db_transactions
from database import base
from mcp.merchant_normalizer import detect_account_pattern
import re


# ============================================================================
# Merchant Name Cleanups
# ============================================================================

def fix_card_payment_merchants() -> dict:
    """
    Extract real merchant names from card payment transactions.

    UK transactions often have format: "CARD PAYMENT TO MERCHANT NAME"
    This migration extracts the actual merchant name and updates the record.

    Returns:
        Dict with transactions_updated count and sample changes
    """
    all_transactions = db_transactions.get_all_truelayer_transactions()

    updated_count = 0
    changes = []

    # Pattern: "CARD PAYMENT TO <merchant>" or "CARD PAYMENT <merchant>"
    card_payment_pattern = re.compile(r'^CARD\s+PAYMENT\s+(?:TO\s+)?(.+)$', re.IGNORECASE)

    for txn in all_transactions:
        description = txn.get('description', '') or ''
        current_merchant = txn.get('merchant_name', '') or ''

        # Try to extract merchant from description
        match = card_payment_pattern.match(description)
        if match:
            extracted_merchant = match.group(1).strip()

            # Only update if different from current merchant
            if extracted_merchant and extracted_merchant != current_merchant:
                success = db_transactions.update_truelayer_transaction_merchant(
                    txn['id'],
                    extracted_merchant
                )

                if success:
                    updated_count += 1
                    if len(changes) < 10:  # Keep first 10 as examples
                        changes.append({
                            'transaction_id': txn['id'],
                            'original': current_merchant,
                            'extracted': extracted_merchant,
                            'description': description[:80]
                        })

    return {
        'success': True,
        'transactions_updated': updated_count,
        'transactions_total': len(all_transactions),
        'sample_changes': changes
    }


# ============================================================================
# Schema Migrations
# ============================================================================

def migrate_add_huququllah_column() -> bool:
    """
    Add huququllah_classification column to truelayer_transactions table.

    This migration is for existing databases created before the Huququllah
    feature was added. New databases already have this column in the schema.

    Returns:
        True if column was added, False if already exists
    """
    with base.get_db() as conn:
        with conn.cursor() as cursor:
            # Check if column already exists
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'truelayer_transactions'
                AND column_name = 'huququllah_classification'
            """)

            exists = cursor.fetchone() is not None

            if exists:
                return False

            # Add column with CHECK constraint
            cursor.execute("""
                ALTER TABLE truelayer_transactions
                ADD COLUMN huququllah_classification VARCHAR(20)
                CHECK(huququllah_classification IN ('essential', 'discretionary'))
            """)

            conn.commit()
            return True


# ============================================================================
# Account Mapping Reapplication
# ============================================================================

def reapply_account_mappings() -> dict:
    """
    Apply all account mappings to existing TrueLayer transactions.

    Scans all transactions for account number patterns (UK sort code + account number)
    and updates merchant names to use the friendly names from account mappings.

    Example:
        Transaction description: "TRANSFER TO 20-12-34 12345678"
        Account mapping: 20-12-34 12345678 → "Savings Account"
        Updated merchant: "Payment to Savings Account"

    Returns:
        Dict with transactions_updated, transactions_total, and message
    """
    # Get all account mappings
    mappings = db_transactions.get_all_account_mappings()

    if not mappings:
        return {
            'success': True,
            'transactions_updated': 0,
            'transactions_total': 0,
            'message': 'No account mappings configured'
        }

    # Create lookup dict for mappings
    mapping_lookup = {
        (m['sort_code'], m['account_number']): m['friendly_name']
        for m in mappings
    }

    # Get all TrueLayer transactions
    transactions = db_transactions.get_all_truelayer_transactions()
    total = len(transactions)
    updated = 0

    for txn in transactions:
        description = txn.get('description', '') or ''
        merchant = txn.get('merchant_name', '') or ''

        # Try to detect account pattern in description or merchant
        account_info = detect_account_pattern(description)
        if not account_info:
            account_info = detect_account_pattern(merchant)

        if account_info:
            sort_code, account_number = account_info
            friendly_name = mapping_lookup.get((sort_code, account_number))

            if friendly_name:
                new_merchant = f"Payment to {friendly_name}"

                # Only update if merchant name is different
                if merchant != new_merchant:
                    success = db_transactions.update_truelayer_transaction_merchant(
                        txn['id'],
                        new_merchant
                    )
                    if success:
                        updated += 1

    return {
        'success': True,
        'transactions_updated': updated,
        'transactions_total': total,
        'message': f'Applied {len(mappings)} account mappings to {updated} transactions'
    }
