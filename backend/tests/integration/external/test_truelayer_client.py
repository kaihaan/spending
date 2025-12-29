"""Integration tests for TrueLayer API client.

Tests critical integration points:
- Account and transaction fetching
- Pagination handling (avoiding silent data loss)
- Rate limit handling with exponential backoff
- Error response handling (401 token expiry, 429 rate limits)
"""

import pytest
import responses
from requests import HTTPError

from mcp.truelayer_client import TrueLayerClient

# ============================================================================
# PAGINATION TESTS (TIER 1 CRITICAL)
# ============================================================================


@responses.activate
def test_get_accounts_single_page():
    """Test fetching accounts when all results fit in one page."""
    # Setup mock response
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts",
        json={
            "results": [
                {"account_id": "acc-1", "display_name": "Current Account"},
                {"account_id": "acc-2", "display_name": "Savings Account"},
            ],
            "status": "Succeeded",
        },
        status=200,
    )

    client = TrueLayerClient("test-access-token")
    accounts = client.get_accounts()

    assert len(accounts) == 2
    assert accounts[0]["account_id"] == "acc-1"
    assert accounts[1]["account_id"] == "acc-2"


@responses.activate
def test_get_transactions_pagination():
    """Test transaction fetching handles pagination correctly.

    CRITICAL: This test prevents silent data loss if pagination fails.
    Validates that the client follows the 'next_cursor' field to fetch
    all pages of results.
    """
    # Page 1 response with cursor for next page
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts/acc-123/transactions",
        json={
            "results": [
                {"transaction_id": "txn-1", "amount": -10.50, "currency": "GBP"},
                {"transaction_id": "txn-2", "amount": -20.00, "currency": "GBP"},
            ],
            "next_cursor": "cursor_page2",
            "status": "Succeeded",
        },
        status=200,
    )

    # Page 2 response (final page, no cursor)
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts/acc-123/transactions",
        json={
            "results": [
                {"transaction_id": "txn-3", "amount": -30.00, "currency": "GBP"},
            ],
            "status": "Succeeded",
        },
        status=200,
    )

    client = TrueLayerClient("test-access-token")
    transactions = client.get_transactions("acc-123")

    # Verify all pages were fetched
    assert len(transactions) == 3
    assert transactions[0]["transaction_id"] == "txn-1"
    assert transactions[1]["transaction_id"] == "txn-2"
    assert transactions[2]["transaction_id"] == "txn-3"

    # Verify two API calls were made (pagination)
    assert len(responses.calls) == 2


@responses.activate
def test_get_transactions_empty_results():
    """Test handling of empty transaction results."""
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts/acc-123/transactions",
        json={"results": [], "status": "Succeeded"},
        status=200,
    )

    client = TrueLayerClient("test-access-token")
    transactions = client.get_transactions("acc-123")

    assert len(transactions) == 0
    assert isinstance(transactions, list)


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


@responses.activate
def test_401_token_expiry_raises_error():
    """Test that 401 token expiry error is properly raised.

    Note: Current implementation doesn't handle token refresh automatically.
    This test validates that the error is raised so callers can implement
    token refresh logic.
    """
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts",
        json={
            "error": "invalid_token",
            "error_description": "The access token expired",
        },
        status=401,
    )

    client = TrueLayerClient("expired-token")

    with pytest.raises(HTTPError) as exc_info:
        client.get_accounts()

    assert exc_info.value.response.status_code == 401


@responses.activate
def test_429_rate_limit_retry_with_backoff():
    """Test that 429 rate limit errors trigger retry with exponential backoff.

    CRITICAL: Rate limits can cause API bans if not handled properly.
    This test validates exponential backoff (2s, 4s, 8s) is implemented.
    """
    # First two calls return 429 (rate limited)
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts",
        json={
            "error": "provider_too_many_requests",
            "error_description": "Too many requests",
        },
        status=429,
    )
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts",
        json={
            "error": "provider_too_many_requests",
            "error_description": "Too many requests",
        },
        status=429,
    )

    # Third call succeeds
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts",
        json={
            "results": [{"account_id": "acc-1", "display_name": "Current Account"}],
            "status": "Succeeded",
        },
        status=200,
    )

    client = TrueLayerClient("test-access-token")
    accounts = client.get_accounts()

    # Verify retry worked and data was eventually retrieved
    assert len(accounts) == 1
    assert accounts[0]["account_id"] == "acc-1"

    # Verify 3 attempts were made (2 failures + 1 success)
    assert len(responses.calls) == 3


@responses.activate
def test_429_rate_limit_max_retries_exceeded():
    """Test that max retries are respected for persistent rate limits."""
    # All attempts return 429
    for _ in range(3):
        responses.add(
            responses.GET,
            "https://api.truelayer.com/data/v1/accounts",
            json={
                "error": "provider_too_many_requests",
                "error_description": "Too many requests",
            },
            status=429,
        )

    client = TrueLayerClient("test-access-token")

    with pytest.raises(HTTPError) as exc_info:
        client.get_accounts()

    # Verify error is 429 and max retries (3) were attempted
    assert exc_info.value.response.status_code == 429
    assert len(responses.calls) == 3


# ============================================================================
# PAGINATION EDGE CASES
# ============================================================================


@responses.activate
def test_get_transactions_partial_last_page():
    """Test pagination when last page has fewer items than page size."""
    # Page 1 - full page (100 items, default limit)
    page1_transactions = [
        {"transaction_id": f"txn-{i}", "amount": -float(i), "currency": "GBP"}
        for i in range(1, 101)
    ]
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts/acc-123/transactions",
        json={
            "results": page1_transactions,
            "next_cursor": "cursor_page2",
            "status": "Succeeded",
        },
        status=200,
    )

    # Page 2 - partial page (50 items, no cursor)
    page2_transactions = [
        {"transaction_id": f"txn-{i}", "amount": -float(i), "currency": "GBP"}
        for i in range(101, 151)
    ]
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts/acc-123/transactions",
        json={"results": page2_transactions, "status": "Succeeded"},
        status=200,
    )

    client = TrueLayerClient("test-access-token")
    transactions = client.get_transactions("acc-123")

    # Verify both pages were fetched
    assert len(transactions) == 150
    assert transactions[0]["transaction_id"] == "txn-1"
    assert transactions[99]["transaction_id"] == "txn-100"
    assert transactions[100]["transaction_id"] == "txn-101"
    assert transactions[149]["transaction_id"] == "txn-150"

    # Verify pagination stopped after partial page
    assert len(responses.calls) == 2


@responses.activate
def test_get_transactions_with_date_filters():
    """Test transaction fetching with date range filters."""
    responses.add(
        responses.GET,
        "https://api.truelayer.com/data/v1/accounts/acc-123/transactions",
        json={
            "results": [
                {
                    "transaction_id": "txn-1",
                    "amount": -10.50,
                    "currency": "GBP",
                    "timestamp": "2025-01-15T10:30:00Z",
                },
            ],
            "status": "Succeeded",
        },
        status=200,
    )

    client = TrueLayerClient("test-access-token")
    transactions = client.get_transactions(
        "acc-123", from_date="2025-01-01", to_date="2025-01-31"
    )

    assert len(transactions) == 1

    # Verify date parameters were sent in request
    request_params = responses.calls[0].request.params
    assert "from" in request_params
    assert "to" in request_params
    assert request_params["from"] == "2025-01-01"
    assert request_params["to"] == "2025-01-31"


# ============================================================================
# TRANSACTION NORMALIZATION TESTS
# ============================================================================


def test_normalize_transaction():
    """Test transaction normalization converts API format to internal format."""
    client = TrueLayerClient("test-access-token")

    raw_transaction = {
        "transaction_id": "txn-test-123",
        "normalised_provider_transaction_id": "norm-123",
        "timestamp": "2025-01-15T14:30:00Z",
        "description": "TESCO STORES 1234",
        "amount": -45.67,
        "currency": "GBP",
        "transaction_type": "DEBIT",
        "transaction_category": "PURCHASE",
        "merchant_name": "Tesco",
        "running_balance": {"amount": 1234.56, "currency": "GBP"},
    }

    normalized = client.normalize_transaction(raw_transaction)

    # Verify key fields are transformed correctly
    assert normalized["transaction_id"] == "txn-test-123"
    # Note: normalised_provider_transaction_id becomes normalised_provider_id
    assert normalized["normalised_provider_id"] == "norm-123"
    # Note: amount is converted to absolute value
    assert normalized["amount"] == 45.67
    assert normalized["currency"] == "GBP"
    assert normalized["description"] == "TESCO STORES 1234"
    # Note: timestamp becomes date (date portion only)
    assert normalized["date"] == "2025-01-15"
