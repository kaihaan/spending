"""
Enrichment Operation Tools

Provides 2 enrichment operation MCP tools:
1. enrich_transactions - Trigger LLM enrichment for transactions
2. get_enrichment_stats - Get enrichment statistics and workflow status

These tools manage LLM-based transaction categorization.
"""

import logging

from ..client.flask_client import FlaskAPIError
from ..server import get_flask_client, mcp
from ..utils.defaults import apply_batch_size_default, apply_user_id_default
from ..utils.formatters import format_error_response, format_success_response
from ..utils.validators import (
    ValidationError,
    validate_batch_size,
    validate_provider,
    validate_user_id,
)

logger = logging.getLogger(__name__)


@mcp.tool()
async def enrich_transactions(
    user_id: int | None = None,
    transaction_ids: list[int] | None = None,
    force_refresh: bool = False,
    provider: str | None = None,
    batch_size: int | None = None,
) -> dict:
    """
    Trigger LLM enrichment for transactions.

    Uses AI to categorize transactions and extract metadata (merchant, category,
    essential vs discretionary classification).

    Args:
        user_id: User ID (default: 1)
        transaction_ids: Specific transaction IDs (optional - defaults to unenriched)
        force_refresh: Re-enrich already enriched transactions (default: false)
        provider: LLM provider - "anthropic", "openai", "google", "deepseek", "ollama" (optional)
        batch_size: Batch size for enrichment (default: 10)

    Returns:
        Job details with estimated cost and queued transaction count

    Example:
        enrich_transactions()  # Enrich all unenriched transactions
        enrich_transactions(provider="anthropic", batch_size=20)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        if batch_size is not None:
            batch_size = apply_batch_size_default(batch_size)

        # Validate
        validate_user_id(user_id)
        if provider:
            validate_provider(provider)
        if batch_size:
            validate_batch_size(batch_size)

        client = get_flask_client()
        logger.info(
            f"Triggering enrichment: user={user_id}, provider={provider}, batch={batch_size}"
        )

        # Build payload
        payload = {"user_id": user_id}
        if transaction_ids:
            payload["transaction_ids"] = transaction_ids
        if force_refresh:
            payload["force_refresh"] = True
        if provider:
            payload["provider"] = provider
        if batch_size:
            payload["batch_size"] = batch_size

        result = client.post("/api/enrichment/trigger", payload)
        logger.info(f"Enrichment queued: {result}")

        return format_success_response(result, "Enrichment job queued successfully")

    except ValidationError as e:
        logger.error(f"Validation error in enrich_transactions: {e}")
        return format_error_response(e)
    except FlaskAPIError as e:
        logger.error(f"API error in enrich_transactions: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in enrich_transactions: {e}")
        return format_error_response(e, {"tool": "enrich_transactions"})


@mcp.tool()
async def get_enrichment_stats(user_id: int | None = None) -> dict:
    """
    Get LLM enrichment statistics and workflow status.

    Provides comprehensive stats on enrichment coverage, cache hit rates,
    provider breakdown, and failed enrichments.

    Args:
        user_id: User ID (default: 1)

    Returns:
        Enrichment statistics including total/enriched counts, cache stats,
        provider breakdown, and failed enrichments

    Example:
        get_enrichment_stats()
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)

        client = get_flask_client()
        logger.info(f"Getting enrichment stats: user={user_id}")

        # Get enrichment status
        result = client.get("/api/enrichment/status", {"user_id": user_id})
        logger.info(
            f"Enrichment stats retrieved: {result.get('enriched_count', 0)} enriched"
        )

        return format_success_response(result)

    except ValidationError as e:
        logger.error(f"Validation error in get_enrichment_stats: {e}")
        return format_error_response(e)
    except FlaskAPIError as e:
        logger.error(f"API error in get_enrichment_stats: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in get_enrichment_stats: {e}")
        return format_error_response(e, {"tool": "get_enrichment_stats"})
