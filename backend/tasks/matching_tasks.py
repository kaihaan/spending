"""Celery tasks for Pre-AI matching operations.

These tasks handle async matching of:
- Amazon orders to bank transactions
- Amazon returns to transactions
- Apple purchases to bank transactions
- Gmail receipts to bank transactions
- Unified matching across all sources
"""

from datetime import datetime

from celery import group
from celery_app import celery_app

import database as db


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def match_amazon_orders_task(self, job_id: int, user_id: int = 1):
    """
    Celery task to match Amazon orders to TrueLayer transactions.

    Args:
        job_id: Pre-created matching job ID for progress tracking
        user_id: User ID (default 1)

    Returns:
        dict: Matching statistics
    """
    try:
        from mcp.amazon_matcher import match_all_amazon_transactions

        # Update job to running status
        db.update_matching_job_status(job_id, "running")

        self.update_state(
            state="STARTED",
            meta={"status": "running", "job_id": job_id, "job_type": "amazon"},
        )

        # Run the matching
        result = match_all_amazon_transactions()

        # Update job with results
        db.update_matching_job_progress(
            job_id=job_id,
            total_items=result.get("total_processed", 0),
            processed_items=result.get("total_processed", 0),
            matched_items=result.get("matched", 0),
            failed_items=0,
        )

        # Mark as completed
        db.update_matching_job_status(job_id, "completed")

        return {
            "status": "completed",
            "job_id": job_id,
            "stats": {
                "total_processed": result.get("total_processed", 0),
                "matched": result.get("matched", 0),
                "unmatched": result.get("unmatched", 0),
            },
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        # Mark job as failed
        db.update_matching_job_status(job_id, "failed", error_message=str(e))

        return {"status": "failed", "job_id": job_id, "error": str(e)}


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def match_amazon_returns_task(self, job_id: int, user_id: int = 1):
    """
    Celery task to match Amazon returns to transactions.

    Args:
        job_id: Pre-created matching job ID for progress tracking
        user_id: User ID (default 1)

    Returns:
        dict: Matching statistics
    """
    try:
        from mcp.amazon_returns_matcher import match_all_returns

        # Update job to running status
        db.update_matching_job_status(job_id, "running")

        self.update_state(
            state="STARTED",
            meta={"status": "running", "job_id": job_id, "job_type": "returns"},
        )

        # Run the matching
        result = match_all_returns()

        # Update job with results
        db.update_matching_job_progress(
            job_id=job_id,
            total_items=result.get("total_processed", 0),
            processed_items=result.get("total_processed", 0),
            matched_items=result.get("matched", 0),
            failed_items=0,
        )

        # Mark as completed
        db.update_matching_job_status(job_id, "completed")

        return {
            "status": "completed",
            "job_id": job_id,
            "stats": {
                "total_processed": result.get("total_processed", 0),
                "matched": result.get("matched", 0),
                "unmatched": result.get("unmatched", 0),
            },
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        # Mark job as failed
        db.update_matching_job_status(job_id, "failed", error_message=str(e))

        return {"status": "failed", "job_id": job_id, "error": str(e)}


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def match_apple_transactions_task(self, job_id: int, user_id: int = 1):
    """
    Celery task to match Apple purchases to bank transactions.

    Args:
        job_id: Pre-created matching job ID for progress tracking
        user_id: User ID (default 1)

    Returns:
        dict: Matching statistics
    """
    try:
        from mcp.apple_matcher import match_all_apple_transactions

        # Update job to running status
        db.update_matching_job_status(job_id, "running")

        self.update_state(
            state="STARTED",
            meta={"status": "running", "job_id": job_id, "job_type": "apple"},
        )

        # Run the matching
        result = match_all_apple_transactions()

        # Update job with results
        db.update_matching_job_progress(
            job_id=job_id,
            total_items=result.get("total_processed", 0),
            processed_items=result.get("total_processed", 0),
            matched_items=result.get("matched", 0),
            failed_items=0,
        )

        # Mark as completed
        db.update_matching_job_status(job_id, "completed")

        return {
            "status": "completed",
            "job_id": job_id,
            "stats": {
                "total_processed": result.get("total_processed", 0),
                "matched": result.get("matched", 0),
                "unmatched": result.get("unmatched", 0),
            },
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        # Mark job as failed
        db.update_matching_job_status(job_id, "failed", error_message=str(e))

        return {"status": "failed", "job_id": job_id, "error": str(e)}


@celery_app.task(bind=True, time_limit=600, soft_time_limit=550)
def match_gmail_receipts_task(self, job_id: int, user_id: int = 1):
    """
    Celery task to match Gmail receipts to bank transactions.

    Args:
        job_id: Pre-created matching job ID for progress tracking
        user_id: User ID (default 1)

    Returns:
        dict: Matching statistics
    """
    try:
        from mcp.gmail_matcher import match_all_gmail_receipts

        # Update job to running status
        db.update_matching_job_status(job_id, "running")

        self.update_state(
            state="STARTED",
            meta={"status": "running", "job_id": job_id, "job_type": "gmail"},
        )

        # Run the matching
        result = match_all_gmail_receipts(user_id=user_id)

        # Update job with results
        db.update_matching_job_progress(
            job_id=job_id,
            total_items=result.get("total_processed", 0),
            processed_items=result.get("total_processed", 0),
            matched_items=result.get("matched", 0),
            failed_items=0,
        )

        # Mark as completed
        db.update_matching_job_status(job_id, "completed")

        return {
            "status": "completed",
            "job_id": job_id,
            "stats": {
                "total_processed": result.get("total_processed", 0),
                "matched": result.get("matched", 0),
                "suggested": result.get("suggested", 0),
                "unmatched": result.get("unmatched", 0),
            },
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as e:
        # Mark job as failed
        db.update_matching_job_status(job_id, "failed", error_message=str(e))

        return {"status": "failed", "job_id": job_id, "error": str(e)}


@celery_app.task(bind=True, time_limit=1800, soft_time_limit=1700)
def unified_matching_task(self, user_id: int, sources: list, sync_first: bool = False):
    """
    Unified matching task - orchestrates parallel matching across all sources.

    This task launches sub-tasks for each source type in parallel using Celery group,
    waits for all to complete, and aggregates the results.

    Args:
        user_id: User ID for matching
        sources: List of sources to match ['amazon', 'apple', 'gmail']
        sync_first: Whether to sync source data before matching

    Returns:
        dict: Aggregated matching statistics from all sources
    """
    try:
        results = {
            "status": "running",
            "user_id": user_id,
            "sources": sources,
            "sync_first": sync_first,
            "started_at": datetime.now().isoformat(),
            "sub_jobs": {},
            "results": {},
        }

        self.update_state(state="STARTED", meta=results)

        # Step 1: Optional sync of source data
        if sync_first:
            self.update_state(
                state="PROGRESS", meta={**results, "phase": "syncing_sources"}
            )

            # TODO: Implement source syncing
            # For now, skip syncing - it requires more complex orchestration
            # sync_tasks = []
            # if 'amazon' in sources:
            #     sync_tasks.append(sync_amazon_task.s(user_id))
            # if 'gmail' in sources:
            #     sync_tasks.append(sync_gmail_task.s(user_id))
            # if sync_tasks:
            #     sync_group = group(sync_tasks)
            #     sync_group.apply_async().get()

        # Step 2: Create jobs for each source
        self.update_state(state="PROGRESS", meta={**results, "phase": "creating_jobs"})

        job_ids = {}
        for source in sources:
            job_type = f"{source}_matching"
            job = db.create_matching_job(user_id, job_type)
            job_ids[source] = job["id"] if isinstance(job, dict) else job
            results["sub_jobs"][source] = job_ids[source]

        # Step 3: Launch parallel matching tasks
        self.update_state(state="PROGRESS", meta={**results, "phase": "matching"})

        match_tasks = []
        if "amazon" in sources and job_ids.get("amazon"):
            match_tasks.append(match_amazon_orders_task.s(job_ids["amazon"], user_id))
        if "apple" in sources and job_ids.get("apple"):
            match_tasks.append(
                match_apple_transactions_task.s(job_ids["apple"], user_id)
            )
        if "gmail" in sources and job_ids.get("gmail"):
            match_tasks.append(match_gmail_receipts_task.s(job_ids["gmail"], user_id))

        if match_tasks:
            # Run all matching tasks in parallel and wait for completion
            match_group = group(match_tasks)
            group_result = match_group.apply_async()

            # Wait for all tasks to complete (with timeout)
            try:
                task_results = group_result.get(timeout=1500)  # 25 minute timeout

                # Map results back to sources
                result_index = 0
                if "amazon" in sources and job_ids.get("amazon"):
                    results["results"]["amazon"] = task_results[result_index]
                    result_index += 1
                if "apple" in sources and job_ids.get("apple"):
                    results["results"]["apple"] = task_results[result_index]
                    result_index += 1
                if "gmail" in sources and job_ids.get("gmail"):
                    results["results"]["gmail"] = task_results[result_index]
                    result_index += 1

            except Exception as e:
                results["error"] = f"Group execution error: {str(e)}"

        # Step 4: Aggregate results
        total_stats = {
            "total_processed": 0,
            "matched": 0,
            "unmatched": 0,
            "sources_completed": 0,
            "sources_failed": 0,
        }

        for source, source_result in results.get("results", {}).items():
            if source_result.get("status") == "completed":
                total_stats["sources_completed"] += 1
                stats = source_result.get("stats", {})
                total_stats["total_processed"] += stats.get("total_processed", 0)
                total_stats["matched"] += stats.get("matched", 0)
                total_stats["unmatched"] += stats.get("unmatched", 0)
            else:
                total_stats["sources_failed"] += 1

        results["status"] = "completed"
        results["completed_at"] = datetime.now().isoformat()
        results["total_stats"] = total_stats

        return results

    except Exception as e:
        return {
            "status": "failed",
            "user_id": user_id,
            "sources": sources,
            "error": str(e),
            "failed_at": datetime.now().isoformat(),
        }
