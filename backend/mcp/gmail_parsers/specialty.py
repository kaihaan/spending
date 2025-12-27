"""
Specialty Parsers

All other vendors
"""

import re

from bs4 import BeautifulSoup

from .base import parse_amount, register_vendor


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
