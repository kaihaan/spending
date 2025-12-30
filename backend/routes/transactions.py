"""
Transactions Routes - Flask Blueprint

Handles all transaction-related endpoints:
- Transaction retrieval with enrichment data
- Enrichment toggle and Huququllah classification
- Enrichment source management

Routes are thin controllers that delegate to transactions_service for business logic.

SECURITY: All routes filter data by current_user to ensure data isolation.
"""

import traceback

from flask import Blueprint, jsonify, request
from flask_login import current_user

from services import transactions_service

transactions_bp = Blueprint("transactions", __name__, url_prefix="/api/transactions")


# ============================================================================
# Transaction Retrieval
# ============================================================================


@transactions_bp.route("", methods=["GET"])
def get_transactions():
    """
    Get all TrueLayer transactions with enrichment data for the current user.

    Uses optimized single-query approach with Redis caching (15 minute TTL).
    Filters by current_user.id to ensure data isolation.

    Returns:
        List of normalized transactions with enrichment and sources
    """
    try:
        transactions = transactions_service.get_all_transactions(
            user_id=current_user.id
        )
        return jsonify(transactions)

    except Exception as e:
        print(f"❌ Get transactions error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@transactions_bp.route("/with-matches", methods=["GET"])
def get_transactions_with_matches():
    """
    Get paginated transactions with match status for each data source.

    Used by the Matches tab to display bank transactions with match badges.

    Query params:
        page (int): Page number (default: 1)
        page_size (int): Items per page (default: 50)

    Returns:
        Dict with items, total, page, page_size, total_pages
    """
    try:
        page = request.args.get("page", 1, type=int)
        page_size = request.args.get("page_size", 50, type=int)

        # Clamp page_size to reasonable limits
        page_size = max(1, min(100, page_size))

        result = transactions_service.get_transactions_with_matches(
            user_id=current_user.id,
            page=page,
            page_size=page_size,
        )
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get transactions with matches error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Transaction Updates
# ============================================================================


@transactions_bp.route("/<int:transaction_id>/toggle-required", methods=["POST"])
def toggle_required(transaction_id):
    """
    Toggle enrichment_required flag for a transaction.

    Path params:
        transaction_id (int): Transaction ID to toggle

    Returns:
        Updated transaction dict with new state
    """
    try:
        result = transactions_service.toggle_enrichment_required(transaction_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Toggle enrichment required error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@transactions_bp.route("/<int:transaction_id>/huququllah", methods=["PUT"])
def update_huququllah(transaction_id):
    """
    Update the Huququllah classification for a transaction.

    Path params:
        transaction_id (int): Transaction ID to update

    Request body:
        classification (str): 'essential', 'discretionary', or null

    Returns:
        Success dict with transaction_id and classification
    """
    try:
        data = request.json
        classification = data.get("classification")

        result = transactions_service.update_huququllah_classification(
            transaction_id, classification
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"❌ Update Huququllah classification error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Enrichment Sources
# ============================================================================


@transactions_bp.route("/<int:txn_id>/enrichment-sources", methods=["GET"])
def get_enrichment_sources(txn_id):
    """
    Get all enrichment sources for a transaction.

    Path params:
        txn_id (int): Transaction ID

    Returns:
        Dict with sources list and transaction_id
    """
    try:
        result = transactions_service.get_enrichment_sources(txn_id)
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get enrichment sources error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@transactions_bp.route("/<int:txn_id>/enrichment-sources/primary", methods=["POST"])
def set_primary_source(txn_id):
    """
    Set the primary enrichment source for a transaction.

    Path params:
        txn_id (int): Transaction ID

    Request body:
        source_type (str): Source type (e.g., 'amazon', 'apple', 'gmail') - required
        source_id (int): Optional source ID

    Returns:
        Success dict with transaction_id and primary_source
    """
    try:
        data = request.json
        source_type = data.get("source_type")
        source_id = data.get("source_id")

        result = transactions_service.set_primary_enrichment_source(
            txn_id, source_type, source_id
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"❌ Set primary enrichment source error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
