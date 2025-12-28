"""
Transaction Enrichment - Database Operations

Handles multi-source transaction enrichment, enrichment status tracking,
and enrichment job management.

Migrated to SQLAlchemy from psycopg2.
"""

import json

from sqlalchemy import func, text
from sqlalchemy.dialects.postgresql import insert

from .base import get_session
from .models.amazon import (
    AmazonBusinessLineItem,
    AmazonBusinessOrder,
    AmazonOrder,
    AmazonReturn,
)
from .models.amazon import (
    TrueLayerAmazonTransactionMatch as AmazonTransactionMatch,
)
from .models.apple import (
    AppleTransaction,
)
from .models.apple import (
    TrueLayerAppleTransactionMatch as AppleTransactionMatch,
)
from .models.enrichment import EnrichmentCache, TransactionEnrichmentSource
from .models.gmail import GmailReceipt, PDFAttachment
from .models.truelayer import TrueLayerTransaction

# ============================================================================
# MULTI-SOURCE ENRICHMENT FUNCTIONS
# ============================================================================


def add_enrichment_source(
    transaction_id: int,
    source_type: str,
    description: str,
    source_id: int = None,
    order_id: str = None,
    line_items: list = None,
    confidence: int = 100,
    match_method: str = None,
    is_primary: bool = None,
) -> int:
    """
    Add an enrichment source for a transaction.
    Does NOT overwrite existing sources - adds a new one.

    Args:
        transaction_id: TrueLayer transaction ID
        source_type: One of 'amazon', 'amazon_business', 'apple', 'gmail', 'manual'
        description: Product/service description from source
        source_id: FK to source table (amazon_orders.id, etc.)
        order_id: Original order/receipt ID
        line_items: Detailed items [{name, quantity, price}]
        confidence: Match confidence 0-100
        match_method: How the match was determined
        is_primary: If True, set as primary. If None, only set as primary if no other sources exist.

    Returns:
        ID of the created enrichment source, or existing ID if duplicate
    """
    with get_session() as session:
        # Determine if this should be primary
        if is_primary is None:
            # Check if any sources already exist for this transaction
            existing_count = (
                session.query(func.count(TransactionEnrichmentSource.id))
                .filter(
                    TransactionEnrichmentSource.truelayer_transaction_id
                    == transaction_id
                )
                .scalar()
            )
            is_primary = existing_count == 0

        # Convert line_items to JSON
        line_items_json = line_items if line_items else None

        stmt = (
            insert(TransactionEnrichmentSource)
            .values(
                truelayer_transaction_id=transaction_id,
                source_type=source_type,
                source_id=source_id,
                description=description,
                order_id=order_id,
                line_items=line_items_json,
                match_confidence=confidence,
                match_method=match_method,
                is_primary=is_primary,
            )
            .on_conflict_do_update(
                index_elements=["truelayer_transaction_id", "source_type", "source_id"],
                set_={
                    "description": description,
                    "order_id": order_id,
                    "line_items": line_items_json,
                    "match_confidence": confidence,
                    "match_method": match_method,
                    "updated_at": func.now(),
                },
            )
            .returning(TransactionEnrichmentSource.id)
        )

        result = session.execute(stmt)
        source_id = result.scalar_one()
        session.commit()
        return source_id


def get_transaction_enrichment_sources(transaction_id: int) -> list:
    """
    Get all enrichment sources for a transaction, ordered by primary then confidence.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        List of enrichment source dicts
    """
    with get_session() as session:
        sources = (
            session.query(TransactionEnrichmentSource)
            .filter(
                TransactionEnrichmentSource.truelayer_transaction_id == transaction_id
            )
            .order_by(
                TransactionEnrichmentSource.is_primary.desc(),
                TransactionEnrichmentSource.match_confidence.desc(),
                TransactionEnrichmentSource.created_at.asc(),
            )
            .all()
        )

        return [
            {
                "id": s.id,
                "source_type": s.source_type,
                "source_id": s.source_id,
                "description": s.description,
                "order_id": s.order_id,
                "line_items": s.line_items,
                "match_confidence": s.match_confidence,
                "match_method": s.match_method,
                "is_primary": s.is_primary,
                "user_verified": s.user_verified,
                "created_at": s.created_at,
            }
            for s in sources
        ]


def get_all_enrichment_sources_for_transactions(transaction_ids: list) -> dict:
    """
    Batch fetch enrichment sources for multiple transactions.

    Args:
        transaction_ids: List of TrueLayer transaction IDs

    Returns:
        Dict mapping transaction_id -> list of enrichment sources
    """
    if not transaction_ids:
        return {}

    with get_session() as session:
        sources = (
            session.query(TransactionEnrichmentSource)
            .filter(
                TransactionEnrichmentSource.truelayer_transaction_id.in_(
                    transaction_ids
                )
            )
            .order_by(
                TransactionEnrichmentSource.truelayer_transaction_id,
                TransactionEnrichmentSource.is_primary.desc(),
                TransactionEnrichmentSource.match_confidence.desc(),
            )
            .all()
        )

        result = {}
        for s in sources:
            txn_id = s.truelayer_transaction_id
            if txn_id not in result:
                result[txn_id] = []
            result[txn_id].append(
                {
                    "truelayer_transaction_id": s.truelayer_transaction_id,
                    "id": s.id,
                    "source_type": s.source_type,
                    "source_id": s.source_id,
                    "description": s.description,
                    "order_id": s.order_id,
                    "line_items": s.line_items,
                    "match_confidence": s.match_confidence,
                    "match_method": s.match_method,
                    "is_primary": s.is_primary,
                    "user_verified": s.user_verified,
                }
            )
        return result


def set_primary_enrichment_source(transaction_id: int, source_id: int) -> bool:
    """
    Set a specific enrichment source as primary for a transaction.
    Unsets any other primary source for the same transaction.

    Args:
        transaction_id: TrueLayer transaction ID
        source_id: Enrichment source ID to set as primary

    Returns:
        True if successful, False if source not found
    """
    with get_session() as session:
        # The trigger will handle unsetting other primaries
        updated = (
            session.query(TransactionEnrichmentSource)
            .filter(
                TransactionEnrichmentSource.id == source_id,
                TransactionEnrichmentSource.truelayer_transaction_id == transaction_id,
            )
            .update({"is_primary": True})
        )
        session.commit()
        return updated > 0


def get_primary_enrichment_description(transaction_id: int) -> str:
    """
    Get the primary enrichment description for a transaction.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Primary description string, or None if no sources
    """
    with get_session() as session:
        source = (
            session.query(TransactionEnrichmentSource.description)
            .filter(
                TransactionEnrichmentSource.truelayer_transaction_id == transaction_id
            )
            .order_by(
                TransactionEnrichmentSource.is_primary.desc(),
                TransactionEnrichmentSource.match_confidence.desc(),
            )
            .first()
        )
        return source[0] if source else None


def get_llm_enrichment_context(transaction_id: int) -> str:
    """
    Get combined context string from all enrichment sources for LLM prompt.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Combined string with all sources labeled, e.g.:
        "Amazon Products: iPhone 15 Pro | Email Receipt: Order #123 confirmed"
    """
    sources = get_transaction_enrichment_sources(transaction_id)
    if not sources:
        return None

    labels = {
        "amazon": "Amazon Products",
        "amazon_business": "Amazon Business",
        "apple": "Apple/App Store",
        "gmail": "Email Receipt",
        "manual": "Manual",
    }

    parts = []
    for source in sources:
        label = labels.get(source["source_type"], "Details")
        parts.append(f"{label}: {source['description']}")

    return " | ".join(parts)


def get_batch_llm_enrichment_context(transaction_ids: list) -> dict:
    """
    Batch fetch LLM enrichment context for multiple transactions.

    Args:
        transaction_ids: List of TrueLayer transaction IDs

    Returns:
        Dict mapping transaction_id -> combined context string
    """
    all_sources = get_all_enrichment_sources_for_transactions(transaction_ids)

    labels = {
        "amazon": "Amazon Products",
        "amazon_business": "Amazon Business",
        "apple": "Apple/App Store",
        "gmail": "Email Receipt",
        "manual": "Manual",
    }

    result = {}
    for txn_id, sources in all_sources.items():
        parts = []
        for source in sources:
            label = labels.get(source["source_type"], "Details")
            parts.append(f"{label}: {source['description']}")
        result[txn_id] = " | ".join(parts) if parts else None

    return result


def delete_enrichment_source(source_id: int) -> bool:
    """
    Delete an enrichment source by ID.

    Args:
        source_id: Enrichment source ID

    Returns:
        True if deleted, False if not found
    """
    with get_session() as session:
        deleted = (
            session.query(TransactionEnrichmentSource)
            .filter(TransactionEnrichmentSource.id == source_id)
            .delete()
        )
        session.commit()
        return deleted > 0


def get_enrichment_source_full_details(enrichment_source_id: int) -> dict | None:
    """
    Fetch full details from the source table for an enrichment source.

    Uses the polymorphic FK pattern (source_type + source_id) to query
    the appropriate source table (amazon_orders, apple_transactions, etc.)

    Args:
        enrichment_source_id: ID from transaction_enrichment_sources table

    Returns:
        Dict with enrichment source metadata plus full details from source table,
        or None if not found
    """
    with get_session() as session:
        # First, get the enrichment source record
        enrichment_source = session.get(
            TransactionEnrichmentSource, enrichment_source_id
        )

        if not enrichment_source:
            return None

        result = {
            "id": enrichment_source.id,
            "truelayer_transaction_id": enrichment_source.truelayer_transaction_id,
            "source_type": enrichment_source.source_type,
            "source_id": enrichment_source.source_id,
            "description": enrichment_source.description,
            "order_id": enrichment_source.order_id,
            "line_items": enrichment_source.line_items,
            "match_confidence": enrichment_source.match_confidence,
            "match_method": enrichment_source.match_method,
            "is_primary": enrichment_source.is_primary,
            "user_verified": enrichment_source.user_verified,
            "created_at": enrichment_source.created_at,
        }

        source_type = enrichment_source.source_type
        source_id = enrichment_source.source_id

        # If no source_id (manual entry), return just the enrichment data
        if source_id is None:
            result["source_details"] = None
            return result

        # Fetch full details from the appropriate source table
        source_details = None

        if source_type == "amazon":
            amazon_order = session.get(AmazonOrder, source_id)
            if amazon_order:
                source_details = {
                    "id": amazon_order.id,
                    "order_id": amazon_order.order_id,
                    "order_date": amazon_order.order_date,
                    "website": amazon_order.website,
                    "currency": amazon_order.currency,
                    "total_owed": amazon_order.total_owed,
                    "product_names": amazon_order.product_names,
                    "order_status": amazon_order.order_status,
                    "shipment_status": amazon_order.shipment_status,
                    "source_file": amazon_order.source_file,
                    "created_at": amazon_order.created_at,
                }
                # Parse product_names into line items
                if source_details.get("product_names"):
                    items = [
                        {"name": name.strip(), "quantity": 1}
                        for name in source_details["product_names"].split(",")
                    ]
                    source_details["parsed_line_items"] = items

        elif source_type == "amazon_business":
            business_order = session.get(AmazonBusinessOrder, source_id)
            if business_order:
                source_details = {
                    "id": business_order.id,
                    "order_id": business_order.order_id,
                    "order_date": business_order.order_date,
                    "region": business_order.region,
                    "purchase_order_number": business_order.purchase_order_number,
                    "order_status": business_order.order_status,
                    "buyer_name": business_order.buyer_name,
                    "buyer_email": business_order.buyer_email,
                    "subtotal": business_order.subtotal,
                    "tax": business_order.tax,
                    "shipping": business_order.shipping,
                    "net_total": business_order.net_total,
                    "currency": business_order.currency,
                    "item_count": business_order.item_count,
                    "product_summary": business_order.product_summary,
                    "created_at": business_order.created_at,
                }
                # Fetch line items
                line_items_query = (
                    session.query(AmazonBusinessLineItem)
                    .filter(
                        AmazonBusinessLineItem.order_id == source_details["order_id"]
                    )
                    .order_by(AmazonBusinessLineItem.id)
                    .all()
                )
                source_details["line_items"] = [
                    {
                        "line_item_id": item.line_item_id,
                        "asin": item.asin,
                        "title": item.title,
                        "brand": item.brand,
                        "category": item.category,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "total_price": item.total_price,
                        "seller_name": item.seller_name,
                    }
                    for item in line_items_query
                ]

        elif source_type == "apple":
            apple_txn = session.get(AppleTransaction, source_id)
            if apple_txn:
                source_details = {
                    "id": apple_txn.id,
                    "order_id": apple_txn.order_id,
                    "order_date": apple_txn.order_date,
                    "total_amount": apple_txn.total_amount,
                    "currency": apple_txn.currency,
                    "app_names": apple_txn.app_names,
                    "publishers": apple_txn.publishers,
                    "item_count": apple_txn.item_count,
                    "source_file": apple_txn.source_file,
                    "created_at": apple_txn.created_at,
                }
                # Parse app_names into line items
                if source_details.get("app_names"):
                    items = [
                        {"name": name.strip(), "quantity": 1}
                        for name in source_details["app_names"].split(",")
                    ]
                    source_details["parsed_line_items"] = items

        elif source_type == "gmail":
            gmail_receipt = session.get(GmailReceipt, source_id)
            if gmail_receipt:
                source_details = {
                    "id": gmail_receipt.id,
                    "connection_id": gmail_receipt.connection_id,
                    "message_id": gmail_receipt.message_id,
                    "thread_id": gmail_receipt.thread_id,
                    "sender_email": gmail_receipt.sender_email,
                    "sender_name": gmail_receipt.sender_name,
                    "subject": gmail_receipt.subject,
                    "received_at": gmail_receipt.received_at,
                    "merchant_name": gmail_receipt.merchant_name,
                    "merchant_domain": gmail_receipt.merchant_domain,
                    "order_id": gmail_receipt.order_id,
                    "total_amount": gmail_receipt.total_amount,
                    "currency_code": gmail_receipt.currency_code,
                    "receipt_date": gmail_receipt.receipt_date,
                    "line_items": gmail_receipt.line_items,
                    "parse_method": gmail_receipt.parse_method,
                    "parse_confidence": gmail_receipt.parse_confidence,
                    "parsing_status": gmail_receipt.parsing_status,
                    "created_at": gmail_receipt.created_at,
                }
                # Fetch PDF attachments
                pdf_attachments_query = (
                    session.query(PDFAttachment)
                    .filter(PDFAttachment.gmail_receipt_id == source_id)
                    .order_by(PDFAttachment.created_at)
                    .all()
                )
                source_details["pdf_attachments"] = [
                    {
                        "id": pdf.id,
                        "filename": pdf.filename,
                        "size_bytes": pdf.size_bytes,
                        "mime_type": pdf.mime_type,
                        "object_key": pdf.object_key,
                        "created_at": pdf.created_at,
                    }
                    for pdf in pdf_attachments_query
                ]

        result["source_details"] = source_details
        return result


def clear_amazon_orders():
    """Delete all Amazon orders and matches from database."""
    with get_session() as session:
        # Count before deletion
        orders_count = session.query(func.count(AmazonOrder.id)).scalar()
        matches_count = session.query(func.count(AmazonTransactionMatch.id)).scalar()

        # Delete matches first (foreign key)
        session.query(AmazonTransactionMatch).delete()

        # Delete orders
        session.query(AmazonOrder).delete()

        session.commit()
        return (orders_count, matches_count)


# ============================================================================


# ============================================================================
# PRE-ENRICHMENT STATUS FUNCTIONS
# ============================================================================


# ============================================================================
# ENRICHMENT REQUIRED FUNCTIONS
# ============================================================================


def toggle_enrichment_required(transaction_id: int) -> dict:
    """Toggle the enrichment_required flag for a transaction.

    Args:
        transaction_id: ID of the transaction to toggle

    Returns:
        Dict with new state: {id, enrichment_required, enrichment_source}
    """
    with get_session() as session:
        # Toggle the flag and return new state
        txn = session.get(TrueLayerTransaction, transaction_id)
        if not txn:
            return None

        # Toggle using COALESCE logic
        txn.enrichment_required = not (txn.enrichment_required or False)

        # Extract enrichment source from metadata
        enrichment_source = None
        if txn.metadata and "enrichment" in txn.metadata:
            enrichment_source = txn.metadata["enrichment"].get("llm_provider")

        session.commit()

        return {
            "id": txn.id,
            "enrichment_required": txn.enrichment_required,
            "enrichment_source": enrichment_source,
        }


def set_enrichment_required(transaction_id: int, required: bool) -> bool:
    """Set enrichment_required status for a transaction.

    Args:
        transaction_id: ID of the transaction
        required: Whether enrichment is required

    Returns:
        True if updated successfully
    """
    with get_session() as session:
        updated = (
            session.query(TrueLayerTransaction)
            .filter(TrueLayerTransaction.id == transaction_id)
            .update({"enrichment_required": required})
        )
        session.commit()
        return updated > 0


def get_required_unenriched_transactions(limit: int = None) -> list:
    """Get transactions where enrichment_required=TRUE AND not yet enriched.

    Args:
        limit: Optional limit on number of transactions to return

    Returns:
        List of transaction dictionaries
    """
    with get_session() as session:
        query = session.query(TrueLayerTransaction).filter(
            TrueLayerTransaction.enrichment_required == True  # noqa: E712
        )

        # Filter for unenriched: metadata.enrichment is NULL OR primary_category is NULL
        # This requires raw SQL filter since SQLAlchemy doesn't handle nested JSONB well
        query = query.filter(
            text(
                "(metadata->'enrichment' IS NULL OR metadata->'enrichment'->>'primary_category' IS NULL)"
            )
        )

        query = query.order_by(TrueLayerTransaction.timestamp.desc())

        if limit:
            query = query.limit(limit)

        txns = query.all()
        return [
            {
                "id": t.id,
                "transaction_id": t.transaction_id,
                "timestamp": t.timestamp,
                "description": t.description,
                "transaction_type": t.transaction_type,
                "transaction_category": t.transaction_category,
                "transaction_classification": t.transaction_classification,
                "amount": t.amount,
                "currency": t.currency,
                "running_balance_amount": t.running_balance_amount,
                "running_balance_currency": t.running_balance_currency,
                "merchant_name": t.merchant_name,
                "normalised_provider_category": t.normalised_provider_category,
                "provider_transaction_category": t.provider_transaction_category,
                "metadata": t.metadata,
                "account_id": t.account_id,
                "enrichment_required": t.enrichment_required,
                "pre_enrichment_status": t.pre_enrichment_status,
            }
            for t in txns
        ]


def clear_enrichment_required_after_success(transaction_id: int) -> bool:
    """Clear enrichment_required flag after successful enrichment.

    Called automatically after enrichment completes.

    Args:
        transaction_id: ID of the transaction

    Returns:
        True if updated successfully
    """
    with get_session() as session:
        updated = (
            session.query(TrueLayerTransaction)
            .filter(TrueLayerTransaction.id == transaction_id)
            .update({"enrichment_required": False})
        )
        session.commit()
        return updated > 0


# ============================================================================

# ============================================================================
# LLM ENRICHMENT CACHE
# ============================================================================


def get_enrichment_from_cache(description, direction):
    """
    Retrieve cached enrichment for a transaction description.

    Args:
        description: Transaction description to look up
        direction: Transaction direction ('in' or 'out')

    Returns:
        Enrichment object or None if not cached
    """
    with get_session() as session:
        cache_entry = (
            session.query(EnrichmentCache)
            .filter(
                EnrichmentCache.transaction_description == description,
                EnrichmentCache.transaction_direction == direction,
            )
            .first()
        )

        if cache_entry and cache_entry.enrichment_data:
            try:
                from mcp.llm_enricher import EnrichmentResult

                data = json.loads(cache_entry.enrichment_data)
                return EnrichmentResult(**data)
            except (json.JSONDecodeError, Exception):
                return None
    return None


def cache_enrichment(description, direction, enrichment, provider, model):
    """
    Cache enrichment result for a transaction description.

    Args:
        description: Transaction description
        direction: Transaction direction ('in' or 'out')
        enrichment: EnrichmentResult object with enrichment data
        provider: LLM provider name
        model: Model name used

    Returns:
        Cache entry ID
    """
    from sqlalchemy.dialects.postgresql import insert

    with get_session() as session:
        enrichment_json = json.dumps(enrichment.__dict__)

        stmt = (
            insert(EnrichmentCache)
            .values(
                transaction_description=description,
                transaction_direction=direction,
                enrichment_data=enrichment_json,
                provider=provider,
                model=model,
            )
            .on_conflict_do_update(
                index_elements=["transaction_description", "transaction_direction"],
                set_={
                    "enrichment_data": enrichment_json,
                    "provider": provider,
                    "model": model,
                    "cached_at": func.current_timestamp(),
                },
            )
            .returning(EnrichmentCache.id)
        )

        result = session.execute(stmt)
        cache_id = result.scalar_one()
        session.commit()
        return cache_id


def get_failed_enrichment_transaction_ids() -> list:
    """Get transaction IDs that have failed enrichments.

    Returns:
        List of transaction IDs
    """
    with get_session() as session:
        transactions = (
            session.query(TrueLayerTransaction.id)
            .filter(text("metadata->'enrichment'->>'status' = 'failed'"))
            .all()
        )
        return [txn[0] for txn in transactions]


# ============================================================================
# PRE-ENRICHMENT STATUS TRACKING
# ============================================================================


def update_pre_enrichment_status(transaction_id: int, status: str) -> bool:
    """Update the pre_enrichment_status for a TrueLayer transaction.

    Args:
        transaction_id: The database ID of the transaction
        status: New status ('None', 'Matched', 'Apple', 'AMZN', 'AMZN RTN')

    Returns:
        True if update was successful, False otherwise
    """
    with get_session() as session:
        result = (
            session.query(TrueLayerTransaction)
            .filter(TrueLayerTransaction.id == transaction_id)
            .update({"pre_enrichment_status": status})
        )
        session.commit()
        return result > 0


def get_identified_summary() -> dict:
    """Get count of identified transactions by vendor (matched + unmatched).

    'Identified' = transactions that pattern-match vendor descriptions OR are in match tables.
    This ensures Identified >= Matched is always true.

    Returns:
        Dictionary with counts: {'Apple': N, 'AMZN': N, 'AMZN RTN': N, 'total': N}
    """
    with get_session() as session:
        # Amazon Purchases: status='AMZN' OR in truelayer_amazon_transaction_matches
        amazon_count = (
            session.query(func.count(func.distinct(TrueLayerTransaction.id)))
            .outerjoin(
                AmazonTransactionMatch,
                TrueLayerTransaction.id
                == AmazonTransactionMatch.truelayer_transaction_id,
            )
            .filter(
                (TrueLayerTransaction.pre_enrichment_status == "AMZN")
                | (AmazonTransactionMatch.id.is_not(None))
            )
            .scalar()
        )

        # Apple: status='Apple' OR in truelayer_apple_transaction_matches
        apple_count = (
            session.query(func.count(func.distinct(TrueLayerTransaction.id)))
            .outerjoin(
                AppleTransactionMatch,
                TrueLayerTransaction.id
                == AppleTransactionMatch.truelayer_transaction_id,
            )
            .filter(
                (TrueLayerTransaction.pre_enrichment_status == "Apple")
                | (AppleTransactionMatch.id.is_not(None))
            )
            .scalar()
        )

        # Amazon Returns: status='AMZN RTN' OR referenced in amazon_returns.refund_transaction_id
        returns_count = (
            session.query(func.count(func.distinct(TrueLayerTransaction.id)))
            .outerjoin(
                AmazonReturn,
                TrueLayerTransaction.id == AmazonReturn.refund_transaction_id,
            )
            .filter(
                (TrueLayerTransaction.pre_enrichment_status == "AMZN RTN")
                | (AmazonReturn.refund_transaction_id.is_not(None))
            )
            .scalar()
        )

        return {
            "AMZN": amazon_count,
            "Apple": apple_count,
            "AMZN RTN": returns_count,
            "total": amazon_count + apple_count + returns_count,
        }


def backfill_pre_enrichment_status() -> dict:
    """Backfill pre_enrichment_status for all existing transactions.

    Analyzes all transactions and sets their status based on:
    1. If already matched (in match tables) -> 'Matched'
    2. If description matches patterns -> 'Apple', 'AMZN', 'AMZN RTN'
    3. Otherwise -> 'None'

    Returns:
        Dictionary with counts of each status assigned
    """
    from mcp.pre_enrichment_detector import detect_pre_enrichment_status

    with get_session() as session:
        # Get all TrueLayer transactions
        transactions = session.query(
            TrueLayerTransaction.id,
            TrueLayerTransaction.description,
            TrueLayerTransaction.merchant_name,
            TrueLayerTransaction.transaction_type,
        ).all()

        counts = {"None": 0, "Apple": 0, "AMZN": 0, "AMZN RTN": 0, "Matched": 0}

        for txn in transactions:
            # Check if already matched in Amazon matches table
            amazon_matched = (
                session.query(AmazonTransactionMatch)
                .filter(AmazonTransactionMatch.truelayer_transaction_id == txn.id)
                .first()
                is not None
            )

            # Check if already matched in Apple matches table
            apple_matched = (
                session.query(AppleTransactionMatch)
                .filter(AppleTransactionMatch.truelayer_transaction_id == txn.id)
                .first()
                is not None
            )

            if amazon_matched or apple_matched:
                status = "Matched"
            else:
                status = detect_pre_enrichment_status(
                    txn.description,
                    txn.merchant_name,
                    txn.transaction_type,
                )

            # Update the transaction status
            session.query(TrueLayerTransaction).filter(
                TrueLayerTransaction.id == txn.id
            ).update({"pre_enrichment_status": status})

            counts[status] += 1

        session.commit()
        return counts
