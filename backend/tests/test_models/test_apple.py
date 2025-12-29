# tests/test_models/test_apple.py
"""Tests for Apple SQLAlchemy models.

Uses test database from conftest.py with "leave no trace" cleanup pattern.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from database.models.apple import (
    AppleTransaction,
)


def test_create_apple_transaction(db_session):
    """Test creating an Apple transaction."""
    unique_order_id = f"MXYZ{uuid.uuid4().hex[:10].upper()}"
    transaction = AppleTransaction(
        order_id=unique_order_id,
        order_date=date(2025, 1, 15),
        total_amount=Decimal("9.99"),
        currency="GBP",
        app_names="TestFlight, Final Cut Pro",
        publishers="Apple Inc., Apple Inc.",
        item_count=2,
    )
    db_session.add(transaction)
    db_session.commit()

    try:
        assert transaction.id is not None
        assert transaction.order_id == unique_order_id
        assert transaction.total_amount == Decimal("9.99")
        assert transaction.currency == "GBP"
        assert transaction.item_count == 2
        assert transaction.created_at is not None
    finally:
        db_session.delete(transaction)
        db_session.commit()


def test_apple_transaction_unique_constraint(db_session):
    """Test unique constraint on order_id."""
    unique_order_id = f"MXYZ{uuid.uuid4().hex[:10].upper()}"
    transaction1 = AppleTransaction(
        order_id=unique_order_id,
        order_date=date(2025, 1, 15),
        total_amount=Decimal("9.99"),
        currency="GBP",
        app_names="TestFlight",
    )
    db_session.add(transaction1)
    db_session.commit()

    try:
        # Attempt to insert duplicate order_id
        transaction2 = AppleTransaction(
            order_id=unique_order_id,
            order_date=date(2025, 1, 16),
            total_amount=Decimal("4.99"),
            currency="GBP",
            app_names="Other App",
        )
        db_session.add(transaction2)
        with pytest.raises(IntegrityError):  # Duplicate order_id
            db_session.commit()
    finally:
        db_session.rollback()
        # Re-fetch and delete transaction1
        existing = (
            db_session.query(AppleTransaction)
            .filter_by(order_id=unique_order_id)
            .first()
        )
        if existing:
            db_session.delete(existing)
            db_session.commit()


def test_apple_transaction_defaults(db_session):
    """Test default values for Apple transaction."""
    unique_order_id = f"MXYZ{uuid.uuid4().hex[:10].upper()}"
    transaction = AppleTransaction(
        order_id=unique_order_id,
        order_date=date(2025, 1, 20),
        total_amount=Decimal("2.99"),
        currency="GBP",
        app_names="Some App",
    )
    db_session.add(transaction)
    db_session.commit()

    try:
        # item_count should default to 1
        assert transaction.item_count == 1
        # publishers can be NULL
        assert transaction.publishers is None
        # source_file can be NULL
        assert transaction.source_file is None
    finally:
        db_session.delete(transaction)
        db_session.commit()


@pytest.mark.skip(reason="Requires TrueLayer transaction models (tested in Phase 3)")
def test_create_truelayer_apple_match(db_session):
    """Test creating a TrueLayer-Apple transaction match."""
    # This test will be enabled in Phase 3 when we can create
    # TrueLayer transactions and Apple transactions


@pytest.mark.skip(reason="Requires TrueLayer transaction models (tested in Phase 3)")
def test_truelayer_apple_match_unique_constraint(db_session):
    """Test unique constraint on truelayer_transaction_id."""
    # This test will be enabled in Phase 3 when we can create
    # TrueLayer transactions and Apple transactions


@pytest.mark.skip(reason="Requires TrueLayer transaction models (tested in Phase 3)")
def test_truelayer_apple_match_confidence_constraint(db_session):
    """Test confidence score constraint (0-100)."""
    # This test will be enabled in Phase 3 when we can create
    # TrueLayer transactions and Apple transactions
