#!/usr/bin/env python3
"""Re-parse Deliveroo receipts to add restaurant field to line items"""

import sys

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, "/home/kaihaan/prj/spending/backend")

from mcp.gmail_parsing.orchestrator import parse_receipt_content

DB_CONFIG = {
    "host": "localhost",
    "port": "5433",
    "user": "spending_user",
    "password": "aC0_Xbvulrw8ldPgU6sa",
    "database": "spending_db",
}


def reparse_deliveroo():
    """Re-parse Deliveroo receipts to add restaurant metadata"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Get Deliveroo receipts with their email content
        cursor.execute("""
            SELECT
                gr.id,
                gr.message_id,
                gr.subject,
                gr.merchant_name,
                gr.sender_email,
                gec.body_html,
                gec.body_text
            FROM gmail_receipts gr
            JOIN gmail_email_content gec ON gr.message_id = gec.message_id
            WHERE gr.merchant_name ILIKE '%deliveroo%'
            ORDER BY gr.id
        """)

        receipts = cursor.fetchall()
        print(f"Found {len(receipts)} Deliveroo receipts to re-parse\n")

        updated = 0
        failed = 0

        for receipt in receipts:
            print(
                f"Re-parsing receipt ID {receipt['id']}: {receipt['subject'][:50]}..."
            )

            # Re-parse the email
            sender_domain = (
                receipt["sender_email"].split("@")[1]
                if "@" in receipt["sender_email"]
                else ""
            )
            parsed_result = parse_receipt_content(
                html_body=receipt["body_html"] or "",
                text_body=receipt["body_text"] or "",
                subject=receipt["subject"],
                sender_email=receipt["sender_email"],
                sender_domain=sender_domain,
                skip_llm=True,
            )

            if not parsed_result:
                print("  ❌ Parsing failed")
                failed += 1
                continue

            # Check if restaurant field was added
            line_items = parsed_result.get("line_items", [])
            has_restaurant = any(
                item.get("restaurant") for item in line_items if isinstance(item, dict)
            )

            if not has_restaurant:
                print("  ⚠️  No restaurant field in parsed result")
                failed += 1
                continue

            # Update the receipt with new line_items
            import json

            cursor.execute(
                """
                UPDATE gmail_receipts
                SET line_items = %s::jsonb,
                    parse_method = %s,
                    parse_confidence = %s
                WHERE id = %s
            """,
                (
                    json.dumps(line_items),
                    parsed_result.get("parse_method"),
                    parsed_result.get("parse_confidence"),
                    receipt["id"],
                ),
            )

            restaurant_name = (
                line_items[0].get("restaurant", "Unknown") if line_items else "Unknown"
            )
            print(f"  ✓ Updated with restaurant: {restaurant_name}")
            updated += 1

        conn.commit()

        print(f"\n{'=' * 80}")
        print("RE-PARSE COMPLETE")
        print(f"{'=' * 80}")
        print(f"Updated: {updated}")
        print(f"Failed: {failed}")
        print(f"{'=' * 80}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    reparse_deliveroo()
