# tests/test_models/test_category.py
import pytest

from database.base import Base, SessionLocal, engine
from database.models.category import Category, CategoryKeyword


@pytest.fixture
def db_session():
    # Create tables before each test
    Base.metadata.create_all(bind=engine)

    # Clean up any existing test data
    connection = engine.connect()
    trans = connection.begin()
    try:
        connection.execute(CategoryKeyword.__table__.delete())
        connection.execute(Category.__table__.delete())
        trans.commit()
    except Exception:
        trans.rollback()
    finally:
        connection.close()

    session = SessionLocal()

    yield session

    # Clean up and close session
    session.rollback()
    session.close()

    # Clean up test data
    connection = engine.connect()
    trans = connection.begin()
    try:
        connection.execute(CategoryKeyword.__table__.delete())
        connection.execute(Category.__table__.delete())
        trans.commit()
    except Exception:
        trans.rollback()
    finally:
        connection.close()


def test_create_category(db_session):
    """Test creating a category."""
    category = Category(
        name="Groceries", rule_pattern="(?i)(tesco|sainsbury|asda)", ai_suggested=False
    )
    db_session.add(category)
    db_session.commit()

    assert category.id is not None
    assert category.name == "Groceries"
    assert category.rule_pattern is not None


def test_create_category_keyword(db_session):
    """Test creating a category keyword."""
    keyword = CategoryKeyword(category_name="Groceries", keyword="tesco")
    db_session.add(keyword)
    db_session.commit()

    assert keyword.id is not None
    assert keyword.category_name == "Groceries"
    assert keyword.keyword == "tesco"
    assert keyword.created_at is not None


def test_category_keywords_relationship(db_session):
    """Test relationship between Category and CategoryKeyword."""
    category = Category(name="Groceries")
    keyword1 = CategoryKeyword(category_name="Groceries", keyword="tesco")
    keyword2 = CategoryKeyword(category_name="Groceries", keyword="sainsbury")

    db_session.add_all([category, keyword1, keyword2])
    db_session.commit()

    # Test relationship (if we add one later)
    assert category.id is not None
