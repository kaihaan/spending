#!/usr/bin/env python3
"""
Detect and flag duplicate email receipts using time + merchant + product.

Duplicates are emails that refer to the same purchase:
- Same merchant
- Same amount
- Same DATE AND TIME (within 5 minutes)
- Same or similar product/line items

NOT duplicates:
- Two coffees from same shop at different times (different purchases)
- Multiple orders from same merchant on same day (different times)
"""

import json
from datetime import datetime
from difflib import SequenceMatcher

import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host": "localhost",
    "port": "5433",
    "user": "spending_user",
    "password": "aC0_Xbvulrw8ldPgU6sa",
    "database": "spending_db",
}


def connect_db():
    return psycopg2.connect(**DB_CONFIG)


def line_items_similar(items1, items2):
    """Check if two line_items arrays are similar enough to be duplicates"""
    if not items1 or not items2:
        return False

    # Convert to strings for comparison
    str1 = json.dumps(items1, sort_keys=True) if items1 else ""
    str2 = json.dumps(items2, sort_keys=True) if items2 else ""

    # Use sequence matching to compare
    similarity = SequenceMatcher(None, str1, str2).ratio()
    return similarity > 0.8  # 80% similar


def times_close(time1, time2, tolerance_minutes=5):
    """Check if two timestamps are within tolerance minutes of each other"""
    if not time1 or not time2:
        return False

    # Convert to datetime if needed
    if isinstance(time1, str):
        time1 = datetime.fromisoformat(time1.replace("Z", "+00:00"))
    if isinstance(time2, str):
        time2 = datetime.fromisoformat(time2.replace("Z", "+00:00"))

    diff = abs((time1 - time2).total_seconds() / 60)
    return diff <= tolerance_minutes


def detect_duplicates():
    """Detect duplicate receipts based on merchant + amount + time + products"""

    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Add duplicate flag columns if they don't exist
        cursor.execute("""
            ALTER TABLE gmail_receipts
            ADD COLUMN IF NOT EXISTS is_duplicate BOOLEAN DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS duplicate_of_id INTEGER REFERENCES gmail_receipts(id)
        """)
        conn.commit()

        print("Detecting duplicates using merchant + amount + time + products...\n")

        # Get all receipts that are purchases (not informational emails)
        cursor.execute("""
            SELECT id, merchant_name, total_amount, received_at, line_items, subject
            FROM gmail_receipts
            WHERE is_purchase = TRUE
              AND total_amount > 0
            ORDER BY merchant_name, total_amount, received_at
        """)

        receipts = cursor.fetchall()
        print(f"Analyzing {len(receipts)} purchase receipts...\n")

        duplicates_found = []
        checked = set()

        for i, receipt in enumerate(receipts):
            if receipt["id"] in checked:
                continue

            # Find potential duplicates
            potential_dupes = []

            for j in range(i + 1, len(receipts)):
                other = receipts[j]

                if other["id"] in checked:
                    continue

                # Must match: merchant, amount
                if (
                    receipt["merchant_name"] != other["merchant_name"]
                    or receipt["total_amount"] != other["total_amount"]
                ):
                    continue

                # Must be within 5 minutes (delivery/dispatch emails come seconds after order)
                if not times_close(
                    receipt["received_at"], other["received_at"], tolerance_minutes=5
                ):
                    continue

                # Must have similar products (or both have no products)
                if not line_items_similar(receipt["line_items"], other["line_items"]):
                    continue

                # This is a duplicate!
                potential_dupes.append(other)
                checked.add(other["id"])

            if potential_dupes:
                # Keep the first one (usually the actual receipt), mark others as duplicates
                for dupe in potential_dupes:
                    duplicates_found.append(
                        {
                            "original_id": receipt["id"],
                            "original_subject": receipt["subject"],
                            "duplicate_id": dupe["id"],
                            "duplicate_subject": dupe["subject"],
                            "merchant": receipt["merchant_name"],
                            "amount": receipt["total_amount"],
                            "time": receipt["received_at"],
                        }
                    )

                    # Mark as duplicate in database
                    cursor.execute(
                        """
                        UPDATE gmail_receipts
                        SET is_duplicate = TRUE,
                            duplicate_of_id = %s
                        WHERE id = %s
                    """,
                        (receipt["id"], dupe["id"]),
                    )

        conn.commit()

        # Report findings
        print("=" * 80)
        print("DUPLICATE DETECTION RESULTS")
        print("=" * 80)
        print(f"\nFound {len(duplicates_found)} duplicate receipt(s):\n")

        for dup in duplicates_found:
            print("Duplicate Group:")
            print(f"  Original: ID {dup['original_id']}")
            print(f"    Subject: {dup['original_subject'][:70]}")
            print(f"  Duplicate: ID {dup['duplicate_id']}")
            print(f"    Subject: {dup['duplicate_subject'][:70]}")
            print(f"  Merchant: {dup['merchant']}, Amount: £{dup['amount']:.2f}")
            print(f"  Time: {dup['time']}")
            print()

        # Summary
        cursor.execute("""
            SELECT
                COUNT(*) FILTER (WHERE is_duplicate = FALSE) as unique_receipts,
                COUNT(*) FILTER (WHERE is_duplicate = TRUE) as duplicates,
                COUNT(*) as total
            FROM gmail_receipts
            WHERE is_purchase = TRUE
        """)

        stats = cursor.fetchone()
        print("=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total purchase receipts: {stats['total']}")
        print(f"Unique receipts: {stats['unique_receipts']}")
        print(f"Duplicates (flagged): {stats['duplicates']}")
        print("=" * 80)

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    detect_duplicates()
