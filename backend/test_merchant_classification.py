#!/usr/bin/env python3
"""Test merchant identification and category classification."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.truelayer_sync import identify_merchant, classify_and_enrich_transaction

# Test merchant identification
test_cases_merchant = [
    {
        'description': 'TESCO STORES 1234 LONDON',
        'merchant_from_api': None,
        'expected': 'TESCO STORES 1234 LONDON'
    },
    {
        'description': 'TFL TRAVEL CH LONDON',
        'merchant_from_api': 'TFL Travel',
        'expected': 'TFL Travel'  # Prefers API merchant
    },
    {
        'description': 'SAINSBURY SUPERMARKET LONDON',
        'merchant_from_api': None,
        'expected': 'SAINSBURY SUPERMARKET LONDON'
    },
]

print("=" * 70)
print("🏪 Testing Merchant Identification")
print("=" * 70)

for i, test in enumerate(test_cases_merchant, 1):
    result = identify_merchant(test['description'], test['merchant_from_api'])
    status = "✅" if result == test['expected'] else "❌"
    print(f"\n{status} Test {i}:")
    print(f"   Description: {test['description']}")
    print(f"   API Merchant: {test['merchant_from_api']}")
    print(f"   Result: {result}")
    print(f"   Expected: {test['expected']}")

# Test category classification
test_cases_category = [
    {
        'description': 'TESCO STORES 1234 LONDON',
        'merchant': 'TESCO STORES 1234',
        'amount': -50.00,
        'expected_category': 'Groceries'
    },
    {
        'description': 'TFL TRAVEL CH LONDON',
        'merchant': 'TFL Travel',
        'amount': -6.20,
        'expected_category': 'Transport'
    },
    {
        'description': 'STARBUCKS COFFEE LONDON',
        'merchant': 'STARBUCKS COFFEE',
        'amount': -4.50,
        'expected_category': 'Dining'
    },
    {
        'description': 'NETFLIX SUBSCRIPTION',
        'merchant': 'NETFLIX',
        'amount': -10.99,
        'expected_category': 'Entertainment'
    },
    {
        'description': 'SALARY PAYMENT',
        'merchant': None,
        'amount': 3000.00,  # Positive = income
        'expected_category': 'Income'
    },
    {
        'description': 'UNKNOWN MERCHANT XYZ',
        'merchant': 'UNKNOWN MERCHANT',
        'amount': -25.00,
        'expected_category': 'Other'  # Should default to Other
    },
]

print("\n" + "=" * 70)
print("📊 Testing Category Classification")
print("=" * 70)

for i, test in enumerate(test_cases_category, 1):
    txn = {
        'description': test['description'],
        'merchant_name': test['merchant'],
        'amount': test['amount']
    }
    enriched = classify_and_enrich_transaction(txn)
    category = enriched.get('category')
    merchant = enriched.get('merchant_name')
    status = "✅" if category == test['expected_category'] else "⚠️"

    print(f"\n{status} Test {i}:")
    print(f"   Description: {test['description']}")
    print(f"   Amount: £{test['amount']:.2f}")
    print(f"   Merchant Identified: {merchant}")
    print(f"   Category: {category}")
    print(f"   Expected: {test['expected_category']}")

print("\n" + "=" * 70)
print("✅ Merchant identification and classification tests complete!")
print("=" * 70)
