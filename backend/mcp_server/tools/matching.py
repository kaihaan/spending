"""
Matching Operation Tools

Provides 4 matching operation MCP tools:
1. match_amazon_orders - Match Amazon orders to bank transactions
2. match_apple_purchases - Match Apple purchases to bank transactions
3. match_gmail_receipts - Match Gmail receipts to bank transactions
4. run_unified_matching - Run matching across all sources

These tools link receipt data to bank transactions.
"""

import logging

from ..client.flask_client import FlaskAPIError
from ..server import get_flask_client, mcp
from ..utils.defaults import apply_user_id_default
from ..utils.formatters import format_error_response, format_success_response
from ..utils.validators import ValidationError, validate_source_list, validate_user_id

logger = logging.getLogger(__name__)


@mcp.tool()
async def match_amazon_orders(
    user_id: int | None = None,
    async_mode: bool = True,
    transaction_id: int | None = None,
) -> dict:
    """
    Match Amazon orders to bank transactions.

    Args:
        user_id: User ID (default: 1)
        async_mode: Run asynchronously (default: true)
        transaction_id: Rematch single transaction (optional)

    Returns:
        Matching summary or job details if async
    """
    try:
        user_id = apply_user_id_default(user_id)
        validate_user_id(user_id)

        client = get_flask_client()
        logger.info(f"Matching Amazon orders: user={user_id}, async={async_mode}")

        payload = {"user_id": user_id}
        if transaction_id:
            payload["transaction_id"] = transaction_id

        result = client.post("/api/amazon/match", payload)
        return format_success_response(result)

    except (ValidationError, FlaskAPIError) as e:
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Error in match_amazon_orders: {e}")
        return format_error_response(e, {"tool": "match_amazon_orders"})


@mcp.tool()
async def match_apple_purchases(
    user_id: int | None = None, async_mode: bool = True
) -> dict:
    """Match Apple purchases to bank transactions."""
    try:
        user_id = apply_user_id_default(user_id)
        validate_user_id(user_id)

        client = get_flask_client()
        result = client.post("/api/apple/match", {"user_id": user_id})
        return format_success_response(result)

    except (ValidationError, FlaskAPIError) as e:
        return format_error_response(e)
    except Exception as e:
        return format_error_response(e, {"tool": "match_apple_purchases"})


@mcp.tool()
async def match_gmail_receipts(user_id: int | None = None) -> dict:
    """Match Gmail receipts to bank transactions."""
    try:
        user_id = apply_user_id_default(user_id)
        validate_user_id(user_id)

        client = get_flask_client()
        result = client.post("/api/gmail/match", {"user_id": user_id})
        return format_success_response(result)

    except (ValidationError, FlaskAPIError) as e:
        return format_error_response(e)
    except Exception as e:
        return format_error_response(e, {"tool": "match_gmail_receipts"})


@mcp.tool()
async def run_unified_matching(
    user_id: int | None = None,
    sources: list[str] | None = None,
    sync_first: bool = False,
) -> dict:
    """
    Run matching across all sources in parallel.

    Args:
        user_id: User ID (default: 1)
        sources: Sources to match (default: ["amazon", "apple", "gmail"])
        sync_first: Sync sources before matching (default: false)

    Returns:
        Job details for unified matching operation
    """
    try:
        user_id = apply_user_id_default(user_id)
        if sources is None:
            sources = ["amazon", "apple", "gmail"]

        validate_user_id(user_id)
        validate_source_list(sources)

        client = get_flask_client()
        logger.info(f"Running unified matching: user={user_id}, sources={sources}")

        result = client.post(
            "/api/matching/run",
            {"user_id": user_id, "sources": sources, "sync_first": sync_first},
        )

        return format_success_response(result)

    except (ValidationError, FlaskAPIError) as e:
        return format_error_response(e)
    except Exception as e:
        return format_error_response(e, {"tool": "run_unified_matching"})
