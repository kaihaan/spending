"""
Amazon Business Transaction Matcher

Matches TrueLayer bank transactions with Amazon Business orders.
Follows the same patterns as apple_matcher_truelayer.py and amazon_matcher.py.
"""

from datetime import UTC, datetime

import database_postgres as database


def match_all_amazon_business_transactions() -> dict:
    """Match all unmatched TrueLayer transactions to Amazon Business orders.

    Returns:
        Dictionary with matching statistics:
        {
            'total_processed': int,
            'matched': int,
            'unmatched': int,
            'matches': list of match details
        }
    """
    # Get unmatched TrueLayer transactions that look like Amazon Business
    unmatched_transactions = (
        database.get_unmatched_truelayer_amazon_business_transactions()
    )
    print(
        f"[Amazon Business Matcher] Found {len(unmatched_transactions)} unmatched Amazon transactions"
    )

    if not unmatched_transactions:
        return {"total_processed": 0, "matched": 0, "unmatched": 0, "matches": []}

    # Get all Amazon Business orders
    all_orders = database.get_amazon_business_orders()
    print(
        f"[Amazon Business Matcher] Found {len(all_orders)} Amazon Business orders in database"
    )

    if not all_orders:
        print(
            "[Amazon Business Matcher] WARNING: No Amazon Business orders in database to match against!"
        )
        return {
            "total_processed": len(unmatched_transactions),
            "matched": 0,
            "unmatched": len(unmatched_transactions),
            "matches": [],
        }

    matched_count = 0
    matches_details = []

    for transaction in unmatched_transactions:
        print(
            f"[Amazon Business Matcher] Checking bank txn: date={transaction.get('timestamp')}, "
            f"amount={transaction.get('amount')}, desc={str(transaction.get('description'))[:50]}..."
        )

        match = find_best_amazon_business_match(transaction, all_orders)

        if match:
            print(
                f"[Amazon Business Matcher] MATCH FOUND: order_id={match['order_id']}, "
                f"products={match['product_summary'][:50] if match['product_summary'] else 'N/A'}..., "
                f"confidence={match['confidence']}"
            )

            # Store match in enrichment_sources table
            success = database.match_truelayer_amazon_business_transaction(
                transaction["id"], match["order_db_id"], match["confidence"]
            )
            print(f"[Amazon Business Matcher] Database update success: {success}")

            if success:
                # Update pre-enrichment status to 'AMZN BIZ'
                database.update_pre_enrichment_status(transaction["id"], "AMZN BIZ")
                matched_count += 1
                matches_details.append(
                    {
                        "transaction_id": transaction["id"],
                        "amazon_order_id": match["order_id"],
                        "confidence": match["confidence"],
                        "product_summary": match["product_summary"],
                    }
                )
        else:
            print("[Amazon Business Matcher] No match found for this transaction")

    print(
        f"[Amazon Business Matcher] RESULT: {matched_count} matched, "
        f"{len(unmatched_transactions) - matched_count} unmatched"
    )

    return {
        "total_processed": len(unmatched_transactions),
        "matched": matched_count,
        "unmatched": len(unmatched_transactions) - matched_count,
        "matches": matches_details,
    }


def find_best_amazon_business_match(transaction: dict, orders: list) -> dict:
    """Find best matching Amazon Business order for a bank transaction.

    Matching criteria:
    - Amount must match exactly (within £0.01)
    - Date must be within ±3 days
    - Confidence based on date proximity

    Args:
        transaction: Bank transaction dictionary
        orders: List of Amazon Business order dictionaries

    Returns:
        Best match dictionary or None if no suitable match found
    """
    # Parse transaction date
    try:
        txn_timestamp = transaction.get("timestamp")
        if isinstance(txn_timestamp, datetime):
            txn_date = txn_timestamp
            if txn_date.tzinfo is None:
                txn_date = txn_date.replace(tzinfo=UTC)
        elif isinstance(txn_timestamp, type(datetime.now().date())):
            txn_date = datetime.combine(txn_timestamp, datetime.min.time(), tzinfo=UTC)
        else:
            date_str = str(txn_timestamp).strip()
            date_part = (
                date_str.split(" ")[0] if " " in date_str else date_str.split("T")[0]
            )
            txn_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=UTC)
    except Exception as e:
        print(f"[Amazon Business Matcher] Failed to parse bank transaction date: {e}")
        return None

    txn_amount = abs(transaction["amount"])
    print(
        f"[Amazon Business Matcher]   Bank txn parsed: date={txn_date.date()}, amount=£{txn_amount:.2f}"
    )

    # Check if this is an Amazon transaction (should already be filtered but double-check)
    merchant = (transaction.get("merchant_name") or "").upper()
    description = (transaction.get("description") or "").upper()

    if not ("AMAZON" in merchant or "AMAZON" in description):
        print("[Amazon Business Matcher]   Skipped: Not an Amazon transaction")
        return None

    # Skip consumer marketplace transactions (handled by amazon_matcher.py)
    if "AMZN MKTP" in description:
        print("[Amazon Business Matcher]   Skipped: Consumer marketplace transaction")
        return None

    # Find candidates
    candidates = []
    print(
        f"[Amazon Business Matcher]   Searching {len(orders)} Amazon Business orders for match..."
    )

    for order in orders:
        # Parse order date
        try:
            order_date = order["order_date"]
            if isinstance(order_date, datetime):
                if order_date.tzinfo is None:
                    order_date = order_date.replace(tzinfo=UTC)
            elif isinstance(order_date, type(datetime.now().date())):
                order_date = datetime.combine(
                    order_date, datetime.min.time(), tzinfo=UTC
                )
            else:
                order_date = datetime.strptime(str(order_date), "%Y-%m-%d").replace(
                    tzinfo=UTC
                )
        except Exception:
            continue

        # Date proximity (±3 days)
        date_diff_days = abs((txn_date - order_date).days)
        if date_diff_days > 3:
            continue

        # Amount match (net_total, within £0.01)
        order_amount = abs(float(order["net_total"]) if order["net_total"] else 0)
        if abs(txn_amount - order_amount) > 0.01:
            continue

        # Calculate confidence score
        confidence = 50  # Base for amount match

        if date_diff_days == 0:
            confidence += 50  # Same day = highest confidence
        elif date_diff_days == 1:
            confidence += 40
        elif date_diff_days == 2:
            confidence += 30
        else:
            confidence += 20  # 3 days

        candidates.append(
            {
                "order_db_id": order["id"],
                "order_id": order["order_id"],
                "product_summary": order.get("product_summary"),
                "confidence": confidence,
                "date_diff": date_diff_days,
            }
        )

    if not candidates:
        # Debug: Show why no candidates found
        print(
            "[Amazon Business Matcher]   No candidates found. Sample Amazon Business orders:"
        )
        for order in orders[:3]:  # Show first 3
            net_total = float(order.get("net_total") or 0)
            print(
                f"[Amazon Business Matcher]     Order: date={order.get('order_date')}, "
                f"amount=£{net_total:.2f}, products={str(order.get('product_summary', ''))[:30]}"
            )
        return None

    print(f"[Amazon Business Matcher]   Found {len(candidates)} candidate(s)")

    # Sort by confidence (descending), then by date difference (ascending)
    candidates.sort(key=lambda x: (-x["confidence"], x["date_diff"]))

    best = candidates[0]
    print(
        f"[Amazon Business Matcher]   Best candidate: {str(best['product_summary'])[:30]}, "
        f"confidence={best['confidence']}"
    )

    if best["confidence"] >= 70:
        return best

    print(f"[Amazon Business Matcher]   Rejected: confidence {best['confidence']} < 70")
    return None


def match_single_transaction(transaction_id: int) -> dict:
    """Match a single transaction to Amazon Business orders.

    Args:
        transaction_id: TrueLayer transaction ID to match

    Returns:
        Match result dictionary
    """
    # Get the transaction
    transaction = database.get_truelayer_transaction_for_matching(transaction_id)
    if not transaction:
        return {"success": False, "error": "Transaction not found"}

    # Get all Amazon Business orders
    all_orders = database.get_amazon_business_orders()
    if not all_orders:
        return {"success": False, "error": "No Amazon Business orders in database"}

    match = find_best_amazon_business_match(transaction, all_orders)

    if match:
        success = database.match_truelayer_amazon_business_transaction(
            transaction_id, match["order_db_id"], match["confidence"]
        )
        if success:
            database.update_pre_enrichment_status(transaction_id, "AMZN BIZ")
            return {"success": True, "match": match}

    return {"success": False, "error": "No matching order found"}
