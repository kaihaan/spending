"""
Gmail Receipt Parser Package

Modular receipt parsing system for Gmail emails.

Architecture:
- utilities: Common utility functions (merchant normalization, currency detection, etc.)
- filtering: Pre-filtering to reject marketing/promotional emails
- schema_extraction: Schema.org markup extraction
- pattern_extraction: Regex-based pattern matching
- llm_extraction: LLM-powered fallback extraction
- orchestrator: Main parsing coordination and database updates

Public API:
- parse_receipt(receipt_id) - Parse a single receipt from database
- parse_receipt_content(...) - Parse email content directly (used during sync)
- parse_pending_receipts(connection_id, limit) - Batch parse pending receipts
"""

# Import main parsing functions from orchestrator
from .orchestrator import (
    parse_receipt,
    parse_receipt_content,
    update_receipt_with_parsed_data,
    mark_receipt_unparseable,
    parse_pending_receipts,
)

# Import utility functions that may be used externally
from .utilities import (
    normalize_merchant_name,
    compute_receipt_hash,
    html_to_text,
    parse_date_string,
    is_valid_merchant_name,
    extract_amount,
    extract_date,
    extract_order_id,
    extract_merchant_from_text,
    DOMAIN_TO_MERCHANT,
)

# Import filtering functions for external use
from .filtering import (
    is_likely_receipt,
    has_schema_order_markup,
    # Vendor-specific filters (can be used externally for testing)
    is_ebay_receipt_email,
    is_amazon_receipt_email,
    is_uber_receipt_email,
    is_paypal_receipt_email,
    is_microsoft_receipt_email,
    is_apple_receipt_email,
    is_deliveroo_receipt_email,
    is_etsy_receipt_email,
)

# Import extraction functions
from .schema_extraction import (
    extract_schema_org,
    parse_schema_org_order,
    infer_description_from_name,
    infer_category_from_name,
)

from .pattern_extraction import (
    extract_with_patterns,
)

from .llm_extraction import (
    extract_with_llm,
)


__all__ = [
    # Main orchestrator functions (primary API)
    'parse_receipt',
    'parse_receipt_content',
    'update_receipt_with_parsed_data',
    'mark_receipt_unparseable',
    'parse_pending_receipts',

    # Utility functions
    'normalize_merchant_name',
    'compute_receipt_hash',
    'html_to_text',
    'parse_date_string',
    'is_valid_merchant_name',
    'extract_amount',
    'extract_date',
    'extract_order_id',
    'extract_merchant_from_text',
    'DOMAIN_TO_MERCHANT',

    # Filtering functions
    'is_likely_receipt',
    'has_schema_order_markup',
    'is_ebay_receipt_email',
    'is_amazon_receipt_email',
    'is_uber_receipt_email',
    'is_paypal_receipt_email',
    'is_microsoft_receipt_email',
    'is_apple_receipt_email',
    'is_deliveroo_receipt_email',
    'is_etsy_receipt_email',

    # Extraction functions
    'extract_schema_org',
    'parse_schema_org_order',
    'infer_description_from_name',
    'infer_category_from_name',
    'extract_with_patterns',
    'extract_with_llm',
]
