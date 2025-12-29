"""Tests for TrueLayer models (BankConnection, TrueLayerAccount, TrueLayerTransaction, TrueLayerBalance).

Uses test database from conftest.py with "leave no trace" cleanup pattern.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from database.models.truelayer import (
    BankConnection,
    TrueLayerAccount,
    TrueLayerTransaction,
)
from database.models.user import User


def test_create_bank_connection(db_session):
    """Test creating a bank connection."""
    unique_email = f"test_truelayer_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=unique_email)
    db_session.add(user)
    db_session.commit()

    unique_provider = f"provider_{uuid.uuid4().hex[:8]}"
    connection = BankConnection(
        user_id=user.id,
        provider_id=unique_provider,
        provider_name="TrueLayer",
        access_token="encrypted_token",
        refresh_token="encrypted_refresh",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()

    try:
        assert connection.id is not None
        assert connection.user_id == user.id
        assert connection.provider_id == unique_provider
        assert connection.connection_status == "active"
    finally:
        # Cleanup in reverse dependency order - commit each delete individually
        # to enforce order (SQLAlchemy doesn't guarantee delete order in batch)
        db_session.delete(connection)
        db_session.commit()
        db_session.delete(user)
        db_session.commit()


def test_create_truelayer_account(db_session):
    """Test creating a TrueLayer account."""
    unique_email = f"test_truelayer_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=unique_email)
    db_session.add(user)
    db_session.commit()

    unique_provider = f"provider_{uuid.uuid4().hex[:8]}"
    connection = BankConnection(
        user_id=user.id,
        provider_id=unique_provider,
        provider_name="TrueLayer",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()

    unique_account_id = f"acc_{uuid.uuid4().hex[:8]}"
    account = TrueLayerAccount(
        connection_id=connection.id,
        account_id=unique_account_id,
        account_type="TRANSACTION",
        display_name="Current Account",
        currency="GBP",
    )
    db_session.add(account)
    db_session.commit()

    try:
        assert account.id is not None
        assert account.account_id == unique_account_id
        assert account.display_name == "Current Account"
    finally:
        # Cleanup in reverse dependency order - commit each delete individually
        db_session.delete(account)
        db_session.commit()
        db_session.delete(connection)
        db_session.commit()
        db_session.delete(user)
        db_session.commit()


def test_create_truelayer_transaction(db_session):
    """Test creating a TrueLayer transaction."""
    unique_email = f"test_truelayer_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=unique_email)
    db_session.add(user)
    db_session.commit()

    unique_provider = f"provider_{uuid.uuid4().hex[:8]}"
    connection = BankConnection(
        user_id=user.id,
        provider_id=unique_provider,
        provider_name="TL",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()

    unique_account_id = f"acc_{uuid.uuid4().hex[:8]}"
    account = TrueLayerAccount(
        connection_id=connection.id,
        account_id=unique_account_id,
        account_type="TRANSACTION",
        display_name="Account",
        currency="GBP",
    )
    db_session.add(account)
    db_session.commit()

    unique_txn_id = f"txn_{uuid.uuid4().hex[:8]}"
    txn = TrueLayerTransaction(
        account_id=account.id,
        transaction_id=unique_txn_id,
        normalised_provider_transaction_id=f"norm_{unique_txn_id}",
        timestamp=datetime.now(UTC),
        description="Test purchase",
        amount=Decimal("10.50"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    db_session.add(txn)
    db_session.commit()

    try:
        assert txn.id is not None
        assert txn.amount == Decimal("10.50")
        assert txn.description == "Test purchase"
    finally:
        # Cleanup in reverse dependency order - commit each delete individually
        db_session.delete(txn)
        db_session.commit()
        db_session.delete(account)
        db_session.commit()
        db_session.delete(connection)
        db_session.commit()
        db_session.delete(user)
        db_session.commit()
