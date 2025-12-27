"""
Apple Routes - Flask Blueprint

Handles all Apple transaction integration endpoints:
- File-based import: HTML parsing and CSV export
- Browser-based import: Automated capture with Playwright
- Transaction matching: Link to TrueLayer bank transactions
- Data operations: List, statistics, clearing

Routes are thin controllers that delegate to apple_service for business logic.
"""

import traceback

from flask import Blueprint, jsonify, request

from services import apple_service

apple_bp = Blueprint("apple", __name__, url_prefix="/api/apple")


# ============================================================================
# File-based Import
# ============================================================================


@apple_bp.route("/import", methods=["POST"])
def import_transactions():
    """
    Import Apple transactions from HTML file.

    Request body:
        filename (str): Name of HTML file in sample folder

    Returns:
        Import result with counts and matching results
    """
    try:
        data = request.json

        if "filename" not in data:
            return jsonify({"error": "Missing filename"}), 400

        filename = data["filename"]
        result = apple_service.import_from_html(filename)

        return jsonify(result), 201

    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"❌ Apple import error: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Import failed: {str(e)}"}), 500


@apple_bp.route("/files", methods=["GET"])
def list_files():
    """
    List available Apple HTML files in the sample folder.

    Returns:
        File list with count
    """
    try:
        result = apple_service.list_html_files()
        return jsonify(result)

    except Exception as e:
        print(f"❌ List Apple files error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@apple_bp.route("/export-csv", methods=["POST"])
def export_csv():
    """
    Convert Apple HTML to CSV format.

    Request body:
        filename (str): Name of HTML file in sample folder

    Returns:
        Export result with CSV filename
    """
    try:
        data = request.json

        if "filename" not in data:
            return jsonify({"error": "Missing filename"}), 400

        filename = data["filename"]
        result = apple_service.export_to_csv(filename)

        return jsonify(result)

    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"❌ Apple CSV export error: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


# ============================================================================
# Browser-based Import
# ============================================================================


@apple_bp.route("/import/browser-start", methods=["POST"])
def start_browser():
    """
    Start a browser session for Apple import.

    Launches a visible Chromium browser navigated to Apple's Report a Problem page.
    User must log in manually with their Apple ID and 2FA.

    Returns:
        Session start result
    """
    try:
        result = apple_service.start_browser_session()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Apple browser start error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 400


@apple_bp.route("/import/browser-status", methods=["GET"])
def get_browser_status():
    """
    Get current browser session status.

    Returns:
        Browser session status dict
    """
    try:
        result = apple_service.get_browser_status()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Apple browser status error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@apple_bp.route("/import/browser-capture", methods=["POST"])
def capture_browser():
    """
    Capture HTML from browser and import transactions.

    Auto-scrolls the page to load all transactions (stops when finding
    transactions already in database), then captures HTML, parses it,
    imports to database, and runs matching.

    Returns:
        Import result with counts and matching results
    """
    try:
        result = apple_service.capture_from_browser()
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"❌ Apple browser capture error: {e}")
        traceback.print_exc()
        return jsonify({"error": f"Capture failed: {str(e)}"}), 500


@apple_bp.route("/import/browser-cancel", methods=["POST"])
def cancel_browser():
    """
    Cancel the current browser session.

    Returns:
        Cancellation result
    """
    try:
        result = apple_service.cancel_browser_session()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Apple browser cancel error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# Data Operations
# ============================================================================


@apple_bp.route("", methods=["GET"])
def get_transactions():
    """
    Get all Apple transactions.

    Returns:
        Transactions list with count
    """
    try:
        result = apple_service.get_transactions()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get Apple transactions error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@apple_bp.route("/statistics", methods=["GET"])
def get_statistics():
    """
    Get Apple transactions statistics.

    Returns:
        Statistics dict
    """
    try:
        result = apple_service.get_statistics()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Get Apple statistics error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@apple_bp.route("/match", methods=["POST"])
def run_matching():
    """
    Run or re-run Apple transaction matching (TrueLayer only).

    Query params:
        async (bool): If 'true', runs matching as async Celery task and returns job_id (default: true)
        user_id (int): User ID for job tracking (default: 1)

    Returns:
        Job details if async, or match results if sync
    """
    try:
        async_mode = request.args.get("async", "true").lower() == "true"
        user_id = int(request.args.get("user_id", 1))

        result = apple_service.run_matching(async_mode=async_mode, user_id=user_id)
        return jsonify(result)

    except Exception as e:
        print(f"❌ Apple matching error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@apple_bp.route("", methods=["DELETE"])
def clear_transactions():
    """
    Clear all Apple transactions (for testing/reimporting).

    Returns:
        Deletion count
    """
    try:
        result = apple_service.clear_transactions()
        return jsonify(result)

    except Exception as e:
        print(f"❌ Clear Apple transactions error: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
