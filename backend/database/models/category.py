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
    ForeignKey,
    Index,
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
    user_id = Column(Integer, nullable=False, default=1, server_default="1")
    job_type = Column(String(50), nullable=False)
    celery_task_id = Column(String(255), nullable=True)
    status = Column(
        String(20),
        nullable=True,
        default="queued",
        server_default="'queued'",
    )
    total_items = Column(Integer, nullable=True, default=0, server_default="0")
    processed_items = Column(Integer, nullable=True, default=0, server_default="0")
    matched_items = Column(Integer, nullable=True, default=0, server_default="0")
    failed_items = Column(Integer, nullable=True, default=0, server_default="0")
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)
    created_at = Column(
        DateTime(timezone=False),
        server_default=func.current_timestamp(),
    )

    __table_args__ = (
        Index("idx_matching_jobs_user_status", "user_id", "status"),
        Index("idx_matching_jobs_celery_task", "celery_task_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<MatchingJob(id={self.id}, type={self.job_type}, status={self.status})>"
        )


class CustomCategory(Base):
    """
    User-created custom categories (promoted or hidden).

    Promoted categories appear as top-level groupings in the UI.
    Hidden categories are filtered out from displays.
    """

    __tablename__ = "custom_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, default=1, server_default="1")
    name = Column(String(100), nullable=False)
    category_type = Column(String(20), nullable=False)  # 'promoted' or 'hidden'
    display_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "name"),)

    def __repr__(self) -> str:
        return f"<CustomCategory(id={self.id}, name={self.name}, type={self.category_type})>"


class SubcategoryMapping(Base):
    """
    Maps subcategories to promoted custom categories.

    Links subcategories from original categorization to user-defined promoted categories.
    """

    __tablename__ = "subcategory_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    custom_category_id = Column(
        Integer,
        ForeignKey("custom_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    subcategory_name = Column(String(255), nullable=False)
    original_category = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("custom_category_id", "subcategory_name"),)

    def __repr__(self) -> str:
        return (
            f"<SubcategoryMapping(id={self.id}, subcategory={self.subcategory_name})>"
        )


class NormalizedCategory(Base):
    """
    Normalized canonical categories with metadata.

    System categories cannot be deleted. Active categories appear in LLM prompts.
    Essential categories are used for Huququllah calculations.
    """

    __tablename__ = "normalized_categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_essential = Column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    display_order = Column(Integer, nullable=False, default=0, server_default="0")
    color = Column(String(30), nullable=True)  # Badge color class
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<NormalizedCategory(id={self.id}, name={self.name})>"


class NormalizedSubcategory(Base):
    """
    Normalized subcategories linked to parent categories via FK.

    Each subcategory belongs to exactly one parent category.
    """

    __tablename__ = "normalized_subcategories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(
        Integer,
        ForeignKey("normalized_categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    display_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("category_id", "name"),)

    def __repr__(self) -> str:
        return f"<NormalizedSubcategory(id={self.id}, name={self.name})>"
