"""
TrueLayer Routes - Flask Blueprint

Handles all TrueLayer bank integration endpoints including OAuth, account discovery,
transaction sync, and import job management. Routes are thin controllers that
delegate to truelayer_service for business logic.
"""

from flask import Blueprint, request, jsonify, redirect
from services import truelayer_service
from mcp import truelayer_auth
import traceback

truelayer_bp = Blueprint('truelayer', __name__, url_prefix='/api/truelayer')


@truelayer_bp.route('/authorize', methods=['GET'])
def authorize():
    """
    Initiate TrueLayer OAuth flow.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        Redirect to TrueLayer OAuth consent screen
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        auth_url = truelayer_auth.get_authorization_url(user_id)
        return redirect(auth_url)
    except Exception as e:
        print(f"❌ TrueLayer authorization error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/callback', methods=['GET'])
def callback():
    """
    Handle TrueLayer OAuth callback.

    Query params:
        code (str): Authorization code
        state (str): OAuth state parameter
        error (str): OAuth error if any

    Returns:
        Redirect to frontend with success/error status
    """
    try:
        return truelayer_auth.handle_oauth_callback(request.args)
    except Exception as e:
        print(f"❌ TrueLayer callback error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/connections', methods=['GET'])
def get_connections():
    """
    Get all TrueLayer connections for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of TrueLayer connection objects
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        connections = truelayer_service.get_connections(user_id)
        return jsonify(connections)

    except Exception as e:
        print(f"❌ Get TrueLayer connections error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/accounts', methods=['GET'])
def get_accounts():
    """
    Get all TrueLayer accounts for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of account objects with connection details
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        accounts = truelayer_service.get_accounts(user_id)
        return jsonify(accounts)

    except Exception as e:
        print(f"❌ Get TrueLayer accounts error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/discover-accounts', methods=['POST'])
def discover_accounts():
    """
    Discover and save new accounts from TrueLayer API.

    Request body:
        user_id (int): User ID (default: 1)

    Returns:
        Result with discovered accounts count
    """
    try:
        data = request.json or {}
        user_id = int(data.get('user_id', 1))

        result = truelayer_service.discover_accounts(user_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Discover TrueLayer accounts error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/sync', methods=['POST'])
def sync_transactions():
    """
    Trigger manual sync of TrueLayer transactions.

    Request body:
        user_id (int): User ID (optional)
        connection_id (int): Connection ID (optional)

    Returns:
        Sync result with summary statistics
    """
    try:
        data = request.json or {}
        user_id = data.get('user_id')
        connection_id = data.get('connection_id')

        if user_id:
            user_id = int(user_id)
        if connection_id:
            connection_id = int(connection_id)

        result = truelayer_service.sync_transactions(
            user_id=user_id,
            connection_id=connection_id
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ TrueLayer sync error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/sync/status', methods=['GET'])
def get_sync_status():
    """
    Get sync status for all accounts.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        Sync status dict with account details
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        status = truelayer_service.get_sync_status(user_id)
        return jsonify(status)

    except Exception as e:
        print(f"❌ TrueLayer sync status error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/disconnect', methods=['POST'])
def disconnect():
    """
    Disconnect TrueLayer bank connection.

    Request body:
        user_id (int): User ID (default: 1)

    Returns:
        Success message with disconnection count
    """
    try:
        data = request.json or {}
        user_id = int(data.get('user_id', 1))

        result = truelayer_service.disconnect(user_id)
        return jsonify(result)

    except Exception as e:
        print(f"❌ TrueLayer disconnect error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/clear-transactions', methods=['DELETE'])
def clear_transactions():
    """
    Clear all TrueLayer transactions for testing.

    Request body:
        user_id (int): User ID (default: 1)
        account_id (int): Specific account ID (optional)

    Returns:
        Result with count of deleted transactions
    """
    try:
        data = request.json or {}
        user_id = int(data.get('user_id', 1))
        account_id = data.get('account_id')

        if account_id:
            account_id = int(account_id)

        result = truelayer_service.clear_transactions(
            user_id=user_id,
            account_id=account_id
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Clear TrueLayer transactions error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/fetch-accounts', methods=['POST'])
def fetch_accounts():
    """
    Fetch accounts from TrueLayer API for a specific connection.

    Request body:
        connection_id (int): Connection ID

    Returns:
        Result with fetched accounts
    """
    try:
        data = request.json or {}
        connection_id = int(data.get('connection_id'))

        result = truelayer_service.fetch_accounts(connection_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Fetch TrueLayer accounts error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/fetch-cards', methods=['POST'])
def fetch_cards():
    """
    Fetch cards from TrueLayer API for a specific connection.

    Request body:
        connection_id (int): Connection ID

    Returns:
        Result with fetched cards
    """
    try:
        data = request.json or {}
        connection_id = int(data.get('connection_id'))

        result = truelayer_service.fetch_cards(connection_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Fetch TrueLayer cards error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/cards', methods=['GET'])
def get_cards():
    """
    Get all TrueLayer cards for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of card objects with connection details
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        cards = truelayer_service.get_cards(user_id)
        return jsonify(cards)

    except Exception as e:
        print(f"❌ Get TrueLayer cards error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/fetch-transactions', methods=['POST'])
def fetch_transactions():
    """
    Fetch transactions from TrueLayer API for a specific account.

    Request body:
        account_id (int): Account ID
        from_date (str): ISO format date (YYYY-MM-DD) (optional)
        to_date (str): ISO format date (YYYY-MM-DD) (optional)

    Returns:
        Result with fetched transactions
    """
    try:
        data = request.json or {}
        account_id = int(data.get('account_id'))
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        result = truelayer_service.fetch_transactions(
            account_id=account_id,
            from_date=from_date,
            to_date=to_date
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Fetch TrueLayer transactions error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/import/plan', methods=['POST'])
def plan_import():
    """
    Plan a batch import job without executing it.

    Request body:
        user_id (int): User ID (default: 1)
        from_date (str): ISO format date (YYYY-MM-DD) (optional)
        to_date (str): ISO format date (YYYY-MM-DD) (optional)

    Returns:
        Import plan with estimated transaction count
    """
    try:
        data = request.json or {}
        user_id = int(data.get('user_id', 1))
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        plan = truelayer_service.plan_import(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date
        )

        return jsonify(plan)

    except Exception as e:
        print(f"❌ Plan TrueLayer import error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/import/start', methods=['POST'])
def start_import():
    """
    Start a batch import job.

    Request body:
        user_id (int): User ID (default: 1)
        from_date (str): ISO format date (YYYY-MM-DD) (optional)
        to_date (str): ISO format date (YYYY-MM-DD) (optional)

    Returns:
        Job details with job_id
    """
    try:
        data = request.json or {}
        user_id = int(data.get('user_id', 1))
        from_date = data.get('from_date')
        to_date = data.get('to_date')

        result = truelayer_service.start_import(
            user_id=user_id,
            from_date=from_date,
            to_date=to_date
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Start TrueLayer import error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/import/status/<int:job_id>', methods=['GET'])
def get_import_status(job_id):
    """
    Get import job status.

    Path params:
        job_id (int): Job ID

    Returns:
        Job status dict or 404 if not found
    """
    try:
        status = truelayer_service.get_import_status(job_id)
        return jsonify(status)

    except ValueError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        print(f"❌ Get TrueLayer import status error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/import/history', methods=['GET'])
def get_import_history():
    """
    Get import job history for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of import jobs
    """
    try:
        user_id = int(request.args.get('user_id', 1))
        history = truelayer_service.get_import_history(user_id)
        return jsonify(history)

    except Exception as e:
        print(f"❌ Get TrueLayer import history error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@truelayer_bp.route('/webhook', methods=['POST'])
def handle_webhook():
    """
    Handle TrueLayer webhook event.

    Request body:
        event_id (str): Unique event ID
        event_type (str): Event type (e.g., 'transaction.created')
        payload (dict): Event payload

    Headers:
        Tl-Signature: Webhook signature for verification

    Returns:
        Success message
    """
    try:
        data = request.json or {}
        event_id = data.get('event_id')
        event_type = data.get('event_type')
        payload = data.get('payload', {})
        signature = request.headers.get('Tl-Signature')

        result = truelayer_service.handle_webhook(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            signature=signature
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ TrueLayer webhook error: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
