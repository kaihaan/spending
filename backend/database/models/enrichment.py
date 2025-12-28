"""
Enrichment models for LLM transaction categorization and caching.

Maps to:
- transaction_enrichment_sources table - Links transactions to enrichment data sources
- llm_enrichment_cache table - Caches LLM enrichment results for reuse

See: .claude/docs/database/DATABASE_SCHEMA.md
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from database.base import Base


class TransactionEnrichmentSource(Base):
    """
    Records which transactions have been enriched with data from external sources.

    Stores polymorphic references to enrichment sources:
    - Amazon orders (source_type='amazon', source_id=amazon_orders.id)
    - Amazon Business orders (source_type='amazon_business', source_id=amazon_business_orders.id)
    - Apple transactions (source_type='apple', source_id=apple_transactions.id)
    - Gmail receipts (source_type='gmail', source_id=gmail_receipts.id)
    - Manual enrichment (source_type='manual', source_id may be NULL)
    """

    __tablename__ = "transaction_enrichment_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truelayer_transaction_id = Column(
        Integer,
        ForeignKey("truelayer_transactions.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Source identification (polymorphic)
    source_type = Column(String(20), nullable=False)
    source_id = Column(Integer, nullable=True)  # FK to source table

    # Enrichment content
    description = Column(Text, nullable=False)  # Product/service description
    order_id = Column(String(100), nullable=True)  # Original order/receipt ID
    line_items = Column(
        JSONB, nullable=True
    )  # Detailed items [{name, quantity, price}]

    # Match metadata
    match_confidence = Column(
        Integer, nullable=False, default=100, server_default="100"
    )
    match_method = Column(String(50), nullable=True)  # How match was determined

    # User control
    is_primary = Column(
        Boolean, nullable=True, default=False, server_default="false"
    )  # User-selected primary source
    user_verified = Column(
        Boolean, nullable=True, default=False, server_default="false"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        # CHECK constraints
        CheckConstraint(
            "match_confidence >= 0 AND match_confidence <= 100",
            name="transaction_enrichment_sources_match_confidence_check",
        ),
        CheckConstraint(
            "source_type IN ('amazon', 'amazon_business', 'apple', 'gmail', 'manual')",
            name="transaction_enrichment_sources_source_type_check",
        ),
        # UNIQUE constraint: same source can't be added twice
        UniqueConstraint(
            "truelayer_transaction_id",
            "source_type",
            "source_id",
            name="enrichment_source_unique",
        ),
        # Performance indexes
        Index("idx_enrichment_sources_txn", "truelayer_transaction_id"),
        Index("idx_enrichment_sources_type", "source_type"),
        Index(
            "idx_enrichment_sources_primary",
            "truelayer_transaction_id",
            postgresql_where=(is_primary == True),  # noqa: E712
        ),
    )

    def __repr__(self) -> str:
        return f"<TransactionEnrichmentSource(id={self.id}, txn={self.truelayer_transaction_id}, source={self.source_type}:{self.source_id})>"


class EnrichmentCache(Base):
    """
    Caches LLM enrichment results for transaction descriptions.

    Allows reuse of LLM categorization for identical transactions,
    reducing API costs and improving response time.
    """

    __tablename__ = "llm_enrichment_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    transaction_description = Column(Text, nullable=False)
    transaction_direction = Column(
        String(10), nullable=True
    )  # 'DEBIT' or 'CREDIT' or NULL
    enrichment_data = Column(Text, nullable=True)  # JSON string (stored as TEXT)
    cached_at = Column(
        DateTime(timezone=False), server_default=func.current_timestamp()
    )

    __table_args__ = (
        # UNIQUE constraint: cache key is (description, direction)
        UniqueConstraint(
            "transaction_description",
            "transaction_direction",
            name="llm_enrichment_cache_transaction_description_transaction_di_key",
        ),
        # Performance index
        Index("idx_cache_description", "transaction_description"),
    )

    def __repr__(self) -> str:
        return f"<EnrichmentCache(id={self.id}, description={self.transaction_description[:30]}...)>"
