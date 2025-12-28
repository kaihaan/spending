"""Tests for TrueLayer models (BankConnection, TrueLayerAccount, TrueLayerTransaction, TrueLayerBalance)."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from database.base import Base, SessionLocal, engine
from database.models.truelayer import (
    BankConnection,
    TrueLayerAccount,
    TrueLayerBalance,
    TrueLayerTransaction,
)
from database.models.user import User


@pytest.fixture
def db_session():
    """Create a fresh database session for each test."""
    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    # Clean up existing test data
    connection = engine.connect()
    trans = connection.begin()
    try:
        # Clean up in reverse dependency order
        connection.execute(TrueLayerBalance.__table__.delete())
        connection.execute(TrueLayerTransaction.__table__.delete())
        connection.execute(TrueLayerAccount.__table__.delete())
        connection.execute(BankConnection.__table__.delete())
        connection.execute(User.__table__.delete().where(User.email.like("test%")))
        trans.commit()
    except Exception:
        trans.rollback()
    finally:
        connection.close()

    session = SessionLocal()
    yield session

    # Clean up after test
    session.rollback()
    session.close()


def test_create_bank_connection(db_session):
    """Test creating a bank connection."""
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()

    connection = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TrueLayer",
        access_token="encrypted_token",
        refresh_token="encrypted_refresh",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()

    assert connection.id is not None
    assert connection.user_id == user.id
    assert connection.provider_id == "truelayer"
    assert connection.connection_status == "active"


def test_create_truelayer_account(db_session):
    """Test creating a TrueLayer account."""
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()

    connection = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TrueLayer",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()

    account = TrueLayerAccount(
        connection_id=connection.id,
        account_id="acc_123",
        account_type="TRANSACTION",
        display_name="Current Account",
        currency="GBP",
    )
    db_session.add(account)
    db_session.commit()

    assert account.id is not None
    assert account.account_id == "acc_123"
    assert account.display_name == "Current Account"


def test_create_truelayer_transaction(db_session):
    """Test creating a TrueLayer transaction."""
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()

    connection = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TL",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()

    account = TrueLayerAccount(
        connection_id=connection.id,
        account_id="acc_123",
        account_type="TRANSACTION",
        display_name="Account",
        currency="GBP",
    )
    db_session.add(account)
    db_session.commit()

    txn = TrueLayerTransaction(
        account_id=account.id,
        transaction_id="txn_123",
        normalised_provider_transaction_id="norm_123",
        timestamp=datetime.now(UTC),
        description="Test purchase",
        amount=Decimal("10.50"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    db_session.add(txn)
    db_session.commit()

    assert txn.id is not None
    assert txn.amount == Decimal("10.50")
    assert txn.description == "Test purchase"
