"""
Transaction Enrichment - Database Operations

Handles multi-source transaction enrichment, enrichment status tracking,
and enrichment job management.

Migrated to SQLAlchemy from psycopg2.
"""

import json

from sqlalchemy import func
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
from .models.enrichment import (
    EnrichmentCache,
    LLMEnrichmentResult,
    RuleEnrichmentResult,
    TransactionEnrichmentSource,
)
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
        new_value = not (txn.enrichment_required or False)
        txn.enrichment_required = new_value

        session.commit()

    # Get enrichment source from dedicated tables
    enrichment = get_combined_enrichment(transaction_id)
    enrichment_source = enrichment.get("source") if enrichment else None

    return {
        "id": transaction_id,
        "enrichment_required": new_value,
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

    Checks the dedicated enrichment tables (rule_enrichment_results,
    llm_enrichment_results, transaction_enrichment_sources) to determine
    if a transaction has been enriched.

    Args:
        limit: Optional limit on number of transactions to return

    Returns:
        List of transaction dictionaries
    """
    with get_session() as session:
        # Get IDs that have enrichment in any table
        rule_ids = session.query(RuleEnrichmentResult.truelayer_transaction_id)
        llm_ids = session.query(LLMEnrichmentResult.truelayer_transaction_id)
        external_ids = session.query(
            TransactionEnrichmentSource.truelayer_transaction_id
        )

        # Union all enriched IDs
        enriched_ids = rule_ids.union(llm_ids).union(external_ids)

        # Query for transactions that need enrichment but don't have it yet
        query = (
            session.query(TrueLayerTransaction)
            .filter(
                TrueLayerTransaction.enrichment_required == True,  # noqa: E712
                ~TrueLayerTransaction.id.in_(enriched_ids),
            )
            .order_by(TrueLayerTransaction.timestamp.desc())
        )

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
    """Get transaction IDs that have enrichment_required=TRUE but no enrichment.

    In the new enrichment architecture, failed enrichments aren't stored.
    This function returns transactions that were marked as needing enrichment
    but don't have entries in any enrichment table (rule, llm, or external).

    Returns:
        List of transaction IDs
    """
    with get_session() as session:
        # Get IDs that have enrichment in any table
        rule_ids = session.query(RuleEnrichmentResult.truelayer_transaction_id)
        llm_ids = session.query(LLMEnrichmentResult.truelayer_transaction_id)
        external_ids = session.query(
            TransactionEnrichmentSource.truelayer_transaction_id
        )

        # Union all enriched IDs
        enriched_ids = rule_ids.union(llm_ids).union(external_ids)

        # Find transactions needing enrichment but without any enrichment data
        transactions = (
            session.query(TrueLayerTransaction.id)
            .filter(
                TrueLayerTransaction.enrichment_required == True,  # noqa: E712
                ~TrueLayerTransaction.id.in_(enriched_ids),
            )
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


# ============================================================================
# RULE-BASED ENRICHMENT RESULTS
# Stores enrichment from category rules, merchant normalizations, direct debits
# ============================================================================


def save_rule_enrichment(
    transaction_id: int,
    primary_category: str,
    rule_type: str,
    subcategory: str | None = None,
    essential_discretionary: str | None = None,
    merchant_clean_name: str | None = None,
    merchant_type: str | None = None,
    matched_rule_id: int | None = None,
    matched_rule_name: str | None = None,
    matched_merchant_id: int | None = None,
    matched_merchant_name: str | None = None,
    confidence_score: float = 1.0,
) -> int:
    """
    Save or update rule-based enrichment for a transaction.
    Uses UPSERT - updates if exists, inserts if new.

    Args:
        transaction_id: TrueLayer transaction ID
        primary_category: Category assigned by rule
        rule_type: One of 'category_rule', 'merchant_rule', 'direct_debit'
        subcategory: Optional subcategory
        essential_discretionary: 'Essential' or 'Discretionary'
        merchant_clean_name: Normalized merchant name
        merchant_type: Type of merchant
        matched_rule_id: ID of the CategoryRule that matched
        matched_rule_name: Name of the rule (denormalized)
        matched_merchant_id: ID of the MerchantNormalization that matched
        matched_merchant_name: Merchant name from normalization
        confidence_score: Confidence (rules are deterministic, default 1.0)

    Returns:
        ID of the enrichment record
    """
    with get_session() as session:
        stmt = (
            insert(RuleEnrichmentResult)
            .values(
                truelayer_transaction_id=transaction_id,
                primary_category=primary_category,
                subcategory=subcategory,
                essential_discretionary=essential_discretionary,
                merchant_clean_name=merchant_clean_name,
                merchant_type=merchant_type,
                rule_type=rule_type,
                matched_rule_id=matched_rule_id,
                matched_rule_name=matched_rule_name,
                matched_merchant_id=matched_merchant_id,
                matched_merchant_name=matched_merchant_name,
                confidence_score=confidence_score,
            )
            .on_conflict_do_update(
                index_elements=["truelayer_transaction_id"],
                set_={
                    "primary_category": primary_category,
                    "subcategory": subcategory,
                    "essential_discretionary": essential_discretionary,
                    "merchant_clean_name": merchant_clean_name,
                    "merchant_type": merchant_type,
                    "rule_type": rule_type,
                    "matched_rule_id": matched_rule_id,
                    "matched_rule_name": matched_rule_name,
                    "matched_merchant_id": matched_merchant_id,
                    "matched_merchant_name": matched_merchant_name,
                    "confidence_score": confidence_score,
                    "updated_at": func.now(),
                },
            )
            .returning(RuleEnrichmentResult.id)
        )

        result = session.execute(stmt)
        enrichment_id = result.scalar_one()
        session.commit()
        return enrichment_id


def get_rule_enrichment(transaction_id: int) -> dict | None:
    """
    Get rule-based enrichment for a transaction.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Dict with enrichment data or None if not enriched
    """
    with get_session() as session:
        result = (
            session.query(RuleEnrichmentResult)
            .filter(RuleEnrichmentResult.truelayer_transaction_id == transaction_id)
            .first()
        )

        if not result:
            return None

        return {
            "id": result.id,
            "primary_category": result.primary_category,
            "subcategory": result.subcategory,
            "essential_discretionary": result.essential_discretionary,
            "merchant_clean_name": result.merchant_clean_name,
            "merchant_type": result.merchant_type,
            "rule_type": result.rule_type,
            "matched_rule_id": result.matched_rule_id,
            "matched_rule_name": result.matched_rule_name,
            "matched_merchant_id": result.matched_merchant_id,
            "matched_merchant_name": result.matched_merchant_name,
            "confidence_score": float(result.confidence_score),
            "created_at": result.created_at,
            "updated_at": result.updated_at,
            "enrichment_source": "rule",
        }


def delete_rule_enrichment(transaction_id: int) -> bool:
    """
    Delete rule-based enrichment for a transaction.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        True if deleted, False if not found
    """
    with get_session() as session:
        result = (
            session.query(RuleEnrichmentResult)
            .filter(RuleEnrichmentResult.truelayer_transaction_id == transaction_id)
            .delete()
        )
        session.commit()
        return result > 0


# ============================================================================
# LLM-BASED ENRICHMENT RESULTS
# Stores enrichment from LLM inference (Claude, GPT, etc.)
# ============================================================================


def save_llm_enrichment(
    transaction_id: int,
    primary_category: str,
    llm_provider: str,
    llm_model: str,
    subcategory: str | None = None,
    essential_discretionary: str | None = None,
    merchant_clean_name: str | None = None,
    merchant_type: str | None = None,
    payment_method: str | None = None,
    payment_method_subtype: str | None = None,
    purchase_date: str | None = None,
    confidence_score: float | None = None,
    cache_id: int | None = None,
    enrichment_source: str = "llm",
) -> int:
    """
    Save or update LLM-based enrichment for a transaction.
    Uses UPSERT - updates if exists, inserts if new.

    Args:
        transaction_id: TrueLayer transaction ID
        primary_category: Category assigned by LLM
        llm_provider: Provider name (e.g., 'anthropic', 'openai')
        llm_model: Model name (e.g., 'claude-3-haiku')
        subcategory: Optional subcategory
        essential_discretionary: 'Essential' or 'Discretionary'
        merchant_clean_name: Cleaned merchant name
        merchant_type: Type of merchant
        payment_method: Payment method inferred
        payment_method_subtype: Subtype of payment
        purchase_date: Inferred purchase date (YYYY-MM-DD)
        confidence_score: LLM confidence (0-1)
        cache_id: ID in llm_enrichment_cache if from cache
        enrichment_source: 'llm' or 'cache'

    Returns:
        ID of the enrichment record
    """
    from datetime import datetime

    # Parse purchase_date if string
    parsed_date = None
    if purchase_date:
        try:
            if isinstance(purchase_date, str):
                parsed_date = datetime.strptime(purchase_date, "%Y-%m-%d").date()
            else:
                parsed_date = purchase_date
        except ValueError:
            parsed_date = None

    with get_session() as session:
        stmt = (
            insert(LLMEnrichmentResult)
            .values(
                truelayer_transaction_id=transaction_id,
                primary_category=primary_category,
                subcategory=subcategory,
                essential_discretionary=essential_discretionary,
                merchant_clean_name=merchant_clean_name,
                merchant_type=merchant_type,
                payment_method=payment_method,
                payment_method_subtype=payment_method_subtype,
                purchase_date=parsed_date,
                llm_provider=llm_provider,
                llm_model=llm_model,
                confidence_score=confidence_score,
                cache_id=cache_id,
                enrichment_source=enrichment_source,
            )
            .on_conflict_do_update(
                index_elements=["truelayer_transaction_id"],
                set_={
                    "primary_category": primary_category,
                    "subcategory": subcategory,
                    "essential_discretionary": essential_discretionary,
                    "merchant_clean_name": merchant_clean_name,
                    "merchant_type": merchant_type,
                    "payment_method": payment_method,
                    "payment_method_subtype": payment_method_subtype,
                    "purchase_date": parsed_date,
                    "llm_provider": llm_provider,
                    "llm_model": llm_model,
                    "confidence_score": confidence_score,
                    "cache_id": cache_id,
                    "enrichment_source": enrichment_source,
                    "updated_at": func.now(),
                },
            )
            .returning(LLMEnrichmentResult.id)
        )

        result = session.execute(stmt)
        enrichment_id = result.scalar_one()
        session.commit()
        return enrichment_id


def get_llm_enrichment(transaction_id: int) -> dict | None:
    """
    Get LLM-based enrichment for a transaction.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Dict with enrichment data or None if not enriched
    """
    with get_session() as session:
        result = (
            session.query(LLMEnrichmentResult)
            .filter(LLMEnrichmentResult.truelayer_transaction_id == transaction_id)
            .first()
        )

        if not result:
            return None

        return {
            "id": result.id,
            "primary_category": result.primary_category,
            "subcategory": result.subcategory,
            "essential_discretionary": result.essential_discretionary,
            "merchant_clean_name": result.merchant_clean_name,
            "merchant_type": result.merchant_type,
            "payment_method": result.payment_method,
            "payment_method_subtype": result.payment_method_subtype,
            "purchase_date": str(result.purchase_date)
            if result.purchase_date
            else None,
            "llm_provider": result.llm_provider,
            "llm_model": result.llm_model,
            "confidence_score": float(result.confidence_score)
            if result.confidence_score
            else None,
            "cache_id": result.cache_id,
            "enrichment_source": result.enrichment_source,
            "created_at": result.created_at,
            "updated_at": result.updated_at,
        }


def delete_llm_enrichment(transaction_id: int) -> bool:
    """
    Delete LLM-based enrichment for a transaction.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        True if deleted, False if not found
    """
    with get_session() as session:
        result = (
            session.query(LLMEnrichmentResult)
            .filter(LLMEnrichmentResult.truelayer_transaction_id == transaction_id)
            .delete()
        )
        session.commit()
        return result > 0


# ============================================================================
# COMBINED ENRICHMENT QUERIES
# Get enrichment from all sources with priority
# ============================================================================


def get_combined_enrichment(transaction_id: int) -> dict | None:
    """
    Get combined enrichment for a transaction from all sources.
    Priority: Rule > LLM > External Sources

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        Dict with combined enrichment data or None if no enrichment
    """
    # Try rule enrichment first (highest priority)
    rule_enrichment = get_rule_enrichment(transaction_id)
    if rule_enrichment:
        return rule_enrichment

    # Try LLM enrichment second
    llm_enrichment = get_llm_enrichment(transaction_id)
    if llm_enrichment:
        return llm_enrichment

    # Try external sources (Amazon, Apple, Gmail)
    sources = get_transaction_enrichment_sources(transaction_id)
    if sources:
        # Get primary source or first source
        primary = next((s for s in sources if s.get("is_primary")), sources[0])
        return {
            "primary_category": None,  # External sources don't have category
            "subcategory": None,
            "merchant_clean_name": primary.get("description"),
            "enrichment_source": primary.get("source_type"),
            "external_source": primary,
        }

    return None


def is_transaction_enriched_new(transaction_id: int) -> bool:
    """
    Check if a transaction has any enrichment data.
    Checks rule, LLM, and external source tables.

    Args:
        transaction_id: TrueLayer transaction ID

    Returns:
        True if enriched from any source
    """
    with get_session() as session:
        # Check rule enrichment
        rule_exists = (
            session.query(RuleEnrichmentResult)
            .filter(RuleEnrichmentResult.truelayer_transaction_id == transaction_id)
            .first()
            is not None
        )
        if rule_exists:
            return True

        # Check LLM enrichment
        llm_exists = (
            session.query(LLMEnrichmentResult)
            .filter(LLMEnrichmentResult.truelayer_transaction_id == transaction_id)
            .first()
            is not None
        )
        if llm_exists:
            return True

        # Check external sources
        return (
            session.query(TransactionEnrichmentSource)
            .filter(
                TransactionEnrichmentSource.truelayer_transaction_id == transaction_id
            )
            .first()
            is not None
        )


def get_unenriched_transactions_new(
    limit: int = 100,
    exclude_matched: bool = True,
) -> list[dict]:
    """
    Get transactions that have no enrichment from any source.
    Used for LLM enrichment queue.

    Args:
        limit: Maximum number of transactions to return
        exclude_matched: If True, exclude transactions with external matches

    Returns:
        List of transaction dicts
    """
    with get_session() as session:
        # Build subqueries for exclusion
        rule_subq = session.query(RuleEnrichmentResult.truelayer_transaction_id)
        llm_subq = session.query(LLMEnrichmentResult.truelayer_transaction_id)

        query = session.query(TrueLayerTransaction).filter(
            ~TrueLayerTransaction.id.in_(rule_subq),
            ~TrueLayerTransaction.id.in_(llm_subq),
        )

        if exclude_matched:
            external_subq = session.query(
                TransactionEnrichmentSource.truelayer_transaction_id
            )
            query = query.filter(~TrueLayerTransaction.id.in_(external_subq))

        transactions = query.limit(limit).all()

        return [
            {
                "id": txn.id,
                "description": txn.description,
                "amount": float(txn.amount) if txn.amount else None,
                "transaction_type": txn.transaction_type,
                "timestamp": txn.timestamp,
            }
            for txn in transactions
        ]
