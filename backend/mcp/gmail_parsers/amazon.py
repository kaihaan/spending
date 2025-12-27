"""
Amazon Email Parser

Handles all Amazon email types:
- Standard orders
- Amazon Fresh grocery orders
- Amazon Business orders
- Order cancellations
- Refunds
- "Ordered:" notification emails
"""

import re

from bs4 import BeautifulSoup

from .base import parse_amount, parse_date_text, register_vendor


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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


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
