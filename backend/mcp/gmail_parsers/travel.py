"""
Travel Parsers

Airbnb, British Airways, DHL
"""

from bs4 import BeautifulSoup
import re
from typing import Optional

from .base import register_vendor, parse_amount, parse_date_text


@register_vendor(['airbnb.com', 'airbnb.co.uk'])
def parse_airbnb_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
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
        'merchant_name': 'Airbnb',
        'merchant_name_normalized': 'airbnb',
        'parse_method': 'vendor_airbnb',
        'parse_confidence': 90,
        'category_hint': 'travel',
        'currency_code': 'GBP',
    }

    # Use text body (cleaner structure)
    text = text_body or ''
    if html_body and not text:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    # Extract Receipt ID
    receipt_match = re.search(r'Receipt ID[:\s]*([A-Z0-9]+)', text, re.IGNORECASE)
    if receipt_match:
        result['order_id'] = receipt_match.group(1)

    # Extract Confirmation code
    confirm_match = re.search(r'Confirmation code[:\s]*([A-Z0-9]+)', text, re.IGNORECASE)
    if confirm_match:
        result['confirmation_code'] = confirm_match.group(1)

    # Extract receipt date (from Receipt ID line: "Receipt ID: RCJTZQP29T · 29 September 2025")
    date_match = re.search(r'Receipt ID[:\s]*[A-Z0-9]+\s*[·•]\s*(\d{1,2}\s+\w+\s+\d{4})', text, re.IGNORECASE)
    if date_match:
        result['receipt_date'] = parse_date_text(date_match.group(1))

    # Extract property/location
    location_match = re.search(r'nights? in\s+(.+?)(?:\n|$)', text, re.IGNORECASE)
    if location_match:
        result['product_name'] = location_match.group(1).strip()

    # Extract stay dates
    stay_match = re.search(r'(\w{3},\s+\d{1,2}\s+\w+\s+\d{4})\s*->\s*(\w{3},\s+\d{1,2}\s+\w+\s+\d{4})', text)
    if stay_match:
        result['stay_start'] = stay_match.group(1)
        result['stay_end'] = stay_match.group(2)

    # Extract total amount (e.g., "Total (GBP)   £1,576.80" or "Amount paid (GBP)   £1,576.80")
    total_patterns = [
        r'Total\s*\(GBP\)\s*£([0-9,]+\.?\d*)',
        r'Amount paid\s*\(GBP\)\s*£([0-9,]+\.?\d*)',
        r'Total\s*£([0-9,]+\.?\d*)',
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            break

    # Extract service fee
    fee_match = re.search(r'(?:Airbnb\s+)?service fee\s+£([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if fee_match:
        result['service_fee'] = parse_amount(fee_match.group(1))

    # Extract taxes
    tax_match = re.search(r'Taxes\s+£([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if tax_match:
        result['tax_amount'] = parse_amount(tax_match.group(1))

    # Extract payment method
    payment_match = re.search(r'(MASTERCARD|VISA|AMEX)[^\d]*(\d{4})', text, re.IGNORECASE)
    if payment_match:
        result['payment_method'] = f"{payment_match.group(1)} •••• {payment_match.group(2)}"

    # Set line_items with property name and stay dates
    if result.get('product_name'):
        item = {
            'name': f"Stay in {result['product_name']}",
            'property_name': result['product_name']
        }
        if result.get('stay_start') and result.get('stay_end'):
            item['stay_dates'] = f"{result['stay_start']} - {result['stay_end']}"
        result['line_items'] = [item]
    else:
        result['line_items'] = [{'name': 'Airbnb stay', 'property_name': 'Unknown'}]

    # Validate
    if result.get('total_amount') or result.get('order_id'):
        return result

    return None


# ============================================================================
# ATLASSIAN PARSER
# ============================================================================



@register_vendor(['crm.ba.com', 'ba.com'])
def parse_british_airways_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse British Airways booking confirmation emails.

    Email format:
    - Subject: "Your booking confirmation X8I5PF"
    - Body contains: booking reference, flight details, passenger info, total
    """
    result = {
        'merchant_name': 'British Airways',
        'merchant_name_normalized': 'british_airways',
        'parse_method': 'vendor_british_airways',
        'parse_confidence': 90,
        'category_hint': 'travel',
        'currency_code': 'GBP',
    }

    # Extract booking reference from subject
    ref_match = re.search(r'confirmation\s+([A-Z0-9]{6})', subject, re.IGNORECASE)
    if ref_match:
        result['order_id'] = ref_match.group(1)

    # Use text body or extract from HTML
    text = text_body or ''
    if html_body and not text:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    # Extract flights as line items
    line_items = []
    # Pattern: "London - Belfast" or "City to City"
    flight_pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*(?:-|to)\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
    flight_matches = re.findall(flight_pattern, text)
    seen_routes = set()
    for origin, dest in flight_matches:
        route = f"{origin} to {dest}"
        if route not in seen_routes and origin.lower() not in ['economy', 'euro', 'business']:
            seen_routes.add(route)
            line_items.append({'name': f"Flight: {route}"})

    # Extract flight numbers
    flight_nums = re.findall(r'\bBA\s*(\d{3,4})\b', text)
    for i, num in enumerate(flight_nums[:len(line_items)]):
        if i < len(line_items):
            line_items[i]['name'] += f" (BA{num})"

    if line_items:
        result['line_items'] = line_items[:4]  # Max 4 flights

    # Extract total amount
    amount_patterns = [
        r'Total[:\s]*£\s*([0-9,]+\.?\d*)',
        r'Grand Total[:\s]*£\s*([0-9,]+\.?\d*)',
        r'Amount paid[:\s]*£\s*([0-9,]+\.?\d*)',
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            break

    if result.get('total_amount') or result.get('order_id'):
        return result
    return None


# ============================================================================
# AUDIO EMOTION PARSER
# ============================================================================



@register_vendor(['dhl.com', 'dhl.co.uk'])
def parse_dhl_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """Parse DHL duty/tax payment receipts."""
    result = {
        'merchant_name': 'DHL',
        'merchant_name_normalized': 'dhl',
        'parse_method': 'vendor_dhl',
        'parse_confidence': 85,
        'category_hint': 'shipping',
        'currency_code': 'GBP',
    }

    text = text_body or ''
    if html_body and not text:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    # Extract waybill/tracking number
    waybill_match = re.search(r'waybill[:\s]*(\d+)', text, re.IGNORECASE)
    if waybill_match:
        result['order_id'] = waybill_match.group(1)

    # Extract amount
    amount_patterns = [
        r'Total[:\s]*£\s*([0-9,]+\.?\d*)',
        r'Amount[:\s]*£\s*([0-9,]+\.?\d*)',
        r'Payment[:\s]*£\s*([0-9,]+\.?\d*)',
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            break

    if result.get('total_amount') or result.get('order_id'):
        return result
    return None


# ============================================================================
# WORLDPAY PARSER
# ============================================================================



