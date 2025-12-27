"""
Digital Services Parsers

Microsoft, Google, Figma, Atlassian, Anthropic
"""

from bs4 import BeautifulSoup
import re
from typing import Optional

from .base import register_vendor, parse_amount, parse_date_text


@register_vendor(['microsoft.com'])
def parse_microsoft_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
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
        'parse_method': 'vendor_microsoft',
        'parse_confidence': 85,
        'merchant_name': 'Microsoft',
        'merchant_name_normalized': 'microsoft',
        'category_hint': 'software_subscription',
    }

    # Extract product from subject - multiple patterns
    # "Your purchase of Microsoft 365 Family has been processed"
    # "Your subscription to Microsoft 365 Personal has been renewed"
    # "You've renewed your Microsoft Teams Essentials subscription"
    # "Your Microsoft order #2600070935 has been processed"
    product_name = None

    subject_patterns = [
        r'purchase of\s+(.+?)\s+has been',
        r'subscription to\s+(.+?)\s+has been',
        r"You['\u2019]ve renewed your\s+(.+?)\s+subscription",  # Handle both curly and straight apostrophe
        r'Your\s+(.+?)\s+order\s*#\d+',
    ]
    for pattern in subject_patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            product_name = match.group(1).strip()
            break

    if product_name:
        result['product_name'] = product_name
        # Microsoft only sells own-branded products, so brand = Microsoft
        result['line_items'] = [{'name': product_name, 'brand': 'Microsoft'}]

    if html_body:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

        # Extract order number (8-12 digits)
        order_match = re.search(r'Order\s*(?:number|#)?[:\s]*(\d{8,12})', text, re.IGNORECASE)
        if order_match:
            result['order_id'] = order_match.group(1)

        # Extract amount - multiple patterns
        amount_patterns = [
            r'Plan Price[:\s]*(?:GBP|USD|EUR)?\s*([0-9,]+\.?\d*)',
            r'(?:GBP|USD|EUR)\s*([0-9,]+\.?\d*)',
            r'[£$€]\s*([0-9,]+\.?\d*)',
            r'Total[:\s]*[£$€]?\s*([0-9,]+\.?\d*)',
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['total_amount'] = parse_amount(match.group(1))
                break

        # Currency detection
        if 'GBP' in text or '£' in text:
            result['currency_code'] = 'GBP'
        elif 'EUR' in text or '€' in text:
            result['currency_code'] = 'EUR'
        elif 'USD' in text or '$' in text:
            result['currency_code'] = 'USD'

        # Subscription period
        period_match = re.search(r'(\d+)\s*(year|month)', text, re.IGNORECASE)
        if period_match:
            result['billing_period'] = f"{period_match.group(1)} {period_match.group(2)}"

        # Payment method
        payment_match = re.search(
            r'(MasterCard|Visa|PayPal|Amex|American Express)[^\d]*(\*{2,4}\d{4})?',
            text,
            re.IGNORECASE
        )
        if payment_match:
            result['payment_method'] = payment_match.group(0).strip()

        # Determine category from product name
        if result.get('product_name'):
            product_lower = result['product_name'].lower()
            if 'xbox' in product_lower or 'game' in product_lower:
                result['category_hint'] = 'entertainment'
            elif '365' in product_lower or 'office' in product_lower:
                result['category_hint'] = 'software_subscription'
            elif 'azure' in product_lower or 'visual studio' in product_lower:
                result['category_hint'] = 'software_subscription'

    # Validate - must have at least amount, order ID, or product name
    if result.get('total_amount') or result.get('order_id') or result.get('line_items'):
        return result

    return None


# ============================================================================
# GOOGLE PARSER
# ============================================================================



@register_vendor(['google.com'])
def parse_google_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
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
        'parse_method': 'vendor_google',
        'parse_confidence': 85,
        'merchant_name': 'Google',
        'merchant_name_normalized': 'google',
    }

    # Detect type from subject
    subject_lower = subject.lower()
    if 'google play' in subject_lower:
        result['category_hint'] = 'software_subscription'
        result['merchant_name'] = 'Google Play'
        result['merchant_name_normalized'] = 'google_play'
    elif 'cloud platform' in subject_lower or 'invoice' in subject_lower:
        result['category_hint'] = 'software_subscription'
        result['merchant_name'] = 'Google Cloud'
        result['merchant_name_normalized'] = 'google_cloud'

    if html_body:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

        # Extract order/invoice number
        order_patterns = [
            r'Order number[:\s]*([A-Z0-9\.\-]+)',
            r'Invoice number[:\s]*(\d+)',
        ]
        for pattern in order_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['order_id'] = match.group(1)
                break

        # Try to extract invoice ID from subject for Google Cloud
        if not result.get('order_id') and 'invoice' in subject_lower:
            subject_match = re.search(r'for\s+([A-Z0-9\-]+)', subject, re.IGNORECASE)
            if subject_match:
                result['order_id'] = subject_match.group(1)

        # Extract invoice date for Google Cloud
        if 'cloud' in result.get('merchant_name_normalized', ''):
            # Pattern 1: "Invoice date: Month DD, YYYY"
            date_match = re.search(r'Invoice date[:\s]+([A-Za-z]+\s+\d{1,2},\s+\d{4})', text, re.IGNORECASE)
            if date_match:
                parsed = parse_date_text(date_match.group(1))
                if parsed:
                    result['receipt_date'] = parsed

            # Pattern 2: "Billing period: YYYY-MM-DD to YYYY-MM-DD" (use end date)
            if not result.get('receipt_date'):
                period_match = re.search(r'to\s+(\d{4}-\d{2}-\d{2})', text, re.IGNORECASE)
                if period_match:
                    parsed = parse_date_text(period_match.group(1))
                    if parsed:
                        result['receipt_date'] = parsed

            # Pattern 3: Subject line "Invoice for [ID] (Month YYYY)" - use first day of month
            if not result.get('receipt_date'):
                subject_date = re.search(r'\(([A-Za-z]+\s+\d{4})\)', subject)
                if subject_date:
                    # Use first day of month as approximation
                    parsed = parse_date_text(subject_date.group(1) + ' 01')
                    if parsed:
                        result['receipt_date'] = parsed

        # Extract amount (Google Play has in HTML)
        amount_patterns = [
            r'[£$€]\s*([0-9,]+\.?\d*)/(?:year|month)',
            r'Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'Price[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
            r'[£$€]\s*([0-9,]+\.[0-9]{2})',
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['total_amount'] = parse_amount(match.group(1))
                break

        # Currency detection
        if '£' in text or 'GBP' in text:
            result['currency_code'] = 'GBP'
        elif '€' in text or 'EUR' in text:
            result['currency_code'] = 'EUR'
        elif '$' in text or 'USD' in text:
            result['currency_code'] = 'USD'

        # Extract product name for Google Play
        product_patterns = [
            r'(?:Product|Item)[:\s]+(.+?)(?:\n|Auto-renewing)',
            r'(\d+ GB.*?)\s+(?:Google One|storage)',
            r'(?:for|of)\s+([A-Za-z0-9\s]+(?:subscription|plan|membership))',  # App subscriptions
        ]
        for pattern in product_patterns:
            match = re.search(pattern, text)
            if match:
                product = match.group(1).strip()
                # Avoid extracting just "Price" or other generic terms
                if product and len(product) > 5 and product.lower() not in ['price', 'total', 'amount', 'order']:
                    result['product_name'] = product
                    break

        # Extract subscription period if present
        period_match = re.search(r'([£$€][0-9,\.]+)/(\w+)', text)
        if period_match:
            result['billing_period'] = period_match.group(2)

    # Set line_items from product name
    # Google only sells own-branded products, so brand = merchant name
    merchant_brand = result.get('merchant_name', 'Google')
    if result.get('product_name'):
        period_suffix = f" ({result['billing_period']})" if result.get('billing_period') else ""
        result['line_items'] = [{'name': f"{result['product_name']}{period_suffix}", 'brand': merchant_brand}]
    elif 'google_cloud' in result.get('merchant_name_normalized', ''):
        result['line_items'] = [{'name': 'Google Cloud Platform services', 'brand': 'Google Cloud'}]
    elif 'google_play' in result.get('merchant_name_normalized', ''):
        result['line_items'] = [{'name': 'Google Play purchase', 'brand': 'Google Play'}]

    # Note: Google Cloud amounts are in PDF attachments
    # We can still extract invoice ID for matching
    if result.get('total_amount') or result.get('order_id'):
        return result

    return None


# ============================================================================
# ANTHROPIC PARSER (Stripe-based receipts)
# ============================================================================



@register_vendor(['mail.anthropic.com'])
def parse_anthropic_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
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
        'merchant_name': 'Anthropic',
        'merchant_name_normalized': 'anthropic',
        'parse_method': 'vendor_anthropic',
        'parse_confidence': 90,
        'category_hint': 'software_subscription',
        'currency_code': 'USD',
    }

    # Extract receipt number from subject
    receipt_match = re.search(r'#(\d{4}-\d{4}-\d{4})', subject)
    if receipt_match:
        result['order_id'] = receipt_match.group(1)

    # Use text body for parsing (cleaner than HTML)
    text = text_body or ''
    if html_body and not text:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    # Extract invoice number
    invoice_match = re.search(r'Invoice number\s+([A-Z0-9\-]+)', text, re.IGNORECASE)
    if invoice_match:
        result['invoice_number'] = invoice_match.group(1)

    # Extract total amount - handle both USD ($) and GBP (£)
    # e.g., "$60.00 Paid", "£180.00 Paid", "Total $60.00", "Amount paid £180.00"
    amount_patterns = [
        r'[\$£]([0-9,]+\.?\d*)\s+Paid',
        r'Total\s+[\$£]([0-9,]+\.?\d*)',
        r'Amount paid\s+[\$£]([0-9,]+\.?\d*)',
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            # Detect currency from match
            full_match = match.group(0)
            if '£' in full_match:
                result['currency_code'] = 'GBP'
            break

    # Extract date (e.g., "November 30, 2025")
    date_match = re.search(r'Paid\s+(\w+\s+\d{1,2},?\s+\d{4})', text, re.IGNORECASE)
    if date_match:
        result['receipt_date'] = parse_date_text(date_match.group(1))

    # Extract VAT/Tax (e.g., "VAT - United Kingdom (20%) $10.00" or "Tax (20%) £30.00")
    vat_match = re.search(r'(?:VAT|Tax)[^\$£]*[\$£]([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if vat_match:
        result['vat_amount'] = parse_amount(vat_match.group(1))

    # Extract subtotal
    subtotal_match = re.search(r'Subtotal\s+[\$£]([0-9,]+\.?\d*)', text, re.IGNORECASE)
    if subtotal_match:
        result['subtotal'] = parse_amount(subtotal_match.group(1))

    # Extract product description
    product_match = re.search(r'Receipt #[\d\-]+\s+(.+?)\s+Qty', text)
    if product_match:
        result['product_name'] = product_match.group(1).strip()

    # Set line_items from product name or default
    if result.get('product_name'):
        result['line_items'] = [{'name': result['product_name'], 'brand': 'Anthropic'}]
    else:
        result['line_items'] = [{'name': 'Claude API usage', 'brand': 'Anthropic'}]

    # Validate
    if result.get('total_amount') or result.get('order_id'):
        return result

    return None


# ============================================================================
# AIRBNB PARSER
# ============================================================================



@register_vendor(['am.atlassian.com', 'atlassian.com'])
def parse_atlassian_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse Atlassian invoice/receipt emails.

    Atlassian receipts contain:
    - Invoice number in subject: IN-XXX-XXX-XXX
    - Payment confirmation
    """
    result = {
        'merchant_name': 'Atlassian',
        'merchant_name_normalized': 'atlassian',
        'parse_method': 'vendor_atlassian',
        'parse_confidence': 85,
        'category_hint': 'software_subscription',
    }

    # Extract invoice number from subject
    invoice_match = re.search(r'(IN-\d{3}-\d{3}-\d+)', subject)
    if invoice_match:
        result['order_id'] = invoice_match.group(1)

    # Use text body
    text = text_body or ''
    if html_body and not text:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text()

    # Try to extract invoice number from body if not in subject
    if not result.get('order_id'):
        invoice_match = re.search(r'invoice\s+(IN-\d{3}-\d{3}-\d+)', text, re.IGNORECASE)
        if invoice_match:
            result['order_id'] = invoice_match.group(1)

    # Currency detection
    if '£' in text or 'GBP' in text:
        result['currency_code'] = 'GBP'
    elif '€' in text or 'EUR' in text:
        result['currency_code'] = 'EUR'
    elif '$' in text or 'USD' in text:
        result['currency_code'] = 'USD'

    # Extract amount (if in email body - often in PDF attachment)
    amount_patterns = [
        r'Total[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
        r'Amount[:\s]*[£$€]\s*([0-9,]+\.?\d*)',
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            break

    # Validate
    if result.get('order_id'):
        return result

    return None


# ============================================================================
# CHARLES TYRWHITT PARSER (for email body - PDF parsed separately)
# ============================================================================



@register_vendor(['figma.com'])
def parse_figma_receipt(html_body: str, text_body: str, subject: str) -> Optional[dict]:
    """
    Parse Figma subscription receipt emails.

    Email format:
    - Subject: "Receipt for subscription payment [Month DD, YYYY]"
    - Contains subscription details and payment amount
    """
    result = {
        'merchant_name': 'Figma',
        'merchant_name_normalized': 'figma',
        'merchant_domain': 'figma.com',
        'parse_method': 'vendor_figma',
        'parse_confidence': 85,
        'category_hint': 'software_subscription',
        'currency_code': 'USD',  # Figma typically charges in USD
    }

    # Extract date from subject "Receipt for subscription payment Nov 30, 2025"
    date_match = re.search(r'(\w{3})\s+(\d{1,2}),?\s+(\d{4})', subject, re.IGNORECASE)
    if date_match:
        month_abbr = date_match.group(1)
        day = int(date_match.group(2))
        year = int(date_match.group(3))
        months = {
            'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
        }
        month = months.get(month_abbr.lower(), 1)
        result['receipt_date'] = f"{year:04d}-{month:02d}-{day:02d}"

    if not html_body and not text_body:
        return result if result.get('receipt_date') else None

    # Prefer HTML for parsing as text_body may be empty or minimal
    text = ''
    if html_body:
        soup = BeautifulSoup(html_body, 'html.parser')
        text = soup.get_text(separator='\n')
    elif text_body and text_body.strip():
        text = text_body

    # Look for amount - could be $ or £
    # Figma format: "Total: £201.60 GBP" or "Total:\n £201.60 GBP"
    amount_patterns = [
        r'Total:?\s*[\n\s]*£([\d,]+\.?\d*)',      # Total: £201.60
        r'Total:?\s*[\n\s]*\$([\d,]+\.?\d*)',     # Total: $15.00
        r'£([\d,]+\.?\d*)\s*GBP',                 # £201.60 GBP
        r'\$([\d,]+\.\d{2})\s*USD',               # $15.00 USD
    ]

    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result['total_amount'] = parse_amount(match.group(1))
            # Detect currency from the pattern or symbol
            if '£' in pattern or '£' in match.group(0):
                result['currency_code'] = 'GBP'
            break

    # Look for subscription type - "Professional team (annual)"
    sub_match = re.search(r'(Professional|Organization|Team|Starter)\s+(team\s+)?\((annual|monthly)\)', text, re.IGNORECASE)
    if sub_match:
        plan_type = sub_match.group(1).title()
        billing = sub_match.group(3).lower() if sub_match.group(3) else 'subscription'
        result['line_items'] = [{
            'name': f'Figma {plan_type} ({billing})',
            'quantity': 1,
            'price': result.get('total_amount'),
        }]

    if result.get('total_amount') or result.get('receipt_date'):
        return result
    return None


# ============================================================================
# LIME SCOOTER PARSER
# ============================================================================



