"""
Gmail integration models for receipt parsing and PDF storage.

Maps to:
- gmail_connections table
- gmail_receipts table
- gmail_email_content table
- pdf_attachments table

See: .claude/docs/database/DATABASE_SCHEMA.md#23-gmail_connections
"""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database.base import Base


class GmailConnection(Base):
    """OAuth connections to Gmail API (encrypted tokens)."""

    __tablename__ = "gmail_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, default=1)
    email_address = Column(String(255), nullable=False)
    access_token = Column(Text, nullable=False)  # Encrypted
    refresh_token = Column(Text, nullable=False)  # Encrypted
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    encryption_version = Column(Integer, nullable=True, default=1)
    scopes = Column(Text, nullable=True)
    connection_status = Column(
        String(20), nullable=True, default="active", server_default="active"
    )
    history_id = Column(String(50), nullable=True)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_from_date = Column(Date, nullable=True)
    error_count = Column(Integer, nullable=True, default=0, server_default="0")
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "email_address", name="uq_gmail_conn_user_email"),
        CheckConstraint(
            "connection_status IN ('active', 'expired', 'revoked', 'error')",
            name="ck_gmail_conn_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailConnection(id={self.id}, email={self.email_address}, status={self.connection_status})>"


class GmailReceipt(Base):
    """Parsed receipt metadata from Gmail."""

    __tablename__ = "gmail_receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(
        Integer,
        ForeignKey("gmail_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id = Column(String(255), nullable=False, unique=True)
    thread_id = Column(String(255), nullable=True)
    sender_email = Column(String(255), nullable=False)
    sender_name = Column(String(255), nullable=True)
    subject = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    merchant_name = Column(String(255), nullable=True)
    merchant_name_normalized = Column(String(255), nullable=True)
    merchant_domain = Column(String(255), nullable=True)
    order_id = Column(String(255), nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    currency_code = Column(String(3), nullable=True, default="GBP")
    receipt_date = Column(Date, nullable=True)
    line_items = Column(JSONB, nullable=True)
    receipt_hash = Column(String(64), nullable=True)
    parse_method = Column(String(30), nullable=True)
    parse_confidence = Column(Integer, nullable=False)
    raw_schema_data = Column(JSONB, nullable=True)
    llm_cost_cents = Column(Integer, nullable=True)
    parsing_status = Column(
        String(20), nullable=True, default="pending", server_default="pending"
    )
    parsing_error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=True, default=0, server_default="0")
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    llm_parse_status = Column(String(20), nullable=True)
    llm_estimated_cost_cents = Column(Integer, nullable=True)
    llm_actual_cost_cents = Column(Integer, nullable=True)
    llm_parsed_at = Column(DateTime(timezone=True), nullable=True)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_gmail_receipts_connection", "connection_id"),
        Index("idx_gmail_receipts_connection_date", "connection_id", "receipt_date"),
        Index("idx_gmail_receipts_merchant", "merchant_name_normalized"),
        Index("idx_gmail_receipts_amount_date", "total_amount", "receipt_date"),
        Index(
            "idx_gmail_receipts_not_deleted",
            "id",
            postgresql_where=Column("deleted_at").is_(None),
        ),
        CheckConstraint(
            "parse_confidence >= 0 AND parse_confidence <= 100",
            name="ck_gmail_receipt_confidence",
        ),
        CheckConstraint(
            "parsing_status IN ('pending', 'parsed', 'failed', 'matched', 'unparseable')",
            name="ck_gmail_receipt_parsing_status",
        ),
        CheckConstraint(
            "parse_method IN ('schema_org', 'pattern', 'llm', 'manual', 'pending', "
            "'pre_filter', 'unknown', 'generic_pdf', 'none', 'vendor_amazon', "
            "'vendor_apple', 'vendor_paypal', 'vendor_uber', 'vendor_lyft', "
            "'vendor_lime', 'vendor_deliveroo', 'vendor_ebay', 'vendor_etsy', "
            "'vendor_vinted', 'vendor_john_lewis', 'vendor_uniqlo', 'vendor_cex', "
            "'vendor_world_of_books', 'vendor_microsoft', 'vendor_google', "
            "'vendor_figma', 'vendor_atlassian', 'vendor_anthropic', 'vendor_airbnb', "
            "'vendor_british_airways', 'vendor_dhl') OR parse_method IS NULL",
            name="ck_gmail_receipt_parse_method",
        ),
        CheckConstraint(
            "llm_parse_status IN ('pending', 'processing', 'completed', 'failed') OR llm_parse_status IS NULL",
            name="ck_gmail_receipt_llm_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailReceipt(id={self.id}, message_id={self.message_id}, merchant={self.merchant_name})>"


class GmailEmailContent(Base):
    """Raw email content for re-parsing (separate from parsed data)."""

    __tablename__ = "gmail_email_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(255), nullable=False, unique=True)
    thread_id = Column(String(255), nullable=True)
    subject = Column(Text, nullable=True)
    from_header = Column(Text, nullable=True)
    to_header = Column(Text, nullable=True)
    date_header = Column(Text, nullable=True)
    list_unsubscribe = Column(Text, nullable=True)
    x_mailer = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    attachments = Column(JSONB, nullable=True)
    size_estimate = Column(Integer, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_gmail_email_content_message_id", "message_id"),
        Index("idx_gmail_email_content_received", "received_at"),
    )

    def __repr__(self) -> str:
        return f"<GmailEmailContent(id={self.id}, message_id={self.message_id}, subject={self.subject})>"


class PDFAttachment(Base):
    """Metadata for PDF attachments stored in MinIO object storage."""

    __tablename__ = "pdf_attachments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    gmail_receipt_id = Column(
        Integer,
        ForeignKey("gmail_receipts.id", ondelete="CASCADE"),
        nullable=True,
    )
    message_id = Column(String(255), nullable=False)
    bucket_name = Column(String(100), nullable=True, default="receipts")
    object_key = Column(String(500), nullable=False, unique=True)
    filename = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    mime_type = Column(
        String(100),
        nullable=True,
        default="application/pdf",
        server_default="application/pdf",
    )
    etag = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("message_id", "filename", name="uq_pdf_message_filename"),
        Index("idx_pdf_attachments_receipt", "gmail_receipt_id"),
        Index("idx_pdf_attachments_hash", "content_hash"),
    )

    def __repr__(self) -> str:
        return f"<PDFAttachment(id={self.id}, filename={self.filename}, size={self.size_bytes})>"
