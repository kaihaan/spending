"""
Amazon Routes - Flask Blueprint

Handles all Amazon integration endpoints:
- Regular Amazon orders (CSV import from consumer account)
- Amazon returns/refunds (CSV import)
- Amazon Business API (SP-API for seller accounts)

Routes are thin controllers that delegate to amazon_service for business logic.
"""

from flask import Blueprint, request, jsonify, redirect
from services import amazon_service
import traceback

amazon_bp = Blueprint('amazon', __name__, url_prefix='/api/amazon')


# ============================================================================
# Regular Amazon Orders (CSV Import)
# ============================================================================

@amazon_bp.route('/import', methods=['POST'])
def import_orders():
    """
    Import Amazon order history from CSV file or content.

    Request body:
        csv_content (str): CSV file content (preferred)
        filename (str): Legacy path to CSV file
        website (str): Amazon website (default: Amazon.co.uk)

    Returns:
        Import result with counts and matching results
    """
    try:
        data = request.json
        website = data.get('website', 'Amazon.co.uk')
        csv_content = data.get('csv_content')
        filename = data.get('filename')

        result = amazon_service.import_orders(
            csv_content=csv_content,
            filename=filename,
            website=website
        )

        return jsonify(result), 201

    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Amazon import error: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@amazon_bp.route('/orders', methods=['GET'])
def get_orders():
    """
    Get all Amazon orders with optional filters.

    Query params:
        date_from (str): Start date (YYYY-MM-DD)
        date_to (str): End date (YYYY-MM-DD)
        website (str): Amazon website filter

    Returns:
        Orders list with count
    """
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')
        website = request.args.get('website')

        result = amazon_service.get_orders(
            date_from=date_from,
            date_to=date_to,
            website=website
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Get Amazon orders error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """
    Get Amazon import and matching statistics (cached).

    Returns:
        Statistics summary (15 minute cache)
    """
    try:
        stats = amazon_service.get_statistics()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Amazon statistics error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/match', methods=['POST'])
def run_matching():
    """
    Run or re-run Amazon matching on existing transactions.

    Query params:
        async (str): If 'true', runs as async Celery task (default: true)
        user_id (int): User ID (default: 1)

    Returns:
        Job details if async, or match results if sync
    """
    try:
        async_mode = request.args.get('async', 'true').lower() == 'true'
        user_id = int(request.args.get('user_id', 1))

        result = amazon_service.run_matching(
            async_mode=async_mode,
            user_id=user_id
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Amazon matching error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/match/<int:transaction_id>', methods=['POST'])
def rematch_single_transaction(transaction_id):
    """
    Re-match a specific transaction with Amazon orders.

    Path params:
        transaction_id (int): Transaction ID to rematch

    Returns:
        Match result or 404 if no match found
    """
    try:
        result = amazon_service.rematch_single(transaction_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Amazon rematch error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/coverage', methods=['GET'])
def check_coverage():
    """
    Check if Amazon order data exists for a date range.

    Query params:
        date_from (str): Start date (YYYY-MM-DD) - required
        date_to (str): End date (YYYY-MM-DD) - required

    Returns:
        Coverage status dict
    """
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        if not date_from or not date_to:
            return jsonify({'error': 'Missing date_from or date_to parameters'}), 400

        coverage = amazon_service.check_coverage(date_from, date_to)
        return jsonify(coverage)

    except Exception as e:
        print(f"❌ Amazon coverage check error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/unmatched', methods=['GET'])
def get_unmatched():
    """
    Get all Amazon transactions that haven't been matched to orders.

    Returns:
        Unmatched transactions list with count
    """
    try:
        result = amazon_service.get_unmatched_transactions()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get unmatched Amazon transactions error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/orders', methods=['DELETE'])
def clear_orders():
    """
    Clear all Amazon orders and matches (for testing/reimporting).

    Returns:
        Deletion counts
    """
    try:
        result = amazon_service.clear_orders()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Clear Amazon orders error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/files', methods=['GET'])
def list_files():
    """
    List available Amazon CSV files in the sample folder.

    Returns:
        File list with count
    """
    try:
        result = amazon_service.list_csv_files()
        return jsonify(result)

    except Exception as e:
        print(f"❌ List Amazon files error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/upload', methods=['POST'])
def upload_file():
    """
    Upload an Amazon CSV file.

    Form data:
        file: CSV file upload

    Returns:
        Upload result with filename
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        result = amazon_service.upload_csv_file(file)

        return jsonify(result), 201

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Amazon upload error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Amazon Returns Endpoints
# ============================================================================

@amazon_bp.route('/returns/import', methods=['POST'])
def import_returns():
    """
    Import Amazon returns/refunds from CSV file or content.

    Request body:
        csv_content (str): CSV file content (preferred)
        filename (str): Legacy path to CSV file

    Returns:
        Import result with counts and matching results
    """
    try:
        data = request.json
        csv_content = data.get('csv_content')
        filename = data.get('filename')

        result = amazon_service.import_returns(
            csv_content=csv_content,
            filename=filename
        )

        return jsonify(result), 201

    except FileNotFoundError as e:
        return jsonify({'error': str(e)}), 404
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"❌ Amazon returns import error: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@amazon_bp.route('/returns', methods=['GET'])
def get_returns():
    """
    Get all Amazon returns.

    Returns:
        Returns list with count
    """
    try:
        result = amazon_service.get_returns()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get Amazon returns error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/returns/statistics', methods=['GET'])
def get_returns_statistics():
    """
    Get Amazon returns statistics (cached).

    Returns:
        Statistics summary (15 minute cache)
    """
    try:
        stats = amazon_service.get_returns_statistics()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Amazon returns statistics error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/returns/match', methods=['POST'])
def run_returns_matching():
    """
    Run or re-run returns matching.

    Query params:
        async (str): If 'true', runs as async Celery task (default: true)
        user_id (int): User ID (default: 1)

    Returns:
        Job details if async, or match results if sync
    """
    try:
        async_mode = request.args.get('async', 'true').lower() == 'true'
        user_id = int(request.args.get('user_id', 1))

        result = amazon_service.run_returns_matching(
            async_mode=async_mode,
            user_id=user_id
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Amazon returns matching error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/returns', methods=['DELETE'])
def clear_returns():
    """
    Clear all Amazon returns (for testing/reimporting).

    Returns:
        Deletion count
    """
    try:
        result = amazon_service.clear_returns()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Clear Amazon returns error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_bp.route('/returns/files', methods=['GET'])
def list_returns_files():
    """
    List available Amazon returns CSV files in the sample folder.

    Returns:
        File list with count
    """
    try:
        result = amazon_service.list_returns_files()
        return jsonify(result)

    except Exception as e:
        print(f"❌ List returns files error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# Amazon Business (SP-API) - Separate blueprint registered at /api/amazon-business
# ============================================================================
# Note: Amazon Business routes are in a separate blueprint to maintain
# distinct URL namespace (/api/amazon-business vs /api/amazon)

amazon_business_bp = Blueprint('amazon_business', __name__, url_prefix='/api/amazon-business')


@amazon_business_bp.route('/authorize', methods=['GET'])
def authorize():
    """
    Start Amazon Business API OAuth flow.

    Returns:
        Authorization URL and state token
    """
    try:
        result = amazon_service.get_authorization_url()
        return jsonify(result)

    except ValueError as e:
        # Missing credentials
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Amazon Business API credentials not configured'
        }), 400
    except Exception as e:
        print(f"❌ Amazon Business authorize error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@amazon_business_bp.route('/callback', methods=['POST'])
def callback():
    """
    Handle Amazon Business API OAuth callback.

    Request body:
        code (str): Authorization code - required
        region (str): Amazon region (default: UK)

    Returns:
        Connection details
    """
    try:
        data = request.json
        code = data.get('code')

        if not code:
            return jsonify({'success': False, 'error': 'Authorization code required'}), 400

        region = data.get('region', 'UK')

        result = amazon_service.handle_oauth_callback(code, region)
        return jsonify(result)

    except Exception as e:
        print(f"❌ Amazon Business callback error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@amazon_business_bp.route('/connection', methods=['GET'])
def get_connection():
    """
    Get Amazon Business connection status.

    Returns:
        Connection details or not connected status
    """
    try:
        status = amazon_service.get_connection_status()
        return jsonify(status)

    except Exception as e:
        print(f"❌ Amazon Business connection status error: {e}")
        traceback.print_exc()
        return jsonify({'connected': False, 'error': str(e)}), 500


@amazon_business_bp.route('/disconnect', methods=['POST'])
def disconnect():
    """
    Disconnect Amazon Business account.

    Returns:
        Success message
    """
    try:
        result = amazon_service.disconnect()
        return jsonify(result)

    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Amazon Business disconnect error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@amazon_business_bp.route('/import', methods=['POST'])
def import_orders():
    """
    Import buyer purchase orders from Amazon Business Reporting API.

    Request body:
        start_date (str): YYYY-MM-DD format - required
        end_date (str): YYYY-MM-DD format - required
        run_matching (bool): Run matching after import (default: true)

    Returns:
        Import and matching results
    """
    try:
        data = request.json
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        run_matching = data.get('run_matching', True)

        if not start_date or not end_date:
            return jsonify({
                'success': False,
                'error': 'start_date and end_date required'
            }), 400

        result = amazon_service.import_business_orders(
            start_date=start_date,
            end_date=end_date,
            run_matching=run_matching
        )

        return jsonify(result)

    except ValueError as e:
        # No connection found
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Please connect Amazon Business API first'
        }), 400
    except Exception as e:
        print(f"❌ Amazon Business import error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@amazon_business_bp.route('/statistics', methods=['GET'])
def get_statistics():
    """
    Get Amazon Business import and matching statistics.

    Returns:
        Statistics summary
    """
    try:
        stats = amazon_service.get_business_statistics()
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Amazon Business statistics error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_business_bp.route('/orders', methods=['GET'])
def get_orders():
    """
    Get Amazon Business orders with optional date filtering.

    Query params:
        date_from (str): Start date (YYYY-MM-DD)
        date_to (str): End date (YYYY-MM-DD)

    Returns:
        Orders list
    """
    try:
        date_from = request.args.get('date_from')
        date_to = request.args.get('date_to')

        orders = amazon_service.get_business_orders(
            date_from=date_from,
            date_to=date_to
        )

        return jsonify(orders)

    except Exception as e:
        print(f"❌ Amazon Business orders error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@amazon_business_bp.route('/match', methods=['POST'])
def run_matching():
    """
    Run matching for Amazon Business transactions.

    Returns:
        Matching results
    """
    try:
        result = amazon_service.run_business_matching()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Amazon Business matching error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@amazon_business_bp.route('/clear', methods=['POST'])
def clear_data():
    """
    Clear all Amazon Business data (for testing/reset).

    Returns:
        Deletion counts by table
    """
    try:
        result = amazon_service.clear_business_data()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Amazon Business clear error: {e}")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500
