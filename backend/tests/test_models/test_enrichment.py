# tests/test_models/test_enrichment.py
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from database.base import Base, SessionLocal, engine
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


@pytest.fixture
def db_session():
    """Create a database session for testing."""
    # Create tables before each test
    Base.metadata.create_all(bind=engine)

    # Clean up any existing test data (reverse order due to foreign keys)
    connection = engine.connect()
    trans = connection.begin()
    try:
        connection.execute(TransactionEnrichmentSource.__table__.delete())
        connection.execute(EnrichmentCache.__table__.delete())
        connection.execute(TrueLayerTransaction.__table__.delete())
        connection.execute(TrueLayerAccount.__table__.delete())
        connection.execute(BankConnection.__table__.delete())
        connection.execute(User.__table__.delete())
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
        connection.execute(TransactionEnrichmentSource.__table__.delete())
        connection.execute(EnrichmentCache.__table__.delete())
        connection.execute(TrueLayerTransaction.__table__.delete())
        connection.execute(TrueLayerAccount.__table__.delete())
        connection.execute(BankConnection.__table__.delete())
        connection.execute(User.__table__.delete())
        trans.commit()
    except Exception:
        trans.rollback()
    finally:
        connection.close()


@pytest.fixture
def user(db_session):
    """Create a test user."""
    test_user = User(email="test@example.com")
    db_session.add(test_user)
    db_session.commit()
    return test_user


@pytest.fixture
def bank_connection(db_session, user):
    """Create a test bank connection."""
    connection = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="Test Bank",
        access_token="encrypted_token",
        connection_status="active",
    )
    db_session.add(connection)
    db_session.commit()
    return connection


@pytest.fixture
def truelayer_account(db_session, bank_connection):
    """Create a test TrueLayer account."""
    account = TrueLayerAccount(
        connection_id=bank_connection.id,
        account_id="test-account-123",
        account_type="TRANSACTION",
        display_name="Test Current Account",
        currency="GBP",
    )
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def truelayer_transaction(db_session, truelayer_account):
    """Create a test TrueLayer transaction."""
    txn = TrueLayerTransaction(
        account_id=truelayer_account.id,
        transaction_id="txn-123",
        normalised_provider_transaction_id="norm-txn-123",
        timestamp=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
        description="AMAZON MARKETPLACE",
        amount=Decimal("29.99"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    db_session.add(txn)
    db_session.commit()
    return txn


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
# EnrichmentCache Tests
# ============================================================================


def test_create_enrichment_cache(db_session):
    """Test creating an enrichment cache entry."""
    cache = EnrichmentCache(
        transaction_description="AMAZON MARKETPLACE",
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Shopping", "merchant": "Amazon"}',
    )
    db_session.add(cache)
    db_session.commit()

    assert cache.id is not None
    assert cache.transaction_description == "AMAZON MARKETPLACE"
    assert cache.transaction_direction == "DEBIT"
    assert cache.enrichment_data == '{"category": "Shopping", "merchant": "Amazon"}'
    assert cache.cached_at is not None


def test_enrichment_cache_unique_constraint(db_session):
    """Test UNIQUE constraint on (description, direction)."""
    # Create first cache entry
    cache1 = EnrichmentCache(
        transaction_description="STARBUCKS",
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Food & Drink"}',
    )
    db_session.add(cache1)
    db_session.commit()

    # Attempt to create duplicate
    cache2 = EnrichmentCache(
        transaction_description="STARBUCKS",  # Same description
        transaction_direction="DEBIT",  # Same direction
        enrichment_data='{"category": "Different"}',
    )
    db_session.add(cache2)

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_enrichment_cache_different_directions(db_session):
    """Test same description with different directions is allowed."""
    cache1 = EnrichmentCache(
        transaction_description="PAYPAL TRANSFER",
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Payment"}',
    )
    db_session.add(cache1)
    db_session.commit()

    # Different direction should be allowed
    cache2 = EnrichmentCache(
        transaction_description="PAYPAL TRANSFER",
        transaction_direction="CREDIT",
        enrichment_data='{"category": "Refund"}',
    )
    db_session.add(cache2)
    db_session.commit()

    assert cache1.id != cache2.id


def test_enrichment_cache_nullable_direction(db_session):
    """Test enrichment cache with NULL direction."""
    cache = EnrichmentCache(
        transaction_description="GENERIC TRANSACTION",
        transaction_direction=None,
        enrichment_data='{"category": "Other"}',
    )
    db_session.add(cache)
    db_session.commit()

    assert cache.transaction_direction is None


def test_enrichment_cache_repr(db_session):
    """Test __repr__ method."""
    cache = EnrichmentCache(
        transaction_description="AMAZON",
        transaction_direction="DEBIT",
        enrichment_data='{"category": "Shopping"}',
    )
    db_session.add(cache)
    db_session.commit()

    repr_str = repr(cache)
    assert "EnrichmentCache" in repr_str
    assert "AMAZON" in repr_str
