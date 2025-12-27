"""
Search & Query Tools

Provides 4 search and query MCP tools:
1. search_transactions - Search transactions by various criteria
2. get_transaction_details - Get full details for a specific transaction
3. get_enrichment_details - Get enrichment details for a transaction
4. search_enriched_transactions - Search for enriched/categorized transactions

These tools enable Claude to query and analyze transaction data interactively.
"""

import logging

from ..server import get_flask_client, mcp
from ..utils.defaults import apply_date_range_defaults, apply_user_id_default
from ..utils.formatters import format_error_response, format_success_response
from ..utils.validators import ValidationError, validate_amount, validate_user_id

logger = logging.getLogger(__name__)


@mcp.tool()
async def search_transactions(
    user_id: int | None = None,
    merchant: str | None = None,
    description: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    enriched_only: bool = False,
    limit: int = 50,
) -> dict:
    """
    Search for transactions by various criteria.

    Searches TrueLayer bank transactions with flexible filtering options.
    Returns transactions sorted by date (most recent first).

    Args:
        user_id: User ID (default: 1)
        merchant: Merchant name (partial match, case-insensitive)
        description: Transaction description (partial match, case-insensitive)
        min_amount: Minimum transaction amount (absolute value)
        max_amount: Maximum transaction amount (absolute value)
        date_from: Start date (YYYY-MM-DD format, default: 30 days ago)
        date_to: End date (YYYY-MM-DD format, default: today)
        category: Category name filter
        subcategory: Subcategory name filter
        enriched_only: Only return enriched transactions (default: false)
        limit: Max results to return (default: 50, max: 500)

    Returns:
        List of matching transactions with enrichment data

    Examples:
        # Search by merchant
        search_transactions(merchant="Amazon")

        # Search by amount range
        search_transactions(min_amount=50, max_amount=200)

        # Search by date and category
        search_transactions(
            date_from="2024-12-01",
            category="Shopping",
            enriched_only=True
        )

        # Search by description
        search_transactions(description="subscription")
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        date_from, date_to = apply_date_range_defaults(date_from, date_to)

        # Validate
        validate_user_id(user_id)
        if min_amount is not None:
            validate_amount(min_amount)
        if max_amount is not None:
            validate_amount(max_amount)

        # Limit bounds
        limit = max(1, min(limit, 500))

        client = get_flask_client()
        logger.info(
            f"Searching transactions: user={user_id}, merchant={merchant}, "
            f"amount={min_amount}-{max_amount}, dates={date_from} to {date_to}"
        )

        # Get all transactions
        transactions = client.get("/api/transactions")

        if not isinstance(transactions, list):
            logger.error(f"Unexpected transactions response: {type(transactions)}")
            transactions = []

        # Apply filters
        filtered = []
        for txn in transactions:
            # Date filter
            txn_date = txn.get("timestamp", "").split("T")[0]
            if date_from and txn_date < date_from:
                continue
            if date_to and txn_date > date_to:
                continue

            # Merchant filter (case-insensitive partial match)
            if merchant:
                merchant_name = txn.get("merchant_name", "") or ""
                if merchant.lower() not in merchant_name.lower():
                    continue

            # Description filter (case-insensitive partial match)
            if description:
                txn_desc = txn.get("description", "") or ""
                if description.lower() not in txn_desc.lower():
                    continue

            # Amount filter (use absolute value)
            if min_amount is not None or max_amount is not None:
                amount = abs(float(txn.get("amount", 0)))
                if min_amount is not None and amount < min_amount:
                    continue
                if max_amount is not None and amount > max_amount:
                    continue

            # Category filter
            if category:
                txn_category = txn.get("category_name", "") or ""
                if category.lower() != txn_category.lower():
                    continue

            # Subcategory filter
            if subcategory:
                txn_subcategory = txn.get("subcategory_name", "") or ""
                if subcategory.lower() != txn_subcategory.lower():
                    continue

            # Enriched filter
            if enriched_only:
                if not txn.get("category_name"):
                    continue

            filtered.append(txn)

        # Sort by date (most recent first)
        filtered.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Limit results
        results = filtered[:limit]

        logger.info(
            f"Found {len(filtered)} matching transactions (returning {len(results)})"
        )

        return format_success_response(
            {
                "transactions": results,
                "total_matches": len(filtered),
                "returned": len(results),
                "filters_applied": {
                    "merchant": merchant,
                    "description": description,
                    "min_amount": min_amount,
                    "max_amount": max_amount,
                    "date_from": date_from,
                    "date_to": date_to,
                    "category": category,
                    "subcategory": subcategory,
                    "enriched_only": enriched_only,
                },
            }
        )

    except ValidationError as e:
        logger.error(f"Validation error in search_transactions: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in search_transactions: {e}")
        return format_error_response(e, {"tool": "search_transactions"})


@mcp.tool()
async def get_transaction_details(
    transaction_id: int, user_id: int | None = None
) -> dict:
    """
    Get full details for a specific transaction including all enrichment sources.

    Retrieves the transaction with all associated enrichment data from
    Amazon, Apple, Gmail, and LLM enrichment.

    Args:
        transaction_id: Transaction ID (required)
        user_id: User ID (default: 1)

    Returns:
        Transaction details with all enrichment sources and metadata

    Example:
        get_transaction_details(transaction_id=12345)
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)

        # Validate
        validate_user_id(user_id)
        if not transaction_id or transaction_id < 1:
            raise ValidationError("transaction_id must be a positive integer")

        client = get_flask_client()
        logger.info(f"Getting transaction details: id={transaction_id}, user={user_id}")

        # Get all transactions (cached)
        transactions = client.get("/api/transactions")

        # Find the specific transaction
        transaction = None
        for txn in transactions:
            if txn.get("id") == transaction_id:
                transaction = txn
                break

        if not transaction:
            raise ValidationError(f"Transaction {transaction_id} not found")

        # Get enrichment sources
        try:
            enrichment_sources = client.get(
                f"/api/transactions/{transaction_id}/enrichment-sources"
            )
            transaction["enrichment_sources"] = enrichment_sources.get("sources", [])
        except Exception as e:
            logger.warning(f"Failed to get enrichment sources: {e}")
            transaction["enrichment_sources"] = []

        # Get detailed source data for each enrichment source
        for source in transaction.get("enrichment_sources", []):
            try:
                source_details = client.get(
                    f"/api/enrichment-sources/{source['id']}/details"
                )
                source["details"] = source_details
            except Exception as e:
                logger.warning(f"Failed to get source details for {source['id']}: {e}")
                source["details"] = None

        logger.info(
            f"Transaction {transaction_id} found with {len(transaction.get('enrichment_sources', []))} sources"
        )

        return format_success_response(
            {
                "transaction": transaction,
                "enrichment_source_count": len(
                    transaction.get("enrichment_sources", [])
                ),
            }
        )

    except ValidationError as e:
        logger.error(f"Validation error in get_transaction_details: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in get_transaction_details: {e}")
        return format_error_response(e, {"tool": "get_transaction_details"})


@mcp.tool()
async def get_enrichment_details(
    transaction_id: int | None = None, include_failed: bool = False, limit: int = 20
) -> dict:
    """
    Get enrichment details and statistics.

    Can retrieve enrichment info for a specific transaction or get
    overall enrichment statistics including failed enrichments.

    Args:
        transaction_id: Specific transaction ID (optional)
        include_failed: Include failed enrichments (default: false)
        limit: Max failed enrichments to return (default: 20)

    Returns:
        Enrichment details with stats, sources, and optionally failures

    Examples:
        # Get overall enrichment stats
        get_enrichment_details()

        # Get enrichment for specific transaction
        get_enrichment_details(transaction_id=12345)

        # Get failed enrichments
        get_enrichment_details(include_failed=True, limit=50)
    """
    try:
        client = get_flask_client()

        result = {}

        # Get overall stats
        try:
            stats = client.get("/api/enrichment/stats")
            result["overall_stats"] = stats
        except Exception as e:
            logger.warning(f"Failed to get enrichment stats: {e}")
            result["overall_stats"] = None

        # Get specific transaction enrichment
        if transaction_id:
            try:
                sources = client.get(
                    f"/api/transactions/{transaction_id}/enrichment-sources"
                )
                result["transaction_enrichment"] = sources
            except Exception as e:
                logger.warning(f"Failed to get transaction enrichment: {e}")
                result["transaction_enrichment"] = {"error": str(e)}

        # Get failed enrichments
        if include_failed:
            try:
                failed = client.get("/api/enrichment/failed", params={"limit": limit})
                result["failed_enrichments"] = failed
            except Exception as e:
                logger.warning(f"Failed to get failed enrichments: {e}")
                result["failed_enrichments"] = []

        logger.info(
            f"Enrichment details retrieved: transaction={transaction_id}, failed={include_failed}"
        )

        return format_success_response(result)

    except Exception as e:
        logger.exception(f"Unexpected error in get_enrichment_details: {e}")
        return format_error_response(e, {"tool": "get_enrichment_details"})


@mcp.tool()
async def search_enriched_transactions(
    user_id: int | None = None,
    provider: str | None = None,
    category: str | None = None,
    min_confidence: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict:
    """
    Search for enriched/categorized transactions with LLM metadata.

    Finds transactions that have been enriched by LLM providers
    with optional filtering by provider, category, and confidence.

    Args:
        user_id: User ID (default: 1)
        provider: LLM provider filter - "anthropic", "openai", "google", "deepseek" (optional)
        category: Category name filter (optional)
        min_confidence: Minimum confidence score 0.0-1.0 (optional)
        date_from: Start date (YYYY-MM-DD format, default: 30 days ago)
        date_to: End date (YYYY-MM-DD format, default: today)
        limit: Max results to return (default: 50, max: 500)

    Returns:
        List of enriched transactions with LLM metadata

    Examples:
        # Find all enriched transactions
        search_enriched_transactions()

        # Find high-confidence Anthropic enrichments
        search_enriched_transactions(
            provider="anthropic",
            min_confidence=0.9
        )

        # Find grocery categorizations
        search_enriched_transactions(
            category="Groceries",
            date_from="2024-12-01"
        )
    """
    try:
        # Apply defaults
        user_id = apply_user_id_default(user_id)
        date_from, date_to = apply_date_range_defaults(date_from, date_to)

        # Validate
        validate_user_id(user_id)
        if min_confidence is not None:
            if not 0.0 <= min_confidence <= 1.0:
                raise ValidationError("min_confidence must be between 0.0 and 1.0")

        # Limit bounds
        limit = max(1, min(limit, 500))

        client = get_flask_client()
        logger.info(
            f"Searching enriched transactions: user={user_id}, provider={provider}, "
            f"category={category}, min_confidence={min_confidence}"
        )

        # Get all transactions
        transactions = client.get("/api/transactions")

        if not isinstance(transactions, list):
            transactions = []

        # Filter for enriched transactions
        enriched = []
        for txn in transactions:
            # Must have category (enriched)
            if not txn.get("category_name"):
                continue

            # Date filter
            txn_date = txn.get("timestamp", "").split("T")[0]
            if date_from and txn_date < date_from:
                continue
            if date_to and txn_date > date_to:
                continue

            # Provider filter (check enrichment_source)
            if provider:
                source = txn.get("enrichment_source", "")
                if provider.lower() not in source.lower():
                    continue

            # Category filter
            if category:
                txn_category = txn.get("category_name", "") or ""
                if category.lower() != txn_category.lower():
                    continue

            # Confidence filter (if available in enrichment metadata)
            if min_confidence is not None:
                confidence = txn.get("confidence_score", 1.0)
                if confidence < min_confidence:
                    continue

            enriched.append(txn)

        # Sort by date (most recent first)
        enriched.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Limit results
        results = enriched[:limit]

        logger.info(
            f"Found {len(enriched)} enriched transactions (returning {len(results)})"
        )

        return format_success_response(
            {
                "transactions": results,
                "total_matches": len(enriched),
                "returned": len(results),
                "filters_applied": {
                    "provider": provider,
                    "category": category,
                    "min_confidence": min_confidence,
                    "date_from": date_from,
                    "date_to": date_to,
                },
            }
        )

    except ValidationError as e:
        logger.error(f"Validation error in search_enriched_transactions: {e}")
        return format_error_response(e)
    except Exception as e:
        logger.exception(f"Unexpected error in search_enriched_transactions: {e}")
        return format_error_response(e, {"tool": "search_enriched_transactions"})
