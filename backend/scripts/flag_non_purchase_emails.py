#!/usr/bin/env python3
"""Flag non-purchase informational emails in gmail_receipts"""

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


def flag_non_purchase_emails():
    """Flag emails that are informational only, not actual purchases"""

    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Criteria for non-purchase emails:
        # 1. No amount or zero amount
        # 2. Delivery/dispatch notifications (no line items)
        # 3. Account/subscription renewals without charges
        # 4. Bill notifications (not invoices)

        print("Flagging non-purchase informational emails...")

        # Flag emails with no amount or zero amount
        cursor.execute("""
            UPDATE gmail_receipts
            SET is_purchase = FALSE
            WHERE (total_amount IS NULL OR total_amount = 0)
              AND is_purchase = TRUE
            RETURNING id, merchant_name, subject, total_amount
        """)

        no_amount = cursor.fetchall()
        print(f"\n✓ Flagged {len(no_amount)} emails with no/zero amount:")
        for row in no_amount[:10]:
            print(f"  ID {row['id']} ({row['merchant_name']}): {row['subject'][:60]}")

        # Flag delivery/dispatch notifications (have subject patterns but no purchase data)
        cursor.execute("""
            UPDATE gmail_receipts
            SET is_purchase = FALSE
            WHERE (
                subject ILIKE '%dispatched%'
                OR subject ILIKE '%shipped%'
                OR subject ILIKE '%out for delivery%'
                OR subject ILIKE '%delivery update%'
                OR subject ILIKE '%tracking%'
                OR subject ILIKE '%on its way%'
                OR subject ILIKE '%delivered%'
            )
            AND (line_items IS NULL OR jsonb_typeof(line_items) = 'null' OR line_items::text = '[]')
            AND (total_amount IS NULL OR total_amount = 0)
            AND is_purchase = TRUE
            RETURNING id, merchant_name, subject
        """)

        delivery_updates = cursor.fetchall()
        print(f"\n✓ Flagged {len(delivery_updates)} delivery/dispatch notifications:")
        for row in delivery_updates[:10]:
            print(f"  ID {row['id']} ({row['merchant_name']}): {row['subject'][:60]}")

        # Flag account notifications and renewals without amounts
        cursor.execute("""
            UPDATE gmail_receipts
            SET is_purchase = FALSE
            WHERE (
                subject ILIKE '%renewal%'
                OR subject ILIKE '%subscription updated%'
                OR subject ILIKE '%your bill%'
                OR subject ILIKE '%statement%'
                OR subject ILIKE '%account summary%'
            )
            AND (total_amount IS NULL OR total_amount = 0)
            AND is_purchase = TRUE
            RETURNING id, merchant_name, subject
        """)

        account_notifs = cursor.fetchall()
        print(f"\n✓ Flagged {len(account_notifs)} account/bill notifications:")
        for row in account_notifs[:10]:
            print(f"  ID {row['id']} ({row['merchant_name']}): {row['subject'][:60]}")

        # Flag return/refund notifications (not the original purchase)
        cursor.execute("""
            UPDATE gmail_receipts
            SET is_purchase = FALSE
            WHERE (
                subject ILIKE '%return%'
                OR subject ILIKE '%refund%'
                OR subject ILIKE '%cancelled%'
            )
            AND (total_amount IS NULL OR total_amount = 0)
            AND is_purchase = TRUE
            RETURNING id, merchant_name, subject
        """)

        returns = cursor.fetchall()
        print(f"\n✓ Flagged {len(returns)} return/refund notifications:")
        for row in returns[:10]:
            print(f"  ID {row['id']} ({row['merchant_name']}): {row['subject'][:60]}")

        conn.commit()

        # Summary statistics
        cursor.execute("""
            SELECT
                COUNT(*) FILTER (WHERE is_purchase = TRUE) as purchases,
                COUNT(*) FILTER (WHERE is_purchase = FALSE) as informational,
                COUNT(*) as total
            FROM gmail_receipts
        """)

        stats = cursor.fetchone()

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total receipts: {stats['total']}")
        print(
            f"Actual purchases: {stats['purchases']} ({stats['purchases'] / stats['total'] * 100:.1f}%)"
        )
        print(
            f"Informational emails: {stats['informational']} ({stats['informational'] / stats['total'] * 100:.1f}%)"
        )
        print("=" * 80)

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    flag_non_purchase_emails()
