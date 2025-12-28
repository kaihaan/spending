"""
TrueLayer integration models for bank connections and transactions.

Maps to:
- bank_connections table
- truelayer_accounts table
- truelayer_transactions table
- truelayer_balances table
- webhook_events table
- oauth_state table
- truelayer_cards table
- truelayer_card_transactions table
- truelayer_card_balance_snapshots table
- truelayer_import_jobs table
- truelayer_import_progress table
- truelayer_enrichment_jobs table

See: .claude/docs/database/DATABASE_SCHEMA.md#5-bank_connections
"""

from sqlalchemy import (
    ARRAY,
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.base import Base


class BankConnection(Base):
    """OAuth connections to TrueLayer API."""

    __tablename__ = "bank_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider_id = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    access_token = Column(Text, nullable=True)  # ENCRYPTED
    refresh_token = Column(Text, nullable=True)  # ENCRYPTED
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    connection_status = Column(
        String(30), nullable=True, default="active", server_default="active"
    )
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    accounts = relationship(
        "TrueLayerAccount", back_populates="connection", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (Index("idx_bank_connections_user_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<BankConnection(id={self.id}, provider={self.provider_id}, status={self.connection_status})>"


class TrueLayerAccount(Base):
    """Bank accounts discovered from TrueLayer API."""

    __tablename__ = "truelayer_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(Integer, ForeignKey("bank_connections.id"), nullable=False)
    account_id = Column(String, nullable=False)  # TrueLayer account ID
    account_type = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    account_number_json = Column(JSONB, nullable=True)
    provider_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    connection = relationship("BankConnection", back_populates="accounts")
    transactions = relationship(
        "TrueLayerTransaction", back_populates="account", cascade="all, delete-orphan"
    )
    balances = relationship(
        "TrueLayerBalance", back_populates="account", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TrueLayerAccount(id={self.id}, name={self.display_name})>"


class TrueLayerTransaction(Base):
    """Bank transactions synced from TrueLayer API."""

    __tablename__ = "truelayer_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("truelayer_accounts.id"), nullable=False)
    transaction_id = Column(String, nullable=False)
    normalised_provider_transaction_id = Column(String, nullable=False, unique=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Numeric, nullable=False)
    currency = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)
    transaction_category = Column(String, nullable=True)
    merchant_name = Column(String, nullable=True)
    running_balance = Column(Numeric, nullable=True)
    pre_enrichment_status = Column(
        String(20), nullable=True, default="None", server_default="None"
    )
    metadata_ = Column(
        "metadata", JSONB, nullable=True
    )  # Use metadata_ in Python, metadata in DB
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account = relationship("TrueLayerAccount", back_populates="transactions")

    # Indexes
    __table_args__ = (
        Index("idx_truelayer_txn_account", "account_id"),
        Index("idx_truelayer_txn_timestamp", "timestamp"),
        Index(
            "idx_truelayer_txn_normalised_id",
            "normalised_provider_transaction_id",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<TrueLayerTransaction(id={self.id}, amount={self.amount}, desc={self.description[:30]})>"


class TrueLayerBalance(Base):
    """Historical snapshots of account balances."""

    __tablename__ = "truelayer_balances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("truelayer_accounts.id"), nullable=False)
    current_balance = Column(Numeric, nullable=False)
    available_balance = Column(Numeric, nullable=True)
    overdraft = Column(Numeric, nullable=True)
    currency = Column(String, nullable=False)
    snapshot_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account = relationship("TrueLayerAccount", back_populates="balances")

    # Indexes
    __table_args__ = (Index("idx_truelayer_balances_account_id", "account_id"),)

    def __repr__(self) -> str:
        return f"<TrueLayerBalance(account_id={self.account_id}, balance={self.current_balance})>"


class WebhookEvent(Base):
    """Incoming webhook events from TrueLayer."""

    __tablename__ = "webhook_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(255), unique=True, nullable=False)
    event_type = Column(String(100), nullable=False)
    payload = Column(JSONB, nullable=False)
    signature = Column(Text, nullable=False)
    processed = Column(Boolean, default=False, server_default="false")
    processed_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), server_default=func.now())

    # Indexes
    __table_args__ = (
        Index("idx_webhook_events_event_id", "event_id", unique=True),
        Index(
            "idx_webhook_events_unprocessed",
            "received_at",
            postgresql_where=(~processed),
        ),
    )

    def __repr__(self) -> str:
        return f"<WebhookEvent(id={self.id}, type={self.event_type}, processed={self.processed})>"


class OAuthState(Base):
    """OAuth state parameters for CSRF protection."""

    __tablename__ = "oauth_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    state = Column(String(255), unique=True, nullable=False)
    code_verifier = Column(Text, nullable=False)
    expires_at = Column(
        DateTime(timezone=False), nullable=False
    )  # Note: WITHOUT timezone in schema
    created_at = Column(
        DateTime(timezone=False), server_default=func.current_timestamp()
    )

    # Indexes
    __table_args__ = (Index("idx_oauth_state_state", "state", unique=True),)

    def __repr__(self) -> str:
        return f"<OAuthState(user_id={self.user_id}, state={self.state[:10]}...)>"


class TrueLayerCard(Base):
    """Credit/debit cards from TrueLayer API."""

    __tablename__ = "truelayer_cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(
        Integer, ForeignKey("bank_connections.id", ondelete="CASCADE"), nullable=False
    )
    card_id = Column(String(255), nullable=False)
    card_name = Column(String(255), nullable=True)
    card_type = Column(String(50), nullable=True)
    last_four = Column(String(4), nullable=True)
    issuer = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True)
    last_synced_at = Column(
        DateTime(timezone=False), nullable=True
    )  # Note: WITHOUT timezone in schema
    created_at = Column(
        DateTime(timezone=False), server_default=func.current_timestamp()
    )
    updated_at = Column(
        DateTime(timezone=False),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    connection = relationship("BankConnection")
    transactions = relationship(
        "TrueLayerCardTransaction", back_populates="card", cascade="all, delete-orphan"
    )
    balance_snapshots = relationship(
        "TrueLayerCardBalanceSnapshot",
        back_populates="card",
        cascade="all, delete-orphan",
    )

    # Indexes
    __table_args__ = (
        Index("idx_truelayer_cards_connection", "connection_id"),
        Index(None, "connection_id", "card_id", unique=True),  # UNIQUE constraint
    )

    def __repr__(self) -> str:
        return f"<TrueLayerCard(id={self.id}, name={self.card_name}, last_four={self.last_four})>"


class TrueLayerCardTransaction(Base):
    """Card transactions from TrueLayer API."""

    __tablename__ = "truelayer_card_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_id = Column(
        Integer, ForeignKey("truelayer_cards.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id = Column(String(255), nullable=True)
    normalised_provider_id = Column(String(255), nullable=True)
    timestamp = Column(
        DateTime(timezone=False), nullable=True
    )  # Note: WITHOUT timezone in schema
    description = Column(Text, nullable=True)
    amount = Column(Numeric, nullable=True)
    currency = Column(String(3), nullable=True)
    transaction_type = Column(String(50), nullable=True)
    category = Column(String(255), nullable=True)
    merchant_name = Column(String(255), nullable=True)
    running_balance = Column(Numeric, nullable=True)
    metadata = Column(Text, nullable=True)  # Note: TEXT not JSONB in schema
    created_at = Column(
        DateTime(timezone=False), server_default=func.current_timestamp()
    )

    # Relationships
    card = relationship("TrueLayerCard", back_populates="transactions")

    # Indexes
    __table_args__ = (Index("idx_truelayer_card_transactions_card", "card_id"),)

    def __repr__(self) -> str:
        return f"<TrueLayerCardTransaction(id={self.id}, amount={self.amount}, desc={self.description[:30] if self.description else ''})>"


class TrueLayerCardBalanceSnapshot(Base):
    """Historical balance snapshots for cards."""

    __tablename__ = "truelayer_card_balance_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    card_id = Column(
        Integer, ForeignKey("truelayer_cards.id", ondelete="CASCADE"), nullable=False
    )
    current_balance = Column(Numeric, nullable=True)
    currency = Column(String(3), nullable=True)
    snapshot_at = Column(
        DateTime(timezone=False), nullable=True
    )  # Note: WITHOUT timezone in schema
    created_at = Column(
        DateTime(timezone=False), server_default=func.current_timestamp()
    )

    # Relationships
    card = relationship("TrueLayerCard", back_populates="balance_snapshots")

    # Indexes
    __table_args__ = (Index("idx_truelayer_card_balance_snapshots_card", "card_id"),)

    def __repr__(self) -> str:
        return f"<TrueLayerCardBalanceSnapshot(card_id={self.card_id}, balance={self.current_balance})>"


class TrueLayerImportJob(Base):
    """Job tracking for TrueLayer transaction imports."""

    __tablename__ = "truelayer_import_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    connection_id = Column(
        Integer, ForeignKey("bank_connections.id", ondelete="SET NULL"), nullable=True
    )
    job_status = Column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    job_type = Column(
        String(20), nullable=False, default="date_range", server_default="date_range"
    )
    from_date = Column(Date, nullable=True)
    to_date = Column(Date, nullable=True)
    account_ids = Column(ARRAY(Text), nullable=True, server_default="{}")
    card_ids = Column(ARRAY(Text), nullable=True, server_default="{}")
    total_accounts = Column(Integer, nullable=True, default=0, server_default="0")
    total_transactions_synced = Column(
        Integer, nullable=True, default=0, server_default="0"
    )
    total_transactions_duplicates = Column(
        Integer, nullable=True, default=0, server_default="0"
    )
    total_transactions_errors = Column(
        Integer, nullable=True, default=0, server_default="0"
    )
    auto_enrich = Column(Boolean, nullable=True, default=True, server_default="true")
    enrich_after_completion = Column(
        Boolean, nullable=True, default=False, server_default="false"
    )
    enrichment_job_id = Column(
        Integer,
        ForeignKey("truelayer_enrichment_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    batch_size = Column(Integer, nullable=True, default=50, server_default="50")
    created_at = Column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    estimated_completion = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True, server_default="{}")
    error_message = Column(Text, nullable=True)

    # Relationships
    progress_items = relationship(
        "TrueLayerImportProgress", back_populates="job", cascade="all, delete-orphan"
    )

    # Indexes & Constraints
    __table_args__ = (
        Index("idx_import_jobs_user_id", "user_id"),
        Index("idx_import_jobs_connection_id", "connection_id"),
        Index("idx_import_jobs_status", "job_status"),
        Index(
            "idx_import_jobs_created_at",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
        CheckConstraint(
            "job_status IN ('pending', 'running', 'completed', 'failed', 'enriching')",
            name="valid_job_status",
        ),
        CheckConstraint(
            "job_type IN ('date_range', 'incremental', 'full_sync')",
            name="valid_job_type",
        ),
        CheckConstraint(
            "from_date IS NULL OR to_date IS NULL OR from_date <= to_date",
            name="valid_dates",
        ),
    )

    def __repr__(self) -> str:
        return f"<TrueLayerImportJob(id={self.id}, status={self.job_status}, type={self.job_type})>"


class TrueLayerImportProgress(Base):
    """Per-account progress tracking for import jobs."""

    __tablename__ = "truelayer_import_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        Integer,
        ForeignKey("truelayer_import_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id = Column(
        Integer, ForeignKey("truelayer_accounts.id", ondelete="SET NULL"), nullable=True
    )
    progress_status = Column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    synced_count = Column(Integer, nullable=True, default=0, server_default="0")
    duplicates_count = Column(Integer, nullable=True, default=0, server_default="0")
    errors_count = Column(Integer, nullable=True, default=0, server_default="0")
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True, server_default="{}")
    created_at = Column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # Relationships
    job = relationship("TrueLayerImportJob", back_populates="progress_items")

    # Indexes & Constraints
    __table_args__ = (
        Index("idx_import_progress_job_id", "job_id"),
        Index("idx_import_progress_account_id", "account_id"),
        Index("idx_import_progress_status", "progress_status"),
        CheckConstraint(
            "progress_status IN ('pending', 'syncing', 'completed', 'failed')",
            name="valid_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<TrueLayerImportProgress(job_id={self.job_id}, account_id={self.account_id}, status={self.progress_status})>"


class TrueLayerEnrichmentJob(Base):
    """Job tracking for transaction enrichment."""

    __tablename__ = "truelayer_enrichment_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    import_job_id = Column(
        Integer,
        ForeignKey("truelayer_import_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    job_status = Column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    transaction_ids = Column(ARRAY(Integer), nullable=True, server_default="{}")
    total_transactions = Column(Integer, nullable=True, default=0, server_default="0")
    successful_enrichments = Column(
        Integer, nullable=True, default=0, server_default="0"
    )
    failed_enrichments = Column(Integer, nullable=True, default=0, server_default="0")
    cached_hits = Column(Integer, nullable=True, default=0, server_default="0")
    total_cost = Column(
        Numeric(10, 4), nullable=True, default=0.00, server_default="0.00"
    )
    total_tokens = Column(Integer, nullable=True, default=0, server_default="0")
    llm_provider = Column(String(50), nullable=True)
    llm_model = Column(String(100), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.current_timestamp()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    metadata_ = Column("metadata", JSONB, nullable=True, server_default="{}")
    error_message = Column(Text, nullable=True)

    # Indexes & Constraints
    __table_args__ = (
        Index("idx_enrichment_jobs_user_id", "user_id"),
        Index("idx_enrichment_jobs_import_job_id", "import_job_id"),
        Index("idx_enrichment_jobs_status", "job_status"),
        Index(
            "idx_enrichment_jobs_created_at",
            "created_at",
            postgresql_ops={"created_at": "DESC"},
        ),
        CheckConstraint(
            "job_status IN ('pending', 'running', 'completed', 'failed')",
            name="valid_enrichment_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<TrueLayerEnrichmentJob(id={self.id}, status={self.job_status}, total={self.total_transactions})>"
