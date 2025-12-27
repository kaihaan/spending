"""
Categories Routes - Flask Blueprints

Handles all category management endpoints with two API versions:

v1 API (Legacy):
- Category promotion from subcategories
- Category hiding and unhiding
- Spending summaries by category

v2 API (Normalized):
- Full CRUD for categories and subcategories
- Foreign key relationships
- Cascade updates for name changes

Routes are thin controllers that delegate to categories_service for business logic.
"""

from flask import Blueprint, request, jsonify
from services import categories_service
import traceback

# v1 Legacy API
categories_v1_bp = Blueprint('categories_v1', __name__, url_prefix='/api/categories')

# v2 Normalized API
categories_v2_bp = Blueprint('categories_v2', __name__, url_prefix='/api/v2/categories')
subcategories_v2_bp = Blueprint('subcategories_v2', __name__, url_prefix='/api/v2/subcategories')


# ============================================================================
# v1 Legacy Category API
# ============================================================================

@categories_v1_bp.route('', methods=['GET'])
def get_categories():
    """
    Get all categories (legacy v1 API).

    Returns:
        List of category dicts
    """
    try:
        categories = categories_service.get_all_categories()
        return jsonify(categories)

    except Exception as e:
        print(f"❌ Get categories error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v1_bp.route('/summary', methods=['GET'])
def get_spending_summary():
    """
    Get all categories with spending totals.

    Query params:
        date_from (str): Optional start date filter (YYYY-MM-DD)
        date_to (str): Optional end date filter (YYYY-MM-DD)

    Returns:
        Dict with categories and hidden_categories lists
    """
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        result = categories_service.get_category_spending_summary(date_from, date_to)
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get category spending summary error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v1_bp.route('/<path:category_name>/subcategories', methods=['GET'])
def get_subcategories(category_name):
    """
    Get subcategories for a specific category with spending totals.

    Path params:
        category_name (str): Category name (URL-decoded)

    Query params:
        date_from (str): Optional start date filter
        date_to (str): Optional end date filter

    Returns:
        Dict with category name and subcategories list
    """
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        result = categories_service.get_subcategory_spending(category_name, date_from, date_to)
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get category subcategories error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v1_bp.route('/promote', methods=['POST'])
def promote():
    """
    Create a promoted category from selected subcategories.

    Request body:
        new_category_name (str): Name for the new promoted category - required
        subcategories (list): List of subcategory patterns to promote - required

    Returns:
        Success dict with category_id and transactions_updated count
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        new_category_name = data.get('new_category_name')
        subcategories = data.get('subcategories', [])

        result = categories_service.promote_category(new_category_name, subcategories)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Promote category error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v1_bp.route('/hide', methods=['POST'])
def hide():
    """
    Hide a category and reset its transactions for re-enrichment.

    Request body:
        category_name (str): Category name to hide - required

    Returns:
        Success dict with category_id and transactions_reset count
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        category_name = data.get('category_name')
        result = categories_service.hide_category(category_name)

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Hide category error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v1_bp.route('/unhide', methods=['POST'])
def unhide():
    """
    Restore a hidden category.

    Request body:
        category_name (str): Category name to restore - required

    Returns:
        Success message
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        category_name = data.get('category_name')
        result = categories_service.unhide_category(category_name)

        return jsonify(result)

    except ValueError as e:
        return jsonify({'success': False, 'message': str(e)}), 404
    except Exception as e:
        print(f"❌ Unhide category error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v1_bp.route('/custom', methods=['GET'])
def get_custom():
    """
    Get all custom categories (promoted and hidden).

    Query params:
        type (str): Optional filter - 'promoted', 'hidden', or None for all

    Returns:
        Dict with categories list
    """
    try:
        category_type = request.args.get('type')
        result = categories_service.get_custom_categories(category_type=category_type)

        return jsonify(result)

    except Exception as e:
        print(f"❌ Get custom categories error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# v2 Normalized Categories API
# ============================================================================

@categories_v2_bp.route('', methods=['GET'])
def get_normalized():
    """
    Get all normalized categories with optional counts.

    Query params:
        active_only (bool): Filter to active categories only (default: false)
        include_counts (bool): Include transaction/subcategory counts (default: true)

    Returns:
        Dict with categories list
    """
    try:
        active_only = request.args.get('active_only', 'false').lower() == 'true'
        include_counts = request.args.get('include_counts', 'true').lower() == 'true'

        result = categories_service.get_normalized_categories(
            active_only=active_only,
            include_counts=include_counts
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Get normalized categories error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v2_bp.route('/<int:category_id>', methods=['GET'])
def get_normalized_single(category_id):
    """
    Get a single normalized category with subcategories.

    Path params:
        category_id (int): Category ID

    Returns:
        Dict with category data
    """
    try:
        result = categories_service.get_normalized_category(category_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Get normalized category error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v2_bp.route('', methods=['POST'])
def create_normalized():
    """
    Create a new normalized category.

    Request body:
        name (str): Category name - required
        description (str): Optional description
        is_essential (bool): Whether category is essential (default: false)
        color (str): Optional color hex code

    Returns:
        Dict with created category
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        result = categories_service.create_normalized_category(
            name=data.get('name'),
            description=data.get('description'),
            is_essential=data.get('is_essential', False),
            color=data.get('color')
        )

        return jsonify(result), 201

    except ValueError as e:
        # Name missing or duplicate
        status = 400 if 'required' in str(e) else 409
        return jsonify({'error': str(e)}), status
    except Exception as e:
        print(f"❌ Create normalized category error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v2_bp.route('/<int:category_id>', methods=['PUT'])
def update_normalized(category_id):
    """
    Update a normalized category. Cascades name changes to all transactions.

    Path params:
        category_id (int): Category ID to update

    Request body:
        name (str): New name (optional)
        description (str): New description (optional)
        is_active (bool): Active status (optional)
        is_essential (bool): Essential status (optional)
        color (str): Color hex code (optional)

    Returns:
        Dict with updated category and cascade counts
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = categories_service.update_normalized_category(
            category_id=category_id,
            name=data.get('name'),
            description=data.get('description'),
            is_active=data.get('is_active'),
            is_essential=data.get('is_essential'),
            color=data.get('color')
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Update normalized category error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v2_bp.route('/<int:category_id>', methods=['DELETE'])
def delete_normalized(category_id):
    """
    Delete a normalized category. System categories cannot be deleted.

    Path params:
        category_id (int): Category ID to delete

    Query params:
        reassign_to (int): Optional category ID to reassign transactions to

    Returns:
        Dict with deletion results
    """
    try:
        reassign_to = request.args.get('reassign_to', type=int)

        result = categories_service.delete_normalized_category(
            category_id=category_id,
            reassign_to_category_id=reassign_to
        )

        return jsonify(result)

    except ValueError as e:
        # Not found or system category error
        status = 404 if 'not found' in str(e).lower() else 400
        return jsonify({'error': str(e)}), status
    except Exception as e:
        print(f"❌ Delete normalized category error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@categories_v2_bp.route('/<int:category_id>/subcategories', methods=['POST'])
def create_subcategory(category_id):
    """
    Create a new normalized subcategory under a category.

    Path params:
        category_id (int): Parent category ID

    Request body:
        name (str): Subcategory name - required
        description (str): Optional description

    Returns:
        Dict with created subcategory
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Request body required'}), 400

        result = categories_service.create_normalized_subcategory(
            category_id=category_id,
            name=data.get('name'),
            description=data.get('description')
        )

        return jsonify(result), 201

    except ValueError as e:
        # Name missing, category not found, or duplicate
        if 'not found' in str(e).lower():
            status = 404
        elif 'required' in str(e).lower():
            status = 400
        else:
            status = 409
        return jsonify({'error': str(e)}), status
    except Exception as e:
        print(f"❌ Create normalized subcategory error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# v2 Normalized Subcategories API
# ============================================================================

@subcategories_v2_bp.route('', methods=['GET'])
def get_normalized():
    """
    Get all normalized subcategories, optionally filtered by category.

    Query params:
        category_id (int): Optional category ID filter
        include_counts (bool): Include transaction counts (default: true)

    Returns:
        Dict with subcategories list
    """
    try:
        category_id = request.args.get('category_id', type=int)
        include_counts = request.args.get('include_counts', 'true').lower() == 'true'

        result = categories_service.get_normalized_subcategories(
            category_id=category_id,
            include_counts=include_counts
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Get normalized subcategories error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@subcategories_v2_bp.route('/<int:subcategory_id>', methods=['GET'])
def get_normalized_single(subcategory_id):
    """
    Get a single normalized subcategory.

    Path params:
        subcategory_id (int): Subcategory ID

    Returns:
        Dict with subcategory data
    """
    try:
        result = categories_service.get_normalized_subcategory(subcategory_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Get normalized subcategory error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@subcategories_v2_bp.route('/<int:subcategory_id>', methods=['PUT'])
def update_normalized(subcategory_id):
    """
    Update a normalized subcategory. Cascades name changes to transactions.

    Path params:
        subcategory_id (int): Subcategory ID to update

    Request body:
        name (str): New name (optional)
        description (str): New description (optional)
        is_active (bool): Active status (optional)
        category_id (int): New parent category ID for moving (optional)

    Returns:
        Dict with updated subcategory and cascade counts
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'No data provided'}), 400

        result = categories_service.update_normalized_subcategory(
            subcategory_id=subcategory_id,
            name=data.get('name'),
            description=data.get('description'),
            is_active=data.get('is_active'),
            category_id=data.get('category_id')
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Update normalized subcategory error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@subcategories_v2_bp.route('/<int:subcategory_id>', methods=['DELETE'])
def delete_normalized(subcategory_id):
    """
    Delete a normalized subcategory.

    Path params:
        subcategory_id (int): Subcategory ID to delete

    Returns:
        Dict with deletion results
    """
    try:
        result = categories_service.delete_normalized_subcategory(subcategory_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Delete normalized subcategory error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
