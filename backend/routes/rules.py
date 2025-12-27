"""
Rules Routes - Flask Blueprint

Handles all rule management endpoints:
- Category rules: Pattern-based transaction categorization
- Merchant rules: Merchant name normalization
- Pattern testing and validation
- Bulk operations and statistics

Routes are thin controllers that delegate to rules_service for business logic.
"""

from flask import Blueprint, request, jsonify
from services import rules_service
import traceback

rules_bp = Blueprint('rules', __name__, url_prefix='/api/rules')


# ============================================================================
# Category Rules
# ============================================================================

@rules_bp.route('/category', methods=['GET'])
def get_category_rules():
    """
    Get all category rules with optional filtering.

    Query params:
        active_only (bool): Filter to active rules only (default: true)
        category (str): Filter by category
        source (str): Filter by source ('manual', 'learned', 'llm')

    Returns:
        List of category rules
    """
    try:
        active_only = request.args.get('active_only', 'true').lower() == 'true'
        category = request.args.get('category')
        source = request.args.get('source')

        rules = rules_service.get_category_rules(
            active_only=active_only,
            category=category,
            source=source
        )

        return jsonify(rules)

    except Exception as e:
        print(f"❌ Get category rules error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/category', methods=['POST'])
def create_category_rule():
    """
    Create a new category rule.

    Request body:
        rule_name (str): Human-readable name - required
        description_pattern (str): Pattern to match - required
        category (str): Target category - required
        pattern_type (str): 'contains', 'starts_with', 'exact', 'regex' (default: contains)
        transaction_type (str): 'CREDIT', 'DEBIT', or null for all
        subcategory (str): Optional subcategory
        priority (int): Integer priority (default: 0)
        source (str): Rule source (default: 'manual')

    Returns:
        Created rule details with ID
    """
    try:
        data = request.json

        result = rules_service.create_category_rule(
            rule_name=data.get('rule_name'),
            description_pattern=data.get('description_pattern', ''),
            category=data.get('category'),
            pattern_type=data.get('pattern_type'),
            transaction_type=data.get('transaction_type'),
            subcategory=data.get('subcategory'),
            priority=data.get('priority', 0),
            source=data.get('source', 'manual')
        )

        return jsonify(result), 201

    except ValueError as e:
        # Pattern validation error
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Create category rule error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/category/<int:rule_id>', methods=['PUT'])
def update_category_rule(rule_id):
    """
    Update an existing category rule.

    Path params:
        rule_id (int): Rule ID to update

    Request body:
        Any fields to update (rule_name, description_pattern, category, etc.)

    Returns:
        Success message or 404 if not found
    """
    try:
        data = request.json
        success = rules_service.update_category_rule(rule_id, **data)

        if success:
            return jsonify({'success': True, 'message': f"Updated rule {rule_id}"})
        else:
            return jsonify({'error': 'Rule not found'}), 404

    except ValueError as e:
        # Pattern validation error
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Update category rule error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/category/<int:rule_id>', methods=['DELETE'])
def delete_category_rule(rule_id):
    """
    Delete a category rule.

    Path params:
        rule_id (int): Rule ID to delete

    Returns:
        Success message or 404 if not found
    """
    try:
        success = rules_service.delete_category_rule(rule_id)

        if success:
            return jsonify({'success': True, 'message': f"Deleted rule {rule_id}"})
        else:
            return jsonify({'error': 'Rule not found'}), 404

    except Exception as e:
        print(f"❌ Delete category rule error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/category/<int:rule_id>/test', methods=['POST'])
def test_category_rule(rule_id):
    """
    Test an existing category rule against all transactions.

    Path params:
        rule_id (int): Rule ID to test

    Query params:
        limit (int): Max transactions to return (default: 10)

    Returns:
        Test results with matching transactions
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        result = rules_service.test_category_rule(rule_id, limit=limit)

        return jsonify(result)

    except ValueError as e:
        # Rule not found
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Test category rule error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/category/test-pattern', methods=['POST'])
def test_pattern():
    """
    Test a pattern against transactions before creating a rule.

    Request body:
        pattern (str): The pattern to test
        pattern_type (str): 'contains', 'starts_with', 'exact', 'regex' (optional - auto-detect from prefix)
        limit (int): Max transactions to return (default: 10)

    Returns:
        Test results with matching transactions
    """
    try:
        data = request.json
        pattern = data.get('pattern', '')
        pattern_type = data.get('pattern_type')
        limit = data.get('limit', 10)

        result = rules_service.test_pattern(
            pattern=pattern,
            pattern_type=pattern_type,
            limit=limit
        )

        return jsonify(result)

    except ValueError as e:
        # Pattern validation error
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Test category pattern error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Merchant Normalization Rules
# ============================================================================

@rules_bp.route('/merchant', methods=['GET'])
def get_merchant_rules():
    """
    Get all merchant normalizations with optional filtering.

    Query params:
        source (str): Filter by source ('manual', 'learned', 'llm', 'direct_debit')
        category (str): Filter by default_category

    Returns:
        List of merchant normalization rules
    """
    try:
        source = request.args.get('source')
        category = request.args.get('category')

        normalizations = rules_service.get_merchant_rules(
            source=source,
            category=category
        )

        return jsonify(normalizations)

    except Exception as e:
        print(f"❌ Get merchant normalizations error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/merchant', methods=['POST'])
def create_merchant_rule():
    """
    Create a new merchant normalization.

    Request body:
        pattern (str): Pattern to match - required
        normalized_name (str): Clean merchant name - required
        pattern_type (str): 'contains', 'starts_with', 'exact', 'regex' (default: contains)
        merchant_type (str): Business type (optional)
        default_category (str): Category to assign (optional)
        priority (int): Integer priority (default: 0)
        source (str): Rule source (default: 'manual')

    Returns:
        Created normalization details with ID
    """
    try:
        data = request.json

        result = rules_service.create_merchant_rule(
            pattern=data.get('pattern', ''),
            normalized_name=data.get('normalized_name'),
            pattern_type=data.get('pattern_type'),
            merchant_type=data.get('merchant_type'),
            default_category=data.get('default_category'),
            priority=data.get('priority', 0),
            source=data.get('source', 'manual')
        )

        return jsonify(result), 201

    except ValueError as e:
        # Pattern validation error
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Create merchant normalization error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/merchant/<int:norm_id>', methods=['PUT'])
def update_merchant_rule(norm_id):
    """
    Update an existing merchant normalization.

    Path params:
        norm_id (int): Normalization ID to update

    Request body:
        Any fields to update (pattern, normalized_name, etc.)

    Returns:
        Success message or 404 if not found
    """
    try:
        data = request.json
        success = rules_service.update_merchant_rule(norm_id, **data)

        if success:
            return jsonify({'success': True, 'message': f"Updated normalization {norm_id}"})
        else:
            return jsonify({'error': 'Normalization not found'}), 404

    except ValueError as e:
        # Pattern validation error
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Update merchant normalization error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/merchant/<int:norm_id>', methods=['DELETE'])
def delete_merchant_rule(norm_id):
    """
    Delete a merchant normalization.

    Path params:
        norm_id (int): Normalization ID to delete

    Returns:
        Success message or 404 if not found
    """
    try:
        success = rules_service.delete_merchant_rule(norm_id)

        if success:
            return jsonify({'success': True, 'message': f"Deleted normalization {norm_id}"})
        else:
            return jsonify({'error': 'Normalization not found'}), 404

    except Exception as e:
        print(f"❌ Delete merchant normalization error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/merchant/<int:norm_id>/test', methods=['POST'])
def test_merchant_rule(norm_id):
    """
    Test an existing merchant normalization against all transactions.

    Path params:
        norm_id (int): Normalization ID to test

    Query params:
        limit (int): Max transactions to return (default: 10)

    Returns:
        Test results with matching transactions
    """
    try:
        limit = request.args.get('limit', 10, type=int)
        result = rules_service.test_merchant_rule(norm_id, limit=limit)

        return jsonify(result)

    except ValueError as e:
        # Normalization not found
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Test merchant normalization error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Bulk Operations
# ============================================================================

@rules_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """
    Get comprehensive rule usage statistics and coverage metrics.

    Returns:
        Statistics with rule counts and coverage
    """
    try:
        stats = rules_service.get_statistics()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Get rules statistics error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/test-all', methods=['POST'])
def test_all():
    """
    Evaluate all rules against all transactions.

    Returns detailed coverage report with category breakdown,
    unused rules, and potential conflicts.

    Returns:
        Test results with coverage analysis
    """
    try:
        result = rules_service.test_all_rules()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Test all rules error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@rules_bp.route('/apply-all', methods=['POST'])
def apply_all():
    """
    Re-apply all rules to all transactions.

    This re-enriches all transactions using the current rules,
    updating any transactions that match.

    Returns:
        Application results with update counts
    """
    try:
        result = rules_service.apply_all_rules()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Apply all rules error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
