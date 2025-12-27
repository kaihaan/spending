"""
Gmail Parsers - Organized Vendor-Specific Email Parsers

This package contains vendor-specific email parsers organized by domain:
- amazon.py: Amazon orders, Fresh, Business, cancellations, refunds
- apple.py: Apple App Store and iTunes receipts
- financial.py: PayPal and payment processors
- rides.py: Uber, Lyft, Lime
- food_delivery.py: Deliveroo
- ecommerce.py: eBay, Etsy, Vinted
- retail.py: John Lewis, Uniqlo, CEX, World of Books, etc.
- digital_services.py: Microsoft, Google, Figma, Atlassian, Anthropic
- travel.py: Airbnb, British Airways, DHL
- specialty.py: All other specialty vendors

Usage:
    from backend.mcp.gmail_parsers import VENDOR_PARSERS, get_vendor_parser

    # Get parser for a specific domain
    parser = get_vendor_parser('amazon.co.uk')
    if parser:
        result = parser(html_body, text_body, subject)
"""

# Import registry and utilities from base
from .base import VENDOR_PARSERS, get_vendor_parser, parse_amount, parse_date_text

# Import all domain modules to trigger @register_vendor decorators
# This registers all parsers into the VENDOR_PARSERS dict
from . import amazon
from . import apple
from . import financial
from . import rides
from . import food_delivery
from . import ecommerce
from . import retail
from . import digital_services
from . import travel
from . import specialty

# Export the registry and lookup function
__all__ = [
    'VENDOR_PARSERS',
    'get_vendor_parser',
    'parse_amount',
    'parse_date_text',
]
