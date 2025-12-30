"""
Amazon Integration - Database Operations

Handles all database operations for Amazon orders, returns, and business accounts.
Includes matching logic for linking Amazon purchases to bank transactions.
"""

from datetime import datetime

from sqlalchemy import func, or_, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from .base import get_session
from .models.amazon import (
    AmazonBusinessConnection,
    AmazonBusinessLineItem,
    AmazonBusinessOrder,
    AmazonDigitalOrder,
    AmazonOrder,
    AmazonReturn,
    TrueLayerAmazonTransactionMatch,
)
from .models.apple import AppleTransaction, TrueLayerAppleTransactionMatch
from .models.enrichment import TransactionEnrichmentSource
from .models.truelayer import TrueLayerTransaction

# ============================================================================
# AMAZON ORDER MANAGEMENT FUNCTIONS
# ============================================================================


def import_amazon_orders(orders, source_file):
    """Bulk import Amazon orders into database."""
    imported = 0
    duplicates = 0

    with get_session() as session:
        for order in orders:
            try:
                new_order = AmazonOrder(
                    order_id=order["order_id"],
                    order_date=order["order_date"],
                    website=order["website"],
                    currency=order["currency"],
                    total_owed=order["total_owed"],
                    product_names=order["product_names"],
                    order_status=order.get("order_status"),
                    shipment_status=order.get("shipment_status"),
                    source_file=source_file,
                )
                session.add(new_order)
                session.flush()
                imported += 1
            except IntegrityError:
                session.rollback()
                duplicates += 1
                continue

        session.commit()
    return (imported, duplicates)


def get_amazon_orders(date_from=None, date_to=None, website=None):
    """Get Amazon orders with optional filters, including match status."""
    with get_session() as session:
        # Left outer join to include match information
        query = session.query(
            AmazonOrder,
            TrueLayerAmazonTransactionMatch.truelayer_transaction_id.label(
                "matched_transaction_id"
            ),
        ).outerjoin(
            TrueLayerAmazonTransactionMatch,
            AmazonOrder.id == TrueLayerAmazonTransactionMatch.amazon_order_id,
        )

        if date_from:
            query = query.filter(AmazonOrder.order_date >= date_from)

        if date_to:
            query = query.filter(AmazonOrder.order_date <= date_to)

        if website:
            query = query.filter(AmazonOrder.website == website)

        results = query.order_by(AmazonOrder.order_date.desc()).all()

        return [
            {
                "id": o.id,
                "order_id": o.order_id,
                "order_date": o.order_date,
                "website": o.website,
                "currency": o.currency,
                "total_owed": float(o.total_owed),
                "product_names": o.product_names,
                "order_status": o.order_status,
                "shipment_status": o.shipment_status,
                "source_file": o.source_file,
                "created_at": o.created_at,
                "matched_transaction_id": matched_txn_id,
            }
            for o, matched_txn_id in results
        ]


def get_amazon_order_by_id(order_id):
    """Get a single Amazon order by its Amazon order ID."""
    with get_session() as session:
        order = (
            session.query(AmazonOrder).filter(AmazonOrder.order_id == order_id).first()
        )

        if not order:
            return None

        return {
            "id": order.id,
            "order_id": order.order_id,
            "order_date": order.order_date,
            "website": order.website,
            "currency": order.currency,
            "total_owed": float(order.total_owed),
            "product_names": order.product_names,
            "order_status": order.order_status,
            "shipment_status": order.shipment_status,
            "source_file": order.source_file,
            "created_at": order.created_at,
        }


def get_unmatched_truelayer_amazon_transactions():
    """Get all TrueLayer transactions with Amazon merchant that haven't been matched."""
    with get_session() as session:
        # Subquery to find matched transaction IDs
        matched_txn_ids = session.query(
            TrueLayerAmazonTransactionMatch.truelayer_transaction_id
        ).subquery()

        # Main query
        transactions = (
            session.query(TrueLayerTransaction)
            .filter(
                or_(
                    func.upper(TrueLayerTransaction.merchant_name).like("%AMAZON%"),
                    func.upper(TrueLayerTransaction.merchant_name).like("%AMZN%"),
                    func.upper(TrueLayerTransaction.description).like("%AMAZON%"),
                    func.upper(TrueLayerTransaction.description).like("%AMZN%"),
                ),
                ~TrueLayerTransaction.id.in_(matched_txn_ids),
            )
            .order_by(TrueLayerTransaction.timestamp.desc())
            .all()
        )

        return [
            {
                "id": t.id,
                "account_id": t.account_id,
                "transaction_id": t.transaction_id,
                "normalised_provider_transaction_id": t.normalised_provider_transaction_id,
                "date": t.timestamp,
                "description": t.description,
                "amount": float(t.amount),
                "currency": t.currency,
                "transaction_type": t.transaction_type,
                "transaction_category": t.transaction_category,
                "merchant": t.merchant_name,
                "running_balance": float(t.running_balance)
                if t.running_balance
                else None,
                "metadata": t.metadata,
                "created_at": t.created_at,
            }
            for t in transactions
        ]


def get_truelayer_transaction_for_matching(transaction_id):
    """Get a TrueLayer transaction by ID for matching purposes."""
    with get_session() as session:
        txn = session.get(TrueLayerTransaction, transaction_id)

        if not txn:
            return None

        return {
            "id": txn.id,
            "account_id": txn.account_id,
            "transaction_id": txn.transaction_id,
            "normalised_provider_transaction_id": txn.normalised_provider_transaction_id,
            "date": txn.timestamp,
            "description": txn.description,
            "amount": float(txn.amount),
            "currency": txn.currency,
            "transaction_type": txn.transaction_type,
            "transaction_category": txn.transaction_category,
            "merchant": txn.merchant_name,
            "running_balance": float(txn.running_balance)
            if txn.running_balance
            else None,
            "metadata": txn.metadata,
            "created_at": txn.created_at,
        }


def match_truelayer_amazon_transaction(
    truelayer_transaction_id, amazon_order_db_id, confidence
):
    """
    Record a match between a TrueLayer transaction and an Amazon order.
    Stores in dedicated truelayer_amazon_transaction_matches table
    and adds to transaction_enrichment_sources for multi-source display.

    Args:
        truelayer_transaction_id: TrueLayer transaction ID
        amazon_order_db_id: Amazon order database ID
        confidence: Match confidence score (0-100)

    Returns:
        Boolean indicating success
    """
    with get_session() as session:
        try:
            # Store the match (upsert)
            stmt = insert(TrueLayerAmazonTransactionMatch).values(
                truelayer_transaction_id=truelayer_transaction_id,
                amazon_order_id=amazon_order_db_id,
                match_confidence=confidence,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["truelayer_transaction_id"],
                set_={
                    "amazon_order_id": stmt.excluded.amazon_order_id,
                    "match_confidence": stmt.excluded.match_confidence,
                    "matched_at": func.now(),
                },
            )
            session.execute(stmt)

            # Get order details for enrichment source
            order = session.get(AmazonOrder, amazon_order_db_id)

            if order and order.product_names:
                # Add to multi-source enrichment table
                enrich_stmt = insert(TransactionEnrichmentSource).values(
                    truelayer_transaction_id=truelayer_transaction_id,
                    source_type="amazon",
                    source_id=amazon_order_db_id,
                    description=order.product_names,
                    order_id=order.order_id,
                    match_confidence=confidence,
                    match_method="amount_date_match",
                    is_primary=True,
                )
                enrich_stmt = enrich_stmt.on_conflict_do_update(
                    index_elements=[
                        "truelayer_transaction_id",
                        "source_type",
                        "source_id",
                    ],
                    set_={
                        "description": enrich_stmt.excluded.description,
                        "order_id": enrich_stmt.excluded.order_id,
                        "match_confidence": enrich_stmt.excluded.match_confidence,
                        "updated_at": func.now(),
                    },
                )
                session.execute(enrich_stmt)

            session.commit()
            return True
        except Exception as e:
            print(f"Error matching TrueLayer transaction: {e}")
            session.rollback()
            return False


def get_unmatched_truelayer_apple_transactions():
    """Get TrueLayer transactions with Apple merchant that haven't been matched."""
    with get_session() as session:
        # Subquery to find matched transaction IDs
        matched_txn_ids = session.query(
            TrueLayerAppleTransactionMatch.truelayer_transaction_id
        ).subquery()

        # Main query
        transactions = (
            session.query(TrueLayerTransaction)
            .filter(
                or_(
                    func.upper(TrueLayerTransaction.merchant_name).like("%APPLE%"),
                    func.upper(TrueLayerTransaction.description).like("%APPLE%"),
                ),
                ~TrueLayerTransaction.id.in_(matched_txn_ids),
            )
            .order_by(TrueLayerTransaction.timestamp.desc())
            .all()
        )

        return [
            {
                "id": t.id,
                "account_id": t.account_id,
                "transaction_id": t.transaction_id,
                "date": t.timestamp,
                "description": t.description,
                "amount": float(t.amount),
                "currency": t.currency,
                "merchant": t.merchant_name,
                "metadata": t.metadata,
            }
            for t in transactions
        ]


def match_truelayer_apple_transaction(
    truelayer_transaction_id, apple_transaction_id, confidence
):
    """
    Record match between TrueLayer transaction and Apple purchase.
    Adds to transaction_enrichment_sources for multi-source display.
    """
    with get_session() as session:
        try:
            # Store match in legacy table
            stmt = insert(TrueLayerAppleTransactionMatch).values(
                truelayer_transaction_id=truelayer_transaction_id,
                apple_transaction_id=apple_transaction_id,
                match_confidence=confidence,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["truelayer_transaction_id"],
                set_={
                    "apple_transaction_id": stmt.excluded.apple_transaction_id,
                    "match_confidence": stmt.excluded.match_confidence,
                    "matched_at": func.now(),
                },
            )
            session.execute(stmt)

            # Get Apple transaction details for enrichment source
            apple = session.get(AppleTransaction, apple_transaction_id)

            if apple and apple.app_names:
                description = apple.app_names
                if apple.publishers:
                    description = f"{apple.app_names} ({apple.publishers})"

                # Check if Amazon already has primary for this transaction
                has_amazon_primary = (
                    session.query(TransactionEnrichmentSource)
                    .filter(
                        TransactionEnrichmentSource.truelayer_transaction_id
                        == truelayer_transaction_id,
                        TransactionEnrichmentSource.source_type == "amazon",
                        TransactionEnrichmentSource.is_primary.is_(True),
                    )
                    .first()
                ) is not None

                # Add to multi-source enrichment table
                enrich_stmt = insert(TransactionEnrichmentSource).values(
                    truelayer_transaction_id=truelayer_transaction_id,
                    source_type="apple",
                    source_id=apple_transaction_id,
                    description=description,
                    order_id=apple.order_id,
                    match_confidence=confidence,
                    match_method="amount_date_match",
                    is_primary=not has_amazon_primary,
                )
                enrich_stmt = enrich_stmt.on_conflict_do_update(
                    index_elements=[
                        "truelayer_transaction_id",
                        "source_type",
                        "source_id",
                    ],
                    set_={
                        "description": enrich_stmt.excluded.description,
                        "order_id": enrich_stmt.excluded.order_id,
                        "match_confidence": enrich_stmt.excluded.match_confidence,
                        "updated_at": func.now(),
                    },
                )
                session.execute(enrich_stmt)

            session.commit()
            return True
        except Exception as e:
            print(f"Error matching TrueLayer Apple transaction: {e}")
            session.rollback()
            return False


def check_amazon_coverage(date_from, date_to):
    """Check if Amazon order data exists for a date range (TrueLayer transactions only)."""
    with get_session() as session:
        # Count Amazon TrueLayer transactions in range
        amazon_txn_count = (
            session.query(func.count(TrueLayerTransaction.id))
            .filter(
                TrueLayerTransaction.timestamp >= date_from,
                TrueLayerTransaction.timestamp <= date_to,
                or_(
                    func.upper(TrueLayerTransaction.merchant_name).like("%AMAZON%"),
                    func.upper(TrueLayerTransaction.merchant_name).like("%AMZN%"),
                    func.upper(TrueLayerTransaction.description).like("%AMAZON%"),
                    func.upper(TrueLayerTransaction.description).like("%AMZN%"),
                ),
            )
            .scalar()
        ) or 0

        # Count Amazon orders in range (with ±3 day buffer)
        amazon_order_count = (
            session.query(func.count(AmazonOrder.id))
            .filter(
                AmazonOrder.order_date
                >= text(f"'{date_from}'::date - interval '3 days'"),
                AmazonOrder.order_date
                <= text(f"'{date_to}'::date + interval '3 days'"),
            )
            .scalar()
        ) or 0

        # Count matched TrueLayer transactions
        matched_count = (
            session.query(func.count(TrueLayerTransaction.id))
            .join(
                TrueLayerAmazonTransactionMatch,
                TrueLayerTransaction.id
                == TrueLayerAmazonTransactionMatch.truelayer_transaction_id,
            )
            .filter(
                TrueLayerTransaction.timestamp >= date_from,
                TrueLayerTransaction.timestamp <= date_to,
            )
            .scalar()
        ) or 0

        return {
            "amazon_transactions": amazon_txn_count,
            "amazon_orders_available": amazon_order_count,
            "matched_count": matched_count,
            "has_coverage": amazon_order_count > 0,
            "match_rate": (matched_count / amazon_txn_count * 100)
            if amazon_txn_count > 0
            else 0,
        }


def get_amazon_statistics():
    """Get overall Amazon import and matching statistics with date range overlap."""
    with get_session() as session:
        # Amazon order statistics
        total_orders = session.query(func.count(AmazonOrder.id)).scalar() or 0
        min_order_date = session.query(func.min(AmazonOrder.order_date)).scalar()
        max_order_date = session.query(func.max(AmazonOrder.order_date)).scalar()
        total_matched = (
            session.query(func.count(TrueLayerAmazonTransactionMatch.id)).scalar() or 0
        )
        total_unmatched = total_orders - total_matched

        # Bank transaction date range
        min_bank_date = session.query(func.min(TrueLayerTransaction.timestamp)).scalar()
        max_bank_date = session.query(func.max(TrueLayerTransaction.timestamp)).scalar()

        # Calculate overlap dates
        overlap_start = None
        overlap_end = None
        if min_order_date and max_order_date and min_bank_date and max_bank_date:
            # Overlap start is the later of the two start dates
            overlap_start = max(
                min_order_date,
                min_bank_date.date()
                if hasattr(min_bank_date, "date")
                else min_bank_date,
            )
            # Overlap end is the earlier of the two end dates
            overlap_end = min(
                max_order_date,
                max_bank_date.date()
                if hasattr(max_bank_date, "date")
                else max_bank_date,
            )
            # If there's no actual overlap, set to None
            if overlap_start > overlap_end:
                overlap_start = None
                overlap_end = None

        return {
            "total_orders": total_orders,
            "min_order_date": min_order_date.isoformat() if min_order_date else None,
            "max_order_date": max_order_date.isoformat() if max_order_date else None,
            "total_matched": total_matched,
            "total_unmatched": total_unmatched,
            "min_bank_date": min_bank_date.date().isoformat()
            if min_bank_date
            else None,
            "max_bank_date": max_bank_date.date().isoformat()
            if max_bank_date
            else None,
            "overlap_start": overlap_start.isoformat() if overlap_start else None,
            "overlap_end": overlap_end.isoformat() if overlap_end else None,
        }


# ============================================================================


# ============================================================================
# AMAZON RETURNS MANAGEMENT FUNCTIONS
# ============================================================================


def import_amazon_returns(returns, source_file):
    """Bulk import Amazon returns into database."""
    imported = 0
    duplicates = 0

    with get_session() as session:
        for ret in returns:
            try:
                new_return = AmazonReturn(
                    order_id=ret["order_id"],
                    reversal_id=ret["reversal_id"],
                    refund_completion_date=ret["refund_completion_date"],
                    currency=ret["currency"],
                    amount_refunded=ret["amount_refunded"],
                    status=ret.get("status"),
                    disbursement_type=ret.get("disbursement_type"),
                    source_file=source_file,
                )
                session.add(new_return)
                session.flush()
                imported += 1
            except IntegrityError:
                session.rollback()
                duplicates += 1
                continue

        session.commit()
    return (imported, duplicates)


def get_amazon_returns(order_id=None):
    """Get Amazon returns with optional order ID filter."""
    with get_session() as session:
        query = session.query(AmazonReturn)

        if order_id:
            query = query.filter(AmazonReturn.order_id == order_id)

        returns = query.order_by(AmazonReturn.refund_completion_date.desc()).all()

        return [
            {
                "id": r.id,
                "order_id": r.order_id,
                "reversal_id": r.reversal_id,
                "refund_completion_date": r.refund_completion_date,
                "currency": r.currency,
                "amount_refunded": float(r.amount_refunded),
                "status": r.status,
                "disbursement_type": r.disbursement_type,
                "original_transaction_id": r.original_transaction_id,
                "refund_transaction_id": r.refund_transaction_id,
                "source_file": r.source_file,
                "created_at": r.created_at,
            }
            for r in returns
        ]


def link_return_to_transactions(
    return_id, original_transaction_id, refund_transaction_id
):
    """Link a return to its original purchase and refund transactions."""
    with get_session() as session:
        ret = session.get(AmazonReturn, return_id)

        if not ret:
            return False

        ret.original_transaction_id = original_transaction_id
        ret.refund_transaction_id = refund_transaction_id
        session.commit()
        return True


def get_returns_statistics():
    """Get overall returns import and matching statistics (OPTIMIZED - single query)."""
    with get_session() as session:
        # Individual scalar queries for each statistic
        total_returns = session.query(func.count(AmazonReturn.id)).scalar() or 0
        min_return_date = session.query(
            func.min(AmazonReturn.refund_completion_date)
        ).scalar()
        max_return_date = session.query(
            func.max(AmazonReturn.refund_completion_date)
        ).scalar()
        total_refunded = (
            session.query(func.sum(AmazonReturn.amount_refunded)).scalar() or 0
        )

        # Matched returns
        matched_returns = (
            session.query(func.count(AmazonReturn.id))
            .filter(AmazonReturn.original_transaction_id.is_not(None))
            .scalar()
        ) or 0

        # Unmatched returns
        unmatched_returns = (
            session.query(func.count(AmazonReturn.id))
            .filter(AmazonReturn.original_transaction_id.is_(None))
            .scalar()
        ) or 0

        return {
            "total_returns": total_returns,
            "min_return_date": min_return_date.isoformat() if min_return_date else None,
            "max_return_date": max_return_date.isoformat() if max_return_date else None,
            "total_refunded": round(float(total_refunded), 2),
            "matched_returns": matched_returns,
            "unmatched_returns": unmatched_returns,
        }


def clear_amazon_returns():
    """Delete all Amazon returns from database. Also removes [RETURNED] labels from transactions."""
    with get_session() as session:
        # Get all transactions marked as returned (legacy table - use raw SQL)
        result = session.execute(
            text("""
                SELECT id, description FROM transactions
                WHERE description LIKE '[RETURNED] %'
            """)
        )
        returned_txns = result.fetchall()

        # Remove [RETURNED] prefix
        for txn_id, description in returned_txns:
            new_desc = description.replace("[RETURNED] ", "", 1)
            session.execute(
                text("""
                    UPDATE transactions
                    SET description = :new_desc
                    WHERE id = :txn_id
                """),
                {"new_desc": new_desc, "txn_id": txn_id},
            )

        # Count and delete returns
        return_count = session.query(func.count(AmazonReturn.id)).scalar() or 0
        session.query(AmazonReturn).delete()
        session.commit()

        return return_count


# ============================================================================


# ============================================================================
# AMAZON DIGITAL ORDERS FUNCTIONS
# ============================================================================


def import_amazon_digital_orders(orders: list, source_file: str) -> tuple:
    """Bulk import Amazon digital orders into database.

    Args:
        orders: List of digital order dictionaries from CSV parser
        source_file: Name of the source CSV file

    Returns:
        Tuple of (imported_count, duplicate_count)
    """
    imported = 0
    duplicates = 0

    with get_session() as session:
        for order in orders:
            try:
                new_order = AmazonDigitalOrder(
                    user_id=1,  # Default user
                    asin=order["asin"],
                    product_name=order["product_name"],
                    order_id=order["order_id"],
                    digital_order_item_id=order["digital_order_item_id"],
                    order_date=order["order_date"],
                    fulfilled_date=order.get("fulfilled_date"),
                    price=order["price"],
                    price_tax=order.get("price_tax"),
                    currency=order.get("currency", "GBP"),
                    publisher=order.get("publisher"),
                    seller_of_record=order.get("seller_of_record"),
                    marketplace=order.get("marketplace"),
                    source_file=source_file,
                )
                session.add(new_order)
                session.flush()
                imported += 1
            except IntegrityError:
                session.rollback()
                duplicates += 1
                continue

        session.commit()
    return (imported, duplicates)


def get_amazon_digital_orders(date_from=None, date_to=None) -> list:
    """Get Amazon digital orders with optional filters.

    Args:
        date_from: Optional start date filter
        date_to: Optional end date filter

    Returns:
        List of digital order dictionaries
    """
    with get_session() as session:
        query = session.query(AmazonDigitalOrder)

        if date_from:
            query = query.filter(AmazonDigitalOrder.order_date >= date_from)

        if date_to:
            query = query.filter(AmazonDigitalOrder.order_date <= date_to)

        orders = query.order_by(AmazonDigitalOrder.order_date.desc()).all()

        return [
            {
                "id": o.id,
                "asin": o.asin,
                "product_name": o.product_name,
                "order_id": o.order_id,
                "digital_order_item_id": o.digital_order_item_id,
                "order_date": o.order_date.isoformat() if o.order_date else None,
                "fulfilled_date": o.fulfilled_date.isoformat()
                if o.fulfilled_date
                else None,
                "price": float(o.price),
                "price_tax": float(o.price_tax) if o.price_tax else None,
                "currency": o.currency,
                "publisher": o.publisher,
                "seller_of_record": o.seller_of_record,
                "marketplace": o.marketplace,
                "source_file": o.source_file,
                "matched_transaction_id": o.matched_transaction_id,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in orders
        ]


def get_amazon_digital_statistics() -> dict:
    """Get Amazon digital orders statistics with bank overlap dates.

    Returns:
        Dictionary with counts and date ranges
    """
    with get_session() as session:
        # Digital order statistics
        total_orders = session.query(func.count(AmazonDigitalOrder.id)).scalar() or 0
        min_order_date = session.query(func.min(AmazonDigitalOrder.order_date)).scalar()
        max_order_date = session.query(func.max(AmazonDigitalOrder.order_date)).scalar()

        # Matched orders (have matched_transaction_id)
        matched_orders = (
            session.query(func.count(AmazonDigitalOrder.id))
            .filter(AmazonDigitalOrder.matched_transaction_id.is_not(None))
            .scalar()
        ) or 0

        unmatched_orders = total_orders - matched_orders

        # Bank transaction date range
        min_bank_date = session.query(func.min(TrueLayerTransaction.timestamp)).scalar()
        max_bank_date = session.query(func.max(TrueLayerTransaction.timestamp)).scalar()

        # Calculate overlap dates
        overlap_start = None
        overlap_end = None
        if min_order_date and max_order_date and min_bank_date and max_bank_date:
            # Overlap start is the later of the two start dates
            order_start = (
                min_order_date.date()
                if hasattr(min_order_date, "date")
                else min_order_date
            )
            bank_start = (
                min_bank_date.date()
                if hasattr(min_bank_date, "date")
                else min_bank_date
            )
            overlap_start = max(order_start, bank_start)

            # Overlap end is the earlier of the two end dates
            order_end = (
                max_order_date.date()
                if hasattr(max_order_date, "date")
                else max_order_date
            )
            bank_end = (
                max_bank_date.date()
                if hasattr(max_bank_date, "date")
                else max_bank_date
            )
            overlap_end = min(order_end, bank_end)

            # If there's no actual overlap, set to None
            if overlap_start > overlap_end:
                overlap_start = None
                overlap_end = None

        return {
            "total_orders": total_orders,
            "matched_orders": matched_orders,
            "unmatched_orders": unmatched_orders,
            "min_order_date": min_order_date.isoformat() if min_order_date else None,
            "max_order_date": max_order_date.isoformat() if max_order_date else None,
            "min_bank_date": min_bank_date.date().isoformat()
            if min_bank_date
            else None,
            "max_bank_date": max_bank_date.date().isoformat()
            if max_bank_date
            else None,
            "overlap_start": overlap_start.isoformat() if overlap_start else None,
            "overlap_end": overlap_end.isoformat() if overlap_end else None,
        }


def clear_amazon_digital_orders() -> int:
    """Delete all Amazon digital orders from database.

    Returns:
        Count of deleted orders
    """
    with get_session() as session:
        order_count = session.query(func.count(AmazonDigitalOrder.id)).scalar() or 0
        session.query(AmazonDigitalOrder).delete()
        session.commit()
        return order_count


# ============================================================================


# ============================================================================
# AMAZON BUSINESS FUNCTIONS
# ============================================================================


def save_amazon_business_connection(
    access_token: str,
    refresh_token: str,
    expires_in: int,
    region: str = "UK",
    user_id: int = 1,
    marketplace_id: str = None,
    is_sandbox: bool = True,
) -> int:
    """Save Amazon SP-API OAuth connection.

    Args:
        access_token: OAuth access token
        refresh_token: OAuth refresh token
        expires_in: Token expiry in seconds
        region: Amazon region (UK, US, DE, etc.)
        user_id: User ID (default 1)
        marketplace_id: Amazon marketplace ID (e.g., A1F83G8C2ARO7P for UK)
        is_sandbox: True for sandbox environment, False for production

    Returns:
        Connection ID
    """
    from datetime import timedelta

    expires_at = datetime.now() + timedelta(seconds=expires_in)

    # Set default marketplace ID if not provided
    if marketplace_id is None:
        marketplace_ids = {
            "UK": "A1F83G8C2ARO7P",
            "US": "ATVPDKIKX0DER",
            "DE": "A1PA6795UKMFR9",
        }
        marketplace_id = marketplace_ids.get(region, "A1F83G8C2ARO7P")

    with get_session() as session:
        new_connection = AmazonBusinessConnection(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=expires_at,
            region=region,
            marketplace_id=marketplace_id,
            is_sandbox=is_sandbox,
        )
        session.add(new_connection)
        session.flush()
        connection_id = new_connection.id
        session.commit()
        return connection_id


def get_amazon_business_connection(connection_id: int = None, user_id: int = 1) -> dict:
    """Get Amazon SP-API connection details.

    Args:
        connection_id: Specific connection ID, or None for user's active connection
        user_id: User ID (default 1)

    Returns:
        Connection dictionary or None
    """
    with get_session() as session:
        if connection_id:
            conn = session.get(AmazonBusinessConnection, connection_id)
        else:
            conn = (
                session.query(AmazonBusinessConnection)
                .filter(
                    AmazonBusinessConnection.user_id == user_id,
                    AmazonBusinessConnection.status == "active",
                )
                .order_by(AmazonBusinessConnection.created_at.desc())
                .first()
            )

        if not conn:
            return None

        return {
            "id": conn.id,
            "user_id": conn.user_id,
            "access_token": conn.access_token,
            "refresh_token": conn.refresh_token,
            "token_expires_at": conn.token_expires_at,
            "region": conn.region,
            "status": conn.status,
            "marketplace_id": conn.marketplace_id,
            "is_sandbox": conn.is_sandbox,
            "last_synced_at": conn.last_synced_at,
            "created_at": conn.created_at,
            "updated_at": conn.updated_at,
        }


def update_amazon_business_tokens(
    connection_id: int, access_token: str, refresh_token: str, expires_at
) -> bool:
    """Update Amazon Business OAuth tokens after refresh.

    Args:
        connection_id: Connection ID
        access_token: New access token
        refresh_token: New refresh token (or existing if not changed)
        expires_at: Token expiry datetime

    Returns:
        True if update was successful
    """
    with get_session() as session:
        conn = session.get(AmazonBusinessConnection, connection_id)

        if not conn:
            return False

        conn.access_token = access_token
        conn.refresh_token = refresh_token
        conn.token_expires_at = expires_at
        conn.updated_at = datetime.now()
        session.commit()
        return True


def import_amazon_business_orders(orders: list) -> tuple:
    """Import Amazon Business orders from API response.

    Args:
        orders: List of order dictionaries from Amazon Business API

    Returns:
        Tuple of (imported_count, duplicate_count)
    """
    imported = 0
    duplicates = 0

    with get_session() as session:
        for order in orders:
            # Extract charge amounts
            charges = order.get("charges", {})
            subtotal = charges.get("SUBTOTAL", {}).get("amount", 0)
            tax = charges.get("TAX", {}).get("amount", 0)
            shipping = charges.get("SHIPPING", {}).get("amount", 0)
            net_total = charges.get("NET_TOTAL", {}).get("amount", 0)

            # Extract buyer info
            buyer = order.get("buyingCustomer", {})
            buyer_name = buyer.get("name", "")
            buyer_email = buyer.get("email", "")

            stmt = insert(AmazonBusinessOrder).values(
                order_id=order.get("orderId"),
                order_date=order.get("orderDate"),
                region=order.get("region"),
                purchase_order_number=order.get("purchaseOrderNumber"),
                order_status=order.get("orderStatus"),
                buyer_name=buyer_name,
                buyer_email=buyer_email,
                subtotal=subtotal,
                tax=tax,
                shipping=shipping,
                net_total=net_total,
                currency=charges.get("NET_TOTAL", {}).get("currency", "GBP"),
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["order_id"])

            result = session.execute(stmt)
            if result.rowcount > 0:
                imported += 1
            else:
                duplicates += 1

        session.commit()

    return imported, duplicates


def import_amazon_business_line_items(line_items: list) -> int:
    """Import Amazon Business line items from API response.

    Args:
        line_items: List of line item dictionaries from Amazon Business API

    Returns:
        Count of imported line items
    """
    imported = 0

    with get_session() as session:
        for item in line_items:
            product = item.get("productDetails", {})

            stmt = insert(AmazonBusinessLineItem).values(
                order_id=item.get("orderId"),
                line_item_id=item.get("orderLineItemId"),
                asin=product.get("asin"),
                title=product.get("title"),
                brand=product.get("brand"),
                category=product.get("category"),
                quantity=item.get("quantity"),
                unit_price=item.get("unitPrice", {}).get("amount"),
                total_price=item.get("totalPrice", {}).get("amount"),
                seller_name=item.get("sellerInfo", {}).get("name"),
            )
            stmt = stmt.on_conflict_do_nothing()

            result = session.execute(stmt)
            if result.rowcount > 0:
                imported += 1

        session.commit()

        # Update product_summary in orders table
        try:
            session.execute(
                text("""
                    UPDATE amazon_business_orders o
                    SET product_summary = (
                        SELECT STRING_AGG(title, ', ')
                        FROM amazon_business_line_items li
                        WHERE li.order_id = o.order_id
                    ),
                    item_count = (
                        SELECT COALESCE(SUM(quantity), 0)
                        FROM amazon_business_line_items li
                        WHERE li.order_id = o.order_id
                    )
                """)
            )
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"Warning: Failed to update product summaries: {e}")

    return imported


def get_amazon_business_orders(date_from=None, date_to=None) -> list:
    """Get all Amazon Business orders.

    Args:
        date_from: Optional start date filter
        date_to: Optional end date filter

    Returns:
        List of order dictionaries
    """
    with get_session() as session:
        query = session.query(AmazonBusinessOrder)

        if date_from:
            query = query.filter(AmazonBusinessOrder.order_date >= date_from)

        if date_to:
            query = query.filter(AmazonBusinessOrder.order_date <= date_to)

        orders = query.order_by(AmazonBusinessOrder.order_date.desc()).all()

        return [
            {
                "id": o.id,
                "order_id": o.order_id,
                "order_date": o.order_date,
                "region": o.region,
                "purchase_order_number": o.purchase_order_number,
                "order_status": o.order_status,
                "buyer_name": o.buyer_name,
                "buyer_email": o.buyer_email,
                "subtotal": float(o.subtotal) if o.subtotal else None,
                "tax": float(o.tax) if o.tax else None,
                "shipping": float(o.shipping) if o.shipping else None,
                "net_total": float(o.net_total) if o.net_total else None,
                "currency": o.currency,
                "item_count": o.item_count,
                "product_summary": o.product_summary,
                "created_at": o.created_at,
            }
            for o in orders
        ]


def get_amazon_business_statistics() -> dict:
    """Get Amazon Business import and matching statistics.

    Returns:
        Dictionary with counts and date ranges
    """
    with get_session() as session:
        # Individual scalar queries for statistics
        total_orders = session.query(func.count(AmazonBusinessOrder.id)).scalar() or 0
        min_order_date = session.query(
            func.min(AmazonBusinessOrder.order_date)
        ).scalar()
        max_order_date = session.query(
            func.max(AmazonBusinessOrder.order_date)
        ).scalar()

        # Count matched transactions (legacy table - use text())
        total_matched = (
            session.execute(
                text("SELECT COUNT(*) FROM truelayer_amazon_business_matches")
            ).scalar()
            or 0
        )

        # Count unmatched Amazon Business transactions
        total_unmatched = (
            session.execute(
                text("""
                    SELECT COUNT(*) FROM truelayer_transactions tt
                    WHERE (UPPER(merchant_name) LIKE '%AMAZON%'
                           OR UPPER(description) LIKE '%AMAZON%')
                      AND UPPER(description) NOT LIKE '%AMZN MKTP%'
                      AND NOT EXISTS (
                          SELECT 1 FROM truelayer_amazon_business_matches tabm
                          WHERE tabm.truelayer_transaction_id = tt.id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM truelayer_amazon_transaction_matches tatm
                          WHERE tatm.truelayer_transaction_id = tt.id
                      )
                """)
            ).scalar()
            or 0
        )

        return {
            "total_orders": total_orders,
            "min_order_date": min_order_date.isoformat() if min_order_date else None,
            "max_order_date": max_order_date.isoformat() if max_order_date else None,
            "total_matched": total_matched,
            "total_unmatched": total_unmatched,
        }


def get_unmatched_truelayer_amazon_business_transactions() -> list:
    """Get TrueLayer transactions with Amazon merchant that haven't been matched
    to Amazon Business orders (excludes consumer marketplace transactions).

    Returns:
        List of unmatched transaction dictionaries
    """
    with get_session() as session:
        # Use text() for complex query with multiple NOT EXISTS
        result = session.execute(
            text("""
                SELECT id, account_id, transaction_id, normalised_provider_transaction_id,
                       timestamp, description, amount, currency, transaction_type,
                       transaction_category, merchant_name, running_balance, metadata
                FROM truelayer_transactions tt
                WHERE (
                    UPPER(merchant_name) LIKE '%AMAZON%'
                    OR UPPER(description) LIKE '%AMAZON%'
                )
                AND UPPER(description) NOT LIKE '%AMZN MKTP%'
                AND NOT EXISTS (
                    SELECT 1 FROM truelayer_amazon_business_matches tabm
                    WHERE tabm.truelayer_transaction_id = tt.id
                )
                AND NOT EXISTS (
                    SELECT 1 FROM truelayer_amazon_transaction_matches tatm
                    WHERE tatm.truelayer_transaction_id = tt.id
                )
                ORDER BY timestamp DESC
            """)
        )

        return [dict(row._mapping) for row in result]


def match_truelayer_amazon_business_transaction(
    truelayer_transaction_id: int, amazon_business_order_id: int, confidence: int
) -> bool:
    """Record a match between TrueLayer transaction and Amazon Business order.
    Stores in legacy table and adds to transaction_enrichment_sources.

    Args:
        truelayer_transaction_id: TrueLayer transaction ID
        amazon_business_order_id: Amazon Business order database ID
        confidence: Match confidence score (0-100)

    Returns:
        True if match was recorded successfully
    """
    with get_session() as session:
        try:
            # Store the match in legacy table using text()
            session.execute(
                text("""
                    INSERT INTO truelayer_amazon_business_matches
                    (truelayer_transaction_id, amazon_business_order_id, match_confidence)
                    VALUES (:txn_id, :order_id, :confidence)
                    ON CONFLICT (truelayer_transaction_id) DO UPDATE
                    SET amazon_business_order_id = EXCLUDED.amazon_business_order_id,
                        match_confidence = EXCLUDED.match_confidence,
                        matched_at = NOW()
                """),
                {
                    "txn_id": truelayer_transaction_id,
                    "order_id": amazon_business_order_id,
                    "confidence": confidence,
                },
            )

            # Get order details for enrichment source
            order = session.get(AmazonBusinessOrder, amazon_business_order_id)

            if order and order.product_summary:
                # Add to multi-source enrichment table
                enrich_stmt = insert(TransactionEnrichmentSource).values(
                    truelayer_transaction_id=truelayer_transaction_id,
                    source_type="amazon_business",
                    source_id=amazon_business_order_id,
                    description=order.product_summary,
                    order_id=order.order_id,
                    match_confidence=confidence,
                    match_method="amount_date_match",
                    is_primary=True,
                )
                enrich_stmt = enrich_stmt.on_conflict_do_update(
                    index_elements=[
                        "truelayer_transaction_id",
                        "source_type",
                        "source_id",
                    ],
                    set_={
                        "description": enrich_stmt.excluded.description,
                        "order_id": enrich_stmt.excluded.order_id,
                        "match_confidence": enrich_stmt.excluded.match_confidence,
                        "updated_at": func.now(),
                    },
                )
                session.execute(enrich_stmt)

            session.commit()
            return True
        except Exception as e:
            print(f"Error matching Amazon Business transaction: {e}")
            session.rollback()
            return False


def delete_amazon_business_connection(connection_id: int) -> bool:
    """Delete an Amazon Business connection.

    Args:
        connection_id: Connection ID to delete

    Returns:
        True if deleted successfully
    """
    with get_session() as session:
        conn = session.get(AmazonBusinessConnection, connection_id)

        if not conn:
            return False

        conn.status = "disconnected"
        conn.updated_at = datetime.now()
        session.commit()
        return True


def clear_amazon_business_data() -> dict:
    """Clear all Amazon Business data (for testing/reset).

    Returns:
        Dictionary with counts of deleted records
    """
    with get_session() as session:
        # Get counts before deletion
        orders_count = session.query(func.count(AmazonBusinessOrder.id)).scalar() or 0
        items_count = session.query(func.count(AmazonBusinessLineItem.id)).scalar() or 0

        # Count matches (legacy table - use text())
        matches_count = (
            session.execute(
                text("SELECT COUNT(*) FROM truelayer_amazon_business_matches")
            ).scalar()
            or 0
        )

        # Delete in order of foreign key dependencies
        session.execute(text("DELETE FROM truelayer_amazon_business_matches"))
        session.query(AmazonBusinessLineItem).delete()
        session.query(AmazonBusinessOrder).delete()

        session.commit()

        return {
            "orders_deleted": orders_count,
            "matches_deleted": matches_count,
            "line_items_deleted": items_count,
        }


def get_amazon_business_order_by_id(order_id: str) -> dict:
    """Get Amazon Business order by order_id for duplicate detection.

    Args:
        order_id: Amazon Order ID (e.g., AmazonOrderId from SP-API)

    Returns:
        Order dictionary or None if not found
    """
    with get_session() as session:
        order = (
            session.query(AmazonBusinessOrder)
            .filter(AmazonBusinessOrder.order_id == order_id)
            .first()
        )

        if not order:
            return None

        return {
            "id": order.id,
            "order_id": order.order_id,
            "order_date": order.order_date,
            "region": order.region,
            "purchase_order_number": order.purchase_order_number,
            "order_status": order.order_status,
            "buyer_name": order.buyer_name,
            "buyer_email": order.buyer_email,
            "subtotal": float(order.subtotal) if order.subtotal else None,
            "tax": float(order.tax) if order.tax else None,
            "shipping": float(order.shipping) if order.shipping else None,
            "net_total": float(order.net_total) if order.net_total else None,
            "currency": order.currency,
            "item_count": order.item_count,
            "product_summary": order.product_summary,
            "created_at": order.created_at,
        }


def insert_amazon_business_order(order: dict) -> int:
    """Insert a single Amazon Business order.

    Args:
        order: Order dictionary with normalized fields

    Returns:
        Order database ID, or None if duplicate
    """
    with get_session() as session:
        stmt = insert(AmazonBusinessOrder).values(
            order_id=order.get("order_id"),
            order_date=order.get("order_date"),
            region=order.get("region"),
            purchase_order_number=order.get("purchase_order_number"),
            order_status=order.get("order_status"),
            buyer_name=order.get("buyer_name"),
            buyer_email=order.get("buyer_email"),
            subtotal=order.get("subtotal"),
            tax=order.get("tax", 0),
            shipping=order.get("shipping", 0),
            net_total=order.get("net_total"),
            currency=order.get("currency", "GBP"),
            item_count=order.get("item_count", 0),
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["order_id"])
        stmt = stmt.returning(AmazonBusinessOrder.id)

        result = session.execute(stmt)
        order_id = result.scalar()
        session.commit()
        return order_id


def insert_amazon_business_line_item(item: dict) -> int:
    """Insert a single Amazon Business line item.

    Args:
        item: Line item dictionary with normalized fields

    Returns:
        Line item database ID
    """
    with get_session() as session:
        new_item = AmazonBusinessLineItem(
            order_id=item.get("order_id"),
            line_item_id=item.get("line_item_id"),
            asin=item.get("asin"),
            title=item.get("title"),
            brand=item.get("brand"),
            category=item.get("category"),
            quantity=item.get("quantity", 1),
            unit_price=item.get("unit_price", 0),
            total_price=item.get("total_price", 0),
            seller_name=item.get("seller_name"),
        )
        session.add(new_item)
        session.flush()
        item_id = new_item.id
        session.commit()
        return item_id


def update_amazon_business_product_summaries() -> int:
    """Update product_summary field by concatenating line items.

    Concatenates all line_items.title for each order into the product_summary field.

    Returns:
        Number of orders updated
    """
    with get_session() as session:
        result = session.execute(
            text("""
                UPDATE amazon_business_orders o
                SET product_summary = (
                    SELECT string_agg(title, ', ')
                    FROM amazon_business_line_items
                    WHERE order_id = o.order_id
                )
                WHERE product_summary IS NULL OR product_summary = ''
            """)
        )
        session.commit()
        return result.rowcount


# ============================================================================
