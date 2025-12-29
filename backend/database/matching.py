"""
Transaction Matching - Database Operations

Handles consistency checking and matching logic across different transaction sources.

Migrated to SQLAlchemy from psycopg2.
"""

from datetime import timedelta

from sqlalchemy import Date, func, text
from sqlalchemy.dialects.postgresql import insert

from .base import get_session
from .models.amazon import AmazonOrder
from .models.apple import AppleTransaction
from .models.category import CategoryRule, MatchingJob, MerchantNormalization
from .models.gmail import GmailConnection, GmailReceipt
from .models.truelayer import TrueLayerTransaction

# ============================================================================
# SOURCE COVERAGE & STALENESS DETECTION
# ============================================================================


def get_source_coverage_dates(user_id: int = 1) -> dict:
    """
    Get the max date coverage for each enrichment source vs bank transactions.

    Used to detect when source data is stale (bank transactions are newer
    than the last synced source data).

    Args:
        user_id: User ID to check coverage for

    Returns:
        dict with date ranges and list of stale sources needing refresh
    """
    with get_session() as session:
        # Get max bank transaction date
        bank_result = session.query(
            func.max(TrueLayerTransaction.timestamp.cast(Date)).label("max_date"),
            func.min(TrueLayerTransaction.timestamp.cast(Date)).label("min_date"),
            func.count().label("count"),
        ).first()

        bank_max = bank_result.max_date if bank_result else None
        bank_min = bank_result.min_date if bank_result else None
        bank_count = bank_result.count if bank_result else 0

        # Get max Amazon order date
        amazon_result = session.query(
            func.max(AmazonOrder.order_date).label("max_date"),
            func.min(AmazonOrder.order_date).label("min_date"),
            func.count().label("count"),
        ).first()

        amazon_max = amazon_result.max_date if amazon_result else None
        amazon_min = amazon_result.min_date if amazon_result else None
        amazon_count = amazon_result.count if amazon_result else 0

        # Get max Apple transaction date
        apple_result = session.query(
            func.max(AppleTransaction.order_date).label("max_date"),
            func.min(AppleTransaction.order_date).label("min_date"),
            func.count().label("count"),
        ).first()

        apple_max = apple_result.max_date if apple_result else None
        apple_min = apple_result.min_date if apple_result else None
        apple_count = apple_result.count if apple_result else 0

        # Get max Gmail receipt date
        gmail_result = (
            session.query(
                func.max(GmailReceipt.receipt_date).label("max_date"),
                func.min(GmailReceipt.receipt_date).label("min_date"),
                func.count().label("count"),
            )
            .join(GmailConnection, GmailReceipt.connection_id == GmailConnection.id)
            .filter(
                GmailConnection.user_id == user_id,
                GmailReceipt.deleted_at.is_(None),
            )
            .first()
        )

        gmail_max = gmail_result.max_date if gmail_result else None
        gmail_min = gmail_result.min_date if gmail_result else None
        gmail_count = gmail_result.count if gmail_result else 0

        # Determine which sources are stale (> 7 days behind bank data)
        stale_sources = []
        stale_threshold_days = 7

        if bank_max:
            threshold_date = bank_max - timedelta(days=stale_threshold_days)

            if amazon_count > 0 and amazon_max and amazon_max < threshold_date:
                stale_sources.append("amazon")
            if apple_count > 0 and apple_max and apple_max < threshold_date:
                stale_sources.append("apple")
            if gmail_count > 0 and gmail_max and gmail_max < threshold_date:
                stale_sources.append("gmail")

        # Convert dates to strings for JSON serialization
        def date_to_str(d):
            return d.isoformat() if d else None

        return {
            "bank_transactions": {
                "max_date": date_to_str(bank_max),
                "min_date": date_to_str(bank_min),
                "count": bank_count,
            },
            "amazon": {
                "max_date": date_to_str(amazon_max),
                "min_date": date_to_str(amazon_min),
                "count": amazon_count,
                "is_stale": "amazon" in stale_sources,
            },
            "apple": {
                "max_date": date_to_str(apple_max),
                "min_date": date_to_str(apple_min),
                "count": apple_count,
                "is_stale": "apple" in stale_sources,
            },
            "gmail": {
                "max_date": date_to_str(gmail_max),
                "min_date": date_to_str(gmail_min),
                "count": gmail_count,
                "is_stale": "gmail" in stale_sources,
            },
            "stale_sources": stale_sources,
            "stale_threshold_days": stale_threshold_days,
        }


# ============================================================================
# CONSISTENCY ENGINE FUNCTIONS
# ============================================================================


def get_category_rules(active_only: bool = True) -> list:
    """Fetch category rules sorted by priority (highest first).

    Args:
        active_only: If True, only return active rules

    Returns:
        List of rule dictionaries
    """
    with get_session() as session:
        query = session.query(CategoryRule)

        if active_only:
            query = query.filter(CategoryRule.is_active == True)  # noqa: E712

        rules = query.order_by(CategoryRule.priority.desc(), CategoryRule.id).all()

        return [
            {
                "id": rule.id,
                "rule_name": rule.rule_name,
                "transaction_type": rule.transaction_type,
                "description_pattern": rule.description_pattern,
                "pattern_type": rule.pattern_type,
                "category": rule.category,
                "subcategory": rule.subcategory,
                "priority": rule.priority,
                "is_active": rule.is_active,
                "source": rule.source,
                "usage_count": rule.usage_count,
                "created_at": rule.created_at,
            }
            for rule in rules
        ]


def get_merchant_normalizations() -> list:
    """Fetch merchant normalizations sorted by priority (highest first).

    Returns:
        List of normalization dictionaries
    """
    with get_session() as session:
        normalizations = session.query(MerchantNormalization).order_by(
            MerchantNormalization.priority.desc(), MerchantNormalization.id
        )

        return [
            {
                "id": norm.id,
                "pattern": norm.pattern,
                "pattern_type": norm.pattern_type,
                "normalized_name": norm.normalized_name,
                "merchant_type": norm.merchant_type,
                "default_category": norm.default_category,
                "priority": norm.priority,
                "source": norm.source,
                "usage_count": norm.usage_count,
                "created_at": norm.created_at,
                "updated_at": norm.updated_at,
            }
            for norm in normalizations
        ]


def increment_rule_usage(rule_id: int) -> bool:
    """Increment usage count for a category rule.

    Args:
        rule_id: ID of the rule to update

    Returns:
        True if updated successfully
    """
    with get_session() as session:
        rule = session.get(CategoryRule, rule_id)
        if rule:
            rule.usage_count += 1
            session.commit()
            return True
        return False


def increment_merchant_normalization_usage(normalization_id: int) -> bool:
    """Increment usage count for a merchant normalization.

    Args:
        normalization_id: ID of the normalization to update

    Returns:
        True if updated successfully
    """
    with get_session() as session:
        norm = session.get(MerchantNormalization, normalization_id)
        if norm:
            norm.usage_count += 1
            norm.updated_at = func.now()
            session.commit()
            return True
        return False


def add_category_rule(
    rule_name: str,
    description_pattern: str,
    category: str,
    transaction_type: str = None,
    subcategory: str = None,
    pattern_type: str = "contains",
    priority: int = 0,
    source: str = "manual",
) -> int:
    """Add a new category rule.

    Args:
        rule_name: Human-readable name for the rule
        description_pattern: Pattern to match in description
        category: Category to assign
        transaction_type: 'CREDIT', 'DEBIT', or None (both)
        subcategory: Optional subcategory
        pattern_type: 'contains', 'starts_with', 'exact', 'regex'
        priority: Higher = checked first
        source: 'manual', 'learned', 'llm'

    Returns:
        ID of the created rule
    """
    with get_session() as session:
        rule = CategoryRule(
            rule_name=rule_name,
            transaction_type=transaction_type,
            description_pattern=description_pattern,
            pattern_type=pattern_type,
            category=category,
            subcategory=subcategory,
            priority=priority,
            source=source,
        )
        session.add(rule)
        session.commit()
        return rule.id


def add_merchant_normalization(
    pattern: str,
    normalized_name: str,
    merchant_type: str = None,
    default_category: str = None,
    pattern_type: str = "contains",
    priority: int = 0,
    source: str = "manual",
) -> int:
    """Add a new merchant normalization.

    Args:
        pattern: Pattern to match in description
        normalized_name: Standardized merchant name
        merchant_type: Type (e.g., 'bakery', 'supermarket')
        default_category: Default category if matched
        pattern_type: 'contains', 'starts_with', 'exact', 'regex'
        priority: Higher = checked first
        source: 'manual', 'learned', 'llm'

    Returns:
        ID of the created normalization
    """
    with get_session() as session:
        stmt = (
            insert(MerchantNormalization)
            .values(
                pattern=pattern,
                pattern_type=pattern_type,
                normalized_name=normalized_name,
                merchant_type=merchant_type,
                default_category=default_category,
                priority=priority,
                source=source,
            )
            .on_conflict_do_update(
                index_elements=["pattern", "pattern_type"],
                set_={
                    "normalized_name": normalized_name,
                    "merchant_type": merchant_type,
                    "default_category": default_category,
                    "priority": priority,
                    "updated_at": func.now(),
                },
            )
            .returning(MerchantNormalization.id)
        )

        result = session.execute(stmt)
        norm_id = result.scalar_one()
        session.commit()
        return norm_id


def delete_category_rule(rule_id: int) -> bool:
    """Delete a category rule.

    Args:
        rule_id: ID of the rule to delete

    Returns:
        True if deleted successfully
    """
    with get_session() as session:
        rule = session.get(CategoryRule, rule_id)
        if rule:
            session.delete(rule)
            session.commit()
            return True
        return False


def delete_merchant_normalization(normalization_id: int) -> bool:
    """Delete a merchant normalization.

    Args:
        normalization_id: ID of the normalization to delete

    Returns:
        True if deleted successfully
    """
    with get_session() as session:
        norm = session.get(MerchantNormalization, normalization_id)
        if norm:
            session.delete(norm)
            session.commit()
            return True
        return False


def update_category_rule(rule_id: int, **kwargs) -> bool:
    """Update a category rule.

    Args:
        rule_id: ID of the rule to update
        **kwargs: Fields to update (rule_name, description_pattern, category, etc.)

    Returns:
        True if updated successfully
    """
    allowed_fields = {
        "rule_name",
        "transaction_type",
        "description_pattern",
        "pattern_type",
        "category",
        "subcategory",
        "priority",
        "is_active",
        "source",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return False

    with get_session() as session:
        rule = session.get(CategoryRule, rule_id)
        if not rule:
            return False

        for key, value in updates.items():
            setattr(rule, key, value)

        session.commit()
        return True


def update_merchant_normalization(normalization_id: int, **kwargs) -> bool:
    """Update a merchant normalization.

    Args:
        normalization_id: ID of the normalization to update
        **kwargs: Fields to update (pattern, normalized_name, etc.)

    Returns:
        True if updated successfully
    """
    allowed_fields = {
        "pattern",
        "pattern_type",
        "normalized_name",
        "merchant_type",
        "default_category",
        "priority",
        "source",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return False

    with get_session() as session:
        norm = session.get(MerchantNormalization, normalization_id)
        if not norm:
            return False

        for key, value in updates.items():
            setattr(norm, key, value)

        norm.updated_at = func.now()
        session.commit()
        return True


# ============================================================================
# MATCHING JOB TRACKING
# ============================================================================


def create_matching_job(user_id: int, job_type: str, celery_task_id: str = None) -> int:
    """
    Create a new matching job entry.

    Args:
        user_id: User ID
        job_type: Type of matching job ('amazon', 'apple', 'returns', 'gmail')
        celery_task_id: Optional Celery task ID

    Returns:
        Job ID
    """
    with get_session() as session:
        job = MatchingJob(
            user_id=user_id, job_type=job_type, celery_task_id=celery_task_id
        )
        session.add(job)
        session.commit()
        return job.id


def update_matching_job_status(
    job_id: int, status: str, error_message: str = None
) -> bool:
    """
    Update matching job status.

    Args:
        job_id: Job ID
        status: New status ('queued', 'running', 'completed', 'failed')
        error_message: Optional error message for failed jobs

    Returns:
        True if updated successfully
    """
    with get_session() as session:
        job = session.get(MatchingJob, job_id)
        if not job:
            return False

        job.status = status

        if status == "running":
            job.started_at = func.now()
        elif status in ("completed", "failed"):
            job.completed_at = func.now()
            if error_message:
                job.error_message = error_message

        session.commit()
        return True


def update_matching_job_progress(
    job_id: int,
    total_items: int = None,
    processed_items: int = None,
    matched_items: int = None,
    failed_items: int = None,
) -> bool:
    """
    Update matching job progress counters.

    Args:
        job_id: Job ID
        total_items: Total items to process
        processed_items: Items processed so far
        matched_items: Items successfully matched
        failed_items: Items that failed

    Returns:
        True if updated successfully
    """
    with get_session() as session:
        job = session.get(MatchingJob, job_id)
        if not job:
            return False

        if total_items is not None:
            job.total_items = total_items
        if processed_items is not None:
            job.processed_items = processed_items
        if matched_items is not None:
            job.matched_items = matched_items
        # Note: failed_items column doesn't exist in MatchingJob model
        # Ignoring for API compatibility

        session.commit()
        return True


def get_matching_job(job_id: int) -> dict:
    """
    Get matching job by ID.

    Args:
        job_id: Job ID

    Returns:
        Job dictionary or None
    """
    with get_session() as session:
        job = session.get(MatchingJob, job_id)
        if not job:
            return None

        # Calculate progress percentage
        total = job.total_items or 0
        processed = job.processed_items or 0
        progress_percentage = round((processed / total * 100) if total > 0 else 0)

        return {
            "id": job.id,
            "user_id": job.user_id,
            "job_type": job.job_type,
            "celery_task_id": job.celery_task_id,
            "status": job.status,
            "total_items": job.total_items,
            "processed_items": job.processed_items,
            "matched_items": job.matched_items,
            "failed_items": None,  # Not in model
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
            "created_at": job.created_at,
            "progress_percentage": progress_percentage,
        }


def get_active_matching_jobs(user_id: int) -> list:
    """
    Get all active (queued/running) matching jobs for a user.

    Args:
        user_id: User ID

    Returns:
        List of active job dictionaries
    """
    with get_session() as session:
        jobs = (
            session.query(MatchingJob)
            .filter(
                MatchingJob.user_id == user_id,
                MatchingJob.status.in_(["queued", "running"]),
            )
            .order_by(MatchingJob.created_at.desc())
            .all()
        )

        results = []
        for job in jobs:
            total = job.total_items or 0
            processed = job.processed_items or 0
            progress_percentage = round((processed / total * 100) if total > 0 else 0)

            results.append(
                {
                    "id": job.id,
                    "user_id": job.user_id,
                    "job_type": job.job_type,
                    "celery_task_id": job.celery_task_id,
                    "status": job.status,
                    "total_items": job.total_items,
                    "processed_items": job.processed_items,
                    "matched_items": job.matched_items,
                    "failed_items": None,  # Not in model
                    "error_message": job.error_message,
                    "started_at": job.started_at,
                    "completed_at": job.completed_at,
                    "created_at": job.created_at,
                    "progress_percentage": progress_percentage,
                }
            )

        return results


def cleanup_stale_matching_jobs(stale_threshold_minutes: int = 30) -> dict:
    """
    Mark stale matching jobs as failed.

    A job is considered stale if:
    - status='queued' and created_at > threshold (task never started)
    - status='running' and started_at > threshold (task hung)

    Args:
        stale_threshold_minutes: Minutes after which a job is considered stale

    Returns:
        {'cleaned_up': count, 'job_ids': [...]}
    """
    with get_session() as session:
        # Find stale jobs using SQLAlchemy text for INTERVAL support
        stale_jobs = session.execute(
            text(
                """
                SELECT id, job_type, status, created_at, started_at
                FROM matching_jobs
                WHERE status IN ('queued', 'running')
                  AND (
                    (status = 'queued' AND created_at < NOW() - INTERVAL :interval1)
                    OR
                    (status = 'running' AND started_at < NOW() - INTERVAL :interval2)
                  )
            """
            ),
            {
                "interval1": f"{stale_threshold_minutes} minutes",
                "interval2": f"{stale_threshold_minutes} minutes",
            },
        ).fetchall()

        if not stale_jobs:
            return {"cleaned_up": 0, "job_ids": []}

        job_ids = [job.id for job in stale_jobs]

        # Mark as failed
        session.query(MatchingJob).filter(MatchingJob.id.in_(job_ids)).update(
            {
                "status": "failed",
                "error_message": "Job stalled - automatically cleaned up after timeout",
                "completed_at": func.now(),
            },
            synchronize_session=False,
        )

        session.commit()

        return {"cleaned_up": len(job_ids), "job_ids": job_ids}
