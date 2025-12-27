"""
Gmail Service - Business Logic

Orchestrates Gmail integration including OAuth, sync, parsing, and matching.
Separates business logic from HTTP routing concerns.
"""

from database import gmail
from mcp import gmail_sync
from tasks.gmail_tasks import sync_gmail_receipts_task


def start_sync(
    user_id: int,
    sync_type: str = "full",
    from_date: str = None,
    to_date: str = None,
    force_reparse: bool = False,
) -> dict:
    """
    Start a Gmail receipt sync job asynchronously.

    Args:
        user_id: User ID
        sync_type: 'full' or 'incremental'
        from_date: ISO format date string (YYYY-MM-DD)
        to_date: ISO format date string (YYYY-MM-DD)
        force_reparse: Whether to re-parse existing emails

    Returns:
        Job details dict with job_id and status

    Raises:
        ValueError: If no Gmail connection found
    """
    # Get connection for user
    connection = gmail.get_gmail_connection(user_id)
    if not connection:
        raise ValueError("No Gmail connection found")

    connection_id = connection["id"]

    # Create job record first for tracking
    job_id = gmail.create_gmail_sync_job(connection_id, job_type=sync_type)

    # Store date range in job if provided
    if from_date or to_date:
        gmail.update_gmail_sync_job_dates(job_id, from_date, to_date)

    # Dispatch async task
    sync_gmail_receipts_task.delay(
        connection_id, sync_type, job_id, from_date, to_date, force_reparse
    )

    print(
        f"📧 Gmail sync queued: job_id={job_id}, type={sync_type}, "
        f"dates={from_date} to {to_date}, force_reparse={force_reparse}"
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "sync_type": sync_type,
        "from_date": from_date,
        "to_date": to_date,
        "force_reparse": force_reparse,
        "connection_id": connection_id,
    }


def get_sync_status(user_id: int) -> dict:
    """
    Get Gmail sync status for a user.

    Args:
        user_id: User ID

    Returns:
        Sync status dict with connection details and latest job
    """
    # Get connection for user
    connection = gmail.get_gmail_connection(user_id)
    if not connection:
        return {"connected": False, "message": "No Gmail connection found"}

    return gmail_sync.get_sync_status(connection["id"])


def get_job_status(job_id: int) -> dict:
    """
    Get status of a specific Gmail sync job.

    Args:
        job_id: Job ID to query

    Returns:
        Job dict with status, progress, and results

    Raises:
        ValueError: If job not found
    """
    job = gmail.get_gmail_sync_job(job_id)
    if not job:
        raise ValueError(f"Gmail sync job {job_id} not found")

    return job


def get_connection(user_id: int) -> dict:
    """
    Get Gmail connection for a user.

    Args:
        user_id: User ID

    Returns:
        Connection dict or None
    """
    return gmail.get_gmail_connection(user_id)


def disconnect(user_id: int) -> bool:
    """
    Disconnect Gmail account for a user.

    Args:
        user_id: User ID

    Returns:
        True if disconnected successfully

    Raises:
        ValueError: If no connection found
    """
    connection = gmail.get_gmail_connection(user_id)
    if not connection:
        raise ValueError("No Gmail connection found")

    return gmail.delete_gmail_connection(connection["id"])


def get_statistics(user_id: int) -> dict:
    """
    Get Gmail receipt statistics for a user.

    Args:
        user_id: User ID

    Returns:
        Statistics dict
    """
    return gmail.get_gmail_statistics(user_id)


def get_receipts(
    user_id: int, limit: int = 100, offset: int = 0, parsing_status: str = None
) -> list:
    """
    Get Gmail receipts for a user.

    Args:
        user_id: User ID
        limit: Max receipts to return
        offset: Pagination offset
        parsing_status: Filter by status ('parsed', 'pending', 'failed')

    Returns:
        List of receipt dicts
    """
    # Get connection for user
    connection = get_connection(user_id)
    if not connection:
        return []

    return gmail.get_gmail_receipts(
        connection_id=connection["id"],
        limit=limit,
        offset=offset,
        status=parsing_status,
    )


def get_receipt_by_id(receipt_id: int) -> dict:
    """
    Get a specific Gmail receipt.

    Args:
        receipt_id: Receipt ID

    Returns:
        Receipt dict or None
    """
    return gmail.get_gmail_receipt_by_id(receipt_id)


def delete_receipt(receipt_id: int) -> bool:
    """
    Soft delete a Gmail receipt.

    Args:
        receipt_id: Receipt ID

    Returns:
        True if deleted successfully
    """
    return gmail.soft_delete_gmail_receipt(receipt_id)


def get_matches(user_id: int = 1) -> list:
    """
    Get all Gmail-to-transaction matches.

    Args:
        user_id: User ID

    Returns:
        List of match dicts
    """
    return gmail.get_gmail_matches(user_id)


def confirm_match(match_id: int) -> bool:
    """
    Confirm a Gmail receipt match.

    Args:
        match_id: Match ID

    Returns:
        True if confirmed successfully
    """
    return gmail.confirm_gmail_match(match_id)


def delete_match(match_id: int) -> bool:
    """
    Delete a Gmail receipt match.

    Args:
        match_id: Match ID

    Returns:
        True if deleted successfully
    """
    return gmail.delete_gmail_match(match_id)


def get_merchants(user_id: int = 1) -> dict:
    """
    Get merchant summary from Gmail receipts.

    Args:
        user_id: User ID

    Returns:
        Dictionary with 'merchants' list and 'summary' stats
    """
    return gmail.get_gmail_merchants_summary(user_id)


def get_merchant_receipts(
    merchant_identifier: str, user_id: int = 1, limit: int = 50, offset: int = 0
) -> dict:
    """
    Get receipts for a specific merchant.

    Args:
        merchant_identifier: Merchant domain or normalized name
        user_id: User ID
        limit: Max receipts to return
        offset: Pagination offset

    Returns:
        Dictionary with 'receipts' list and 'total' count
    """
    # Auto-detect if identifier is a domain (contains '.') or normalized name
    if "." in merchant_identifier:
        return gmail.get_receipts_by_domain(
            merchant_domain=merchant_identifier,
            user_id=user_id,
            limit=limit,
            offset=offset,
        )
    return gmail.get_receipts_by_domain(
        merchant_normalized=merchant_identifier,
        user_id=user_id,
        limit=limit,
        offset=offset,
    )


def get_sender_patterns(user_id: int = 1) -> list:
    """
    Get sender email patterns from Gmail receipts.

    Args:
        user_id: User ID

    Returns:
        List of sender pattern dicts
    """
    return gmail.get_gmail_sender_patterns_list(user_id)


def get_llm_queue(limit: int = 50) -> dict:
    """
    Get receipts in the LLM processing queue.

    Args:
        limit: Max receipts to return

    Returns:
        LLM queue summary dict
    """
    return gmail.get_llm_queue_summary(limit=limit)
