# tests/test_models/test_gmail.py
"""Tests for Gmail SQLAlchemy models.

Uses test database from conftest.py with "leave no trace" cleanup pattern.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from database.models.gmail import (
    GmailConnection,
    GmailEmailContent,
    GmailReceipt,
    PDFAttachment,
)


def test_create_gmail_connection(db_session):
    """Test creating a Gmail connection."""
    # Use a unique user_id to avoid conflicts with production data
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"

    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="encrypted_access_token",
        refresh_token="encrypted_refresh_token",
        token_expires_at=datetime(2025, 2, 15, 12, 0, 0, tzinfo=UTC),
        encryption_version=1,
        scopes="https://www.googleapis.com/auth/gmail.readonly",
        connection_status="active",
        history_id="12345",
        sync_from_date=date(2025, 1, 1),
    )
    db_session.add(connection)
    db_session.commit()

    try:
        assert connection.id is not None
        assert connection.email_address == unique_email
        assert connection.connection_status == "active"
        assert connection.error_count == 0
        assert connection.created_at is not None
        assert connection.updated_at is not None
    finally:
        db_session.delete(connection)
        db_session.commit()


def test_gmail_connection_unique_constraint(db_session):
    """Test unique constraint on (user_id, email_address)."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"

    connection1 = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token1",
        refresh_token="refresh1",
    )
    db_session.add(connection1)
    db_session.commit()

    try:
        # Attempt to insert duplicate (user_id, email_address)
        connection2 = GmailConnection(
            user_id=unique_user_id,
            email_address=unique_email,
            access_token="token2",
            refresh_token="refresh2",
        )
        db_session.add(connection2)
        with pytest.raises(IntegrityError):  # Duplicate (user_id, email_address)
            db_session.commit()
    finally:
        db_session.rollback()
        existing = (
            db_session.query(GmailConnection)
            .filter_by(user_id=unique_user_id, email_address=unique_email)
            .first()
        )
        if existing:
            db_session.delete(existing)
            db_session.commit()


def test_gmail_connection_status_check_constraint(db_session):
    """Test connection_status CHECK constraint."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"

    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
        connection_status="invalid_status",  # Invalid status
    )
    db_session.add(connection)
    with pytest.raises(IntegrityError):  # CHECK constraint violation
        db_session.commit()
    db_session.rollback()


def test_create_gmail_receipt(db_session):
    """Test creating a Gmail receipt."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"

    # First create a connection
    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
    )
    db_session.add(connection)
    db_session.commit()

    # Now create a receipt
    receipt = GmailReceipt(
        connection_id=connection.id,
        message_id=unique_message_id,
        sender_email="orders@amazon.com",
        sender_name="Amazon",
        subject="Your Amazon.com order #123-4567890-1234567",
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        merchant_name="Amazon",
        merchant_name_normalized="amazon",
        merchant_domain="amazon.com",
        order_id="123-4567890-1234567",
        total_amount=Decimal("49.99"),
        currency_code="GBP",
        receipt_date=date(2025, 1, 15),
        line_items={"items": [{"name": "USB Cable", "price": 49.99}]},
        receipt_hash="abc123def456",
        parse_method="vendor_amazon",
        parse_confidence=95,
        parsing_status="parsed",
    )
    db_session.add(receipt)
    db_session.commit()

    try:
        assert receipt.id is not None
        assert receipt.message_id == unique_message_id
        assert receipt.total_amount == Decimal("49.99")
        assert receipt.parse_confidence == 95
        assert receipt.retry_count == 0
        assert receipt.created_at is not None
        assert receipt.updated_at is not None
    finally:
        # Only delete connection - DB CASCADE will delete receipt
        db_session.delete(connection)
        db_session.commit()


def test_gmail_receipt_unique_constraint(db_session):
    """Test unique constraint on message_id."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"

    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
    )
    db_session.add(connection)
    db_session.commit()

    receipt1 = GmailReceipt(
        connection_id=connection.id,
        message_id=unique_message_id,
        sender_email="test@example.com",
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        parse_confidence=0,
    )
    db_session.add(receipt1)
    db_session.commit()

    try:
        # Attempt to insert duplicate message_id
        receipt2 = GmailReceipt(
            connection_id=connection.id,
            message_id=unique_message_id,
            sender_email="test@example.com",
            received_at=datetime(2025, 1, 16, 10, 30, 0, tzinfo=UTC),
            parse_confidence=0,
        )
        db_session.add(receipt2)
        with pytest.raises(IntegrityError):  # Duplicate message_id
            db_session.commit()
    finally:
        db_session.rollback()
        # Only delete connection - DB CASCADE will delete receipt
        existing_conn = (
            db_session.query(GmailConnection)
            .filter_by(user_id=unique_user_id, email_address=unique_email)
            .first()
        )
        if existing_conn:
            db_session.delete(existing_conn)
            db_session.commit()


def test_gmail_receipt_parse_confidence_check_constraint(db_session):
    """Test parse_confidence CHECK constraint (0-100)."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"

    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
    )
    db_session.add(connection)
    db_session.commit()

    try:
        receipt = GmailReceipt(
            connection_id=connection.id,
            message_id=unique_message_id,
            sender_email="test@example.com",
            received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
            parse_confidence=150,  # Invalid: > 100
        )
        db_session.add(receipt)
        with pytest.raises(IntegrityError):  # CHECK constraint violation
            db_session.commit()
    finally:
        db_session.rollback()
        existing = (
            db_session.query(GmailConnection)
            .filter_by(user_id=unique_user_id, email_address=unique_email)
            .first()
        )
        if existing:
            db_session.delete(existing)
            db_session.commit()


def test_create_gmail_email_content(db_session):
    """Test creating Gmail email content."""
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"

    content = GmailEmailContent(
        message_id=unique_message_id,
        thread_id="thread_abc",
        subject="Test Email",
        from_header="test@example.com",
        to_header="user@gmail.com",
        date_header="Mon, 15 Jan 2025 10:30:00 +0000",
        body_html="<html><body>Test email body</body></html>",
        body_text="Test email body",
        snippet="Test email...",
        attachments=[{"filename": "receipt.pdf", "mimeType": "application/pdf"}],
        size_estimate=1024,
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
    )
    db_session.add(content)
    db_session.commit()

    try:
        assert content.id is not None
        assert content.message_id == unique_message_id
        assert content.subject == "Test Email"
        assert content.fetched_at is not None
    finally:
        db_session.delete(content)
        db_session.commit()


def test_gmail_email_content_unique_constraint(db_session):
    """Test unique constraint on message_id."""
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"

    content1 = GmailEmailContent(
        message_id=unique_message_id,
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
    )
    db_session.add(content1)
    db_session.commit()

    try:
        # Attempt to insert duplicate message_id
        content2 = GmailEmailContent(
            message_id=unique_message_id,
            received_at=datetime(2025, 1, 16, 10, 30, 0, tzinfo=UTC),
        )
        db_session.add(content2)
        with pytest.raises(IntegrityError):  # Duplicate message_id
            db_session.commit()
    finally:
        db_session.rollback()
        existing = (
            db_session.query(GmailEmailContent)
            .filter_by(message_id=unique_message_id)
            .first()
        )
        if existing:
            db_session.delete(existing)
            db_session.commit()


def test_create_pdf_attachment(db_session):
    """Test creating a PDF attachment."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"
    unique_object_key = f"2025/01/15/{unique_message_id}/receipt.pdf"

    # First create a connection
    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
    )
    db_session.add(connection)
    db_session.commit()

    # Create a receipt
    receipt = GmailReceipt(
        connection_id=connection.id,
        message_id=unique_message_id,
        sender_email="orders@example.com",
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        parse_confidence=0,
    )
    db_session.add(receipt)
    db_session.commit()

    # Create a PDF attachment
    attachment = PDFAttachment(
        gmail_receipt_id=receipt.id,
        message_id=unique_message_id,
        bucket_name="receipts",
        object_key=unique_object_key,
        filename="receipt.pdf",
        content_hash="sha256_abc123",
        size_bytes=102400,
        mime_type="application/pdf",
        etag="etag_12345",
    )
    db_session.add(attachment)
    db_session.commit()

    try:
        assert attachment.id is not None
        assert attachment.message_id == unique_message_id
        assert attachment.size_bytes == 102400
        assert attachment.created_at is not None
    finally:
        # Only delete connection - DB CASCADE will delete receipt and attachment
        # (Gmail models have ondelete="CASCADE" on foreign keys)
        db_session.delete(connection)
        db_session.commit()


def test_pdf_attachment_unique_object_key(db_session):
    """Test unique constraint on object_key."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"
    unique_object_key = f"2025/01/15/{unique_message_id}/receipt.pdf"

    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
    )
    db_session.add(connection)
    db_session.commit()

    receipt = GmailReceipt(
        connection_id=connection.id,
        message_id=unique_message_id,
        sender_email="test@example.com",
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        parse_confidence=0,
    )
    db_session.add(receipt)
    db_session.commit()

    attachment1 = PDFAttachment(
        gmail_receipt_id=receipt.id,
        message_id=unique_message_id,
        object_key=unique_object_key,
        filename="receipt.pdf",
        content_hash="hash1",
        size_bytes=1024,
    )
    db_session.add(attachment1)
    db_session.commit()

    try:
        # Attempt to insert duplicate object_key
        attachment2 = PDFAttachment(
            gmail_receipt_id=receipt.id,
            message_id=unique_message_id,
            object_key=unique_object_key,
            filename="receipt_copy.pdf",
            content_hash="hash2",
            size_bytes=2048,
        )
        db_session.add(attachment2)
        with pytest.raises(IntegrityError):  # Duplicate object_key
            db_session.commit()
    finally:
        db_session.rollback()
        # Only delete connection - DB CASCADE will delete receipt and attachment
        existing_conn = (
            db_session.query(GmailConnection)
            .filter_by(user_id=unique_user_id, email_address=unique_email)
            .first()
        )
        if existing_conn:
            db_session.delete(existing_conn)
            db_session.commit()


def test_pdf_attachment_unique_message_filename(db_session):
    """Test unique constraint on (message_id, filename)."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"
    unique_object_key1 = f"2025/01/15/{unique_message_id}/receipt.pdf"
    unique_object_key2 = f"2025/01/15/{unique_message_id}/other_path/receipt.pdf"

    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
    )
    db_session.add(connection)
    db_session.commit()

    receipt = GmailReceipt(
        connection_id=connection.id,
        message_id=unique_message_id,
        sender_email="test@example.com",
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        parse_confidence=0,
    )
    db_session.add(receipt)
    db_session.commit()

    attachment1 = PDFAttachment(
        gmail_receipt_id=receipt.id,
        message_id=unique_message_id,
        object_key=unique_object_key1,
        filename="receipt.pdf",
        content_hash="hash1",
        size_bytes=1024,
    )
    db_session.add(attachment1)
    db_session.commit()

    try:
        # Attempt to insert duplicate (message_id, filename)
        attachment2 = PDFAttachment(
            gmail_receipt_id=receipt.id,
            message_id=unique_message_id,
            object_key=unique_object_key2,  # Different key
            filename="receipt.pdf",  # Same filename
            content_hash="hash2",
            size_bytes=2048,
        )
        db_session.add(attachment2)
        with pytest.raises(IntegrityError):  # Duplicate (message_id, filename)
            db_session.commit()
    finally:
        db_session.rollback()
        # Only delete connection - DB CASCADE will delete receipt and attachment
        existing_conn = (
            db_session.query(GmailConnection)
            .filter_by(user_id=unique_user_id, email_address=unique_email)
            .first()
        )
        if existing_conn:
            db_session.delete(existing_conn)
            db_session.commit()


def test_pdf_attachment_cascade_delete(db_session):
    """Test CASCADE DELETE when gmail_receipt is deleted."""
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    unique_email = f"test_{uuid.uuid4().hex[:8]}@gmail.com"
    unique_message_id = f"msg_{uuid.uuid4().hex[:12]}"
    unique_object_key = f"2025/01/15/{unique_message_id}/receipt.pdf"

    connection = GmailConnection(
        user_id=unique_user_id,
        email_address=unique_email,
        access_token="token",
        refresh_token="refresh",
    )
    db_session.add(connection)
    db_session.commit()

    receipt = GmailReceipt(
        connection_id=connection.id,
        message_id=unique_message_id,
        sender_email="test@example.com",
        received_at=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        parse_confidence=0,
    )
    db_session.add(receipt)
    db_session.commit()

    attachment = PDFAttachment(
        gmail_receipt_id=receipt.id,
        message_id=unique_message_id,
        object_key=unique_object_key,
        filename="receipt.pdf",
        content_hash="hash1",
        size_bytes=1024,
    )
    db_session.add(attachment)
    db_session.commit()

    try:
        # Delete the receipt
        db_session.delete(receipt)
        db_session.commit()

        # Attachment should be cascade deleted
        remaining_attachments = (
            db_session.query(PDFAttachment)
            .filter_by(message_id=unique_message_id)
            .all()
        )
        assert len(remaining_attachments) == 0
    finally:
        # Clean up connection
        existing = (
            db_session.query(GmailConnection)
            .filter_by(user_id=unique_user_id, email_address=unique_email)
            .first()
        )
        if existing:
            db_session.delete(existing)
            db_session.commit()
