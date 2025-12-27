"""
Apple Email Parser

Handles Apple App Store and iTunes receipts/invoices.
Supports both new (2024+) and old (pre-2024) email formats.
"""

from bs4 import BeautifulSoup
import re
from typing import Optional

from .base import register_vendor, parse_amount, parse_date_text


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
        ('=C2=A3', '£'),      # GBP symbol
        ('=C2=A0', ' '),      # Non-breaking space
        ('=E2=80=A2', '•'),   # Bullet point
        ('=\n', ''),          # Line continuation
    ]

    result = text
    for encoded, decoded in replacements:
        result = result.replace(encoded, decoded)

    return result


@register_vendor(['apple.com', 'itunes.com', 'email.apple.com'])
def parse_apple_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
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
        'merchant_name': 'Apple',
        'merchant_name_normalized': 'apple',
        'parse_method': 'vendor_apple',
        'parse_confidence': 90,
        'category_hint': 'subscription',
        'currency_code': 'GBP',  # Default for UK invoices
    }

    if not html_body:
        return None

    # Decode quoted-printable content first
    decoded_html = decode_quoted_printable_amount(html_body)
    soup = BeautifulSoup(decoded_html, 'html.parser')

    # Detect format: new format has custom-* classes, old format has aapl-desktop-tbl
    is_new_format = soup.find('p', class_=lambda x: x and x.startswith('custom-')) is not None

    if is_new_format:
        # === NEW FORMAT (2024+) with CSS classes ===
        result = _parse_apple_new_format(soup, result)
    else:
        # === OLD FORMAT (pre-2024) with table-based layout ===
        result = _parse_apple_old_format(soup, decoded_html, result)

    # Build line items
    subscription_details = result.get('subscription_details', [])
    line_items = []
    if result.get('product_name'):
        item = {
            'name': result['product_name'],
            'description': result.get('subscription_name', infer_apple_description(result['product_name'])),
            'category_hint': infer_apple_category(result['product_name']),
            'quantity': 1,
            'price': result.get('total_amount'),
            'brand': result['product_name'],  # App/service name (normalized from app_name)
            'app_name': result['product_name'],  # Kept for backward compatibility
        }
        # Add renewal info if available
        for detail in subscription_details:
            if 'renews' in detail.lower():
                item['renewal_date'] = detail
                break
        line_items.append(item)

    if line_items:
        result['line_items'] = line_items

    # Validate - must have amount or order ID
    if result.get('total_amount') or result.get('order_id'):
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
    date_elem = soup.find('p', class_='custom-18w16cf')
    if date_elem:
        date_text = date_elem.get_text(strip=True)
        parsed_date = parse_date_text(date_text)
        if parsed_date:
            result['receipt_date'] = parsed_date

    # Extract Order ID
    order_id = extract_apple_field_value(soup, 'Order ID')
    if order_id:
        result['order_id'] = order_id

    # Extract Document number (Apple's invoice number)
    document = extract_apple_field_value(soup, 'Document')
    if document:
        result['document_id'] = document

    # Extract Sequence number
    sequence = extract_apple_field_value(soup, 'Sequence')
    if sequence:
        result['sequence_id'] = sequence

    # Extract product/app name (in custom-gzadzy class - bold product name)
    product_elem = soup.find('p', class_='custom-gzadzy')
    if product_elem:
        result['product_name'] = product_elem.get_text(strip=True)

    # Extract subscription details (in custom-wogfc8 class)
    subscription_elems = soup.find_all('p', class_='custom-wogfc8')
    subscription_details = []
    for elem in subscription_elems:
        text = elem.get_text(strip=True)
        if text and len(text) > 2:
            subscription_details.append(text)
    if subscription_details:
        result['subscription_details'] = subscription_details
        # First detail is usually the subscription name
        if subscription_details:
            result['subscription_name'] = subscription_details[0]

    # Extract item amount (in custom-137u684 class - bold amount)
    amount_elem = soup.find('p', class_='custom-137u684')
    if amount_elem:
        amount_text = amount_elem.get_text(strip=True)
        amount = parse_amount(amount_text)
        if amount:
            result['total_amount'] = amount

    # Extract VAT amount (in custom-vr1cqx span)
    vat_elem = soup.find('span', class_='custom-vr1cqx')
    if vat_elem:
        vat_text = vat_elem.get_text(strip=True)
        vat_amount = parse_amount(vat_text)
        if vat_amount:
            result['vat_amount'] = vat_amount

    # Extract subtotal (in custom-1s7arqf class after "Subtotal")
    subtotal = extract_apple_subtotal(soup)
    if subtotal:
        result['subtotal'] = subtotal

    # Extract payment method (in custom-15zbox7 class)
    payment_elem = soup.find('p', class_='custom-15zbox7')
    if payment_elem:
        payment_text = payment_elem.get_text(strip=True)
        result['payment_method'] = payment_text

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
    date_match = re.search(r'INVOICE DATE</span>.*?<span[^>]*>(\d{1,2}\s+\w+\s+\d{4})</span>', html_body, re.IGNORECASE | re.DOTALL)
    if date_match:
        parsed_date = parse_date_text(date_match.group(1))
        if parsed_date:
            result['receipt_date'] = parsed_date

    # Extract Order ID: <span style="...">ORDER ID</span><br><span...><a href="...">MM61N78HGZ</a></span>
    order_match = re.search(r'ORDER ID</span>.*?<a[^>]*>([A-Z0-9]+)</a>', html_body, re.IGNORECASE | re.DOTALL)
    if order_match:
        result['order_id'] = order_match.group(1)
    else:
        # Alternative: ORDER ID without link
        order_match2 = re.search(r'ORDER ID</span>.*?<br[^>]*>\s*([A-Z0-9]+)', html_body, re.IGNORECASE | re.DOTALL)
        if order_match2:
            result['order_id'] = order_match2.group(1)

    # Extract Document No: <span style="...">DOCUMENT NO.</span><br>216891678188
    doc_match = re.search(r'DOCUMENT NO\.</span>.*?<br[^>]*>\s*(\d+)', html_body, re.IGNORECASE | re.DOTALL)
    if doc_match:
        result['document_id'] = doc_match.group(1)

    # Extract Sequence No: <span style="...">SEQUENCE NO.</span><br>2-6358439100
    seq_match = re.search(r'SEQUENCE NO\.</span>.*?<br[^>]*>\s*([0-9-]+)', html_body, re.IGNORECASE | re.DOTALL)
    if seq_match:
        result['sequence_id'] = seq_match.group(1)

    # Extract Product name: <span style="font-size:14px;font-weight:500;">Apple TV</span>
    product_match = re.search(r'font-weight:\s*500[^>]*>\s*([^<]+)</span>', html_body)
    if product_match:
        result['product_name'] = product_match.group(1).strip()

    # Extract Total amount: after "TOTAL" label, look for £X.XX
    # Pattern: <td...>TOTAL</td>...£8.99
    total_match = re.search(r'>TOTAL</td>.*?£(\d+\.?\d*)', html_body, re.IGNORECASE | re.DOTALL)
    if total_match:
        result['total_amount'] = float(total_match.group(1))
    else:
        # Alternative: look for bold amount after item name
        # <span style="font-weight:600;white-space:nowrap;">£8.99</span>
        amounts = re.findall(r'font-weight:\s*600[^>]*>\s*£(\d+\.?\d*)\s*</span>', html_body)
        if amounts:
            # Last bold amount is usually the total
            result['total_amount'] = float(amounts[-1])

    # Extract VAT: look for VAT pattern with amount
    vat_match = re.search(r'VAT.*?£(\d+\.?\d*)', html_body, re.IGNORECASE)
    if vat_match:
        result['vat_amount'] = float(vat_match.group(1))

    # Extract Subtotal
    subtotal_match = re.search(r'>Subtotal</span>.*?£(\d+\.?\d*)', html_body, re.IGNORECASE | re.DOTALL)
    if subtotal_match:
        result['subtotal'] = float(subtotal_match.group(1))

    return result


def extract_apple_field_value(soup: BeautifulSoup, field_name: str) -> Optional[str]:
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
    for label in soup.find_all('p', class_='custom-f41j3e'):
        if field_name.lower() in label.get_text().lower():
            # The value should be in the next sibling with custom-zresjj class
            next_sibling = label.find_next_sibling('p', class_='custom-zresjj')
            if next_sibling:
                return next_sibling.get_text(strip=True).replace('<br/>', '').strip()

    return None


def extract_apple_subtotal(soup: BeautifulSoup) -> Optional[float]:
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
    for elem in soup.find_all('p', class_='custom-4tra68'):
        if 'subtotal' in elem.get_text().lower():
            # Look for amount in nearby custom-68yyeh div
            parent = elem.find_parent()
            if parent:
                amount_elem = parent.find('p', class_='custom-1s7arqf')
                if amount_elem:
                    return parse_amount(amount_elem.get_text(strip=True))
    return None


def infer_apple_description(name: str) -> Optional[str]:
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
        (r'icloud|storage', 'cloud storage subscription'),
        (r'apple music|music subscription', 'music streaming subscription'),
        (r'apple tv', 'video streaming subscription'),
        (r'tv\+', 'Apple TV+ subscription'),
        (r'apple arcade', 'gaming subscription'),
        (r'apple one', 'bundled services subscription'),
        (r'apple news', 'news subscription'),
        (r'apple fitness', 'fitness subscription'),
        (r'in-app purchase|in app', 'in-app purchase'),
        (r'bfi player', 'BFI streaming subscription'),
        (r'hazard perception', 'driving test preparation'),
        (r'subscription', 'subscription service'),
        (r'app$|\.app', 'mobile application'),
        (r'game', 'mobile game'),
    ]

    for pattern, desc in patterns:
        if re.search(pattern, name_lower):
            return desc

    return 'app/digital content'


def infer_apple_category(name: str) -> str:
    """
    Infer category for Apple items.

    Args:
        name: Item name

    Returns:
        Category hint
    """
    if not name:
        return 'subscription'

    name_lower = name.lower()

    if re.search(r'icloud|storage|apple one|music|tv\+|arcade|news|fitness|apple tv|bfi|player', name_lower):
        return 'subscription'
    if re.search(r'game|games', name_lower):
        return 'entertainment'
    if re.search(r'in-app|coins|gems|premium', name_lower):
        return 'entertainment'
    if re.search(r'hazard|driving|test|education', name_lower):
        return 'education'

    return 'subscription'
