#!/usr/bin/env python3
"""
Test script to manually dispatch PDF processing tasks for existing receipts.
This tests Phase 2 async PDF processing without relying on the sync loop.
"""

import os
import re
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from database_postgres import get_db

from tasks.gmail_tasks import process_pdf_receipt_task


def extract_translink_pdf_url(html_body: str) -> str:
    """Extract PDF URL from Translink email."""
    link_match = re.search(
        r'href="([^"]+)"[^>]*>\s*Click here to view your receipt',
        html_body,
        re.IGNORECASE,
    )
    if link_match:
        return link_match.group(1)
    return None


def get_email_content(message_id: str):
    """Fetch email content from database."""
    with get_db() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
                SELECT body_html, body_text, attachments
                FROM gmail_email_content
                WHERE message_id = %s
            """,
            (message_id,),
        )
        result = cursor.fetchone()
        if result:
            return {
                "body_html": result[0],
                "body_text": result[1],
                "attachments": result[2] or [],
            }
    return None


def test_translink_pdf(receipt_id: int, message_id: str, connection_id: int):
    """Test Translink PDF processing (external URL)."""
    print(f"\n{'=' * 80}")
    print("Testing Translink PDF Processing")
    print(f"Receipt ID: {receipt_id}, Message ID: {message_id}")
    print(f"{'=' * 80}\n")

    # Get email content
    content = get_email_content(message_id)
    if not content:
        print(f"❌ Email content not found for message {message_id}")
        return False

    # Extract PDF URL
    pdf_url = extract_translink_pdf_url(content["body_html"])
    if not pdf_url:
        print("❌ Could not find PDF URL in email body")
        return False

    print(f"✅ Found PDF URL: {pdf_url}")

    # Dispatch task
    pdf_task_info = {"external_url": pdf_url, "filename": "translink_receipt.pdf"}

    print("📤 Dispatching PDF task to Celery...")
    task = process_pdf_receipt_task.delay(
        receipt_id=receipt_id,
        message_id=message_id,
        attachment_info=pdf_task_info,
        sender_domain="translink.co.uk",
        connection_id=connection_id,
        received_date="2025-12-22",
    )

    print(f"✅ Task dispatched: {task.id}")
    print(f"   Task state: {task.state}")

    return True


def test_google_pdf(receipt_id: int, message_id: str, connection_id: int):
    """Test Google Cloud PDF processing (Gmail attachment)."""
    print(f"\n{'=' * 80}")
    print("Testing Google Cloud PDF Processing")
    print(f"Receipt ID: {receipt_id}, Message ID: {message_id}")
    print(f"{'=' * 80}\n")

    # Get email content
    content = get_email_content(message_id)
    if not content:
        print(f"❌ Email content not found for message {message_id}")
        return False

    # Find PDF attachment
    attachments = content.get("attachments", [])
    pdf_attachment = None
    for att in attachments:
        if att.get("mime_type", "").startswith("application/pdf"):
            pdf_attachment = att
            break

    if not pdf_attachment:
        print("❌ No PDF attachment found")
        print(f"   Available attachments: {[a.get('filename') for a in attachments]}")
        return False

    print(f"✅ Found PDF attachment: {pdf_attachment.get('filename')}")
    print(f"   Attachment ID: {pdf_attachment.get('attachment_id')}")

    # Dispatch task
    pdf_task_info = {
        "attachment_id": pdf_attachment.get("attachment_id"),
        "filename": pdf_attachment.get("filename", "google_invoice.pdf"),
    }

    print("📤 Dispatching PDF task to Celery...")
    task = process_pdf_receipt_task.delay(
        receipt_id=receipt_id,
        message_id=message_id,
        attachment_info=pdf_task_info,
        sender_domain="google.com",
        connection_id=connection_id,
        received_date="2025-12-02",
    )

    print(f"✅ Task dispatched: {task.id}")
    print(f"   Task state: {task.state}")

    return True


if __name__ == "__main__":
    print("\n🧪 Manual PDF Processing Test (Phase 2 Validation)")
    print("=" * 80)

    # Test Translink (external URL)
    success1 = test_translink_pdf(
        receipt_id=8999, message_id="19b465dee395bfe1", connection_id=4
    )

    # Test Google (Gmail attachment)
    success2 = test_google_pdf(
        receipt_id=9015, message_id="19adca88365c2e46", connection_id=4
    )

    print(f"\n{'=' * 80}")
    print("Test Summary:")
    print(f"  Translink PDF: {'✅ PASSED' if success1 else '❌ FAILED'}")
    print(f"  Google PDF: {'✅ PASSED' if success2 else '❌ FAILED'}")
    print(f"{'=' * 80}\n")

    print("📊 Monitor task execution with:")
    print(
        "   docker logs -f spending-celery | grep -E '(PDF|PERF|receipt 8999|receipt 9015)'"
    )
    print("\n📋 Check task status in database:")
    print(
        "   SELECT id, message_id, pdf_processing_status, pdf_retry_count, pdf_last_error"
    )
    print("   FROM gmail_receipts WHERE id IN (8999, 9015);")
