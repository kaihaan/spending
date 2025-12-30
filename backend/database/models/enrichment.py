"""
Enrichment models for LLM transaction categorization and caching.

Maps to:
- transaction_enrichment_sources table - Links transactions to enrichment data sources
- rule_enrichment_results table - Rule-based enrichment (category rules, merchant norms)
- llm_enrichment_results table - LLM-based enrichment results per transaction
- llm_enrichment_cache table - Caches LLM enrichment results for reuse
- llm_models table (DEPRECATED) - Configuration for LLM providers

See: .claude/docs/database/DATABASE_SCHEMA.md
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


# ============================================================================
# DEDICATED ENRICHMENT RESULT TABLES
# Store enrichment from each source independently (no overwrites)
# ============================================================================


class RuleEnrichmentResult(Base):
    """
    Stores enrichment results from consistency rules.

    Each transaction can have at most one rule-based enrichment.
    Sources include:
    - category_rule: CategoryRule pattern matches
    - merchant_rule: MerchantNormalization pattern matches
    - direct_debit: Direct debit mapping rules
    """

    __tablename__ = "rule_enrichment_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truelayer_transaction_id = Column(
        Integer,
        ForeignKey("truelayer_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Categorization result
    primary_category = Column(String(100), nullable=False)
    subcategory = Column(String(100), nullable=True)
    essential_discretionary = Column(String(20), nullable=True)

    # Merchant info
    merchant_clean_name = Column(String(255), nullable=True)
    merchant_type = Column(String(100), nullable=True)

    # Rule match metadata
    rule_type = Column(String(30), nullable=False)
    matched_rule_id = Column(Integer, nullable=True)
    matched_rule_name = Column(String(100), nullable=True)
    matched_merchant_id = Column(Integer, nullable=True)
    matched_merchant_name = Column(String(255), nullable=True)

    # Confidence (rules are deterministic)
    confidence_score = Column(
        Numeric(3, 2), nullable=False, default=1.00, server_default="1.00"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "rule_type IN ('category_rule', 'merchant_rule', 'direct_debit')",
            name="rule_enrichment_rule_type_check",
        ),
        CheckConstraint(
            "confidence_score >= 0 AND confidence_score <= 1",
            name="rule_enrichment_confidence_check",
        ),
        Index("idx_rule_enrichment_txn", "truelayer_transaction_id"),
        Index("idx_rule_enrichment_category", "primary_category"),
        Index("idx_rule_enrichment_type", "rule_type"),
    )

    def __repr__(self) -> str:
        return f"<RuleEnrichmentResult(id={self.id}, txn={self.truelayer_transaction_id}, category={self.primary_category})>"


class LLMEnrichmentResult(Base):
    """
    Stores enrichment results from LLM inference.

    Each transaction can have at most one LLM-based enrichment.
    Links to EnrichmentCache for deduplication tracking.
    """

    __tablename__ = "llm_enrichment_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    truelayer_transaction_id = Column(
        Integer,
        ForeignKey("truelayer_transactions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Categorization result
    primary_category = Column(String(100), nullable=False)
    subcategory = Column(String(100), nullable=True)
    essential_discretionary = Column(String(20), nullable=True)

    # Merchant info
    merchant_clean_name = Column(String(255), nullable=True)
    merchant_type = Column(String(100), nullable=True)

    # Payment info (LLM can infer these)
    payment_method = Column(String(50), nullable=True)
    payment_method_subtype = Column(String(50), nullable=True)
    purchase_date = Column(Date, nullable=True)

    # LLM metadata
    llm_provider = Column(String(50), nullable=False)
    llm_model = Column(String(100), nullable=False)
    confidence_score = Column(Numeric(3, 2), nullable=True)

    # Cache linkage
    cache_id = Column(
        Integer,
        ForeignKey("llm_enrichment_cache.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Source tracking
    enrichment_source = Column(
        String(20), nullable=False, default="llm", server_default="llm"
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="llm_enrichment_confidence_check",
        ),
        CheckConstraint(
            "enrichment_source IN ('llm', 'cache')",
            name="llm_enrichment_source_check",
        ),
        Index("idx_llm_enrichment_txn", "truelayer_transaction_id"),
        Index("idx_llm_enrichment_category", "primary_category"),
        Index("idx_llm_enrichment_provider", "llm_provider"),
    )

    def __repr__(self) -> str:
        return f"<LLMEnrichmentResult(id={self.id}, txn={self.truelayer_transaction_id}, category={self.primary_category})>"


# ============================================================================
# DEPRECATED TABLES - Kept for Alembic sync only
# These tables exist in DB but are no longer actively used
# ============================================================================


class LLMModel(Base):
    """
    DEPRECATED: LLM model configuration.

    Originally used to track available LLM models.
    Configuration is now done via environment variables.
    Kept only for Alembic migration sync.
    """

    __tablename__ = "llm_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False)
    model_name = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    is_builtin = Column(Boolean, nullable=True, default=True, server_default="true")
    is_active = Column(Boolean, nullable=True, default=False, server_default="false")
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "provider", "model_name", name="llm_models_provider_model_name_key"
        ),
    )

    def __repr__(self) -> str:
        return f"<LLMModel(id={self.id}, provider={self.provider}, model={self.model_name})>"
