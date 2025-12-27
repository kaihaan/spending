"""
Sync Operation Tools

Provides 6 low-level sync operation MCP tools:
1. sync_bank_transactions - Sync TrueLayer bank transactions
2. sync_gmail_receipts - Sync Gmail receipt emails
3. sync_apple_purchases - Import Apple/App Store purchases
4. sync_amazon_business - Sync Amazon Business orders via SP-API
5. sync_amazon_orders - Import Amazon consumer orders from CSV
6. poll_job_status - Poll async job status until completion

These tools provide granular control over individual sync operations.
"""

import logging
from datetime import datetime

from ..client.flask_client import FlaskAPIError
from ..server import get_flask_client, mcp
from ..utils.defaults import (
    apply_date_range_defaults,
    apply_user_id_default,
    get_default_gmail_sync_type,
)
from ..utils.formatters import format_error_response, format_success_response
from ..utils.validators import (
    ValidationError,
    validate_date_range,
    validate_sync_type,
    validate_user_id,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Tool 1: sync_bank_transactions
# ============================================================================


@mcp.tool()
async def sync_bank_transactions(
    user_id: int | None = None, connection_id: int | None = None
) -> dict:
    """
    Sync TrueLayer bank transactions.

    Fetches the latest transactions from all connected bank accounts via TrueLayer API.

    Args:
        user_id: User ID (default: 1)
        connection_id: Specific connection ID (default: first active connection)

    Returns:
        Sync summary with total transactions synced, duplicates, and errors

    Example:
        sync_bank_transactions()  # Sync all accounts
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        client = get_flask_client()
        logger.info(
            f"Syncing bank transactions: user={user_id}, connection={connection_id}"
        )

        # Call TrueLayer sync endpoint
        payload = {"user_id": user_id}
        if connection_id:
            payload["connection_id"] = connection_id

        result = client.post("/api/truelayer/sync", payload)
        logger.info(f"Bank sync completed: {result.get('summary', {})}")

        return format_success_response(result)

    except ValidationError as e:
        logger.error(f"Validation error in sync_bank_transactions: {e}")
        return format_error_response(e)
    except FlaskAPIError as e:
        logger.error(f"API error in sync_bank_transactions: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in sync_bank_transactions: {e}")
        return format_error_response(e, {"tool": "sync_bank_transactions"})


# ============================================================================
# Tool 2: sync_gmail_receipts
# ============================================================================


@mcp.tool()
async def sync_gmail_receipts(
    user_id: int | None = None,
    sync_type: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    force_reparse: bool = False,
) -> dict:
    """
    Sync Gmail receipt emails.

    Fetches receipt emails from Gmail, parses them using vendor-specific parsers,
    and stores extracted purchase data.

    Args:
        user_id: User ID (default: 1)
        sync_type: Sync mode - "full", "incremental", or "auto" (default: "auto")
        from_date: Start date YYYY-MM-DD (default: 30 days ago)
        to_date: End date YYYY-MM-DD (default: today)
        force_reparse: Re-parse existing emails (default: false)

    Returns:
        Job details with job_id and status (async operation)

    Example:
        sync_gmail_receipts()  # Auto sync last 30 days
        sync_gmail_receipts(sync_type="full", force_reparse=True)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        if sync_type is None:
            sync_type = get_default_gmail_sync_type()
        from_date, to_date = apply_date_range_defaults(from_date, to_date)

        # Validate
        validate_user_id(user_id)
        validate_sync_type(sync_type)
        validate_date_range(from_date, to_date)

        client = get_flask_client()
        logger.info(
            f"Syncing Gmail receipts: user={user_id}, type={sync_type}, dates={from_date} to {to_date}"
        )

        # Call Gmail sync endpoint
        result = client.post(
            "/api/gmail/sync",
            {
                "user_id": user_id,
                "sync_type": sync_type,
                "from_date": from_date,
                "to_date": to_date,
                "force_reparse": force_reparse,
            },
        )

        logger.info(f"Gmail sync queued: job_id={result.get('job_id')}")

        return format_success_response(result, "Gmail sync job queued successfully")

    except ValidationError as e:
        logger.error(f"Validation error in sync_gmail_receipts: {e}")
        return format_error_response(e)
    except FlaskAPIError as e:
        logger.error(f"API error in sync_gmail_receipts: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in sync_gmail_receipts: {e}")
        return format_error_response(e, {"tool": "sync_gmail_receipts"})


# ============================================================================
# Tool 3: poll_job_status
# ============================================================================


@mcp.tool()
async def poll_job_status(
    job_id: str,
    job_type: str,
    timeout_seconds: int = 300,
    poll_interval_seconds: int = 5,
) -> dict:
    """
    Poll async job status until completion.

    Monitors an asynchronous job (Gmail sync, matching, enrichment) until it completes
    or times out.

    Args:
        job_id: Job ID to poll
        job_type: Type of job - "gmail_sync", "matching", or "enrichment"
        timeout_seconds: Max wait time in seconds (default: 300 = 5 minutes)
        poll_interval_seconds: Seconds between polls (default: 5)

    Returns:
        Final job status and result

    Example:
        poll_job_status(job_id="42", job_type="gmail_sync")
    """
    try:
        # Validate
        if not job_id:
            raise ValidationError("job_id is required", field="job_id")

        client = get_flask_client()
        logger.info(
            f"Polling job {job_id} (type={job_type}), timeout={timeout_seconds}s"
        )

        start_time = datetime.now()

        while True:
            # Check timeout
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout_seconds:
                logger.warning(f"Job {job_id} timeout after {elapsed}s")
                return format_error_response(
                    Exception(f"Job timeout after {timeout_seconds}s"),
                    {"job_id": job_id, "elapsed_seconds": elapsed},
                )

            # Poll job status
            try:
                if job_type == "gmail_sync":
                    status = client.get(
                        "/api/gmail/sync/status", {"user_id": 1}
                    )  # TODO: Get user_id from job
                elif job_type == "matching":
                    status = client.get(f"/api/matching/status/{job_id}")
                elif job_type == "enrichment":
                    status = client.get(f"/api/enrichment/status/{job_id}")
                else:
                    status = client.get(f"/api/jobs/{job_id}/status")

                # Check if complete
                if status.get("status") in ["completed", "failed", "success"]:
                    logger.info(f"Job {job_id} completed: {status.get('status')}")
                    return format_success_response(status)

                logger.debug(
                    f"Job {job_id} still running: {status.get('progress', 'N/A')}"
                )

            except FlaskAPIError as e:
                logger.error(f"Error polling job {job_id}: {e}")
                # If job not found, it may have completed - return error
                return format_error_response(e, {"job_id": job_id})

            # Wait before next poll
            import asyncio

            await asyncio.sleep(poll_interval_seconds)

    except ValidationError as e:
        logger.error(f"Validation error in poll_job_status: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in poll_job_status: {e}")
        return format_error_response(e, {"tool": "poll_job_status", "job_id": job_id})


# ============================================================================
# Tools 4-6: Stub implementations
# ============================================================================


@mcp.tool()
async def sync_apple_purchases(filename: str, user_id: int | None = None) -> dict:
    """
    Import Apple/App Store purchases from HTML file.

    Note: This tool requires manual file upload via the web UI first.

    Args:
        filename: Path to Apple HTML file
        user_id: User ID (default: 1)

    Returns:
        Import summary with transactions imported and matching results
    """
    return format_error_response(
        Exception(
            "Apple import requires file upload via web UI. Use /api/apple/import endpoint."
        ),
        {"tool": "sync_apple_purchases"},
    )


@mcp.tool()
async def sync_amazon_business(
    start_date: str, end_date: str, run_matching: bool = True
) -> dict:
    """
    Sync Amazon Business orders via SP-API.

    Args:
        start_date: Start date YYYY-MM-DD
        end_date: End date YYYY-MM-DD
        run_matching: Run matching after sync (default: true)

    Returns:
        Sync summary with orders and line items imported
    """
    return format_error_response(
        Exception(
            "Amazon Business sync not yet implemented. OAuth integration required."
        ),
        {"tool": "sync_amazon_business"},
    )


@mcp.tool()
async def sync_amazon_orders(
    csv_file_path: str, website: str = "amazon.co.uk", user_id: int | None = None
) -> dict:
    """
    Import Amazon consumer orders from CSV file.

    Note: This tool requires manual CSV file upload via the web UI first.

    Args:
        csv_file_path: Path to Amazon CSV file
        website: Amazon site - "amazon.co.uk" or "amazon.com" (default: "amazon.co.uk")
        user_id: User ID (default: 1)

    Returns:
        Import summary with orders imported and matching results
    """
    return format_error_response(
        Exception(
            "Amazon CSV import requires file upload via web UI. Use /api/amazon/import endpoint."
        ),
        {"tool": "sync_amazon_orders"},
    )
