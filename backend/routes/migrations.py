"""
Migrations Routes - Flask Blueprint

Handles database migration endpoints:
- Merchant name cleanup for card payments
- Schema migrations (e.g., adding Huququllah column)
- Reapplying account mappings to historical data

Migration Context:
These are one-time operations run when updating database schemas or
cleaning up historical transaction data. They modify existing records
in bulk and should be used with caution.

Routes are thin controllers that delegate to migrations_service for business logic.
"""

import traceback

from flask import Blueprint, jsonify

from services import migrations_service

migrations_bp = Blueprint("migrations", __name__, url_prefix="/api/migrations")


# ============================================================================
# Merchant Name Cleanups
# ============================================================================


@migrations_bp.route("/fix-card-payment-merchants", methods=["POST"])
def fix_card_payment_merchants():
    """
    Extract real merchant names from card payment transactions.

    Processes transactions with descriptions like:
    - "CARD PAYMENT TO MERCHANT NAME"
    - "CARD PAYMENT MERCHANT NAME"

    Extracts the actual merchant name and updates the merchant_name field.

    Returns:
        Dict with success, transactions_updated, transactions_total, and sample_changes

    Example response:
        {
            "success": true,
            "transactions_updated": 45,
            "transactions_total": 1500,
            "sample_changes": [
                {
                    "transaction_id": 123,
                    "original": "",
                    "extracted": "TESCO STORES",
                    "description": "CARD PAYMENT TO TESCO STORES"
                }
            ]
        }
    """
    try:
        result = migrations_service.fix_card_payment_merchants()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Fix card payment merchants error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Schema Migrations
# ============================================================================


@migrations_bp.route("/add-huququllah-column", methods=["POST"])
def migrate_huququllah_column():
    """
    Migration endpoint to add huququllah_classification column.

    This migration is for existing databases created before the Huququllah
    feature was added. New databases already have this column in the schema.

    The column is added with a CHECK constraint to ensure valid values:
    - 'essential': Essential spending (not subject to Huququllah)
    - 'discretionary': Discretionary spending (19% obligation applies)

    Returns:
        Dict with success, column_added boolean, and message

    Example response:
        {
            "success": true,
            "column_added": true,
            "message": "Migration completed successfully"
        }

        OR (if column already exists):

        {
            "success": true,
            "column_added": false,
            "message": "Column already exists"
        }
    """
    try:
        was_added = migrations_service.migrate_add_huququllah_column()

        return jsonify(
            {
                "success": True,
                "column_added": was_added,
                "message": "Migration completed successfully"
                if was_added
                else "Column already exists",
            }
        )

    except Exception as e:
        print(f"❌ Huququllah column migration error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Account Mapping Reapplication
# ============================================================================


@migrations_bp.route("/reapply-account-mappings", methods=["POST"])
def reapply_account_mappings():
    """
    Apply all account mappings to existing TrueLayer transactions.

    Scans all transactions for UK account number patterns (sort code + account number)
    and updates merchant names to use the friendly names from account mappings.

    Example transformation:
        Before:
            description: "TRANSFER TO 20-12-34 12345678"
            merchant_name: ""

        After (with account mapping: 20-12-34 12345678 → "Savings Account"):
            merchant_name: "Payment to Savings Account"

    This is useful when:
    1. New account mappings are created and need to be applied to historical data
    2. Account mappings are updated and changes need to propagate
    3. Merchant names need to be recalculated after data cleanup

    Returns:
        Dict with success, transactions_updated, transactions_total, and message

    Example response:
        {
            "success": true,
            "transactions_updated": 156,
            "transactions_total": 1500,
            "message": "Applied 3 account mappings to 156 transactions"
        }

        OR (if no mappings configured):

        {
            "success": true,
            "transactions_updated": 0,
            "transactions_total": 0,
            "message": "No account mappings configured"
        }
    """
    try:
        result = migrations_service.reapply_account_mappings()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Reapply account mappings error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
