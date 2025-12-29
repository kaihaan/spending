# tests/test_models/test_amazon.py
"""Tests for Amazon SQLAlchemy models.

Uses test database from conftest.py with "leave no trace" cleanup pattern.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from database.models.amazon import (
    AmazonBusinessConnection,
    AmazonBusinessLineItem,
    AmazonBusinessOrder,
    AmazonOrder,
)


def test_create_amazon_order(db_session):
    """Test creating an Amazon order."""
    unique_order_id = (
        f"{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:7]}-{uuid.uuid4().hex[:7]}"
    )
    order = AmazonOrder(
        order_id=unique_order_id,
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

    try:
        assert order.id is not None
        assert order.order_id == unique_order_id
        assert order.total_owed == Decimal("49.99")
        assert order.created_at is not None
    finally:
        db_session.delete(order)
        db_session.commit()


def test_amazon_order_unique_constraint(db_session):
    """Test unique constraint on order_id."""
    unique_order_id = (
        f"{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:7]}-{uuid.uuid4().hex[:7]}"
    )
    order1 = AmazonOrder(
        order_id=unique_order_id,
        order_date=date(2025, 1, 15),
        website="amazon.co.uk",
        currency="GBP",
        total_owed=Decimal("49.99"),
        product_names="USB Cable",
    )
    db_session.add(order1)
    db_session.commit()

    try:
        # Attempt to insert duplicate order_id
        order2 = AmazonOrder(
            order_id=unique_order_id,
            order_date=date(2025, 1, 16),
            website="amazon.co.uk",
            currency="GBP",
            total_owed=Decimal("29.99"),
            product_names="Other Product",
        )
        db_session.add(order2)
        with pytest.raises(IntegrityError):  # Duplicate order_id
            db_session.commit()
    finally:
        db_session.rollback()
        existing = (
            db_session.query(AmazonOrder).filter_by(order_id=unique_order_id).first()
        )
        if existing:
            db_session.delete(existing)
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
    # Use a unique user_id to avoid conflicts with production data
    unique_user_id = 900000 + (uuid.uuid4().int % 100000)
    connection = AmazonBusinessConnection(
        user_id=unique_user_id,
        access_token="encrypted_token_data",
        refresh_token="encrypted_refresh_token",
        token_expires_at=datetime(2025, 2, 15, 12, 0, 0, tzinfo=UTC),
        region="UK",
        status="active",
    )
    db_session.add(connection)
    db_session.commit()

    try:
        assert connection.id is not None
        assert connection.user_id == unique_user_id
        assert connection.region == "UK"
        assert connection.status == "active"
        assert connection.created_at is not None
        assert connection.updated_at is not None
    finally:
        db_session.delete(connection)
        db_session.commit()


def test_create_amazon_business_order(db_session):
    """Test creating an Amazon Business order."""
    unique_order_id = (
        f"ABC-{uuid.uuid4().hex[:3].upper()}-{uuid.uuid4().hex[:3].upper()}"
    )
    order = AmazonBusinessOrder(
        order_id=unique_order_id,
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

    try:
        assert order.id is not None
        assert order.order_id == unique_order_id
        assert order.net_total == Decimal("125.00")
        assert order.created_at is not None
    finally:
        db_session.delete(order)
        db_session.commit()


def test_amazon_business_order_unique_constraint(db_session):
    """Test unique constraint on business order_id."""
    unique_order_id = (
        f"ABC-{uuid.uuid4().hex[:3].upper()}-{uuid.uuid4().hex[:3].upper()}"
    )
    order1 = AmazonBusinessOrder(
        order_id=unique_order_id,
        order_date=date(2025, 1, 10),
        net_total=Decimal("125.00"),
    )
    db_session.add(order1)
    db_session.commit()

    try:
        # Attempt to insert duplicate order_id
        order2 = AmazonBusinessOrder(
            order_id=unique_order_id,
            order_date=date(2025, 1, 11),
            net_total=Decimal("150.00"),
        )
        db_session.add(order2)
        with pytest.raises(IntegrityError):  # Duplicate order_id
            db_session.commit()
    finally:
        db_session.rollback()
        existing = (
            db_session.query(AmazonBusinessOrder)
            .filter_by(order_id=unique_order_id)
            .first()
        )
        if existing:
            db_session.delete(existing)
            db_session.commit()


def test_create_amazon_business_line_item(db_session):
    """Test creating an Amazon Business line item."""
    unique_order_id = (
        f"ABC-{uuid.uuid4().hex[:3].upper()}-{uuid.uuid4().hex[:3].upper()}"
    )
    unique_line_item_id = f"LINE-{uuid.uuid4().hex[:6].upper()}"

    # First create a business order
    order = AmazonBusinessOrder(
        order_id=unique_order_id,
        order_date=date(2025, 1, 10),
        net_total=Decimal("125.00"),
    )
    db_session.add(order)
    db_session.commit()

    # Now create a line item
    line_item = AmazonBusinessLineItem(
        order_id=unique_order_id,
        line_item_id=unique_line_item_id,
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

    try:
        assert line_item.id is not None
        assert line_item.order_id == unique_order_id
        assert line_item.total_price == Decimal("50.00")
        assert line_item.created_at is not None
    finally:
        # Clean up in reverse dependency order
        db_session.delete(line_item)
        db_session.delete(order)
        db_session.commit()


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
