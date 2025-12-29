"""
Gmail integration models for receipt parsing and PDF storage.

Maps to:
- gmail_connections table
- gmail_receipts table
- gmail_email_content table
- pdf_attachments table
- gmail_oauth_state table
- gmail_sync_jobs table
- gmail_parse_statistics table
- gmail_sender_patterns table
- gmail_transaction_matches table
- gmail_merchant_aliases table (DEPRECATED)
- gmail_merchant_statistics table (DEPRECATED)
- gmail_processing_errors table (DEPRECATED)

See: .claude/docs/database/DATABASE_SCHEMA.md#23-gmail_connections
"""

from sqlalchemy import (
    Boolean,
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

    # PDF attachment processing fields
    pdf_processing_status = Column(
        String(20),
        nullable=True,
        default="none",
        server_default="none",
        comment="Status of async PDF processing: none, pending, processing, completed, failed, skipped",
    )
    pdf_retry_count = Column(Integer, nullable=True, default=0, server_default="0")
    pdf_last_error = Column(Text, nullable=True)

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


# Alias for compatibility with imports
PdfAttachment = PDFAttachment


class GmailOAuthState(Base):
    """OAuth state storage for Gmail authorization flow."""

    __tablename__ = "gmail_oauth_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    state = Column(String(255), nullable=False, unique=True)
    code_verifier = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_gmail_oauth_state_state", "state"),
        Index("idx_gmail_oauth_state_expires", "expires_at"),
    )

    def __repr__(self) -> str:
        return f"<GmailOAuthState(id={self.id}, user_id={self.user_id}, state={self.state})>"


class GmailSyncJob(Base):
    """Gmail sync job tracking."""

    __tablename__ = "gmail_sync_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(
        Integer,
        ForeignKey("gmail_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(
        String(20), nullable=True, default="queued", server_default="'queued'"
    )
    job_type = Column(
        String(20), nullable=True, default="full", server_default="'full'"
    )
    total_messages = Column(Integer, nullable=True, default=0, server_default="0")
    processed_messages = Column(Integer, nullable=True, default=0, server_default="0")
    parsed_receipts = Column(Integer, nullable=True, default=0, server_default="0")
    failed_messages = Column(Integer, nullable=True, default=0, server_default="0")
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sync_from_date = Column(Date, nullable=True)
    sync_to_date = Column(Date, nullable=True)
    stats = Column(JSONB, nullable=True, server_default="{}")

    __table_args__ = (
        Index("idx_gmail_sync_jobs_connection", "connection_id"),
        Index(
            "idx_gmail_sync_jobs_status",
            "status",
            postgresql_where=Column("status").in_(["queued", "running"]),
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'failed', 'cancelled')",
            name="gmail_sync_jobs_status_check",
        ),
        CheckConstraint(
            "job_type IN ('full', 'incremental')",
            name="gmail_sync_jobs_job_type_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailSyncJob(id={self.id}, connection_id={self.connection_id}, status={self.status})>"


class GmailParseStatistic(Base):
    """Parse statistics for tracking Gmail parsing performance."""

    __tablename__ = "gmail_parse_statistics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(
        Integer,
        ForeignKey("gmail_connections.id", ondelete="CASCADE"),
        nullable=False,
    )
    sync_job_id = Column(
        Integer,
        ForeignKey("gmail_sync_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id = Column(String(255), nullable=False)
    sender_domain = Column(String(255), nullable=False)
    merchant_normalized = Column(String(255), nullable=True)
    parse_method = Column(String(30), nullable=True)
    merchant_extracted = Column(Boolean, nullable=True)
    brand_extracted = Column(Boolean, nullable=True)
    amount_extracted = Column(Boolean, nullable=True)
    date_extracted = Column(Boolean, nullable=True)
    order_id_extracted = Column(Boolean, nullable=True)
    line_items_extracted = Column(Boolean, nullable=True)
    match_attempted = Column(Boolean, nullable=True, default=False)
    match_success = Column(Boolean, nullable=True)
    match_confidence = Column(Integer, nullable=True)
    parse_duration_ms = Column(Integer, nullable=True)
    llm_cost_cents = Column(Integer, nullable=True)
    parsing_status = Column(String(20), nullable=False)
    parsing_error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_parse_stats_job", "sync_job_id"),
        Index("idx_parse_stats_merchant", "merchant_normalized"),
        Index("idx_parse_stats_merchant_method", "merchant_normalized", "parse_method"),
        Index("idx_parse_stats_method", "parse_method"),
        Index("idx_parse_stats_sender", "sender_domain"),
        CheckConstraint(
            "parse_method IN ('vendor_amazon', 'vendor_uber', 'vendor_apple', "
            "'vendor_paypal', 'vendor_deliveroo', 'vendor_google', 'schema_org', "
            "'pattern', 'llm', 'pdf_fallback', 'pre_filter', 'unknown') OR parse_method IS NULL",
            name="gmail_parse_statistics_parse_method_check",
        ),
        CheckConstraint(
            "parsing_status IN ('parsed', 'unparseable', 'filtered', 'failed')",
            name="gmail_parse_statistics_parsing_status_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailParseStatistic(id={self.id}, merchant={self.merchant_normalized}, method={self.parse_method})>"


class GmailSenderPattern(Base):
    """Sender patterns for merchant identification."""

    __tablename__ = "gmail_sender_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_domain = Column(String(255), nullable=False)
    sender_pattern = Column(String(255), nullable=True)
    merchant_name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)
    parse_type = Column(String(20), nullable=False)
    pattern_config = Column(JSONB, nullable=True)
    date_tolerance_days = Column(Integer, nullable=True, default=7, server_default="7")
    is_active = Column(Boolean, nullable=True, default=True, server_default="true")
    usage_count = Column(Integer, nullable=True, default=0, server_default="0")
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_gmail_sender_patterns_domain", "sender_domain"),
        Index(
            "idx_gmail_sender_patterns_active",
            "is_active",
            postgresql_where=Column("is_active").is_(True),
        ),
        CheckConstraint(
            "parse_type IN ('schema_org', 'pattern', 'llm')",
            name="gmail_sender_patterns_parse_type_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailSenderPattern(id={self.id}, domain={self.sender_domain}, merchant={self.merchant_name})>"


class GmailMatch(Base):
    """Gmail receipt to TrueLayer transaction matches."""

    __tablename__ = "gmail_transaction_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truelayer_transaction_id = Column(
        Integer,
        ForeignKey("truelayer_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    gmail_receipt_id = Column(
        Integer,
        ForeignKey("gmail_receipts.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_confidence = Column(Integer, nullable=False)
    match_type = Column(
        String(20),
        nullable=True,
        default="standard",
        server_default="'standard'",
    )
    match_method = Column(String(100), nullable=True)
    currency_converted = Column(
        Boolean, nullable=True, default=False, server_default="false"
    )
    conversion_rate = Column(Numeric(10, 6), nullable=True)
    user_confirmed = Column(
        Boolean, nullable=True, default=False, server_default="false"
    )
    matched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "truelayer_transaction_id",
            "gmail_receipt_id",
            name="gmail_match_unique",
        ),
        Index("idx_gmail_matches_transaction", "truelayer_transaction_id"),
        Index("idx_gmail_matches_receipt", "gmail_receipt_id"),
        Index(
            "idx_gmail_matches_unconfirmed",
            "match_confidence",
            postgresql_where=(
                (Column("match_confidence") < 80)
                & (Column("user_confirmed").is_(False))
            ),
        ),
        CheckConstraint(
            "match_confidence >= 0 AND match_confidence <= 100",
            name="gmail_transaction_matches_match_confidence_check",
        ),
        CheckConstraint(
            "match_type IN ('standard', 'split_payment', 'bundled_order')",
            name="gmail_transaction_matches_match_type_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailMatch(id={self.id}, txn_id={self.truelayer_transaction_id}, receipt_id={self.gmail_receipt_id}, confidence={self.match_confidence})>"


# MatchingJob is imported from .category


# ============================================================================
# DEPRECATED TABLES - Kept for Alembic sync only
# These tables exist in DB but are no longer actively used
# ============================================================================


class GmailMerchantAlias(Base):
    """
    DEPRECATED: Merchant name aliases for matching.

    Maps bank statement names to receipt merchant names.
    Kept only for Alembic migration sync.
    """

    __tablename__ = "gmail_merchant_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bank_name = Column(String(255), nullable=False)
    receipt_name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=True, default=True, server_default="true")
    usage_count = Column(Integer, nullable=True, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<GmailMerchantAlias(id={self.id}, bank={self.bank_name}, receipt={self.receipt_name})>"


class GmailMerchantStatistic(Base):
    """
    DEPRECATED: Aggregated statistics for merchant parsing.

    Tracks parsing success rates by merchant and parse method.
    Kept only for Alembic migration sync.
    """

    __tablename__ = "gmail_merchant_statistics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(
        Integer,
        ForeignKey("gmail_connections.id", ondelete="CASCADE"),
        nullable=True,
    )
    sender_domain = Column(String(255), nullable=False)
    merchant_normalized = Column(String(255), nullable=True)
    parse_method = Column(String(30), nullable=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    total_attempts = Column(Integer, nullable=False, default=0, server_default="0")
    parsed_count = Column(Integer, nullable=False, default=0, server_default="0")
    failed_count = Column(Integer, nullable=False, default=0, server_default="0")
    merchant_extracted_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    brand_extracted_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    amount_extracted_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    date_extracted_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    order_id_extracted_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    line_items_extracted_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    match_attempted_count = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    match_success_count = Column(Integer, nullable=False, default=0, server_default="0")
    avg_match_confidence = Column(Numeric(5, 2), nullable=True)
    avg_parse_duration_ms = Column(Integer, nullable=True)
    total_llm_cost_cents = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "sender_domain",
            "merchant_normalized",
            "parse_method",
            "period_start",
            name="unique_merchant_stats",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailMerchantStatistic(id={self.id}, domain={self.sender_domain}, method={self.parse_method})>"


class GmailProcessingError(Base):
    """
    DEPRECATED: Error tracking for Gmail processing.

    Records errors during Gmail sync and parsing.
    Kept only for Alembic migration sync.
    """

    __tablename__ = "gmail_processing_errors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(
        Integer,
        ForeignKey("gmail_connections.id", ondelete="CASCADE"),
        nullable=True,
    )
    sync_job_id = Column(
        Integer,
        ForeignKey("gmail_sync_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    message_id = Column(String(255), nullable=True)
    receipt_id = Column(
        Integer,
        ForeignKey("gmail_receipts.id", ondelete="CASCADE"),
        nullable=True,
    )
    error_stage = Column(String(30), nullable=False)
    error_type = Column(String(30), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    error_context = Column(JSONB, nullable=True)
    is_retryable = Column(Boolean, nullable=True, default=False, server_default="false")
    retry_count = Column(Integer, nullable=True, default=0, server_default="0")
    last_retry_at = Column(DateTime(timezone=True), nullable=True)
    occurred_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "error_stage IN ('fetch', 'parse', 'vendor_parse', 'schema_parse', "
            "'pattern_parse', 'llm_parse', 'pdf_parse', 'storage', 'match', 'validation')",
            name="gmail_processing_errors_error_stage_check",
        ),
        CheckConstraint(
            "error_type IN ('api_error', 'timeout', 'parse_error', 'validation', "
            "'db_error', 'network', 'rate_limit', 'auth_error', 'unknown')",
            name="gmail_processing_errors_error_type_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<GmailProcessingError(id={self.id}, stage={self.error_stage}, type={self.error_type})>"
