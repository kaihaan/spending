"""
Apple Transactions - Database Operations

Handles all database operations for Apple transaction imports and matching.

Migrated to SQLAlchemy from psycopg2.
"""

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from .base import get_session
from .models.apple import AppleTransaction, TrueLayerAppleTransactionMatch

# ============================================================================
# APPLE TRANSACTIONS MANAGEMENT FUNCTIONS
# ============================================================================


def import_apple_transactions(transactions, source_file):
    """Bulk import Apple transactions from parsed HTML data."""
    with get_session() as session:
        imported = 0
        duplicates = 0

        for txn in transactions:
            # Use ON CONFLICT DO NOTHING to handle duplicates gracefully
            stmt = (
                insert(AppleTransaction)
                .values(
                    order_id=txn["order_id"],
                    order_date=txn["order_date"],
                    total_amount=txn["total_amount"],
                    currency=txn.get("currency", "GBP"),
                    app_names=txn["app_names"],
                    publishers=txn.get("publishers", ""),
                    item_count=txn.get("item_count", 1),
                    source_file=source_file,
                )
                .on_conflict_do_nothing(index_elements=["order_id"])
            )

            result = session.execute(stmt)
            # rowcount is 1 if inserted, 0 if conflict (duplicate)
            if result.rowcount > 0:
                imported += 1
            else:
                duplicates += 1

        session.commit()
    return imported, duplicates


def get_apple_order_ids():
    """Get set of all Apple order IDs already in database.

    Used by browser import to determine when to stop scrolling.
    """
    with get_session() as session:
        order_ids = session.query(AppleTransaction.order_id).all()
        return {order_id[0] for order_id in order_ids}


def get_apple_transactions(date_from=None, date_to=None):
    """Get all Apple transactions, optionally filtered by date range."""
    with get_session() as session:
        query = session.query(
            AppleTransaction,
            TrueLayerAppleTransactionMatch.truelayer_transaction_id.label(
                "matched_bank_transaction_id"
            ),
        ).outerjoin(
            TrueLayerAppleTransactionMatch,
            AppleTransaction.id == TrueLayerAppleTransactionMatch.apple_transaction_id,
        )

        if date_from:
            query = query.filter(AppleTransaction.order_date >= date_from)

        if date_to:
            query = query.filter(AppleTransaction.order_date <= date_to)

        query = query.order_by(AppleTransaction.order_date.desc())

        results = []
        for apple_txn, matched_bank_id in query.all():
            txn_dict = {
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
                "matched_bank_transaction_id": matched_bank_id,
            }
            results.append(txn_dict)

        return results


def get_apple_transaction_by_id(order_id):
    """Get a specific Apple transaction by database ID."""
    with get_session() as session:
        transaction = session.get(AppleTransaction, order_id)
        if not transaction:
            return None

        return {
            "id": transaction.id,
            "order_id": transaction.order_id,
            "order_date": transaction.order_date,
            "total_amount": transaction.total_amount,
            "currency": transaction.currency,
            "app_names": transaction.app_names,
            "publishers": transaction.publishers,
            "item_count": transaction.item_count,
            "source_file": transaction.source_file,
            "created_at": transaction.created_at,
        }


def get_apple_statistics():
    """Get statistics about imported Apple transactions."""
    with get_session() as session:
        # Total transactions
        total = session.query(func.count(AppleTransaction.id)).scalar()

        if total == 0:
            return {
                "total_transactions": 0,
                "min_transaction_date": None,
                "max_transaction_date": None,
                "total_spent": 0,
                "matched_transactions": 0,
                "unmatched_transactions": 0,
            }

        # Date range
        date_result = session.query(
            func.min(AppleTransaction.order_date).label("min_date"),
            func.max(AppleTransaction.order_date).label("max_date"),
        ).first()
        min_date = date_result.min_date
        max_date = date_result.max_date

        # Total spent
        total_spent = (
            session.query(func.sum(AppleTransaction.total_amount)).scalar() or 0
        )

        # Matched count
        matched = session.query(func.count(TrueLayerAppleTransactionMatch.id)).scalar()

        return {
            "total_transactions": total,
            "min_transaction_date": min_date,
            "max_transaction_date": max_date,
            "total_spent": float(total_spent),
            "matched_transactions": matched,
            "unmatched_transactions": total - matched,
        }


def match_apple_transaction(bank_transaction_id, apple_transaction_db_id, confidence):
    """Record a match between a bank transaction and an Apple purchase."""
    with get_session() as session:
        # Check if transaction already matched
        existing = (
            session.query(TrueLayerAppleTransactionMatch)
            .filter(
                TrueLayerAppleTransactionMatch.truelayer_transaction_id
                == bank_transaction_id
            )
            .first()
        )

        if existing:
            # Update existing match
            existing.apple_transaction_id = apple_transaction_db_id
            existing.match_confidence = confidence
            existing.matched_at = func.current_timestamp()
            session.commit()
            return existing.id

        # Insert new match
        new_match = TrueLayerAppleTransactionMatch(
            truelayer_transaction_id=bank_transaction_id,
            apple_transaction_id=apple_transaction_db_id,
            match_confidence=confidence,
        )
        session.add(new_match)
        session.commit()
        return new_match.id


def clear_apple_transactions():
    """Delete all Apple transactions from database."""
    with get_session() as session:
        # Count before deletion
        count = session.query(func.count(AppleTransaction.id)).scalar()

        # Delete TrueLayer matches first (foreign key constraint)
        session.query(TrueLayerAppleTransactionMatch).delete()

        # Delete transactions
        session.query(AppleTransaction).delete()

        session.commit()
        return count
