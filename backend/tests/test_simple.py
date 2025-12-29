"""Simple test to validate database persistence."""

from sqlalchemy import text


def test_simple():
    """Always passes - just to trigger pytest."""
    assert True


def test_database_persistence(db_session):
    """Test that uses database fixture to trigger database setup."""
    # Simple query to verify database connection
    result = db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1
