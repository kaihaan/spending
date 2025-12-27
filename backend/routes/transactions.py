"""
Transactions Routes - Flask Blueprint

Handles all transaction-related endpoints:
- Transaction retrieval with enrichment data
- Enrichment toggle and Huququllah classification
- Enrichment source management

Routes are thin controllers that delegate to transactions_service for business logic.
"""

from flask import Blueprint, request, jsonify
from services import transactions_service
import traceback

transactions_bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')


# ============================================================================
# Transaction Retrieval
# ============================================================================

@transactions_bp.route('', methods=['GET'])
def get_transactions():
    """
    Get all TrueLayer transactions with enrichment data.

    Uses optimized single-query approach with Redis caching (15 minute TTL).

    Returns:
        List of normalized transactions with enrichment and sources
    """
    try:
        transactions = transactions_service.get_all_transactions()
        return jsonify(transactions)

    except Exception as e:
        print(f"❌ Get transactions error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Transaction Updates
# ============================================================================

@transactions_bp.route('/<int:transaction_id>/toggle-required', methods=['POST'])
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
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Toggle enrichment required error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@transactions_bp.route('/<int:transaction_id>/huququllah', methods=['PUT'])
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
        classification = data.get('classification')

        result = transactions_service.update_huququllah_classification(
            transaction_id,
            classification
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Update Huququllah classification error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Enrichment Sources
# ============================================================================

@transactions_bp.route('/<int:txn_id>/enrichment-sources', methods=['GET'])
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
        return jsonify({'error': str(e)}), 500


@transactions_bp.route('/<int:txn_id>/enrichment-sources/primary', methods=['POST'])
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
        source_type = data.get('source_type')
        source_id = data.get('source_id')

        result = transactions_service.set_primary_enrichment_source(
            txn_id,
            source_type,
            source_id
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Set primary enrichment source error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
