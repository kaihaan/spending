# tests/test_models/test_category.py
"""Tests for category SQLAlchemy models.

Uses test database from conftest.py with "leave no trace" cleanup pattern.
"""

import uuid

from database.models.category import Category, CategoryKeyword


def test_create_category(db_session):
    """Test creating a category."""
    unique_name = f"Groceries_{uuid.uuid4().hex[:8]}"
    category = Category(
        name=unique_name, rule_pattern="(?i)(tesco|sainsbury|asda)", ai_suggested=False
    )
    db_session.add(category)
    db_session.commit()

    try:
        assert category.id is not None
        assert category.name == unique_name
        assert category.rule_pattern is not None
    finally:
        db_session.delete(category)
        db_session.commit()


def test_create_category_keyword(db_session):
    """Test creating a category keyword."""
    unique_category = f"Groceries_{uuid.uuid4().hex[:8]}"
    keyword = CategoryKeyword(category_name=unique_category, keyword="tesco")
    db_session.add(keyword)
    db_session.commit()

    try:
        assert keyword.id is not None
        assert keyword.category_name == unique_category
        assert keyword.keyword == "tesco"
        assert keyword.created_at is not None
    finally:
        db_session.delete(keyword)
        db_session.commit()


def test_category_keywords_relationship(db_session):
    """Test relationship between Category and CategoryKeyword."""
    unique_name = f"Groceries_{uuid.uuid4().hex[:8]}"
    category = Category(name=unique_name)
    keyword1 = CategoryKeyword(category_name=unique_name, keyword="tesco")
    keyword2 = CategoryKeyword(category_name=unique_name, keyword="sainsbury")

    db_session.add_all([category, keyword1, keyword2])
    db_session.commit()

    try:
        assert category.id is not None
        assert keyword1.id is not None
        assert keyword2.id is not None
    finally:
        # Clean up in reverse dependency order
        db_session.delete(keyword1)
        db_session.delete(keyword2)
        db_session.delete(category)
        db_session.commit()
