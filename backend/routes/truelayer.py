"""
TrueLayer Routes - Flask Blueprint

Handles all TrueLayer bank integration endpoints including OAuth, account discovery,
transaction sync, and import job management. Routes are thin controllers that
delegate to truelayer_service for business logic.
"""

import traceback
from datetime import UTC

from flask import Blueprint, jsonify, redirect, request

from mcp import truelayer_auth
from services import truelayer_service

truelayer_bp = Blueprint("truelayer", __name__, url_prefix="/api/truelayer")


@truelayer_bp.route("/authorize", methods=["GET"])
def authorize():
    """
    Initiate TrueLayer OAuth flow.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        JSON with auth_url, state, and code_verifier for frontend-managed OAuth
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        result = truelayer_auth.get_authorization_url(user_id)
        # Return JSON instead of redirecting to allow frontend to manage OAuth state
        return jsonify(result)
    except Exception as e:
        print(f"❌ TrueLayer authorization error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/callback", methods=["GET", "POST"])
def callback():
    """
    Handle TrueLayer OAuth callback.

    Completes the full OAuth flow: retrieves code_verifier from database,
    exchanges authorization code for tokens, and saves the connection.

    Query params:
        code (str): Authorization code from TrueLayer
        state (str): OAuth state parameter for CSRF protection
        error (str): OAuth error if authorization failed

    Returns:
        Redirect to frontend settings page with success/error status
    """
    try:
        # Check for OAuth errors from TrueLayer
        error = request.args.get("error")
        if error:
            error_description = request.args.get(
                "error_description", "Authorization failed"
            )
            print(f"❌ TrueLayer OAuth error: {error} - {error_description}")
            return redirect(f"http://localhost:5173/settings#bank?error={error}")

        # Get authorization code and state from TrueLayer callback
        code = request.args.get("code")
        state = request.args.get("state")

        if not code or not state:
            print("❌ Missing code or state in callback")
            return redirect("http://localhost:5173/settings#bank?error=missing_params")

        print(f"✓ TrueLayer OAuth callback received (state: {state[:8]}...)")

        # Retrieve code_verifier and user_id from database using state
        from datetime import datetime, timedelta

        from backend.database.base import get_session
        from backend.database.models.truelayer import OAuthState

        with get_session() as session:
            # Query OAuth state created within last 10 minutes
            ten_minutes_ago = datetime.now(UTC) - timedelta(minutes=10)
            oauth_state = (
                session.query(OAuthState)
                .filter(
                    OAuthState.state == state,
                    OAuthState.created_at > ten_minutes_ago,
                )
                .first()
            )

        if not oauth_state:
            print(f"❌ Invalid or expired OAuth state: {state[:8]}...")
            return redirect("http://localhost:5173/settings#bank?error=invalid_state")

        user_id = oauth_state.user_id
        code_verifier = oauth_state.code_verifier
        print(f"✓ Retrieved OAuth state for user {user_id}")

        # Exchange authorization code for access/refresh tokens
        print("📝 Exchanging authorization code for tokens...")
        token_data = truelayer_auth.exchange_code_for_token(code, code_verifier)

        # Get provider info to check for existing connection
        print("🔍 Identifying bank provider...")
        provider_id, provider_name = truelayer_auth.get_provider_from_accounts(
            token_data["access_token"]
        )
        print(f"   Provider: {provider_name} (id: {provider_id})")

        # Check if connection already exists for this provider
        from backend.database import truelayer

        existing_connections = truelayer.get_user_connections(user_id)
        existing_connection = next(
            (c for c in existing_connections if c.get("provider_id") == provider_id),
            None,
        )

        if existing_connection:
            # Update existing connection with new tokens
            connection_id = existing_connection["id"]
            print(
                f"♻️  Updating existing connection (id={connection_id}) with fresh tokens..."
            )

            # Encrypt tokens
            encrypted_access = truelayer_auth.encrypt_token(token_data["access_token"])
            encrypted_refresh = (
                truelayer_auth.encrypt_token(token_data["refresh_token"])
                if token_data.get("refresh_token")
                else None
            )

            truelayer.update_connection_tokens(
                connection_id=connection_id,
                access_token=encrypted_access,
                refresh_token=encrypted_refresh,
                expires_at=token_data.get("expires_at"),
            )
            print("✓ Tokens refreshed for existing connection")
        else:
            # Create new connection
            print(f"💾 Creating new bank connection for user {user_id}...")
            connection = truelayer_auth.save_bank_connection(user_id, token_data)
            connection_id = connection.get("connection_id")
            print(f"✓ New TrueLayer connection created (id={connection_id})")

        # Discover and save bank accounts
        print("🔍 Discovering bank accounts...")
        try:
            account_discovery = truelayer_auth.discover_and_save_accounts(
                connection_id=connection_id,
                access_token=token_data["access_token"],  # Use unencrypted token
            )
            print(
                f"✓ Discovered and saved {account_discovery.get('accounts_saved')} accounts"
            )
        except Exception as discover_error:
            print(f"⚠️  Account discovery failed: {discover_error}")
            # Continue anyway - connection is saved, user can retry later
            import traceback

            traceback.print_exc()

        # Clean up OAuth state from database
        with get_session() as session:
            session.query(OAuthState).filter(OAuthState.state == state).delete()
            session.commit()

        # Redirect to frontend settings with success
        return redirect("http://localhost:5173/settings#bank?success=true")

    except Exception as e:
        print(f"❌ TrueLayer callback error: {e}")
        traceback.print_exc()
        return redirect("http://localhost:5173/settings#bank?error=callback_error")


@truelayer_bp.route("/exchange-token", methods=["POST"])
def exchange_token():
    """
    Exchange authorization code for access/refresh tokens.

    Called by frontend after OAuth callback with code from sessionStorage.

    Request body:
        code (str): Authorization code from TrueLayer
        code_verifier (str): PKCE code verifier from sessionStorage
        user_id (int): User ID (default: 1)

    Returns:
        JSON with connection details and success status
    """
    try:
        data = request.json or {}
        code = data.get("code")
        code_verifier = data.get("code_verifier")
        user_id = int(data.get("user_id", 1))

        if not code or not code_verifier:
            return jsonify({"error": "Missing code or code_verifier"}), 400

        # Exchange authorization code for tokens
        print("📝 Exchanging authorization code for tokens...")
        token_data = truelayer_auth.exchange_code_for_token(code, code_verifier)

        # Save connection to database
        print(f"💾 Saving bank connection for user {user_id}...")
        connection = truelayer_auth.save_bank_connection(user_id, token_data)

        print(f"✓ TrueLayer connection established: {connection.get('provider_name')}")

        return jsonify(
            {
                "success": True,
                "connection": connection,
                "message": "Bank connected successfully",
            }
        )

    except Exception as e:
        print(f"❌ Token exchange error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/connections", methods=["GET"])
def get_connections():
    """
    Get all TrueLayer connections for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of TrueLayer connection objects
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        connections = truelayer_service.get_connections(user_id)
        return jsonify(connections)

    except Exception as e:
        print(f"❌ Get TrueLayer connections error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/accounts", methods=["GET"])
def get_accounts():
    """
    Get all TrueLayer accounts for a user, grouped by connection.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        {
            "connections": [
                {
                    "id": int,
                    "provider_id": str,
                    "provider_name": str,
                    "connection_status": str,
                    "is_token_expired": bool,
                    "last_synced_at": str,
                    "accounts": [...]
                }
            ]
        }
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        accounts = truelayer_service.get_accounts(user_id)

        # Group accounts by connection
        connections_map = {}
        for account in accounts:
            conn = account.get("connection", {})
            conn_id = conn.get("id")

            if conn_id not in connections_map:
                connections_map[conn_id] = {
                    "id": conn.get("id"),
                    "provider_id": conn.get("provider_id"),
                    "provider_name": conn.get("provider_name"),
                    "connection_status": conn.get("connection_status"),
                    "is_token_expired": conn.get("is_token_expired", False),
                    "last_synced_at": conn.get("last_synced_at"),
                    "accounts": [],
                }

            # Add account to connection (without nested connection object)
            account_data = {
                "id": account.get("id"),
                "account_id": account.get("account_id"),
                "display_name": account.get("display_name"),
                "account_type": account.get("account_type"),
                "currency": account.get("currency"),
                "last_synced_at": account.get("last_synced_at"),
            }
            connections_map[conn_id]["accounts"].append(account_data)

        # Convert map to list
        connections = list(connections_map.values())

        return jsonify({"connections": connections})

    except Exception as e:
        print(f"❌ Get TrueLayer accounts error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/discover-accounts", methods=["POST"])
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
        user_id = int(data.get("user_id", 1))

        result = truelayer_service.discover_accounts(user_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Discover TrueLayer accounts error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/sync", methods=["POST"])
def sync_transactions():
    """
    Trigger manual sync of TrueLayer transactions.

    Query params:
        async (str): If 'true', runs as Celery task and returns job_id

    Request body:
        user_id (int): User ID (optional)
        connection_id (int): Connection ID (optional)
        date_from (str): Start date YYYY-MM-DD (optional)
        date_to (str): End date YYYY-MM-DD (optional)

    Returns:
        - Sync mode: Sync result with summary statistics
        - Async mode: Job details with job_id for progress tracking
    """
    try:
        data = request.json or {}
        user_id = data.get("user_id")
        connection_id = data.get("connection_id")
        date_from = data.get("date_from")
        date_to = data.get("date_to")

        if user_id:
            user_id = int(user_id)
        if connection_id:
            connection_id = int(connection_id)

        # Check if async mode requested
        async_mode = request.args.get("async", "false").lower() == "true"

        if async_mode:
            # Async mode: Trigger Celery task
            from tasks.truelayer_tasks import sync_truelayer_task

            task = sync_truelayer_task.delay(
                user_id=user_id,
                connection_id=connection_id,
                date_from=date_from,
                date_to=date_to,
            )

            return jsonify(
                {
                    "job_id": task.id,
                    "status": "queued",
                    "message": "TrueLayer sync started in background",
                    "user_id": user_id,
                    "connection_id": connection_id,
                    "date_from": date_from,
                    "date_to": date_to,
                }
            )
        # Sync mode (existing behavior)
        result = truelayer_service.sync_transactions(
            user_id=user_id,
            connection_id=connection_id,
            date_from=date_from,
            date_to=date_to,
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ TrueLayer sync error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/jobs/<job_id>", methods=["GET"])
def get_job_status(job_id):
    """
    Get TrueLayer sync job status by Celery task ID.

    Path params:
        job_id (str): Celery task ID

    Returns:
        Job status with progress or result
    """
    try:
        status = truelayer_service.get_job_status(job_id)

        # Check if service indicated a specific HTTP status
        http_status = status.pop("_http_status", 200)

        return jsonify(status), http_status

    except Exception as e:
        print(f"❌ TrueLayer job status error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    """
    Get sync status for all accounts.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        Sync status dict with account details
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        status = truelayer_service.get_sync_status(user_id)
        return jsonify(status)

    except Exception as e:
        print(f"❌ TrueLayer sync status error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/disconnect", methods=["POST"])
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
        user_id = int(data.get("user_id", 1))

        result = truelayer_service.disconnect(user_id)
        return jsonify(result)

    except Exception as e:
        print(f"❌ TrueLayer disconnect error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/clear-transactions", methods=["DELETE"])
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
        user_id = int(data.get("user_id", 1))
        account_id = data.get("account_id")

        if account_id:
            account_id = int(account_id)

        result = truelayer_service.clear_transactions(
            user_id=user_id, account_id=account_id
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Clear TrueLayer transactions error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/fetch-accounts", methods=["POST"])
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
        connection_id = int(data.get("connection_id"))

        result = truelayer_service.fetch_accounts(connection_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Fetch TrueLayer accounts error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/fetch-cards", methods=["POST"])
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
        connection_id = int(data.get("connection_id"))

        result = truelayer_service.fetch_cards(connection_id)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Fetch TrueLayer cards error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/cards", methods=["GET"])
def get_cards():
    """
    Get all TrueLayer cards for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of card objects with connection details
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        cards = truelayer_service.get_cards(user_id)
        return jsonify(cards)

    except Exception as e:
        print(f"❌ Get TrueLayer cards error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/fetch-transactions", methods=["POST"])
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
        account_id = int(data.get("account_id"))
        from_date = data.get("from_date")
        to_date = data.get("to_date")

        result = truelayer_service.fetch_transactions(
            account_id=account_id, from_date=from_date, to_date=to_date
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Fetch TrueLayer transactions error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/import/plan", methods=["POST"])
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
        user_id = int(data.get("user_id", 1))
        from_date = data.get("from_date")
        to_date = data.get("to_date")

        plan = truelayer_service.plan_import(
            user_id=user_id, from_date=from_date, to_date=to_date
        )

        return jsonify(plan)

    except Exception as e:
        print(f"❌ Plan TrueLayer import error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/import/start", methods=["POST"])
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
        user_id = int(data.get("user_id", 1))
        from_date = data.get("from_date")
        to_date = data.get("to_date")

        result = truelayer_service.start_import(
            user_id=user_id, from_date=from_date, to_date=to_date
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ Start TrueLayer import error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/import/status/<int:job_id>", methods=["GET"])
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
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Get TrueLayer import status error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/import/history", methods=["GET"])
def get_import_history():
    """
    Get import job history for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of import jobs
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        history = truelayer_service.get_import_history(user_id)
        return jsonify(history)

    except Exception as e:
        print(f"❌ Get TrueLayer import history error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@truelayer_bp.route("/webhook", methods=["POST"])
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
        event_id = data.get("event_id")
        event_type = data.get("event_type")
        payload = data.get("payload", {})
        signature = request.headers.get("Tl-Signature")

        result = truelayer_service.handle_webhook(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            signature=signature,
        )

        return jsonify(result)

    except Exception as e:
        print(f"❌ TrueLayer webhook error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
