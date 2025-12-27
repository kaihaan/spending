"""
Smart Default Values

Provides intelligent default values for MCP tool parameters:
- Date ranges (relative to today)
- User IDs
- Batch sizes
- Sync types

Goal: 90% of tool calls should work with defaults (no parameters needed)
"""

from datetime import datetime, timedelta

from ..config import config


def get_default_user_id() -> int:
    """
    Get default user ID.

    Returns:
        Default user ID from config
    """
    return config.DEFAULT_USER_ID


def get_default_date_range(days_back: int | None = None) -> tuple[str, str]:
    """
    Get default date range for sync operations.

    Args:
        days_back: Number of days to go back from today (defaults to config value)

    Returns:
        (date_from, date_to) as ISO date strings (YYYY-MM-DD)

    Example:
        >>> get_default_date_range(30)
        ('2024-11-27', '2025-12-27')
    """
    if days_back is None:
        days_back = config.DEFAULT_DATE_RANGE_DAYS

    today = datetime.now().date()
    date_from = (today - timedelta(days=days_back)).isoformat()
    date_to = today.isoformat()

    return date_from, date_to


def get_default_batch_size() -> int:
    """
    Get default batch size for LLM enrichment.

    Returns:
        Default batch size from config
    """
    return config.DEFAULT_BATCH_SIZE


def get_default_poll_interval() -> int:
    """
    Get default poll interval for async job status checks.

    Returns:
        Poll interval in seconds
    """
    return config.DEFAULT_POLL_INTERVAL


def get_default_job_timeout() -> int:
    """
    Get default timeout for async jobs.

    Returns:
        Timeout in seconds
    """
    return config.DEFAULT_JOB_TIMEOUT


def get_default_gmail_sync_type() -> str:
    """
    Get default Gmail sync type.

    Returns:
        'auto', 'full', or 'incremental'
    """
    return config.DEFAULT_GMAIL_SYNC_TYPE


def get_default_staleness_threshold() -> int:
    """
    Get default staleness threshold for source coverage warnings.

    Returns:
        Threshold in days
    """
    return config.STALENESS_THRESHOLD_DAYS


def apply_date_range_defaults(
    date_from: str | None = None,
    date_to: str | None = None,
    days_back: int | None = None,
) -> tuple[str, str]:
    """
    Apply smart defaults to date range parameters.

    If both date_from and date_to are provided, use them as-is.
    If neither is provided, generate default range.
    If only one is provided, infer the other.

    Args:
        date_from: Start date (ISO format YYYY-MM-DD)
        date_to: End date (ISO format YYYY-MM-DD)
        days_back: Number of days back for default range

    Returns:
        (date_from, date_to) as ISO date strings

    Examples:
        >>> apply_date_range_defaults(None, None)
        ('2024-11-27', '2025-12-27')  # Default 30-day range

        >>> apply_date_range_defaults('2024-12-01', None)
        ('2024-12-01', '2025-12-27')  # Use provided start, default end to today

        >>> apply_date_range_defaults(None, '2024-12-31')
        ('2024-12-01', '2024-12-31')  # Use provided end, default start to 30 days before

        >>> apply_date_range_defaults('2024-12-01', '2024-12-31')
        ('2024-12-01', '2024-12-31')  # Use both as-is
    """
    # Both provided - use as-is
    if date_from and date_to:
        return date_from, date_to

    # Neither provided - generate default range
    if not date_from and not date_to:
        return get_default_date_range(days_back)

    # Only date_from provided - default date_to to today
    if date_from and not date_to:
        today = datetime.now().date()
        return date_from, today.isoformat()

    # Only date_to provided - default date_from to N days before date_to
    if date_to and not date_from:
        if days_back is None:
            days_back = config.DEFAULT_DATE_RANGE_DAYS

        to_date = datetime.fromisoformat(date_to).date()
        from_date = to_date - timedelta(days=days_back)
        return from_date.isoformat(), date_to

    # Fallback (shouldn't reach here)
    return get_default_date_range(days_back)


def apply_user_id_default(user_id: int | None = None) -> int:
    """
    Apply default user ID if not provided.

    Args:
        user_id: User ID or None

    Returns:
        User ID (provided or default)
    """
    return user_id if user_id is not None else get_default_user_id()


def apply_batch_size_default(batch_size: int | None = None) -> int:
    """
    Apply default batch size if not provided.

    Args:
        batch_size: Batch size or None

    Returns:
        Batch size (provided or default)
    """
    return batch_size if batch_size is not None else get_default_batch_size()
