# backend/database/models/category.py
"""
Category models for transaction classification.

Maps to:
- categories table
- category_keywords table

See: .claude/docs/database/DATABASE_SCHEMA.md#10-categories
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
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
