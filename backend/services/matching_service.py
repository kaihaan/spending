"""
Matching Service - Business Logic

Orchestrates cross-source transaction matching including:
- Unified matching across Amazon, Apple, and Gmail receipts
- Job tracking and status monitoring
- Source coverage analysis (detecting stale data)
- Stale job cleanup

Matching Context:
Links bank transactions to purchase receipts from multiple sources
(Amazon orders, Apple purchases, Gmail receipts) to enrich transaction
data with detailed line items, merchant info, and accurate categorization.

Separates business logic from HTTP routing concerns.
"""

from database import (
    cleanup_stale_matching_jobs,
    get_matching_job,
)
from database import (
    matching as db_matching,
)

# ============================================================================
# Matching Job Operations
# ============================================================================


def get_job_status(job_id: int) -> dict:
    """
    Get status of a specific matching job.

    Args:
        job_id: Job ID to query

    Returns:
        Job dict with status, progress, and results

    Raises:
        ValueError: If job not found
    """
    job = get_matching_job(job_id)

    if not job:
        raise ValueError("Job not found")

    return job


def cleanup_stale_jobs(threshold_minutes: int = 30) -> dict:
    """
    Cleanup stale matching jobs older than threshold.

    Marks jobs stuck in 'queued' or 'running' status as 'failed'.
    Useful for recovering from worker crashes or network issues.

    Args:
        threshold_minutes: Age threshold in minutes (default: 30)

    Returns:
        Dict with cleaned_up count and job_ids list
    """
    result = cleanup_stale_matching_jobs(stale_threshold_minutes=threshold_minutes)

    return {
        "success": True,
        "cleaned_up": result["cleaned_up"],
        "job_ids": result["job_ids"],
    }


# ============================================================================
# Source Coverage & Staleness Detection
# ============================================================================


def get_coverage(user_id: int = 1) -> dict:
    """
    Get source coverage dates to detect stale data.

    Returns date ranges for each source and flags which ones are stale
    (more than 7 days behind bank transaction data).

    Args:
        user_id: User ID to check coverage for

    Returns:
        Coverage dict with:
        - bank_transactions: Max date and count
        - amazon: Max date, count, and is_stale flag
        - apple: Max date, count, and is_stale flag
        - gmail: Max date, count, and is_stale flag
        - stale_sources: List of stale source names
        - stale_threshold_days: Staleness threshold (7 days)
    """
    coverage = db_matching.get_source_coverage_dates(user_id)
    return coverage


# ============================================================================
# Unified Matching
# ============================================================================


def run_unified_matching(
    user_id: int = 1, sources: list = None, sync_first: bool = False
) -> dict:
    """
    Run unified matching across all sources in parallel.

    Launches a Celery task that runs matching for Amazon, Apple, and Gmail
    simultaneously. Optionally syncs source data before matching.

    Args:
        user_id: User ID for matching
        sources: List of sources to match (default: ['amazon', 'apple', 'gmail'])
        sync_first: Whether to sync source data before matching (default: False)

    Returns:
        Dict with job_id, status, sources, and optional stale warning

    Raises:
        ImportError: If unified matching task not implemented
    """
    if sources is None:
        sources = ["amazon", "apple", "gmail"]

    # Check source coverage first
    coverage = db_matching.get_source_coverage_dates(user_id)
    stale_warning = None
    if coverage.get("stale_sources"):
        stale_warning = {
            "stale_sources": coverage["stale_sources"],
            "bank_max_date": coverage["bank_transactions"]["max_date"],
            "sources": {
                source: coverage[source] for source in coverage["stale_sources"]
            },
        }

    # Import and launch Celery task
    try:
        from tasks.matching_tasks import unified_matching_task

        task = unified_matching_task.delay(user_id, sources, sync_first)

        return {
            "job_id": task.id,
            "status": "running",
            "sources": sources,
            "sync_sources_first": sync_first,
            "source_coverage_warning": stale_warning,
        }

    except ImportError:
        # Fallback if Celery task not yet implemented
        raise ImportError(
            "Unified matching task not yet implemented. "
            "Run individual matchers via /api/amazon/match, /api/apple/match, /api/gmail/match"
        )
