"""
Direct Debit Routes - Flask Blueprint

Handles direct debit management endpoints:
- Payee detection and listing
- Custom payee-to-merchant mappings
- Bulk application of mappings
- New payee discovery

Direct Debit Context:
UK bank transactions for direct debits often have cryptic payee names
(e.g., "DD EMMANUEL COLL 123456"). This helps users create readable
merchant names and consistent categorization.

Routes are thin controllers that delegate to direct_debit_service for business logic.
"""

import traceback

from flask import Blueprint, jsonify, request

from services import direct_debit_service

direct_debit_bp = Blueprint("direct_debit", __name__, url_prefix="/api/direct-debit")


# ============================================================================
# Direct Debit Operations
# ============================================================================


@direct_debit_bp.route("/payees", methods=["GET"])
def get_payees():
    """
    Get unique direct debit payees from transactions.

    Returns list of payees with transaction counts and current enrichment status.

    Returns:
        List of payee dicts with counts and sample descriptions
    """
    try:
        payees = direct_debit_service.get_payees()
        return jsonify(payees)

    except Exception as e:
        print(f"❌ Direct debit payees error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@direct_debit_bp.route("/mappings", methods=["GET"])
def get_mappings():
    """
    Get all configured direct debit mappings.

    Returns:
        List of mapping dicts with payee patterns and enrichment data
    """
    try:
        mappings = direct_debit_service.get_mappings()
        return jsonify(mappings)

    except Exception as e:
        print(f"❌ Direct debit mappings error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@direct_debit_bp.route("/mappings", methods=["POST"])
def save_mapping():
    """
    Create or update a direct debit mapping.

    Request body:
        payee_pattern (str): Pattern to match (e.g., "EMMANUEL COLL") - required
        normalized_name (str): Clean merchant name (e.g., "Emmanuel College") - required
        category (str): Category to assign - required
        subcategory (str): Optional subcategory
        merchant_type (str): Optional merchant type

    Returns:
        Success dict with mapping_id

    Example:
        {
            "payee_pattern": "EMMANUEL COLL",
            "normalized_name": "Emmanuel College",
            "category": "Charity",
            "subcategory": "Emmanuel College",
            "merchant_type": "Educational/Charity"
        }
    """
    try:
        data = request.json

        if not data:
            return jsonify({"error": "Missing request body"}), 400

        result = direct_debit_service.save_mapping(
            payee_pattern=data.get("payee_pattern"),
            normalized_name=data.get("normalized_name"),
            category=data.get("category"),
            subcategory=data.get("subcategory"),
            merchant_type=data.get("merchant_type"),
        )

        return jsonify(result), 201

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"❌ Save direct debit mapping error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@direct_debit_bp.route("/mappings/<int:mapping_id>", methods=["DELETE"])
def delete_mapping(mapping_id):
    """
    Delete a direct debit mapping.

    Path params:
        mapping_id (int): Mapping ID to delete

    Returns:
        Success message
    """
    try:
        result = direct_debit_service.delete_mapping(mapping_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Delete direct debit mapping error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@direct_debit_bp.route("/apply-mappings", methods=["POST"])
def apply_mappings():
    """
    Apply all direct debit mappings to transactions.

    Re-enriches all direct debit transactions using the configured mappings.
    Invalidates transaction cache after application.

    Returns:
        Dict with updated_count and transactions list
    """
    try:
        result = direct_debit_service.apply_mappings()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Apply direct debit mappings error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@direct_debit_bp.route("/new", methods=["GET"])
def get_new():
    """
    Get newly detected direct debit payees that haven't been mapped.

    Returns list of unmapped payees with transaction counts and mandate numbers.

    Returns:
        Dict with new payees list
    """
    try:
        result = direct_debit_service.get_new_payees()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Detect new direct debits error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
