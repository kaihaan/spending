"""
Amazon Returns Matcher MCP Component
Matches returns to original orders and transactions.
Updates transaction descriptions and marks items as returned.
"""

from datetime import UTC, datetime, timedelta

from backend.database.amazon import (
    get_amazon_order_by_id,
    get_amazon_returns,
    link_return_to_transactions,
)
from backend.database.enrichment import (
    add_enrichment_source,
    update_pre_enrichment_status,
)


def match_all_returns():
    """
    Match all unmatched returns to their original orders and transactions.

    Returns:
        Dictionary with matching statistics
    """
    # Get all returns that haven't been matched yet
    all_returns = get_amazon_returns()
    unmatched_returns = [r for r in all_returns if r["original_transaction_id"] is None]

    if not unmatched_returns:
        return {"total_processed": 0, "matched": 0, "unmatched": 0, "matches": []}

    matched_count = 0
    matches_details = []

    for ret in unmatched_returns:
        # Try to find matches
        match_result = match_single_return(ret)

        if match_result and match_result["success"]:
            matched_count += 1
            matches_details.append(
                {
                    "return_id": ret["id"],
                    "order_id": ret["order_id"],
                    "amount_refunded": ret["amount_refunded"],
                    "original_transaction_id": match_result["original_transaction_id"],
                    "refund_transaction_id": match_result["refund_transaction_id"],
                }
            )

    return {
        "total_processed": len(unmatched_returns),
        "matched": matched_count,
        "unmatched": len(unmatched_returns) - matched_count,
        "matches": matches_details,
    }


def match_single_return(ret):
    """
    Match a single return to its original order and transactions.

    Args:
        ret: Return dictionary

    Returns:
        Match result dictionary or None
    """
    # Step 1: Find the original Amazon order by order_id
    order = get_amazon_order_by_id(ret["order_id"])

    if not order:
        return {"success": False, "reason": "Order not found"}

    # Step 2: Find the original purchase transaction
    # Look for transaction matched to this order
    original_transaction = find_transaction_for_order(order["id"])

    if not original_transaction:
        return {"success": False, "reason": "Original transaction not found"}

    # Step 3: Find the refund transaction
    # Look for positive amount transaction near the refund date
    refund_transaction = find_refund_transaction(ret)

    if not refund_transaction:
        return {"success": False, "reason": "Refund transaction not found"}

    # Step 4: Add enrichment source for refund transaction
    add_refund_enrichment_source(
        refund_transaction["id"], order["product_names"], ret["order_id"]
    )

    # Step 4.5: Update pre-enrichment status to 'Matched' for refund transaction
    update_pre_enrichment_status(refund_transaction["id"], "Matched")

    # Step 5: Mark original transaction as returned (updates enrichment source description)
    mark_original_as_returned(original_transaction["id"])

    # Step 6: Link return to transactions
    # Now that FK constraints are removed, we can link TrueLayer transactions
    link_return_to_transactions(
        ret["id"], original_transaction["id"], refund_transaction["id"]
    )

    return {
        "success": True,
        "original_transaction_id": original_transaction["id"],
        "refund_transaction_id": refund_transaction["id"],
        "source": "truelayer",
    }


def find_transaction_for_order(order_db_id):
    """
    Find the bank transaction that was matched to a specific Amazon order.
    Checks TrueLayer transactions only (legacy table dropped).

    Args:
        order_db_id: Database ID of the Amazon order

    Returns:
        Transaction dictionary or None (with 'source' field set to 'truelayer')
    """
    from sqlalchemy import text

    from backend.database.base import get_session

    with get_session() as session:
        # Check TrueLayer transactions with Amazon matches
        result = session.execute(
            text("""
                SELECT tt.*, 'truelayer' as source
                FROM truelayer_transactions tt
                JOIN truelayer_amazon_transaction_matches tatm
                    ON tt.id = tatm.truelayer_transaction_id
                WHERE tatm.amazon_order_id = :order_id
            """),
            {"order_id": order_db_id},
        ).first()

        return dict(result._mapping) if result else None


def find_refund_transaction(ret):
    """
    Find the bank transaction representing the refund (OPTIMIZED - SQL filtering).
    Looks for positive amount (credit) near the refund completion date.

    Args:
        ret: Return dictionary

    Returns:
        Transaction dictionary or None
    """
    from sqlalchemy import text

    from backend.database.base import get_session

    # Parse refund date
    try:
        refund_date_val = ret["refund_completion_date"]
        if isinstance(refund_date_val, datetime):
            refund_date = refund_date_val
            if refund_date.tzinfo is None:
                refund_date = refund_date.replace(tzinfo=UTC)
        elif isinstance(refund_date_val, type(datetime.now().date())):
            refund_date = datetime.combine(
                refund_date_val, datetime.min.time(), tzinfo=UTC
            )
        else:
            refund_date = datetime.strptime(str(refund_date_val), "%Y-%m-%d").replace(
                tzinfo=UTC
            )
    except Exception:  # Fixed: was bare except
        return None

    amount_refunded = abs(ret["amount_refunded"])

    # Use SQL to filter transactions (not Python loops) - MASSIVE performance improvement
    with get_session() as session:
        # SQL does the filtering - only fetch matching candidates
        results = session.execute(
            text("""
                SELECT *
                FROM truelayer_transactions
                WHERE transaction_type = 'CREDIT'
                  AND amount = :amount
                  AND (UPPER(merchant_name) LIKE '%AMAZON%'
                       OR UPPER(merchant_name) LIKE '%AMZN%'
                       OR UPPER(description) LIKE '%AMAZON%'
                       OR UPPER(description) LIKE '%AMZN%')
                  AND timestamp BETWEEN :start_date AND :end_date
                ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - :refund_date)))
                LIMIT 5
            """),
            {
                "amount": amount_refunded,
                "start_date": refund_date - timedelta(days=7),
                "end_date": refund_date + timedelta(days=3),
                "refund_date": refund_date,
            },
        ).fetchall()

        candidates = [dict(row._mapping) for row in results]

    if not candidates:
        return None

    # Return best match (already sorted by date proximity in SQL)
    best_match = dict(candidates[0])

    # Normalize field names for compatibility
    best_match["source"] = "truelayer"
    best_match["date"] = best_match.get("timestamp")
    best_match["merchant"] = best_match.get("merchant_name")

    return best_match


def amounts_match(amount1, amount2, tolerance=0.01):
    """
    Check if two amounts match (exact match with tiny tolerance for floating point).

    Args:
        amount1: First amount
        amount2: Second amount
        tolerance: Maximum difference allowed (default 0.01 for rounding)

    Returns:
        Boolean indicating if amounts match
    """
    return abs(abs(amount1) - abs(amount2)) < tolerance


def add_refund_enrichment_source(transaction_id, order_product_names, amazon_order_id):
    """Add an enrichment source entry for a refund transaction."""
    description = (
        f"[REFUND] {order_product_names}" if order_product_names else "[REFUND]"
    )

    # Use add_enrichment_source function from enrichment module
    add_enrichment_source(
        transaction_id=transaction_id,
        source_type="amazon",
        description=description,
        order_id=amazon_order_id,
        match_confidence=100,
        match_method="return_match",
        is_primary=True,
    )
    return True


def mark_original_as_returned(transaction_id):
    """Mark the original transaction as returned by updating its enrichment source description."""
    from datetime import datetime

    from backend.database.base import get_session
    from backend.database.models.enrichment import TransactionEnrichmentSource
    from backend.database.models.truelayer import TrueLayerTransaction

    with get_session() as session:
        # Check if there's an existing enrichment source
        enrichment = (
            session.query(TransactionEnrichmentSource)
            .filter(
                TransactionEnrichmentSource.truelayer_transaction_id == transaction_id,
                TransactionEnrichmentSource.is_primary == True,  # noqa: E712
            )
            .first()
        )

        if enrichment:
            current_desc = enrichment.description or ""
            if not current_desc.startswith("[RETURNED] "):
                enrichment.description = f"[RETURNED] {current_desc}"
                enrichment.updated_at = datetime.now(UTC)
                session.commit()
                return True
        else:
            # No enrichment source exists, get description from transaction and create one
            txn = (
                session.query(TrueLayerTransaction)
                .filter(TrueLayerTransaction.id == transaction_id)
                .first()
            )

            if txn:
                desc = txn.description or ""
                new_enrichment = TransactionEnrichmentSource(
                    truelayer_transaction_id=transaction_id,
                    source_type="manual",
                    description=f"[RETURNED] {desc}",
                    match_confidence=100,
                    match_method="return_original",
                    is_primary=True,
                )
                session.add(new_enrichment)
                session.commit()
                return True

        return False
