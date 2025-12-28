"""
Amazon integration models for orders, returns, and business integration.

Maps to:
- amazon_orders table
- amazon_returns table
- amazon_business_connections table
- amazon_business_orders table
- amazon_business_line_items table
- truelayer_amazon_transaction_matches table

See: .claude/docs/database/DATABASE_SCHEMA.md#12-amazon_orders
"""

from sqlalchemy import (
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


class AmazonOrder(Base):
    """Amazon orders imported from statement."""

    __tablename__ = "amazon_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), nullable=False, unique=True)
    order_date = Column(Date, nullable=False)
    website = Column(String(50), nullable=False)
    currency = Column(String(10), nullable=False)
    total_owed = Column(Numeric, nullable=False)
    product_names = Column(Text, nullable=False)
    order_status = Column(String(50), nullable=True)
    shipment_status = Column(String(50), nullable=True)
    source_file = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<AmazonOrder(id={self.id}, order_id={self.order_id}, total={self.total_owed})>"


class AmazonReturn(Base):
    """Amazon returns/refunds."""

    __tablename__ = "amazon_returns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), nullable=False)
    reversal_id = Column(String(50), nullable=False)
    refund_completion_date = Column(Date, nullable=False)
    currency = Column(String(10), nullable=False)
    amount_refunded = Column(Numeric, nullable=False)
    status = Column(String(50), nullable=True)
    disbursement_type = Column(String(50), nullable=True)
    source_file = Column(String(255), nullable=True)
    # Legacy columns - no foreign key since transactions table not in SQLAlchemy
    original_transaction_id = Column(Integer, nullable=True)
    refund_transaction_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_amazon_returns_original_txn", "original_transaction_id"),
        Index("idx_amazon_returns_refund_txn", "refund_transaction_id"),
    )

    def __repr__(self) -> str:
        return f"<AmazonReturn(id={self.id}, order_id={self.order_id}, amount={self.amount_refunded})>"


class AmazonBusinessConnection(Base):
    """OAuth connections for Amazon Business API."""

    __tablename__ = "amazon_business_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=True, default=1)
    access_token = Column(Text, nullable=False)  # Encrypted
    refresh_token = Column(Text, nullable=False)  # Encrypted
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    region = Column(String(10), nullable=True, default="UK")
    status = Column(
        String(20), nullable=True, default="active", server_default="active"
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AmazonBusinessConnection(id={self.id}, region={self.region}, status={self.status})>"


class AmazonBusinessOrder(Base):
    """Amazon Business orders imported from API."""

    __tablename__ = "amazon_business_orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(50), nullable=False, unique=True)
    order_date = Column(Date, nullable=False)
    region = Column(String(10), nullable=True)
    purchase_order_number = Column(String(100), nullable=True)
    order_status = Column(String(50), nullable=True)
    buyer_name = Column(String(255), nullable=True)
    buyer_email = Column(String(255), nullable=True)
    subtotal = Column(Numeric(12, 2), nullable=True)
    tax = Column(Numeric(12, 2), nullable=True)
    shipping = Column(Numeric(12, 2), nullable=True)
    net_total = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(10), nullable=True, default="GBP")
    item_count = Column(Integer, nullable=True, default=1)
    product_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_amazon_business_orders_date", "order_date"),
        Index("idx_amazon_business_orders_net_total", "net_total"),
    )

    def __repr__(self) -> str:
        return f"<AmazonBusinessOrder(id={self.id}, order_id={self.order_id}, total={self.net_total})>"


class AmazonBusinessLineItem(Base):
    """Line item details for Amazon Business orders."""

    __tablename__ = "amazon_business_line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(
        String(50), ForeignKey("amazon_business_orders.order_id"), nullable=False
    )
    line_item_id = Column(String(50), nullable=True)
    asin = Column(String(20), nullable=True)
    title = Column(Text, nullable=True)
    brand = Column(String(255), nullable=True)
    category = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=True)
    total_price = Column(Numeric(12, 2), nullable=True)
    seller_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_amazon_business_line_items_order_id", "order_id"),
        Index("idx_amazon_business_line_items_asin", "asin"),
    )

    def __repr__(self) -> str:
        return f"<AmazonBusinessLineItem(id={self.id}, order_id={self.order_id}, title={self.title})>"


class TrueLayerAmazonTransactionMatch(Base):
    """Linking TrueLayer transactions to Amazon orders."""

    __tablename__ = "truelayer_amazon_transaction_matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truelayer_transaction_id = Column(
        Integer, ForeignKey("truelayer_transactions.id"), nullable=False, unique=True
    )
    amazon_order_id = Column(Integer, ForeignKey("amazon_orders.id"), nullable=False)
    match_confidence = Column(Numeric(5, 2), nullable=False)
    matched_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_truelayer_amazon_matches_truelayer_txn", "truelayer_transaction_id"),
        Index("idx_truelayer_amazon_matches_amazon_order", "amazon_order_id"),
    )

    def __repr__(self) -> str:
        return f"<TrueLayerAmazonTransactionMatch(id={self.id}, truelayer_id={self.truelayer_transaction_id}, amazon_id={self.amazon_order_id})>"
