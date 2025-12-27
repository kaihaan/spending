"""
Gmail Routes - Flask Blueprint

Handles all Gmail integration endpoints including OAuth, sync, parsing, and matching.
Routes are thin controllers that delegate to gmail_service for business logic.
"""

import traceback

from flask import Blueprint, jsonify, request

from mcp import gmail_auth
from services import gmail_service

gmail_bp = Blueprint("gmail", __name__, url_prefix="/api/gmail")


@gmail_bp.route("/authorize", methods=["GET"])
def authorize():
    """
    Initiate Gmail OAuth flow.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        Redirect to Google OAuth consent screen
    """
    try:
        from flask import redirect

        user_id = int(request.args.get("user_id", 1))
        result = gmail_auth.get_authorization_url(user_id)
        return redirect(result["auth_url"])
    except Exception as e:
        print(f"❌ Gmail authorization error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/callback", methods=["GET"])
def callback():
    """
    Handle Gmail OAuth callback.

    Query params:
        state (str): OAuth state parameter
        code (str): Authorization code
        error (str): OAuth error if any

    Returns:
        Redirect to frontend with success/error status
    """
    try:
        return gmail_auth.handle_oauth_callback(request.args)
    except Exception as e:
        print(f"❌ Gmail callback error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/connection", methods=["GET"])
def get_connection():
    """
    Get Gmail connection status for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        Connection details or null if not connected
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        connection = gmail_service.get_connection(user_id)

        if not connection:
            return jsonify(None)

        # Remove sensitive fields
        connection.pop("access_token", None)
        connection.pop("refresh_token", None)

        return jsonify(connection)

    except Exception as e:
        print(f"❌ Get Gmail connection error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/connections", methods=["GET"])
def get_connections():
    """
    Get all Gmail connections (alias for /connection).
    Returns connection in a list for API consistency.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of connection objects
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        connection = gmail_service.get_connection(user_id)

        if not connection:
            return jsonify([])

        # Remove sensitive fields
        connection.pop("access_token", None)
        connection.pop("refresh_token", None)

        return jsonify([connection])

    except Exception as e:
        print(f"❌ Get Gmail connections error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/disconnect", methods=["POST"])
def disconnect():
    """
    Disconnect Gmail account.

    Request body:
        user_id (int): User ID (default: 1)

    Returns:
        Success message
    """
    try:
        data = request.json or {}
        user_id = int(data.get("user_id", 1))

        gmail_service.disconnect(user_id)
        return jsonify({"message": "Gmail account disconnected successfully"})

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Gmail disconnect error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/statistics", methods=["GET"])
def get_statistics():
    """
    Get Gmail receipt statistics.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        Statistics summary
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        stats = gmail_service.get_statistics(user_id)
        return jsonify(stats)

    except Exception as e:
        print(f"❌ Gmail statistics error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/receipts", methods=["GET"])
def get_receipts():
    """
    Get Gmail receipts with pagination and filtering.

    Query params:
        user_id (int): User ID (default: 1)
        limit (int): Max receipts to return (default: 100)
        offset (int): Pagination offset (default: 0)
        parsing_status (str): Filter by status ('parsed', 'pending', 'failed')

    Returns:
        List of receipts
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        limit = int(request.args.get("limit", 100))
        offset = int(request.args.get("offset", 0))
        parsing_status = request.args.get("parsing_status")

        receipts = gmail_service.get_receipts(
            user_id=user_id, limit=limit, offset=offset, parsing_status=parsing_status
        )

        return jsonify(receipts)

    except Exception as e:
        print(f"❌ Get Gmail receipts error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/receipts/<int:receipt_id>", methods=["GET"])
def get_receipt(receipt_id):
    """
    Get a specific Gmail receipt.

    Path params:
        receipt_id (int): Receipt ID

    Returns:
        Receipt details or 404
    """
    try:
        receipt = gmail_service.get_receipt_by_id(receipt_id)

        if not receipt:
            return jsonify({"error": "Receipt not found"}), 404

        return jsonify(receipt)

    except Exception as e:
        print(f"❌ Get Gmail receipt error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/receipts/<int:receipt_id>", methods=["DELETE"])
def delete_receipt(receipt_id):
    """
    Soft delete a Gmail receipt.

    Path params:
        receipt_id (int): Receipt ID

    Returns:
        Success message
    """
    try:
        gmail_service.delete_receipt(receipt_id)
        return jsonify({"message": "Receipt deleted successfully"})

    except Exception as e:
        print(f"❌ Delete Gmail receipt error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/sync", methods=["POST"])
def start_sync():
    """
    Start a Gmail receipt sync job asynchronously.

    Request body:
        user_id (int): User ID (default: 1)
        sync_type (str): 'full' or 'incremental' (default: 'full')
        from_date (str): ISO format date (YYYY-MM-DD)
        to_date (str): ISO format date (YYYY-MM-DD)
        force_reparse (bool): Re-parse existing emails (default: false)

    Returns:
        Job details with job_id and status
    """
    try:
        data = request.json or {}
        user_id = int(data.get("user_id", 1))
        sync_type = data.get("sync_type", "full")
        from_date = data.get("from_date")
        to_date = data.get("to_date")
        force_reparse = data.get("force_reparse", False)

        result = gmail_service.start_sync(
            user_id=user_id,
            sync_type=sync_type,
            from_date=from_date,
            to_date=to_date,
            force_reparse=force_reparse,
        )

        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"❌ Gmail sync error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/sync/status", methods=["GET"])
def get_sync_status():
    """
    Get Gmail sync status for a user.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        Sync status with connection details and latest job
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        status = gmail_service.get_sync_status(user_id)
        return jsonify(status)

    except Exception as e:
        print(f"❌ Gmail sync status error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/match", methods=["POST"])
def run_matching():
    """
    Run Gmail receipt matching to link receipts with bank transactions.

    Query params:
        async (str): If 'true', runs as async Celery task (default: false for Gmail)
        user_id (int): User ID (default: 1)

    Returns:
        Match results if sync, or job details if async
    """
    try:
        async_mode = request.args.get("async", "false").lower() == "true"
        user_id = int(request.args.get("user_id", 1))

        if async_mode:
            # Async mode: Trigger Celery task
            from tasks.gmail_tasks import match_gmail_receipts_task

            task = match_gmail_receipts_task.delay(user_id)

            return jsonify(
                {
                    "job_id": task.id,
                    "status": "queued",
                    "message": "Gmail matching started in background",
                }
            )
        # Sync mode: Run matching directly
        from mcp.gmail_matcher import match_all_gmail_receipts

        results = match_all_gmail_receipts(user_id)

        return jsonify(
            {
                "results": {
                    "total_processed": results.get("total_receipts", 0),
                    "matched": results.get("matched", 0),
                    "unmatched": results.get("unmatched", 0),
                    "auto_matched": results.get("auto_matched", 0),
                    "needs_confirmation": results.get("needs_confirmation", 0),
                }
            }
        )

    except Exception as e:
        print(f"❌ Gmail matching error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/matches", methods=["GET"])
def get_matches():
    """
    Get all Gmail-to-transaction matches.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of matches
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        matches = gmail_service.get_matches(user_id)
        return jsonify(matches)

    except Exception as e:
        print(f"❌ Get Gmail matches error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/matches/<int:match_id>/confirm", methods=["POST"])
def confirm_match(match_id):
    """
    Confirm a Gmail receipt match.

    Path params:
        match_id (int): Match ID

    Returns:
        Success message
    """
    try:
        gmail_service.confirm_match(match_id)
        return jsonify({"message": "Match confirmed successfully"})

    except Exception as e:
        print(f"❌ Confirm Gmail match error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/matches/<int:match_id>", methods=["DELETE"])
def delete_match(match_id):
    """
    Delete a Gmail receipt match.

    Path params:
        match_id (int): Match ID

    Returns:
        Success message
    """
    try:
        gmail_service.delete_match(match_id)
        return jsonify({"message": "Match deleted successfully"})

    except Exception as e:
        print(f"❌ Delete Gmail match error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/merchants", methods=["GET"])
def get_merchants():
    """
    Get merchant summary from Gmail receipts.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of merchants with receipt counts
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        merchants = gmail_service.get_merchants(user_id)
        return jsonify(merchants)

    except Exception as e:
        print(f"❌ Get Gmail merchants error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/merchants/<merchant_identifier>/receipts", methods=["GET"])
def get_merchant_receipts(merchant_identifier):
    """
    Get receipts for a specific merchant.

    Path params:
        merchant_identifier (str): Merchant domain or normalized name

    Query params:
        user_id (int): User ID (default: 1)
        limit (int): Max receipts to return (default: 50)
        offset (int): Pagination offset (default: 0)

    Returns:
        Dictionary with receipts list and total count
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        limit = int(request.args.get("limit", 50))
        offset = int(request.args.get("offset", 0))

        result = gmail_service.get_merchant_receipts(
            merchant_identifier=merchant_identifier,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get merchant receipts error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/sender-patterns", methods=["GET"])
def get_sender_patterns():
    """
    Get sender email patterns from Gmail receipts.

    Query params:
        user_id (int): User ID (default: 1)

    Returns:
        List of sender patterns
    """
    try:
        user_id = int(request.args.get("user_id", 1))
        patterns = gmail_service.get_sender_patterns(user_id)
        return jsonify(patterns)

    except Exception as e:
        print(f"❌ Get sender patterns error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@gmail_bp.route("/llm-queue", methods=["GET"])
def get_llm_queue():
    """
    Get receipts in the LLM processing queue.

    Query params:
        limit (int): Max receipts to return (default: 50)

    Returns:
        LLM queue summary
    """
    try:
        limit = int(request.args.get("limit", 50))
        queue = gmail_service.get_llm_queue(limit=limit)
        return jsonify(queue)

    except Exception as e:
        print(f"❌ Get LLM queue error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
