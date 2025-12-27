"""
Apple Service - Business Logic

Orchestrates Apple transaction integration including:
- HTML file import from Apple Report a Problem page
- Browser-based import with auto-scrolling and duplicate detection
- Transaction matching with TrueLayer bank transactions
- CSV export functionality

Separates business logic from HTTP routing concerns.
"""

import os

from database import apple, create_matching_job, update_matching_job_status
from mcp import apple_browser_import, apple_matcher_truelayer, apple_parser

# ============================================================================
# File-based Import
# ============================================================================


def import_from_html(filename: str) -> dict:
    """
    Import Apple transactions from HTML file.

    Args:
        filename: Name of HTML file in sample folder

    Returns:
        Import result with counts and matching results

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If no transactions found
    """
    file_path = os.path.join("..", "sample", filename)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {filename}")

    # Parse HTML file
    transactions = apple_parser.parse_apple_html(file_path)

    if not transactions:
        raise ValueError("No transactions found in HTML file")

    # Import to database
    imported, duplicates = apple.import_apple_transactions(transactions, filename)

    # Run matching with TrueLayer transactions
    match_results = apple_matcher_truelayer.match_all_apple_transactions()

    return {
        "success": True,
        "transactions_imported": imported,
        "transactions_duplicated": duplicates,
        "matching_results": match_results,
        "filename": filename,
    }


def list_html_files() -> dict:
    """
    List available Apple HTML files in the sample folder.

    Returns:
        File list with count
    """
    files = apple_parser.get_apple_html_files("../sample")

    # Get just the filenames
    file_list = [{"filename": os.path.basename(f), "path": f} for f in files]

    return {"files": file_list, "count": len(file_list)}


def export_to_csv(filename: str) -> dict:
    """
    Convert Apple HTML to CSV format.

    Args:
        filename: Name of HTML file in sample folder

    Returns:
        Export result with CSV filename

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If no transactions found
    """
    file_path = os.path.join("..", "sample", filename)

    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {filename}")

    # Parse HTML file
    transactions = apple_parser.parse_apple_html(file_path)

    if not transactions:
        raise ValueError("No transactions found in HTML file")

    # Generate CSV filename
    csv_filename = filename.replace(".html", ".csv")
    csv_path = os.path.join("..", "sample", csv_filename)

    # Export to CSV
    apple_parser.export_to_csv(transactions, csv_path)

    return {
        "success": True,
        "csv_filename": csv_filename,
        "transactions_count": len(transactions),
        "message": f"Exported {len(transactions)} transactions to {csv_filename}",
    }


# ============================================================================
# Browser-based Import
# ============================================================================


def start_browser_session() -> dict:
    """
    Start a browser session for Apple import.

    Launches a visible Chromium browser navigated to Apple's Report a Problem page.
    User must log in manually with their Apple ID and 2FA.

    Returns:
        Session start result

    Raises:
        Exception: If browser launch fails
    """
    apple_browser_import.AppleBrowserSession.start_session()

    return {
        "success": True,
        "status": "ready",
        "message": "Browser launched. Log in to your Apple ID and navigate to your purchase history.",
    }


def get_browser_status() -> dict:
    """
    Get current browser session status.

    Returns:
        Browser session status dict
    """
    return apple_browser_import.AppleBrowserSession.get_status()


def capture_from_browser() -> dict:
    """
    Capture HTML from browser and import transactions.

    Auto-scrolls the page to load all transactions (stops when finding
    transactions already in database), then captures HTML, parses it,
    imports to database, and runs matching.

    Returns:
        Import result with counts and matching results

    Raises:
        ValueError: If no transactions found in page
        Exception: If capture fails
    """
    # Get known order_ids for stop condition during scrolling
    known_order_ids = apple.get_apple_order_ids()
    print(
        f"[Apple Import] Found {len(known_order_ids)} existing Apple order_ids in database"
    )

    # Auto-scroll to load all transactions, then capture HTML
    html_content = apple_browser_import.AppleBrowserSession.scroll_and_capture(
        known_order_ids
    )

    # Parse HTML content
    transactions = apple_parser.parse_apple_html_content(html_content)

    if not transactions:
        raise ValueError(
            "No transactions found in page. Make sure your purchase history is visible."
        )

    # Import to database
    imported, duplicates = apple.import_apple_transactions(
        transactions, "browser-import"
    )

    # Run matching with TrueLayer transactions
    match_results = apple_matcher_truelayer.match_all_apple_transactions()

    return {
        "success": True,
        "transactions_imported": imported,
        "transactions_duplicated": duplicates,
        "matching_results": match_results,
        "source": "browser-import",
    }


def cancel_browser_session() -> dict:
    """
    Cancel the current browser session.

    Returns:
        Cancellation result
    """
    apple_browser_import.AppleBrowserSession.cancel_session()

    return {"success": True, "message": "Browser session cancelled"}


# ============================================================================
# Data Operations
# ============================================================================


def get_transactions() -> dict:
    """
    Get all Apple transactions.

    Returns:
        Transactions list with count
    """
    transactions = apple.get_apple_transactions()

    return {"transactions": transactions, "count": len(transactions)}


def get_statistics() -> dict:
    """
    Get Apple transactions statistics.

    Returns:
        Statistics dict
    """
    return apple.get_apple_statistics()


def run_matching(async_mode: bool = True, user_id: int = 1) -> dict:
    """
    Run or re-run Apple transaction matching (TrueLayer only).

    Args:
        async_mode: If True, runs as Celery task and returns job_id
        user_id: User ID for job tracking

    Returns:
        Job details if async, or match results if sync
    """
    if async_mode:
        from tasks.matching_tasks import match_apple_transactions_task

        # Create job entry
        job_id = create_matching_job(user_id, "apple")

        # Dispatch Celery task
        task = match_apple_transactions_task.delay(job_id, user_id)

        # Update job status
        update_matching_job_status(job_id, "queued")

        return {
            "success": True,
            "async": True,
            "job_id": job_id,
            "celery_task_id": task.id,
            "status": "queued",
        }
    # Sync mode for backward compatibility
    results = apple_matcher_truelayer.match_all_apple_transactions()

    return {"success": True, "async": False, "results": results}


def clear_transactions() -> dict:
    """
    Clear all Apple transactions (for testing/reimporting).

    Returns:
        Deletion count
    """
    transactions_deleted = apple.clear_apple_transactions()

    return {
        "success": True,
        "transactions_deleted": transactions_deleted,
        "message": f"Cleared {transactions_deleted} Apple transactions",
    }
