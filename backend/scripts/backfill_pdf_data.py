#!/usr/bin/env python3
"""Backfill PDF-extracted data to gmail_receipts"""

import sys

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, "/home/kaihaan/prj/spending/backend")

from mcp.gmail_pdf_parser import parse_receipt_pdf
from mcp.minio_client import get_pdf

DB_CONFIG = {
    "host": "localhost",
    "port": "5433",
    "user": "spending_user",
    "password": "aC0_Xbvulrw8ldPgU6sa",
    "database": "spending_db",
}


def backfill_pdf_data():
    """Update gmail_receipts with data extracted from PDF attachments"""
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Find receipts that have PDF attachments but missing data
        cursor.execute("""
            SELECT gr.id, gr.merchant_name, gr.sender_email, pa.object_key, pa.filename
            FROM gmail_receipts gr
            JOIN pdf_attachments pa ON gr.id = pa.gmail_receipt_id
            WHERE (gr.total_amount IS NULL OR gr.total_amount = 0)
            ORDER BY gr.id
        """)

        receipts = cursor.fetchall()
        print(f"Found {len(receipts)} receipts with PDFs but missing amounts\n")

        updated = 0
        failed = 0

        for receipt in receipts:
            print(f"Processing ID {receipt['id']} ({receipt['merchant_name']})...")

            # Get PDF from MinIO
            pdf_bytes = get_pdf(receipt["object_key"])
            if not pdf_bytes:
                print("  ❌ Failed to get PDF from MinIO")
                failed += 1
                continue

            # Parse PDF
            sender_domain = (
                receipt["sender_email"].split("@")[1]
                if "@" in receipt["sender_email"]
                else ""
            )
            pdf_result = parse_receipt_pdf(
                pdf_bytes, sender_domain, receipt["filename"]
            )

            if not pdf_result or pdf_result.get("total_amount") is None:
                print("  ⚠️  PDF parsing failed or no amount found")
                failed += 1
                continue

            # Update receipt with PDF data
            update_fields = []
            update_values = []

            if pdf_result.get("total_amount") is not None:
                update_fields.append("total_amount = %s")
                update_values.append(pdf_result["total_amount"])

            if pdf_result.get("currency_code"):
                update_fields.append("currency_code = %s")
                update_values.append(pdf_result["currency_code"])

            if pdf_result.get("order_id"):
                update_fields.append("order_id = %s")
                update_values.append(pdf_result["order_id"])

            if pdf_result.get("line_items"):
                update_fields.append("line_items = %s::jsonb")
                import json

                update_values.append(json.dumps(pdf_result["line_items"]))

            if pdf_result.get("parse_method"):
                update_fields.append("parse_method = %s")
                update_values.append(pdf_result["parse_method"])

            if pdf_result.get("parse_confidence"):
                update_fields.append("parse_confidence = %s")
                update_values.append(pdf_result["parse_confidence"])

            if update_fields:
                update_values.append(receipt["id"])
                cursor.execute(
                    f"""
                    UPDATE gmail_receipts
                    SET {", ".join(update_fields)}
                    WHERE id = %s
                """,
                    update_values,
                )

                print(f"  ✓ Updated with amount: £{pdf_result['total_amount']:.2f}")
                updated += 1
            else:
                print("  ⚠️  No fields to update")
                failed += 1

        conn.commit()

        print(f"\n{'=' * 80}")
        print("BACKFILL COMPLETE")
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
    backfill_pdf_data()
