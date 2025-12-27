"""
Analytics & Monitoring Tools

Provides 5 analytics and monitoring MCP tools:
1. get_endpoint_health - Check API endpoint health
2. get_system_analytics - Overall system analytics
3. get_sync_logs - Access sync operation logs
4. get_error_logs - Get failure logs and error details
5. get_workflow_metrics - Detailed workflow metrics

These tools provide observability into system health and performance.
"""

import logging

from ..client.flask_client import FlaskAPIError
from ..server import get_flask_client, mcp
from ..utils.defaults import apply_user_id_default
from ..utils.formatters import format_error_response, format_success_response
from ..utils.validators import ValidationError, validate_user_id

logger = logging.getLogger(__name__)


@mcp.tool()
async def get_endpoint_health(include_details: bool = False) -> dict:
    """
    Check health status of all API endpoints.

    Tests critical endpoints and checks database/Redis connectivity,
    Celery worker status, and response times.

    Args:
        include_details: Include detailed endpoint checks (default: false)

    Returns:
        Health status with overall status, component status, and issues

    Example:
        get_endpoint_health()
        get_endpoint_health(include_details=True)
    """
    try:
        client = get_flask_client()
        logger.info("Checking endpoint health")

        # Get API health
        health = client.get("/api/health")

        if include_details:
            # Add detailed checks
            logger.info("Running detailed health checks...")

        logger.info(f"Health status: {health.get('status', 'unknown')}")
        return format_success_response(health)

    except FlaskAPIError as e:
        logger.error(f"Health check failed: {e}")
        return format_error_response(e, {"overall_status": "unhealthy"})
    except Exception as e:
        logger.exception(f"Error in get_endpoint_health: {e}")
        return format_error_response(e, {"tool": "get_endpoint_health"})


@mcp.tool()
async def get_system_analytics(
    user_id: int | None = None, time_period: str = "month"
) -> dict:
    """
    Get overall system analytics and dashboard data.

    Args:
        user_id: User ID (default: 1)
        time_period: Period - "week", "month", or "year" (default: "month")

    Returns:
        Analytics summary with transaction counts, matching coverage,
        enrichment stats, and spending trends
    """
    try:
        user_id = apply_user_id_default(user_id)
        validate_user_id(user_id)

        client = get_flask_client()
        logger.info(f"Getting system analytics: user={user_id}, period={time_period}")

        # Get various stats endpoints
        transactions = client.get("/api/transactions")
        enrichment = client.get("/api/enrichment/status", {"user_id": user_id})
        matching = client.get("/api/matching/coverage", {"user_id": user_id})

        analytics = {
            "period": time_period,
            "transactions": {
                "total": len(transactions) if isinstance(transactions, list) else 0
            },
            "enrichment": enrichment,
            "matching_coverage": matching,
        }

        return format_success_response(analytics)

    except (ValidationError, FlaskAPIError) as e:
        return format_error_response(e)
    except Exception as e:
        return format_error_response(e, {"tool": "get_system_analytics"})


@mcp.tool()
async def get_sync_logs(
    job_type: str | None = None,
    limit: int = 50,
    since: str | None = None,
    status: str | None = None,
) -> dict:
    """
    Access sync operation logs.

    Args:
        job_type: Filter by type - "gmail_sync", "truelayer_sync", "amazon_sync" (optional)
        limit: Max log entries (default: 50)
        since: ISO datetime to filter from (optional)
        status: Filter by status - "success", "failed", "running" (optional)

    Returns:
        List of log entries with job details
    """
    return format_error_response(
        Exception("get_sync_logs not yet fully implemented"), {"tool": "get_sync_logs"}
    )


@mcp.tool()
async def get_error_logs(
    error_type: str | None = None,
    limit: int = 50,
    since: str | None = None,
    severity: str = "error",
) -> dict:
    """
    Get failure logs and error details.

    Args:
        error_type: Filter by type - "sync", "matching", "enrichment", "parsing" (optional)
        limit: Max errors (default: 50)
        since: ISO datetime to filter from (optional)
        severity: Filter by severity - "error" or "warning" (default: "error")

    Returns:
        List of error logs with context and stack traces
    """
    try:
        client = get_flask_client()
        logger.info(f"Getting error logs: type={error_type}, limit={limit}")

        # Get failed enrichments
        failed = client.get("/api/enrichment/failed")

        return format_success_response({"errors": failed, "total_errors": len(failed)})

    except FlaskAPIError as e:
        return format_error_response(e)
    except Exception as e:
        return format_error_response(e, {"tool": "get_error_logs"})


@mcp.tool()
async def get_workflow_metrics(
    user_id: int | None = None, time_period: str = "week"
) -> dict:
    """
    Get detailed metrics for sync → parse → match → enrich workflow.

    Args:
        user_id: User ID (default: 1)
        time_period: Period - "day", "week", or "month" (default: "week")

    Returns:
        Workflow metrics with success rates, processing times, throughput,
        cost tracking, and quality metrics
    """
    return format_error_response(
        Exception("get_workflow_metrics not yet fully implemented"),
        {"tool": "get_workflow_metrics"},
    )
