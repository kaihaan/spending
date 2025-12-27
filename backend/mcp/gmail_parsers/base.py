"""
Gmail Parser Base - Shared Utilities and Registry

Contains:
- Parser registry and decorator for vendor-specific parsers
- Common utility functions for amount and date parsing
- Type definitions for parser functions
"""

import re
from datetime import datetime
from typing import Optional, Callable


# Type alias for parser functions
VendorParser = Callable[[str, str, str], Optional[dict]]


# Registry of vendor domain -> parser function
VENDOR_PARSERS: dict[str, VendorParser] = {}


def register_vendor(domains: list[str]):
    """Decorator to register a parser for specific domains."""
    def decorator(func: VendorParser):
        for domain in domains:
            VENDOR_PARSERS[domain] = func
        return func
    return decorator


def get_vendor_parser(sender_domain: str) -> Optional[VendorParser]:
    """
    Get vendor-specific parser for a domain.

    Args:
        sender_domain: Email sender domain (e.g., 'amazon.co.uk')

    Returns:
        Parser function or None if no specific parser exists
    """
    if not sender_domain:
        return None

    sender_domain = sender_domain.lower()

    # Check exact match first
    if sender_domain in VENDOR_PARSERS:
        return VENDOR_PARSERS[sender_domain]

    # Check partial match (e.g., 'email.amazon.co.uk' matches 'amazon.co.uk')
    for domain, parser in VENDOR_PARSERS.items():
        if domain in sender_domain:
            return parser

    return None


def parse_amount(text: str) -> Optional[float]:
    """Extract numeric amount from text like '£12.34', '12.34 GBP', or '€ 63,75' (European format)."""
    if not text:
        return None

    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[£$€¥\s]', '', text)

    # Handle European format: comma as decimal separator (e.g., "63,75" -> "63.75")
    # Pattern: comma followed by exactly 2 digits at end of number
    if re.match(r'^\d+,\d{2}$', cleaned):
        cleaned = cleaned.replace(',', '.')
    else:
        # Otherwise remove commas (thousands separators)
        cleaned = cleaned.replace(',', '')

    # Extract number
    match = re.search(r'(\d+\.?\d*)', cleaned)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            pass
    return None


def parse_date_text(text: str) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD."""
    if not text:
        return None

    # Month name patterns (full and abbreviated)
    month_pattern = r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)'

    # Common patterns
    patterns = [
        # 15 January 2024 or 15 Jan 2024
        (rf'(\d{{1,2}})\s+({month_pattern})\s+(\d{{4}})', 'DMY_FULL'),
        # January 15, 2024 or Jan 15, 2024
        (rf'({month_pattern})\s+(\d{{1,2}}),?\s+(\d{{4}})', 'MDY_FULL'),
        # 15/01/2024 or 15-01-2024
        (r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', 'DMY'),
        # 2024-01-15
        (r'(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})', 'YMD'),
    ]

    # Map both full and abbreviated month names to numbers
    months = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'sept': 9, 'september': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12,
    }

    for pattern, fmt in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                if fmt == 'DMY_FULL':
                    day = int(match.group(1))
                    month = months[match.group(2).lower()]
                    year = int(match.group(3))
                elif fmt == 'MDY_FULL':
                    month = months[match.group(1).lower()]
                    day = int(match.group(2))
                    year = int(match.group(3))
                elif fmt == 'DMY':
                    day = int(match.group(1))
                    month = int(match.group(2))
                    year = int(match.group(3))
                elif fmt == 'YMD':
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                else:
                    continue

                return f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, KeyError):
                continue

    return None
