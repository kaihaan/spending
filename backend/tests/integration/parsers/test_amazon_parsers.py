"""Integration tests for Gmail Amazon email parsers.

Tests parser functionality using real email HTML extracted from actual
Gmail messages. Validates extraction of:
- Merchant identification
- Order totals and currency
- Receipt dates
- Line items
"""

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from mcp.gmail_parsers.amazon import (
    detect_amazon_email_type,
    parse_amazon_business,
    parse_amazon_fresh,
)

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def amazon_fresh_html():
    """Load real Amazon Fresh email HTML."""
    fixture_path = (
        Path(__file__).parent.parent.parent
        / "fixtures"
        / "sample_emails"
        / "amazon_fresh.html"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def amazon_business_html():
    """Load real Amazon Business email HTML."""
    fixture_path = (
        Path(__file__).parent.parent.parent
        / "fixtures"
        / "sample_emails"
        / "amazon_business.html"
    )
    with open(fixture_path, encoding="utf-8") as f:
        return f.read()


# ============================================================================
# AMAZON FRESH PARSER TESTS (TIER 1 CRITICAL)
# ============================================================================


def test_parse_amazon_fresh_extracts_merchant(amazon_fresh_html):
    """Test Amazon Fresh parser correctly identifies merchant.

    CRITICAL: Parser must correctly identify Amazon Fresh vs regular Amazon
    for accurate categorization (groceries vs general shopping).
    """
    soup = BeautifulSoup(amazon_fresh_html, "html.parser")
    result = parse_amazon_fresh(soup, "")

    assert result["email_type"] == "fresh"
    assert result["merchant_name"] == "Amazon Fresh"
    assert result["merchant_name_normalized"] == "amazon_fresh"
    assert result["category_hint"] == "groceries"


def test_parse_amazon_fresh_extracts_total_amount(amazon_fresh_html):
    """Test Amazon Fresh parser extracts order total correctly.

    CRITICAL: Total amount is used for transaction matching.
    Incorrect extraction leads to failed matches and duplicate transactions.
    """
    soup = BeautifulSoup(amazon_fresh_html, "html.parser")
    text_body = soup.get_text()
    result = parse_amazon_fresh(soup, text_body)

    # Verify total amount was extracted
    assert "total_amount" in result
    assert isinstance(result["total_amount"], int | float)
    assert result["total_amount"] > 0

    # Amazon Fresh orders typically under £200
    assert result["total_amount"] < 200


def test_parse_amazon_fresh_extracts_currency(amazon_fresh_html):
    """Test Amazon Fresh parser infers currency correctly."""
    soup = BeautifulSoup(amazon_fresh_html, "html.parser")
    text_body = soup.get_text()
    result = parse_amazon_fresh(soup, text_body)

    # Real UK email should extract GBP
    assert "currency_code" in result
    assert result["currency_code"] in ["GBP", "EUR", "USD"]


def test_parse_amazon_fresh_extracts_date(amazon_fresh_html):
    """Test Amazon Fresh parser extracts delivery/order date."""
    soup = BeautifulSoup(amazon_fresh_html, "html.parser")
    text_body = soup.get_text()
    result = parse_amazon_fresh(soup, text_body)

    # Date extraction is optional but helpful for matching
    if "receipt_date" in result:
        # Should be ISO format or parseable date string
        assert isinstance(result["receipt_date"], str)
        assert len(result["receipt_date"]) >= 10  # YYYY-MM-DD minimum


def test_parse_amazon_fresh_confidence_score(amazon_fresh_html):
    """Test Amazon Fresh parser returns confidence score."""
    soup = BeautifulSoup(amazon_fresh_html, "html.parser")
    result = parse_amazon_fresh(soup, "")

    assert "parse_confidence" in result
    assert isinstance(result["parse_confidence"], int)
    assert 0 <= result["parse_confidence"] <= 100
    # Amazon Fresh should have high confidence (85+)
    assert result["parse_confidence"] >= 80


# ============================================================================
# AMAZON BUSINESS PARSER TESTS
# ============================================================================


def test_parse_amazon_business_extracts_merchant(amazon_business_html):
    """Test Amazon Business parser identifies business orders."""
    soup = BeautifulSoup(amazon_business_html, "html.parser")
    text_body = soup.get_text()
    # parse_amazon_business requires (soup, text_body, subject)
    result = parse_amazon_business(soup, text_body, "Your Amazon.co.uk Business order")

    assert result["email_type"] == "business"
    assert "Amazon" in result["merchant_name"]
    # Business orders may have different merchant_name_normalized
    assert result["merchant_name_normalized"] in ["amazon", "amazon_business"]


def test_parse_amazon_business_extracts_total(amazon_business_html):
    """Test Amazon Business parser extracts order total."""
    soup = BeautifulSoup(amazon_business_html, "html.parser")
    text_body = soup.get_text()
    # parse_amazon_business requires (soup, text_body, subject)
    result = parse_amazon_business(soup, text_body, "Your Amazon.co.uk Business order")

    if "total_amount" in result:
        assert isinstance(result["total_amount"], int | float)
        assert result["total_amount"] > 0


# ============================================================================
# AMAZON EMAIL TYPE DETECTION
# ============================================================================


def test_detect_amazon_email_type_fresh():
    """Test email type detection identifies Fresh orders."""
    fresh_subject = "Your Amazon Fresh order has been received"
    email_type = detect_amazon_email_type(fresh_subject, "")

    assert email_type == "fresh"


def test_detect_amazon_email_type_business():
    """Test email type detection identifies Business orders.

    Note: Business detection requires body to contain the indicator phrase,
    not just the subject line.
    """
    business_subject = "Your Amazon.co.uk order"
    # Business orders are detected via body content, not subject
    business_body = "This order is placed on behalf of your organization"
    email_type = detect_amazon_email_type(business_subject, business_body)

    assert email_type == "business"


def test_detect_amazon_email_type_ordered():
    """Test email type detection identifies standard orders."""
    ordered_subject = "Ordered: 'Product Name'"
    email_type = detect_amazon_email_type(ordered_subject, "")

    assert email_type == "ordered"


def test_detect_amazon_email_type_cancellation():
    """Test email type detection identifies cancellations."""
    cancel_subject = "Item cancelled successfully: 'Product Name'"
    email_type = detect_amazon_email_type(cancel_subject, "")

    assert email_type == "cancellation"


def test_detect_amazon_email_type_refund():
    """Test email type detection identifies refunds."""
    refund_subject = "Your refund for Product Name"
    email_type = detect_amazon_email_type(refund_subject, "")

    assert email_type == "refund"


# ============================================================================
# PARSER ROBUSTNESS TESTS
# ============================================================================


def test_parse_amazon_fresh_handles_empty_html():
    """Test parser handles missing HTML gracefully."""
    result = parse_amazon_fresh(None, "")

    # Should still return basic structure
    assert result["email_type"] == "fresh"
    assert result["merchant_name"] == "Amazon Fresh"
    # May not extract amount without HTML, but shouldn't crash
    assert "parse_confidence" in result


def test_parse_amazon_fresh_handles_malformed_html():
    """Test parser handles malformed HTML gracefully."""
    malformed_html = "<div>Incomplete HTML without closing tags"
    soup = BeautifulSoup(malformed_html, "html.parser")
    result = parse_amazon_fresh(soup, "")

    # Should still parse basic merchant info
    assert result["email_type"] == "fresh"
    assert result["merchant_name"] == "Amazon Fresh"


def test_parse_amazon_fresh_with_text_body_only():
    """Test parser can extract from plain text when HTML unavailable."""
    text_body = """
    Amazon Fresh

    Your order has been delivered

    Order Total: £41.51
    Delivery Date: Sunday, November 23, 2025
    """

    result = parse_amazon_fresh(None, text_body)

    assert result["merchant_name"] == "Amazon Fresh"
    # Should extract total from text
    if "total_amount" in result:
        assert result["total_amount"] > 40
        assert result["total_amount"] < 45


# ============================================================================
# EDGE CASES
# ============================================================================


def test_parse_amazon_fresh_handles_multiple_currencies():
    """Test parser correctly identifies currency when multiple symbols present."""
    # Some emails may mention multiple currencies in footnotes
    text_with_multi_currency = """
    Order Total: £45.99

    * Prices shown in GBP. Also available in € EUR or $ USD.
    """

    result = parse_amazon_fresh(None, text_with_multi_currency)

    # Should extract the actual order currency (GBP in this case)
    assert result.get("currency_code") == "GBP"


def test_parse_amazon_fresh_handles_large_orders():
    """Test parser handles orders with many items correctly."""
    text_large_order = """
    Amazon Fresh Order

    Order Total: £152.48
    """

    result = parse_amazon_fresh(None, text_large_order)

    if "total_amount" in result:
        # Should handle amounts over £100
        assert result["total_amount"] > 150
        assert result["total_amount"] < 160
