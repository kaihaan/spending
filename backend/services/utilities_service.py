"""
Utilities Service - System Utilities and Testing

Provides utility operations for:
- Cache statistics and management
- Pre-enrichment status tracking
- Active job monitoring
- Testing data cleanup
- Storage status monitoring
- Enrichment source details

These are helper endpoints for development, testing, and system monitoring.
"""

import cache_manager

import database
from database import base
from database import enrichment as db_enrichment
from database import gmail as db_gmail
from database import pdf as db_pdf
from mcp.minio_client import (
    get_storage_stats as minio_get_storage_stats,
)
from mcp.minio_client import (
    is_available as minio_is_available,
)

# ============================================================================
# Cache Statistics
# ============================================================================


def get_cache_stats() -> dict:
    """
    Get Redis cache statistics.

    Returns:
        Dict with cache hit/miss ratios, key counts, memory usage, etc.
    """
    return cache_manager.get_cache_stats()


# ============================================================================
# Pre-Enrichment Status Tracking
# ============================================================================


def get_pre_enrichment_summary() -> dict:
    """
    Get summary of identified transactions by vendor.

    'Identified' means transactions that either:
    1. Match vendor patterns in description
    2. Are linked in vendor match tables

    This ensures: Identified >= Matched is always true.

    Returns:
        Dict with counts: {'Apple': N, 'AMZN': N, 'AMZN RTN': N, 'total': N}
    """
    return database.get_identified_summary()


def backfill_pre_enrichment_status() -> dict:
    """
    Backfill pre_enrichment_status for all existing transactions.

    Analyzes all transactions and sets their status based on:
    1. If already matched (in match tables) → 'Matched'
    2. If description matches patterns → 'Apple', 'AMZN', 'AMZN RTN'
    3. Otherwise → 'None'

    This is useful when:
    - New pattern detection logic is added
    - Historical data needs status recalculation
    - Database is migrated or restored

    Returns:
        Dict with counts of each status assigned
    """
    counts = database.backfill_pre_enrichment_status()

    # Invalidate transaction cache after backfill
    cache_manager.cache_invalidate_transactions()

    return counts


# ============================================================================
# Active Job Monitoring
# ============================================================================


def get_active_jobs(user_id: int = 1) -> dict:
    """
    Get all active Pre-AI jobs for the current user.

    Returns any running Gmail sync jobs and matching jobs.
    Used by frontend to resume progress tracking after navigation.

    Auto-cleans up stale jobs (stuck > 30 min) before returning.

    Args:
        user_id: User ID to check jobs for

    Returns:
        Dict with 'gmail_sync' and 'matching' job lists
    """
    # Auto-cleanup stale jobs before checking active ones
    cleanup_result = db_gmail.cleanup_stale_matching_jobs(stale_threshold_minutes=30)

    if cleanup_result["cleaned_up"] > 0:
        print(
            f"🧹 Auto-cleaned {cleanup_result['cleaned_up']} stale matching jobs: {cleanup_result['job_ids']}"
        )

    # Get active Gmail sync job
    gmail_job = db_gmail.get_latest_active_gmail_sync_job(user_id)

    # Get active matching jobs
    matching_jobs = db_gmail.get_active_matching_jobs(user_id)

    return {"gmail_sync": gmail_job, "matching": matching_jobs}


# ============================================================================
# Testing Data Cleanup
# ============================================================================


def clear_testing_data(data_types: list[str]) -> dict:
    """
    Clear selected data types for testing purposes.

    DANGER: This permanently deletes data from the database.
    Use with extreme caution - primarily for development/testing.

    Allowed types:
    - truelayer_transactions
    - amazon_orders
    - truelayer_amazon_matches
    - apple_transactions
    - truelayer_apple_matches
    - enrichment_cache
    - import_history
    - category_rules
    - gmail_receipts
    - gmail_email_content
    - gmail_sync_jobs
    - gmail_transaction_matches

    Args:
        data_types: List of data type names to clear

    Returns:
        Dict with success status and cleared counts per data type

    Raises:
        ValueError: If invalid data type provided or no types specified
    """
    if not data_types:
        raise ValueError("No data types specified. At least one type must be selected.")

    # Define allowed types and their corresponding tables
    allowed_types = {
        "truelayer_transactions": "DELETE FROM truelayer_transactions",
        "amazon_orders": "DELETE FROM amazon_orders",
        "truelayer_amazon_matches": "DELETE FROM truelayer_amazon_transaction_matches",
        "apple_transactions": "DELETE FROM apple_transactions",
        "truelayer_apple_matches": "DELETE FROM truelayer_apple_transaction_matches",
        "enrichment_cache": "DELETE FROM llm_enrichment_cache",
        "import_history": "DELETE FROM truelayer_import_jobs",
        "category_rules": "DELETE FROM category_keywords",
        "gmail_receipts": "DELETE FROM gmail_receipts",
        "gmail_email_content": "DELETE FROM gmail_email_content",
        "gmail_sync_jobs": "DELETE FROM gmail_sync_jobs",
        "gmail_transaction_matches": "DELETE FROM gmail_transaction_matches",
    }

    # Validate types
    invalid_types = [t for t in data_types if t not in allowed_types]
    if invalid_types:
        raise ValueError(
            f"Invalid data type: {invalid_types[0]}. "
            f"Allowed types: {', '.join(allowed_types.keys())}"
        )

    # Execute clearing operations with fail-fast behavior
    cleared_counts = dict.fromkeys(allowed_types.keys(), 0)

    from sqlalchemy import text

    with base.get_session() as session:
        for data_type in data_types:
            try:
                delete_sql = allowed_types[data_type]
                result = session.execute(text(delete_sql))
                row_count = result.rowcount
                cleared_counts[data_type] = row_count
                session.commit()

            except Exception as e:
                # Fail-fast: stop on first error
                session.rollback()
                raise ValueError(f"Failed to clear {data_type}: {str(e)}") from e

    # Invalidate caches after clearing data
    cache_manager.cache_invalidate_transactions()

    return {"success": True, "cleared": cleared_counts}


# ============================================================================
# Storage Status Monitoring
# ============================================================================


def get_storage_status() -> dict:
    """
    Get MinIO storage status and statistics.

    Returns:
        Dict with:
        - minio_available: bool
        - database_stats: PDF attachment counts
        - minio_stats: Storage metrics (if available)
    """
    available = minio_is_available()
    db_stats = db_pdf.get_pdf_storage_stats()

    result = {"minio_available": available, "database_stats": db_stats}

    if available:
        minio_stats = minio_get_storage_stats()
        result["minio_stats"] = minio_stats

    return result


# ============================================================================
# Enrichment Source Details
# ============================================================================


def get_enrichment_source_details(source_id: int) -> dict:
    """
    Fetch full details from the source table for an enrichment source.

    Returns the enrichment source metadata plus complete data from the
    appropriate source table (amazon_orders, apple_transactions, gmail_receipts, etc.)
    based on the source_type.

    Args:
        source_id: Enrichment source ID

    Returns:
        Dict with enrichment source metadata and full source details

    Raises:
        ValueError: If enrichment source not found
    """
    result = db_enrichment.get_enrichment_source_full_details(source_id)

    if not result:
        raise ValueError("Enrichment source not found")

    # Format dates for JSON serialization
    def format_dates(obj):
        if isinstance(obj, dict):
            return {k: format_dates(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [format_dates(item) for item in obj]
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return obj

    return format_dates(result)
