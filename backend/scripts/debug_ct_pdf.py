#!/usr/bin/env python3
"""Debug Charles Tyrwhitt PDF parsing"""

import sys

import psycopg2
from psycopg2.extras import RealDictCursor

sys.path.insert(0, "/home/kaihaan/prj/spending/backend")

import re

from mcp.gmail_pdf_parser import extract_text_from_pdf, parse_charles_tyrwhitt_pdf
from mcp.minio_client import get_pdf

DB_CONFIG = {
    "host": "localhost",
    "port": "5433",
    "user": "spending_user",
    "password": "aC0_Xbvulrw8ldPgU6sa",
    "database": "spending_db",
}


def debug_ct_pdf():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get a Charles Tyrwhitt PDF attachment
    cursor.execute("""
        SELECT pa.object_key, pa.filename, gr.subject
        FROM pdf_attachments pa
        JOIN gmail_receipts gr ON pa.gmail_receipt_id = gr.id
        WHERE gr.merchant_name = 'Charles Tyrwhitt'
        LIMIT 1
    """)

    pdf_info = cursor.fetchone()
    if not pdf_info:
        print("No Charles Tyrwhitt PDF found")
        return

    print(f"PDF: {pdf_info['filename']}")
    print(f"Subject: {pdf_info['subject']}")
    print(f"Object key: {pdf_info['object_key']}\n")

    # Get PDF from MinIO
    try:
        pdf_bytes = get_pdf(pdf_info["object_key"])
        if not pdf_bytes:
            print("❌ Failed to get PDF from MinIO")
            return

        print(f"PDF size: {len(pdf_bytes)} bytes\n")

        # Extract text
        text = extract_text_from_pdf(pdf_bytes)
        if not text:
            print("❌ Failed to extract text from PDF")
            return

        print("=" * 80)
        print("EXTRACTED TEXT (first 2000 chars):")
        print("=" * 80)
        print(text[:2000])
        print("\n" + "=" * 80)

        # Try parsing
        result = parse_charles_tyrwhitt_pdf(pdf_bytes)
        print("\nPARSE RESULT:")
        print("=" * 80)
        if result:
            for key, value in result.items():
                print(f"{key}: {value}")
        else:
            print("❌ Parser returned None")

        # Try manual pattern matching
        print("\n" + "=" * 80)
        print("MANUAL PATTERN TESTS:")
        print("=" * 80)

        # Test total patterns
        total_patterns = [
            r"(?:Grand\s+)?Total[:\s]*£\s*([0-9,]+\.?\d*)",
            r"(?:Grand\s+)?Total\s+(?:GBP\s+)?£?\s*([0-9,]+\.?\d*)",
            r"Amount\s+(?:Paid|Due)[:\s]*£\s*([0-9,]+\.?\d*)",
            r"Total[:\s]+([0-9,]+\.[0-9]{2})",
        ]
        for i, pattern in enumerate(total_patterns):
            matches = re.findall(pattern, text, re.IGNORECASE)
            print(f"Pattern {i + 1}: {matches[:5] if matches else 'No matches'}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    debug_ct_pdf()
