"""
Gmail Parser Utilities

Common utility functions for parsing receipt emails.
Includes:
- Merchant name normalization
- Currency detection
- Amount/date/order ID extraction
- Hash computation for deduplication
- HTML to text conversion
- Validation helpers
"""

import re
import hashlib
from datetime import datetime
from typing import Optional, Tuple
from bs4 import BeautifulSoup

import database_postgres as database


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
