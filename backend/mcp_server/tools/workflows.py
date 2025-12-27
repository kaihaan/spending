"""
High-Level Workflow Tools

Provides 5 high-level MCP tools that orchestrate multiple operations:
1. sync_all_sources - Sync all data sources (bank, Gmail, Apple, Amazon)
2. run_full_pipeline - Complete pipeline: sync → parse → match → enrich
3. run_pre_enrichment - Run all matching operations
4. check_sync_status - Get status of all active/recent sync operations
5. get_source_coverage - Check data coverage and staleness

These tools implement common workflows and use smart defaults.
"""

import asyncio
import logging
from datetime import datetime

from ..client.flask_client import FlaskAPIError
from ..server import get_flask_client, mcp
from ..utils.defaults import apply_date_range_defaults, apply_user_id_default
from ..utils.formatters import format_error_response, format_success_response
from ..utils.validators import ValidationError, validate_date_range, validate_user_id

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================


async def wait_for_async_jobs(jobs: list[dict], timeout: int = 300) -> list[dict]:
    """
    Poll job status until all complete or timeout.

    Args:
        jobs: List of job dicts with job_id and type
        timeout: Timeout in seconds

    Returns:
        List of completed job results
    """
    client = get_flask_client()
    start_time = datetime.now()
    results = []

    remaining_jobs = jobs.copy()

    while remaining_jobs:
        # Check timeout
        elapsed = (datetime.now() - start_time).total_seconds()
        if elapsed > timeout:
            logger.warning(
                f"Job timeout after {elapsed}s, {len(remaining_jobs)} jobs still pending"
            )
            break

        # Poll each remaining job
        for job in remaining_jobs[:]:
            try:
                # Get job status (endpoint varies by job type)
                if job["type"] == "gmail_sync":
                    status = client.get(
                        "/api/gmail/sync/status", {"user_id": job.get("user_id", 1)}
                    )
                elif job["type"] == "matching":
                    status = client.get(f"/api/matching/status/{job['job_id']}")
                else:
                    # Generic status check
                    status = client.get(f"/api/jobs/{job['job_id']}/status")

                # Check if complete
                if status.get("status") in ["completed", "failed", "success"]:
                    results.append(status)
                    remaining_jobs.remove(job)
                    logger.info(
                        f"Job {job['job_id']} completed: {status.get('status')}"
                    )

            except Exception as e:
                logger.error(f"Error checking job {job.get('job_id')}: {e}")

        # Wait before next poll
        if remaining_jobs:
            await asyncio.sleep(5)

    return results


# ============================================================================
# Tool 1: sync_all_sources
# ============================================================================


@mcp.tool()
async def sync_all_sources(
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    force_refresh: bool = False,
    skip_matching: bool = False,
) -> dict:
    """
    Sync all available data sources (bank + Gmail + Apple + Amazon).

    This high-level workflow tool syncs all connected data sources in the correct order,
    waits for async jobs to complete, and optionally runs matching operations.

    Args:
        user_id: User ID (default: 1)
        date_from: Start date in ISO format YYYY-MM-DD (default: 30 days ago)
        date_to: End date in ISO format YYYY-MM-DD (default: today)
        force_refresh: Force refresh of existing data (default: false)
        skip_matching: Skip matching operations after sync (default: false)

    Returns:
        Sync results summary with status for each source

    Example:
        sync_all_sources()  # Uses smart defaults
        sync_all_sources(date_from="2024-12-01", date_to="2024-12-31")
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        date_from, date_to = apply_date_range_defaults(date_from, date_to)

        # Validate
        validate_user_id(user_id)
        validate_date_range(date_from, date_to)

        client = get_flask_client()

        logger.info(
            f"Starting sync_all_sources: user={user_id}, dates={date_from} to {date_to}"
        )

        results = {
            "status": "in_progress",
            "sources_synced": [],
            "results": {},
            "date_range": {"from": date_from, "to": date_to},
        }

        async_jobs = []

        # Step 1: Check connections
        try:
            truelayer_conn = client.get(
                "/api/truelayer/connections", {"user_id": user_id}
            )
            gmail_conn = client.get("/api/gmail/connection", {"user_id": user_id})

            logger.info(
                f"Connections - TrueLayer: {bool(truelayer_conn)}, Gmail: {bool(gmail_conn)}"
            )
        except Exception as e:
            logger.warning(f"Failed to check connections: {e}")
            truelayer_conn = None
            gmail_conn = None

        # Step 2: Sync TrueLayer (synchronous)
        if truelayer_conn and len(truelayer_conn) > 0:
            try:
                truelayer_result = client.post(
                    "/api/truelayer/sync", {"user_id": user_id}
                )
                results["sources_synced"].append("truelayer")
                results["results"]["truelayer"] = truelayer_result
                logger.info(
                    f"TrueLayer sync completed: {truelayer_result.get('summary', {})}"
                )
            except FlaskAPIError as e:
                logger.error(f"TrueLayer sync failed: {e}")
                results["results"]["truelayer"] = {"error": str(e), "status": "failed"}
        else:
            results["results"]["truelayer"] = {"status": "not_connected"}

        # Step 3: Sync Gmail (asynchronous)
        if gmail_conn and gmail_conn.get("connected"):
            try:
                gmail_result = client.post(
                    "/api/gmail/sync",
                    {
                        "user_id": user_id,
                        "sync_type": "auto",
                        "from_date": date_from,
                        "to_date": date_to,
                        "force_reparse": force_refresh,
                    },
                )
                results["sources_synced"].append("gmail")
                results["results"]["gmail"] = gmail_result

                if gmail_result.get("job_id"):
                    async_jobs.append(
                        {
                            "job_id": gmail_result["job_id"],
                            "type": "gmail_sync",
                            "user_id": user_id,
                        }
                    )

                logger.info(f"Gmail sync queued: job_id={gmail_result.get('job_id')}")
            except FlaskAPIError as e:
                logger.error(f"Gmail sync failed: {e}")
                results["results"]["gmail"] = {"error": str(e), "status": "failed"}
        else:
            results["results"]["gmail"] = {"status": "not_connected"}

        # Step 4: Amazon and Apple (require file uploads - skip for now)
        results["results"]["apple"] = {
            "status": "skipped",
            "reason": "Requires HTML file upload via web UI",
        }
        results["results"]["amazon"] = {
            "status": "skipped",
            "reason": "Requires CSV file upload or Amazon Business OAuth",
        }

        # Step 5: Wait for async jobs
        if async_jobs:
            logger.info(f"Waiting for {len(async_jobs)} async jobs...")
            job_results = await wait_for_async_jobs(async_jobs, timeout=300)
            logger.info(f"Async jobs completed: {len(job_results)}/{len(async_jobs)}")

            # Update results with job outcomes
            for job_result in job_results:
                if job_result.get("type") == "gmail_sync":
                    results["results"]["gmail"]["final_status"] = job_result

        # Step 6: Run unified matching (unless skip_matching=True)
        if not skip_matching and results["sources_synced"]:
            try:
                logger.info("Running unified matching...")
                matching_result = client.post(
                    "/api/matching/run",
                    {
                        "user_id": user_id,
                        "sources": ["amazon", "apple", "gmail"],
                        "sync_first": False,
                    },
                )
                results["matching"] = matching_result
                logger.info(f"Matching completed: {matching_result}")
            except FlaskAPIError as e:
                logger.error(f"Matching failed: {e}")
                results["matching"] = {"error": str(e), "status": "failed"}

        results["status"] = "completed"
        logger.info(
            f"sync_all_sources completed: {len(results['sources_synced'])} sources synced"
        )

        return format_success_response(results)

    except ValidationError as e:
        logger.error(f"Validation error in sync_all_sources: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in sync_all_sources: {e}")
        return format_error_response(e, {"tool": "sync_all_sources"})


# ============================================================================
# Tool 2: run_full_pipeline
# ============================================================================


@mcp.tool()
async def run_full_pipeline(
    user_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    enrichment_provider: str | None = None,
    batch_size: int | None = None,
    only_unenriched: bool = True,
) -> dict:
    """
    Run complete data pipeline: sync → parse → match → enrich.

    This is the most comprehensive workflow tool. It syncs all sources, waits for
    completion, runs matching operations, and triggers LLM enrichment.

    Args:
        user_id: User ID (default: 1)
        date_from: Start date YYYY-MM-DD (default: 30 days ago)
        date_to: End date YYYY-MM-DD (default: today)
        enrichment_provider: LLM provider (default: anthropic)
        batch_size: Enrichment batch size (default: 10)
        only_unenriched: Only enrich transactions without existing enrichment (default: true)

    Returns:
        Pipeline summary with sync, matching, and enrichment results

    Example:
        run_full_pipeline()  # Complete pipeline with defaults
        run_full_pipeline(enrichment_provider="openai", batch_size=20)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        date_from, date_to = apply_date_range_defaults(date_from, date_to)

        # Validate
        validate_user_id(user_id)
        validate_date_range(date_from, date_to)

        logger.info(
            f"Starting run_full_pipeline: user={user_id}, dates={date_from} to {date_to}"
        )

        pipeline_result = {
            "pipeline_status": "running",
            "timestamp": datetime.now().isoformat(),
        }

        # Step 1: Sync all sources
        logger.info("Pipeline Step 1/4: Syncing all sources...")
        sync_result = await sync_all_sources(
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            skip_matching=True,  # We'll run matching separately
        )
        pipeline_result["sync_summary"] = sync_result

        # Step 2: Run pre-enrichment matching
        logger.info("Pipeline Step 2/4: Running pre-enrichment matching...")
        matching_result = await run_pre_enrichment(user_id=user_id)
        pipeline_result["matching_summary"] = matching_result

        # Step 3: Trigger enrichment
        logger.info("Pipeline Step 3/4: Triggering LLM enrichment...")
        client = get_flask_client()

        enrichment_payload = {"user_id": user_id}
        if enrichment_provider:
            enrichment_payload["provider"] = enrichment_provider
        if batch_size:
            enrichment_payload["batch_size"] = batch_size
        if not only_unenriched:
            enrichment_payload["force_refresh"] = True

        try:
            enrichment_result = client.post(
                "/api/enrichment/trigger", enrichment_payload
            )
            pipeline_result["enrichment"] = enrichment_result
            logger.info(f"Enrichment queued: {enrichment_result}")
        except FlaskAPIError as e:
            logger.error(f"Enrichment failed: {e}")
            pipeline_result["enrichment"] = {"error": str(e), "status": "failed"}

        # Step 4: Get final stats
        logger.info("Pipeline Step 4/4: Fetching final statistics...")
        try:
            final_stats = client.get("/api/enrichment/status", {"user_id": user_id})
            pipeline_result["final_stats"] = final_stats
        except Exception as e:
            logger.warning(f"Failed to get final stats: {e}")

        pipeline_result["pipeline_status"] = "completed"
        logger.info("run_full_pipeline completed successfully")

        return format_success_response(pipeline_result)

    except ValidationError as e:
        logger.error(f"Validation error in run_full_pipeline: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in run_full_pipeline: {e}")
        return format_error_response(e, {"tool": "run_full_pipeline"})


# ============================================================================
# Tool 3: run_pre_enrichment
# ============================================================================


@mcp.tool()
async def run_pre_enrichment(
    user_id: int | None = None,
    sources: list[str] | None = None,
    check_staleness: bool = True,
) -> dict:
    """
    Run all matching operations (Amazon + Apple + Gmail).

    This tool runs matching for receipt sources before LLM enrichment. It checks
    for stale sources and warns if data needs syncing.

    Args:
        user_id: User ID (default: 1)
        sources: List of sources to match (default: ["amazon", "apple", "gmail"])
        check_staleness: Warn if sources are stale (default: true)

    Returns:
        Matching summary with results for each source and staleness warnings

    Example:
        run_pre_enrichment()  # Match all sources
        run_pre_enrichment(sources=["amazon", "gmail"])  # Match specific sources
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        if sources is None:
            sources = ["amazon", "apple", "gmail"]

        # Validate
        validate_user_id(user_id)

        client = get_flask_client()

        logger.info(f"Starting run_pre_enrichment: user={user_id}, sources={sources}")

        result = {"status": "running", "staleness_warnings": [], "matching_results": {}}

        # Step 1: Check source staleness
        if check_staleness:
            try:
                coverage = client.get("/api/matching/coverage", {"user_id": user_id})
                stale_sources = coverage.get("stale_sources", [])

                if stale_sources:
                    for source in stale_sources:
                        source_data = coverage.get(source, {})
                        days_behind = source_data.get("days_behind", 0)

                        result["staleness_warnings"].append(
                            {
                                "source": source,
                                "days_behind": days_behind,
                                "recommendation": f"Run sync_{source} to update {source} data",
                            }
                        )

                    logger.warning(f"Stale sources detected: {stale_sources}")

            except Exception as e:
                logger.warning(f"Failed to check staleness: {e}")

        # Step 2: Run unified matching
        try:
            logger.info(f"Running matching for sources: {sources}")
            matching_result = client.post(
                "/api/matching/run",
                {"user_id": user_id, "sources": sources, "sync_first": False},
            )

            result["matching_results"] = matching_result
            result["status"] = "completed"

            logger.info(f"Matching completed: {matching_result}")

        except FlaskAPIError as e:
            logger.error(f"Matching failed: {e}")
            result["matching_results"] = {"error": str(e), "status": "failed"}
            result["status"] = "failed"

        return format_success_response(result)

    except ValidationError as e:
        logger.error(f"Validation error in run_pre_enrichment: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in run_pre_enrichment: {e}")
        return format_error_response(e, {"tool": "run_pre_enrichment"})


# ============================================================================
# Tool 4: check_sync_status
# ============================================================================


@mcp.tool()
async def check_sync_status(
    user_id: int | None = None, include_completed: bool = False, hours_back: int = 24
) -> dict:
    """
    Get status of all active/recent sync operations.

    This tool provides visibility into running and recent sync jobs across all sources.

    Args:
        user_id: User ID (default: 1)
        include_completed: Include completed jobs (default: false)
        hours_back: Hours of history for completed jobs (default: 24)

    Returns:
        List of active and recent sync jobs with status and progress

    Example:
        check_sync_status()  # Active jobs only
        check_sync_status(include_completed=True, hours_back=48)  # Last 2 days
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        client = get_flask_client()

        logger.info(
            f"Checking sync status: user={user_id}, include_completed={include_completed}"
        )

        result = {"active_jobs": [], "recent_completed": []}

        # Get Gmail sync status
        try:
            gmail_status = client.get("/api/gmail/sync/status", {"user_id": user_id})
            if gmail_status.get("status") in ["running", "queued"]:
                result["active_jobs"].append(
                    {
                        "job_id": gmail_status.get("job_id"),
                        "type": "gmail_sync",
                        "status": gmail_status.get("status"),
                        "progress": gmail_status.get("progress"),
                        "started_at": gmail_status.get("started_at"),
                    }
                )
            elif include_completed and gmail_status.get("status") == "completed":
                result["recent_completed"].append(
                    {
                        "job_id": gmail_status.get("job_id"),
                        "type": "gmail_sync",
                        "status": "completed",
                        "completed_at": gmail_status.get("completed_at"),
                        "result": gmail_status.get("summary"),
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to get Gmail status: {e}")

        # Get TrueLayer import status
        try:
            import_history = client.get(
                "/api/truelayer/import/history", {"user_id": user_id}
            )
            if import_history and len(import_history) > 0:
                latest = import_history[0]
                if latest.get("status") == "running":
                    result["active_jobs"].append(
                        {
                            "job_id": latest.get("job_id"),
                            "type": "truelayer_sync",
                            "status": "running",
                            "progress": latest.get("progress"),
                            "started_at": latest.get("started_at"),
                        }
                    )
                elif include_completed and latest.get("status") == "completed":
                    result["recent_completed"].append(
                        {
                            "job_id": latest.get("job_id"),
                            "type": "truelayer_sync",
                            "status": "completed",
                            "completed_at": latest.get("completed_at"),
                            "result": latest.get("summary"),
                        }
                    )

        except Exception as e:
            logger.warning(f"Failed to get TrueLayer import history: {e}")

        logger.info(
            f"Found {len(result['active_jobs'])} active jobs, {len(result['recent_completed'])} completed"
        )

        return format_success_response(result)

    except ValidationError as e:
        logger.error(f"Validation error in check_sync_status: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in check_sync_status: {e}")
        return format_error_response(e, {"tool": "check_sync_status"})


# ============================================================================
# Tool 5: get_source_coverage
# ============================================================================


@mcp.tool()
async def get_source_coverage(user_id: int | None = None) -> dict:
    """
    Check data coverage and staleness for all sources.

    This tool shows the date range coverage for each data source and identifies
    sources that are stale (behind bank transaction data).

    Args:
        user_id: User ID (default: 1)

    Returns:
        Coverage summary with date ranges, counts, and staleness warnings for each source

    Example:
        get_source_coverage()  # Check all sources
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        client = get_flask_client()

        logger.info(f"Getting source coverage: user={user_id}")

        # Get coverage from API
        try:
            coverage = client.get("/api/matching/coverage", {"user_id": user_id})
            logger.info(f"Coverage retrieved: {coverage}")
            return format_success_response(coverage)

        except FlaskAPIError as e:
            logger.error(f"Failed to get coverage: {e}")
            return format_error_response(e)

    except ValidationError as e:
        logger.error(f"Validation error in get_source_coverage: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in get_source_coverage: {e}")
        return format_error_response(e, {"tool": "get_source_coverage"})
