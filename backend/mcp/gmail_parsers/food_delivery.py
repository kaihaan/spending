"""
Food Delivery Parsers

Deliveroo
"""

from bs4 import BeautifulSoup
import re
from typing import Optional

from .base import register_vendor, parse_amount, parse_date_text


@register_vendor(['deliveroo.co.uk', 'deliveroo.com'])
def parse_deliveroo_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
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
        'merchant_name': 'Deliveroo',
        'merchant_name_normalized': 'deliveroo',
        'parse_method': 'vendor_deliveroo',
        'parse_confidence': 85,
        'category_hint': 'food_delivery',
        'currency_code': 'GBP',
    }

    # Prefer text_body for parsing (more structured than HTML)
    # Normalize line endings
    text = (text_body or '').replace('\r\n', '\n').replace('\r', '\n')
    if not text and html_body:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    if not text:
        return None

    # Extract restaurant name - multiple patterns
    restaurant = None

    # Pattern 1: "{Restaurant} has your order!" (new format)
    rest_match = re.search(r'([\w][\w\s&\'\-]+)\s+has your order', text)
    if rest_match:
        restaurant = rest_match.group(1).strip()

    # Pattern 2: From subject - "order from {Restaurant}"
    if not restaurant:
        subject_patterns = [
            r'order from\s+(.+?)(?:\s*-|\s*$)',
            r'from\s+([A-Za-z0-9\s&\'\-]+?)(?:\s*order|\s*-|\s*$)',
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
        r'Total\s+£([\d,.]+)',
        r'Total[:\s]*£\s*([\d,]+\.?\d*)',
        r'Order total[:\s]*£\s*([\d,]+\.?\d*)',
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            break

    # Extract individual line items
    # Format: "3x    Naan Bread  - £2.00"
    line_items = []
    item_pattern = r'(\d+)x\s+(.+?)\s+-\s+£([\d.]+)'
    for match in re.finditer(item_pattern, text):
        qty = int(match.group(1))
        name = match.group(2).strip()
        price = parse_amount(match.group(3))
        # Skip modifiers (lines starting with --)
        if not name.startswith('--'):
            item = {
                'name': name,
                'quantity': qty,
                'price': price
            }
            # Add restaurant as brand/source for food items
            if restaurant:
                item['restaurant'] = restaurant
                item['brand'] = restaurant  # Restaurant is the brand for food delivery
            line_items.append(item)

    # Set line_items - prefer extracted items, fallback to restaurant name
    if line_items:
        result['line_items'] = line_items
    elif restaurant:
        result['line_items'] = [{
            'name': f"Order from {restaurant}",
            'restaurant': restaurant,
            'brand': restaurant  # Restaurant is the brand for food delivery
        }]

    if restaurant:
        result['restaurant_name'] = restaurant

    # Extract order ID from text
    order_match = re.search(r'Order #(\d+)', text)
    if order_match:
        result['order_id'] = order_match.group(1)

    # Extract delivery completion date
    date_patterns = [
        r'Delivered on\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})',  # "Delivered on June 15, 2024"
        r'Order completed[:\s]+(\d{1,2}/\d{1,2}/\d{4})',   # "Order completed: 15/06/2024"
        r'(\d{1,2}\s+[A-Za-z]+\s+\d{4})',                   # "15 June 2024"
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            # Try multiple formats
            for fmt in ['%B %d, %Y', '%d/%m/%Y', '%d %B %Y']:
                try:
                    from datetime import datetime
                    result['receipt_date'] = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue
            if result.get('receipt_date'):
                break

    if result.get('total_amount'):
        return result

    return None


# ============================================================================
# EBAY PARSER
# ============================================================================



