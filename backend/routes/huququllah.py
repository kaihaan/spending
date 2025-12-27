"""
Huququllah Routes - Flask Blueprint

Handles Huququllah (Islamic wealth obligation) endpoints:
- Smart classification suggestions
- Summary calculations (19% of discretionary spending)
- Unclassified transaction tracking

Huququllah Context:
Members of the Baha'i Faith are required to pay 19% of their discretionary
income after essential expenses (Huququllah means "Right of God").

Routes are thin controllers that delegate to huququllah_service for business logic.
"""

from flask import Blueprint, request, jsonify
from services import huququllah_service
import traceback

huququllah_bp = Blueprint('huququllah', __name__, url_prefix='/api/huququllah')


# ============================================================================
# Huququllah Operations
# ============================================================================

@huququllah_bp.route('/suggest/<int:transaction_id>', methods=['GET'])
def get_suggestion(transaction_id):
    """
    Get a smart suggestion for classifying a transaction.

    Uses pattern matching and historical data to suggest whether
    a transaction should be classified as essential or discretionary.

    Path params:
        transaction_id (int): Transaction ID to classify

    Returns:
        Suggestion dict with classification and confidence
    """
    try:
        suggestion = huququllah_service.get_suggestion(transaction_id)
        return jsonify(suggestion)

    except Exception as e:
        print(f"❌ Huququllah suggestion error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@huququllah_bp.route('/summary', methods=['GET'])
def get_summary():
    """
    Get Huququllah summary with essential vs discretionary totals and 19% calculation.

    Query params:
        date_from (str): Optional start date filter (YYYY-MM-DD)
        date_to (str): Optional end date filter (YYYY-MM-DD)

    Returns:
        Summary dict with:
        - total_essential: Total essential spending
        - total_discretionary: Total discretionary spending
        - huququllah_due: 19% of discretionary (amount owed)
        - unclassified_count: Number of unclassified transactions
        - unclassified_amount: Total amount of unclassified transactions
    """
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        summary = huququllah_service.get_summary(date_from, date_to)
        return jsonify(summary)

    except Exception as e:
        print(f"❌ Huququllah summary error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@huququllah_bp.route('/unclassified', methods=['GET'])
def get_unclassified():
    """
    Get all transactions that haven't been classified yet.

    Returns transactions that have no manual classification and no
    LLM-based essential/discretionary classification.

    Returns:
        List of unclassified transaction dicts
    """
    try:
        transactions = huququllah_service.get_unclassified_transactions()
        return jsonify(transactions)

    except Exception as e:
        print(f"❌ Get unclassified transactions error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
