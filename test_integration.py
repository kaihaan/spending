#!/usr/bin/env python3
"""
Integration Test Suite for Refactored Backend

Tests all major API endpoints to verify:
- Database layer refactoring (database/*)
- Service layer separation (services/*)
- Route blueprints (routes/*)
- Gmail parsing modularization (mcp/gmail_parsing/*)
"""

import requests
import sys
import json
from datetime import datetime

BASE_URL = "http://localhost:5000"
PASSED = 0
FAILED = 0

def test(name, url, expected_keys=None, expected_status=200, method='GET', json_data=None):
    """Run a single test case"""
    global PASSED, FAILED

    try:
        if method == 'GET':
            response = requests.get(f"{BASE_URL}{url}", timeout=5)
        elif method == 'POST':
            response = requests.post(f"{BASE_URL}{url}", json=json_data, timeout=5)

        # Check status code
        if response.status_code != expected_status:
            print(f"❌ {name}")
            print(f"   Expected status {expected_status}, got {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            FAILED += 1
            return False

        # Check expected keys if JSON response
        if expected_keys and response.headers.get('content-type', '').startswith('application/json'):
            data = response.json()

            # Handle list responses
            if isinstance(data, list):
                if len(data) == 0:
                    print(f"⚠️  {name} - Empty list returned")
                    PASSED += 1
                    return True
                data = data[0] if isinstance(data[0], dict) else {}

            missing_keys = [k for k in expected_keys if k not in data]
            if missing_keys:
                print(f"❌ {name}")
                print(f"   Missing keys: {missing_keys}")
                print(f"   Response keys: {list(data.keys())[:10]}")
                FAILED += 1
                return False

        print(f"✅ {name}")
        PASSED += 1
        return True

    except requests.exceptions.RequestException as e:
        print(f"❌ {name}")
        print(f"   Connection error: {e}")
        FAILED += 1
        return False
    except json.JSONDecodeError as e:
        print(f"❌ {name}")
        print(f"   JSON decode error: {e}")
        FAILED += 1
        return False
    except Exception as e:
        print(f"❌ {name}")
        print(f"   Unexpected error: {e}")
        FAILED += 1
        return False

def main():
    print("="*60)
    print("INTEGRATION TEST SUITE - Refactored Backend")
    print("="*60)
    print()

    # Health check
    print("Core Health:")
    test("Health Check", "/api/health", expected_keys=['status'])
    print()

    # TrueLayer Routes (routes/truelayer.py + services/truelayer_service.py)
    print("TrueLayer Integration (routes/truelayer.py):")
    test("Get TrueLayer Connections", "/api/truelayer/connections", expected_keys=['id', 'provider_name'])
    test("Get TrueLayer Accounts", "/api/truelayer/accounts")
    test("Get TrueLayer Sync Status", "/api/truelayer/sync/status")
    test("Get TrueLayer Import History", "/api/truelayer/import/history")
    print()

    # Gmail Routes (routes/gmail.py + services/gmail_service.py)
    print("Gmail Integration (routes/gmail.py):")
    test("Get Gmail Connections", "/api/gmail/connections", expected_keys=['id', 'email_address'])
    test("Get Gmail Statistics", "/api/gmail/statistics")
    test("Get Gmail Merchants", "/api/gmail/merchants")
    test("Get Gmail Receipts", "/api/gmail/receipts")
    test("Get Gmail Sync Status", "/api/gmail/sync/status")
    print()

    # Enrichment Routes (routes/enrichment.py + services/enrichment_service.py)
    print("LLM Enrichment (routes/enrichment.py):")
    test("Get Enrichment Config", "/api/enrichment/config")
    test("Get Enrichment Status", "/api/enrichment/status", expected_keys=['total_transactions'])
    test("Get Enrichment Stats (alias)", "/api/enrichment/stats", expected_keys=['total_transactions'])
    test("Get Cache Stats", "/api/enrichment/cache/stats")
    test("Get Failed Enrichments", "/api/enrichment/failed")
    print()

    # Matching Routes (routes/matching.py + services/matching_service.py)
    print("Cross-Source Matching (routes/matching.py):")
    test("Get Matching Coverage", "/api/matching/coverage", expected_keys=['bank_transactions', 'stale_sources'])
    test("Get Matching Stats (alias)", "/api/matching/stats", expected_keys=['bank_transactions', 'stale_sources'])
    print()

    # Transaction Routes (routes/transactions.py + database/transactions.py)
    print("Transactions (routes/transactions.py):")
    test("Get All Transactions", "/api/transactions")
    test("Get Transaction Summary", "/api/categories/summary")
    print()

    # Category Routes (routes/categories_v1.py, routes/categories_v2.py + database/categories.py)
    print("Categories (routes/categories_v*.py):")
    test("Get Categories V1", "/api/categories")
    test("Get Categories V2", "/api/v2/categories")
    test("Get Subcategories V2", "/api/v2/subcategories")
    print()

    # Rules Routes (routes/rules.py + database/matching.py)
    print("Rules & Merchant Normalization (routes/rules.py):")
    test("Get Category Rules", "/api/rules/category")
    test("Get Merchant Normalizations", "/api/rules/merchant")
    print()

    # Settings Routes (routes/settings.py)
    print("Settings (routes/settings.py):")
    test("Get User Settings", "/api/settings/account-mappings")
    print()

    # Amazon Routes (routes/amazon.py + database/amazon.py)
    print("Amazon Integration (routes/amazon.py):")
    test("Get Amazon Orders", "/api/amazon/orders")
    test("Get Amazon Statistics", "/api/amazon/statistics")
    print()

    # Apple Routes (routes/apple.py + database/apple.py)
    print("Apple Integration (routes/apple.py):")
    test("Get Apple Transactions", "/api/apple")
    test("Get Apple Statistics", "/api/apple/statistics")
    print()

    # Direct Debit Routes (routes/direct_debit.py + database/direct_debit.py)
    print("Direct Debit (routes/direct_debit.py):")
    test("Get Direct Debit Mappings", "/api/direct-debit/mappings")
    print()

    # Huququllah Routes (routes/huququllah.py + database/huququllah.py)
    print("Huququllah (routes/huququllah.py):")
    test("Get Huququllah Calculations", "/api/huququllah/summary")
    print()

    # Print summary
    print()
    print("="*60)
    print(f"RESULTS: {PASSED} passed, {FAILED} failed")
    print("="*60)

    if FAILED > 0:
        sys.exit(1)
    else:
        print("✅ All tests passed!")
        sys.exit(0)

if __name__ == "__main__":
    main()
