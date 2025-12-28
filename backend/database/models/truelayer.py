"""
TrueLayer integration models for bank connections and transactions.

Maps to:
- bank_connections table
- truelayer_accounts table
- truelayer_transactions table
- truelayer_balances table

See: .claude/docs/database/DATABASE_SCHEMA.md#5-bank_connections
"""

from sqlalchemy import (
    Column,
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
