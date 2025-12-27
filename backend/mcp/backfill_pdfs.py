"""
Backfill scripts for Gmail data:
1. Email content - fetch from Gmail API and store in gmail_email_content table
2. PDF attachments - download from Gmail and store in MinIO

Usage:
    source venv/bin/activate
    cd backend

    # Backfill email content for receipts missing it:
    DB_TYPE=postgres python -c "from mcp.backfill_pdfs import backfill_email_content; backfill_email_content()"

    # Backfill PDFs:
    DB_TYPE=postgres python -c "from mcp.backfill_pdfs import backfill_all_pdfs; backfill_all_pdfs()"
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import time

import database

from .gmail_auth import get_gmail_credentials
from .gmail_client import build_gmail_service, get_message_content
from .minio_client import is_available, store_pdf


def backfill_email_content(batch_size: int = 50, delay_seconds: float = 0.5):
    """
    Backfill email content for receipts that are missing entries in gmail_email_content.

    Fetches raw email content from Gmail API and stores in gmail_email_content table.
    This enables re-parsing emails with updated vendor parsers without re-fetching.

    Args:
        batch_size: Number of emails to fetch per batch (default 50)
        delay_seconds: Delay between API calls to respect rate limits (default 0.5s)
    """
    print("=== Backfill Email Content ===\n")

    # Find receipts missing content
    conn = database.connection_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    gr.id,
                    gr.connection_id,
                    gr.message_id,
                    gr.merchant_name,
                    gr.received_at
                FROM gmail_receipts gr
                WHERE gr.deleted_at IS NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM gmail_email_content gec
                    WHERE gec.message_id = gr.message_id
                  )
                ORDER BY gr.connection_id, gr.received_at DESC
            """)
            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            missing = [dict(zip(columns, row, strict=False)) for row in rows]
    finally:
        database.connection_pool.putconn(conn)

    total = len(missing)
    print(f"Found {total} receipts missing email content\n")

    if not missing:
        print("✓ All receipts have email content stored")
        return None

    # Group by connection_id for efficiency
    by_connection = {}
    for receipt in missing:
        cid = receipt["connection_id"]
        if cid not in by_connection:
            by_connection[cid] = []
        by_connection[cid].append(receipt)

    print(f"Receipts grouped by {len(by_connection)} connection(s)\n")

    # Process each connection
    fetched = 0
    failed = 0
    services = {}  # Cache Gmail service per connection

    for connection_id, receipts in by_connection.items():
        print(f"\n--- Connection {connection_id} ({len(receipts)} receipts) ---")

        # Get or create Gmail service for this connection
        if connection_id not in services:
            try:
                access_token, refresh_token = get_gmail_credentials(connection_id)
                service = build_gmail_service(access_token, refresh_token)
                if not service:
                    print(
                        f"❌ Could not build Gmail service for connection {connection_id}"
                    )
                    failed += len(receipts)
                    continue
                services[connection_id] = service
                print("✓ Gmail service ready")
            except Exception as e:
                print(f"❌ Failed to get credentials: {e}")
                failed += len(receipts)
                continue

        service = services[connection_id]

        # Fetch each receipt's content
        for i, receipt in enumerate(receipts):
            message_id = receipt["message_id"]
            merchant = receipt.get("merchant_name", "Unknown")

            try:
                # Fetch from Gmail API
                message = get_message_content(service, message_id)

                if not message:
                    print(f"  ⚠️ [{i + 1}/{len(receipts)}] Could not fetch: {merchant}")
                    failed += 1
                    continue

                # Store in database
                database.save_gmail_email_content(message)
                fetched += 1

                # Progress update every 10 or at end
                if (i + 1) % 10 == 0 or i == len(receipts) - 1:
                    print(f"  ✓ [{i + 1}/{len(receipts)}] Fetched: {merchant}")

                # Rate limit delay
                time.sleep(delay_seconds)

            except Exception as e:
                print(f"  ❌ [{i + 1}/{len(receipts)}] Error for {merchant}: {e}")
                failed += 1

    print("\n=== Summary ===")
    print(f"Total missing: {total}")
    print(f"Fetched: {fetched}")
    print(f"Failed: {failed}")

    return {"fetched": fetched, "failed": failed, "total": total}


def backfill_all_pdfs(vendor_filter: str = None):
    """
    Backfill PDFs for all receipts that have PDF attachments but aren't stored in MinIO.

    Args:
        vendor_filter: Optional merchant_domain to filter (e.g., 'google.com')
    """
    title = (
        f"Backfill PDFs for {vendor_filter}" if vendor_filter else "Backfill All PDFs"
    )
    print(f"=== {title} ===\n")

    # Check MinIO availability
    if not is_available():
        print("❌ MinIO not available")
        return
    print("✓ MinIO available\n")

    # Get Gmail service - find an active connection
    conn = database.connection_pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, email_address FROM gmail_connections
                WHERE connection_status = 'active' LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                print("❌ No active Gmail connection found")
                return
            connection_id = row[0]
            email_address = row[1]
    finally:
        database.connection_pool.putconn(conn)

    # Get credentials and build service
    try:
        access_token, refresh_token = get_gmail_credentials(connection_id)
        service = build_gmail_service(access_token, refresh_token)
        if not service:
            print("❌ Could not build Gmail service")
            return
        print(f"✓ Gmail service ready for {email_address}\n")
    except Exception as e:
        print(f"❌ Failed to get Gmail credentials: {e}")
        return

    # Query for receipts with PDF attachments but not stored in MinIO
    conn = database.connection_pool.getconn()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT
                    gr.id,
                    gr.message_id,
                    gr.merchant_name,
                    gr.merchant_domain,
                    gr.total_amount,
                    gr.received_at,
                    gec.attachments
                FROM gmail_receipts gr
                JOIN gmail_email_content gec ON gec.message_id = gr.message_id
                LEFT JOIN pdf_attachments pa ON pa.gmail_receipt_id = gr.id
                WHERE pa.id IS NULL
                  AND gec.attachments IS NOT NULL
                  AND jsonb_array_length(gec.attachments) > 0
                  AND EXISTS (
                    SELECT 1 FROM jsonb_array_elements(gec.attachments) att
                    WHERE att->>'mime_type' = 'application/pdf'
                  )
            """
            if vendor_filter:
                query += " AND gr.merchant_domain = %s"
                query += " ORDER BY gr.received_at DESC"
                cur.execute(query, (vendor_filter,))
            else:
                query += " ORDER BY gr.merchant_domain, gr.received_at DESC"
                cur.execute(query)

            rows = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            receipts = [dict(zip(columns, row, strict=False)) for row in rows]
    finally:
        database.connection_pool.putconn(conn)

    print(f"Found {len(receipts)} receipts with PDF attachments to backfill\n")

    if not receipts:
        print("✓ All receipts with PDF attachments have been stored")
        return

    # Process each receipt
    stored = 0
    failed = 0

    current_domain = None
    for receipt in receipts:
        receipt_id = receipt["id"]
        message_id = receipt["message_id"]
        merchant = receipt["merchant_name"]
        domain = receipt.get("merchant_domain", "unknown")
        amount = receipt["total_amount"]
        received_at = receipt["received_at"]

        # Print domain header when it changes
        if domain != current_domain:
            current_domain = domain
            print(f"\n--- {domain} ---")

        # Parse attachments from JSON
        attachments = receipt["attachments"]
        if isinstance(attachments, str):
            attachments = json.loads(attachments)

        print(f"Processing: {merchant} - £{amount}")
        print(f"  Message ID: {message_id}")

        # Find PDF attachments
        pdf_attachments = [
            a for a in attachments if a.get("mime_type") == "application/pdf"
        ]
        if not pdf_attachments:
            print("  ⚠️ No PDF attachments found")
            failed += 1
            continue

        print(f"  Found {len(pdf_attachments)} PDF attachment(s)")

        # Download and store each PDF
        for att in pdf_attachments:
            filename = att.get("filename", "invoice.pdf")
            attachment_id = att.get("attachment_id")

            if not attachment_id:
                print(f"  ⚠️ No attachment_id for {filename}")
                continue

            try:
                # Download PDF from Gmail
                from .gmail_client import get_pdf_attachments

                pdf_contents = get_pdf_attachments(service, message_id, [att])

                if not pdf_contents:
                    print(f"  ⚠️ Failed to download {filename}")
                    continue

                pdf_content = pdf_contents[0]["content"]
                print(f"  Downloaded: {filename} ({len(pdf_content)} bytes)")

                # Store in MinIO
                minio_result = store_pdf(
                    pdf_bytes=pdf_content,
                    message_id=message_id,
                    filename=filename,
                    received_date=received_at,
                    metadata={"merchant": merchant},
                )

                if not minio_result:
                    print(f"  ⚠️ MinIO storage failed for {filename}")
                    continue

                # Save to database
                database.save_pdf_attachment(
                    gmail_receipt_id=receipt_id,
                    message_id=message_id,
                    bucket_name=minio_result["bucket_name"],
                    object_key=minio_result["object_key"],
                    filename=minio_result["filename"],
                    content_hash=minio_result["content_hash"],
                    size_bytes=minio_result["size_bytes"],
                    etag=minio_result["etag"],
                )

                print(f"  ✓ Stored: {minio_result['object_key']}")
                stored += 1

            except Exception as e:
                print(f"  ❌ Error: {e}")
                failed += 1

        print()

    print("\n=== Summary ===")
    print(f"Stored: {stored} PDFs")
    print(f"Failed: {failed}")


def backfill_google_cloud_pdfs():
    """Backwards-compatible wrapper for Google Cloud PDFs only."""
    backfill_all_pdfs(vendor_filter="google.com")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        backfill_all_pdfs(vendor_filter=sys.argv[1])
    else:
        backfill_all_pdfs()
