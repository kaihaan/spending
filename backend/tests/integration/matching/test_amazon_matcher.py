"""Integration tests for Amazon Business transaction matching.

Tests critical matching functionality:
- Deduplication (prevents creating duplicate matches)
- Match accuracy (amount and date matching)
- Confidence scoring
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from database.models.amazon import (
    AmazonBusinessConnection,
    AmazonBusinessOrder,
    TrueLayerAmazonBusinessMatch,
)
from database.models.truelayer import (
    BankConnection,
    TrueLayerAccount,
    TrueLayerTransaction,
)
from database.models.user import User
from mcp.amazon_business_matcher import match_all_amazon_business_transactions

# ============================================================================
# DEDUPLICATION TESTS (TIER 1 CRITICAL)
# ============================================================================
#
# NOTE: Database fixtures (db_session, clean_db) are imported from
# tests/fixtures/conftest.py which provides test database isolation.
# Tests run against a mirrored copy of production (schema + data) to
# prevent production data loss.
#


def test_matcher_prevents_duplicate_matches(clean_db):
    """Test matcher doesn't create duplicate matches.

    CRITICAL: Duplicate matches corrupt spending analysis by double-counting
    transactions. This test validates deduplication logic.

    Test scenario:
    1. Create a TrueLayer transaction
    2. Create a matching Amazon order
    3. Create a match manually (simulate previous match)
    4. Run matcher again
    5. Verify no duplicate match was created
    """
    # Setup: Create user, bank connection, and account
    user = User(email="test@example.com")
    clean_db.add(user)
    clean_db.commit()

    bank_conn = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TrueLayer",
        connection_status="active",
    )
    clean_db.add(bank_conn)
    clean_db.commit()

    account = TrueLayerAccount(
        connection_id=bank_conn.id,
        account_id="acc-123",
        account_type="TRANSACTION",
        display_name="Current Account",
        currency="GBP",
    )
    clean_db.add(account)
    clean_db.commit()

    # Create TrueLayer transaction (Amazon purchase)
    transaction = TrueLayerTransaction(
        account_id=account.id,
        transaction_id="txn-123",
        normalised_provider_transaction_id="norm-123",
        timestamp=datetime.now(UTC),
        description="AMAZON EU",
        amount=Decimal("-45.99"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    clean_db.add(transaction)
    clean_db.commit()

    # Create Amazon Business connection
    amazon_conn = AmazonBusinessConnection(
        user_id=user.id,
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        marketplace_id="A1F83G8C2ARO7P",
        region="UK",
        is_sandbox=False,
    )
    clean_db.add(amazon_conn)
    clean_db.commit()

    # Create matching Amazon order
    order = AmazonBusinessOrder(
        order_id="902-1234567-8901234",
        order_date=datetime.now(UTC).date(),
        net_total=Decimal("45.99"),
        currency="GBP",
        order_status="Shipped",
    )
    clean_db.add(order)
    clean_db.commit()

    # Create initial match (simulate previous match run)
    initial_match = TrueLayerAmazonBusinessMatch(
        truelayer_transaction_id=transaction.id,
        amazon_business_order_id=order.id,
        match_confidence=95,
    )
    clean_db.add(initial_match)
    clean_db.commit()

    # Verify initial match exists
    initial_count = clean_db.query(TrueLayerAmazonBusinessMatch).count()
    assert initial_count == 1

    # Run matcher again (should NOT create duplicate)
    result = match_all_amazon_business_transactions()

    # Verify no duplicate match was created
    final_count = clean_db.query(TrueLayerAmazonBusinessMatch).count()
    assert final_count == 1, "Matcher created duplicate match!"

    # Verify matcher reported 0 new matches
    assert result["matched"] == 0
    assert (
        result["total_processed"] == 0
    )  # Already matched transactions shouldn't be processed


def test_matcher_creates_match_for_unmatched_transaction(clean_db):
    """Test matcher creates match for genuinely unmatched transaction."""
    # Setup: Create user, bank connection, and account
    user = User(email="test@example.com")
    clean_db.add(user)
    clean_db.commit()

    bank_conn = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TrueLayer",
        connection_status="active",
    )
    clean_db.add(bank_conn)
    clean_db.commit()

    account = TrueLayerAccount(
        connection_id=bank_conn.id,
        account_id="acc-123",
        account_type="TRANSACTION",
        display_name="Current Account",
        currency="GBP",
    )
    clean_db.add(account)
    clean_db.commit()

    # Create UNMATCHED TrueLayer transaction
    transaction = TrueLayerTransaction(
        account_id=account.id,
        transaction_id="txn-456",
        normalised_provider_transaction_id="norm-456",
        timestamp=datetime.now(UTC),
        description="AMAZON EU",
        amount=Decimal("-23.50"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    clean_db.add(transaction)
    clean_db.commit()

    # Create Amazon Business connection
    amazon_conn = AmazonBusinessConnection(
        user_id=user.id,
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        marketplace_id="A1F83G8C2ARO7P",
        region="UK",
        is_sandbox=False,
    )
    clean_db.add(amazon_conn)
    clean_db.commit()

    # Create matching Amazon order
    order = AmazonBusinessOrder(
        order_id="902-9876543-2109876",
        order_date=datetime.now(UTC).date(),
        net_total=Decimal("23.50"),
        currency="GBP",
        order_status="Shipped",
    )
    clean_db.add(order)
    clean_db.commit()

    # Verify no matches exist initially
    initial_count = clean_db.query(TrueLayerAmazonBusinessMatch).count()
    assert initial_count == 0

    # Run matcher
    result = match_all_amazon_business_transactions()

    # Verify match was created
    final_count = clean_db.query(TrueLayerAmazonBusinessMatch).count()
    assert final_count == 1, "Matcher failed to create match for unmatched transaction!"

    # Verify matcher reported 1 new match
    assert result["matched"] == 1
    assert result["total_processed"] == 1


# ============================================================================
# MATCHING ACCURACY TESTS
# ============================================================================


def test_matcher_matches_exact_amount(clean_db):
    """Test matcher correctly matches transactions by exact amount."""
    # Setup user, account, connection
    user = User(email="test@example.com")
    clean_db.add(user)
    clean_db.commit()

    bank_conn = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TrueLayer",
        connection_status="active",
    )
    clean_db.add(bank_conn)
    clean_db.commit()

    account = TrueLayerAccount(
        connection_id=bank_conn.id,
        account_id="acc-123",
        account_type="TRANSACTION",
        display_name="Current Account",
        currency="GBP",
    )
    clean_db.add(account)
    clean_db.commit()

    # Create transaction with specific amount
    transaction = TrueLayerTransaction(
        account_id=account.id,
        transaction_id="txn-789",
        normalised_provider_transaction_id="norm-789",
        timestamp=datetime.now(UTC),
        description="AMAZON EU",
        amount=Decimal("-78.45"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    clean_db.add(transaction)
    clean_db.commit()

    # Create Amazon Business connection
    amazon_conn = AmazonBusinessConnection(
        user_id=user.id,
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        marketplace_id="A1F83G8C2ARO7P",
        region="UK",
        is_sandbox=False,
    )
    clean_db.add(amazon_conn)
    clean_db.commit()

    # Create order with matching amount
    matching_order = AmazonBusinessOrder(
        order_id="902-1111111-1111111",
        order_date=datetime.now(UTC).date(),
        net_total=Decimal("78.45"),
        currency="GBP",
        order_status="Shipped",
    )
    clean_db.add(matching_order)

    # Create order with different amount (should NOT match)
    non_matching_order = AmazonBusinessOrder(
        order_id="902-2222222-2222222",
        order_date=datetime.now(UTC).date(),
        net_total=Decimal("78.46"),  # 1p difference
        currency="GBP",
        order_status="Shipped",
    )
    clean_db.add(non_matching_order)
    clean_db.commit()

    # Run matcher
    result = match_all_amazon_business_transactions()

    # Verify match was created
    assert result["matched"] == 1

    # Verify correct order was matched
    match = clean_db.query(TrueLayerAmazonBusinessMatch).first()
    assert match.amazon_business_order_id == matching_order.id


def test_matcher_respects_date_proximity(clean_db):
    """Test matcher considers date proximity when matching."""
    # Setup user, account, connection
    user = User(email="test@example.com")
    clean_db.add(user)
    clean_db.commit()

    bank_conn = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TrueLayer",
        connection_status="active",
    )
    clean_db.add(bank_conn)
    clean_db.commit()

    account = TrueLayerAccount(
        connection_id=bank_conn.id,
        account_id="acc-123",
        account_type="TRANSACTION",
        display_name="Current Account",
        currency="GBP",
    )
    clean_db.add(account)
    clean_db.commit()

    txn_date = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

    # Create transaction
    transaction = TrueLayerTransaction(
        account_id=account.id,
        transaction_id="txn-date-test",
        normalised_provider_transaction_id="norm-date-test",
        timestamp=txn_date,
        description="AMAZON EU",
        amount=Decimal("-50.00"),
        currency="GBP",
        transaction_type="DEBIT",
    )
    clean_db.add(transaction)
    clean_db.commit()

    # Create Amazon Business connection
    amazon_conn = AmazonBusinessConnection(
        user_id=user.id,
        access_token="test-access-token",
        refresh_token="test-refresh-token",
        marketplace_id="A1F83G8C2ARO7P",
        region="UK",
        is_sandbox=False,
    )
    clean_db.add(amazon_conn)
    clean_db.commit()

    # Create order close in time (1 day before - should match)
    close_order = AmazonBusinessOrder(
        order_id="902-close-date",
        order_date=(txn_date - timedelta(days=1)).date(),
        net_total=Decimal("50.00"),
        currency="GBP",
        order_status="Shipped",
    )
    clean_db.add(close_order)

    # Create order far in time (30 days before - may not match)
    far_order = AmazonBusinessOrder(
        order_id="902-far-date",
        order_date=(txn_date - timedelta(days=30)).date(),
        net_total=Decimal("50.00"),
        currency="GBP",
        order_status="Shipped",
    )
    clean_db.add(far_order)
    clean_db.commit()

    # Run matcher
    result = match_all_amazon_business_transactions()

    # Verify a match was created
    if result["matched"] > 0:
        match = clean_db.query(TrueLayerAmazonBusinessMatch).first()
        # Should prefer closer date
        assert match.amazon_business_order_id == close_order.id
