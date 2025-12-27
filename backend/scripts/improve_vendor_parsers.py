#!/usr/bin/env python3
"""
Script to improve vendor parsers with brand metadata where available.

Since Amazon emails don't contain brand info in the receipt, we'll:
1. Add restaurant extraction for Deliveroo/Uber
2. Add developer extraction for Apple
3. Improve PayPal to extract actual merchant
4. Improve Google Play to extract app/subscription names
5. Add new parsers for missing vendors

Note: Amazon brand data requires external API enrichment, not email parsing.
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("""
================================================================================
VENDOR PARSER IMPROVEMENT PLAN
================================================================================

Based on QA analysis, the following improvements are needed:

1. ✗ Amazon brand metadata - NOT AVAILABLE in email receipts
   → Requires Amazon Product API enrichment (separate task)

2. ✓ Deliveroo/Uber restaurant extraction - Available in emails
   → Will update vendor_deliveroo and vendor_uber parsers

3. ✓ Apple developer/publisher extraction - Available in emails
   → Will update vendor_apple parser

4. ✓ PayPal actual merchant extraction - Available in email body
   → Will update vendor_paypal parser

5. ✓ Google Play app/subscription names - Available in emails
   → Will update vendor_google parser

6. ✓ New parsers for high-volume merchants:
   - World of Books (7 receipts, 70% confidence)
   - Charles Tyrwhitt (3 receipts, 80% confidence)
   - Uniqlo (3 receipts, 85% confidence)

================================================================================
RECOMMENDED APPROACH
================================================================================

For Amazon brand enrichment:
- Create separate LLM-based enrichment task
- OR integrate with Amazon Product Advertising API
- This is NOT an email parsing task

Let's proceed with email-based improvements first.
Press Enter to continue or Ctrl+C to cancel...
""")

try:
    input()
except KeyboardInterrupt:
    print("\nCancelled.")
    sys.exit(0)

print("\nStarting vendor parser improvements...")
print("(Implementation will be done via code edits to gmail_parsers/ modules)")
