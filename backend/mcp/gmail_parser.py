"""
Gmail Receipt Parser Module

Three-tier parsing strategy:
1. Schema.org JSON-LD extraction (95% confidence)
2. Pattern-based extraction using regex (80% confidence)
3. LLM fallback (70% confidence)
"""

import re
import json
import hashlib
from datetime import datetime
from typing import Optional, Tuple
from bs4 import BeautifulSoup

try:
    import extruct
    EXTRUCT_AVAILABLE = True
except ImportError:
    EXTRUCT_AVAILABLE = False

import database_postgres as database
from mcp.gmail_parsers.base import get_vendor_parser
from mcp.logging_config import get_logger

# Initialize logger
logger = get_logger(__name__)


# Domain to merchant name mappings for known senders
# Maps email domains to canonical merchant names
DOMAIN_TO_MERCHANT = {
    # UK Mobile providers
    's-email-o2.co.uk': 'O2',
    'email.o2.co.uk': 'O2',
    'o2.co.uk': 'O2',
    'ee.co.uk': 'EE',
    'three.co.uk': 'Three',
    'vodafone.co.uk': 'Vodafone',
    # UK Utilities
    'britishgas.co.uk': 'British Gas',
    'edfenergy.com': 'EDF Energy',
    'octopus.energy': 'Octopus Energy',
    # UK Retailers
    'johnlewis.co.uk': 'John Lewis',
    'marksandspencer.com': 'M&S',
    'tesco.com': 'Tesco',
    'sainsburys.co.uk': 'Sainsburys',
    'argos.co.uk': 'Argos',
    'currys.co.uk': 'Currys',
    # Food delivery
    'deliveroo.co.uk': 'Deliveroo',
    'just-eat.co.uk': 'Just Eat',
    'uber.com': 'Uber',
    'ubereats.com': 'Uber Eats',
    # Streaming/Entertainment
    'netflix.com': 'Netflix',
    'spotify.com': 'Spotify',
    'disneyplus.com': 'Disney+',
    # Cloud/Tech
    'google.com': 'Google Cloud',
    'cloud.google.com': 'Google Cloud',
    'aws.amazon.com': 'AWS',
    'microsoft.com': 'Microsoft',
    'github.com': 'GitHub',
    'anthropic.com': 'Anthropic',
    'mail.anthropic.com': 'Anthropic',
    # Other retailers
    'ctshirts.co.uk': 'Charles Tyrwhitt',
    'ctshirts.com': 'Charles Tyrwhitt',
    'bloomling.com': 'Bloomling',
    'nisbets.co.uk': 'Nisbets',
    'wob.com': 'World of Books',
    'procook.co.uk': 'ProCook',
    'grahamandgreen.co.uk': 'Graham & Green',
    'hortology.co.uk': 'Hortology',
    'andertons.co.uk': 'Andertons',
    'serif.com': 'Serif (Affinity)',
    'lebara.com': 'Lebara',
    'laver.co.uk': 'Laver',
    'eventbrite.com': 'Eventbrite',
    'order.eventbrite.com': 'Eventbrite',
    # Healthcare
    'service.theindependentpharmacy.co.uk': 'The Independent Pharmacy',
    'theindependentpharmacy.co.uk': 'The Independent Pharmacy',
    # Education
    'findivsales.admin.cam.ac.uk': 'Cambridge University',
    'cam.ac.uk': 'Cambridge University',
}

# Currency symbols and codes mapping
CURRENCY_SYMBOLS = {
    '£': 'GBP',
    '$': 'USD',
    '€': 'EUR',
    '¥': 'JPY',
    'CHF': 'CHF',
}

# Common amount patterns for different currencies
AMOUNT_PATTERNS = [
    # £12.34 or GBP 12.34
    r'(?:£|GBP)\s*([0-9,]+\.?[0-9]*)',
    # $12.34 or USD 12.34
    r'(?:\$|USD)\s*([0-9,]+\.?[0-9]*)',
    # €12.34 or EUR 12.34
    r'(?:€|EUR)\s*([0-9,]+\.?[0-9]*)',
    # 12.34 GBP (amount before currency)
    r'([0-9,]+\.[0-9]{2})\s*(?:GBP|USD|EUR)',
]

# Common total amount label patterns
TOTAL_PATTERNS = [
    r'(?:total|order total|amount|grand total|payment|charged|paid)[:\s]*[£$€]?\s*([0-9,]+\.?[0-9]*)',
    r'[£$€]\s*([0-9,]+\.[0-9]{2})\s*(?:total|paid|charged)',
]

# Date patterns
DATE_PATTERNS = [
    # DD/MM/YYYY or DD-MM-YYYY
    (r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'DMY'),
    # YYYY-MM-DD (ISO)
    (r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', 'YMD'),
    # Month DD, YYYY
    (r'(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})', 'MDY'),
    # DD Month YYYY
    (r'(\d{1,2})(?:st|nd|rd|th)?\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{4})', 'DMY'),
]

MONTH_MAP = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}

# Strong receipt indicators (weighted +2)
STRONG_RECEIPT_INDICATORS = [
    'order confirmed', 'order confirmation', 'your order has been',
    'payment received', 'payment confirmation', 'receipt for your',
    'invoice #', 'invoice number', 'order #', 'order number',
    'transaction id', 'confirmation number', 'booking confirmed',
    'thank you for your order', 'thank you for your purchase',
    'your receipt', 'e-receipt', 'digital receipt',
]

# Weak receipt indicators (weighted +1)
WEAK_RECEIPT_INDICATORS = [
    'order', 'receipt', 'invoice', 'confirmation', 'purchase',
    'payment', 'transaction', 'booking', 'subscription',
]

# Strong marketing/promotional indicators (weighted -3, any one = reject)
STRONG_MARKETING_INDICATORS = [
    'shop now', 'buy now', 'order now', 'get yours',
    'sale ends', 'limited time', 'flash sale', 'black friday',
    'cyber monday', 'exclusive deal', 'special offer',
    'save up to', 'up to % off', 'deals you', 'deals for',
    'gift ideas', 'gift guide', 'perfect gift',
    'don\'t miss', 'last chance', 'hurry',
    'view in browser', 'email preferences', 'manage preferences',
]

# Weak marketing indicators (weighted -1)
WEAK_MARKETING_INDICATORS = [
    'unsubscribe', 'newsletter', 'promotional', 'marketing',
    'sale', 'discount', 'offer', 'promo', 'savings',
]

# Known transactional sender patterns (full email prefixes, not just domains)
KNOWN_RECEIPT_SENDERS = [
    'auto-confirm@amazon', 'order-update@amazon', 'shipment-tracking@amazon', 'return@amazon',
    'noreply@uber.com', 'receipts@uber.com',
    'noreply@apple.com', 'no_reply@email.apple.com',
    'service@paypal', 'noreply@paypal',
    'noreply@deliveroo', 'orders@deliveroo',
    'receipts@netflix.com', 'info@account.netflix.com',
    'noreply@spotify.com',
    'noreply@google.com', 'payments-noreply@google.com',
    'msa@communication.microsoft.com',  # Account notifications
    # eBay transactional senders
    'ebay@ebay.com', 'orders@ebay.com', 'transaction@ebay.com', 'ebay@reply.ebay.com',
]

# Known marketing sender patterns (reject these even from known domains)
KNOWN_MARKETING_SENDERS = [
    'store-news@amazon', 'deals@amazon', 'recommendations@amazon',
    'marketing@', 'promo@', 'newsletter@',
    'deals@', 'offers@', 'sales@', 'promotions@',
    'campaign@', 'email@', 'hello@',  # Often marketing
    # eBay marketing senders
    'newsletter@ebay', 'promotions@ebay', 'deals@ebay', 'offers@ebay',
    # Uber marketing senders
    'marketing@uber', 'promo@uber', 'promotions@uber', 'deals@uber', 'news@uber',
]


def is_ebay_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    eBay-specific receipt filter using strict subject patterns.

    Only accepts these 3 subject patterns:
    1. "{name}, your order is confirmed"
    2. "Order confirmed: {product description}"
    3. "Your order is confirmed."

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an eBay email
    """
    sender_lower = sender_email.lower()

    # Only process eBay emails
    if 'ebay' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Pattern 1: "{name}, your order is confirmed"
    if ', your order is confirmed' in subject_lower:
        return (True, 'eBay receipt: {name}, your order is confirmed', 95)

    # Pattern 2: "Order confirmed: {product description}"
    if subject_lower.startswith('order confirmed:'):
        return (True, 'eBay receipt: Order confirmed: {product}', 95)

    # Pattern 3: "Your order is confirmed."
    if subject_lower == 'your order is confirmed.' or subject_lower == 'your order is confirmed':
        return (True, 'eBay receipt: Your order is confirmed', 95)

    # Reject all other eBay emails
    return (False, 'eBay email - not a receipt', 90)


def is_amazon_receipt_email(subject: str, sender_email: str, body_text: str = None) -> tuple:
    """
    Amazon-specific receipt filter using subject patterns and body content.

    Accepts:
    - Regular orders: Subject starts with "Ordered:"
    - Amazon Fresh: Subject "Your Amazon Fresh order has been received"
    - Amazon Business: Subject "Your Amazon.co.uk order." (exact match)
    - Refunds: Subject contains "your refund" or "refund for"
    - Body fallback: Contains "Thanks for your order"

    Rejects:
    - Marketing senders
    - Return notifications
    - Shipment/delivery notifications

    Args:
        subject: Email subject line
        sender_email: Full sender email address
        body_text: Email body text (HTML or plain text)

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Amazon email
    """
    sender_lower = sender_email.lower()

    # Only process Amazon emails
    if 'amazon' not in sender_lower:
        return (None, None, None)

    # Reject known marketing senders first (fast path)
    AMAZON_MARKETING_SENDERS = [
        'store-news@amazon', 'deals@amazon', 'recommendations@amazon',
        'marketing@amazon', 'promo@amazon',
    ]
    for pattern in AMAZON_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Amazon marketing sender: {pattern}', 95)

    subject_lower = subject.lower()

    # Reject return notification emails (not receipts)
    # Patterns: "Your return {of product}", "dropoff confirmation for {product}"
    if subject_lower.startswith('your return'):
        return (False, 'Amazon return notification (not a receipt)', 95)
    if 'drop' in subject_lower and 'confirmation' in subject_lower:
        # Matches: "dropoff confirmation", "drop-off confirmation", "drop off confirmation"
        return (False, 'Amazon return dropoff confirmation (not a receipt)', 95)

    # Reject shipment/delivery notifications (not receipts)
    SHIPMENT_PATTERNS = [
        'has been dispatched', 'has been shipped', 'has shipped',
        'out for delivery', 'arriving today', 'arriving tomorrow',
        'delivered:', 'dispatched:'
    ]
    for pattern in SHIPMENT_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Amazon shipment notification: {pattern}', 95)

    # === ACCEPT PATTERNS (subject-based) ===

    # Regular Amazon order receipts: "Ordered: 'Product Name...'"
    if subject_lower.startswith('ordered:'):
        return (True, 'Amazon order receipt (Ordered: subject pattern)', 95)

    # Amazon Fresh order confirmations (specific subject pattern)
    if subject_lower == 'your amazon fresh order has been received':
        return (True, 'Amazon Fresh order confirmation', 95)

    # Amazon Business: body contains "order is placed on behalf of"
    # NOTE: Subject "Your Amazon.co.uk order." is NOT unique to Business - must check body
    if body_text and 'order is placed on behalf of' in body_text.lower():
        return (True, 'Amazon Business order (body indicator)', 95)

    # Simple body-based filter: Amazon receipts contain "Thanks for your order"
    if body_text and 'thanks for your order' in body_text.lower():
        return (True, 'Amazon receipt (body contains "Thanks for your order")', 95)

    # Check for refund emails (different body pattern)
    if 'your refund' in subject_lower or 'refund for' in subject_lower:
        return (True, 'Amazon refund email', 90)

    # Accept from return@ sender (refunds)
    if 'return@amazon' in sender_lower:
        return (True, 'Amazon refund sender', 90)

    # Reject all other Amazon emails (delivery notifications, cancellations, etc.)
    return (False, 'Amazon email without receipt indicator', 90)


def is_uber_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Uber-specific receipt filter using strict subject pattern.

    Only accepts: "Your {daypart} trip with Uber"
    e.g., "Your Thursday evening trip with Uber"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Uber email
    """
    sender_lower = sender_email.lower()

    # Only process Uber emails
    if 'uber' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Only accept pattern: "Your {daypart} trip with Uber"
    # e.g., "Your Thursday evening trip with Uber"
    if subject_lower.startswith('your ') and 'trip with uber' in subject_lower:
        return (True, 'Uber receipt: Your {daypart} trip with Uber', 95)

    # Reject all other Uber emails
    return (False, 'Uber email - not a trip receipt', 90)


def is_paypal_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    PayPal-specific receipt filter using strict subject patterns.

    Accepts ONLY these 3 patterns:
    1. "Receipt for your payment to {merchant}"
    2. "Your PayPal receipt"
    3. "Receipt for your paypal payment"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a PayPal email
    """
    sender_lower = sender_email.lower()

    # Only process PayPal emails
    if 'paypal' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Pattern 1: "Receipt for your payment to {merchant}"
    if subject_lower.startswith('receipt for your payment to'):
        return (True, 'PayPal receipt: Receipt for your payment to {merchant}', 95)

    # Pattern 2: "Your PayPal receipt"
    if subject_lower == 'your paypal receipt':
        return (True, 'PayPal receipt: Your PayPal receipt', 95)

    # Pattern 3: "Receipt for your paypal payment"
    if subject_lower == 'receipt for your paypal payment':
        return (True, 'PayPal receipt: Receipt for your paypal payment', 95)

    # Reject all other PayPal emails
    return (False, 'PayPal email - not a receipt', 90)


def is_microsoft_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Microsoft-specific receipt vs marketing classification.

    Microsoft sends purchase receipts from microsoft-noreply@microsoft.com
    with subjects like "Your purchase of [PRODUCT] has been processed".

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Microsoft email
    """
    sender_lower = sender_email.lower()

    # Only process Microsoft emails
    if 'microsoft' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Reject known marketing senders first
    MICROSOFT_MARKETING_SENDERS = [
        'marketing@microsoft', 'promo@microsoft', 'newsletter@microsoft',
        'offers@microsoft', 'xbox@microsoft',
    ]
    for pattern in MICROSOFT_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Microsoft marketing sender: {pattern}', 95)

    # Accept receipt subject patterns (HIGH confidence)
    MICROSOFT_RECEIPT_PATTERNS = [
        ('your purchase of', 95),
        ('has been processed', 90),
        ('order confirmation', 95),
        ('your order', 90),
        ('subscription renewed', 90),
        ('payment received', 90),
        ('receipt for your', 95),
    ]
    for pattern, confidence in MICROSOFT_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Microsoft receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    MICROSOFT_MARKETING_PATTERNS = [
        'special offer', 'save on', 'exclusive deal', 'limited time',
        'try for free', 'introducing', 'new features', 'update available',
        'security alert', 'sign-in activity', 'verify your',
    ]
    for pattern in MICROSOFT_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Microsoft marketing subject: {pattern}', 90)

    # Accept from noreply@ sender for transactions
    if 'microsoft-noreply@microsoft' in sender_lower:
        return (True, 'Microsoft noreply sender', 85)

    # Ambiguous Microsoft email - reject to avoid false positives
    return (False, 'Microsoft - no receipt indicators', 60)


def is_apple_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Apple-specific receipt vs marketing classification.

    Apple sends many marketing emails from the same domains as receipts.
    Need to distinguish receipts/invoices from App Store promos.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Apple email
    """
    sender_lower = sender_email.lower()

    # Only process Apple emails
    if 'apple' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Reject known marketing senders first
    APPLE_MARKETING_SENDERS = [
        'news@apple', 'news@email.apple', 'marketing@apple',
        'promo@apple', 'store@apple',
    ]
    for pattern in APPLE_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Apple marketing sender: {pattern}', 95)

    # Reject subscription notification patterns FIRST (these have no amounts)
    APPLE_SUBSCRIPTION_NOTIFICATION_PATTERNS = [
        'subscription is confirmed',
        'subscription is expiring',
        'subscription confirmation',
        'subscription renewal',
        'your subscription is',
        'pre-order for',
        'is now available',
    ]
    for pattern in APPLE_SUBSCRIPTION_NOTIFICATION_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Apple subscription notification: {pattern}', 95)

    # Accept receipt subject patterns (HIGH confidence) - actual invoices with amounts
    APPLE_RECEIPT_PATTERNS = [
        ('your receipt from apple', 95),
        ('your invoice from apple', 95),
        ('your apple store order', 95),
        ('order confirmation', 90),
        ('your purchase', 90),
    ]
    for pattern, confidence in APPLE_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Apple receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    APPLE_MARKETING_PATTERNS = [
        'new in the app store', 'discover', 'special offer',
        'try apple', 'get more from', 'introducing',
        'free trial', 'upgrade to', 'what\'s new',
    ]
    for pattern in APPLE_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Apple marketing subject: {pattern}', 90)

    # Ambiguous Apple email - reject to avoid false positives
    return (False, 'Apple - no receipt indicators', 60)


def is_lyft_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Lyft-specific receipt vs marketing classification.

    Lyft sends ride receipts and promotional emails from the same domain.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Lyft email
    """
    sender_lower = sender_email.lower()

    # Only process Lyft emails
    if 'lyft' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept receipt subject patterns (HIGH confidence)
    LYFT_RECEIPT_PATTERNS = [
        ('your receipt for rides', 95),
        ('your lyft ride receipt', 95),
        ('receipt for your ride', 95),
        ('your ride on', 90),
    ]
    for pattern, confidence in LYFT_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Lyft receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    LYFT_MARKETING_PATTERNS = [
        'earn credits', 'refer a friend', 'special offer',
        'free ride', 'promo code', 'discount',
    ]
    for pattern in LYFT_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Lyft marketing subject: {pattern}', 90)

    # Ambiguous Lyft email - reject to avoid false positives
    return (False, 'Lyft - no receipt indicators', 60)


def is_deliveroo_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Deliveroo-specific receipt vs marketing classification.

    Only accepts: "Your order's in the kitchen 🎉" (the actual receipt)
    Rejects: cancellations, surveys, marketing, etc.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Deliveroo email
    """
    sender_lower = sender_email.lower()

    # Only process Deliveroo emails
    if 'deliveroo' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY "Your order's in the kitchen" emails (actual receipts)
    if "order's in the kitchen" in subject_lower or "order is in the kitchen" in subject_lower:
        return (True, 'Deliveroo order confirmation', 95)

    # Reject everything else from Deliveroo (cancellations, surveys, marketing)
    return (False, 'Deliveroo - not an order confirmation', 90)


def is_spotify_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Spotify-specific classification - always marketing, never receipts.

    Spotify does not send receipt emails - all emails are marketing/promotional.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Spotify email
    """
    sender_lower = sender_email.lower()

    # Only process Spotify emails
    if 'spotify' not in sender_lower:
        return (None, None, None)

    # Spotify never sends receipts via email - all are marketing
    return (False, 'Spotify - never sends receipt emails', 95)


def is_netflix_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Netflix-specific classification - always marketing, never receipts.

    Netflix does not send receipt emails - all emails are marketing/promotional.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Netflix email
    """
    sender_lower = sender_email.lower()

    # Only process Netflix emails
    if 'netflix' not in sender_lower:
        return (None, None, None)

    # Netflix never sends receipts via email - all are marketing
    return (False, 'Netflix - never sends receipt emails', 95)


def is_google_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Google-specific receipt vs marketing classification.

    Google sends receipts from:
    - Google Play: googleplay-noreply@google.com
    - Google Payments/Cloud: payments-noreply@google.com

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Google email
    """
    sender_lower = sender_email.lower()

    # Only process Google emails
    if 'google' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept from known receipt senders
    GOOGLE_RECEIPT_SENDERS = [
        'googleplay-noreply@google.com',
        'payments-noreply@google.com',
    ]
    for pattern in GOOGLE_RECEIPT_SENDERS:
        if pattern in sender_lower:
            # Check subject for receipt indicators
            if any(ind in subject_lower for ind in ['receipt', 'invoice', 'order', 'payment']):
                return (True, f'Google receipt sender: {pattern}', 95)

    # Accept receipt subject patterns (HIGH confidence)
    GOOGLE_RECEIPT_PATTERNS = [
        ('google play order receipt', 95),
        ('your invoice is available', 95),
        ('payment confirmation', 90),
        ('order confirmation', 90),
        ('your receipt', 90),
    ]
    for pattern, confidence in GOOGLE_RECEIPT_PATTERNS:
        if pattern in subject_lower:
            return (True, f'Google receipt subject: {pattern}', confidence)

    # Reject marketing subject patterns
    GOOGLE_MARKETING_PATTERNS = [
        'new features', 'introducing', 'try google',
        'upgrade to', 'get more', 'special offer',
    ]
    for pattern in GOOGLE_MARKETING_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Google marketing subject: {pattern}', 90)

    # Ambiguous Google email - reject to avoid false positives
    return (False, 'Google - no receipt indicators', 60)


def is_ocado_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Ocado-specific filter - reject marketing emails.

    marketing.ocado.com sends only marketing emails, never receipts.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Ocado email
    """
    sender_lower = sender_email.lower()

    # Only process Ocado emails
    if 'ocado' not in sender_lower:
        return (None, None, None)

    # Reject all marketing.ocado.com emails
    if 'marketing.ocado' in sender_lower:
        return (False, 'Ocado marketing sender', 95)

    # Allow other Ocado emails through (will be filtered by generic logic)
    return (None, None, None)


def is_citizens_of_soil_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Citizens of the Soil receipt filter.

    Accepts: "Olive oil order #XXX confirmed 🙌" (purchase confirmations)
    Rejects: "Your order #XXX is on the way..." (shipping notifications)

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Citizens of the Soil email
    """
    sender_lower = sender_email.lower()

    # Only process Citizens of the Soil emails
    if 'citizensofsoil' not in sender_lower and 'citizens of soil' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept: "Olive oil order #XXX confirmed" (purchase confirmation)
    if 'confirmed' in subject_lower and 'order' in subject_lower:
        return (True, 'Citizens of the Soil order confirmation', 95)

    # Reject: "Your order #XXX is on the way..." (shipping notification)
    if 'is on the way' in subject_lower:
        return (False, 'Citizens of the Soil shipping notification', 95)

    # Reject other emails from this sender
    return (False, 'Citizens of the Soil - not a receipt', 90)


def is_figma_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Figma receipt filter.

    Accepts: "Receipt for subscription payment {month day, year}"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Figma email
    """
    sender_lower = sender_email.lower()

    # Only process Figma emails
    if 'figma' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept: "Receipt for subscription payment {month day, year}"
    if subject_lower.startswith('receipt for subscription payment'):
        return (True, 'Figma subscription receipt', 95)

    # Reject other emails from this sender
    return (False, 'Figma - not a receipt', 90)


def is_sebago_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Sebago-specific receipt filter.

    Accepts: "Your Sebago Order" from orders@sebago.co.uk
    Rejects: Status updates, marketing from info@email.sebago.co.uk

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Sebago email
    """
    sender_lower = sender_email.lower()

    # Only process Sebago emails
    if 'sebago' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Reject marketing emails from info@email.sebago.co.uk
    if 'info@' in sender_lower or 'email.sebago' in sender_lower:
        return (False, 'Sebago marketing email', 95)

    # Accept: "Your Sebago Order" or "Your order from Sebago"
    if 'sebago order' in subject_lower or 'order from sebago' in subject_lower:
        return (True, 'Sebago order confirmation', 95)

    # Reject status updates
    if 'has updates' in subject_lower or 'status' in subject_lower:
        return (False, 'Sebago status update (not a receipt)', 95)

    # Reject other Sebago emails
    return (False, 'Sebago - not an order confirmation', 90)


def is_gmail_forwarded_email(subject: str, sender_email: str) -> tuple:
    """
    Reject all gmail.com emails (user-forwarded receipts).

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a gmail.com email
    """
    if 'gmail.com' in sender_email.lower():
        return (False, 'Forwarded email from gmail.com', 95)
    return (None, None, None)


def is_sony_email(subject: str, sender_email: str) -> tuple:
    """
    Reject all bmail.sony-europe.com emails.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Sony email
    """
    if 'bmail.sony-europe.com' in sender_email.lower():
        return (False, 'Sony marketing email', 95)
    return (None, None, None)


def is_booking_email(subject: str, sender_email: str) -> tuple:
    """
    Reject all booking.com emails.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a booking.com email
    """
    if 'booking.com' in sender_email.lower():
        return (False, 'Booking.com email rejected', 95)
    return (None, None, None)


def is_non_receipt_notification(subject: str, sender_email: str) -> tuple:
    """
    Filter out booking confirmations and shipping notifications.

    These are NOT receipts - they don't contain payment amounts:
    - Booking confirmations (restaurant reservations, travel bookings)
    - Shipping/delivery notifications
    - Order status updates

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a known non-receipt notification
    """
    subject_lower = subject.lower()

    # Booking confirmation patterns (restaurant reservations, etc.)
    BOOKING_CONFIRMATION_PATTERNS = [
        'booking confirmation for',
        'your reservation at',
        'reservation confirmed',
        'table booked',
        'your booking at',
    ]
    for pattern in BOOKING_CONFIRMATION_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Booking confirmation: {pattern}', 95)

    # Shipping/delivery notification patterns (not receipts)
    SHIPPING_NOTIFICATION_PATTERNS = [
        'your order is on the way',
        'your order has shipped',
        'your order has been shipped',
        'your order has been delivered',
        'your package is on its way',
        'out for delivery',
        'delivery update',
        'tracking your order',
        'your shipment',
        'has been dispatched',
        'is being prepared',
    ]
    for pattern in SHIPPING_NOTIFICATION_PATTERNS:
        if pattern in subject_lower:
            return (False, f'Shipping notification: {pattern}', 95)

    # Known shipping notification domains (all emails are shipping updates, not receipts)
    SHIPPING_DOMAINS = [
        'woolrich.com',  # Only sends delivery notifications
    ]
    for domain in SHIPPING_DOMAINS:
        if domain in sender_email.lower():
            # Reject all emails from these domains except actual receipts/purchase confirmations
            is_purchase_email = any(kw in subject_lower for kw in ['receipt', 'invoice', 'your purchase', 'thank you for your purchase'])
            if not is_purchase_email:
                return (False, f'Shipping notification domain: {domain}', 95)

    # Known booking/reservation domains
    BOOKING_DOMAINS = [
        'thefork.co.uk', 'thefork.com',
        'opentable.com', 'opentable.co.uk',
    ]
    sender_lower = sender_email.lower()
    for domain in BOOKING_DOMAINS:
        if domain in sender_lower:
            # Only reject if it's a confirmation, not a receipt
            if 'confirmation' in subject_lower or 'booked' in subject_lower:
                return (False, f'Booking platform confirmation: {domain}', 95)

    return (None, None, None)


def is_designacable_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Designacable receipt filter.

    Accepts ONLY: "Your designacable.com order confirmation"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Designacable email
    """
    sender_lower = sender_email.lower()

    # Only process Designacable emails
    if 'designacable' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY: "Your designacable.com order confirmation"
    if subject_lower == 'your designacable.com order confirmation':
        return (True, 'Designacable order confirmation', 95)

    # Reject all other Designacable emails
    return (False, 'Designacable - not order confirmation', 90)


def is_ryanair_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Ryanair receipt filter.

    Accepts ONLY: "Ryanair Travel Itinerary"

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Ryanair email
    """
    sender_lower = sender_email.lower()

    # Only process Ryanair emails
    if 'ryanair' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY: "Ryanair Travel Itinerary"
    if subject_lower == 'ryanair travel itinerary':
        return (True, 'Ryanair Travel Itinerary', 95)

    # Reject all other Ryanair emails
    return (False, 'Ryanair - not travel itinerary', 90)


def is_charles_tyrwhitt_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Charles Tyrwhitt receipt filter.

    Accepts ONLY: "With our thanks, here is your Charles Tyrwhitt e-receipt!"
    These emails contain the actual receipt as an attached PDF.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not a Charles Tyrwhitt email
    """
    sender_lower = sender_email.lower()

    # Only process Charles Tyrwhitt emails
    if 'ctshirts' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # Accept ONLY e-receipt emails (have PDF attachment)
    if subject_lower == 'with our thanks, here is your charles tyrwhitt e-receipt!':
        return (True, 'Charles Tyrwhitt e-receipt (PDF attached)', 95)

    # Reject order confirmations and other emails
    return (False, 'Charles Tyrwhitt - not e-receipt', 90)


def is_etsy_receipt_email(subject: str, sender_email: str) -> tuple:
    """
    Etsy-specific receipt filter.

    Etsy sends TWO types of transactional emails:
    1. Purchase receipts: "Your Etsy Purchase from {seller} ({order_id})" - ACCEPT
    2. Dispatch notifications: "Your Etsy Order dispatched (Receipt #{order_id})" - REJECT

    Only purchase receipts contain actual payment amounts.
    Dispatch notifications are shipping updates, not receipts.

    Args:
        subject: Email subject line
        sender_email: Full sender email address

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
        Returns (None, None, None) if not an Etsy email
    """
    sender_lower = sender_email.lower()

    # Only process Etsy emails
    if 'etsy' not in sender_lower:
        return (None, None, None)

    subject_lower = subject.lower()

    # ACCEPT: "Your Etsy Purchase from {seller} ({order_id})"
    # Pattern: starts with "your etsy purchase from"
    if subject_lower.startswith('your etsy purchase from'):
        return (True, 'Etsy purchase receipt', 95)

    # REJECT: "Your Etsy Order dispatched (Receipt #{order_id})"
    # These are shipping notifications, NOT receipts
    if 'dispatched' in subject_lower or 'shipped' in subject_lower:
        return (False, 'Etsy dispatch/shipping notification (not a receipt)', 95)

    # REJECT: Other shipping/delivery patterns
    if 'on the way' in subject_lower or 'delivered' in subject_lower:
        return (False, 'Etsy delivery notification (not a receipt)', 95)

    # Reject all other Etsy emails (marketing, surveys, etc.)
    return (False, 'Etsy - not a purchase receipt', 90)


def is_likely_receipt(
    subject: str,
    body_text: str,
    sender_email: str,
    sender_domain: str = None,
    list_unsubscribe: str = None,
    has_schema_order: bool = False
) -> tuple:
    """
    Determine if email is likely a receipt vs marketing/promotional.

    Uses multi-signal approach:
    1. Schema.org Order markup = definite receipt
    2. List-Unsubscribe header = likely marketing
    3. Sender email pattern matching
    4. Content keyword scoring

    Args:
        subject: Email subject
        body_text: Email body text (first 1000 chars used)
        sender_email: Full sender email address
        sender_domain: Sender domain (optional)
        list_unsubscribe: List-Unsubscribe header value (optional)
        has_schema_order: Whether email has Schema.org Order markup

    Returns:
        Tuple of (is_receipt: bool, reason: str, confidence: int)
    """
    # Signal 1: Schema.org Order markup is definitive
    if has_schema_order:
        return (True, 'Has Schema.org Order markup', 100)

    # Signal 1.5: Reject user-forwarded emails and known non-receipt senders first
    gmail_result = is_gmail_forwarded_email(subject, sender_email)
    if gmail_result[0] is not None:
        return gmail_result

    sony_result = is_sony_email(subject, sender_email)
    if sony_result[0] is not None:
        return sony_result

    booking_result = is_booking_email(subject, sender_email)
    if booking_result[0] is not None:
        return booking_result

    # Filter out booking confirmations and shipping notifications
    non_receipt_result = is_non_receipt_notification(subject, sender_email)
    if non_receipt_result[0] is not None:
        return non_receipt_result

    # Signal 1.6: Vendor-specific pre-filters (before generic processing)
    # These vendors need special handling due to high volume of marketing emails
    designacable_result = is_designacable_receipt_email(subject, sender_email)
    if designacable_result[0] is not None:
        return designacable_result

    ryanair_result = is_ryanair_receipt_email(subject, sender_email)
    if ryanair_result[0] is not None:
        return ryanair_result

    charles_tyrwhitt_result = is_charles_tyrwhitt_receipt_email(subject, sender_email)
    if charles_tyrwhitt_result[0] is not None:
        return charles_tyrwhitt_result

    ebay_result = is_ebay_receipt_email(subject, sender_email)
    if ebay_result[0] is not None:
        return ebay_result

    amazon_result = is_amazon_receipt_email(subject, sender_email, body_text)
    if amazon_result[0] is not None:
        return amazon_result

    uber_result = is_uber_receipt_email(subject, sender_email)
    if uber_result[0] is not None:
        return uber_result

    paypal_result = is_paypal_receipt_email(subject, sender_email)
    if paypal_result[0] is not None:
        return paypal_result

    microsoft_result = is_microsoft_receipt_email(subject, sender_email)
    if microsoft_result[0] is not None:
        return microsoft_result

    apple_result = is_apple_receipt_email(subject, sender_email)
    if apple_result[0] is not None:
        return apple_result

    lyft_result = is_lyft_receipt_email(subject, sender_email)
    if lyft_result[0] is not None:
        return lyft_result

    deliveroo_result = is_deliveroo_receipt_email(subject, sender_email)
    if deliveroo_result[0] is not None:
        return deliveroo_result

    spotify_result = is_spotify_receipt_email(subject, sender_email)
    if spotify_result[0] is not None:
        return spotify_result

    netflix_result = is_netflix_receipt_email(subject, sender_email)
    if netflix_result[0] is not None:
        return netflix_result

    google_result = is_google_receipt_email(subject, sender_email)
    if google_result[0] is not None:
        return google_result

    ocado_result = is_ocado_receipt_email(subject, sender_email)
    if ocado_result[0] is not None:
        return ocado_result

    citizens_result = is_citizens_of_soil_receipt_email(subject, sender_email)
    if citizens_result[0] is not None:
        return citizens_result

    figma_result = is_figma_receipt_email(subject, sender_email)
    if figma_result[0] is not None:
        return figma_result

    sebago_result = is_sebago_receipt_email(subject, sender_email)
    if sebago_result[0] is not None:
        return sebago_result

    etsy_result = is_etsy_receipt_email(subject, sender_email)
    if etsy_result[0] is not None:
        return etsy_result

    sender_lower = (sender_email or '').lower()
    text = f"{subject} {body_text[:1000]}".lower()

    # Signal 2: List-Unsubscribe header strongly indicates marketing
    if list_unsubscribe:
        # But check if it's from a known receipt sender first
        is_known_receipt_sender = any(
            pattern in sender_lower for pattern in KNOWN_RECEIPT_SENDERS
        )
        if not is_known_receipt_sender:
            return (False, 'Has List-Unsubscribe header (marketing)', 85)

    # Signal 3: Check sender patterns
    # Known marketing senders = reject
    for pattern in KNOWN_MARKETING_SENDERS:
        if pattern in sender_lower:
            return (False, f'Marketing sender pattern: {pattern}', 90)

    # Known receipt senders = accept (but verify with content)
    is_known_receipt_sender = any(
        pattern in sender_lower for pattern in KNOWN_RECEIPT_SENDERS
    )

    # Signal 4: Content scoring
    score = 0

    # Strong marketing indicators (any one = likely reject)
    for indicator in STRONG_MARKETING_INDICATORS:
        if indicator in text:
            score -= 3
            # If we hit a strong marketing indicator and not from known receipt sender
            if not is_known_receipt_sender:
                return (False, f'Strong marketing indicator: {indicator}', 80)

    # Weak marketing indicators
    for indicator in WEAK_MARKETING_INDICATORS:
        if indicator in text:
            score -= 1

    # Strong receipt indicators
    for indicator in STRONG_RECEIPT_INDICATORS:
        if indicator in text:
            score += 2

    # Weak receipt indicators
    for indicator in WEAK_RECEIPT_INDICATORS:
        if indicator in text:
            score += 1

    # Check for order/invoice number patterns (strong receipt signal)
    has_order_number = bool(re.search(
        r'(?:order|invoice|confirmation|booking|transaction)\s*(?:#|number|no\.?|id)?\s*[:.]?\s*[A-Z0-9-]{5,}',
        text, re.IGNORECASE
    ))
    if has_order_number:
        score += 3

    # Known receipt sender gets a bonus
    if is_known_receipt_sender:
        score += 2

    # Decision threshold
    if score >= 3:
        return (True, f'Receipt score: {score}', min(70 + score * 5, 95))
    elif score <= -2:
        return (False, f'Marketing score: {score}', min(70 + abs(score) * 5, 95))
    else:
        # Ambiguous - lean towards not a receipt to avoid false positives
        return (False, f'Ambiguous score: {score} (defaulting to not receipt)', 50)


def has_schema_order_markup(html_body: str) -> bool:
    """Check if HTML contains Schema.org Order markup (definitive receipt signal)."""
    if not html_body:
        return False
    # Check for JSON-LD Order type
    if '"@type"' in html_body and '"Order"' in html_body:
        return True
    # Check for microdata Order type
    if 'itemtype' in html_body and 'schema.org/Order' in html_body:
        return True
    return False


def is_valid_merchant_name(merchant: str) -> bool:
    """
    Validate that extracted merchant name is reasonable.

    Rejects:
    - Empty/None values
    - Too short (<2 chars) or too long (>50 chars)
    - Contains date patterns (e.g., "December 12")
    - Is mostly prepositions/articles
    - Contains promotional keywords

    Args:
        merchant: Extracted merchant name

    Returns:
        True if valid merchant name, False otherwise
    """
    if not merchant:
        return False

    merchant_lower = merchant.lower().strip()

    # Length checks
    if len(merchant_lower) < 2 or len(merchant_lower) > 50:
        return False

    # Reject if contains date patterns
    date_patterns = [
        r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b',
        r'\b\d{1,2}(?:st|nd|rd|th)?\b',  # 1st, 2nd, 12th, etc.
        r'\b20\d{2}\b',  # Years like 2024, 2025
    ]
    for pattern in date_patterns:
        if re.search(pattern, merchant_lower):
            return False

    # Reject if it's mostly common words (prepositions, articles, pronouns)
    invalid_words = {
        'for', 'your', 'the', 'a', 'an', 'on', 'in', 'at', 'to', 'of',
        'from', 'with', 'by', 'and', 'or', 'is', 'are', 'was', 'were',
        'this', 'that', 'these', 'those', 'my', 'our', 'their',
        'rides', 'ride', 'trip', 'trips', 'subscription', 'payment',
    }
    words = merchant_lower.split()
    if len(words) > 0:
        invalid_count = sum(1 for w in words if w in invalid_words)
        if invalid_count / len(words) > 0.5:  # More than half are invalid words
            return False

    # Reject promotional phrases
    promo_patterns = [
        'black friday', 'cyber monday', 'sale', 'deals', 'offer',
        'save up', 'discount', 'special', 'limited time', 'exclusive',
        'gift', 'promo', 'marketing', 'newsletter',
    ]
    for pattern in promo_patterns:
        if pattern in merchant_lower:
            return False

    # Reject if it starts with common non-merchant words
    # Note: 'the' and 'a/an' are allowed as they appear in legitimate names
    # (e.g., "The Independent Pharmacy", "The Body Shop", "A Beautiful World")
    bad_starts = ['for ', 'your ', 'on ', 'in ', 'thank ']
    for bad_start in bad_starts:
        if merchant_lower.startswith(bad_start):
            return False

    # Reject common email subject phrases
    invalid_phrases = [
        'thank you', 'thanks for', 'your order', 'your receipt',
        'order confirmation', 'payment confirmation', 'purchase confirmation',
    ]
    for phrase in invalid_phrases:
        if phrase in merchant_lower:
            return False

    return True


def parse_receipt(receipt_id: int) -> dict:
    """
    Main entry point for parsing a receipt.

    Flow (IMPORTANT - pre-filter runs BEFORE extraction):
    1. Check Schema.org Order markup (definitive receipt)
    2. Pre-filter to reject marketing emails
    3. Schema.org extraction
    4. Vendor-specific parsing
    5. Pattern-based extraction
    6. LLM fallback

    Args:
        receipt_id: Database ID of the receipt to parse

    Returns:
        Dictionary with parsed data and status
    """
    receipt = database.get_gmail_receipt_by_id(receipt_id)
    if not receipt:
        return {'error': 'Receipt not found', 'receipt_id': receipt_id}

    raw_data = receipt.get('raw_schema_data') or {}
    if isinstance(raw_data, str):
        try:
            raw_data = json.loads(raw_data)
        except json.JSONDecodeError:
            raw_data = {}

    html_body = raw_data.get('body_html', '')
    text_body = raw_data.get('body_text', '')
    subject = receipt.get('subject', '')
    sender_email = receipt.get('sender_email', '')
    sender_name = receipt.get('sender_name', '')
    sender_domain = receipt.get('merchant_domain', '')
    list_unsubscribe = raw_data.get('list_unsubscribe', '')
    received_at = receipt.get('received_at')  # Get timestamp for date fallback

    # Prepare text for filtering
    text_body_cleaned = text_body or html_to_text(html_body)

    # STEP 1: Check for Schema.org Order markup (definitive receipt signal)
    has_order_markup = has_schema_order_markup(html_body)

    # STEP 2: PRE-FILTER - Run BEFORE any extraction to reject marketing emails
    is_receipt, filter_reason, filter_confidence = is_likely_receipt(
        subject=subject,
        body_text=text_body_cleaned,
        sender_email=sender_email,
        sender_domain=sender_domain,
        list_unsubscribe=list_unsubscribe,
        has_schema_order=has_order_markup
    )

    if not is_receipt:
        logger.debug(f"Pre-filter rejected: {filter_reason}", extra={'receipt_id': receipt_id})
        return mark_receipt_unparseable(
            receipt_id,
            f'Pre-filtered: {filter_reason}'
        )

    logger.debug(f"Pre-filter passed: {filter_reason}", extra={'receipt_id': receipt_id})

    # STEP 3: Try Schema.org extraction (highest confidence)
    if html_body:
        schema_result = extract_schema_org(html_body)
        if schema_result and schema_result.get('merchant_name'):
            # Fallback: use email received_at timestamp if no date was parsed
            if not schema_result.get('receipt_date') and received_at:
                schema_result['receipt_date'] = received_at.strftime('%Y-%m-%d') if hasattr(received_at, 'strftime') else str(received_at)
                schema_result['date_source'] = 'email_received'
            logger.info("Schema.org parsing succeeded", extra={'receipt_id': receipt_id, 'parse_method': 'schema_org'})
            return update_receipt_with_parsed_data(receipt_id, schema_result)

    # STEP 4: Try vendor-specific parser (high confidence for known formats)
    vendor_parser = get_vendor_parser(sender_domain)
    if vendor_parser:
        vendor_result = vendor_parser(html_body, text_body, subject)
        # Accept vendor result if it has amount OR at least identified the merchant
        # (e.g., Amazon "Ordered:" emails may not have parseable amounts)
        if vendor_result and (vendor_result.get('total_amount') or vendor_result.get('merchant_name_normalized')):
            # Fallback: use email received_at timestamp if no date was parsed
            if not vendor_result.get('receipt_date') and received_at:
                vendor_result['receipt_date'] = received_at.strftime('%Y-%m-%d') if hasattr(received_at, 'strftime') else str(received_at)
                vendor_result['date_source'] = 'email_received'
            logger.info(
                f"Vendor parsing succeeded: {vendor_result.get('parse_method')}",
                extra={'receipt_id': receipt_id, 'parse_method': vendor_result.get('parse_method')}
            )
            return update_receipt_with_parsed_data(receipt_id, vendor_result)

    # STEP 5: Try pattern-based extraction
    pattern_result = extract_with_patterns(
        subject=subject,
        body_text=text_body_cleaned,
        sender_domain=sender_domain,
        sender_email=sender_email,
        sender_name=sender_name
    )

    # Validate pattern result before accepting
    if pattern_result and pattern_result.get('total_amount'):
        merchant = pattern_result.get('merchant_name', '')
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get('receipt_date') and received_at:
                pattern_result['receipt_date'] = received_at.strftime('%Y-%m-%d') if hasattr(received_at, 'strftime') else str(received_at)
                pattern_result['date_source'] = 'email_received'
            logger.info("Pattern parsing succeeded", extra={'receipt_id': receipt_id, 'parse_method': 'pattern'})
            return update_receipt_with_parsed_data(receipt_id, pattern_result)
        else:
            logger.warning(f"Pattern found invalid merchant name: '{merchant}'", extra={'receipt_id': receipt_id})
            pattern_result['merchant_name'] = None  # Clear invalid merchant

    # STEP 6: Try LLM extraction as fallback
    llm_result = extract_with_llm(
        subject=subject,
        sender=sender_email,
        body_text=text_body_cleaned
    )
    if llm_result and llm_result.get('total_amount'):
        # Fallback: use email received_at timestamp if no date was parsed
        if not llm_result.get('receipt_date') and received_at:
            llm_result['receipt_date'] = received_at.strftime('%Y-%m-%d') if hasattr(received_at, 'strftime') else str(received_at)
            llm_result['date_source'] = 'email_received'
        logger.info("LLM parsing succeeded", extra={'receipt_id': receipt_id, 'parse_method': 'llm'})
        return update_receipt_with_parsed_data(receipt_id, llm_result)

    # Fall back to pattern data if we have VALID merchant at least
    if pattern_result and pattern_result.get('merchant_name'):
        merchant = pattern_result.get('merchant_name', '')
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get('receipt_date') and received_at:
                pattern_result['receipt_date'] = received_at.strftime('%Y-%m-%d') if hasattr(received_at, 'strftime') else str(received_at)
                pattern_result['date_source'] = 'email_received'
            pattern_result['parse_confidence'] = 50
            pattern_result['parsing_status'] = 'parsed'
            return update_receipt_with_parsed_data(receipt_id, pattern_result)
        else:
            logger.warning(f"Fallback rejected invalid merchant name: '{merchant}'", extra={'receipt_id': receipt_id})

    # Mark as unparseable
    return mark_receipt_unparseable(receipt_id, 'No structured data, patterns, or LLM extraction succeeded')


def parse_receipt_content(
    html_body: str,
    text_body: str,
    subject: str,
    sender_email: str,
    sender_domain: str = None,
    sender_name: str = None,
    list_unsubscribe: str = None,
    skip_llm: bool = True,
    received_at: datetime = None
) -> dict:
    """
    Parse email content directly (without database).

    Used during sync to parse emails before storing.
    Returns parsed data dictionary that can be stored directly.

    Flow:
    1. Pre-filter to reject marketing emails
    2. Vendor-specific parsing (highest priority - tailored to known formats)
    3. Schema.org extraction (fallback for vendors without custom parsers)
    4. Pattern-based extraction
    5. LLM fallback (optional, disabled by default during sync)

    Args:
        html_body: HTML body of email
        text_body: Plain text body of email
        subject: Email subject
        sender_email: Sender email address
        sender_domain: Sender domain (extracted from email if not provided)
        sender_name: Sender display name from email header
        list_unsubscribe: List-Unsubscribe header value
        skip_llm: Skip LLM extraction (faster, no cost)
        received_at: Email received timestamp (fallback for receipt_date if not parsed)

    Returns:
        Dictionary with parsed data:
        - merchant_name, merchant_name_normalized
        - total_amount, currency_code
        - order_id, receipt_date (falls back to received_at if not parsed from body)
        - date_source ('email_body' or 'email_received' to track date origin)
        - line_items (list)
        - parse_method, parse_confidence
        - parsing_status ('parsed' or 'unparseable')
        - parsing_error (if unparseable)
    """
    # Extract domain if not provided
    if not sender_domain and sender_email:
        if '@' in sender_email:
            sender_domain = sender_email.split('@')[-1].lower()

    # Prepare text for filtering
    text_body_cleaned = text_body or html_to_text(html_body)

    # STEP 1: Check for Schema.org Order markup (definitive receipt signal)
    has_order_markup = has_schema_order_markup(html_body) if html_body else False

    # STEP 2: PRE-FILTER - Run BEFORE any extraction to reject marketing emails
    is_receipt, filter_reason, filter_confidence = is_likely_receipt(
        subject=subject,
        body_text=text_body_cleaned,
        sender_email=sender_email,
        sender_domain=sender_domain,
        list_unsubscribe=list_unsubscribe,
        has_schema_order=has_order_markup
    )

    if not is_receipt:
        return {
            'parsing_status': 'unparseable',
            'parsing_error': f'Pre-filtered: {filter_reason}',
            'parse_confidence': 0,
            'parse_method': 'pre_filter',
        }

    # STEP 3: Try vendor-specific parser FIRST (highest confidence for known formats)
    # Vendor parsers are tailored to specific email formats and should take priority
    vendor_parser = get_vendor_parser(sender_domain)
    if vendor_parser:
        try:
            vendor_result = vendor_parser(html_body or '', text_body or '', subject)
            # Accept vendor result if it has amount, order_id, OR identified the merchant
            if vendor_result and (vendor_result.get('total_amount') or vendor_result.get('order_id') or vendor_result.get('merchant_name_normalized')):
                # Fallback: use email received_at timestamp if no date was parsed from body
                if not vendor_result.get('receipt_date') and received_at:
                    vendor_result['receipt_date'] = received_at.strftime('%Y-%m-%d')
                    vendor_result['date_source'] = 'email_received'  # Track where date came from
                vendor_result['parsing_status'] = 'parsed'
                return vendor_result
        except Exception as e:
            # CRITICAL FIX: Vendor parser crashes should not kill entire sync
            # Log error and fall through to next parser instead
            from mcp.logging_config import get_logger
            from mcp.error_tracking import GmailError, ErrorStage

            logger = get_logger(__name__)
            logger.error(
                f"Vendor parser failed for {sender_domain}: {e}",
                extra={'merchant': sender_domain},
                exc_info=True
            )

            # Track error for statistics (don't let error tracking itself crash sync)
            try:
                error = GmailError.from_exception(
                    e, ErrorStage.VENDOR_PARSE,
                    context={'sender_domain': sender_domain, 'message_id': message_id}
                )
                # Note: connection_id and sync_job_id not available at this level
                # Error will be logged but not linked to specific job
                error.log()
            except:
                pass  # Silently ignore error tracking failures

            # Fall through to next parser (schema.org, pattern, etc.)

    # STEP 4: Try Schema.org extraction (fallback for vendors without custom parsers)
    if html_body:
        schema_result = extract_schema_org(html_body)
        if schema_result and schema_result.get('merchant_name'):
            # Fallback: use email received_at timestamp if no date was parsed
            if not schema_result.get('receipt_date') and received_at:
                schema_result['receipt_date'] = received_at.strftime('%Y-%m-%d')
                schema_result['date_source'] = 'email_received'
            schema_result['parsing_status'] = 'parsed'
            return schema_result

    # STEP 5: Try pattern-based extraction
    pattern_result = extract_with_patterns(
        subject=subject,
        body_text=text_body_cleaned,
        sender_domain=sender_domain,
        sender_email=sender_email,
        sender_name=sender_name
    )

    # Validate pattern result before accepting
    if pattern_result and pattern_result.get('total_amount'):
        merchant = pattern_result.get('merchant_name', '')
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get('receipt_date') and received_at:
                pattern_result['receipt_date'] = received_at.strftime('%Y-%m-%d')
                pattern_result['date_source'] = 'email_received'
            pattern_result['parsing_status'] = 'parsed'
            return pattern_result

    # STEP 6: Try LLM extraction as fallback (if enabled)
    if not skip_llm:
        llm_result = extract_with_llm(
            subject=subject,
            sender=sender_email,
            body_text=text_body_cleaned
        )
        if llm_result and llm_result.get('total_amount'):
            # Fallback: use email received_at timestamp if no date was parsed
            if not llm_result.get('receipt_date') and received_at:
                llm_result['receipt_date'] = received_at.strftime('%Y-%m-%d')
                llm_result['date_source'] = 'email_received'
            llm_result['parsing_status'] = 'parsed'
            return llm_result

    # Fall back to pattern data if we have VALID merchant at least
    if pattern_result and pattern_result.get('merchant_name'):
        merchant = pattern_result.get('merchant_name', '')
        if is_valid_merchant_name(merchant):
            # Fallback: use email received_at timestamp if no date was parsed
            if not pattern_result.get('receipt_date') and received_at:
                pattern_result['receipt_date'] = received_at.strftime('%Y-%m-%d')
                pattern_result['date_source'] = 'email_received'
            pattern_result['parse_confidence'] = 50
            pattern_result['parsing_status'] = 'parsed'
            return pattern_result

    # Mark as unparseable - still return basic info for tracking
    return {
        'parsing_status': 'unparseable',
        'parsing_error': 'No structured data or patterns found',
        'parse_confidence': 0,
        'parse_method': 'none',
        'merchant_name': sender_domain,  # Use domain as fallback merchant
        'merchant_name_normalized': sender_domain.replace('.', '_') if sender_domain else None,
    }


def extract_schema_org(html_body: str) -> Optional[dict]:
    """
    Extract Schema.org data from email HTML using extruct.

    Handles JSON-LD, Microdata, and RDFa formats uniformly.

    Args:
        html_body: Raw HTML content of email

    Returns:
        Parsed receipt dictionary or None
    """
    if not html_body:
        return None

    # Try extruct first (handles JSON-LD, Microdata, RDFa)
    if EXTRUCT_AVAILABLE:
        result = _extract_with_extruct(html_body)
        if result:
            return result

    # Fallback to manual BeautifulSoup parsing for JSON-LD only
    return _extract_json_ld_manual(html_body)


def _extract_with_extruct(html_body: str) -> Optional[dict]:
    """
    Extract structured data using extruct library.

    Args:
        html_body: Raw HTML content

    Returns:
        Parsed receipt dictionary or None
    """
    try:
        # Extract all supported formats
        data = extruct.extract(
            html_body,
            syntaxes=['json-ld', 'microdata', 'rdfa'],
            uniform=True  # Normalize all formats to same structure
        )

        # Check each syntax type for Order/Invoice/Receipt
        for syntax in ['json-ld', 'microdata', 'rdfa']:
            items = data.get(syntax, [])
            for item in items:
                item_type = item.get('@type', '')

                # Handle array types (extruct sometimes returns list)
                if isinstance(item_type, list):
                    item_type = item_type[0] if item_type else ''

                # Check for receipt-related types
                if item_type in ['Order', 'Invoice', 'Receipt', 'ConfirmAction']:
                    return parse_schema_org_order(item)

                # Check nested @graph structure
                if '@graph' in item:
                    for node in item['@graph']:
                        node_type = node.get('@type', '')
                        if isinstance(node_type, list):
                            node_type = node_type[0] if node_type else ''
                        if node_type in ['Order', 'Invoice', 'Receipt']:
                            return parse_schema_org_order(node)

    except Exception as e:
        logger.warning(f"Extruct extraction failed: {e}", exc_info=True)

    return None


def _extract_json_ld_manual(html_body: str) -> Optional[dict]:
    """
    Fallback manual JSON-LD extraction using BeautifulSoup.

    Args:
        html_body: Raw HTML content

    Returns:
        Parsed receipt dictionary or None
    """
    try:
        soup = BeautifulSoup(html_body, 'lxml')
    except Exception:
        soup = BeautifulSoup(html_body, 'html.parser')

    scripts = soup.find_all('script', type='application/ld+json')

    for script in scripts:
        try:
            if not script.string:
                continue

            data = json.loads(script.string)

            # Handle both single object and array of objects
            items = data if isinstance(data, list) else [data]

            for item in items:
                item_type = item.get('@type', '')

                # Check for receipt-related types
                if item_type in ['Order', 'Invoice', 'Receipt', 'ConfirmAction']:
                    return parse_schema_org_order(item)

                # Check nested @graph structure
                if '@graph' in item:
                    for node in item['@graph']:
                        if node.get('@type') in ['Order', 'Invoice', 'Receipt']:
                            return parse_schema_org_order(node)

        except (json.JSONDecodeError, AttributeError, TypeError):
            continue

    return None


def parse_schema_org_order(data: dict) -> dict:
    """
    Parse Schema.org Order/Invoice into our receipt format.

    Args:
        data: Schema.org JSON-LD object

    Returns:
        Receipt data dictionary
    """
    # Extract merchant name from various possible locations
    merchant_name = None
    seller = data.get('seller') or data.get('merchant') or data.get('provider')
    if isinstance(seller, dict):
        merchant_name = seller.get('name')
    elif isinstance(seller, str):
        merchant_name = seller

    # Extract total amount
    total_amount = None
    currency = 'GBP'

    # Try price specification first
    price_spec = data.get('acceptedOffer', {}).get('priceSpecification', {})
    if price_spec:
        total_amount = price_spec.get('price')
        currency = price_spec.get('priceCurrency', 'GBP')

    # Fallback to direct price fields
    if total_amount is None:
        total_amount = (
            data.get('totalPrice') or
            data.get('total') or
            data.get('price') or
            data.get('totalPaymentDue', {}).get('value')
        )

    if total_amount is None:
        total_payment = data.get('totalPaymentDue')
        if isinstance(total_payment, dict):
            total_amount = total_payment.get('value') or total_payment.get('price')
            currency = total_payment.get('priceCurrency', currency)

    # Convert amount to float
    if total_amount is not None:
        try:
            total_amount = float(str(total_amount).replace(',', ''))
        except (ValueError, TypeError):
            total_amount = None

    # Extract date
    receipt_date = None
    date_str = data.get('orderDate') or data.get('paymentDueDate') or data.get('dateCreated')
    if date_str:
        receipt_date = parse_date_string(date_str)

    # Extract line items with enhanced data
    line_items = []
    ordered_items = data.get('orderedItem', [])
    if not isinstance(ordered_items, list):
        ordered_items = [ordered_items]

    for item in ordered_items:
        if isinstance(item, dict):
            item_name = item.get('name') or item.get('orderedItem', {}).get('name')
            item_desc = item.get('description')
            item_price = item.get('price')

            # Try to get price from nested priceSpecification
            if item_price is None:
                price_spec = item.get('priceSpecification', {})
                if isinstance(price_spec, dict):
                    item_price = price_spec.get('price')

            # Try to convert price to float
            if item_price is not None:
                try:
                    item_price = float(str(item_price).replace(',', ''))
                except (ValueError, TypeError):
                    item_price = None

            line_items.append({
                'name': item_name,
                'description': item_desc or infer_description_from_name(item_name),
                'category_hint': infer_category_from_name(item_name),
                'quantity': item.get('orderQuantity', 1),
                'price': item_price
            })

    return {
        'merchant_name': merchant_name,
        'merchant_name_normalized': normalize_merchant_name(merchant_name),
        'order_id': data.get('orderNumber') or data.get('confirmationNumber'),
        'total_amount': total_amount,
        'currency_code': currency,
        'receipt_date': receipt_date,
        'line_items': line_items if line_items else None,
        'parse_method': 'schema_org',
        'parse_confidence': 95,
        'parsing_status': 'parsed',
        'raw_schema_data': data,
    }


def infer_description_from_name(name: str) -> Optional[str]:
    """
    Infer a brief description from product name.

    Args:
        name: Product name

    Returns:
        Brief description or None
    """
    if not name:
        return None

    name_lower = name.lower()

    type_patterns = [
        (r'headphone|earphone|earbud|airpod', 'audio headphones/earbuds'),
        (r'cable|charger|adapter|usb', 'charging/connectivity accessory'),
        (r'case|cover|screen protector', 'protective case/cover'),
        (r'battery|power bank', 'portable power/battery'),
        (r'book|kindle|paperback|hardcover', 'book'),
        (r'shirt|dress|pants|jeans|jacket|coat', 'clothing item'),
        (r'toy|lego|game|puzzle', 'toy/game'),
        (r'vitamin|supplement|medicine', 'health supplement'),
        (r'food|snack|chocolate|coffee|tea', 'food/beverage'),
        (r'cleaning|soap|detergent', 'cleaning product'),
        (r'phone|tablet|laptop|computer', 'electronic device'),
        (r'subscription|monthly|annual', 'subscription service'),
        (r'delivery|shipping', 'delivery service'),
    ]

    for pattern, description in type_patterns:
        if re.search(pattern, name_lower):
            return description

    return None


def infer_category_from_name(name: str) -> str:
    """
    Infer category hint from product name.

    Args:
        name: Product name

    Returns:
        Category hint string
    """
    if not name:
        return 'other'

    name_lower = name.lower()

    category_patterns = [
        (r'headphone|speaker|audio|earphone|earbud|airpod|cable|charger|phone|tablet|laptop|computer|usb|hdmi|adapter|battery|power bank', 'electronics'),
        (r'book|kindle|paperback|hardcover|novel|magazine', 'entertainment'),
        (r'shirt|dress|pants|jeans|jacket|coat|shoe|sock|underwear|clothing', 'clothing'),
        (r'food|snack|chocolate|coffee|tea|grocery|organic|vitamin|supplement', 'groceries'),
        (r'toy|lego|game|puzzle|doll|action figure', 'entertainment'),
        (r'cleaning|soap|detergent|shampoo|toothpaste|tissue', 'home'),
        (r'medicine|pharmacy|health|first aid|bandage', 'health'),
        (r'kitchen|cooking|pan|pot|utensil|plate|bowl|cup', 'home'),
        (r'uber|lyft|taxi|ride|trip', 'transport'),
        (r'deliveroo|uber eats|just eat|delivery', 'food_delivery'),
        (r'subscription|monthly|annual|premium|membership', 'subscription'),
        (r'netflix|spotify|disney|streaming', 'subscription'),
    ]

    for pattern, category in category_patterns:
        if re.search(pattern, name_lower):
            return category

    return 'other'


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


def extract_with_llm(
    subject: str,
    sender: str,
    body_text: str
) -> Optional[dict]:
    """
    Extract receipt data using LLM.

    Uses the configured LLM provider to parse unstructured receipt emails.
    Returns parsed data with cost tracking.

    Args:
        subject: Email subject
        sender: Sender email/name
        body_text: Plain text body

    Returns:
        Parsed receipt dictionary or None
    """
    try:
        from config.llm_config import load_llm_config, LLMProvider
        from mcp.llm_providers import (
            AnthropicProvider,
            OpenAIProvider,
            GoogleProvider,
            DeepseekProvider,
            OllamaProvider,
        )
    except ImportError as e:
        logger.warning(f"LLM providers not available: {e}")
        return None

    config = load_llm_config()
    if not config:
        logger.debug("LLM not configured for Gmail parsing")
        return None

    # Build provider
    providers = {
        LLMProvider.ANTHROPIC: AnthropicProvider,
        LLMProvider.OPENAI: OpenAIProvider,
        LLMProvider.GOOGLE: GoogleProvider,
        LLMProvider.DEEPSEEK: DeepseekProvider,
        LLMProvider.OLLAMA: OllamaProvider,
    }

    ProviderClass = providers.get(config.provider)
    if not ProviderClass:
        logger.warning(f"Unknown LLM provider: {config.provider}")
        return None

    try:
        provider_kwargs = {
            "api_key": config.api_key,
            "model": config.model,
            "timeout": config.timeout,
            "debug": config.debug,
            "api_base_url": config.api_base_url,
        }

        if config.provider == LLMProvider.OLLAMA:
            provider_kwargs["cost_per_token"] = config.ollama_cost_per_token
        if config.provider == LLMProvider.ANTHROPIC:
            provider_kwargs["admin_api_key"] = config.anthropic_admin_api_key

        provider = ProviderClass(**provider_kwargs)
    except Exception as e:
        logger.error(f"Failed to initialize LLM provider: {e}", exc_info=True)
        return None

    # Truncate body to avoid token limits (max ~2000 chars)
    truncated_body = body_text[:2000] if body_text else ""

    # Build prompt for receipt extraction with enhanced line item details
    prompt = f"""Extract receipt/purchase information from this email. Return JSON only, no explanation.

Subject: {subject}
From: {sender}
Body:
{truncated_body}

Extract and return this JSON structure (use null for missing fields):
{{
  "merchant_name": "Store name",
  "order_id": "Order/confirmation number",
  "total_amount": 12.34,
  "currency_code": "GBP",
  "receipt_date": "YYYY-MM-DD",
  "line_items": [
    {{
      "name": "Full product name as shown",
      "description": "Brief description of what this item IS (e.g., 'wireless earbuds', 'monthly subscription')",
      "category_hint": "groceries|electronics|clothing|entertainment|food_delivery|transport|subscription|services|health|home|other",
      "quantity": 1,
      "price": 12.34
    }}
  ]
}}

Important:
- total_amount must be a number (no currency symbols)
- receipt_date must be YYYY-MM-DD format
- For line_items: extract ALL items if visible, include price per item when shown
- category_hint should be one of: groceries, electronics, clothing, entertainment, food_delivery, transport, subscription, services, health, home, other
- Return only valid JSON, no markdown or explanation"""

    try:
        response = provider.complete(prompt)

        if not response or not response.content:
            return None

        # Parse JSON from response
        content = response.content.strip()

        # Handle markdown code blocks
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()

        parsed = json.loads(content)

        # Calculate cost in cents
        cost_cents = 0
        if hasattr(response, 'total_tokens') and hasattr(response, 'cost_per_1k_tokens'):
            cost_cents = int((response.total_tokens / 1000) * response.cost_per_1k_tokens * 100)
        elif hasattr(response, 'cost'):
            cost_cents = int(response.cost * 100)

        return {
            'merchant_name': parsed.get('merchant_name'),
            'merchant_name_normalized': normalize_merchant_name(parsed.get('merchant_name')),
            'order_id': parsed.get('order_id'),
            'total_amount': float(parsed['total_amount']) if parsed.get('total_amount') else None,
            'currency_code': parsed.get('currency_code', 'GBP'),
            'receipt_date': parsed.get('receipt_date'),
            'line_items': parsed.get('line_items'),
            'parse_method': 'llm',
            'parse_confidence': 70,
            'parsing_status': 'parsed',
            'llm_cost_cents': cost_cents,
        }

    except json.JSONDecodeError as e:
        logger.warning(f"LLM returned invalid JSON: {e}")
        return None
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}", exc_info=True)
        return None


def normalize_merchant_name(name: str) -> Optional[str]:
    """
    Normalize merchant name for matching.

    Args:
        name: Raw merchant name

    Returns:
        Normalized lowercase name
    """
    if not name:
        return None

    # Convert to lowercase
    normalized = name.lower().strip()

    # Remove common suffixes
    for suffix in [' ltd', ' limited', ' inc', ' plc', ' llc', '.com', '.co.uk', ' uk']:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()

    # Remove special characters but keep spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)

    # Collapse multiple spaces
    normalized = re.sub(r'\s+', ' ', normalized)

    return normalized.strip() if normalized else None


def extract_amount(text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract total amount and currency from text.

    Args:
        text: Combined subject and body text

    Returns:
        Tuple of (amount, currency_code)
    """
    text_lower = text.lower()

    # First try total-specific patterns
    for pattern in TOTAL_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(',', '')
            try:
                amount = float(amount_str)
                # Detect currency from context
                currency = detect_currency_from_context(text, match.start())
                return amount, currency
            except ValueError:
                continue

    # Try general amount patterns
    best_amount = None
    best_currency = None

    for pattern in AMOUNT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match_str in matches:
            try:
                amount = float(match_str.replace(',', ''))
                # Take the largest amount (usually the total)
                if best_amount is None or amount > best_amount:
                    best_amount = amount
                    # Detect currency from pattern
                    if '£' in pattern or 'GBP' in pattern:
                        best_currency = 'GBP'
                    elif '$' in pattern or 'USD' in pattern:
                        best_currency = 'USD'
                    elif '€' in pattern or 'EUR' in pattern:
                        best_currency = 'EUR'
            except ValueError:
                continue

    return best_amount, best_currency


def detect_currency_from_context(text: str, position: int) -> str:
    """
    Detect currency from symbols near the match position.

    Args:
        text: Full text
        position: Position of amount match

    Returns:
        Currency code (defaults to GBP)
    """
    # Check 20 chars before and after position
    context = text[max(0, position - 20):position + 30]

    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in context:
            return code

    return 'GBP'  # Default to GBP


def extract_order_id(text: str) -> Optional[str]:
    """
    Extract order/confirmation number from text.

    Args:
        text: Combined subject and body text

    Returns:
        Order ID string or None
    """
    patterns = [
        r'order\s*(?:#|number|no\.?|id)?[:\s]*([A-Z0-9\-]{5,30})',
        r'confirmation\s*(?:#|number|no\.?)?[:\s]*([A-Z0-9\-]{5,30})',
        r'reference\s*(?:#|number|no\.?)?[:\s]*([A-Z0-9\-]{5,30})',
        r'booking\s*(?:#|number|no\.?|ref)?[:\s]*([A-Z0-9\-]{5,30})',
        r'invoice\s*(?:#|number|no\.?)?[:\s]*([A-Z0-9\-]{5,30})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            order_id = match.group(1).strip()
            # Filter out common false positives
            if len(order_id) >= 5 and not order_id.lower() in ['your', 'order', 'total']:
                return order_id

    return None


def extract_date(text: str) -> Optional[str]:
    """
    Extract date from text.

    Args:
        text: Combined subject and body text

    Returns:
        Date string in YYYY-MM-DD format or None
    """
    for pattern, format_type in DATE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                groups = match.groups()

                if format_type == 'DMY' and len(groups) == 3:
                    if groups[0].isdigit():
                        day, month, year = int(groups[0]), int(groups[1]), int(groups[2])
                    else:
                        # Month name format
                        day = int(groups[0])
                        month = MONTH_MAP.get(groups[1].lower()[:3], 1)
                        year = int(groups[2])

                elif format_type == 'YMD':
                    year, month, day = int(groups[0]), int(groups[1]), int(groups[2])

                elif format_type == 'MDY':
                    month = MONTH_MAP.get(groups[0].lower()[:3], 1)
                    day = int(groups[1])
                    year = int(groups[2])

                else:
                    continue

                # Validate date
                if 1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2100:
                    return f"{year:04d}-{month:02d}-{day:02d}"

            except (ValueError, IndexError):
                continue

    return None


def parse_date_string(date_str: str) -> Optional[str]:
    """
    Parse various date string formats to YYYY-MM-DD.

    Args:
        date_str: Date string from Schema.org

    Returns:
        Date string in YYYY-MM-DD format or None
    """
    if not date_str:
        return None

    # Already in ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}', date_str):
        return date_str[:10]

    # Try common formats
    formats = [
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%m/%d/%Y',
        '%d-%m-%Y',
        '%B %d, %Y',
        '%d %B %Y',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue

    # Fallback to regex extraction
    return extract_date(date_str)


def extract_merchant_from_text(
    subject: str,
    sender_email: str,
    sender_domain: str,
    sender_name: str = None
) -> Optional[str]:
    """
    Extract merchant name from email metadata.

    Priority order:
    1. Known domain mapping (DOMAIN_TO_MERCHANT)
    2. Sender name from email header (if valid)
    3. Subject line patterns
    4. Domain-based fallback

    Args:
        subject: Email subject
        sender_email: Sender email address
        sender_domain: Sender domain
        sender_name: Sender name from email header (e.g., "Bloomling" from "Bloomling <uk@bloomling.com>")

    Returns:
        Merchant name or None
    """
    # Priority 1: Check known domain mapping
    if sender_domain and sender_domain.lower() in DOMAIN_TO_MERCHANT:
        return DOMAIN_TO_MERCHANT[sender_domain.lower()]

    # Priority 2: Use sender name if it looks like a merchant (not generic)
    if sender_name:
        sender_name_clean = sender_name.strip()
        # Reject generic sender names
        generic_senders = {'noreply', 'no-reply', 'info', 'support', 'orders', 'receipts',
                          'notifications', 'hello', 'team', 'customer service'}
        if (len(sender_name_clean) >= 2 and
            sender_name_clean.lower() not in generic_senders and
            not sender_name_clean.lower().startswith('no') and
            is_valid_merchant_name(sender_name_clean)):
            return sender_name_clean

    # Priority 3: Try to extract from subject (with validation)
    subject_patterns = [
        r'(?:your\s+)?(?:order|receipt|confirmation)\s+(?:from\s+)?([A-Za-z0-9\s&\']+)',
        r'([A-Za-z0-9\s&\']+?)(?:\s+order|\s+receipt|\s+confirmation)',
        r'thank(?:s|you)?\s+for\s+(?:your\s+)?(?:order|purchase)\s+(?:from\s+)?([A-Za-z0-9\s&\']+)',
    ]

    for pattern in subject_patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            merchant = match.group(1).strip()
            # Validate extracted merchant name
            if len(merchant) >= 2 and is_valid_merchant_name(merchant):
                return merchant

    # Priority 4: Fallback to domain-based name
    if sender_domain:
        # Remove common prefixes
        domain_name = sender_domain.split('.')[0]
        for prefix in ['no-reply', 'noreply', 'info', 'mail', 'email', 'orders', 'receipts']:
            if domain_name.lower() == prefix:
                return None
        return domain_name.replace('-', ' ').replace('_', ' ').title()

    return None


def get_sender_pattern(sender_domain: str) -> Optional[dict]:
    """
    Get sender-specific parsing pattern from database.

    Args:
        sender_domain: Sender's domain

    Returns:
        Pattern configuration or None
    """
    if not sender_domain:
        return None

    return database.get_gmail_sender_pattern(sender_domain)


def html_to_text(html: str) -> str:
    """
    Convert HTML to plain text.

    Args:
        html: HTML content

    Returns:
        Plain text content
    """
    if not html:
        return ''

    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        soup = BeautifulSoup(html, 'html.parser')

    # Remove script and style elements
    for element in soup(['script', 'style', 'head', 'meta', 'noscript']):
        element.decompose()

    # Get text and clean up whitespace
    text = soup.get_text(separator=' ')
    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def compute_receipt_hash(
    merchant_name: str,
    amount: float,
    receipt_date: str,
    order_id: str = None
) -> str:
    """
    Compute deduplication hash for a receipt.

    Args:
        merchant_name: Normalized merchant name
        amount: Total amount
        receipt_date: Date string (YYYY-MM-DD)
        order_id: Optional order ID

    Returns:
        SHA256 hash string
    """
    components = [
        (merchant_name or '').lower().strip(),
        f"{float(amount):.2f}" if amount else '',
        receipt_date or '',
        (order_id or '').strip(),
    ]
    hash_input = '|'.join(components)
    return hashlib.sha256(hash_input.encode()).hexdigest()


def update_receipt_with_parsed_data(receipt_id: int, parsed_data: dict) -> dict:
    """
    Update receipt in database with parsed data.

    Args:
        receipt_id: Database receipt ID
        parsed_data: Parsed receipt data

    Returns:
        Updated receipt dictionary
    """
    # Compute receipt hash for deduplication
    receipt_hash = compute_receipt_hash(
        parsed_data.get('merchant_name_normalized'),
        parsed_data.get('total_amount'),
        parsed_data.get('receipt_date'),
        parsed_data.get('order_id')
    )

    # Update database
    database.update_gmail_receipt_parsed(
        receipt_id=receipt_id,
        merchant_name=parsed_data.get('merchant_name'),
        merchant_name_normalized=parsed_data.get('merchant_name_normalized'),
        order_id=parsed_data.get('order_id'),
        total_amount=parsed_data.get('total_amount'),
        currency_code=parsed_data.get('currency_code', 'GBP'),
        receipt_date=parsed_data.get('receipt_date'),
        line_items=parsed_data.get('line_items'),
        receipt_hash=receipt_hash,
        parse_method=parsed_data.get('parse_method'),
        parse_confidence=parsed_data.get('parse_confidence'),
        parsing_status=parsed_data.get('parsing_status', 'parsed'),
        llm_cost_cents=parsed_data.get('llm_cost_cents'),
    )

    return {
        'status': 'parsed',
        'receipt_id': receipt_id,
        'parse_method': parsed_data.get('parse_method'),
        'parse_confidence': parsed_data.get('parse_confidence'),
        'merchant_name': parsed_data.get('merchant_name'),
        'total_amount': parsed_data.get('total_amount'),
    }


def mark_receipt_unparseable(receipt_id: int, error: str) -> dict:
    """
    Mark receipt as unparseable.

    Args:
        receipt_id: Database receipt ID
        error: Error message

    Returns:
        Status dictionary
    """
    database.update_gmail_receipt_status(
        receipt_id=receipt_id,
        parsing_status='unparseable',
        parsing_error=error
    )

    return {
        'status': 'unparseable',
        'receipt_id': receipt_id,
        'error': error,
    }


def parse_pending_receipts(connection_id: int, limit: int = 100) -> dict:
    """
    Parse all pending receipts for a connection.

    Args:
        connection_id: Database connection ID
        limit: Maximum receipts to process

    Returns:
        Summary dictionary
    """
    pending = database.get_pending_gmail_receipts(connection_id, limit)

    results = {
        'total': len(pending),
        'parsed': 0,
        'failed': 0,
        'by_method': {'schema_org': 0, 'pattern': 0, 'llm': 0},
    }

    for receipt in pending:
        try:
            result = parse_receipt(receipt['id'])

            if result.get('status') == 'parsed':
                results['parsed'] += 1
                method = result.get('parse_method', 'unknown')
                if method in results['by_method']:
                    results['by_method'][method] += 1
            else:
                results['failed'] += 1

        except Exception as e:
            logger.error(f"Failed to parse receipt {receipt['id']}: {e}", extra={'receipt_id': receipt['id']}, exc_info=True)
            results['failed'] += 1

    return results
