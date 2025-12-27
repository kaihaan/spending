#!/usr/bin/env python3
"""
Test Amazon date extraction fix.

Re-parses Amazon receipts to test improved date extraction patterns.
"""

import os
import sys

# Add backend to path
sys.path.insert(0, "/home/kaihaan/prj/spending/backend")

# Set environment
os.environ["DB_TYPE"] = "postgres"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5433"
os.environ["POSTGRES_PASSWORD"] = "aC0_Xbvulrw8ldPgU6sa"


import database_postgres as database

from mcp.gmail_parsing.orchestrator import parse_receipt_content


def test_reparse_amazon():
    """Re-parse Amazon receipts to test date extraction."""
    print("=" * 80)
    print("Testing Amazon Date Extraction Fix")
    print("=" * 80)

    # Get Amazon receipts with their email content
    query = """
        SELECT
            gr.id,
            gr.message_id,
            gr.subject,
            gr.receipt_date as old_date,
            gec.body_html,
            gec.body_text,
            gec.received_at,
            gec.from_header,
            ''::text as from_name
        FROM gmail_receipts gr
        JOIN gmail_email_content gec ON gr.message_id = gec.message_id
        WHERE gr.parse_method = 'vendor_amazon'
          AND gr.deleted_at IS NULL
        ORDER BY gr.id
    """

    with database.get_db() as conn, conn.cursor() as cursor:
        cursor.execute(query)
        receipts = cursor.fetchall()

    if not receipts:
        print("❌ No Amazon receipts found")
        return

    print(f"\n✓ Found {len(receipts)} Amazon receipts to test\n")

    success_count = 0
    fallback_count = 0
    failed_count = 0

    for receipt in receipts:
        (
            receipt_id,
            message_id,
            subject,
            old_date,
            html,
            text,
            received_at,
            from_email,
            from_name,
        ) = receipt

        # Extract sender domain
        sender_domain = from_email.split("@")[-1] if "@" in from_email else ""

        # Re-parse with new logic
        parsed = parse_receipt_content(
            html_body=html,
            text_body=text,
            subject=subject,
            sender_email=from_email,
            sender_domain=sender_domain,
            sender_name=from_name,
            skip_llm=True,
            received_at=received_at,
        )

        new_date = parsed.get("receipt_date")
        date_source = parsed.get("date_source", "email_body")

        if new_date:
            # Update database
            with database.get_db() as conn, conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE gmail_receipts SET receipt_date = %s WHERE id = %s",
                    (new_date, receipt_id),
                )
                conn.commit()

            if date_source == "email_received":
                fallback_count += 1
                print(f"✓ ID {receipt_id:4d}: {new_date} (fallback) | {subject[:60]}")
            else:
                success_count += 1
                print(f"✓ ID {receipt_id:4d}: {new_date} (parsed)   | {subject[:60]}")
        else:
            failed_count += 1
            print(f"❌ ID {receipt_id:4d}: NO DATE      | {subject[:60]}")

    print("\n" + "=" * 80)
    print("RESULTS:")
    print("=" * 80)
    print(
        f"✓ Parsed from email body: {success_count}/{len(receipts)} ({success_count * 100.0 / len(receipts):.1f}%)"
    )
    print(
        f"⚠ Fallback to received_at: {fallback_count}/{len(receipts)} ({fallback_count * 100.0 / len(receipts):.1f}%)"
    )
    print(
        f"❌ Failed (no date): {failed_count}/{len(receipts)} ({failed_count * 100.0 / len(receipts):.1f}%)"
    )
    print(
        f"📊 Total with dates: {success_count + fallback_count}/{len(receipts)} ({(success_count + fallback_count) * 100.0 / len(receipts):.1f}%)"
    )
    print("=" * 80)


if __name__ == "__main__":
    test_reparse_amazon()
