#!/usr/bin/env python3
"""
Test brand extraction fix.

Re-parses receipts to test improved brand extraction for multiple vendors.
"""

import os
import sys

# Add backend to path
sys.path.insert(0, '/home/kaihaan/prj/spending/backend')

# Set environment
os.environ['DB_TYPE'] = 'postgres'
os.environ['POSTGRES_HOST'] = 'localhost'
os.environ['POSTGRES_PORT'] = '5433'
os.environ['POSTGRES_PASSWORD'] = 'aC0_Xbvulrw8ldPgU6sa'

import database_postgres as database
from mcp.gmail_parsing.orchestrator import parse_receipt_content

def test_brand_extraction():
    """Re-parse receipts to test brand extraction."""
    print("=" * 80)
    print("Testing Brand Extraction Fix")
    print("=" * 80)

    # Target vendors: Amazon, Apple, eBay, Uber, Deliveroo
    vendors = ['vendor_amazon', 'vendor_apple', 'vendor_ebay', 'vendor_uber', 'vendor_deliveroo']

    # Get sample receipts from each vendor
    query = """
        SELECT
            gr.id,
            gr.message_id,
            gr.parse_method,
            gr.subject,
            gr.line_items,
            gec.body_html,
            gec.body_text,
            gec.received_at,
            gec.from_header
        FROM gmail_receipts gr
        JOIN gmail_email_content gec ON gr.message_id = gec.message_id
        WHERE gr.parse_method = ANY(%s)
          AND gr.deleted_at IS NULL
        ORDER BY gr.parse_method, gr.id
        LIMIT 50
    """

    with database.get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(query, (vendors,))
            receipts = cursor.fetchall()

    if not receipts:
        print("❌ No receipts found")
        return

    print(f"\n✓ Found {len(receipts)} receipts to test\n")

    results = {
        'vendor_amazon': {'total': 0, 'with_brand': 0},
        'vendor_apple': {'total': 0, 'with_brand': 0},
        'vendor_ebay': {'total': 0, 'with_brand': 0},
        'vendor_uber': {'total': 0, 'with_brand': 0},
        'vendor_deliveroo': {'total': 0, 'with_brand': 0},
    }

    for receipt in receipts:
        receipt_id, message_id, parse_method, subject, old_items, html, text, received_at, from_header = receipt

        # Extract sender domain
        sender_domain = from_header.split('@')[-1] if '@' in from_header else ''

        # Re-parse with new logic
        parsed = parse_receipt_content(
            html_body=html,
            text_body=text,
            subject=subject,
            sender_email=from_header,
            sender_domain=sender_domain,
            skip_llm=True,
            received_at=received_at
        )

        new_items = parsed.get('line_items', [])
        has_brand = any(item.get('brand') for item in new_items) if new_items else False

        results[parse_method]['total'] += 1
        if has_brand:
            results[parse_method]['with_brand'] += 1

        # Update database if line_items changed
        if new_items and new_items != old_items:
            with database.get_db() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE gmail_receipts SET line_items = %s WHERE id = %s",
                        (database.psycopg2.extras.Json(new_items), receipt_id)
                    )
                    conn.commit()

        # Show sample
        if results[parse_method]['total'] <= 3:  # Show first 3 of each vendor
            brand_value = new_items[0].get('brand', 'NONE') if new_items else 'NO_ITEMS'
            symbol = "✓" if has_brand else "❌"
            print(f"{symbol} {parse_method:20s} ID {receipt_id:4d}: brand={brand_value:30s} | {subject[:40]}")

    print("\n" + "=" * 80)
    print("RESULTS BY VENDOR:")
    print("=" * 80)
    for vendor, stats in results.items():
        if stats['total'] > 0:
            pct = (stats['with_brand'] / stats['total']) * 100 if stats['total'] > 0 else 0
            symbol = "✓" if pct >= 80 else "⚠" if pct >= 50 else "❌"
            print(f"{symbol} {vendor:20s}: {stats['with_brand']:3d}/{stats['total']:3d} ({pct:5.1f}%)")

    print("\n" + "=" * 80)
    print("OVERALL:")
    print("=" * 80)
    total = sum(v['total'] for v in results.values())
    with_brand = sum(v['with_brand'] for v in results.values())
    pct = (with_brand / total) * 100 if total > 0 else 0
    print(f"✓ Total receipts with brand: {with_brand}/{total} ({pct:.1f}%)")
    print("=" * 80)


if __name__ == '__main__':
    test_brand_extraction()
