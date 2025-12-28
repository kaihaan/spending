# backend/database/models/category.py
"""
Category models for transaction classification.

Maps to:
- categories table
- category_keywords table
- category_rules table - Pattern-based categorization rules
- merchant_normalizations table - Merchant name standardization
- matching_jobs table - Async matching job tracking

See: .claude/docs/database/DATABASE_SCHEMA.md#10-categories
"""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from database.base import Base


class Category(Base):
    """Transaction category for classification."""

    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    rule_pattern = Column(Text, nullable=True)
    ai_suggested = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name={self.name})>"


class CategoryKeyword(Base):
    """Keywords for category matching."""

    __tablename__ = "category_keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String, nullable=False)
    keyword = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CategoryKeyword(id={self.id}, category={self.category_name}, keyword={self.keyword})>"


class CategoryRule(Base):
    """
    Pattern-based rules for automatically categorizing transactions.

    Used by consistency engine to categorize transactions based on description patterns.
    Especially useful for inbound/CREDIT transactions.
    """

    __tablename__ = "category_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    rule_name = Column(String(100), nullable=False)
    transaction_type = Column(String(10), nullable=True)  # 'CREDIT', 'DEBIT', or NULL
    description_pattern = Column(String(255), nullable=False)
    pattern_type = Column(
        String(20), nullable=False, default="contains", server_default="contains"
    )
    category = Column(String(100), nullable=False)
    subcategory = Column(String(100), nullable=True)
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    source = Column(
        String(50), nullable=False, default="manual", server_default="manual"
    )
    usage_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CategoryRule(id={self.id}, name={self.rule_name}, pattern={self.description_pattern})>"


class MerchantNormalization(Base):
    """
    Merchant name normalization patterns.

    Maps messy merchant names (e.g., 'GAILS') to clean names (e.g., "Gail's Bakery").
    """

    __tablename__ = "merchant_normalizations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern = Column(String(255), nullable=False)
    pattern_type = Column(
        String(20), nullable=False, default="contains", server_default="contains"
    )
    normalized_name = Column(String(255), nullable=False)
    merchant_type = Column(String(100), nullable=True)
    default_category = Column(String(100), nullable=True)
    priority = Column(Integer, nullable=False, default=0, server_default="0")
    source = Column(
        String(50), nullable=False, default="manual", server_default="manual"
    )
    usage_count = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=False), server_default=func.now())
    updated_at = Column(DateTime(timezone=False), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "pattern",
            "pattern_type",
            name="merchant_normalizations_pattern_pattern_type_key",
        ),
    )

    def __repr__(self) -> str:
        return f"<MerchantNormalization(id={self.id}, pattern={self.pattern}, normalized={self.normalized_name})>"


class MatchingJob(Base):
    """
    Async job tracking for transaction matching operations.

    Tracks progress and status of background matching tasks (Amazon, Apple, Gmail).
    """

    __tablename__ = "matching_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    job_type = Column(String(50), nullable=False)  # 'amazon', 'apple', 'gmail', etc.
    celery_task_id = Column(String(255), nullable=True)
    status = Column(
        String(20), nullable=False, default="queued", server_default="queued"
    )
    total_items = Column(Integer, nullable=True)
    processed_items = Column(Integer, nullable=True)
    matched_items = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=False), server_default=func.now())
    started_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<MatchingJob(id={self.id}, type={self.job_type}, status={self.status})>"
        )
