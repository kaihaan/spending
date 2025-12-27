"""
Gmail Vendor-Specific Receipt Parsers

Parses receipt emails from major vendors using their known email formats.
These parsers are more reliable than generic pattern extraction because
they target vendor-specific HTML structures.
"""

import re
from collections.abc import Callable
from datetime import datetime

from bs4 import BeautifulSoup

# Type alias for parser functions
VendorParser = Callable[[str, str, str], dict | None]


# Registry of vendor domain -> parser function
VENDOR_PARSERS: dict[str, VendorParser] = {}


def register_vendor(domains: list[str]):
    """Decorator to register a parser for specific domains."""

    def decorator(func: VendorParser):
        for domain in domains:
            VENDOR_PARSERS[domain] = func
        return func

    return decorator


def get_vendor_parser(sender_domain: str) -> VendorParser | None:
    """
    Get vendor-specific parser for a domain.

    Args:
        sender_domain: Email sender domain (e.g., 'amazon.co.uk')

    Returns:
        Parser function or None if no specific parser exists
    """
    if not sender_domain:
        return None

    sender_domain = sender_domain.lower()

    # Check exact match first
    if sender_domain in VENDOR_PARSERS:
        return VENDOR_PARSERS[sender_domain]

    # Check partial match (e.g., 'email.amazon.co.uk' matches 'amazon.co.uk')
    for domain, parser in VENDOR_PARSERS.items():
        if domain in sender_domain:
            return parser

    return None


def parse_amount(text: str) -> float | None:
    """Extract numeric amount from text like '£12.34', '12.34 GBP', or '€ 63,75' (European format)."""
    if not text:
        return None

    # Remove currency symbols and whitespace
    cleaned = re.sub(r"[£$€¥\s]", "", text)

    # Handle European format: comma as decimal separator (e.g., "63,75" -> "63.75")
    # Pattern: comma followed by exactly 2 digits at end of number
    if re.match(r"^\d+,\d{2}$", cleaned):
        cleaned = cleaned.replace(",", ".")
    else:
        # Otherwise remove commas (thousands separators)
        cleaned = cleaned.replace(",", "")

    # Extract number
    match = re.search(r"(\d+\.?\d*)", cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def parse_date_text(text: str) -> str | None:
    """Parse various date formats to YYYY-MM-DD."""
    if not text:
        return None

    # Month name patterns (full and abbreviated)
    month_pattern = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"

    # Common patterns
    patterns = [
        # 15 January 2024 or 15 Jan 2024
        (rf"(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})", "DMY_FULL"),
        # January 15, 2024 or Jan 15, 2024
        (rf"({month_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})", "MDY_FULL"),
        # 15/01/2024 or 15-01-2024
        (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", "DMY"),
        # 2024-01-15
        (r"(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})", "YMD"),
    ]

    # Map both full and abbreviated month names to numbers
    months = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    for pattern, fmt in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if fmt == "DMY_FULL":
                    day = int(match.group(1))
                    month = months[match.group(2).lower()]
                    year = int(match.group(3))
                elif fmt == "MDY_FULL":
                    month = months[match.group(1).lower()]
                    day = int(match.group(2))
                    year = int(match.group(3))
                elif fmt == "DMY":
                    day = int(match.group(1))
                    month = int(match.group(2))
                    year = int(match.group(3))
                elif fmt == "YMD":
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                else:
                    continue

                return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, KeyError):
                continue

    return None


# ============================================================================
# AMAZON PARSER
# ============================================================================


def detect_amazon_email_type(subject: str, text_body: str) -> str:
    """
    Detect the type of Amazon email for routing to specialized parser.

    Amazon sends different email types that require different parsing strategies:
    - ordered: "Ordered: 'Item Name...'" notification emails
    - order: Regular purchase confirmations ("Your Amazon.co.uk order.")
    - cancellation: Order item cancelled
    - refund: Refund issued
    - fresh: Amazon Fresh grocery orders
    - business: Amazon Business orders
    - shipment: Shipping/delivery notifications

    Args:
        subject: Email subject line
        text_body: Plain text body

    Returns:
        Email type string: 'ordered', 'order', 'cancellation', 'refund', 'fresh', 'business', 'shipment'
    """
    subject_lower = subject.lower()

    # "Ordered:" notification emails - distinct from regular order confirmations
    if subject_lower.startswith("ordered:"):
        return "ordered"

    if "cancelled" in subject_lower:
        return "cancellation"
    if "refund" in subject_lower:
        return "refund"
    if "fresh" in subject_lower:
        return "fresh"

    # Amazon Business detection (body indicator only)
    # NOTE: Subject "Your Amazon.co.uk order." is NOT unique to Business - must check body
    if text_body and "order is placed on behalf of" in text_body.lower():
        return "business"

    if any(
        x in subject_lower
        for x in ["shipped", "dispatched", "out for delivery", "delivered"]
    ):
        return "shipment"
    return "order"


def parse_amazon_cancellation(soup, subject: str) -> dict:
    """
    Parse Amazon order cancellation email.

    Extracts item name from subject line (format: 'Item cancelled successfully: "ItemName..."')

    Args:
        soup: BeautifulSoup parsed HTML (may be None)
        subject: Email subject line

    Returns:
        Dict with cancellation-specific fields
    """
    # Extract item name from subject: 'Item cancelled successfully: "WoodWick..."'
    item_name = None
    item_match = re.search(
        r'cancelled successfully[:\s]*["\']?(.+?)["\']?\s*$', subject, re.IGNORECASE
    )
    if item_match:
        item_name = item_match.group(1).strip()
        # Clean up truncation markers
        item_name = re.sub(r"\.{2,}$", "", item_name).strip()

    return {
        "email_type": "cancellation",
        "is_cancellation": True,
        "merchant_name": "Amazon",
        "merchant_name_normalized": "amazon",
        "item_name": item_name,
        "parse_confidence": 85 if item_name else 70,
    }


def parse_amazon_refund(soup, subject: str, text_body: str) -> dict:
    """
    Parse Amazon refund email.

    Extracts:
    - Item name from subject (format: 'Your refund for ITEMNAME...')
    - Refund amount from body (e.g., '£307.19 will be credited')

    Args:
        soup: BeautifulSoup parsed HTML (may be None)
        subject: Email subject line
        text_body: Plain text body

    Returns:
        Dict with refund-specific fields
    """
    # Extract item name from subject: "Your refund for TERRAMASTER F4-424..."
    item_name = None
    item_match = re.search(r"refund for\s+(.+?)\.{0,3}$", subject, re.IGNORECASE)
    if item_match:
        item_name = item_match.group(1).strip()

    # Extract refund amount from body
    refund_amount = None
    currency_code = None
    text_to_search = text_body or ""

    refund_patterns = [
        (r"[£]([0-9,]+\.?\d*)\s*(?:will be credited|refunded|to your)", "GBP"),
        (r"[$]([0-9,]+\.?\d*)\s*(?:will be credited|refunded|to your)", "USD"),
        (r"[€]([0-9,]+\.?\d*)\s*(?:will be credited|refunded|to your)", "EUR"),
        (r"Total refund\s*[£$€]?\s*([0-9,]+\.?\d*)", None),
        (r"Refund subtotal\s*[£$€]?\s*([0-9,]+\.?\d*)", None),
    ]

    for pattern, currency in refund_patterns:
        match = re.search(pattern, text_to_search, re.IGNORECASE)
        if match:
            refund_amount = parse_amount(match.group(1))
            if currency:
                currency_code = currency
            break

    # Infer currency from currency symbols in text if not already found
    if not currency_code:
        if "£" in text_to_search:
            currency_code = "GBP"
        elif "€" in text_to_search:
            currency_code = "EUR"
        elif "$" in text_to_search:
            currency_code = "USD"

    return {
        "email_type": "refund",
        "is_refund": True,
        "merchant_name": "Amazon",
        "merchant_name_normalized": "amazon",
        "item_name": item_name,
        "refund_amount": refund_amount,
        "total_amount": refund_amount,  # For consistency with order parsing
        "currency_code": currency_code,
        "parse_confidence": 90 if refund_amount else 75,
    }


def parse_amazon_fresh(soup, text_body: str) -> dict:
    """
    Parse Amazon Fresh grocery order email.

    Amazon Fresh orders have different structure than regular Amazon orders.
    They're grocery deliveries with different merchant identification.

    Args:
        soup: BeautifulSoup parsed HTML (may be None)
        text_body: Plain text body

    Returns:
        Dict with Fresh-specific fields
    """
    result = {
        "email_type": "fresh",
        "merchant_name": "Amazon Fresh",
        "merchant_name_normalized": "amazon_fresh",
        "category_hint": "groceries",
        "parse_confidence": 85,
    }

    # Try to extract amount from HTML or text
    text = ""
    if soup:
        text = soup.get_text()
    elif text_body:
        text = text_body

    if text:
        # Amazon Fresh order total patterns
        total_patterns = [
            r"Order\s+Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
            r"Grand\s+Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
            r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Your\s+order\s+total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Infer currency
        if "£" in text:
            result["currency_code"] = "GBP"
        elif "€" in text:
            result["currency_code"] = "EUR"
        elif "$" in text:
            result["currency_code"] = "USD"

        # Extract date - Fresh orders have delivery date
        date_patterns = [
            r"Delivery\s+date[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\d{1,2}\s+\w+\s+\d{4})",
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2}(?:,\s+\d{4})?)",
            r"(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                parsed = parse_date_text(match.group(1))
                if parsed:
                    result["receipt_date"] = parsed
                    break

    return result


def parse_amazon_business(soup, text_body: str, subject: str) -> dict:
    """
    Parse Amazon Business order confirmation email.

    Amazon Business orders have similar structure to regular orders but:
    - Contain "This order is placed on behalf of" indicator
    - May have different order number format
    - Associated with business account

    Args:
        soup: BeautifulSoup parsed HTML (may be None)
        text_body: Plain text body
        subject: Email subject line

    Returns:
        Dict with business order fields
    """
    result = {
        "email_type": "business",
        "merchant_name": "Amazon Business",
        "merchant_name_normalized": "amazon_business",
        "is_business_order": True,
        "parse_confidence": 90,
    }

    if not soup:
        return result

    # Reuse order parsing logic for amounts/dates
    text = soup.get_text()

    # Extract total amount (same patterns as regular orders)
    total_patterns = [
        r"Order Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
        r"Grand Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
        r"Total for this order[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Currency detection
    if "£" in text:
        result["currency_code"] = "GBP"
    elif "€" in text:
        result["currency_code"] = "EUR"
    elif "$" in text:
        result["currency_code"] = "USD"

    # Extract date
    date_patterns = [
        # Order placement dates
        (r"Order\s+placed[:\s]+(\d{1,2}\s+\w+\s+\d{4})", None),
        (r"Order\s+placed[:\s]+(\w+\s+\d{1,2},?\s+\d{4})", None),
        # Arriving dates (with optional weekday)
        (r"Arriving[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2},?\s+\d{4})", None),
        (r"Arriving[:\s]+(?:\w+day,?\s+)?(\d{1,2}\s+\w+\s+\d{4})", None),
        (r"Arriving[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2})", None),
        # Generic patterns
        (
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
            None,
        ),
        (
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})",
            None,
        ),
    ]
    for pattern, _ in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parsed = parse_date_text(match.group(1))
            if parsed:
                result["receipt_date"] = parsed
                break

    # Extract line items
    line_items = extract_amazon_line_items(soup, text)
    if line_items:
        result["line_items"] = line_items

    return result


def parse_amazon_order(soup, text_body: str, subject: str) -> dict:
    """
    Parse standard Amazon order confirmation email.

    This is the original parsing logic, extracted into a separate function
    for use in the type-routed main parser.

    Args:
        soup: BeautifulSoup parsed HTML
        text_body: Plain text body
        subject: Email subject line

    Returns:
        Dict with order-specific fields
    """
    result = {
        "email_type": "order",
        "merchant_name": "Amazon",
        "merchant_name_normalized": "amazon",
        "parse_confidence": 85,
    }

    if not soup:
        return result

    # Find total amount - Amazon uses various table structures
    total_patterns = [
        r"Order Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
        r"Grand Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
        r"Total for this order[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
    ]

    text = soup.get_text()
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Infer currency from text
    if "£" in text:
        result["currency_code"] = "GBP"
    elif "€" in text:
        result["currency_code"] = "EUR"
    elif "$" in text:
        result["currency_code"] = "USD"

    # Try to find date - Amazon uses many formats
    date_patterns = [
        # Explicit order/dispatch dates with full year
        (r"Order\s+placed[:\s]+(\d{1,2}\s+\w+\s+\d{4})", None),
        (r"Order\s+placed[:\s]+(\w+\s+\d{1,2},?\s+\d{4})", None),
        (r"Ordered\s+on[:\s]+(\d{1,2}\s+\w+\s+\d{4})", None),
        (r"Ordered\s+on[:\s]+(\w+\s+\d{1,2},?\s+\d{4})", None),
        (r"Dispatched\s+on[:\s]+(\d{1,2}\s+\w+\s+\d{4})", None),
        (r"Dispatched[:\s]+(\d{1,2}\s+\w+\s+\d{4})", None),
        (r"Delivered[:\s]+(\d{1,2}\s+\w+\s+\d{4})", None),
        (r"Delivered\s+on[:\s]+(\d{1,2}\s+\w+\s+\d{4})", None),
        # Arriving dates - common in order confirmations (with optional weekday)
        (
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2},?\s+\d{4})",
            None,
        ),  # "Arriving: Saturday, June 14, 2025"
        (
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\d{1,2}\s+\w+\s+\d{4})",
            None,
        ),  # "Arriving: Saturday 14 June 2025"
        (
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2})",
            None,
        ),  # "Arriving: Saturday, June 14" (no year)
        # Generic date patterns
        (
            r"(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})",
            None,
        ),
        (
            r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})",
            None,
        ),
    ]

    for pattern, _ in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parsed = parse_date_text(match.group(1))
            if parsed:
                result["receipt_date"] = parsed
                break

    # Fallback: try subject line for date
    if not result.get("receipt_date"):
        subject_date = parse_date_text(subject)
        if subject_date:
            result["receipt_date"] = subject_date

    # Extract structured line items with names and prices
    line_items = extract_amazon_line_items(soup, text)
    if line_items:
        result["line_items"] = line_items

    return result


def parse_amazon_ordered(soup, text_body: str, subject: str) -> dict:
    """
    Parse Amazon "Ordered:" notification emails.

    Format: Subject starts with "Ordered: 'Item Name...'" or "Ordered: 2 'Item Name...'"
    These emails contain order confirmation with:
    - Item details in subject and body
    - Order total in body (format: "Total\n279.97 GBP")
    - Order ID (format: Order #\n206-7081774-1099517)

    Args:
        soup: BeautifulSoup parsed HTML
        text_body: Plain text body
        subject: Email subject line

    Returns:
        Dict with order-specific fields
    """
    result = {
        "email_type": "ordered",
        "merchant_name": "Amazon",
        "merchant_name_normalized": "amazon",
        "parse_confidence": 90,
    }

    # Get text to search - prefer text_body, fall back to soup
    text = text_body or ""
    if not text and soup:
        text = soup.get_text()

    # Extract order ID - format: "Order #\n206-7081774-1099517"
    order_match = re.search(r"Order\s*#\s*\n?\s*(\d{3}-\d{7}-\d{7})", text)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract total amount - format: "Total\n279.97 GBP" or "Total\n10.6 GBP"
    total_match = re.search(r"Total\s*\n\s*([0-9,.]+)\s*(GBP|EUR|USD)", text)
    if total_match:
        result["total_amount"] = parse_amount(total_match.group(1))
        result["currency_code"] = total_match.group(2)
    else:
        # Fallback pattern for inline format
        total_match2 = re.search(r"Total[:\s]+([0-9,.]+)\s*(GBP|EUR|USD)", text)
        if total_match2:
            result["total_amount"] = parse_amount(total_match2.group(1))
            result["currency_code"] = total_match2.group(2)

    # Extract line items - format: "* Item Name\n  Quantity: 1\n  279.97 GBP"
    # Note: Amazon emails may use \r\n or \r line endings
    line_items = []
    # Normalize line endings to \n for consistent matching
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Use ^* anchor with MULTILINE to match line-starting asterisks only (not asterisks within product names)
    # Use .+? non-greedy match to capture full product name including embedded asterisks (e.g., "3x stronger*")
    item_pattern = r"^\*\s*(.+?)\s+Quantity:\s*(\d+)\s+([0-9,.]+)\s*(GBP|EUR|USD)"
    for match in re.finditer(item_pattern, normalized_text, re.MULTILINE):
        item_name = match.group(1).strip()
        quantity = int(match.group(2))
        unit_price = parse_amount(match.group(3))
        currency = match.group(4)
        item = {
            "name": item_name,
            "quantity": quantity,
            "unit_price": unit_price,
            "currency": currency,
        }
        # Extract and add brand
        brand = extract_amazon_brand(item_name)
        if brand:
            item["brand"] = brand
        line_items.append(item)

    if line_items:
        result["line_items"] = line_items
    else:
        # Fallback: Extract item name from subject
        # Format: "Ordered: 'Item Name...'" or "Ordered: 2 'Item Name...'"
        # Handle both straight quotes (') and curly quotes (\u2018, \u2019)
        item_match = re.search(
            r"Ordered:\s*(?:\d+\s*)?['\u2018]([^'\u2019]+)['\u2019]", subject
        )
        if item_match:
            item_name = item_match.group(1).strip()
            item = {"name": item_name}
            brand = extract_amazon_brand(item_name)
            if brand:
                item["brand"] = brand
            result["line_items"] = [item]
        else:
            # Additional fallback for straight quotes
            item_match2 = re.search(r"Ordered:\s*(?:\d+\s*)?'([^']+)'", subject)
            if item_match2:
                item_name = item_match2.group(1).strip()
                item = {"name": item_name}
                brand = extract_amazon_brand(item_name)
                if brand:
                    item["brand"] = brand
                result["line_items"] = [item]

    # Try to extract date
    date_patterns = [
        # Arriving dates with full month/day (most common in "Ordered:" emails)
        (
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2},?\s+\d{4})",
            None,
        ),  # "Arriving: Saturday, June 14, 2025"
        (
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\d{1,2}\s+\w+\s+\d{4})",
            None,
        ),  # "Arriving: Saturday 14 June 2025"
        (
            r"Arriving[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2})",
            None,
        ),  # "Arriving: Saturday, June 14" (no year)
        # Delivery dates
        (r"Delivery[:\s]+(?:\w+day,?\s+)?(\w+\s+\d{1,2},?\s+\d{4})", None),
        (r"Delivery[:\s]+(?:\w+day,?\s+)?(\d{1,2}\s+\w+\s+\d{4})", None),
        # Generic full date patterns
        (
            r"(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4})",
            None,
        ),
        (
            r"((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4})",
            None,
        ),
    ]

    for pattern, _ in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            parsed = parse_date_text(match.group(1))
            if parsed:
                result["receipt_date"] = parsed
                break

    return result


@register_vendor(["amazon.co.uk", "amazon.com", "amazon.de", "amazon.fr"])
def parse_amazon_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Amazon emails - orders, cancellations, refunds, Fresh, shipments.

    Routes to specialized parsers based on email type detected from subject:
    - ordered: "Ordered: 'Item...'" notification emails
    - order: Standard purchase confirmations ("Your Amazon.co.uk order.")
    - cancellation: Item cancelled notifications
    - refund: Refund issued notifications
    - fresh: Amazon Fresh grocery orders
    - business: Amazon Business orders
    - shipment: Shipping/delivery updates (treated as orders)

    All types extract order ID where available and return consistent structure.
    """
    # Detect email type and route to specialized parser
    email_type = detect_amazon_email_type(subject, text_body or "")
    soup = BeautifulSoup(html_body, "html.parser") if html_body else None

    # Route to specialized parser based on type
    if email_type == "ordered":
        result = parse_amazon_ordered(soup, text_body, subject)
    elif email_type == "cancellation":
        result = parse_amazon_cancellation(soup, subject)
    elif email_type == "refund":
        result = parse_amazon_refund(soup, subject, text_body)
    elif email_type == "fresh":
        result = parse_amazon_fresh(soup, text_body)
    elif email_type == "business":
        result = parse_amazon_business(soup, text_body, subject)
    else:
        # 'order' and 'shipment' use the standard order parser
        result = parse_amazon_order(soup, text_body, subject)

    # Add common fields
    result["parse_method"] = "vendor_amazon"

    # Extract order ID (common to all Amazon email types)
    # Note: parse_amazon_ordered already extracts order_id, but this is a fallback
    if not result.get("order_id"):
        order_pattern = r"(\d{3}-\d{7}-\d{7})"
        order_match = re.search(order_pattern, subject) or re.search(
            order_pattern, text_body or ""
        )
        if order_match:
            result["order_id"] = order_match.group(1)

    # For cancellations, refunds, fresh, business, and ordered - return if we have useful data
    if email_type in ("cancellation", "refund", "fresh", "business", "ordered"):
        return result

    # For orders/shipments, return if we have any useful data
    # Even partial data (merchant info) is useful for matching
    if result.get("merchant_name_normalized"):
        return result

    return None


def extract_amazon_brand(product_name: str) -> str | None:
    """
    Extract brand name from Amazon product name.

    Amazon product names typically follow pattern: "[Brand] [Product Description]"
    Examples:
    - "WoodWick Scented Candle..." → "WoodWick"
    - "Sure Men Maximum Protection..." → "Sure Men"
    - "Apple AirPods Pro..." → "Apple"
    - "tesamoll Thermo Cover..." → "tesamoll" (lowercase brand)

    Args:
        product_name: Full product name from Amazon

    Returns:
        Brand name or None
    """
    if not product_name or len(product_name) < 3:
        return None

    # Strategy 1: Extract first 1-3 capitalized words (most common)
    # Stop at lowercase word, punctuation, or numbers
    brand_match = re.match(
        r"^([A-Z][A-Za-z0-9]*(?:\s+[A-Z][A-Za-z0-9]*){0,2})", product_name
    )
    if brand_match:
        brand = brand_match.group(1).strip()
        # Validate: brand should be 2-30 chars
        if 2 <= len(brand) <= 30:
            return brand

    # Strategy 2: Fallback for lowercase brands (e.g., "tesamoll", "bananair")
    # Extract first word if it's meaningful (>= 3 chars, not a number)
    first_word = product_name.split()[0] if product_name.split() else None
    if first_word and len(first_word) >= 3 and not first_word.isdigit():
        # Exclude common non-brand prefixes
        if not first_word.lower().startswith(("pack", "set", "bundle", "qty")):
            return first_word

    return None


def extract_product_brand(product_name: str) -> str | None:
    """
    Generic brand extraction for retail products (eBay, Uniqlo, etc.).

    Handles multiple formats:
    - Capitalized brand: "Sony WH-1000XM4..." -> "Sony"
    - Lowercase brand: "bananair sun lounger..." -> "bananair"
    - Multi-word brand: "Dell UltraSharp 27..." -> "Dell UltraSharp"
    - Delimiter-based: "designacable.com - USB Cable" -> "designacable.com"

    Args:
        product_name: Product name string

    Returns:
        Brand name or None
    """
    if not product_name or len(product_name) < 2:
        return None

    # Strategy 1: Try capitalized brand first (most common)
    brand_match = re.match(
        r"^([A-Z][A-Za-z0-9&\'\.]*(?:\s+[A-Z][A-Za-z0-9&\'\.]*){0,2})", product_name
    )
    if brand_match:
        brand = brand_match.group(1).strip()
        if 2 <= len(brand) <= 40:
            return brand

    # Strategy 2: Delimiter-based (dash, comma, colon, parenthesis)
    delim_match = re.match(r"^([^-,:\(]+?)[\s]*[\-,:\(]", product_name)
    if delim_match:
        brand = delim_match.group(1).strip()
        # Exclude quantity prefixes
        if brand and not brand.lower().startswith(
            ("pack of", "set of", "bundle", "x ", "qty")
        ):
            if 2 <= len(brand) <= 40:
                return brand

    # Strategy 3: First word if meaningful (>= 3 chars, not a number)
    first_word = product_name.split()[0] if product_name.split() else None
    if first_word and len(first_word) >= 3 and not first_word.isdigit():
        return first_word

    return None


def extract_amazon_line_items(soup: BeautifulSoup, text: str) -> list:
    """
    Extract structured line items from Amazon email HTML.

    Attempts to parse product names, quantities, and prices from various
    Amazon email formats (order confirmation, shipment, digital).

    Args:
        soup: BeautifulSoup parsed HTML
        text: Plain text version for fallback

    Returns:
        List of structured item dicts with name, quantity, price, category_hint
    """
    items = []
    seen_names = set()

    # Strategy 1: Look for table rows with product info
    # Amazon often uses tables with product name in one cell, price in another
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                # Try to identify product name and price cells
                item_data = extract_item_from_row(cells)
                if item_data and item_data["name"] not in seen_names:
                    seen_names.add(item_data["name"])
                    items.append(item_data)

    # Strategy 2: Look for product links with nearby prices
    for link in soup.find_all("a", href=re.compile(r"/dp/|/gp/product/")):
        link_text = link.get_text(strip=True)
        if link_text and 10 < len(link_text) < 200:
            # Look for price in parent or nearby siblings
            parent = link.find_parent(["td", "div", "tr"])
            price = None
            if parent:
                price_match = re.search(r"[£$€]\s*([0-9,]+\.?\d*)", parent.get_text())
                if price_match:
                    price = parse_amount(price_match.group(1))

            if link_text not in seen_names:
                seen_names.add(link_text)
                cleaned_name = clean_product_name(link_text)
                item = {
                    "name": cleaned_name,
                    "description": infer_product_description(link_text),
                    "category_hint": infer_amazon_category(link_text),
                    "quantity": 1,
                    "price": price,
                }
                # Extract and add brand
                brand = extract_amazon_brand(cleaned_name)
                if brand:
                    item["brand"] = brand
                items.append(item)

    # Strategy 3: Fallback - find text that looks like product names
    if not items:
        # Look for elements with substantial text that aren't navigation/footer
        for elem in soup.find_all(["td", "span", "div"]):
            elem_text = elem.get_text(strip=True)
            # Product names are typically 10-150 chars, no prices or order IDs
            if (
                10 < len(elem_text) < 150
                and not re.search(
                    r"[£$€]|\d{3}-\d{7}|order|total|subtotal|shipping|tax",
                    elem_text.lower(),
                )
                and elem_text not in seen_names
            ):
                # Check it's likely a product (has uppercase, reasonable structure)
                if re.search(r"[A-Z]", elem_text) and not elem_text.isupper():
                    seen_names.add(elem_text)
                    cleaned_name = clean_product_name(elem_text)
                    item = {
                        "name": cleaned_name,
                        "description": infer_product_description(elem_text),
                        "category_hint": infer_amazon_category(elem_text),
                        "quantity": 1,
                        "price": None,
                    }
                    # Extract and add brand
                    brand = extract_amazon_brand(cleaned_name)
                    if brand:
                        item["brand"] = brand
                    items.append(item)

    # Limit to 10 items max
    return items[:10]


def extract_item_from_row(cells: list) -> dict | None:
    """
    Extract item data from a table row's cells.

    Args:
        cells: List of BeautifulSoup elements (td/th cells)

    Returns:
        Item dict or None if not a product row
    """
    name = None
    price = None
    quantity = 1

    for cell in cells:
        cell_text = cell.get_text(strip=True)

        # Skip empty or very short cells
        if len(cell_text) < 3:
            continue

        # Check for price pattern
        price_match = re.search(r"[£$€]\s*([0-9,]+\.?\d*)", cell_text)
        if price_match and not name:
            # Price cell - but might also contain product info
            price = parse_amount(price_match.group(1))
            continue

        # Check for quantity pattern (e.g., "Qty: 2" or "x2")
        qty_match = re.search(
            r"(?:qty|quantity)[:\s]*(\d+)|x(\d+)", cell_text, re.IGNORECASE
        )
        if qty_match:
            quantity = int(qty_match.group(1) or qty_match.group(2))
            continue

        # If it looks like a product name (reasonable length, not just numbers)
        if 10 < len(cell_text) < 200 and re.search(r"[a-zA-Z]{3,}", cell_text):
            # Avoid common non-product text
            if not re.search(
                r"order|total|subtotal|shipping|tax|delivery|amazon", cell_text.lower()
            ):
                name = cell_text

    if name:
        cleaned_name = clean_product_name(name)
        item = {
            "name": cleaned_name,
            "description": infer_product_description(name),
            "category_hint": infer_amazon_category(name),
            "quantity": quantity,
            "price": price,
        }
        # Extract and add brand
        brand = extract_amazon_brand(cleaned_name)
        if brand:
            item["brand"] = brand
        return item

    return None


def clean_product_name(name: str) -> str:
    """
    Clean up product name by removing noise.

    Args:
        name: Raw product name from email

    Returns:
        Cleaned product name
    """
    if not name:
        return name

    # Remove common prefixes/suffixes
    cleaned = re.sub(r"^(Buy|Shop|View|See)\s+", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\s+(Buy now|Shop now|View item)$", "", cleaned, flags=re.IGNORECASE
    )

    # Remove excessive whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Truncate very long names
    if len(cleaned) > 150:
        cleaned = cleaned[:147] + "..."

    return cleaned


def infer_product_description(name: str) -> str | None:
    """
    Infer a brief description of what the product IS based on its name.

    Args:
        name: Product name

    Returns:
        Brief description or None
    """
    if not name:
        return None

    name_lower = name.lower()

    # Common product type mappings
    type_patterns = [
        (r"headphone|earphone|earbud|airpod", "audio headphones/earbuds"),
        (r"cable|charger|adapter|usb", "charging/connectivity accessory"),
        (r"case|cover|screen protector", "protective case/cover"),
        (r"battery|power bank", "portable power/battery"),
        (r"book|kindle|paperback|hardcover", "book"),
        (r"shirt|dress|pants|jeans|jacket|coat", "clothing item"),
        (r"toy|lego|game|puzzle", "toy/game"),
        (r"vitamin|supplement|medicine", "health supplement"),
        (r"food|snack|chocolate|coffee|tea", "food/beverage"),
        (r"cleaning|soap|detergent", "cleaning product"),
        (r"phone|tablet|laptop|computer", "electronic device"),
        (r"watch|clock", "timepiece"),
        (r"light|lamp|bulb", "lighting"),
        (r"kitchen|cooking|pan|pot", "kitchen item"),
    ]

    for pattern, description in type_patterns:
        if re.search(pattern, name_lower):
            return description

    return None


def infer_amazon_category(name: str) -> str:
    """
    Infer category hint from product name for enrichment.

    Args:
        name: Product name

    Returns:
        Category hint string
    """
    if not name:
        return "other"

    name_lower = name.lower()

    category_patterns = [
        (
            r"headphone|speaker|audio|earphone|earbud|airpod|cable|charger|phone|tablet|laptop|computer|usb|hdmi|adapter|battery|power bank",
            "electronics",
        ),
        (r"book|kindle|paperback|hardcover|novel|magazine", "entertainment"),
        (
            r"shirt|dress|pants|jeans|jacket|coat|shoe|sock|underwear|clothing",
            "clothing",
        ),
        (
            r"food|snack|chocolate|coffee|tea|grocery|organic|vitamin|supplement",
            "groceries",
        ),
        (r"toy|lego|game|puzzle|doll|action figure", "entertainment"),
        (r"cleaning|soap|detergent|shampoo|toothpaste|tissue", "home"),
        (r"medicine|pharmacy|health|first aid|bandage", "health"),
        (r"kitchen|cooking|pan|pot|utensil|plate|bowl|cup", "home"),
        (r"garden|plant|seed|outdoor|patio", "home"),
        (r"pet|dog|cat|fish|bird", "other"),
        (r"baby|diaper|infant|toddler", "other"),
        (r"office|stationery|pen|paper|desk", "other"),
    ]

    for pattern, category in category_patterns:
        if re.search(pattern, name_lower):
            return category

    return "other"


# ============================================================================
# APPLE PARSER
# ============================================================================


def decode_quoted_printable_amount(text: str) -> str:
    """
    Decode quoted-printable encoded currency amounts.

    Apple emails use quoted-printable encoding where:
    - =C2=A3 is the £ symbol (UTF-8 encoded)
    - =E2=80=A2 is the bullet point (•)

    Args:
        text: Potentially encoded text

    Returns:
        Decoded text with proper currency symbols
    """
    if not text:
        return text

    # Common quoted-printable patterns in Apple emails
    replacements = [
        ("=C2=A3", "£"),  # GBP symbol
        ("=C2=A0", " "),  # Non-breaking space
        ("=E2=80=A2", "•"),  # Bullet point
        ("=\n", ""),  # Line continuation
    ]

    result = text
    for encoded, decoded in replacements:
        result = result.replace(encoded, decoded)

    return result


@register_vendor(["apple.com", "itunes.com", "email.apple.com"])
def parse_apple_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Apple App Store and iTunes invoice/receipt emails.

    Supports two email formats:
    1. New format (2024+): Uses CSS classes like custom-18w16cf, custom-gzadzy, etc.
    2. Old format (pre-2024): Table-based layout with inline styles

    Subject patterns:
    - "Your invoice from Apple."
    - "Your receipt from Apple."
    """
    result = {
        "merchant_name": "Apple",
        "merchant_name_normalized": "apple",
        "parse_method": "vendor_apple",
        "parse_confidence": 90,
        "category_hint": "subscription",
        "currency_code": "GBP",  # Default for UK invoices
    }

    if not html_body:
        return None

    # Decode quoted-printable content first
    decoded_html = decode_quoted_printable_amount(html_body)
    soup = BeautifulSoup(decoded_html, "html.parser")

    # Detect format: new format has custom-* classes, old format has aapl-desktop-tbl
    is_new_format = (
        soup.find("p", class_=lambda x: x and x.startswith("custom-")) is not None
    )

    if is_new_format:
        # === NEW FORMAT (2024+) with CSS classes ===
        result = _parse_apple_new_format(soup, result)
    else:
        # === OLD FORMAT (pre-2024) with table-based layout ===
        result = _parse_apple_old_format(soup, decoded_html, result)

    # Build line items
    subscription_details = result.get("subscription_details", [])
    line_items = []
    if result.get("product_name"):
        item = {
            "name": result["product_name"],
            "description": result.get(
                "subscription_name", infer_apple_description(result["product_name"])
            ),
            "category_hint": infer_apple_category(result["product_name"]),
            "quantity": 1,
            "price": result.get("total_amount"),
            "brand": result[
                "product_name"
            ],  # App/service name (normalized from app_name)
            "app_name": result["product_name"],  # Kept for backward compatibility
        }
        # Add renewal info if available
        for detail in subscription_details:
            if "renews" in detail.lower():
                item["renewal_date"] = detail
                break
        line_items.append(item)

    if line_items:
        result["line_items"] = line_items

    # Validate - must have amount or order ID
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


def _parse_apple_new_format(soup: BeautifulSoup, result: dict) -> dict:
    """
    Parse Apple's new email format (2024+) with CSS classes.

    CSS classes used:
    - custom-18w16cf: Date
    - custom-f41j3e: Field labels (Sequence, Order ID, Document, Apple Account)
    - custom-zresjj: Field values
    - custom-gzadzy: Product/App name (bold)
    - custom-wogfc8: Subscription name and details
    - custom-137u684: Item amount (bold)
    - custom-15zbox7: Payment method
    - custom-1s7arqf: Subtotal amounts
    """
    # Extract date (in custom-18w16cf class)
    date_elem = soup.find("p", class_="custom-18w16cf")
    if date_elem:
        date_text = date_elem.get_text(strip=True)
        parsed_date = parse_date_text(date_text)
        if parsed_date:
            result["receipt_date"] = parsed_date

    # Extract Order ID
    order_id = extract_apple_field_value(soup, "Order ID")
    if order_id:
        result["order_id"] = order_id

    # Extract Document number (Apple's invoice number)
    document = extract_apple_field_value(soup, "Document")
    if document:
        result["document_id"] = document

    # Extract Sequence number
    sequence = extract_apple_field_value(soup, "Sequence")
    if sequence:
        result["sequence_id"] = sequence

    # Extract product/app name (in custom-gzadzy class - bold product name)
    product_elem = soup.find("p", class_="custom-gzadzy")
    if product_elem:
        result["product_name"] = product_elem.get_text(strip=True)

    # Extract subscription details (in custom-wogfc8 class)
    subscription_elems = soup.find_all("p", class_="custom-wogfc8")
    subscription_details = []
    for elem in subscription_elems:
        text = elem.get_text(strip=True)
        if text and len(text) > 2:
            subscription_details.append(text)
    if subscription_details:
        result["subscription_details"] = subscription_details
        # First detail is usually the subscription name
        if subscription_details:
            result["subscription_name"] = subscription_details[0]

    # Extract item amount (in custom-137u684 class - bold amount)
    amount_elem = soup.find("p", class_="custom-137u684")
    if amount_elem:
        amount_text = amount_elem.get_text(strip=True)
        amount = parse_amount(amount_text)
        if amount:
            result["total_amount"] = amount

    # Extract VAT amount (in custom-vr1cqx span)
    vat_elem = soup.find("span", class_="custom-vr1cqx")
    if vat_elem:
        vat_text = vat_elem.get_text(strip=True)
        vat_amount = parse_amount(vat_text)
        if vat_amount:
            result["vat_amount"] = vat_amount

    # Extract subtotal (in custom-1s7arqf class after "Subtotal")
    subtotal = extract_apple_subtotal(soup)
    if subtotal:
        result["subtotal"] = subtotal

    # Extract payment method (in custom-15zbox7 class)
    payment_elem = soup.find("p", class_="custom-15zbox7")
    if payment_elem:
        payment_text = payment_elem.get_text(strip=True)
        result["payment_method"] = payment_text

    return result


def _parse_apple_old_format(soup: BeautifulSoup, html_body: str, result: dict) -> dict:
    """
    Parse Apple's old email format (pre-2024) with table-based layout.

    Old format uses:
    - <span style="font-size:10px;">LABEL</span><br>VALUE structure
    - Table cells with inline styles for amounts
    - "TOTAL" label followed by amount in next cell
    """
    # Extract Invoice Date: <span style="...font-size:10px;">INVOICE DATE</span><br><span dir="auto">24 Dec 2024</span>
    date_match = re.search(
        r"INVOICE DATE</span>.*?<span[^>]*>(\d{1,2}\s+\w+\s+\d{4})</span>",
        html_body,
        re.IGNORECASE | re.DOTALL,
    )
    if date_match:
        parsed_date = parse_date_text(date_match.group(1))
        if parsed_date:
            result["receipt_date"] = parsed_date

    # Extract Order ID: <span style="...">ORDER ID</span><br><span...><a href="...">MM61N78HGZ</a></span>
    order_match = re.search(
        r"ORDER ID</span>.*?<a[^>]*>([A-Z0-9]+)</a>",
        html_body,
        re.IGNORECASE | re.DOTALL,
    )
    if order_match:
        result["order_id"] = order_match.group(1)
    else:
        # Alternative: ORDER ID without link
        order_match2 = re.search(
            r"ORDER ID</span>.*?<br[^>]*>\s*([A-Z0-9]+)",
            html_body,
            re.IGNORECASE | re.DOTALL,
        )
        if order_match2:
            result["order_id"] = order_match2.group(1)

    # Extract Document No: <span style="...">DOCUMENT NO.</span><br>216891678188
    doc_match = re.search(
        r"DOCUMENT NO\.</span>.*?<br[^>]*>\s*(\d+)",
        html_body,
        re.IGNORECASE | re.DOTALL,
    )
    if doc_match:
        result["document_id"] = doc_match.group(1)

    # Extract Sequence No: <span style="...">SEQUENCE NO.</span><br>2-6358439100
    seq_match = re.search(
        r"SEQUENCE NO\.</span>.*?<br[^>]*>\s*([0-9-]+)",
        html_body,
        re.IGNORECASE | re.DOTALL,
    )
    if seq_match:
        result["sequence_id"] = seq_match.group(1)

    # Extract Product name: <span style="font-size:14px;font-weight:500;">Apple TV</span>
    product_match = re.search(r"font-weight:\s*500[^>]*>\s*([^<]+)</span>", html_body)
    if product_match:
        result["product_name"] = product_match.group(1).strip()

    # Extract Total amount: after "TOTAL" label, look for £X.XX
    # Pattern: <td...>TOTAL</td>...£8.99
    total_match = re.search(
        r">TOTAL</td>.*?£(\d+\.?\d*)", html_body, re.IGNORECASE | re.DOTALL
    )
    if total_match:
        result["total_amount"] = float(total_match.group(1))
    else:
        # Alternative: look for bold amount after item name
        # <span style="font-weight:600;white-space:nowrap;">£8.99</span>
        amounts = re.findall(
            r"font-weight:\s*600[^>]*>\s*£(\d+\.?\d*)\s*</span>", html_body
        )
        if amounts:
            # Last bold amount is usually the total
            result["total_amount"] = float(amounts[-1])

    # Extract VAT: look for VAT pattern with amount
    vat_match = re.search(r"VAT.*?£(\d+\.?\d*)", html_body, re.IGNORECASE)
    if vat_match:
        result["vat_amount"] = float(vat_match.group(1))

    # Extract Subtotal
    subtotal_match = re.search(
        r">Subtotal</span>.*?£(\d+\.?\d*)", html_body, re.IGNORECASE | re.DOTALL
    )
    if subtotal_match:
        result["subtotal"] = float(subtotal_match.group(1))

    return result


def extract_apple_field_value(soup: BeautifulSoup, field_name: str) -> str | None:
    """
    Extract a field value from Apple's label/value HTML structure.

    Apple uses <p class="custom-f41j3e">Label:</p> followed by
    <p class="custom-zresjj">Value</p>

    Args:
        soup: BeautifulSoup parsed HTML
        field_name: The label to search for (e.g., "Order ID")

    Returns:
        The field value or None
    """
    # Find the label element
    for label in soup.find_all("p", class_="custom-f41j3e"):
        if field_name.lower() in label.get_text().lower():
            # The value should be in the next sibling with custom-zresjj class
            next_sibling = label.find_next_sibling("p", class_="custom-zresjj")
            if next_sibling:
                return next_sibling.get_text(strip=True).replace("<br/>", "").strip()

    return None


def extract_apple_subtotal(soup: BeautifulSoup) -> float | None:
    """
    Extract subtotal amount from Apple invoice.

    The subtotal appears after "Subtotal" text in custom-4tra68 class,
    with the amount in custom-1s7arqf class.

    Args:
        soup: BeautifulSoup parsed HTML

    Returns:
        Subtotal amount or None
    """
    # Find "Subtotal" label
    for elem in soup.find_all("p", class_="custom-4tra68"):
        if "subtotal" in elem.get_text().lower():
            # Look for amount in nearby custom-68yyeh div
            parent = elem.find_parent()
            if parent:
                amount_elem = parent.find("p", class_="custom-1s7arqf")
                if amount_elem:
                    return parse_amount(amount_elem.get_text(strip=True))
    return None


def infer_apple_description(name: str) -> str | None:
    """
    Infer description for Apple items.

    Args:
        name: Item name

    Returns:
        Description or None
    """
    if not name:
        return None

    name_lower = name.lower()

    patterns = [
        (r"icloud|storage", "cloud storage subscription"),
        (r"apple music|music subscription", "music streaming subscription"),
        (r"apple tv", "video streaming subscription"),
        (r"tv\+", "Apple TV+ subscription"),
        (r"apple arcade", "gaming subscription"),
        (r"apple one", "bundled services subscription"),
        (r"apple news", "news subscription"),
        (r"apple fitness", "fitness subscription"),
        (r"in-app purchase|in app", "in-app purchase"),
        (r"bfi player", "BFI streaming subscription"),
        (r"hazard perception", "driving test preparation"),
        (r"subscription", "subscription service"),
        (r"app$|\.app", "mobile application"),
        (r"game", "mobile game"),
    ]

    for pattern, desc in patterns:
        if re.search(pattern, name_lower):
            return desc

    return "app/digital content"


def infer_apple_category(name: str) -> str:
    """
    Infer category for Apple items.

    Args:
        name: Item name

    Returns:
        Category hint
    """
    if not name:
        return "subscription"

    name_lower = name.lower()

    if re.search(
        r"icloud|storage|apple one|music|tv\+|arcade|news|fitness|apple tv|bfi|player",
        name_lower,
    ):
        return "subscription"
    if re.search(r"game|games", name_lower):
        return "entertainment"
    if re.search(r"in-app|coins|gems|premium", name_lower):
        return "entertainment"
    if re.search(r"hazard|driving|test|education", name_lower):
        return "education"

    return "subscription"


# ============================================================================
# PAYPAL PARSER
# ============================================================================


@register_vendor(["paypal.co.uk", "paypal.com", "mail.paypal.co.uk"])
def parse_paypal_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse PayPal payment receipts.

    PayPal receipts have:
    - Transaction ID (alphanumeric, 10-17 chars)
    - Merchant/seller name (from subject or body)
    - Amount sent/received
    - Currency (GBP, USD, EUR)
    - Date of transaction
    """
    result = {
        "parse_method": "vendor_paypal",
        "parse_confidence": 85,
        "merchant_name": "PayPal",
        "merchant_name_normalized": "paypal",
    }

    # Try to extract merchant from subject first
    # "Receipt for your payment to JustHost - Bluehost"
    # "Receipt for Your Payment to Microsoft Payments"
    subject_merchant_match = re.search(
        r"(?:payment to|receipt for your payment to)\s+([A-Za-z0-9\s\-&\'\.]+)",
        subject,
        re.IGNORECASE,
    )
    if subject_merchant_match:
        merchant = subject_merchant_match.group(1).strip()
        if 2 < len(merchant) < 50:
            result["payee_name"] = merchant
            result["merchant_name_normalized"] = (
                merchant.lower().replace(" ", "_").replace("-", "_")
            )

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

        # Extract transaction ID (alphanumeric, 10-17 chars)
        tx_match = re.search(
            r"Transaction\s*ID[:\s]*([A-Z0-9]{10,17})", text, re.IGNORECASE
        )
        if tx_match:
            result["order_id"] = tx_match.group(1)

        # Extract merchant from body if not found in subject
        if "payee_name" not in result:
            merchant_patterns = [
                r"Payment to[:\s]+([A-Za-z0-9\s\-&\'\.]+?)(?:\s*Transaction|\s*Amount|\s*£|\s*\$|\s*€)",
                r"Paid to[:\s]+([A-Za-z0-9\s\-&\'\.]+)",
                r"Sent to[:\s]+([A-Za-z0-9\s\-&\'\.]+)",
            ]
            for pattern in merchant_patterns:
                match = re.search(pattern, text)
                if match:
                    merchant = match.group(1).strip()
                    if 2 < len(merchant) < 50:
                        result["payee_name"] = merchant
                        result["merchant_name_normalized"] = (
                            merchant.lower().replace(" ", "_").replace("-", "_")
                        )
                        break

        # Extract total amount
        amount_patterns = [
            r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"You (?:sent|paid)[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Amount[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Payment[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Currency detection
        if "£" in text or "GBP" in text:
            result["currency_code"] = "GBP"
        elif "€" in text or "EUR" in text:
            result["currency_code"] = "EUR"
        elif "$" in text or "USD" in text:
            result["currency_code"] = "USD"

        # Date extraction - multiple formats
        date_patterns = [
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})",
            r"(?:Date|Transaction date)[:\s]*([\d]+\s+\w+\s+\d{4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["receipt_date"] = parse_date_text(match.group(1))
                break

    # Set line_items with payee information
    if result.get("payee_name"):
        result["line_items"] = [
            {
                "name": f"Payment to {result['payee_name']}",
                "merchant": result["payee_name"],
                "payment_method": "PayPal",
            }
        ]
    else:
        result["line_items"] = [
            {
                "name": "PayPal payment",
                "merchant": "Unknown",
                "payment_method": "PayPal",
            }
        ]

    # Validate - must have at least amount or transaction ID
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# UBER PARSER
# ============================================================================


def detect_uber_email_type(subject: str, html_body: str) -> str:
    """
    Detect the type of Uber email for routing.

    Args:
        subject: Email subject line
        html_body: HTML body content

    Returns:
        Email type string: 'ride' or 'eats'
    """
    subject_lower = subject.lower()
    if "eats" in subject_lower or "order with uber eats" in subject_lower:
        return "eats"
    if "ubereats" in (html_body or "").lower():
        return "eats"
    return "ride"


@register_vendor(["uber.com", "ubereats.com"])
def parse_uber_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Uber ride receipts and Uber Eats order receipts.

    Routes based on email type:
    - ride: Uber transportation receipts (category: transport)
    - eats: Uber Eats food delivery receipts (category: food_delivery)

    Extracts: total amount, currency, date, time
    """
    email_type = detect_uber_email_type(subject, html_body)

    # Set merchant based on type
    if email_type == "eats":
        result = {
            "merchant_name": "Uber Eats",
            "merchant_name_normalized": "uber_eats",
            "category_hint": "food_delivery",
            "email_type": "eats",
        }
    else:
        result = {
            "merchant_name": "Uber",
            "merchant_name_normalized": "uber",
            "category_hint": "transport",
            "email_type": "ride",
        }

    result["parse_method"] = "vendor_uber"
    result["parse_confidence"] = 85

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

        # Extract total - Uber uses specific patterns
        total_patterns = [
            r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"You paid[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Amount charged[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"[£$€]([0-9,]+\.[0-9]{2})",  # Fallback: any currency amount
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Infer currency from text
        if "£" in text:
            result["currency_code"] = "GBP"
        elif "€" in text:
            result["currency_code"] = "EUR"
        elif "$" in text:
            result["currency_code"] = "USD"

        # Extract date - multiple formats
        date_patterns = [
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4})",
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})",
        ]
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["receipt_date"] = parse_date_text(match.group(1))
                break

        # Extract time if available
        time_match = re.search(r"(\d{1,2}:\d{2})\s*(?:am|pm)?", text, re.IGNORECASE)
        if time_match:
            result["trip_time"] = time_match.group(1)

        # Extract line items based on type
        if email_type == "eats":
            # Try to extract restaurant name for Uber Eats
            restaurant_patterns = [
                r"(?:Your order from|Order from)\s+([A-Za-z0-9\s&\'\-]+?)(?:\s*is|\s*has|\n)",
                r"Restaurant[:\s]+([A-Za-z0-9\s&\'\-]+?)(?:\n|\s{2,})",
                r"Thanks for ordering from\s+([A-Za-z0-9\s&\'\-]+)",
            ]
            for pattern in restaurant_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    restaurant = match.group(1).strip()
                    if len(restaurant) > 2 and len(restaurant) < 100:
                        result["restaurant_name"] = restaurant
                        result["line_items"] = [
                            {
                                "name": f"Order from {restaurant}",
                                "restaurant": restaurant,
                                "brand": restaurant,  # Restaurant is the brand for food delivery
                            }
                        ]
                        break
            # Fallback: just note it's a food order
            if "line_items" not in result:
                result["line_items"] = [
                    {
                        "name": "Uber Eats order",
                        "restaurant": "Unknown",
                        "brand": "Uber Eats",  # Service brand when restaurant unknown
                    }
                ]
        else:
            # For rides, create a trip description
            trip_desc_parts = []
            if result.get("receipt_date"):
                trip_desc_parts.append(result["receipt_date"])
            if result.get("trip_time"):
                trip_desc_parts.append(result["trip_time"])

            if trip_desc_parts:
                result["line_items"] = [
                    {
                        "name": f"Uber ride ({', '.join(trip_desc_parts)})",
                        "brand": "Uber",  # Service brand
                    }
                ]
            else:
                result["line_items"] = [
                    {
                        "name": "Uber ride",
                        "brand": "Uber",  # Service brand
                    }
                ]

    if result.get("total_amount"):
        return result

    return None


# ============================================================================
# LYFT PARSER
# ============================================================================


@register_vendor(["lyftmail.com"])
def parse_lyft_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Lyft ride receipts.

    Lyft emails have:
    - Subject: "Your receipt for rides on [Month Day]"
    - Trip date, pickup/dropoff locations
    - Fare breakdown and total amount
    """
    result = {
        "merchant_name": "Lyft",
        "merchant_name_normalized": "lyft",
        "parse_method": "vendor_lyft",
        "parse_confidence": 85,
    }

    # Extract date from subject (e.g., "Your receipt for rides on December 12")
    subject_date_match = re.search(
        r"(?:on|from)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})",
        subject,
        re.IGNORECASE,
    )

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

        # Extract total amount - Lyft uses various patterns
        total_patterns = [
            r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"You paid[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Charged[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"[£$€]\s*([0-9,]+\.[0-9]{2})\s*(?:total|charged)",
            # Lyft sometimes just shows the amount
            r"Total\s+\$([0-9,]+\.[0-9]{2})",
        ]

        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Try to find full date in body (with year)
        full_date = parse_date_text(text)
        if full_date:
            result["receipt_date"] = full_date
        elif subject_date_match:
            # Use subject date with current year (will be refined by received_at fallback)
            months = {
                "january": 1,
                "february": 2,
                "march": 3,
                "april": 4,
                "may": 5,
                "june": 6,
                "july": 7,
                "august": 8,
                "september": 9,
                "october": 10,
                "november": 11,
                "december": 12,
            }
            month = months.get(subject_date_match.group(1).lower())
            day = int(subject_date_match.group(2))
            if month and day:
                # Use current year - matching will use received_at as fallback
                year = datetime.now().year
                result["receipt_date"] = f"{year:04d}-{month:02d}-{day:02d}"

        # Extract trip details if available
        trip_match = re.search(r"(?:from|pickup)[:\s]*([^,\n]+)", text, re.IGNORECASE)
        if trip_match:
            result["line_items"] = [f"Lyft ride: {trip_match.group(1).strip()[:50]}"]

    # Validate - must have amount or we can't match
    if result.get("total_amount"):
        return result

    # Even without amount, return if we have valid Lyft email structure
    if subject_date_match:
        return result

    return None


# ============================================================================
# DELIVEROO PARSER
# ============================================================================


@register_vendor(["deliveroo.co.uk", "deliveroo.com"])
def parse_deliveroo_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Deliveroo order receipts.

    Subject patterns:
    - "Your order's in the kitchen" (new format)
    - "Your Deliveroo order from {Restaurant}"
    - "Thanks for your order from {Restaurant}"

    Text body format:
    - "{Restaurant} has your order!"
    - Line items: "3x    Naan Bread  - £2.00"
    - Total: "Total                  £86.87"
    """
    result = {
        "merchant_name": "Deliveroo",
        "merchant_name_normalized": "deliveroo",
        "parse_method": "vendor_deliveroo",
        "parse_confidence": 85,
        "category_hint": "food_delivery",
        "currency_code": "GBP",
    }

    # Prefer text_body for parsing (more structured than HTML)
    # Normalize line endings
    text = (text_body or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text and html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    if not text:
        return None

    # Extract restaurant name - multiple patterns
    restaurant = None

    # Pattern 1: "{Restaurant} has your order!" (new format)
    rest_match = re.search(r"([\w][\w\s&\'\-]+)\s+has your order", text)
    if rest_match:
        restaurant = rest_match.group(1).strip()

    # Pattern 2: From subject - "order from {Restaurant}"
    if not restaurant:
        subject_patterns = [
            r"order from\s+(.+?)(?:\s*-|\s*$)",
            r"from\s+([A-Za-z0-9\s&\'\-]+?)(?:\s*order|\s*-|\s*$)",
        ]
        for pattern in subject_patterns:
            match = re.search(pattern, subject, re.IGNORECASE)
            if match:
                restaurant = match.group(1).strip()
                if len(restaurant) > 2 and len(restaurant) < 100:
                    break
                restaurant = None

    # Extract total amount
    total_patterns = [
        r"Total\s+£([\d,.]+)",
        r"Total[:\s]*£\s*([\d,]+\.?\d*)",
        r"Order total[:\s]*£\s*([\d,]+\.?\d*)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Extract individual line items
    # Format: "3x    Naan Bread  - £2.00"
    line_items = []
    item_pattern = r"(\d+)x\s+(.+?)\s+-\s+£([\d.]+)"
    for match in re.finditer(item_pattern, text):
        qty = int(match.group(1))
        name = match.group(2).strip()
        price = parse_amount(match.group(3))
        # Skip modifiers (lines starting with --)
        if not name.startswith("--"):
            item = {"name": name, "quantity": qty, "price": price}
            # Add restaurant as brand/source for food items
            if restaurant:
                item["restaurant"] = restaurant
                item["brand"] = restaurant  # Restaurant is the brand for food delivery
            line_items.append(item)

    # Set line_items - prefer extracted items, fallback to restaurant name
    if line_items:
        result["line_items"] = line_items
    elif restaurant:
        result["line_items"] = [
            {
                "name": f"Order from {restaurant}",
                "restaurant": restaurant,
                "brand": restaurant,  # Restaurant is the brand for food delivery
            }
        ]

    if restaurant:
        result["restaurant_name"] = restaurant

    # Extract order ID from text
    order_match = re.search(r"Order #(\d+)", text)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract delivery completion date
    date_patterns = [
        r"Delivered on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",  # "Delivered on June 15, 2024"
        r"Order completed[:\s]+(\d{1,2}/\d{1,2}/\d{4})",  # "Order completed: 15/06/2024"
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})",  # "15 June 2024"
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Try multiple formats
            for fmt in ["%B %d, %Y", "%d/%m/%Y", "%d %B %Y"]:
                try:
                    from datetime import datetime

                    result["receipt_date"] = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if result.get("receipt_date"):
                break

    if result.get("total_amount"):
        return result

    return None


# ============================================================================
# EBAY PARSER
# ============================================================================


@register_vendor(["ebay.co.uk", "ebay.com", "ebay.de", "ebay.fr", "ebay.com.au"])
def parse_ebay_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse eBay order confirmation emails.

    eBay order confirmations have:
    - Subject: "Order confirmed: [Item Name]" or "[Name], your order is confirmed"
    - Price in <span class="blueFix"><b>£XX.XX</b></span>
    - Item ID and Transaction ID in FetchOrderDetails URLs
    - Order number format: NN-NNNNN-NNNNN (optional)

    Args:
        html_body: Raw HTML content
        text_body: Plain text content
        subject: Email subject line

    Returns:
        Parsed receipt dictionary or None if not a valid order confirmation
    """
    result = {
        "merchant_name": "eBay",
        "merchant_name_normalized": "ebay",
        "parse_method": "vendor_ebay",
        "parse_confidence": 90,
    }

    subject_lower = subject.lower()

    # Reject if subject indicates marketing email
    marketing_indicators = [
        "watchlist",
        "price drop",
        "deals",
        "ending soon",
        "recommended",
        "top picks",
        "you might like",
        "saved search",
        "daily deals",
    ]
    for indicator in marketing_indicators:
        if indicator in subject_lower:
            return None  # Not an order confirmation

    # Verify this is an order confirmation
    receipt_indicators = [
        "order confirmed",
        "your order is confirmed",
        "thanks for your order",
        "you paid for your item",
        "payment sent",
        "you've paid",
    ]
    is_order_email = any(ind in subject_lower for ind in receipt_indicators)
    if not is_order_email:
        return None

    # Extract item name from subject
    item_name = extract_ebay_item_from_subject(subject)

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")

        # Extract order details from structured HTML
        order_data = extract_ebay_order_details(soup)

        # Merge extracted data
        if order_data.get("order_number"):
            result["order_id"] = order_data["order_number"]
        elif order_data.get("transaction_id"):
            result["order_id"] = order_data["transaction_id"]

        if order_data.get("item_id"):
            result["ebay_item_id"] = order_data["item_id"]
        if order_data.get("transaction_id"):
            result["ebay_transaction_id"] = order_data["transaction_id"]
        if order_data.get("price"):
            result["total_amount"] = order_data["price"]
        if order_data.get("currency"):
            result["currency_code"] = order_data["currency"]
        if order_data.get("seller"):
            result["seller_name"] = order_data["seller"]

        # Get item name from HTML if not in subject
        if not item_name and order_data.get("item_name"):
            item_name = order_data["item_name"]

    # Build line items
    if item_name:
        cleaned_name = clean_ebay_product_name(item_name)
        item = {
            "name": cleaned_name,
            "description": infer_ebay_description(item_name),
            "category_hint": infer_ebay_category(item_name),
            "quantity": 1,
            "price": result.get("total_amount"),
        }
        # Extract brand from product name
        brand = extract_product_brand(cleaned_name)
        if brand:
            item["brand"] = brand
        # Add seller name if available
        if result.get("seller_name"):
            item["seller"] = result["seller_name"]
        result["line_items"] = [item]

    # Validate we have essential data
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


def extract_ebay_item_from_subject(subject: str) -> str | None:
    """
    Extract item name from eBay order confirmation subject.

    Patterns:
    - "Order confirmed: [Item Name]"
    - "[Name], your order is confirmed" (item not in subject)

    Args:
        subject: Email subject line

    Returns:
        Item name or None
    """
    # Pattern 1: "Order confirmed: Item Name"
    match = re.search(r"Order confirmed:\s*(.+?)(?:\s*$)", subject, re.IGNORECASE)
    if match:
        item_name = match.group(1).strip()
        if len(item_name) > 3:
            return item_name

    return None


def extract_ebay_order_details(soup: BeautifulSoup) -> dict:
    """
    Extract structured order details from eBay HTML.

    eBay uses various HTML structures including:
    - FetchOrderDetails URLs with itemId and transactionId
    - Price in <span class="blueFix"><b>£XX.XX</b></span>
    - Label/value pairs in table cells

    Args:
        soup: BeautifulSoup parsed HTML

    Returns:
        Dictionary with extracted order details
    """
    data = {}

    # Strategy 1: Extract from FetchOrderDetails URLs
    fetch_links = soup.find_all(
        "a", href=re.compile(r"FetchOrderDetails", re.IGNORECASE)
    )
    for link in fetch_links:
        href = link.get("href", "")

        # Extract itemId
        item_match = re.search(r"itemId[=:](\d+)", href, re.IGNORECASE)
        if item_match and "item_id" not in data:
            data["item_id"] = item_match.group(1)

        # Extract transactionId
        tx_match = re.search(r"transactionId[=:](\d+)", href, re.IGNORECASE)
        if tx_match and "transaction_id" not in data:
            data["transaction_id"] = tx_match.group(1)

    # Strategy 2: Find price in blueFix span (eBay's price display class)
    # Look for "Price:" label followed by blueFix span
    text_content = soup.get_text()

    # Find price patterns in text
    price_patterns = [
        r"Price[:\s]*[£]([0-9,]+\.?\d*)",
        r"Price[:\s]*GBP\s*([0-9,]+\.?\d*)",
        r"Price[:\s]*\$([0-9,]+\.?\d*)",
        r"Price[:\s]*EUR\s*([0-9,]+\.?\d*)",
    ]

    for pattern in price_patterns:
        match = re.search(pattern, text_content, re.IGNORECASE)
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
                data["price"] = amount
                # Determine currency
                if "£" in pattern or "GBP" in pattern:
                    data["currency"] = "GBP"
                elif "$" in pattern:
                    data["currency"] = "USD"
                elif "EUR" in pattern:
                    data["currency"] = "EUR"
                break
            except ValueError:
                continue

    # Alternative: Look for blueFix spans directly
    if "price" not in data:
        for span in soup.find_all("span", class_="blueFix"):
            span_text = span.get_text(strip=True)
            price, currency = parse_ebay_price(span_text)
            if price:
                data["price"] = price
                data["currency"] = currency
                break

    # Strategy 3: Extract item name from title link
    title_link = soup.find("a", class_="title")
    if title_link:
        title_text = title_link.get_text(strip=True)
        if len(title_text) > 5 and len(title_text) < 300:
            data["item_name"] = title_text

    # Alternative: Find h3 with title class
    if not data.get("item_name"):
        for h3 in soup.find_all("h3", class_=re.compile(r"title", re.IGNORECASE)):
            text = h3.get_text(strip=True)
            if len(text) > 5 and len(text) < 300:
                data["item_name"] = text
                break

    # Strategy 4: Look for order number (format: NN-NNNNN-NNNNN)
    order_match = re.search(r"(\d{2}-\d{5}-\d{5})", text_content)
    if order_match:
        data["order_number"] = order_match.group(1)

    return data


def parse_ebay_price(text: str) -> tuple:
    """
    Parse eBay price text to amount and currency.

    eBay prices appear as:
    - "£6.76" or "GBP 6.76"
    - May include encoded characters

    Args:
        text: Price text from HTML

    Returns:
        Tuple of (amount: float, currency: str) or (None, None)
    """
    if not text:
        return None, None

    # Clean up any encoded characters
    text = text.replace("=C2=A3", "£").replace("=C2=A0", " ")

    # Try common patterns
    patterns = [
        (r"[£]([0-9,]+\.?\d*)", "GBP"),
        (r"GBP\s*([0-9,]+\.?\d*)", "GBP"),
        (r"[$]([0-9,]+\.?\d*)", "USD"),
        (r"USD\s*([0-9,]+\.?\d*)", "USD"),
        (r"[€]([0-9,]+\.?\d*)", "EUR"),
        (r"EUR\s*([0-9,]+\.?\d*)", "EUR"),
    ]

    for pattern, currency in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amount = float(match.group(1).replace(",", ""))
                return amount, currency
            except ValueError:
                continue

    return None, None


def clean_ebay_product_name(name: str) -> str:
    """
    Clean eBay product name for display.

    Args:
        name: Raw product name

    Returns:
        Cleaned product name
    """
    if not name:
        return ""

    # Remove excessive whitespace
    name = " ".join(name.split())

    # Truncate very long names
    if len(name) > 150:
        name = name[:147] + "..."

    return name


def infer_ebay_description(name: str) -> str | None:
    """
    Infer description from eBay item name.

    Args:
        name: Item name

    Returns:
        Brief description or None
    """
    if not name:
        return None

    name_lower = name.lower()

    patterns = [
        (r"laptop|notebook|thinkpad|macbook|chromebook", "laptop computer"),
        (r"phone|iphone|samsung galaxy|pixel|smartphone", "mobile phone"),
        (r"tablet|ipad", "tablet device"),
        (r"book|paperback|hardcover|novel", "book"),
        (r"cable|charger|adapter|usb", "accessory/cable"),
        (r"headphone|earphone|earbud|airpod", "audio headphones"),
        (r"watch|smartwatch", "watch"),
        (r"camera|lens|dslr", "camera equipment"),
        (r"game|playstation|xbox|nintendo|ps5|ps4", "video game/console"),
        (r"clothing|shirt|dress|pants|jacket|coat", "clothing"),
        (r"shoes|trainers|boots|sneakers", "footwear"),
        (r"keyboard|mouse|monitor|display", "computer peripheral"),
        (r"speaker|bluetooth", "audio speaker"),
        (r"printer|scanner", "office equipment"),
    ]

    for pattern, description in patterns:
        if re.search(pattern, name_lower):
            return description

    return "eBay purchase"


def infer_ebay_category(name: str) -> str:
    """
    Infer spending category from eBay item name.

    Args:
        name: Item name

    Returns:
        Category hint string
    """
    if not name:
        return "shopping"

    name_lower = name.lower()

    category_patterns = [
        (
            r"laptop|notebook|computer|thinkpad|macbook|phone|tablet|ipad|iphone|camera|keyboard|mouse|monitor",
            "electronics",
        ),
        (r"book|paperback|hardcover|novel|kindle|magazine", "entertainment"),
        (r"game|playstation|xbox|nintendo|gaming|ps5|ps4", "entertainment"),
        (
            r"shirt|dress|pants|jacket|coat|clothing|shoes|trainers|boots|sneakers|fashion",
            "clothing",
        ),
        (
            r"headphone|earphone|earbud|speaker|audio|cable|charger|adapter",
            "electronics",
        ),
        (r"toy|lego|puzzle|doll|figure", "entertainment"),
        (r"food|coffee|tea|snack", "groceries"),
        (r"medicine|vitamin|supplement|health", "health"),
        (r"kitchen|cooking|pan|pot|utensil", "home"),
        (r"garden|plant|outdoor|patio", "home"),
        (r"car|vehicle|automotive|motor|bike|bicycle", "transport"),
        (r"office|stationery|pen|paper|desk", "home"),
        (r"baby|child|kids", "family"),
        (r"pet|dog|cat|animal", "pets"),
    ]

    for pattern, category in category_patterns:
        if re.search(pattern, name_lower):
            return category

    return "shopping"


# ============================================================================
# MICROSOFT PARSER
# ============================================================================


@register_vendor(["microsoft.com"])
def parse_microsoft_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Microsoft purchase receipts (Microsoft 365, Xbox, Store).

    Microsoft purchase emails have:
    - Subject: "Your purchase of [PRODUCT] has been processed"
    - Order number (8-12 digits)
    - Product name and subscription details
    - Amount in GBP/USD/EUR
    - Billing period for subscriptions
    """
    result = {
        "parse_method": "vendor_microsoft",
        "parse_confidence": 85,
        "merchant_name": "Microsoft",
        "merchant_name_normalized": "microsoft",
        "category_hint": "software_subscription",
    }

    # Extract product from subject - multiple patterns
    # "Your purchase of Microsoft 365 Family has been processed"
    # "Your subscription to Microsoft 365 Personal has been renewed"
    # "You've renewed your Microsoft Teams Essentials subscription"
    # "Your Microsoft order #2600070935 has been processed"
    product_name = None

    subject_patterns = [
        r"purchase of\s+(.+?)\s+has been",
        r"subscription to\s+(.+?)\s+has been",
        r"You['\u2019]ve renewed your\s+(.+?)\s+subscription",  # Handle both curly and straight apostrophe
        r"Your\s+(.+?)\s+order\s*#\d+",
    ]
    for pattern in subject_patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            product_name = match.group(1).strip()
            break

    if product_name:
        result["product_name"] = product_name
        # Microsoft only sells own-branded products, so brand = Microsoft
        result["line_items"] = [{"name": product_name, "brand": "Microsoft"}]

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

        # Extract order number (8-12 digits)
        order_match = re.search(
            r"Order\s*(?:number|#)?[:\s]*(\d{8,12})", text, re.IGNORECASE
        )
        if order_match:
            result["order_id"] = order_match.group(1)

        # Extract amount - multiple patterns
        amount_patterns = [
            r"Plan Price[:\s]*(?:GBP|USD|EUR)?\s*([0-9,]+\.?\d*)",
            r"(?:GBP|USD|EUR)\s*([0-9,]+\.?\d*)",
            r"[£$€]\s*([0-9,]+\.?\d*)",
            r"Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Currency detection
        if "GBP" in text or "£" in text:
            result["currency_code"] = "GBP"
        elif "EUR" in text or "€" in text:
            result["currency_code"] = "EUR"
        elif "USD" in text or "$" in text:
            result["currency_code"] = "USD"

        # Subscription period
        period_match = re.search(r"(\d+)\s*(year|month)", text, re.IGNORECASE)
        if period_match:
            result["billing_period"] = (
                f"{period_match.group(1)} {period_match.group(2)}"
            )

        # Payment method
        payment_match = re.search(
            r"(MasterCard|Visa|PayPal|Amex|American Express)[^\d]*(\*{2,4}\d{4})?",
            text,
            re.IGNORECASE,
        )
        if payment_match:
            result["payment_method"] = payment_match.group(0).strip()

        # Determine category from product name
        if result.get("product_name"):
            product_lower = result["product_name"].lower()
            if "xbox" in product_lower or "game" in product_lower:
                result["category_hint"] = "entertainment"
            elif (
                "365" in product_lower
                or "office" in product_lower
                or "azure" in product_lower
                or "visual studio" in product_lower
            ):
                result["category_hint"] = "software_subscription"

    # Validate - must have at least amount, order ID, or product name
    if result.get("total_amount") or result.get("order_id") or result.get("line_items"):
        return result

    return None


# ============================================================================
# GOOGLE PARSER
# ============================================================================


@register_vendor(["google.com"])
def parse_google_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Google Play and Google Cloud receipts.

    Google Play receipts have amounts in HTML.
    Google Cloud invoices have amounts in PDF attachments (not extracted here).

    Google Play receipts contain:
    - Order number (e.g., SOP.3326-9787-8456-67380..6)
    - Product name (e.g., 100 GB Google One)
    - Price with period (e.g., £15.99/year)
    - VAT breakdown

    Google Cloud invoices contain:
    - Invoice number (e.g., 5437021344)
    - Billing ID (amount in PDF attachment)
    """
    result = {
        "parse_method": "vendor_google",
        "parse_confidence": 85,
        "merchant_name": "Google",
        "merchant_name_normalized": "google",
    }

    # Detect type from subject
    subject_lower = subject.lower()
    if "google play" in subject_lower:
        result["category_hint"] = "software_subscription"
        result["merchant_name"] = "Google Play"
        result["merchant_name_normalized"] = "google_play"
    elif "cloud platform" in subject_lower or "invoice" in subject_lower:
        result["category_hint"] = "software_subscription"
        result["merchant_name"] = "Google Cloud"
        result["merchant_name_normalized"] = "google_cloud"

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

        # Extract order/invoice number
        order_patterns = [
            r"Order number[:\s]*([A-Z0-9\.\-]+)",
            r"Invoice number[:\s]*(\d+)",
        ]
        for pattern in order_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["order_id"] = match.group(1)
                break

        # Try to extract invoice ID from subject for Google Cloud
        if not result.get("order_id") and "invoice" in subject_lower:
            subject_match = re.search(r"for\s+([A-Z0-9\-]+)", subject, re.IGNORECASE)
            if subject_match:
                result["order_id"] = subject_match.group(1)

        # Extract invoice date for Google Cloud
        if "cloud" in result.get("merchant_name_normalized", ""):
            # Pattern 1: "Invoice date: Month DD, YYYY"
            date_match = re.search(
                r"Invoice date[:\s]+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.IGNORECASE
            )
            if date_match:
                parsed = parse_date_text(date_match.group(1))
                if parsed:
                    result["receipt_date"] = parsed

            # Pattern 2: "Billing period: YYYY-MM-DD to YYYY-MM-DD" (use end date)
            if not result.get("receipt_date"):
                period_match = re.search(
                    r"to\s+(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE
                )
                if period_match:
                    parsed = parse_date_text(period_match.group(1))
                    if parsed:
                        result["receipt_date"] = parsed

            # Pattern 3: Subject line "Invoice for [ID] (Month YYYY)" - use first day of month
            if not result.get("receipt_date"):
                subject_date = re.search(r"\(([A-Za-z]+\s+\d{4})\)", subject)
                if subject_date:
                    # Use first day of month as approximation
                    parsed = parse_date_text(subject_date.group(1) + " 01")
                    if parsed:
                        result["receipt_date"] = parsed

        # Extract amount (Google Play has in HTML)
        amount_patterns = [
            r"[£$€]\s*([0-9,]+\.?\d*)/(?:year|month)",
            r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"Price[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
            r"[£$€]\s*([0-9,]+\.[0-9]{2})",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Currency detection
        if "£" in text or "GBP" in text:
            result["currency_code"] = "GBP"
        elif "€" in text or "EUR" in text:
            result["currency_code"] = "EUR"
        elif "$" in text or "USD" in text:
            result["currency_code"] = "USD"

        # Extract product name for Google Play
        product_patterns = [
            r"(?:Product|Item)[:\s]+(.+?)(?:\n|Auto-renewing)",
            r"(\d+ GB.*?)\s+(?:Google One|storage)",
            r"(?:for|of)\s+([A-Za-z0-9\s]+(?:subscription|plan|membership))",  # App subscriptions
        ]
        for pattern in product_patterns:
            match = re.search(pattern, text)
            if match:
                product = match.group(1).strip()
                # Avoid extracting just "Price" or other generic terms
                if (
                    product
                    and len(product) > 5
                    and product.lower() not in ["price", "total", "amount", "order"]
                ):
                    result["product_name"] = product
                    break

        # Extract subscription period if present
        period_match = re.search(r"([£$€][0-9,\.]+)/(\w+)", text)
        if period_match:
            result["billing_period"] = period_match.group(2)

    # Set line_items from product name
    # Google only sells own-branded products, so brand = merchant name
    merchant_brand = result.get("merchant_name", "Google")
    if result.get("product_name"):
        period_suffix = (
            f" ({result['billing_period']})" if result.get("billing_period") else ""
        )
        result["line_items"] = [
            {
                "name": f"{result['product_name']}{period_suffix}",
                "brand": merchant_brand,
            }
        ]
    elif "google_cloud" in result.get("merchant_name_normalized", ""):
        result["line_items"] = [
            {"name": "Google Cloud Platform services", "brand": "Google Cloud"}
        ]
    elif "google_play" in result.get("merchant_name_normalized", ""):
        result["line_items"] = [
            {"name": "Google Play purchase", "brand": "Google Play"}
        ]

    # Note: Google Cloud amounts are in PDF attachments
    # We can still extract invoice ID for matching
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# ANTHROPIC PARSER (Stripe-based receipts)
# ============================================================================


@register_vendor(["mail.anthropic.com"])
def parse_anthropic_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Anthropic receipt emails (Stripe-based).

    Anthropic receipts contain:
    - Receipt number in subject: #XXXX-XXXX-XXXX
    - Amount: $XX.XX
    - Date: Month DD, YYYY
    - Invoice number: XXXXXXXX-XXXX
    - VAT breakdown
    """
    result = {
        "merchant_name": "Anthropic",
        "merchant_name_normalized": "anthropic",
        "parse_method": "vendor_anthropic",
        "parse_confidence": 90,
        "category_hint": "software_subscription",
        "currency_code": "USD",
    }

    # Extract receipt number from subject
    receipt_match = re.search(r"#(\d{4}-\d{4}-\d{4})", subject)
    if receipt_match:
        result["order_id"] = receipt_match.group(1)

    # Use text body for parsing (cleaner than HTML)
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract invoice number
    invoice_match = re.search(r"Invoice number\s+([A-Z0-9\-]+)", text, re.IGNORECASE)
    if invoice_match:
        result["invoice_number"] = invoice_match.group(1)

    # Extract total amount - handle both USD ($) and GBP (£)
    # e.g., "$60.00 Paid", "£180.00 Paid", "Total $60.00", "Amount paid £180.00"
    amount_patterns = [
        r"[\$£]([0-9,]+\.?\d*)\s+Paid",
        r"Total\s+[\$£]([0-9,]+\.?\d*)",
        r"Amount paid\s+[\$£]([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            # Detect currency from match
            full_match = match.group(0)
            if "£" in full_match:
                result["currency_code"] = "GBP"
            break

    # Extract date (e.g., "November 30, 2025")
    date_match = re.search(r"Paid\s+(\w+\s+\d{1,2},?\s+\d{4})", text, re.IGNORECASE)
    if date_match:
        result["receipt_date"] = parse_date_text(date_match.group(1))

    # Extract VAT/Tax (e.g., "VAT - United Kingdom (20%) $10.00" or "Tax (20%) £30.00")
    vat_match = re.search(
        r"(?:VAT|Tax)[^\$£]*[\$£]([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if vat_match:
        result["vat_amount"] = parse_amount(vat_match.group(1))

    # Extract subtotal
    subtotal_match = re.search(r"Subtotal\s+[\$£]([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if subtotal_match:
        result["subtotal"] = parse_amount(subtotal_match.group(1))

    # Extract product description
    product_match = re.search(r"Receipt #[\d\-]+\s+(.+?)\s+Qty", text)
    if product_match:
        result["product_name"] = product_match.group(1).strip()

    # Set line_items from product name or default
    if result.get("product_name"):
        result["line_items"] = [{"name": result["product_name"], "brand": "Anthropic"}]
    else:
        result["line_items"] = [{"name": "Claude API usage", "brand": "Anthropic"}]

    # Validate
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# AIRBNB PARSER
# ============================================================================


@register_vendor(["airbnb.com", "airbnb.co.uk"])
def parse_airbnb_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Airbnb receipt emails.

    Airbnb receipts contain:
    - Receipt ID: XXXXXXXXXX
    - Confirmation code: XXXXXXXXX
    - Property details
    - Stay dates
    - Price breakdown (nightly rate, service fee, taxes)
    - Total amount
    - Payment method
    """
    result = {
        "merchant_name": "Airbnb",
        "merchant_name_normalized": "airbnb",
        "parse_method": "vendor_airbnb",
        "parse_confidence": 90,
        "category_hint": "travel",
        "currency_code": "GBP",
    }

    # Use text body (cleaner structure)
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract Receipt ID
    receipt_match = re.search(r"Receipt ID[:\s]*([A-Z0-9]+)", text, re.IGNORECASE)
    if receipt_match:
        result["order_id"] = receipt_match.group(1)

    # Extract Confirmation code
    confirm_match = re.search(
        r"Confirmation code[:\s]*([A-Z0-9]+)", text, re.IGNORECASE
    )
    if confirm_match:
        result["confirmation_code"] = confirm_match.group(1)

    # Extract receipt date (from Receipt ID line: "Receipt ID: RCJTZQP29T · 29 September 2025")
    date_match = re.search(
        r"Receipt ID[:\s]*[A-Z0-9]+\s*[·•]\s*(\d{1,2}\s+\w+\s+\d{4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        result["receipt_date"] = parse_date_text(date_match.group(1))

    # Extract property/location
    location_match = re.search(r"nights? in\s+(.+?)(?:\n|$)", text, re.IGNORECASE)
    if location_match:
        result["product_name"] = location_match.group(1).strip()

    # Extract stay dates
    stay_match = re.search(
        r"(\w{3},\s+\d{1,2}\s+\w+\s+\d{4})\s*->\s*(\w{3},\s+\d{1,2}\s+\w+\s+\d{4})",
        text,
    )
    if stay_match:
        result["stay_start"] = stay_match.group(1)
        result["stay_end"] = stay_match.group(2)

    # Extract total amount (e.g., "Total (GBP)   £1,576.80" or "Amount paid (GBP)   £1,576.80")
    total_patterns = [
        r"Total\s*\(GBP\)\s*£([0-9,]+\.?\d*)",
        r"Amount paid\s*\(GBP\)\s*£([0-9,]+\.?\d*)",
        r"Total\s*£([0-9,]+\.?\d*)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Extract service fee
    fee_match = re.search(
        r"(?:Airbnb\s+)?service fee\s+£([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if fee_match:
        result["service_fee"] = parse_amount(fee_match.group(1))

    # Extract taxes
    tax_match = re.search(r"Taxes\s+£([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if tax_match:
        result["tax_amount"] = parse_amount(tax_match.group(1))

    # Extract payment method
    payment_match = re.search(
        r"(MASTERCARD|VISA|AMEX)[^\d]*(\d{4})", text, re.IGNORECASE
    )
    if payment_match:
        result["payment_method"] = (
            f"{payment_match.group(1)} •••• {payment_match.group(2)}"
        )

    # Set line_items with property name and stay dates
    if result.get("product_name"):
        item = {
            "name": f"Stay in {result['product_name']}",
            "property_name": result["product_name"],
        }
        if result.get("stay_start") and result.get("stay_end"):
            item["stay_dates"] = f"{result['stay_start']} - {result['stay_end']}"
        result["line_items"] = [item]
    else:
        result["line_items"] = [{"name": "Airbnb stay", "property_name": "Unknown"}]

    # Validate
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# ATLASSIAN PARSER
# ============================================================================


@register_vendor(["am.atlassian.com", "atlassian.com"])
def parse_atlassian_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Atlassian invoice/receipt emails.

    Atlassian receipts contain:
    - Invoice number in subject: IN-XXX-XXX-XXX
    - Payment confirmation
    """
    result = {
        "merchant_name": "Atlassian",
        "merchant_name_normalized": "atlassian",
        "parse_method": "vendor_atlassian",
        "parse_confidence": 85,
        "category_hint": "software_subscription",
    }

    # Extract invoice number from subject
    invoice_match = re.search(r"(IN-\d{3}-\d{3}-\d+)", subject)
    if invoice_match:
        result["order_id"] = invoice_match.group(1)

    # Use text body
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Try to extract invoice number from body if not in subject
    if not result.get("order_id"):
        invoice_match = re.search(
            r"invoice\s+(IN-\d{3}-\d{3}-\d+)", text, re.IGNORECASE
        )
        if invoice_match:
            result["order_id"] = invoice_match.group(1)

    # Currency detection
    if "£" in text or "GBP" in text:
        result["currency_code"] = "GBP"
    elif "€" in text or "EUR" in text:
        result["currency_code"] = "EUR"
    elif "$" in text or "USD" in text:
        result["currency_code"] = "USD"

    # Extract amount (if in email body - often in PDF attachment)
    amount_patterns = [
        r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Validate
    if result.get("order_id"):
        return result

    return None


# ============================================================================
# CHARLES TYRWHITT PARSER (for email body - PDF parsed separately)
# ============================================================================


@register_vendor(["ctshirts.co.uk", "ctshirts.com"])
def parse_charles_tyrwhitt_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Charles Tyrwhitt receipt emails.

    Note: The actual receipt details are in the PDF attachment.
    This parser extracts what's available in the email body.
    PDF parsing is handled separately by gmail_pdf_parser.py
    """
    result = {
        "merchant_name": "Charles Tyrwhitt",
        "merchant_name_normalized": "charles_tyrwhitt",
        "parse_method": "vendor_charles_tyrwhitt",
        "parse_confidence": 80,
        "category_hint": "clothing",
        "currency_code": "GBP",
        "has_pdf_attachment": True,  # Flag for PDF parsing
    }

    # Check if this is an e-receipt (has PDF) or order confirmation
    if "e-receipt" in subject.lower():
        result["email_type"] = "e_receipt"
    elif "order confirmation" in subject.lower():
        result["email_type"] = "order_confirmation"
        # Extract reference from subject
        ref_match = re.search(r"Ref[:\s]*([A-Z0-9]+)", subject, re.IGNORECASE)
        if ref_match:
            result["order_id"] = ref_match.group(1)

    # Use text body
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Try to extract order reference from body
    if not result.get("order_id"):
        ref_match = re.search(
            r"(?:Order|Reference)[:\s#]*([A-Z0-9]+)", text, re.IGNORECASE
        )
        if ref_match:
            result["order_id"] = ref_match.group(1)

    # For e-receipts, the PDF will be parsed separately
    # Return basic info to identify the vendor
    return result


# ============================================================================
# MINDBODYONLINE PARSER (triyoga, etc.)
# ============================================================================


@register_vendor(["mindbodyonline.com"])
def parse_mindbody_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Mindbody Online sales receipts (used by yoga studios, gyms, etc.).

    Email formats:
    Format 1 - Sales Receipt:
    - Subject: "[Business] Sales Receipt"
    - Sale Date: DD/MM/YYYY - HH:MM
    - Sale ID: numeric
    - Items with prices
    - Total (incl. tax of £X.XX): £Y.YY

    Format 2 - Purchase Receipt:
    - Subject: "Receipt for Your [Business] Purchase"
    - "Purchased X item(s) for £Y.YY on DD/MM/YYYY - HH:MM"
    """
    # Extract business name from subject
    # Format 1: "triyoga Sales Receipt"
    # Format 2: "Receipt for Your triyoga Purchase"
    business_name = "Mindbody"
    business_match = re.match(r"^(.+?)\s+Sales Receipt", subject, re.IGNORECASE)
    if business_match:
        business_name = business_match.group(1).strip()
    else:
        purchase_match = re.search(
            r"Receipt for Your\s+(.+?)\s+Purchase", subject, re.IGNORECASE
        )
        if purchase_match:
            business_name = purchase_match.group(1).strip()

    result = {
        "merchant_name": business_name,
        "merchant_name_normalized": re.sub(
            r"[^a-z0-9]+", "_", business_name.lower()
        ).strip("_"),
        "parse_method": "vendor_mindbody",
        "parse_confidence": 90,
        "category_hint": "health_fitness",
        "currency_code": "GBP",
    }

    # Use text body or extract from HTML
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract Sale ID
    sale_id_match = re.search(r"Sale ID[:\s]*(\d+)", text, re.IGNORECASE)
    if sale_id_match:
        result["order_id"] = sale_id_match.group(1)

    # Extract date - multiple formats
    # Format 1: "Sale Date: DD/MM/YYYY"
    # Format 2: "Purchased X item(s) for £Y.YY on DD/MM/YYYY - HH:MM"
    date_patterns = [
        r"Sale Date[:\s]*(\d{1,2})/(\d{1,2})/(\d{4})",
        r"on\s+(\d{1,2})/(\d{1,2})/(\d{4})",
    ]
    for pattern in date_patterns:
        date_match = re.search(pattern, text, re.IGNORECASE)
        if date_match:
            day = int(date_match.group(1))
            month = int(date_match.group(2))
            year = int(date_match.group(3))
            result["receipt_date"] = f"{year:04d}-{month:02d}-{day:02d}"
            break

    # Extract Total amount - multiple formats
    # Format 1: "Total (incl. tax of £X.XX): £Y.YY"
    # Format 2: "Purchased X item(s) for £Y.YY on..."
    total_patterns = [
        r"Purchased\s+\d+\s+item\(?s?\)?\s+for\s+£\s*([0-9,]+\.?\d*)",  # Purchased 1 item(s) for £25.00
        r"Total\s*\([^)]*\)[:\s]*£\s*([0-9,]+\.?\d*)",  # Total (incl. tax...): £25.00
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",  # Total: £25.00
    ]

    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Extract tax amount if present
    tax_match = re.search(
        r"(?:incl\.?\s*)?tax\s*(?:of)?\s*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if tax_match:
        result["vat_amount"] = parse_amount(tax_match.group(1))

    # Extract line items from structured HTML
    # MindBody uses <div id="lineItems"> with table rows for each item
    line_items = []

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")

        # Method 1: Use structured HTML with id="lineItems"
        line_items_div = soup.find(id="lineItems")
        if line_items_div:
            # Find all table rows in the line items section
            for row in line_items_div.find_all("tr"):
                cells = row.find_all("td")
                if len(cells) >= 3:
                    # Format: <td>qty</td><td>item name</td><td>£price</td>
                    qty_text = cells[0].get_text(strip=True)
                    item_name = cells[1].get_text(strip=True)
                    price_text = cells[2].get_text(strip=True)

                    # Extract price from "£25.00" format
                    price_match = re.search(r"£\s*([0-9,]+\.?\d*)", price_text)
                    qty = 1
                    try:
                        qty = int(qty_text)
                    except ValueError:
                        pass

                    if item_name and price_match:
                        line_items.append(
                            {
                                "name": item_name,
                                "quantity": qty,
                                "price": parse_amount(price_match.group(1)),
                            }
                        )

    # Fallback: Extract from text body with improved pattern
    if not line_items and text:
        # Pattern: "1 TRIYOGA – 1 Class (Y) £25.00" - but NOT "Total..."
        # Look for lines starting with a qty number, followed by item name, ending with price
        for line in text.split("\n"):
            line = line.strip()
            # Skip lines containing "Total" or "tax"
            if "total" in line.lower() or "tax" in line.lower():
                continue
            item_match = re.match(r"^(\d+)\s+(.+?)\s+£([0-9,]+\.?\d*)$", line)
            if item_match:
                line_items.append(
                    {
                        "name": item_match.group(2).strip(),
                        "quantity": int(item_match.group(1)),
                        "price": parse_amount(item_match.group(3)),
                    }
                )

    if line_items:
        result["line_items"] = line_items

    # Validate - must have amount
    if result.get("total_amount"):
        return result

    # Return with order_id even without amount
    if result.get("order_id"):
        return result

    return None


# ============================================================================
# VINTED PARSER (secondhand marketplace)
# ============================================================================


@register_vendor(["vinted.co.uk", "vinted.com", "vinted.fr", "vinted.de"])
def parse_vinted_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Vinted purchase receipts.

    Email format:
    - Subject: Your receipt for "[Item Name]"
    - Body contains: Seller, Order (item name), Paid amount with breakdown
    - Paid: £X.XX (postage: £X.XX + item: £X.XX + Buyer Protection fee: £X.XX)
    """
    result = {
        "merchant_name": "Vinted",
        "merchant_name_normalized": "vinted",
        "parse_method": "vendor_vinted",
        "parse_confidence": 90,
        "category_hint": "clothing",
        "currency_code": "GBP",
    }

    # Extract item name from subject: Your receipt for "Item Name"
    item_match = re.search(
        r'receipt for ["\u201c]([^"\u201d]+)["\u201d]', subject, re.IGNORECASE
    )
    if item_match:
        item_name = item_match.group(1).strip()
        result["line_items"] = [{"name": item_name}]

    # Use text body or extract from HTML
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract total paid amount: "Paid: £19.44" or "Paid: £19.44 (breakdown...)"
    paid_match = re.search(r"Paid[:\s]*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if paid_match:
        result["total_amount"] = parse_amount(paid_match.group(1))

    # Extract seller name
    seller_match = re.search(r"Seller[:\s]*(\w+)", text, re.IGNORECASE)
    if seller_match:
        result["seller_name"] = seller_match.group(1)

    # Extract breakdown if available
    postage_match = re.search(r"postage[:\s]*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if postage_match:
        result["postage_amount"] = parse_amount(postage_match.group(1))

    item_price_match = re.search(r"item[:\s]*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE)
    if item_price_match:
        result["item_amount"] = parse_amount(item_price_match.group(1))
        # Update line item with price
        if result.get("line_items"):
            result["line_items"][0]["price"] = result["item_amount"]

    protection_match = re.search(
        r"(?:Buyer\s+)?Protection(?:\s+fee)?[:\s]*£\s*([0-9,]+\.?\d*)",
        text,
        re.IGNORECASE,
    )
    if protection_match:
        result["protection_fee"] = parse_amount(protection_match.group(1))

    # Validate - must have amount
    if result.get("total_amount"):
        return result

    return None


# ============================================================================
# FASTSPRING PARSER (software purchases)
# ============================================================================


@register_vendor(["fastspring.com"])
def parse_fastspring_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse FastSpring software purchase receipts.

    Email format:
    - Subject: "[Name], here is your receipt for the order [ORDER_ID]"
    - Body contains: product name, download links, amount
    """
    result = {
        "merchant_name": "FastSpring",
        "merchant_name_normalized": "fastspring",
        "parse_method": "vendor_fastspring",
        "parse_confidence": 85,
        "category_hint": "software",
    }

    # Extract order ID from subject
    order_match = re.search(r"order\s+([A-Z0-9\-]+)", subject, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Use text body or extract from HTML
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Try to extract product name
    # Pattern: "Your Order [Product Name] Download"
    product_match = re.search(r"Your Order\s+(.+?)\s+Download", text, re.IGNORECASE)
    if product_match:
        product_name = product_match.group(1).strip()
        result["line_items"] = [{"name": product_name}]
        # Use product vendor as merchant if identifiable
        if product_name and len(product_name) < 50:
            result["merchant_name"] = product_name

    # Extract amount - various patterns
    amount_patterns = [
        r"Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        r"Price[:\s]*[£$€]\s*([0-9,]+\.?\d*)",
        r"[£$€]\s*([0-9,]+\.[0-9]{2})",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Detect currency
    if "£" in text:
        result["currency_code"] = "GBP"
    elif "€" in text:
        result["currency_code"] = "EUR"
    elif "$" in text:
        result["currency_code"] = "USD"

    # Validate - accept if we have order_id even without amount
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# CITIZENS OF SOIL PARSER (olive oil subscription)
# ============================================================================


@register_vendor(["citizensofsoil.com"])
def parse_citizens_of_soil_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Citizens of Soil olive oil order confirmations.

    Email format:
    - Subject: "Olive oil order #121862 confirmed 🙌"
    - Body contains: order ID, product, total amount
    """
    result = {
        "merchant_name": "Citizens of Soil",
        "merchant_name_normalized": "citizensofsoil",
        "parse_method": "vendor_citizens_of_soil",
        "parse_confidence": 90,
        "category_hint": "groceries",
        "currency_code": "GBP",
    }

    # Extract order ID from subject: "Olive oil order #121862 confirmed"
    order_match = re.search(r"order\s*#(\d+)", subject, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Use text body for parsing
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract total amount: "Total\n£15.00 GBP" or "Total £15.00"
    total_patterns = [
        r"Total\s*[£$€]\s*([0-9,]+\.?\d*)",
        r"Total\s+([0-9,]+\.?\d*)\s*GBP",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Extract product name
    product_match = re.search(
        r"What\'s coming.*?\n+(.+?)\s*×\s*\d+", text, re.IGNORECASE | re.DOTALL
    )
    if product_match:
        product_name = product_match.group(1).strip()
        if product_name:
            result["line_items"] = [{"name": product_name}]

    # Validate - need at least order_id or amount
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# ETSY PARSER (marketplace purchases)
# ============================================================================


@register_vendor(["etsy.com"])
def parse_etsy_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Etsy purchase receipts.

    Email format:
    - Subject: "Your Etsy Purchase from {SellerName} ({order_id})"
    - Body contains: Order summary, items, prices, totals

    Note: Dispatch notifications ("Your Etsy Order dispatched...") should be
    filtered out before reaching this parser.
    """
    result = {
        "merchant_name": "Etsy",
        "merchant_name_normalized": "etsy",
        "parse_method": "vendor_etsy",
        "parse_confidence": 90,
        "category_hint": "marketplace",
        "currency_code": "GBP",
    }

    # Extract seller name and order ID from subject
    # Pattern: "Your Etsy Purchase from SellerName (order_id)"
    subject_match = re.search(
        r"Your Etsy Purchase from\s+(.+?)\s*\((\d+)\)", subject, re.IGNORECASE
    )
    if subject_match:
        result["seller_name"] = subject_match.group(1).strip()
        result["order_id"] = subject_match.group(2).strip()

    # Use text body or extract from HTML
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract total amount - Etsy uses various patterns
    # "Order total: £12.34" or "Total: £12.34" or "Grand total £12.34"
    total_patterns = [
        r"(?:Order\s+)?[Tt]otal[:\s]*£\s*([0-9,]+\.?\d*)",
        r"(?:Grand\s+)?[Tt]otal[:\s]*£\s*([0-9,]+\.?\d*)",
        r"(?:Order\s+)?[Tt]otal[:\s]*\$\s*([0-9,]+\.?\d*)",
        r"(?:Grand\s+)?[Tt]otal[:\s]*€\s*([0-9,]+\.?\d*)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            # Detect currency from pattern
            if "€" in pattern:
                result["currency_code"] = "EUR"
            elif "$" in pattern:
                result["currency_code"] = "USD"
            break

    # Extract shipping cost if present
    shipping_match = re.search(
        r"Shipping[:\s]*£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE
    )
    if shipping_match:
        result["shipping_amount"] = parse_amount(shipping_match.group(1))

    # Try to extract item names from the order summary
    # Etsy items often appear in structured lists
    item_patterns = [
        r"Item[:\s]*(.+?)(?:\s*Qty|\s*£|\n)",
        r"([^£€$\n]+?)\s*×\s*\d+\s*£\s*[0-9,]+\.?\d*",
    ]
    items = []
    for pattern in item_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            item_name = match.strip() if isinstance(match, str) else match[0].strip()
            if item_name and len(item_name) > 3 and len(item_name) < 200:
                # Filter out common non-item text
                if not any(
                    skip in item_name.lower()
                    for skip in [
                        "order",
                        "total",
                        "shipping",
                        "subtotal",
                        "tax",
                        "etsy",
                    ]
                ):
                    item = {"name": item_name}
                    if result.get("seller_name"):
                        item["seller"] = result["seller_name"]
                    items.append(item)
        if items:
            break

    if items:
        result["line_items"] = items
    elif result.get("seller_name"):
        # Fallback: Create basic item with seller
        result["line_items"] = [
            {
                "name": f"Purchase from {result['seller_name']}",
                "seller": result["seller_name"],
            }
        ]

    # Validate - need at least order_id (from subject) or amount
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# BLACK SHEEP COFFEE PARSER (coffee shop orders)
# ============================================================================


@register_vendor(["leavetheherdbehind.com"])
def parse_black_sheep_coffee_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Black Sheep Coffee order confirmations.

    Domain: leavetheherdbehind.com (their brand tagline)
    Email format:
    - Subject: "Order Confirmation - {order_number} - {city} - {location}"
    - Example: "Order Confirmation - 279 - London - Jubilee Place"
    - Body contains: Order details, items, and total
    """
    result = {
        "merchant_name": "Black Sheep Coffee",
        "merchant_name_normalized": "black sheep coffee",
        "parse_method": "vendor_black_sheep_coffee",
        "parse_confidence": 90,
        "category_hint": "food_drink",
        "currency_code": "GBP",
    }

    # Extract order number, city, and location from subject
    # Pattern: "Order Confirmation - {number} - {city} - {location}"
    subject_match = re.search(
        r"Order Confirmation\s*-\s*(\d+)\s*-\s*([^-]+?)\s*-\s*(.+)",
        subject,
        re.IGNORECASE,
    )
    if subject_match:
        result["order_id"] = subject_match.group(1).strip()
        result["city"] = subject_match.group(2).strip()
        result["location"] = subject_match.group(3).strip()

    # Use text body or extract from HTML
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract total amount
    total_patterns = [
        r"[Tt]otal[:\s]*£\s*([0-9,]+\.?\d*)",
        r"[Oo]rder\s+[Tt]otal[:\s]*£\s*([0-9,]+\.?\d*)",
        r"[Aa]mount[:\s]*£\s*([0-9,]+\.?\d*)",
        r"£\s*([0-9,]+\.\d{2})\s*(?:total|paid)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Try to extract items from the order
    # Coffee shop items often appear as: "Item Name x1 £3.50" or "Item Name £3.50"
    item_patterns = [
        r"([A-Za-z][A-Za-z\s]+?)\s*(?:x\d+)?\s*£\s*([0-9,]+\.?\d*)",
    ]
    items = []
    for pattern in item_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            item_name = match[0].strip() if isinstance(match, tuple) else match.strip()
            if item_name and len(item_name) > 2 and len(item_name) < 100:
                # Filter out non-item text
                skip_words = [
                    "total",
                    "subtotal",
                    "order",
                    "confirmation",
                    "amount",
                    "payment",
                    "tax",
                    "vat",
                ]
                if not any(skip in item_name.lower() for skip in skip_words):
                    item_data = {"name": item_name}
                    if isinstance(match, tuple) and len(match) > 1:
                        price = parse_amount(match[1])
                        if price:
                            item_data["price"] = price
                    # Add location if available
                    if result.get("location"):
                        item_data["location"] = result["location"]
                    items.append(item_data)
        if items:
            break

    if items:
        result["line_items"] = items[:10]  # Limit to 10 items
    else:
        # Fallback: Create basic line item with location
        fallback_item = {"name": "Coffee order"}
        if result.get("location"):
            fallback_item["location"] = result["location"]
        result["line_items"] = [fallback_item]

    # Validate - need at least order_id or amount
    if result.get("total_amount") or result.get("order_id"):
        return result

    return None


# ============================================================================
# BRITISH AIRWAYS PARSER
# ============================================================================


@register_vendor(["crm.ba.com", "ba.com"])
def parse_british_airways_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse British Airways booking confirmation emails.

    Email format:
    - Subject: "Your booking confirmation X8I5PF"
    - Body contains: booking reference, flight details, passenger info, total
    """
    result = {
        "merchant_name": "British Airways",
        "merchant_name_normalized": "british_airways",
        "parse_method": "vendor_british_airways",
        "parse_confidence": 90,
        "category_hint": "travel",
        "currency_code": "GBP",
    }

    # Extract booking reference from subject
    ref_match = re.search(r"confirmation\s+([A-Z0-9]{6})", subject, re.IGNORECASE)
    if ref_match:
        result["order_id"] = ref_match.group(1)

    # Use text body or extract from HTML
    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract flights as line items
    line_items = []
    # Pattern: "London - Belfast" or "City to City"
    flight_pattern = r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:-|to)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
    flight_matches = re.findall(flight_pattern, text)
    seen_routes = set()
    for origin, dest in flight_matches:
        route = f"{origin} to {dest}"
        if route not in seen_routes and origin.lower() not in [
            "economy",
            "euro",
            "business",
        ]:
            seen_routes.add(route)
            line_items.append({"name": f"Flight: {route}"})

    # Extract flight numbers
    flight_nums = re.findall(r"\bBA\s*(\d{3,4})\b", text)
    for i, num in enumerate(flight_nums[: len(line_items)]):
        if i < len(line_items):
            line_items[i]["name"] += f" (BA{num})"

    if line_items:
        result["line_items"] = line_items[:4]  # Max 4 flights

    # Extract total amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Grand Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount paid[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# AUDIO EMOTION PARSER
# ============================================================================


@register_vendor(["audioemotion.co.uk"])
def parse_audio_emotion_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse Audio Emotion audio equipment order confirmations."""
    result = {
        "merchant_name": "Audio Emotion",
        "merchant_name_normalized": "audio_emotion",
        "parse_method": "vendor_audio_emotion",
        "parse_confidence": 85,
        "category_hint": "electronics",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract order ID
    order_match = re.search(
        r"order\s*(?:#|number|:)?\s*(\d+)", subject + " " + text, re.IGNORECASE
    )
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Grand Total[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# NOVATION MUSIC PARSER
# ============================================================================


@register_vendor(["novationmusic.com"])
def parse_novation_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """Parse Novation Music order confirmations."""
    result = {
        "merchant_name": "Novation Music",
        "merchant_name_normalized": "novation",
        "parse_method": "vendor_novation",
        "parse_confidence": 85,
        "category_hint": "electronics",
        "currency_code": "GBP",
    }

    # Extract order ID from subject: "Your Novation order confirmation (#700024906)"
    order_match = re.search(r"#(\d+)", subject)
    if order_match:
        result["order_id"] = order_match.group(1)

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# JOHN LEWIS PARSER
# ============================================================================


@register_vendor(["johnlewis.co.uk", "johnlewis.com"])
def parse_john_lewis_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse John Lewis purchase confirmations."""
    result = {
        "merchant_name": "John Lewis",
        "merchant_name_normalized": "john_lewis",
        "parse_method": "vendor_john_lewis",
        "parse_confidence": 90,
        "category_hint": "retail",
        "currency_code": "GBP",
    }

    # Extract order ID from subject: "Thank you for your purchase 509392169"
    order_match = re.search(r"purchase\s+(\d+)", subject, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# BLUEHOST PARSER
# ============================================================================


@register_vendor(["account.bluehost.com", "bluehost.com"])
def parse_bluehost_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """Parse Bluehost hosting order confirmations."""
    result = {
        "merchant_name": "Bluehost",
        "merchant_name_normalized": "bluehost",
        "parse_method": "vendor_bluehost",
        "parse_confidence": 85,
        "category_hint": "hosting",
        "currency_code": "USD",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract order ID
    order_match = re.search(r"order\s*(?:#|ID|:)?\s*(\d+)", text, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*\$\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*\$\s*([0-9,]+\.?\d*)",
        r"\$\s*([0-9,]+\.[0-9]{2})",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    # Detect currency - Bluehost is typically USD but check
    if "£" in text:
        result["currency_code"] = "GBP"

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# CEX / WEBUY PARSER
# ============================================================================


@register_vendor(["webuy.com", "cex.co.uk"])
def parse_cex_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """Parse CeX/WeBuy order confirmations."""
    result = {
        "merchant_name": "CeX",
        "merchant_name_normalized": "cex",
        "parse_method": "vendor_cex",
        "parse_confidence": 85,
        "category_hint": "electronics",
        "currency_code": "GBP",
    }

    # Extract order ID from subject: "CeX order confirmation: 19719781"
    order_match = re.search(r"confirmation[:\s]*(\d+)", subject, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# YRECEIPTS / MOSS PARSER
# ============================================================================


@register_vendor(["yreceipts.com"])
def parse_yreceipts_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse yReceipts digital receipts (used by various retailers like Moss)."""
    # Extract merchant name from subject: "Your receipt from Moss"
    merchant_match = re.search(
        r"receipt from\s+(.+?)(?:\s*$|\s*-)", subject, re.IGNORECASE
    )
    merchant_name = merchant_match.group(1).strip() if merchant_match else "Unknown"

    result = {
        "merchant_name": merchant_name,
        "merchant_name_normalized": merchant_name.lower()
        .replace(" ", "_")
        .replace("'", ""),
        "parse_method": "vendor_yreceipts",
        "parse_confidence": 80,
        "category_hint": "retail",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount"):
        return result
    return None


# ============================================================================
# DHL PARSER
# ============================================================================


@register_vendor(["dhl.com", "dhl.co.uk"])
def parse_dhl_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """Parse DHL duty/tax payment receipts."""
    result = {
        "merchant_name": "DHL",
        "merchant_name_normalized": "dhl",
        "parse_method": "vendor_dhl",
        "parse_confidence": 85,
        "category_hint": "shipping",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract waybill/tracking number
    waybill_match = re.search(r"waybill[:\s]*(\d+)", text, re.IGNORECASE)
    if waybill_match:
        result["order_id"] = waybill_match.group(1)

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Payment[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# WORLDPAY PARSER
# ============================================================================


@register_vendor(["worldpay.com"])
def parse_worldpay_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """Parse Worldpay transaction confirmations."""
    result = {
        "merchant_name": "Worldpay",
        "merchant_name_normalized": "worldpay",
        "parse_method": "vendor_worldpay",
        "parse_confidence": 80,
        "category_hint": "payment",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract transaction reference
    ref_match = re.search(r"reference[:\s]*([A-Z0-9\-]+)", text, re.IGNORECASE)
    if ref_match:
        result["order_id"] = ref_match.group(1)

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*£\s*([0-9,]+\.?\d*)",
        r"£\s*([0-9,]+\.[0-9]{2})",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# DESIGNACABLE PARSER
# ============================================================================


@register_vendor(["designacable.com"])
def parse_designacable_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse Designacable custom cable order confirmations."""
    result = {
        "merchant_name": "Designacable",
        "merchant_name_normalized": "designacable",
        "parse_method": "vendor_designacable",
        "parse_confidence": 85,
        "category_hint": "electronics",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract order ID
    order_match = re.search(
        r"order\s*(?:#|:)?\s*(\d+)", subject + " " + text, re.IGNORECASE
    )
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# COOKSMILL PARSER
# ============================================================================


@register_vendor(["cooksmill.co.uk"])
def parse_cooksmill_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse Cooksmill kitchenware order confirmations."""
    result = {
        "merchant_name": "Cooksmill",
        "merchant_name_normalized": "cooksmill",
        "parse_method": "vendor_cooksmill",
        "parse_confidence": 85,
        "category_hint": "home",
        "currency_code": "GBP",
    }

    # Extract order ID from subject: "Your Cooksmill order confirmation (#4000007561)"
    order_match = re.search(r"#(\d+)", subject)
    if order_match:
        result["order_id"] = order_match.group(1)

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# BAHA'I EVENTS PARSER
# ============================================================================


@register_vendor(["bahaievents.org.uk"])
def parse_bahai_events_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse Baha'i Events payment confirmations."""
    result = {
        "merchant_name": "Baha'i Events",
        "merchant_name_normalized": "bahai_events",
        "parse_method": "vendor_bahai_events",
        "parse_confidence": 85,
        "category_hint": "community",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Payment[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount"):
        return result
    return None


# ============================================================================
# BAHA'I BOOKS PARSER
# ============================================================================


@register_vendor(["bahai.org.uk"])
def parse_bahai_books_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse Baha'i Books UK invoices."""
    result = {
        "merchant_name": "Baha'i Books UK",
        "merchant_name_normalized": "bahai_books",
        "parse_method": "vendor_bahai_books",
        "parse_confidence": 85,
        "category_hint": "books",
        "currency_code": "GBP",
    }

    # Extract invoice number from subject: "Invoice #D4551"
    invoice_match = re.search(r"#([A-Z]?\d+)", subject)
    if invoice_match:
        result["order_id"] = invoice_match.group(1)

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Amount[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# WORLD OF BOOKS PARSER
# ============================================================================


@register_vendor(["worldofbooks.com", "wob.com"])
def parse_world_of_books_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse World of Books order confirmations.

    Email format:
    - Order number: WOB1053001728131
    - "Title" header followed by book title lines
    - Condition: "GB / VERY_GOOD"
    - Qty: 1
    - Price: £3.50
    """
    result = {
        "merchant_name": "World of Books",
        "merchant_name_normalized": "world_of_books",
        "parse_method": "vendor_world_of_books",
        "parse_confidence": 85,
        "category_hint": "books",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Extract order ID - format: WOB1053001728131
    order_match = re.search(r"(WOB\d+)", text)
    if order_match:
        result["order_id"] = order_match.group(1)
    else:
        # Fallback: generic order number
        order_match = re.search(r"order\s*(?:#|:)?\s*(\d+)", text, re.IGNORECASE)
        if order_match:
            result["order_id"] = order_match.group(1)

    # Extract line items - two formats:
    # Format 1 (text): Title/Price headers followed by book details
    # Format 2 (HTML table): <td>qty</td><td>title</td><td>status</td>
    line_items = []

    # Try HTML table format first (newer wob.com format)
    # Pattern: <td>qty</td><td>Book Title (Condition)</td><td>Status</td>
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        # Find table rows after "Title" header
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 2:
                    # Check if first cell is a quantity number
                    qty_text = cells[0].get_text(strip=True)
                    title_text = cells[1].get_text(strip=True)
                    if qty_text.isdigit() and title_text and len(title_text) >= 2:
                        # Skip rows that look like addresses or status-only
                        if (
                            "shipped" not in title_text.lower()
                            and "@" not in title_text
                        ):
                            line_items.append(
                                {
                                    "name": title_text,
                                    "quantity": int(qty_text),
                                }
                            )

    # Fallback to text format
    # Pattern: Title\nPrice\n\nBook Name\n\nGB / VERY_GOOD\n\nQty: 1\n\n£3.50
    if not line_items:
        title_match = re.search(
            r"Title\s*\n\s*Price\s*\n(.+?)(?:Subtotal|Shipping address)",
            text,
            re.DOTALL,
        )
        if title_match:
            items_section = title_match.group(1)
            lines = [l.strip() for l in items_section.split("\n") if l.strip()]

            i = 0
            while i < len(lines):
                line = lines[i]
                # Skip known non-book lines
                if line in ["tracking numbers:", "Price"] or line.startswith("Qty:"):
                    i += 1
                    continue

                # Check if this looks like a book title (not a price, not a condition code)
                if not re.match(r"^£", line) and not re.match(
                    r"^[A-Z]{2}\s*/\s*\w+", line
                ):
                    title = line
                    qty = 1
                    price = None

                    # Look ahead for qty and price
                    for j in range(i + 1, min(i + 5, len(lines))):
                        next_line = lines[j]
                        qty_match = re.match(r"Qty:\s*(\d+)", next_line)
                        if qty_match:
                            qty = int(qty_match.group(1))
                        price_match = re.match(r"£([0-9,]+\.?\d*)", next_line)
                        if price_match:
                            price = parse_amount(price_match.group(1))
                            break

                    if title and len(title) >= 2 and price is not None:
                        line_items.append(
                            {
                                "name": title,
                                "quantity": qty,
                                "price": price,
                            }
                        )

                i += 1

    # Deduplicate line items (HTML may have duplicate tables)
    if line_items:
        seen = set()
        unique_items = []
        for item in line_items:
            key = item["name"]
            if key not in seen:
                seen.add(key)
                unique_items.append(item)
        result["line_items"] = unique_items

    # Extract total amount
    amount_patterns = [
        r"Total\s*\n\s*£\s*([0-9,]+\.?\d*)",  # Total on one line, amount on next
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",  # Total: £X.XX
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id") or result.get("line_items"):
        return result
    return None


# ============================================================================
# SMOL PRODUCTS PARSER
# ============================================================================


@register_vendor(["smolproducts.com"])
def parse_smol_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """Parse Smol eco-products order confirmations."""
    result = {
        "merchant_name": "Smol",
        "merchant_name_normalized": "smol",
        "parse_method": "vendor_smol",
        "parse_confidence": 85,
        "category_hint": "household",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract order ID
    order_match = re.search(r"order\s*(?:#|:)?\s*(\d+)", text, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# CABLES4ALL PARSER
# ============================================================================


@register_vendor(["cables4all.co.uk"])
def parse_cables4all_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """Parse Cables4All order confirmations."""
    result = {
        "merchant_name": "Cables4All",
        "merchant_name_normalized": "cables4all",
        "parse_method": "vendor_cables4all",
        "parse_confidence": 85,
        "category_hint": "electronics",
        "currency_code": "GBP",
    }

    text = text_body or ""
    if html_body and not text:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text()

    # Extract order ID
    order_match = re.search(r"order\s*(?:#|:)?\s*(\d+)", text, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract amount
    amount_patterns = [
        r"Total[:\s]*£\s*([0-9,]+\.?\d*)",
        r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            break

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# GEAR4MUSIC PARSER
# ============================================================================
@register_vendor(["gear4music.com"])
def parse_gear4music_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Gear4music order confirmation emails.

    Email format:
    - Subject: "Your order W11318155 has been placed"
    - Grand Total with £ in HTML (&#163; encoded)
    - Products: "1 x AKG P5 S Dynamic Vocal Microphone..."
    """
    result = {
        "merchant_name": "Gear4music",
        "merchant_domain": "gear4music.com",
        "parse_method": "vendor_gear4music",
        "parse_confidence": 90,
        "category_hint": "music_equipment",
        "currency_code": "GBP",
    }

    # Extract order ID from subject
    order_match = re.search(r"order\s+(W\d+)", subject, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Parse HTML for details
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text(separator="\n")

        # Extract Grand Total - look for &#163; (£ encoded) pattern
        # Pattern in HTML: <strong>&#163;42.89</strong>
        amount_match = re.search(r"&#163;([0-9,]+\.?\d*)", html_body)
        if amount_match:
            result["total_amount"] = parse_amount(amount_match.group(1))
        else:
            # Fallback to text pattern
            amount_match = re.search(
                r"Grand Total.*?£\s*([0-9,]+\.?\d*)", text, re.IGNORECASE | re.DOTALL
            )
            if amount_match:
                result["total_amount"] = parse_amount(amount_match.group(1))

        # Extract line items - pattern: "1 x Product Name" followed by price
        items = []
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        for i, line in enumerate(lines):
            # Match pattern like "1 x AKG P5 S Dynamic..."
            item_match = re.match(r"^(\d+)\s*x\s+(.+)$", line)
            if item_match:
                qty = int(item_match.group(1))
                name = item_match.group(2).strip()

                # Look for price in next lines
                price = None
                for j in range(i + 1, min(i + 3, len(lines))):
                    price_match = re.search(r"^£\s*([0-9,]+\.?\d*)$", lines[j])
                    if price_match:
                        price = parse_amount(price_match.group(1))
                        break

                items.append({"name": name, "quantity": qty, "price": price})

        if items:
            result["line_items"] = items

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# UNIQLO PARSER
# ============================================================================
@register_vendor(["uniqlo.eu", "uniqlo.com", "ml.store.uniqlo.com"])
def parse_uniqlo_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Uniqlo order emails.

    Email formats:
    1. Invoice emails (ml.store.uniqlo.com):
       - Subject: "Your invoice is here" or "Here's your UNIQLO receipt"
       - Contains detailed order with products and totals
    2. Order confirmation (uniqlo.eu):
       - Subject: "Thanks, we've received your order!"
       - Contains order number but no prices
    """
    result = {
        "merchant_name": "Uniqlo",
        "merchant_domain": "uniqlo.com",
        "parse_method": "vendor_uniqlo",
        "parse_confidence": 85,
        "category_hint": "clothing",
        "currency_code": "GBP",
    }

    text = ""

    # Parse HTML for invoice emails
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text(separator="\n")

        # Extract order number from various patterns
        order_patterns = [
            r"Order Number[:\s]*([0-9\-]+)",
            r"Order:?\s*#?\s*([0-9\-]+)",
        ]
        for pattern in order_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["order_id"] = match.group(1)
                break

        # Also check subject for order number
        if not result.get("order_id"):
            order_match = re.search(
                r"Order Number[:\s]*([0-9\-]+)", subject, re.IGNORECASE
            )
            if order_match:
                result["order_id"] = order_match.group(1)

        # Extract total amount
        total_patterns = [
            r"Order Total[:\s]*£\s*([0-9,]+\.?\d*)",
            r"TOTAL[:\s]*£\s*([0-9,]+\.?\d*)",
            r"Item Subtotal[:\s]*£\s*([0-9,]+\.?\d*)",
        ]
        for pattern in total_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result["total_amount"] = parse_amount(match.group(1))
                break

        # Extract line items from invoice emails
        items = []
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        i = 0
        while i < len(lines):
            line = lines[i]
            # Product format: "47421309005000, Cotton Boxer Briefs"
            product_match = re.match(r"^(\d{10,}),\s*(.+)$", line)
            if product_match:
                product_code = product_match.group(1)
                product_name = product_match.group(2).strip()

                # Next line is usually color/size
                variant = ""
                if i + 1 < len(lines):
                    variant = lines[i + 1]

                # Look for price in following lines
                price = None
                qty = 1
                for j in range(i + 1, min(i + 6, len(lines))):
                    # Quantity pattern: "2 items" or "1 x"
                    qty_match = re.search(r"^(\d+)\s*(?:items?|x)$", lines[j])
                    if qty_match:
                        qty = int(qty_match.group(1))
                    # Price pattern
                    price_match = re.match(r"^£\s*([0-9,]+\.?\d*)$", lines[j])
                    if price_match:
                        price = parse_amount(price_match.group(1))
                        break

                full_name = product_name
                if (
                    variant
                    and not variant.startswith("Buy")
                    and not variant.startswith("Price")
                ):
                    full_name = f"{product_name} ({variant})"

                items.append({"name": full_name, "quantity": qty, "price": price})
            i += 1

        if items:
            result["line_items"] = items

    # Fallback to text body
    elif text_body:
        text = text_body
        order_match = re.search(r"Order Number[:\s]*([0-9\-]+)", text, re.IGNORECASE)
        if order_match:
            result["order_id"] = order_match.group(1)

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# BLOOMLING PARSER
# ============================================================================
@register_vendor(["bloomling.com", "bloomling.co.uk"])
def parse_bloomling_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse Bloomling (online garden store) order emails.

    Email format:
    - Subject: "Thank you for your order #NNNNNNNNNNNN"
    - Text body has product list: "1x [Product Name](url), quantity, Item no.: XXX"
    - HTML has prices in <span>£X.XX</span> format
    - Final total is the last price in the email
    """
    result = {
        "merchant_name": "Bloomling",
        "merchant_name_normalized": "bloomling",
        "merchant_domain": "bloomling.com",
        "parse_method": "vendor_bloomling",
        "parse_confidence": 90,
        "category_hint": "home_garden",
        "currency_code": "GBP",
    }

    # Extract order number from subject
    order_match = re.search(r"order\s*#?\s*(\d{10,})", subject, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Parse line items from text body
    items = []
    if text_body:
        # Pattern: "1x [Product Name](url), quantity info, Item no.: XXX"
        item_pattern = r"(\d+)x\s*\[([^\]]+)\]\([^)]+\)(?:,\s*([^,]+))?(?:,\s*Item no\.?:\s*(\S+))?"
        for match in re.finditer(item_pattern, text_body):
            qty = int(match.group(1))
            name = match.group(2).strip()
            variant = match.group(3).strip() if match.group(3) else None
            item_no = match.group(4) if match.group(4) else None

            item = {
                "name": name,
                "quantity": qty,
            }
            if item_no:
                item["sku"] = item_no
            if variant and "1 item" not in variant.lower():
                item["variant"] = variant

            items.append(item)

    # Extract prices from HTML
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")

        # Find all price spans - format: <span>£X.XX</span>
        prices = []
        for span in soup.find_all("span"):
            text = span.get_text(strip=True)
            price_match = re.match(r"^£(\d+\.?\d*)$", text)
            if price_match:
                prices.append(parse_amount(price_match.group(1)))

        # Assign prices to items (prices appear in order)
        # The structure has each price twice (once small, once bold)
        unique_prices = []
        seen = set()
        for p in prices:
            if p not in seen:
                unique_prices.append(p)
                seen.add(p)

        # Last unique price is typically the grand total
        if unique_prices:
            result["total_amount"] = unique_prices[-1]

            # Try to assign prices to items (skip last 2-3 which are subtotal/shipping/total)
            item_prices = unique_prices[:-3] if len(unique_prices) > 3 else []
            for i, item in enumerate(items):
                if i < len(item_prices):
                    item["price"] = item_prices[i]

    if items:
        result["line_items"] = items

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# O2 MOBILE PARSER
# ============================================================================
@register_vendor(["s-email-o2.co.uk", "email.o2.co.uk", "o2.co.uk"])
def parse_o2_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse O2 Mobile order confirmation emails.

    Email format:
    - Subject: "Thank you for your Order"
    - HTML contains order details in table format
    - Order number: NCxxxxxxxx
    - Plan details, phone number, monthly charges
    - Grand total (may be negative for credits)
    """
    result = {
        "merchant_name": "O2",
        "merchant_name_normalized": "o2",
        "merchant_domain": "o2.co.uk",
        "parse_method": "vendor_o2",
        "parse_confidence": 90,
        "category_hint": "mobile_phone",
        "currency_code": "GBP",
    }

    if not html_body:
        return None

    soup = BeautifulSoup(html_body, "html.parser")
    text = soup.get_text(separator="\n")

    # Extract order number (format: NCxxxxxxxx)
    order_match = re.search(
        r"Order\s*(?:number)?[:\s]*([A-Z]{2}\d{8})", text, re.IGNORECASE
    )
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract phone number being ordered/upgraded
    phone_match = re.search(r"(?:order|line)[:\s]*(\d{11})", text, re.IGNORECASE)
    if phone_match:
        result["phone_number"] = phone_match.group(1)

    # Extract plan details
    plan_match = re.search(r"plan\s+([^,\n]+(?:,\s*[^,\n]+)*)", text, re.IGNORECASE)
    if plan_match:
        result["plan_name"] = plan_match.group(1).strip()

    # Extract grand total
    # O2 emails show: "Order grand total\n-£13.99\n£0.00" (discount then final total)
    # We want the LAST non-negative amount after "Order grand total"
    grand_total_match = re.search(
        r"Order grand total(.*?)(?=\n\n|\Z)", text, re.IGNORECASE | re.DOTALL
    )
    if grand_total_match:
        section = grand_total_match.group(1)
        # Find all amounts in this section
        amounts = re.findall(r"(-)?£(\d+\.?\d*)", section)
        # Take the last non-negative amount (the final total)
        for neg, val in reversed(amounts):
            amount = parse_amount(val)
            if not neg and amount is not None:
                result["total_amount"] = amount
                break
            if neg and amount is not None:
                # If only negative found, it's a credit
                result["total_amount"] = -amount
                break

    # Extract monthly charge
    monthly_match = re.search(
        r"Monthly\s+Charge[:\s]*£?(\d+\.?\d*)", text, re.IGNORECASE
    )
    if monthly_match:
        result["monthly_charge"] = parse_amount(monthly_match.group(1))

    # Build line items from plan and charges
    items = []
    if result.get("plan_name"):
        item = {"name": result["plan_name"], "quantity": 1}
        if result.get("monthly_charge"):
            item["price"] = result["monthly_charge"]
        items.append(item)

    if items:
        result["line_items"] = items

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# REVERB PARSER
# ============================================================================
@register_vendor(["reverb.com", "email.reverb.com"])
def parse_reverb_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Reverb.com order confirmation emails.

    Reverb is a marketplace for musical instruments and gear.

    Email format:
    - Subject: "Your order of [Product Name] on Reverb"
    - HTML contains order details with prices
    - Order number is 8 digits
    """
    result = {
        "merchant_name": "Reverb",
        "merchant_name_normalized": "reverb",
        "merchant_domain": "reverb.com",
        "parse_method": "vendor_reverb",
        "parse_confidence": 90,
        "category_hint": "music_gear",
        "currency_code": "GBP",
    }

    # Extract product name from subject
    # Format: "Your order of [Product Name] on Reverb"
    product_name = None
    subject_match = re.search(r"Your order of (.+?) on Reverb", subject, re.IGNORECASE)
    if subject_match:
        product_name = subject_match.group(1).strip()

    if not html_body:
        if product_name:
            result["line_items"] = [{"name": product_name, "quantity": 1}]
            return result
        return None

    soup = BeautifulSoup(html_body, "html.parser")
    text = soup.get_text(separator="\n")

    # Extract order number (8 digits)
    order_match = re.search(r"Order\s*#?\s*(\d{7,9})", text, re.IGNORECASE)
    if order_match:
        result["order_id"] = order_match.group(1)

    # Extract prices - look for £ amounts
    prices = re.findall(r"£([\d,]+\.?\d*)", text)
    prices = [parse_amount(p) for p in prices if parse_amount(p) > 0]

    # Typical structure: item price, subtotal, shipping, total
    # Total is usually the largest or last significant amount
    if prices:
        # Find total - use findall and take LAST match (grand total appears after subtotal/shipping)
        total_matches = re.findall(
            r"Total\s*[\n\r\s]*£([\d,]+\.?\d*)", text, re.IGNORECASE
        )
        if total_matches:
            result["total_amount"] = parse_amount(
                total_matches[-1]
            )  # Last match is grand total

        # Find shipping
        shipping_match = re.search(
            r"Shipping\s*\n?\s*£([\d,]+\.?\d*)", text, re.IGNORECASE
        )
        if shipping_match:
            result["shipping"] = parse_amount(shipping_match.group(1))

        # Find subtotal/item price
        subtotal_match = re.search(
            r"Subtotal\s*\n?\s*£([\d,]+\.?\d*)", text, re.IGNORECASE
        )
        if subtotal_match:
            result["subtotal"] = parse_amount(subtotal_match.group(1))

    # Build line items
    items = []
    if product_name:
        item = {"name": product_name, "quantity": 1}
        # Use subtotal as item price (before shipping)
        if result.get("subtotal"):
            item["price"] = result["subtotal"]
        elif prices and len(prices) >= 1:
            item["price"] = prices[0]
        items.append(item)

    if items:
        result["line_items"] = items

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# GUITARGUITAR PARSER
# ============================================================================


@register_vendor(["guitarguitar.co.uk"])
def parse_guitarguitar_receipt(
    html_body: str, text_body: str, subject: str
) -> dict | None:
    """
    Parse GuitarGuitar sales receipt emails.

    Email format:
    - Subject: "GUITARGUITAR Sale Ref: XXXXXXXXX - Thanks for your order"
    - Order Number - XXXXXXX
    - Receipt Date - DD Month YYYY
    - Product table: Qty, Type, Product Description, Unit Price, Total Price
    - VAT and Sale Total at bottom
    """
    result = {
        "merchant_name": "GuitarGuitar",
        "merchant_name_normalized": "guitarguitar",
        "merchant_domain": "guitarguitar.co.uk",
        "parse_method": "vendor_guitarguitar",
        "parse_confidence": 90,
        "category_hint": "music_gear",
        "currency_code": "GBP",
    }

    # Extract Sale Ref from subject
    sale_ref_match = re.search(r"Sale Ref:\s*(\d+)", subject, re.IGNORECASE)
    if sale_ref_match:
        result["order_id"] = sale_ref_match.group(1)

    if not html_body:
        return result if result.get("order_id") else None

    soup = BeautifulSoup(html_body, "html.parser")
    text = soup.get_text(separator="\n")

    # Extract Order Number if not in subject
    if not result.get("order_id"):
        order_match = re.search(r"Order Number\s*-?\s*(\d+)", text, re.IGNORECASE)
        if order_match:
            result["order_id"] = order_match.group(1)

    # Extract Receipt Date - "30 October 2024"
    date_match = re.search(
        r"Receipt Date\s*-?\s*(\d{1,2})\s+(\w+)\s+(\d{4})", text, re.IGNORECASE
    )
    if date_match:
        day = int(date_match.group(1))
        month_name = date_match.group(2)
        year = int(date_match.group(3))
        months = {
            "january": 1,
            "february": 2,
            "march": 3,
            "april": 4,
            "may": 5,
            "june": 6,
            "july": 7,
            "august": 8,
            "september": 9,
            "october": 10,
            "november": 11,
            "december": 12,
        }
        month = months.get(month_name.lower(), 1)
        result["receipt_date"] = f"{year:04d}-{month:02d}-{day:02d}"

    # Extract Sale Total
    total_match = re.search(r"Sale Total\s*£?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if total_match:
        result["total_amount"] = parse_amount(total_match.group(1))

    # Extract VAT
    vat_match = re.search(r"VAT\s*£?([\d,]+\.?\d*)", text, re.IGNORECASE)
    if vat_match:
        result["vat_amount"] = parse_amount(vat_match.group(1))

    # Extract product items
    # Look for pattern: Product Description ... SKU: ... £price £price
    items = []

    # Find product blocks - they contain description followed by SKU
    product_pattern = r"Sale\s+([A-Z][^\n]+?)\s+SKU:\s*(\d+)[^\n]*\n?\s*£([\d,]+\.?\d*)"
    for match in re.finditer(product_pattern, text, re.IGNORECASE):
        product_name = match.group(1).strip()
        sku = match.group(2)
        price = parse_amount(match.group(3))

        # Skip shipping entries
        if "shipping" in product_name.lower() or price == 0:
            continue

        items.append(
            {
                "name": product_name,
                "sku": sku,
                "price": price,
                "quantity": 1,
            }
        )

    if items:
        result["line_items"] = items

    if result.get("total_amount") or result.get("order_id"):
        return result
    return None


# ============================================================================
# FIGMA PARSER
# ============================================================================


@register_vendor(["figma.com"])
def parse_figma_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Figma subscription receipt emails.

    Email format:
    - Subject: "Receipt for subscription payment [Month DD, YYYY]"
    - Contains subscription details and payment amount
    """
    result = {
        "merchant_name": "Figma",
        "merchant_name_normalized": "figma",
        "merchant_domain": "figma.com",
        "parse_method": "vendor_figma",
        "parse_confidence": 85,
        "category_hint": "software_subscription",
        "currency_code": "USD",  # Figma typically charges in USD
    }

    # Extract date from subject "Receipt for subscription payment Nov 30, 2025"
    date_match = re.search(r"(\w{3})\s+(\d{1,2}),?\s+(\d{4})", subject, re.IGNORECASE)
    if date_match:
        month_abbr = date_match.group(1)
        day = int(date_match.group(2))
        year = int(date_match.group(3))
        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = months.get(month_abbr.lower(), 1)
        result["receipt_date"] = f"{year:04d}-{month:02d}-{day:02d}"

    if not html_body and not text_body:
        return result if result.get("receipt_date") else None

    # Prefer HTML for parsing as text_body may be empty or minimal
    text = ""
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        text = soup.get_text(separator="\n")
    elif text_body and text_body.strip():
        text = text_body

    # Look for amount - could be $ or £
    # Figma format: "Total: £201.60 GBP" or "Total:\n £201.60 GBP"
    amount_patterns = [
        r"Total:?\s*[\n\s]*£([\d,]+\.?\d*)",  # Total: £201.60
        r"Total:?\s*[\n\s]*\$([\d,]+\.?\d*)",  # Total: $15.00
        r"£([\d,]+\.?\d*)\s*GBP",  # £201.60 GBP
        r"\$([\d,]+\.\d{2})\s*USD",  # $15.00 USD
    ]

    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result["total_amount"] = parse_amount(match.group(1))
            # Detect currency from the pattern or symbol
            if "£" in pattern or "£" in match.group(0):
                result["currency_code"] = "GBP"
            break

    # Look for subscription type - "Professional team (annual)"
    sub_match = re.search(
        r"(Professional|Organization|Team|Starter)\s+(team\s+)?\((annual|monthly)\)",
        text,
        re.IGNORECASE,
    )
    if sub_match:
        plan_type = sub_match.group(1).title()
        billing = sub_match.group(3).lower() if sub_match.group(3) else "subscription"
        result["line_items"] = [
            {
                "name": f"Figma {plan_type} ({billing})",
                "quantity": 1,
                "price": result.get("total_amount"),
            }
        ]

    if result.get("total_amount") or result.get("receipt_date"):
        return result
    return None


# ============================================================================
# LIME SCOOTER PARSER
# ============================================================================


@register_vendor(["li.me"])
def parse_lime_receipt(html_body: str, text_body: str, subject: str) -> dict | None:
    """
    Parse Lime scooter receipt/refund emails.

    Email format:
    - Subject: "Receipt for your refund" or "Receipt For Your Refund"
    - Date of issue: DD Mon YYYY
    - Distance, ride times
    - Fee breakdown (Start Fee, Riding, Subtotal, VAT)
    - Refund amount (negative) or charge amount
    """
    is_refund = "refund" in subject.lower()

    result = {
        "merchant_name": "Lime",
        "merchant_name_normalized": "lime",
        "merchant_domain": "li.me",
        "parse_method": "vendor_lime",
        "parse_confidence": 85,
        "category_hint": "transport_scooter",
        "currency_code": "GBP",
    }

    if not html_body:
        return None

    soup = BeautifulSoup(html_body, "html.parser")
    text = soup.get_text(separator="\n")

    # Extract date - "Date of issue: 07 Sep 2024"
    date_match = re.search(
        r"Date of issue:\s*(\d{1,2})\s+(\w{3})\s+(\d{4})", text, re.IGNORECASE
    )
    if date_match:
        day = int(date_match.group(1))
        month_abbr = date_match.group(2)
        year = int(date_match.group(3))
        months = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month = months.get(month_abbr.lower(), 1)
        result["receipt_date"] = f"{year:04d}-{month:02d}-{day:02d}"

    # Find refund or total amount
    # Refund pattern: "Refunded to Apple Pay -£6.22"
    # Or total pattern near end
    if is_refund:
        refund_match = re.search(
            r"Refunded\s+(?:to\s+\w+\s+\w+\s+)?-?£([\d,]+\.?\d*)", text, re.IGNORECASE
        )
        if refund_match:
            # Store as negative for refunds
            result["total_amount"] = -parse_amount(refund_match.group(1))
    else:
        # Look for total/charged amount
        total_match = re.search(
            r"(?:Total|Charged)\s*[\n\s]*£([\d,]+\.?\d*)", text, re.IGNORECASE
        )
        if total_match:
            result["total_amount"] = parse_amount(total_match.group(1))

    # Extract ride description
    distance_match = re.search(r"([\d.]+)\s*mi\s+distance", text, re.IGNORECASE)
    time_match = re.search(
        r"(\d+:\d+\s*[AP]\.?M\.?)\s*-\s*(\d+:\d+\s*[AP]\.?M\.?)", text, re.IGNORECASE
    )

    if distance_match:
        distance = distance_match.group(1)
        ride_desc = f"Lime ride ({distance} miles)"
        if is_refund:
            ride_desc = f"Lime ride refund ({distance} miles)"
        result["line_items"] = [
            {
                "name": ride_desc,
                "quantity": 1,
                "price": result.get("total_amount"),
            }
        ]

    if result.get("total_amount") or result.get("receipt_date"):
        return result
    return None
