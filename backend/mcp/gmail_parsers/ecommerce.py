"""
E-commerce Parsers

eBay, Etsy, Vinted
"""

from bs4 import BeautifulSoup
import re
from typing import Optional

from .base import register_vendor, parse_amount, parse_date_text


@register_vendor(['ebay.co.uk', 'ebay.com', 'ebay.de', 'ebay.fr', 'ebay.com.au'])
def parse_ebay_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
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
        'merchant_name': 'eBay',
        'merchant_name_normalized': 'ebay',
        'parse_method': 'vendor_ebay',
        'parse_confidence': 90,
    }

    subject_lower = subject.lower()

    # Reject if subject indicates marketing email
    marketing_indicators = [
        'watchlist', 'price drop', 'deals', 'ending soon', 'recommended',
        'top picks', 'you might like', 'saved search', 'daily deals',
    ]
    for indicator in marketing_indicators:
        if indicator in subject_lower:
            return None  # Not an order confirmation

    # Verify this is an order confirmation
    receipt_indicators = [
        'order confirmed', 'your order is confirmed', 'thanks for your order',
        'you paid for your item', 'payment sent', "you've paid",
    ]
    is_order_email = any(ind in subject_lower for ind in receipt_indicators)
    if not is_order_email:
        return None

    # Extract item name from subject
    item_name = extract_ebay_item_from_subject(subject)

    if html_body:
        soup = BeautifulSoup(html_body, 'html.parser')

        # Extract order details from structured HTML
        order_data = extract_ebay_order_details(soup)

        # Merge extracted data
        if order_data.get('order_number'):
            result['order_id'] = order_data['order_number']
        elif order_data.get('transaction_id'):
            result['order_id'] = order_data['transaction_id']

        if order_data.get('item_id'):
            result['ebay_item_id'] = order_data['item_id']
        if order_data.get('transaction_id'):
            result['ebay_transaction_id'] = order_data['transaction_id']
        if order_data.get('price'):
            result['total_amount'] = order_data['price']
        if order_data.get('currency'):
            result['currency_code'] = order_data['currency']
        if order_data.get('seller'):
            result['seller_name'] = order_data['seller']

        # Get item name from HTML if not in subject
        if not item_name and order_data.get('item_name'):
            item_name = order_data['item_name']

    # Build line items
    if item_name:
        cleaned_name = clean_ebay_product_name(item_name)
        item = {
            'name': cleaned_name,
            'description': infer_ebay_description(item_name),
            'category_hint': infer_ebay_category(item_name),
            'quantity': 1,
            'price': result.get('total_amount'),
        }
        # Extract brand from product name
        brand = extract_product_brand(cleaned_name)
        if brand:
            item['brand'] = brand
        # Add seller name if available
        if result.get('seller_name'):
            item['seller'] = result['seller_name']
        result['line_items'] = [item]

    # Validate we have essential data
    if result.get('total_amount') or result.get('order_id'):
        return result

    return None




@register_vendor(['vinted.co.uk', 'vinted.com', 'vinted.fr', 'vinted.de'])
def parse_vinted_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse Vinted purchase receipts.

    Email format:
    - Subject: Your receipt for "[Item Name]"
    - Body contains: Seller, Order (item name), Paid amount with breakdown
    - Paid: £X.XX (postage: £X.XX + item: £X.XX + Buyer Protection fee: £X.XX)
    """
    result = {
        'merchant_name': 'Vinted',
        'merchant_name_normalized': 'vinted',
        'parse_method': 'vendor_vinted',
        'parse_confidence': 90,
        'category_hint': 'clothing',
        'currency_code': 'GBP',
    }

    # Extract item name from subject: Your receipt for "Item Name"
    item_match = re.search(r'receipt for ["\u201c]([^"\u201d]+)["\u201d]', subject, re.IGNORECASE)
    if item_match:
        item_name = item_match.group(1).strip()
        result['line_items'] = [{'name': item_name}]

    # Use text body or extract from HTML
    text = text_body or ''
    if html_body and not text:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    # Extract total paid amount: "Paid: £19.44" or "Paid: £19.44 (breakdown...)"
    paid_match = re.search(r'Paid[:\s]*£\s*([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if paid_match:
        result['total_amount'] = parse_amount(paid_match.group(1))

    # Extract seller name
    seller_match = re.search(r'Seller[:\s]*(\w+)', text, re.IGNORECASE)
    if seller_match:
        result['seller_name'] = seller_match.group(1)

    # Extract breakdown if available
    postage_match = re.search(r'postage[:\s]*£\s*([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if postage_match:
        result['postage_amount'] = parse_amount(postage_match.group(1))

    item_price_match = re.search(r'item[:\s]*£\s*([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if item_price_match:
        result['item_amount'] = parse_amount(item_price_match.group(1))
        # Update line item with price
        if result.get('line_items'):
            result['line_items'][0]['price'] = result['item_amount']

    protection_match = re.search(r'(?:Buyer\s+)?Protection(?:\s+fee)?[:\s]*£\s*([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if protection_match:
        result['protection_fee'] = parse_amount(protection_match.group(1))

    # Validate - must have amount
    if result.get('total_amount'):
        return result

    return None


# ============================================================================
# FASTSPRING PARSER (software purchases)
# ============================================================================



@register_vendor(['etsy.com'])
def parse_etsy_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse Etsy purchase receipts.

    Email format:
    - Subject: "Your Etsy Purchase from {SellerName} ({order_id})"
    - Body contains: Order summary, items, prices, totals

    Note: Dispatch notifications ("Your Etsy Order dispatched...") should be
    filtered out before reaching this parser.
    """
    result = {
        'merchant_name': 'Etsy',
        'merchant_name_normalized': 'etsy',
        'parse_method': 'vendor_etsy',
        'parse_confidence': 90,
        'category_hint': 'marketplace',
        'currency_code': 'GBP',
    }

    # Extract seller name and order ID from subject
    # Pattern: "Your Etsy Purchase from SellerName (order_id)"
    subject_match = re.search(
        r'Your Etsy Purchase from\s+(.+?)\s*\((\d+)\)',
        subject,
        re.IGNORECASE
    )
    if subject_match:
        result['seller_name'] = subject_match.group(1).strip()
        result['order_id'] = subject_match.group(2).strip()

    # Use text body or extract from HTML
    text = text_body or ''
    if html_body and not text:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    # Extract total amount - Etsy uses various patterns
    # "Order total: £12.34" or "Total: £12.34" or "Grand total £12.34"
    total_patterns = [
        r'(?:Order\s+)?[Tt]otal[:\s]*£\s*([0-9,]+\.?\d*)',
        r'(?:Grand\s+)?[Tt]otal[:\s]*£\s*([0-9,]+\.?\d*)',
        r'(?:Order\s+)?[Tt]otal[:\s]*\$\s*([0-9,]+\.?\d*)',
        r'(?:Grand\s+)?[Tt]otal[:\s]*€\s*([0-9,]+\.?\d*)',
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            # Detect currency from pattern
            if '€' in pattern:
                result['currency_code'] = 'EUR'
            elif '$' in pattern:
                result['currency_code'] = 'USD'
            break

    # Extract shipping cost if present
    shipping_match = re.search(r'Shipping[:\s]*£\s*([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if shipping_match:
        result['shipping_amount'] = parse_amount(shipping_match.group(1))

    # Try to extract item names from the order summary
    # Etsy items often appear in structured lists
    item_patterns = [
        r'Item[:\s]*(.+?)(?:\s*Qty|\s*£|\n)',
        r'([^£€$\n]+?)\s*×\s*\d+\s*£\s*[0-9,]+\.?\d*',
    ]
    items = []
    for pattern in item_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            item_name = match.strip() if isinstance(match, str) else match[0].strip()
            if item_name and len(item_name) > 3 and len(item_name) < 200:
                # Filter out common non-item text
                if not any(skip in item_name.lower() for skip in ['order', 'total', 'shipping', 'subtotal', 'tax', 'etsy']):
                    item = {'name': item_name}
                    if result.get('seller_name'):
                        item['seller'] = result['seller_name']
                    items.append(item)
        if items:
            break

    if items:
        result['line_items'] = items
    elif result.get('seller_name'):
        # Fallback: Create basic item with seller
        result['line_items'] = [{
            'name': f"Purchase from {result['seller_name']}",
            'seller': result['seller_name']
        }]

    # Validate - need at least order_id (from subject) or amount
    if result.get('total_amount') or result.get('order_id'):
        return result

    return None


# ============================================================================
# BLACK SHEEP COFFEE PARSER (coffee shop orders)
# ============================================================================



