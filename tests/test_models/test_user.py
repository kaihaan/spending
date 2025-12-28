# tests/test_models/test_user.py
import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from database.base import SessionLocal, engine, Base
from database.models.user import User


@pytest.fixture(scope="function")
def db_session():
    """Create fresh database session for each test."""
    # Ensure users table exists
    Base.metadata.create_all(bind=engine)

    # Create a connection and start a transaction
    connection = engine.connect()
    transaction = connection.begin()

    # Create session bound to the connection
    session = SessionLocal(bind=connection)

    yield session

    # Rollback transaction (clean up test data)
    session.close()
    connection.close()


def test_create_user(db_session):
    """Test creating a user."""
    user = User(email="test_create@example.com")
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.email == "test_create@example.com"
    assert user.created_at is not None
    assert user.updated_at is not None


def test_user_email_unique(db_session):
    """Test email uniqueness constraint."""
    user1 = User(email="test_unique@example.com")
    db_session.add(user1)
    db_session.commit()

    user2 = User(email="test_unique@example.com")
    db_session.add(user2)

    with pytest.raises(IntegrityError):
        db_session.commit()
