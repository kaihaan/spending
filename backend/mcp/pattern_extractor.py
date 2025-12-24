"""
Transaction Pattern Extractor
Extracts structured data from transaction descriptions using patterns from patterns.csv
"""

import re
from typing import Dict, Optional, Tuple

# Pattern definitions based on patterns.csv
# Each pattern includes: provider, variant, pattern, and variables
PATTERNS = [
    {
        'provider': 'Apple Pay',
        'variant': None,
        'pattern': r'^(.+?)\s*\(VIA APPLE PAY\),\s*ON\s+(\d{1,2})-(\d{1,2})-(\d{4})$',
        'variables': ['payee', 'day', 'month', 'year'],
        'confidence': 95
    },
    {
        'provider': 'Card Payment',
        'variant': None,
        'pattern': r'^CARD PAYMENT TO\s+(.+?)\s*ON\s+(\d{1,2})-(\d{1,2})-(\d{4})$',
        'variables': ['payee', 'day', 'month', 'year'],
        'confidence': 90
    },
    {
        'provider': 'Card Payment',
        'variant': None,
        'pattern': r'^CARD PAYMENT TO\s+(.+?)\*(.+?)\s+ON\s+(\d{1,2})-(\d{1,2})-(\d{4})$',
        'variables': ['payee', 'reference', 'day', 'month', 'year'],
        'confidence': 95
    },
    {
        'provider': 'Card Payment',
        'variant': 'Zipcar',
        'pattern': r'^CARD PAYMENT TO\s+(.+?)\s+Trip\s+(\w+)\s+ON\s+(\d{1,2})-(\d{1,2})-(\d{4})$',
        'variables': ['payee', 'trip_date', 'day', 'month', 'year'],
        'confidence': 90
    },
    {
        'provider': 'Direct Debit',
        'variant': None,
        'pattern': r'^DIRECT DEBIT PAYMENT TO\s+(.+?)\s+REF\s+([A-Z0-9\-_]+)\s*[/,]*\s*MANDATE NO\s+(\d+)$',
        'variables': ['payee', 'reference', 'mandate_number'],
        'confidence': 95
    },
    {
        'provider': 'Transfer',
        'variant': None,
        'pattern': r'^TRANSFER FROM\s+(.+)$',
        'variables': ['sender'],
        'confidence': 90
    },
    {
        'provider': 'Santander',
        'variant': 'Cashback',
        'pattern': r'^(\d+)\s+Direct Debit Payments at\s+([\d.]+)%\s+Cashback$',
        'variables': ['payment_count', 'rate'],
        'confidence': 90
    },
    {
        'provider': 'Santander',
        'variant': 'Interest',
        'pattern': r'^INTEREST PAID AFTER TAX\s+([\d.]+)\s+DEDUCTED$',
        'variables': ['tax'],
        'confidence': 85
    },
]

# Provider-specific variant detection patterns
VARIANT_PATTERNS = {
    'AIRBNB': {
        'provider': 'Card Payment',
        'variant': 'AIRBNB',
        'pattern': r'AIRBNB'
    },
    'Marketplace': {
        'provider': 'Amazon',
        'variant': 'Marketplace',
        'pattern': r'AMZNMktplace'
    },
    'Zettle': {
        'provider': 'Apple Pay',
        'variant': 'Zettle',
        'pattern': r'ZETTLE'
    },
    'PPOINT': {
        'provider': 'Apple Pay',
        'variant': 'PPOINT',
        'pattern': r'PPOINT_\*'
    },
    'LIME': {
        'provider': 'Card Payment',
        'variant': 'LIME',
        'pattern': r'LIME'
    },
    'SUMUP': {
        'provider': 'Apple Pay',
        'variant': 'SUMUP',
        'pattern': r'SUMUP\s*\*'
    },
}


def extract_provider_and_variant(description: str) -> Tuple[Optional[str], Optional[str], int]:
    """
    Extract provider and variant from transaction description.

    Args:
        description: Transaction description text

    Returns:
        Tuple of (provider, variant, confidence) - all None if no match found
    """
    if not description:
        return None, None, 0

    description_upper = description.upper()

    # First try variant-specific patterns
    for variant_name, variant_config in VARIANT_PATTERNS.items():
        if re.search(variant_config['pattern'], description_upper):
            return variant_config['provider'], variant_config['variant'], 85

    # Then try general patterns
    for pattern_config in PATTERNS:
        pattern = pattern_config['pattern']
        if re.match(pattern, description):
            return (
                pattern_config['provider'],
                pattern_config['variant'],
                pattern_config['confidence']
            )

    return None, None, 0


def extract_variables(description: str) -> Dict[str, Optional[str]]:
    """
    Extract variables from transaction description using pattern matching.

    Args:
        description: Transaction description text

    Returns:
        Dictionary with extracted variables and confidence score
    """
    if not description:
        return {'extraction_confidence': 0}

    description_upper = description.upper()
    result = {
        'provider': None,
        'variant': None,
        'payee': None,
        'reference': None,
        'mandate_number': None,
        'branch': None,
        'entity': None,
        'trip_date': None,
        'sender': None,
        'rate': None,
        'tax': None,
        'payment_count': None,
        'extraction_confidence': 0
    }

    # Try each pattern
    for pattern_config in PATTERNS:
        match = re.match(pattern_config['pattern'], description)
        if match:
            result['provider'] = pattern_config['provider']
            result['variant'] = pattern_config['variant']
            result['extraction_confidence'] = pattern_config['confidence']

            # Extract variables based on the pattern
            groups = match.groups()
            variables = pattern_config['variables']

            for i, var_name in enumerate(variables):
                if i < len(groups) and groups[i]:
                    if var_name in ['day', 'month', 'year']:
                        # Handle date components - skip for now as they're in description
                        continue
                    result[var_name] = groups[i].strip()

            return result

    # Try variant patterns to at least get provider/variant
    for variant_name, variant_config in VARIANT_PATTERNS.items():
        if re.search(variant_config['pattern'], description_upper):
            result['provider'] = variant_config['provider']
            result['variant'] = variant_config['variant']
            result['extraction_confidence'] = 60
            break

    # Try to extract payee from common patterns even if full pattern doesn't match
    if not result['payee']:
        # Card Payment TO patterns
        match = re.search(r'CARD PAYMENT TO\s+([A-Za-z0-9\s\-*]+?)(?:\s+ON|\s*$|\*)', description)
        if match:
            payee = match.group(1).strip()
            # Remove reference codes
            payee = re.sub(r'\*\w+.*$', '', payee).strip()
            result['payee'] = payee
            if not result['provider']:
                result['provider'] = 'Card Payment'
            result['extraction_confidence'] = max(result['extraction_confidence'], 70)

    return result


def extract_direct_debit_payee_fallback(description: str) -> Dict[str, Optional[str]]:
    """
    Fallback extraction for direct debit transactions when strict pattern fails.
    Extracts payee from 'DIRECT DEBIT PAYMENT TO {payee} REF...' format.

    This handles variations in formatting that the strict pattern doesn't catch:
    - Different spacing/punctuation around REF and MANDATE
    - Missing MANDATE NO entirely
    - Extra characters in reference field

    Args:
        description: Transaction description text

    Returns:
        Dictionary with extracted fields (provider, payee, reference, mandate_number)
    """
    if not description:
        return {}

    # Pattern: DIRECT DEBIT PAYMENT TO {payee} REF {anything}
    # or: DIRECT DEBIT PAYMENT TO {payee} (no REF)
    match = re.match(
        r'^DIRECT DEBIT PAYMENT TO\s+(.+?)(?:\s+REF\s+(.*))?$',
        description,
        re.IGNORECASE
    )

    if match:
        payee = match.group(1).strip()
        rest = match.group(2) or ''

        # Try to extract mandate number from rest
        mandate_match = re.search(r'MANDATE NO\s+(\d+)', rest, re.IGNORECASE)
        mandate_number = mandate_match.group(1) if mandate_match else None

        # Try to extract reference (everything before MANDATE NO or comma)
        reference = None
        if rest:
            ref_match = re.match(r'^([^,]+?)(?:\s*[,/]\s*MANDATE|\s*MANDATE|\s*$)', rest, re.IGNORECASE)
            if ref_match:
                reference = ref_match.group(1).strip()

        return {
            'provider': 'Direct Debit',
            'payee': payee,
            'reference': reference,
            'mandate_number': mandate_number,
            'extraction_confidence': 80  # Lower confidence for fallback
        }

    return {}


def extract_and_update(description: str) -> Dict[str, any]:
    """
    Extract all pattern-based data from a transaction description.

    Args:
        description: Transaction description

    Returns:
        Dictionary with all extracted fields and confidence score.
        Only includes fields with high confidence (>= 70).
    """
    extracted = extract_variables(description)

    # Only return fields with sufficient confidence
    if extracted['extraction_confidence'] >= 70:
        # Return all non-None fields
        return {k: v for k, v in extracted.items() if v is not None}
    else:
        # Return with zero confidence for fields that didn't match
        extracted['extraction_confidence'] = 0
        return extracted
