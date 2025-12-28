# tests/test_models/test_amazon.py
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from database.base import Base, SessionLocal, engine
from database.models.amazon import (
    AmazonBusinessConnection,
    AmazonBusinessLineItem,
    AmazonBusinessOrder,
    AmazonOrder,
    AmazonReturn,
    TrueLayerAmazonTransactionMatch,
)


@pytest.fixture
def db_session():
    # Create tables before each test
    Base.metadata.create_all(bind=engine)

    # Clean up any existing test data (reverse order due to foreign keys)
    connection = engine.connect()
    trans = connection.begin()
    try:
        connection.execute(TrueLayerAmazonTransactionMatch.__table__.delete())
        connection.execute(AmazonBusinessLineItem.__table__.delete())
        connection.execute(AmazonBusinessOrder.__table__.delete())
        connection.execute(AmazonBusinessConnection.__table__.delete())
        connection.execute(AmazonReturn.__table__.delete())
        connection.execute(AmazonOrder.__table__.delete())
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
        connection.execute(TrueLayerAmazonTransactionMatch.__table__.delete())
        connection.execute(AmazonBusinessLineItem.__table__.delete())
        connection.execute(AmazonBusinessOrder.__table__.delete())
        connection.execute(AmazonBusinessConnection.__table__.delete())
        connection.execute(AmazonReturn.__table__.delete())
        connection.execute(AmazonOrder.__table__.delete())
        trans.commit()
    except Exception:
        trans.rollback()
    finally:
        connection.close()


def test_create_amazon_order(db_session):
    """Test creating an Amazon order."""
    order = AmazonOrder(
        order_id="123-4567890-1234567",
        order_date=date(2025, 1, 15),
        website="amazon.co.uk",
        currency="GBP",
        total_owed=Decimal("49.99"),
        product_names="USB Cable, Phone Case",
        order_status="Shipped",
        shipment_status="Delivered",
    )
    db_session.add(order)
    db_session.commit()

    assert order.id is not None
    assert order.order_id == "123-4567890-1234567"
    assert order.total_owed == Decimal("49.99")
    assert order.created_at is not None


def test_amazon_order_unique_constraint(db_session):
    """Test unique constraint on order_id."""
    order1 = AmazonOrder(
        order_id="123-4567890-1234567",
        order_date=date(2025, 1, 15),
        website="amazon.co.uk",
        currency="GBP",
        total_owed=Decimal("49.99"),
        product_names="USB Cable",
    )
    db_session.add(order1)
    db_session.commit()

    # Attempt to insert duplicate order_id
    order2 = AmazonOrder(
        order_id="123-4567890-1234567",
        order_date=date(2025, 1, 16),
        website="amazon.co.uk",
        currency="GBP",
        total_owed=Decimal("29.99"),
        product_names="Other Product",
    )
    db_session.add(order2)
    with pytest.raises(IntegrityError):  # Duplicate order_id
        db_session.commit()


@pytest.mark.skip(
    reason="Requires transactions table (tested in Phase 4 - Legacy Models)"
)
def test_create_amazon_return(db_session):
    """Test creating an Amazon return."""
    # This test will be enabled in Phase 4 when the legacy transactions table is created
    # AmazonReturn has FKs to transactions table (original_transaction_id, refund_transaction_id)


def test_create_amazon_business_connection(db_session):
    """Test creating an Amazon Business connection."""
    connection = AmazonBusinessConnection(
        user_id=1,
        access_token="encrypted_token_data",
        refresh_token="encrypted_refresh_token",
        token_expires_at=datetime(2025, 2, 15, 12, 0, 0, tzinfo=UTC),
        region="UK",
        status="active",
    )
    db_session.add(connection)
    db_session.commit()

    assert connection.id is not None
    assert connection.user_id == 1
    assert connection.region == "UK"
    assert connection.status == "active"
    assert connection.created_at is not None
    assert connection.updated_at is not None


def test_create_amazon_business_order(db_session):
    """Test creating an Amazon Business order."""
    order = AmazonBusinessOrder(
        order_id="ABC-123-XYZ",
        order_date=date(2025, 1, 10),
        region="UK",
        order_status="Shipped",
        buyer_name="Test Buyer",
        buyer_email="buyer@example.com",
        subtotal=Decimal("100.00"),
        tax=Decimal("20.00"),
        shipping=Decimal("5.00"),
        net_total=Decimal("125.00"),
        currency="GBP",
        item_count=3,
        product_summary="Office Supplies, Paper, Pens",
    )
    db_session.add(order)
    db_session.commit()

    assert order.id is not None
    assert order.order_id == "ABC-123-XYZ"
    assert order.net_total == Decimal("125.00")
    assert order.created_at is not None


def test_amazon_business_order_unique_constraint(db_session):
    """Test unique constraint on business order_id."""
    order1 = AmazonBusinessOrder(
        order_id="ABC-123-XYZ",
        order_date=date(2025, 1, 10),
        net_total=Decimal("125.00"),
    )
    db_session.add(order1)
    db_session.commit()

    # Attempt to insert duplicate order_id
    order2 = AmazonBusinessOrder(
        order_id="ABC-123-XYZ",
        order_date=date(2025, 1, 11),
        net_total=Decimal("150.00"),
    )
    db_session.add(order2)
    with pytest.raises(IntegrityError):  # Duplicate order_id
        db_session.commit()


def test_create_amazon_business_line_item(db_session):
    """Test creating an Amazon Business line item."""
    # First create a business order
    order = AmazonBusinessOrder(
        order_id="ABC-123-XYZ",
        order_date=date(2025, 1, 10),
        net_total=Decimal("125.00"),
    )
    db_session.add(order)
    db_session.commit()

    # Now create a line item
    line_item = AmazonBusinessLineItem(
        order_id="ABC-123-XYZ",
        line_item_id="LINE-001",
        asin="B08XYZBCDE",
        title="Wireless Mouse",
        brand="Logitech",
        category="Electronics",
        quantity=2,
        unit_price=Decimal("25.00"),
        total_price=Decimal("50.00"),
        seller_name="Amazon UK",
    )
    db_session.add(line_item)
    db_session.commit()

    assert line_item.id is not None
    assert line_item.order_id == "ABC-123-XYZ"
    assert line_item.total_price == Decimal("50.00")
    assert line_item.created_at is not None


@pytest.mark.skip(reason="Requires TrueLayer transaction models (tested in Phase 3)")
def test_create_truelayer_amazon_match(db_session):
    """Test creating a TrueLayer-Amazon transaction match."""
    # This test will be enabled in Phase 3 when we can create
    # TrueLayer transactions and Amazon orders


@pytest.mark.skip(reason="Requires TrueLayer transaction models (tested in Phase 3)")
def test_truelayer_amazon_match_unique_constraint(db_session):
    """Test unique constraint on truelayer_transaction_id."""
    # This test will be enabled in Phase 3 when we can create
    # TrueLayer transactions and Amazon orders
