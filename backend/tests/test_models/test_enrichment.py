# tests/test_models/test_enrichment.py
"""Tests for enrichment SQLAlchemy models.

Uses test database from conftest.py with "leave no trace" cleanup pattern.
All test data is created with unique identifiers and cleaned up after tests.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from database.models.enrichment import (
    EnrichmentCache,
    TransactionEnrichmentSource,
)
from database.models.truelayer import (
    BankConnection,
    TrueLayerAccount,
    TrueLayerTransaction,
)
from database.models.user import User

# ============================================================================
# Test Fixtures with Cleanup (Leave No Trace Pattern)
#
# Note: Database FK constraints don't have ON DELETE CASCADE, so we must
# delete in reverse dependency order: child records before parent records.
# ============================================================================


@pytest.fixture
def test_user(db_session):
    """Create a test user with unique email, cleaned up after test.

    Note: This fixture must be the LAST to yield in the fixture chain
    so it cleans up FIRST (pytest teardown is LIFO order).
    """
    unique_email = f"test_enrichment_{uuid.uuid4().hex[:8]}@example.com"
    user = User(email=unique_email)
    db_session.add(user)
    db_session.commit()
    user_id = user.id

    yield user

    # Cleanup: User is deleted by dependent fixtures first (LIFO teardown)
    # Only delete if still exists (might have been deleted by cascade test)
    try:
        db_session.rollback()  # Clear any pending state
        existing_user = db_session.get(User, user_id)
        if existing_user:
            db_session.delete(existing_user)
            db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def bank_connection(db_session, test_user):
    """Create a test bank connection, explicitly cleaned up before user."""
    connection = BankConnection(
        user_id=test_user.id,
        provider_id=f"test_provider_{uuid.uuid4().hex[:8]}",
        provider_name="Test Bank",
        access_token="encrypted_token",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()
    connection_id = connection.id

    yield connection

    # Cleanup: Delete connection before user cleanup runs
    try:
        db_session.rollback()  # Clear any pending state
        existing = db_session.get(BankConnection, connection_id)
        if existing:
            db_session.delete(existing)
            db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def truelayer_account(db_session, bank_connection):
    """Create a test TrueLayer account, explicitly cleaned up before connection."""
    account = TrueLayerAccount(
        connection_id=bank_connection.id,
        account_id=f"test-account-{uuid.uuid4().hex[:8]}",
        account_type="TRANSACTION",
        display_name="Test Current Account",
        currency="GBP",
    )
    db_session.add(account)
    db_session.commit()
    account_id = account.id

    yield account

    # Cleanup: Delete account before connection cleanup runs
    try:
        db_session.rollback()  # Clear any pending state
        existing = db_session.get(TrueLayerAccount, account_id)
        if existing:
            db_session.delete(existing)
            db_session.commit()
    except Exception:
        db_session.rollback()


@pytest.fixture
def truelayer_transaction(db_session, truelayer_account):
    """Create a test TrueLayer transaction, explicitly cleaned up before account."""
    unique_id = uuid.uuid4().hex[:8]
    txn = TrueLayerTransaction(
        account_id=truelayer_account.id,
        transaction_id=f"txn-{unique_id}",
        normalised_provider_transaction_id=f"norm-txn-{unique_id}",
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        description="AMAZON MARKETPLACE",
        amount=Decimal("29.99"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    db_session.add(txn)
    db_session.commit()
    txn_id = txn.id

    yield txn

    # Cleanup: Delete transaction before account cleanup runs
    try:
        db_session.rollback()  # Clear any pending state
        existing = db_session.get(TrueLayerTransaction, txn_id)
        if existing:
            db_session.delete(existing)
            db_session.commit()
    except Exception:
        db_session.rollback()


# ============================================================================
# TransactionEnrichmentSource Tests
# ============================================================================


def test_create_transaction_enrichment_source(db_session, truelayer_transaction):
    """Test creating a transaction enrichment source."""
    source = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="amazon",
        source_id=123,
        description="USB Cable, Phone Case",
        order_id="123-4567890-1234567",
        match_confidence=95,
        match_method="amount_date_match",
        is_primary=True,
        user_verified=False,
    )
    db_session.add(source)
    db_session.commit()

    assert source.id is not None
    assert source.truelayer_transaction_id == truelayer_transaction.id
    assert source.source_type == "amazon"
    assert source.source_id == 123
    assert source.description == "USB Cable, Phone Case"
    assert source.order_id == "123-4567890-1234567"
    assert source.match_confidence == 95
    assert source.match_method == "amount_date_match"
    assert source.is_primary is True
    assert source.user_verified is False
    assert source.created_at is not None
    assert source.updated_at is not None


def test_enrichment_source_defaults(db_session, truelayer_transaction):
    """Test default values for enrichment source."""
    source = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="gmail",
        description="Receipt from Coffee Shop",
    )
    db_session.add(source)
    db_session.commit()

    assert source.match_confidence == 100  # Default
    assert source.is_primary is False  # Default
    assert source.user_verified is False  # Default


def test_enrichment_source_with_line_items(db_session, truelayer_transaction):
    """Test enrichment source with JSONB line items."""
    line_items = [
        {"name": "USB Cable", "quantity": 1, "price": "9.99"},
        {"name": "Phone Case", "quantity": 2, "price": "10.00"},
    ]

    source = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="amazon",
        description="USB Cable, Phone Case",
        line_items=line_items,
    )
    db_session.add(source)
    db_session.commit()

    # Refresh to get JSONB data
    db_session.refresh(source)
    assert source.line_items is not None
    assert len(source.line_items) == 2
    assert source.line_items[0]["name"] == "USB Cable"


def test_enrichment_source_type_constraint(db_session, truelayer_transaction):
    """Test CHECK constraint on source_type."""
    source = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="invalid_type",  # Not in allowed list
        description="Test",
    )
    db_session.add(source)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_enrichment_source_confidence_constraint(db_session, truelayer_transaction):
    """Test CHECK constraint on match_confidence (0-100)."""
    source = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="amazon",
        description="Test",
        match_confidence=150,  # Invalid: > 100
    )
    db_session.add(source)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_enrichment_source_unique_constraint(db_session, truelayer_transaction):
    """Test UNIQUE constraint on (transaction_id, source_type, source_id)."""
    # Create first enrichment source
    source1 = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="amazon",
        source_id=123,
        description="First match",
    )
    db_session.add(source1)
    db_session.commit()

    # Attempt to create duplicate
    source2 = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="amazon",
        source_id=123,  # Same source_id
        description="Duplicate match",
    )
    db_session.add(source2)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_enrichment_source_cascade_delete(db_session, truelayer_transaction):
    """Test CASCADE DELETE when transaction is deleted."""
    source = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="amazon",
        description="Test",
    )
    db_session.add(source)
    db_session.commit()
    source_id = source.id

    # Delete the transaction
    db_session.delete(truelayer_transaction)
    db_session.commit()

    # Enrichment source should be deleted too
    deleted_source = db_session.get(TransactionEnrichmentSource, source_id)
    assert deleted_source is None


def test_enrichment_source_repr(db_session, truelayer_transaction):
    """Test __repr__ method."""
    source = TransactionEnrichmentSource(
        truelayer_transaction_id=truelayer_transaction.id,
        source_type="amazon",
        source_id=123,
        description="USB Cable",
    )
    db_session.add(source)
    db_session.commit()

    repr_str = repr(source)
    assert "TransactionEnrichmentSource" in repr_str
    assert "amazon" in repr_str
    assert "123" in repr_str


# ============================================================================
# EnrichmentCache Tests (with cleanup)
# ============================================================================


def test_create_enrichment_cache(db_session):
    """Test creating an enrichment cache entry."""
    unique_desc = f"AMAZON MARKETPLACE_{uuid.uuid4().hex[:8]}"
    cache = EnrichmentCache(
        transaction_description=unique_desc,
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Shopping", "merchant": "Amazon"}',
    )
    db_session.add(cache)
    db_session.commit()

    try:
        assert cache.id is not None
        assert cache.transaction_description == unique_desc
        assert cache.transaction_direction == "DEBIT"
        assert cache.enrichment_data == '{"category": "Shopping", "merchant": "Amazon"}'
        assert cache.cached_at is not None
    finally:
        # Cleanup
        db_session.delete(cache)
        db_session.commit()


def test_enrichment_cache_unique_constraint(db_session):
    """Test UNIQUE constraint on (description, direction)."""
    unique_desc = f"STARBUCKS_{uuid.uuid4().hex[:8]}"

    # Create first cache entry
    cache1 = EnrichmentCache(
        transaction_description=unique_desc,
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Food & Drink"}',
    )
    db_session.add(cache1)
    db_session.commit()

    try:
        # Attempt to create duplicate
        cache2 = EnrichmentCache(
            transaction_description=unique_desc,  # Same description
            transaction_direction="DEBIT",  # Same direction
            enrichment_data='{"category": "Different"}',
        )
        db_session.add(cache2)

        with pytest.raises(IntegrityError):
            db_session.commit()
    finally:
        # Cleanup - rollback any failed transaction first
        db_session.rollback()
        # Re-fetch and delete cache1
        cache1 = (
            db_session.query(EnrichmentCache)
            .filter_by(transaction_description=unique_desc)
            .first()
        )
        if cache1:
            db_session.delete(cache1)
            db_session.commit()


def test_enrichment_cache_different_directions(db_session):
    """Test same description with different directions is allowed."""
    unique_desc = f"PAYPAL TRANSFER_{uuid.uuid4().hex[:8]}"

    cache1 = EnrichmentCache(
        transaction_description=unique_desc,
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Payment"}',
    )
    db_session.add(cache1)
    db_session.commit()

    # Different direction should be allowed
    cache2 = EnrichmentCache(
        transaction_description=unique_desc,
        transaction_direction="CREDIT",
        enrichment_data='{"category": "Refund"}',
    )
    db_session.add(cache2)
    db_session.commit()

    try:
        assert cache1.id != cache2.id
    finally:
        # Cleanup both
        db_session.delete(cache1)
        db_session.delete(cache2)
        db_session.commit()


def test_enrichment_cache_nullable_direction(db_session):
    """Test enrichment cache with NULL direction."""
    unique_desc = f"GENERIC TRANSACTION_{uuid.uuid4().hex[:8]}"
    cache = EnrichmentCache(
        transaction_description=unique_desc,
        transaction_direction=None,
        enrichment_data='{"category": "Other"}',
    )
    db_session.add(cache)
    db_session.commit()

    try:
        assert cache.transaction_direction is None
    finally:
        db_session.delete(cache)
        db_session.commit()


def test_enrichment_cache_repr(db_session):
    """Test __repr__ method."""
    unique_desc = f"AMAZON_{uuid.uuid4().hex[:8]}"
    cache = EnrichmentCache(
        transaction_description=unique_desc,
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Shopping"}',
    )
    db_session.add(cache)
    db_session.commit()

    try:
        repr_str = repr(cache)
        assert "EnrichmentCache" in repr_str
        assert unique_desc in repr_str
    finally:
        db_session.delete(cache)
        db_session.commit()
