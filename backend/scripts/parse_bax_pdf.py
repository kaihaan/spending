#!/usr/bin/env python3
"""
Quick script to download and parse Bax Music PDF invoice.
"""

import sys
sys.path.insert(0, '/app')

from mcp.gmail_client import build_gmail_service, get_attachment_content
from mcp.gmail_pdf_parser import extract_text_from_pdf
import database_postgres as db
import re

# Get Bax Music receipt
receipt = db.get_gmail_receipt_by_id(10080)
if not receipt:
    print("❌ Receipt not found")
    sys.exit(1)

print(f"📧 Receipt: {receipt['subject']}")
print(f"   Merchant: {receipt['merchant_name']}")
print(f"   Current amount: {receipt.get('total_amount')}")

# Get email content with attachments
import psycopg2.extras
with db.get_db() as conn:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
        cursor.execute("""
            SELECT attachments, message_id
            FROM gmail_email_content
            WHERE message_id = %s
        """, (receipt['message_id'],))
        email_content = cursor.fetchone()

if not email_content or not email_content['attachments']:
    print("❌ No attachments found")
    sys.exit(1)

import json
attachments = json.loads(email_content['attachments']) if isinstance(email_content['attachments'], str) else email_content['attachments']

# Find the invoice PDF
invoice_pdf = None
for att in attachments:
    if 'BAX-INV' in att['filename']:
        invoice_pdf = att
        break

if not invoice_pdf:
    print("❌ Invoice PDF not found")
    sys.exit(1)

print(f"\n📄 Found PDF: {invoice_pdf['filename']} ({invoice_pdf['size']} bytes)")

# Download PDF
connection = db.get_gmail_connection(1)
if not connection:
    print("❌ No Gmail connection")
    sys.exit(1)

session = build_gmail_service(connection['access_token'], connection.get('refresh_token'))
pdf_bytes = get_attachment_content(session, email_content['message_id'], invoice_pdf['attachment_id'])

print(f"✓ Downloaded {len(pdf_bytes)} bytes")

# Extract text
pdf_text = extract_text_from_pdf(pdf_bytes)
if not pdf_text:
    print("❌ Failed to extract PDF text")
    sys.exit(1)

print(f"\n📝 PDF Text (first 500 chars):")
print("=" * 60)
print(pdf_text[:500])
print("=" * 60)

# Parse amount - look for "Total" or "Amount Due" patterns
amount_patterns = [
    r'(?:Total|Amount\s+Due|Invoice\s+Total)[:\s]+[£$€]?\s*(\d+[.,]\d{2})',
    r'[£$€]\s*(\d+[.,]\d{2})\s*(?:GBP|USD|EUR)?$',
    r'Total\s+[£$€]?\s*(\d+[.,]\d{2})',
]

amount = None
for pattern in amount_patterns:
    matches = re.findall(pattern, pdf_text, re.MULTILINE | re.IGNORECASE)
    if matches:
        # Get the last match (usually the final total)
        amount_str = matches[-1].replace(',', '.')
        amount = float(amount_str)
        print(f"\n✓ Found amount: £{amount}")
        break

if not amount:
    print("\n⚠️  Could not extract amount automatically")
    print("\nPlease review the PDF text above and tell me the total amount.")
else:
    # Update receipt
    with db.get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                UPDATE gmail_receipts
                SET total_amount = %s,
                    currency_code = 'GBP'
                WHERE id = %s
            """, (amount, 10080))
            conn.commit()
    print(f"\n✅ Updated receipt {10080} with amount £{amount}")
