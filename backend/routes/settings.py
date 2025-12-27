"""
Settings Routes - Flask Blueprint

Handles user settings management endpoints:
- Account mappings: Friendly names for bank accounts
- Account discovery: Automatic detection of unmapped accounts

Account Mapping Context:
UK transactions often include cryptic account numbers in descriptions.
Users can map these to friendly names (e.g., "20-12-34 12345678" → "Savings Account").

Routes are thin controllers that delegate to settings_service for business logic.
"""

import traceback

from flask import Blueprint, jsonify, request

from services import settings_service

settings_bp = Blueprint("settings", __name__, url_prefix="/api/settings")


# ============================================================================
# Account Mappings
# ============================================================================


@settings_bp.route("/account-mappings", methods=["GET"])
def get_mappings():
    """
    Get all account mappings.

    Returns:
        List of account mapping dicts with sort_code, account_number, friendly_name
    """
    try:
        mappings = settings_service.get_account_mappings()
        return jsonify(mappings)

    except Exception as e:
        print(f"❌ Get account mappings error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/account-mappings", methods=["POST"])
def create_mapping():
    """
    Create a new account mapping.

    Request body:
        sort_code (str): 6-digit sort code (can include hyphens/spaces) - required
        account_number (str): 8-digit account number (can include spaces) - required
        friendly_name (str): Human-readable account name - required

    Returns:
        Success dict with mapping id

    Example:
        {
            "sort_code": "20-12-34",
            "account_number": "12345678",
            "friendly_name": "Savings Account"
        }
    """
    try:
        data = request.json

        result = settings_service.create_account_mapping(
            sort_code=data.get("sort_code"),
            account_number=data.get("account_number"),
            friendly_name=data.get("friendly_name"),
        )

        return jsonify(result), 201

    except ValueError as e:
        # Validation error or duplicate
        status = 409 if "already exists" in str(e) else 400
        return jsonify({"error": str(e)}), status
    except Exception as e:
        print(f"❌ Create account mapping error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/account-mappings/<int:mapping_id>", methods=["PUT"])
def update_mapping(mapping_id):
    """
    Update an existing account mapping.

    Path params:
        mapping_id (int): Mapping ID to update

    Request body:
        friendly_name (str): New friendly name - required

    Returns:
        Success dict
    """
    try:
        data = request.json

        result = settings_service.update_account_mapping(
            mapping_id=mapping_id, friendly_name=data.get("friendly_name")
        )

        return jsonify(result)

    except ValueError as e:
        status = 404 if "not found" in str(e).lower() else 400
        return jsonify({"error": str(e)}), status
    except Exception as e:
        print(f"❌ Update account mapping error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@settings_bp.route("/account-mappings/<int:mapping_id>", methods=["DELETE"])
def delete_mapping(mapping_id):
    """
    Delete an account mapping.

    Path params:
        mapping_id (int): Mapping ID to delete

    Returns:
        Success dict
    """
    try:
        result = settings_service.delete_account_mapping(mapping_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Delete account mapping error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Account Discovery
# ============================================================================


@settings_bp.route("/account-mappings/discover", methods=["GET"])
def discover():
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
    try:
        result = settings_service.discover_account_mappings()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Discover account mappings error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
