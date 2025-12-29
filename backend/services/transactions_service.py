"""
Transactions Service - Business Logic

Orchestrates transaction data operations including:
- Transaction retrieval with enrichment data
- Transaction normalization and formatting
- Enrichment source management
- Huququllah classification
- Redis caching for performance

Separates business logic from HTTP routing concerns.
"""

import cache_manager

from database import (
    enrichment as db_enrichment,
)
from database import (
    transactions as db_transactions,
)
from database import (
    truelayer,
)

# ============================================================================
# Helper Functions
# ============================================================================


def normalize_transaction(t: dict) -> dict:
    """
    Normalize transaction field names for frontend consistency.

    Args:
        t: Raw transaction dict from database

    Returns:
        Normalized transaction dict with consistent field names
    """
    # Normalize timestamp to date field for frontend
    timestamp = t.get("timestamp")
    if timestamp:
        # If timestamp is already a string, use as-is
        if isinstance(timestamp, str):
            date_str = timestamp.split("T")[0] if "T" in timestamp else timestamp
        else:
            # If it's a datetime object, convert to ISO format
            date_str = timestamp.isoformat().split("T")[0]
    else:
        date_str = None

    return {
        "id": t.get("id"),
        "date": date_str,  # Normalized from timestamp for frontend
        "description": t.get("description"),
        "amount": float(t.get("amount", 0)) if t.get("amount") is not None else None,
        "transaction_type": t.get("transaction_type"),
        "account_id": t.get("account_id"),
        "provider_id": t.get("provider_id"),
        "category": t.get("category"),
        "meta": t.get("meta"),
        "timestamp": t.get("timestamp").isoformat()
        if hasattr(t.get("timestamp"), "isoformat")
        else t.get("timestamp"),
    }


def build_enrichment_object(t: dict) -> dict:
    """
    Build enrichment object from transaction enrichment columns.

    Args:
        t: Raw transaction dict with prefixed enrichment columns

    Returns:
        Enrichment dict with all enrichment fields
    """
    has_enrichment = bool(t.get("enrichment_primary_category"))

    if has_enrichment:
        return {
            "is_enriched": True,
            "primary_category": t.get("enrichment_primary_category"),
            "subcategory": t.get("enrichment_subcategory"),
            "merchant_clean_name": t.get("enrichment_merchant_clean_name"),
            "merchant_type": t.get("enrichment_merchant_type"),
            "essential_discretionary": t.get("enrichment_essential_discretionary"),
            "payment_method": t.get("enrichment_payment_method"),
            "payment_method_subtype": t.get("enrichment_payment_method_subtype"),
            "confidence_score": float(t.get("enrichment_confidence_score", 0))
            if t.get("enrichment_confidence_score")
            else None,
            "enriched_at": t.get("enrichment_enriched_at").isoformat()
            if t.get("enrichment_enriched_at")
            else None,
            "enrichment_source": t.get("enrichment_llm_provider", "llm"),
            "llm_provider": t.get("enrichment_llm_provider"),
            "llm_model": t.get("enrichment_llm_model"),
        }
    return {"is_enriched": False}


def format_enrichment_sources(sources: list) -> list:
    """
    Format enrichment sources for frontend display.

    Args:
        sources: Raw enrichment sources from database

    Returns:
        Formatted sources list
    """
    return [
        {
            "id": s.get("id"),
            "source_type": s.get("source_type"),
            "source_id": s.get("source_id"),
            "description": s.get("description"),
            "order_id": s.get("order_id"),
            "confidence": s.get("match_confidence"),
            "match_method": s.get("match_method"),
            "is_primary": s.get("is_primary", False),
            "user_verified": s.get("user_verified", False),
            "line_items": s.get("line_items"),
        }
        for s in sources
    ]


# ============================================================================
# Transaction Retrieval
# ============================================================================


def get_all_transactions(user_id: int | None = None) -> list:
    """
    Get all TrueLayer transactions with enrichment data for a specific user.

    Uses optimized single-query approach with Redis caching.
    Cache TTL: 15 minutes.

    Args:
        user_id: User ID to filter transactions by. If None, returns empty list
                 for security (no transactions visible without explicit user context).

    Returns:
        List of normalized transactions with enrichment and sources
    """
    # SECURITY: Require explicit user_id to prevent data leakage
    if user_id is None:
        return []

    # Check cache first (user-specific cache key)
    cache_key = f"transactions:user:{user_id}"
    cached_data = cache_manager.cache_get(cache_key)
    if cached_data is not None:
        return cached_data

    # Cache miss - fetch from database (filtered by user)
    all_transactions = (
        truelayer.get_all_truelayer_transactions_with_enrichment(user_id=user_id) or []
    )

    # Batch-fetch enrichment sources for all transactions
    transaction_ids = [t.get("id") for t in all_transactions if t.get("id")]
    enrichment_sources_map = {}
    if transaction_ids:
        enrichment_sources_map = (
            db_enrichment.get_all_enrichment_sources_for_transactions(transaction_ids)
        )

    # Normalize and build response
    normalized = []
    for t in all_transactions:
        # Normalize field names
        transaction = normalize_transaction(t)

        # Build enrichment object
        enrichment_obj = build_enrichment_object(t)
        transaction["enrichment"] = enrichment_obj

        # Flatten key enrichment fields to top level
        if enrichment_obj["is_enriched"]:
            transaction["subcategory"] = t.get("enrichment_subcategory")
            transaction["merchant_clean_name"] = t.get("enrichment_merchant_clean_name")
            transaction["essential_discretionary"] = t.get(
                "enrichment_essential_discretionary"
            )
            transaction["confidence_score"] = (
                float(t.get("enrichment_confidence_score", 0))
                if t.get("enrichment_confidence_score")
                else None
            )
            transaction["enrichment_source"] = t.get("enrichment_llm_provider", "llm")
            transaction["payment_method"] = t.get("enrichment_payment_method")
            transaction["payment_method_subtype"] = t.get(
                "enrichment_payment_method_subtype"
            )
        else:
            transaction["subcategory"] = None
            transaction["merchant_clean_name"] = None
            transaction["essential_discretionary"] = None
            transaction["confidence_score"] = None
            transaction["enrichment_source"] = None
            transaction["payment_method"] = None
            transaction["payment_method_subtype"] = None

        # Include enrichment_required flag
        transaction["enrichment_required"] = t.get("enrichment_required", True)

        # Compute huququllah_classification: manual override or LLM classification
        manual_classification = t.get("manual_huququllah_classification")
        llm_classification = (
            t.get("enrichment_essential_discretionary", "").lower()
            if t.get("enrichment_essential_discretionary")
            else None
        )
        transaction["huququllah_classification"] = (
            manual_classification or llm_classification
        )

        # Add enrichment sources
        txn_id = t.get("id")
        sources = enrichment_sources_map.get(txn_id, [])
        transaction["enrichment_sources"] = format_enrichment_sources(sources)

        normalized.append(transaction)

    # Sort by date descending (most recent first)
    normalized.sort(key=lambda t: str(t.get("date", "")), reverse=True)

    # Cache the result (15 minute TTL)
    cache_manager.cache_set(cache_key, normalized, ttl=900)

    return normalized


# ============================================================================
# Transaction Updates
# ============================================================================


def toggle_enrichment_required(transaction_id: int) -> dict:
    """
    Toggle enrichment_required flag for a transaction.

    Args:
        transaction_id: Transaction ID to toggle

    Returns:
        Updated transaction dict with new state

    Raises:
        ValueError: If transaction not found
    """
    result = db_transactions.toggle_enrichment_required(transaction_id)

    if not result:
        raise ValueError("Transaction not found")

    # Invalidate transactions cache
    cache_manager.cache_delete("transactions:all")

    return result


def update_huququllah_classification(transaction_id: int, classification: str) -> dict:
    """
    Update the Huququllah classification for a transaction.

    Args:
        transaction_id: Transaction ID to update
        classification: 'essential', 'discretionary', or None

    Returns:
        Success dict with transaction_id and classification

    Raises:
        ValueError: If classification invalid or transaction not found
    """
    # Validate classification
    if classification not in ["essential", "discretionary", None]:
        raise ValueError(
            'Invalid classification. Must be "essential", "discretionary", or null'
        )

    success = db_transactions.update_transaction_huququllah(
        transaction_id, classification
    )

    if not success:
        raise ValueError("Transaction not found")

    return {
        "success": True,
        "transaction_id": transaction_id,
        "classification": classification,
    }


# ============================================================================
# Enrichment Sources
# ============================================================================


def get_enrichment_sources(transaction_id: int) -> dict:
    """
    Get all enrichment sources for a transaction.

    Args:
        transaction_id: Transaction ID

    Returns:
        Dict with sources list and transaction_id
    """
    sources = db_transactions.get_transaction_enrichment_sources(transaction_id)

    # Format for frontend
    formatted_sources = []
    for source in sources:
        formatted_sources.append(
            {
                "id": source.get("id"),
                "source_type": source.get("source_type"),
                "source_id": source.get("source_id"),
                "description": source.get("description"),
                "order_id": source.get("order_id"),
                "line_items": source.get("line_items"),
                "confidence": source.get("match_confidence"),
                "match_method": source.get("match_method"),
                "is_primary": source.get("is_primary", False),
                "user_verified": source.get("user_verified", False),
                "created_at": source.get("created_at").isoformat()
                if source.get("created_at")
                else None,
            }
        )

    return {"sources": formatted_sources, "transaction_id": transaction_id}


def set_primary_enrichment_source(
    transaction_id: int, source_type: str, source_id: int = None
) -> dict:
    """
    Set the primary enrichment source for a transaction.

    Args:
        transaction_id: Transaction ID
        source_type: Source type (e.g., 'amazon', 'apple', 'gmail')
        source_id: Optional source ID

    Returns:
        Success dict with transaction_id and primary_source

    Raises:
        ValueError: If source_type missing or source not found
    """
    if not source_type:
        raise ValueError("source_type is required")

    success = db_transactions.set_primary_enrichment_source(
        transaction_id, source_type, source_id
    )

    if not success:
        raise ValueError("Source not found or update failed")

    # Invalidate cache since transaction data changed
    cache_manager.cache_delete("transactions:all")

    return {
        "success": True,
        "transaction_id": transaction_id,
        "primary_source": {"source_type": source_type, "source_id": source_id},
    }
