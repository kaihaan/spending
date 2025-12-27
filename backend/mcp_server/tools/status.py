"""
Connection & Status Tools

Provides 3 connection and status MCP tools:
1. get_connection_status - Check OAuth connection status
2. get_data_summary - Summary of all data in system
3. get_recent_activity - Recent activity feed

These tools provide visibility into connections and system state.
"""

import logging

from ..server import get_flask_client, mcp
from ..utils.defaults import apply_user_id_default
from ..utils.formatters import (
    format_connection_status,
    format_error_response,
    format_success_response,
)
from ..utils.validators import ValidationError, validate_user_id

logger = logging.getLogger(__name__)


@mcp.tool()
async def get_connection_status(user_id: int | None = None) -> dict:
    """
    Check OAuth connection status for all sources.

    Shows which data sources are connected, last sync times, and token expiration.

    Args:
        user_id: User ID (default: 1)

    Returns:
        Connection status for TrueLayer, Gmail, Amazon Business, Apple

    Example:
        get_connection_status()
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        client = get_flask_client()
        logger.info(f"Getting connection status: user={user_id}")

        connections = {}

        # TrueLayer
        try:
            truelayer_conn = client.get(
                "/api/truelayer/connections", {"user_id": user_id}
            )
            if truelayer_conn and len(truelayer_conn) > 0:
                conn = truelayer_conn[0]
                connections["truelayer"] = format_connection_status(conn, "truelayer")
            else:
                connections["truelayer"] = {"connected": False}
        except Exception as e:
            logger.warning(f"Failed to get TrueLayer connection: {e}")
            connections["truelayer"] = {"connected": False, "error": str(e)}

        # Gmail
        try:
            gmail_conn = client.get("/api/gmail/connection", {"user_id": user_id})
            connections["gmail"] = format_connection_status(gmail_conn, "gmail")
        except Exception as e:
            logger.warning(f"Failed to get Gmail connection: {e}")
            connections["gmail"] = {"connected": False, "error": str(e)}

        # Apple (no OAuth - file-based)
        connections["apple"] = {
            "connected": False,
            "note": "Apple uses CSV/HTML import (no OAuth)",
        }

        # Amazon Business (SP-API)
        try:
            amazon_conn = client.get(
                "/api/amazon-business/connection", {"user_id": user_id}
            )
            connections["amazon_business"] = format_connection_status(
                amazon_conn, "amazon_business"
            )
        except Exception as e:
            logger.warning(f"Failed to get Amazon Business connection: {e}")
            connections["amazon_business"] = {"connected": False, "error": str(e)}

        # Amazon consumer (no OAuth - CSV-based)
        connections["amazon"] = {
            "connected": False,
            "note": "Amazon consumer uses CSV import (no OAuth)",
        }

        logger.info(f"Connection status retrieved: {list(connections.keys())}")

        return format_success_response(connections)

    except ValidationError as e:
        logger.error(f"Validation error in get_connection_status: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in get_connection_status: {e}")
        return format_error_response(e, {"tool": "get_connection_status"})


@mcp.tool()
async def get_data_summary(user_id: int | None = None) -> dict:
    """
    Get summary of all data in the system.

    Shows transaction counts, date ranges, enrichment status, and source breakdowns.

    Args:
        user_id: User ID (default: 1)

    Returns:
        Data summary with transaction counts, categories, and enrichment sources

    Example:
        get_data_summary()
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        client = get_flask_client()
        logger.info(f"Getting data summary: user={user_id}")

        # Get transactions
        transactions = client.get("/api/transactions")

        # Get enrichment stats
        enrichment = client.get("/api/enrichment/status", {"user_id": user_id})

        # Get statistics from various sources
        try:
            amazon_stats = client.get("/api/amazon/statistics")
        except Exception:  # Fixed: was bare except
            amazon_stats = {"total_orders": 0}

        try:
            apple_stats = client.get("/api/apple/statistics")
        except Exception:  # Fixed: was bare except
            apple_stats = {"total_transactions": 0}

        try:
            gmail_stats = client.get("/api/gmail/statistics")
        except Exception:  # Fixed: was bare except
            gmail_stats = {"total_receipts": 0}

        summary = {
            "transactions": {
                "total": len(transactions) if isinstance(transactions, list) else 0,
                "date_range": {
                    "earliest": None,  # TODO: Calculate from transactions
                    "latest": None,
                },
            },
            "enrichment_sources": {
                "amazon_orders": amazon_stats.get("total_orders", 0),
                "apple_purchases": apple_stats.get("total_transactions", 0),
                "gmail_receipts": gmail_stats.get("total_receipts", 0),
            },
            "enrichment": {
                "enriched": enrichment.get("enriched_count", 0),
                "unenriched": enrichment.get("unenriched_count", 0),
                "percentage": enrichment.get("enrichment_percentage", 0),
            },
        }

        logger.info(f"Data summary: {summary['transactions']['total']} transactions")

        return format_success_response(summary)

    except ValidationError as e:
        logger.error(f"Validation error in get_data_summary: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in get_data_summary: {e}")
        return format_error_response(e, {"tool": "get_data_summary"})


@mcp.tool()
async def get_recent_activity(
    user_id: int | None = None, limit: int = 20, hours_back: int = 24
) -> dict:
    """
    Get recent activity feed (syncs, matches, enrichments).

    Shows a chronological log of recent operations across all sources.

    Args:
        user_id: User ID (default: 1)
        limit: Max activities to return (default: 20)
        hours_back: Hours of history (default: 24)

    Returns:
        List of recent activities with timestamps, types, and statuses

    Example:
        get_recent_activity()
        get_recent_activity(hours_back=48, limit=50)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        logger.info(f"Getting recent activity: user={user_id}, hours_back={hours_back}")

        # TODO: Implement activity feed aggregation from various sources
        activities = []

        return format_success_response({"activities": activities})

    except ValidationError as e:
        logger.error(f"Validation error in get_recent_activity: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in get_recent_activity: {e}")
        return format_error_response(e, {"tool": "get_recent_activity"})
