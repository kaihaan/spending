"""
Gmail Pattern-based Extraction

Regex pattern-based extraction of receipt data from email content.
Uses domain mappings, sender patterns, and common receipt formats.
"""

from typing import Optional

from .utilities import (
    extract_amount,
    extract_date,
    extract_order_id,
    extract_merchant_from_text,
    get_sender_pattern,
    normalize_merchant_name,
)


def extract_with_patterns(
    subject: str,
    body_text: str,
    sender_domain: str,
    sender_email: str,
    sender_name: str = None
) -> Optional[dict]:
    """
    Extract receipt data using regex patterns.

    Args:
        subject: Email subject line
        body_text: Plain text body content
        sender_domain: Sender's domain
        sender_email: Full sender email
        sender_name: Sender display name from email header

    Returns:
        Parsed receipt dictionary or None
    """
    combined_text = f"{subject}\n{body_text}"

    # Try to get sender-specific patterns from database
    sender_pattern = get_sender_pattern(sender_domain)

    # Extract merchant name
    merchant_name = None
    if sender_pattern:
        merchant_name = sender_pattern.get('merchant_name')
    else:
        # Try to extract from common patterns (uses domain mapping -> sender name -> subject)
        merchant_name = extract_merchant_from_text(subject, sender_email, sender_domain, sender_name)

    # Extract total amount and currency
    total_amount, currency = extract_amount(combined_text)

    # Extract order ID
    order_id = extract_order_id(combined_text)

    # Extract date
    receipt_date = extract_date(combined_text)

    # Only return if we found meaningful data
    if total_amount is not None or merchant_name:
        return {
            'merchant_name': merchant_name,
            'merchant_name_normalized': normalize_merchant_name(merchant_name),
            'order_id': order_id,
            'total_amount': total_amount,
            'currency_code': currency or 'GBP',
            'receipt_date': receipt_date,
            'line_items': None,
            'parse_method': 'pattern',
            'parse_confidence': 80 if total_amount and merchant_name else 60,
            'parsing_status': 'parsed',
        }

    return None
