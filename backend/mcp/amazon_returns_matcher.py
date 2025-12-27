"""
Amazon Returns Matcher MCP Component
Matches returns to original orders and transactions.
Updates transaction descriptions and marks items as returned.
"""

from datetime import UTC, datetime, timedelta

import database


def match_all_returns():
    """
    Match all unmatched returns to their original orders and transactions.

    Returns:
        Dictionary with matching statistics
    """
    # Get all returns that haven't been matched yet
    all_returns = database.get_amazon_returns()
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
    order = database.get_amazon_order_by_id(ret["order_id"])

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
    database.update_pre_enrichment_status(refund_transaction["id"], "Matched")

    # Step 5: Mark original transaction as returned (updates enrichment source description)
    mark_original_as_returned(original_transaction["id"])

    # Step 6: Link return to transactions
    # Now that FK constraints are removed, we can link TrueLayer transactions
    database.link_return_to_transactions(
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
    from psycopg2.extras import RealDictCursor

    with database.get_db() as conn:
        c = conn.cursor(cursor_factory=RealDictCursor)

        # Check TrueLayer transactions
        c.execute(
            """
            SELECT tt.*, 'truelayer' as source
            FROM truelayer_transactions tt
            JOIN truelayer_amazon_transaction_matches tatm ON tt.id = tatm.truelayer_transaction_id
            WHERE tatm.amazon_order_id = %s
        """,
            (order_db_id,),
        )
        row = c.fetchone()

        return dict(row) if row else None


def find_refund_transaction(ret):
    """
    Find the bank transaction representing the refund (OPTIMIZED - SQL filtering).
    Looks for positive amount (credit) near the refund completion date.

    Args:
        ret: Return dictionary

    Returns:
        Transaction dictionary or None
    """
    from psycopg2.extras import RealDictCursor

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
    with database.get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # SQL does the filtering - only fetch matching candidates
            cursor.execute(
                """
                SELECT *
                FROM truelayer_transactions
                WHERE transaction_type = 'CREDIT'
                  AND amount = %s
                  AND (UPPER(merchant_name) LIKE '%%AMAZON%%'
                       OR UPPER(merchant_name) LIKE '%%AMZN%%'
                       OR UPPER(description) LIKE '%%AMAZON%%'
                       OR UPPER(description) LIKE '%%AMZN%%')
                  AND timestamp BETWEEN %s AND %s
                ORDER BY ABS(EXTRACT(EPOCH FROM (timestamp - %s)))
                LIMIT 5
            """,
                (
                    amount_refunded,
                    refund_date - timedelta(days=7),
                    refund_date + timedelta(days=3),
                    refund_date,
                ),
            )

            candidates = cursor.fetchall()

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

    with database.get_db() as conn, conn.cursor() as cursor:
        description = (
            f"[REFUND] {order_product_names}" if order_product_names else "[REFUND]"
        )
        cursor.execute(
            """
                INSERT INTO transaction_enrichment_sources
                    (truelayer_transaction_id, source_type, description,
                     order_id, match_confidence, match_method, is_primary)
                VALUES (%s, 'amazon', %s, %s, 100, 'return_match', TRUE)
                ON CONFLICT (truelayer_transaction_id, source_type, source_id)
                DO UPDATE SET
                    description = EXCLUDED.description,
                    updated_at = NOW()
            """,
            (transaction_id, description, amazon_order_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def mark_original_as_returned(transaction_id):
    """Mark the original transaction as returned by updating its enrichment source description."""
    from psycopg2.extras import RealDictCursor

    with database.get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check if there's an existing enrichment source
            cursor.execute(
                """
                SELECT id, description FROM transaction_enrichment_sources
                WHERE truelayer_transaction_id = %s AND is_primary = TRUE
                LIMIT 1
            """,
                (transaction_id,),
            )
            row = cursor.fetchone()

            if row:
                current_desc = row["description"] or ""
                if not current_desc.startswith("[RETURNED] "):
                    new_desc = f"[RETURNED] {current_desc}"
                    cursor.execute(
                        """
                        UPDATE transaction_enrichment_sources
                        SET description = %s, updated_at = NOW()
                        WHERE id = %s
                    """,
                        (new_desc, row["id"]),
                    )
                    conn.commit()
                    return True
            else:
                # No enrichment source exists, get description from transaction and create one
                cursor.execute(
                    """
                    SELECT description FROM truelayer_transactions WHERE id = %s
                """,
                    (transaction_id,),
                )
                txn_row = cursor.fetchone()
                if txn_row:
                    desc = txn_row["description"] or ""
                    cursor.execute(
                        """
                        INSERT INTO transaction_enrichment_sources
                            (truelayer_transaction_id, source_type, description,
                             match_confidence, match_method, is_primary)
                        VALUES (%s, 'manual', %s, 100, 'return_original', TRUE)
                    """,
                        (transaction_id, f"[RETURNED] {desc}"),
                    )
                    conn.commit()
                    return True

            return False
