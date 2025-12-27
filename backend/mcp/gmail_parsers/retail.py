"""
Retail Parsers

John Lewis, Uniqlo, CEX, etc.
"""

import re

from bs4 import BeautifulSoup

from .base import parse_amount, register_vendor


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
