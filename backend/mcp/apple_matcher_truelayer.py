"""
Apple Transaction Matcher for TrueLayer
Matches TrueLayer bank transactions with Apple Store purchases.
"""

from datetime import UTC, datetime

import database


def match_all_apple_transactions():
    """
    Match all unmatched TrueLayer transactions to Apple purchases.

    Returns:
        Dictionary with matching statistics
    """
    # Get unmatched TrueLayer transactions
    unmatched_transactions = database.get_unmatched_truelayer_apple_transactions()
    print(
        f"[Apple Matcher] Found {len(unmatched_transactions)} unmatched TrueLayer APPLE transactions"
    )

    if not unmatched_transactions:
        return {"total_processed": 0, "matched": 0, "unmatched": 0, "matches": []}

    # Get all Apple transactions
    all_apple = database.get_apple_transactions()
    print(f"[Apple Matcher] Found {len(all_apple)} Apple transactions in database")

    if not all_apple:
        print(
            "[Apple Matcher] WARNING: No Apple transactions in database to match against!"
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
            f"[Apple Matcher] Checking bank txn: date={transaction.get('date')}, amount={transaction.get('amount')}, desc={transaction.get('description')[:50]}..."
        )
        match = find_best_apple_match(transaction, all_apple)

        if match:
            print(
                f"[Apple Matcher] MATCH FOUND: order_id={match['order_id']}, app={match['app_names']}, confidence={match['confidence']}"
            )
            # Store match in enrichment_sources table
            success = database.match_truelayer_apple_transaction(
                transaction["id"], match["apple_db_id"], match["confidence"]
            )
            print(f"[Apple Matcher] Database update success: {success}")

            if success:
                # Update pre-enrichment status to 'Matched'
                database.update_pre_enrichment_status(transaction["id"], "Matched")
                matched_count += 1
                matches_details.append(
                    {
                        "transaction_id": transaction["id"],
                        "apple_order_id": match["order_id"],
                        "confidence": match["confidence"],
                        "app_names": match["app_names"],
                    }
                )
        else:
            print("[Apple Matcher] No match found for this transaction")

    print(
        f"[Apple Matcher] RESULT: {matched_count} matched, {len(unmatched_transactions) - matched_count} unmatched"
    )
    return {
        "total_processed": len(unmatched_transactions),
        "matched": matched_count,
        "unmatched": len(unmatched_transactions) - matched_count,
        "matches": matches_details,
    }


def find_best_apple_match(transaction, apple_transactions):
    """Find best matching Apple purchase for transaction."""
    # Parse transaction date
    try:
        txn_date_val = transaction["date"]
        if isinstance(txn_date_val, datetime):
            txn_date = txn_date_val
            # Ensure timezone-aware
            if txn_date.tzinfo is None:
                txn_date = txn_date.replace(tzinfo=UTC)
        elif isinstance(txn_date_val, type(datetime.now().date())):  # date type
            txn_date = datetime.combine(txn_date_val, datetime.min.time(), tzinfo=UTC)
        else:
            date_str = str(txn_date_val).strip()
            date_part = (
                date_str.split(" ")[0] if " " in date_str else date_str.split("T")[0]
            )
            txn_date = datetime.strptime(date_part, "%Y-%m-%d").replace(tzinfo=UTC)
    except Exception as e:
        print(f"[Apple Matcher] Failed to parse bank transaction date: {e}")
        return None

    txn_amount = abs(transaction["amount"])
    print(
        f"[Apple Matcher]   Bank txn parsed: date={txn_date.date()}, amount=£{txn_amount:.2f}"
    )

    # Check if Apple transaction
    merchant = (transaction.get("merchant") or "").upper()
    description = (transaction.get("description") or "").upper()
    if not ("APPLE" in merchant or "APPLE" in description):
        print("[Apple Matcher]   Skipped: Not an Apple transaction")
        return None

    # Find candidates
    candidates = []
    print(
        f"[Apple Matcher]   Searching {len(apple_transactions)} Apple transactions for match..."
    )
    for apple in apple_transactions:
        # Parse Apple order date
        try:
            if isinstance(apple["order_date"], datetime):
                apple_date = apple["order_date"]
                # Ensure timezone-aware
                if apple_date.tzinfo is None:
                    apple_date = apple_date.replace(tzinfo=UTC)
            elif isinstance(
                apple["order_date"], type(datetime.now().date())
            ):  # date type
                apple_date = datetime.combine(
                    apple["order_date"], datetime.min.time(), tzinfo=UTC
                )
            else:
                apple_date = datetime.strptime(
                    str(apple["order_date"]), "%Y-%m-%d"
                ).replace(tzinfo=UTC)
        except Exception:  # Fixed: was bare except
            continue

        # Date proximity (±3 days)
        date_diff_days = abs((txn_date - apple_date).days)
        if date_diff_days > 3:
            continue

        # Amount match (convert Decimal to float for comparison)
        if abs(txn_amount - float(abs(apple["total_amount"]))) > 0.01:
            continue

        # Calculate confidence
        confidence = 50  # Base for amount match
        if date_diff_days == 0:
            confidence += 50
        elif date_diff_days == 1:
            confidence += 40
        elif date_diff_days == 2:
            confidence += 30
        else:
            confidence += 20

        candidates.append(
            {
                "apple_db_id": apple["id"],
                "order_id": apple["order_id"],
                "app_names": apple["app_names"],
                "confidence": confidence,
                "date_diff": date_diff_days,
            }
        )

    if not candidates:
        # Debug: Show why no candidates found
        print("[Apple Matcher]   No candidates found. Sample Apple transactions:")
        for apple in apple_transactions[:3]:  # Show first 3
            print(
                f"[Apple Matcher]     Apple: date={apple.get('order_date')}, amount=£{float(apple.get('total_amount', 0)):.2f}, app={apple.get('app_names', '')[:30]}"
            )
        return None

    print(f"[Apple Matcher]   Found {len(candidates)} candidate(s)")

    # Sort by confidence
    candidates.sort(key=lambda x: (-x["confidence"], x["date_diff"]))

    best = candidates[0]
    print(
        f"[Apple Matcher]   Best candidate: {best['app_names'][:30]}, confidence={best['confidence']}"
    )
    if best["confidence"] >= 70:
        return best

    print(f"[Apple Matcher]   Rejected: confidence {best['confidence']} < 70")
    return None
