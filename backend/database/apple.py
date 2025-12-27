"""
Apple Transactions - Database Operations

Handles all database operations for Apple transaction imports and matching.
"""

from psycopg2.extras import RealDictCursor

from .base import get_db

# ============================================================================
# APPLE TRANSACTIONS MANAGEMENT FUNCTIONS
# ============================================================================


def import_apple_transactions(transactions, source_file):
    """Bulk import Apple transactions from parsed HTML data."""
    with get_db() as conn, conn.cursor() as cursor:
        imported = 0
        duplicates = 0

        for txn in transactions:
            # Use ON CONFLICT DO NOTHING to handle duplicates gracefully
            # This avoids transaction aborts on duplicate keys in PostgreSQL
            cursor.execute(
                """
                    INSERT INTO apple_transactions (
                        order_id, order_date, total_amount, currency,
                        app_names, publishers, item_count, source_file
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (order_id) DO NOTHING
                """,
                (
                    txn["order_id"],
                    txn["order_date"],
                    txn["total_amount"],
                    txn.get("currency", "GBP"),
                    txn["app_names"],
                    txn.get("publishers", ""),
                    txn.get("item_count", 1),
                    source_file,
                ),
            )
            # rowcount is 1 if inserted, 0 if conflict (duplicate)
            if cursor.rowcount > 0:
                imported += 1
            else:
                duplicates += 1

        conn.commit()
    return imported, duplicates


def get_apple_order_ids():
    """Get set of all Apple order IDs already in database.

    Used by browser import to determine when to stop scrolling.
    """
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT order_id FROM apple_transactions")
        return {row[0] for row in cursor.fetchall()}


def get_apple_transactions(date_from=None, date_to=None):
    """Get all Apple transactions, optionally filtered by date range."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """
                SELECT
                    a.*,
                    m.truelayer_transaction_id as matched_bank_transaction_id
                FROM apple_transactions a
                LEFT JOIN truelayer_apple_transaction_matches m ON a.id = m.apple_transaction_id
                WHERE 1=1
            """
            params = []

            if date_from:
                query += " AND a.order_date >= %s"
                params.append(date_from)

            if date_to:
                query += " AND a.order_date <= %s"
                params.append(date_to)

            query += " ORDER BY a.order_date DESC"

            cursor.execute(query, params)
            return cursor.fetchall()


def get_apple_transaction_by_id(order_id):
    """Get a specific Apple transaction by database ID."""
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute("SELECT * FROM apple_transactions WHERE id = %s", (order_id,))
        return cursor.fetchone()


def get_apple_statistics():
    """Get statistics about imported Apple transactions."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Total transactions
            cursor.execute("SELECT COUNT(*) as count FROM apple_transactions")
            total = cursor.fetchone()["count"]

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
            cursor.execute(
                "SELECT MIN(order_date) as min_date, MAX(order_date) as max_date FROM apple_transactions"
            )
            date_result = cursor.fetchone()
            min_date = date_result["min_date"]
            max_date = date_result["max_date"]

            # Total spent
            cursor.execute("SELECT SUM(total_amount) as total FROM apple_transactions")
            total_spent = cursor.fetchone()["total"] or 0

            # Matched count
            cursor.execute(
                "SELECT COUNT(*) as count FROM truelayer_apple_transaction_matches"
            )
            matched = cursor.fetchone()["count"]

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
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check if transaction already matched
            cursor.execute(
                """
                SELECT id FROM apple_transaction_matches
                WHERE bank_transaction_id = %s
                """,
                (bank_transaction_id,),
            )

            existing = cursor.fetchone()
            if existing:
                # Update existing match
                cursor.execute(
                    """
                    UPDATE apple_transaction_matches
                    SET apple_transaction_id = %s, confidence = %s, matched_at = CURRENT_TIMESTAMP
                    WHERE bank_transaction_id = %s
                    """,
                    (apple_transaction_db_id, confidence, bank_transaction_id),
                )
                conn.commit()
                return existing["id"]
            # Insert new match
            cursor.execute(
                """
                    INSERT INTO apple_transaction_matches (
                        bank_transaction_id, apple_transaction_id, confidence
                    ) VALUES (%s, %s, %s)
                    RETURNING id
                    """,
                (bank_transaction_id, apple_transaction_db_id, confidence),
            )
            match_id = cursor.fetchone()[0]
            conn.commit()
            return match_id


def clear_apple_transactions():
    """Delete all Apple transactions from database."""
    with get_db() as conn, conn.cursor() as cursor:
        # Count before deletion
        cursor.execute("SELECT COUNT(*) FROM apple_transactions")
        count = cursor.fetchone()[0]

        # Delete TrueLayer matches first (foreign key constraint)
        cursor.execute("DELETE FROM truelayer_apple_transaction_matches")

        # Delete transactions
        cursor.execute("DELETE FROM apple_transactions")

        conn.commit()
        return count
