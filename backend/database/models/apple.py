"""
Apple integration models for App Store and iTunes purchases.

Maps to:
- apple_transactions table
- truelayer_apple_transaction_matches table

See: .claude/docs/database/DATABASE_SCHEMA.md#15-apple_transactions
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
)
from sqlalchemy.sql import func

from database.base import Base


class AppleTransaction(Base):
    """Apple purchases imported from statement."""

    __tablename__ = "apple_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100), nullable=False, unique=True)
    order_date = Column(Date, nullable=False)
    total_amount = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(3), nullable=False)
    app_names = Column(Text, nullable=False)
    publishers = Column(Text, nullable=True)
    item_count = Column(Integer, nullable=True, default=1)
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("idx_apple_transactions_date", "order_date"),)

    def __repr__(self) -> str:
        return f"<AppleTransaction(id={self.id}, order_id={self.order_id}, total={self.total_amount})>"


class TrueLayerAppleTransactionMatch(Base):
    """Linking TrueLayer transactions to Apple purchases."""

    __tablename__ = "truelayer_apple_transaction_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truelayer_transaction_id = Column(
        Integer,
        ForeignKey("truelayer_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    apple_transaction_id = Column(
        Integer,
        ForeignKey("apple_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_confidence = Column(Integer, nullable=False)
    matched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_truelayer_apple_matches_transaction", "truelayer_transaction_id"),
        Index("idx_truelayer_apple_matches_apple", "apple_transaction_id"),
        CheckConstraint(
            "match_confidence >= 0 AND match_confidence <= 100",
            name="truelayer_apple_transaction_matches_match_confidence_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<TrueLayerAppleTransactionMatch(id={self.id}, truelayer_id={self.truelayer_transaction_id}, apple_id={self.apple_transaction_id})>"
