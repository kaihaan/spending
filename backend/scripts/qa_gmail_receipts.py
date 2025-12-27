#!/usr/bin/env python3
"""QA script for Gmail receipts - checks data quality issues"""

import psycopg2
from psycopg2.extras import RealDictCursor
import json
import os
from collections import defaultdict

# Database connection
DB_CONFIG = {
    'host': 'localhost',
    'port': '5433',
    'user': 'spending_user',
    'password': 'aC0_Xbvulrw8ldPgU6sa',
    'database': 'spending_db'
}

def connect_db():
    return psycopg2.connect(**DB_CONFIG)

def check_merchant_names(cursor):
    """Check for fallback or badly executed pattern match merchant names"""
    print("\n" + "="*80)
    print("1. MERCHANT NAME QUALITY CHECK")
    print("="*80)

    # Generic/fallback merchant names that indicate parsing failure
    generic_names = [
        'Unknown', 'unknown', 'N/A', 'Email', 'Receipt',
        'Order', 'Invoice', 'Payment', 'Transaction',
        'Purchase', 'Statement', 'Bill'
    ]

    # Check for generic merchant names
    cursor.execute("""
        SELECT id, merchant_name, subject, sender_email, parse_method, parse_confidence
        FROM gmail_receipts
        WHERE merchant_name = ANY(%s)
        ORDER BY merchant_name, id
    """, (generic_names,))

    fallback_merchants = cursor.fetchall()

    print(f"\n❌ Found {len(fallback_merchants)} receipts with generic/fallback merchant names:")
    if fallback_merchants:
        for row in fallback_merchants[:20]:  # Show first 20
            print(f"  ID {row['id']}: '{row['merchant_name']}' from {row['sender_email']}")
            print(f"    Subject: {row['subject'][:80]}")
            print(f"    Parse: {row['parse_method']} (confidence: {row['parse_confidence']})")

    # Check for NULL merchant names
    cursor.execute("""
        SELECT COUNT(*) as count, parse_method, parse_confidence
        FROM gmail_receipts
        WHERE merchant_name IS NULL
        GROUP BY parse_method, parse_confidence
        ORDER BY count DESC
    """)

    null_merchants = cursor.fetchall()
    total_null = sum(row['count'] for row in null_merchants)

    print(f"\n❌ Found {total_null} receipts with NULL merchant names:")
    for row in null_merchants:
        print(f"  {row['count']} receipts via {row['parse_method']} (confidence: {row['parse_confidence']})")

    # Check for merchant names that are email addresses (likely parsing failure)
    cursor.execute("""
        SELECT id, merchant_name, subject, parse_method
        FROM gmail_receipts
        WHERE merchant_name LIKE '%@%'
        ORDER BY id
        LIMIT 20
    """)

    email_merchants = cursor.fetchall()

    if email_merchants:
        print(f"\n⚠️  Found {len(email_merchants)} receipts with email addresses as merchant names:")
        for row in email_merchants[:10]:
            print(f"  ID {row['id']}: {row['merchant_name']}")
            print(f"    Subject: {row['subject'][:80]}")

    return len(fallback_merchants) + total_null

def check_line_items(cursor):
    """Check for generic fallback text in line items"""
    print("\n" + "="*80)
    print("2. LINE ITEMS QUALITY CHECK")
    print("="*80)

    cursor.execute("""
        SELECT id, merchant_name, line_items, total_amount, subject, parse_method
        FROM gmail_receipts
        WHERE line_items IS NOT NULL
          AND jsonb_typeof(line_items) = 'array'
          AND line_items != 'null'::jsonb
        ORDER BY id DESC
        LIMIT 500
    """)

    receipts = cursor.fetchall()

    generic_patterns = [
        'item', 'product', 'purchase', 'order', 'service',
        'subscription', 'payment', 'charge', 'unknown',
        'price (year)', 'price (month)', 'total'
    ]

    generic_items = []
    for receipt in receipts:
        items = receipt['line_items']
        if items:
            for item in items:
                if isinstance(item, dict):
                    name = item.get('name', '').lower()
                    # Check if name is generic or too short
                    if (len(name) < 5 or
                        any(pattern in name for pattern in generic_patterns) and len(name) < 20):
                        generic_items.append({
                            'id': receipt['id'],
                            'merchant': receipt['merchant_name'],
                            'item_name': item.get('name'),
                            'subject': receipt['subject'],
                            'parse_method': receipt['parse_method']
                        })
                        break

    print(f"\n⚠️  Found {len(generic_items)} receipts with generic/short line item names:")
    for item in generic_items[:20]:
        print(f"  ID {item['id']} ({item['merchant']}): '{item['item_name']}'")
        print(f"    Parse: {item['parse_method']}")
        print(f"    Subject: {item['subject'][:80]}")

    # Check for missing line items when amount is present
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM gmail_receipts
        WHERE total_amount > 0
          AND (line_items IS NULL
               OR jsonb_typeof(line_items) != 'array'
               OR line_items = '[]'::jsonb)
    """)

    missing_items = cursor.fetchone()['count']
    print(f"\n❌ Found {missing_items} receipts with amounts but no line items")

    return len(generic_items)

def check_amounts(cursor):
    """Check for missing or incorrect amounts"""
    print("\n" + "="*80)
    print("3. AMOUNT VALIDATION CHECK")
    print("="*80)

    # Check for NULL amounts
    cursor.execute("""
        SELECT COUNT(*) as count, parse_method
        FROM gmail_receipts
        WHERE total_amount IS NULL
        GROUP BY parse_method
        ORDER BY count DESC
    """)

    null_amounts = cursor.fetchall()
    total_null = sum(row['count'] for row in null_amounts)

    print(f"\n❌ Found {total_null} receipts with NULL amounts:")
    for row in null_amounts:
        print(f"  {row['count']} via {row['parse_method']}")

    # Check for zero amounts
    cursor.execute("""
        SELECT COUNT(*) as count, merchant_name
        FROM gmail_receipts
        WHERE total_amount = 0
        GROUP BY merchant_name
        ORDER BY count DESC
        LIMIT 10
    """)

    zero_amounts = cursor.fetchall()
    total_zero = sum(row['count'] for row in zero_amounts)

    print(f"\n⚠️  Found {total_zero} receipts with zero amounts:")
    for row in zero_amounts:
        print(f"  {row['count']} from {row['merchant_name']}")

    # Check for mismatched amounts (line items don't sum to total)
    cursor.execute("""
        SELECT id, merchant_name, total_amount, line_items, subject
        FROM gmail_receipts
        WHERE line_items IS NOT NULL
          AND jsonb_typeof(line_items) = 'array'
          AND line_items::text != 'null'
          AND line_items::text != '[]'
        LIMIT 200
    """)

    receipts = cursor.fetchall()
    receipts = [r for r in receipts if r.get('line_items') and len(r.get('line_items', [])) > 0]
    mismatched = []

    for receipt in receipts:
        total = float(receipt['total_amount'] or 0)
        items = receipt['line_items']

        # Calculate sum of line items
        items_sum = 0
        for item in items:
            if isinstance(item, dict):
                # Try different field names
                price = item.get('price') or item.get('unit_price') or item.get('total_price')
                quantity = item.get('quantity', 1)

                if price:
                    try:
                        items_sum += float(price) * int(quantity)
                    except (ValueError, TypeError):
                        pass

        # Check if sums match (within 1% tolerance)
        if items_sum > 0 and abs(total - items_sum) > 0.01 * max(total, items_sum):
            mismatched.append({
                'id': receipt['id'],
                'merchant': receipt['merchant_name'],
                'total': total,
                'items_sum': items_sum,
                'diff': abs(total - items_sum)
            })

    print(f"\n⚠️  Found {len(mismatched)} receipts where line items don't sum to total:")
    for item in mismatched[:15]:
        print(f"  ID {item['id']} ({item['merchant']}): Total={item['total']:.2f}, Items Sum={item['items_sum']:.2f}, Diff={item['diff']:.2f}")

    return total_null

def check_duplicates(cursor):
    """Check for duplicate receipts (delivery/follow-up emails accepted as original)"""
    print("\n" + "="*80)
    print("4. DUPLICATE RECEIPTS CHECK")
    print("="*80)

    # Find receipts with same merchant, amount, and date (within 1 day)
    cursor.execute("""
        WITH grouped_receipts AS (
            SELECT
                merchant_name,
                total_amount,
                DATE(received_at) as receipt_day,
                array_agg(id ORDER BY received_at) as receipt_ids,
                array_agg(subject ORDER BY received_at) as subjects,
                array_agg(parse_method ORDER BY received_at) as parse_methods,
                COUNT(*) as count
            FROM gmail_receipts
            WHERE merchant_name IS NOT NULL
                AND total_amount IS NOT NULL
                AND total_amount > 0
            GROUP BY merchant_name, total_amount, DATE(received_at)
            HAVING COUNT(*) > 1
        )
        SELECT * FROM grouped_receipts
        ORDER BY count DESC, merchant_name
        LIMIT 30
    """)

    duplicates = cursor.fetchall()

    print(f"\n⚠️  Found {len(duplicates)} groups of potential duplicate receipts:")
    for dup in duplicates[:20]:
        print(f"\n  {dup['merchant_name']} - £{dup['total_amount']:.2f} on {dup['receipt_day']}")
        print(f"  {dup['count']} receipts: IDs {dup['receipt_ids']}")
        for i, (subj, method) in enumerate(zip(dup['subjects'], dup['parse_methods'])):
            print(f"    {i+1}. {subj[:70]} ({method})")

    # Check for similar subjects from same sender
    cursor.execute("""
        SELECT
            sender_email,
            COUNT(*) as count,
            array_agg(DISTINCT subject) as subjects,
            array_agg(id) as ids
        FROM gmail_receipts
        WHERE subject LIKE '%delivered%'
           OR subject LIKE '%dispatched%'
           OR subject LIKE '%shipped%'
           OR subject LIKE '%tracking%'
        GROUP BY sender_email
        HAVING COUNT(*) > 5
        ORDER BY count DESC
        LIMIT 10
    """)

    delivery_emails = cursor.fetchall()

    if delivery_emails:
        print(f"\n⚠️  Found senders with many delivery/dispatch emails (potential duplicates):")
        for row in delivery_emails:
            print(f"  {row['sender_email']}: {row['count']} emails")
            print(f"    Sample subjects: {row['subjects'][:3]}")

    return len(duplicates)

def check_brand_metadata(cursor):
    """Check for brand/manufacturer metadata in line items"""
    print("\n" + "="*80)
    print("5. BRAND METADATA CHECK")
    print("="*80)

    cursor.execute("""
        SELECT id, merchant_name, line_items, subject, parse_method
        FROM gmail_receipts
        WHERE line_items IS NOT NULL
          AND jsonb_typeof(line_items) = 'array'
          AND line_items::text != 'null'
          AND line_items::text != '[]'
        ORDER BY id DESC
        LIMIT 300
    """)

    receipts = cursor.fetchall()
    receipts = [r for r in receipts if r.get('line_items') and len(r.get('line_items', [])) > 0]

    # Categorize by merchant type and check for brand info
    brands_by_merchant = defaultdict(lambda: {'has_brand': 0, 'missing_brand': 0, 'examples': []})

    for receipt in receipts:
        merchant = receipt['merchant_name'] or 'Unknown'
        items = receipt['line_items']

        has_brand = False
        missing_brand = False

        for item in items:
            if isinstance(item, dict):
                # Check for brand/manufacturer fields
                if any(key in item for key in ['brand', 'manufacturer', 'seller', 'developer', 'publisher', 'restaurant']):
                    has_brand = True
                else:
                    # Check if brand info is in the name field for certain merchants
                    name = item.get('name', '')

                    # For Amazon, brand should be in separate field
                    if 'amazon' in merchant.lower():
                        missing_brand = True
                        if len(brands_by_merchant[merchant]['examples']) < 3:
                            brands_by_merchant[merchant]['examples'].append({
                                'id': receipt['id'],
                                'item': name[:80],
                                'parse_method': receipt['parse_method']
                            })

        if has_brand:
            brands_by_merchant[merchant]['has_brand'] += 1
        elif missing_brand:
            brands_by_merchant[merchant]['missing_brand'] += 1

    print(f"\n⚠️  Brand metadata analysis by merchant:")
    for merchant, stats in sorted(brands_by_merchant.items(), key=lambda x: x[1]['missing_brand'], reverse=True)[:15]:
        total = stats['has_brand'] + stats['missing_brand']
        pct = (stats['has_brand'] / total * 100) if total > 0 else 0
        print(f"\n  {merchant}:")
        print(f"    With brand: {stats['has_brand']}/{total} ({pct:.1f}%)")
        if stats['examples']:
            print(f"    Missing brand examples:")
            for ex in stats['examples']:
                print(f"      ID {ex['id']}: {ex['item']}")

    # Specific checks for known merchant types
    print(f"\n📊 Specific merchant type checks:")

    # Amazon - should have brand/manufacturer
    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN line_items::text LIKE '%"brand"%'
                        OR line_items::text LIKE '%"manufacturer"%'
                   THEN 1 ELSE 0 END) as with_brand
        FROM gmail_receipts
        WHERE merchant_name ILIKE '%amazon%'
          AND line_items IS NOT NULL
          AND jsonb_typeof(line_items) = 'array'
          AND line_items::text != 'null'
          AND line_items::text != '[]'
    """)

    amazon_stats = cursor.fetchone()
    if amazon_stats and amazon_stats['total'] > 0:
        pct = amazon_stats['with_brand'] / amazon_stats['total'] * 100
        print(f"  Amazon: {amazon_stats['with_brand']}/{amazon_stats['total']} have brand info ({pct:.1f}%)")

    # Deliveroo/UberEats - should have restaurant
    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN line_items::text LIKE '%"restaurant"%'
                   THEN 1 ELSE 0 END) as with_restaurant
        FROM gmail_receipts
        WHERE (merchant_name ILIKE '%deliveroo%' OR merchant_name ILIKE '%uber%')
          AND line_items IS NOT NULL
          AND jsonb_typeof(line_items) = 'array'
          AND line_items::text != 'null'
          AND line_items::text != '[]'
    """)

    delivery_stats = cursor.fetchone()
    if delivery_stats and delivery_stats['total'] > 0:
        pct = delivery_stats['with_restaurant'] / delivery_stats['total'] * 100
        print(f"  Deliveroo/Uber: {delivery_stats['with_restaurant']}/{delivery_stats['total']} have restaurant info ({pct:.1f}%)")

    # Apple - should have developer/publisher
    cursor.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN line_items::text LIKE '%"developer"%'
                        OR line_items::text LIKE '%"publisher"%'
                   THEN 1 ELSE 0 END) as with_developer
        FROM gmail_receipts
        WHERE merchant_name ILIKE '%apple%'
          AND line_items IS NOT NULL
          AND jsonb_typeof(line_items) = 'array'
          AND line_items::text != 'null'
          AND line_items::text != '[]'
    """)

    apple_stats = cursor.fetchone()
    if apple_stats and apple_stats['total'] > 0:
        pct = apple_stats['with_developer'] / apple_stats['total'] * 100
        print(f"  Apple: {apple_stats['with_developer']}/{apple_stats['total']} have developer info ({pct:.1f}%)")

    return sum(stats['missing_brand'] for stats in brands_by_merchant.values())

def generate_summary_report(cursor):
    """Generate overall summary statistics"""
    print("\n" + "="*80)
    print("SUMMARY REPORT")
    print("="*80)

    cursor.execute("SELECT COUNT(*) as total FROM gmail_receipts")
    total = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(DISTINCT merchant_name) as merchants FROM gmail_receipts WHERE merchant_name IS NOT NULL")
    merchants = cursor.fetchone()['merchants']

    cursor.execute("""
        SELECT parse_method, COUNT(*) as count, AVG(parse_confidence) as avg_confidence
        FROM gmail_receipts
        GROUP BY parse_method
        ORDER BY count DESC
    """)
    parse_methods = cursor.fetchall()

    print(f"\n📊 Total receipts: {total}")
    print(f"📊 Unique merchants: {merchants}")
    print(f"\n📊 Parse methods breakdown:")
    for method in parse_methods:
        pct = method['count'] / total * 100
        print(f"  {method['parse_method']}: {method['count']} ({pct:.1f}%) - avg confidence: {method['avg_confidence']:.1f}")

    # Quality score
    cursor.execute("""
        SELECT
            COUNT(*) FILTER (WHERE merchant_name IS NOT NULL AND merchant_name != 'Unknown') as good_merchant,
            COUNT(*) FILTER (WHERE total_amount IS NOT NULL AND total_amount > 0) as has_amount,
            COUNT(*) FILTER (WHERE line_items IS NOT NULL
                                AND jsonb_typeof(line_items) = 'array'
                                AND line_items::text != 'null'
                                AND line_items::text != '[]') as has_items
        FROM gmail_receipts
    """)

    quality = cursor.fetchone()

    print(f"\n📊 Quality metrics:")
    print(f"  Valid merchant names: {quality['good_merchant']}/{total} ({quality['good_merchant']/total*100:.1f}%)")
    print(f"  Has amount: {quality['has_amount']}/{total} ({quality['has_amount']/total*100:.1f}%)")
    print(f"  Has line items: {quality['has_items']}/{total} ({quality['has_items']/total*100:.1f}%)")

def main():
    print("\n" + "="*80)
    print("GMAIL RECEIPTS QA ANALYSIS")
    print("="*80)

    conn = connect_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Run all checks
        issue_counts = {}
        issue_counts['merchant'] = check_merchant_names(cursor)
        issue_counts['items'] = check_line_items(cursor)
        issue_counts['amounts'] = check_amounts(cursor)
        issue_counts['duplicates'] = check_duplicates(cursor)
        issue_counts['brands'] = check_brand_metadata(cursor)

        # Summary
        generate_summary_report(cursor)

        print("\n" + "="*80)
        print("ISSUES SUMMARY")
        print("="*80)
        print(f"  Merchant name issues: {issue_counts['merchant']}")
        print(f"  Line item quality issues: {issue_counts['items']}")
        print(f"  Amount issues: {issue_counts['amounts']}")
        print(f"  Potential duplicates: {issue_counts['duplicates']}")
        print(f"  Missing brand metadata: {issue_counts['brands']}")
        print("="*80)

    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()
