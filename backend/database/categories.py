"""
Categories & Rules - Database Operations

Handles all database operations for transaction categorization, category rules,
and category management.

Modules:
- Category promotion (promote_category, demote_category, etc.)
- Normalized categories & subcategories (get_all_categories, get_subcategories, etc.)
- Category rules testing and statistics (test_category_rule, get_rule_statistics, etc.)
"""

from .base import get_db
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


# ============================================================================
# CATEGORY PROMOTION FUNCTIONS
# ============================================================================

def get_custom_categories(category_type=None, user_id=1):
    """Get custom categories, optionally filtered by type ('promoted' or 'hidden')."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if category_type:
                cursor.execute('''
                    SELECT id, name, category_type, display_order, created_at, updated_at
                    FROM custom_categories
                    WHERE user_id = %s AND category_type = %s
                    ORDER BY display_order ASC, name ASC
                ''', (user_id, category_type))
            else:
                cursor.execute('''
                    SELECT id, name, category_type, display_order, created_at, updated_at
                    FROM custom_categories
                    WHERE user_id = %s
                    ORDER BY category_type ASC, display_order ASC, name ASC
                ''', (user_id,))
            return cursor.fetchall()


def get_category_spending_summary(date_from=None, date_to=None):
    """Get all categories with spending totals from transactions."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Build the query with optional date filters
            query = '''
                SELECT
                    COALESCE(transaction_category, 'Uncategorized') as name,
                    SUM(amount) as total_spend,
                    COUNT(*) as transaction_count
                FROM truelayer_transactions
                WHERE transaction_type = 'DEBIT'
            '''
            params = []

            if date_from:
                query += ' AND timestamp >= %s'
                params.append(date_from)
            if date_to:
                query += ' AND timestamp <= %s'
                params.append(date_to)

            query += '''
                GROUP BY transaction_category
                ORDER BY total_spend DESC
            '''

            cursor.execute(query, params)
            categories = cursor.fetchall()

            # Check which are custom categories
            custom_cats = get_custom_categories(category_type='promoted')
            custom_names = {c['name'] for c in custom_cats}

            for cat in categories:
                cat['is_custom'] = cat['name'] in custom_names
                cat['total_spend'] = float(cat['total_spend']) if cat['total_spend'] else 0.0

            return categories


def get_subcategory_spending(category_name, date_from=None, date_to=None):
    """Get subcategories within a category with spending totals."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = '''
                SELECT
                    COALESCE(metadata->'enrichment'->>'subcategory', 'Unknown') as name,
                    SUM(amount) as total_spend,
                    COUNT(*) as transaction_count
                FROM truelayer_transactions
                WHERE transaction_type = 'DEBIT'
                  AND transaction_category = %s
            '''
            params = [category_name]

            if date_from:
                query += ' AND timestamp >= %s'
                params.append(date_from)
            if date_to:
                query += ' AND timestamp <= %s'
                params.append(date_to)

            query += '''
                GROUP BY metadata->'enrichment'->>'subcategory'
                ORDER BY total_spend DESC
            '''

            cursor.execute(query, params)
            subcategories = cursor.fetchall()

            # Check which subcategories are already mapped
            cursor.execute('''
                SELECT subcategory_name
                FROM subcategory_mappings
            ''')
            mapped = {row['subcategory_name'] for row in cursor.fetchall()}

            for sub in subcategories:
                sub['already_mapped'] = sub['name'] in mapped
                sub['total_spend'] = float(sub['total_spend']) if sub['total_spend'] else 0.0

            return subcategories


def create_promoted_category(name, subcategories, user_id=1):
    """
    Create a promoted category from subcategories and update all matching transactions.

    Args:
        name: Name of the new category
        subcategories: List of dicts with 'name' and 'original_category' keys
        user_id: User ID (default 1)

    Returns:
        Dict with category_id and transactions_updated count
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                # Insert the custom category
                cursor.execute('''
                    INSERT INTO custom_categories (user_id, name, category_type)
                    VALUES (%s, %s, 'promoted')
                    RETURNING id
                ''', (user_id, name))
                category_id = cursor.fetchone()['id']

                # Insert subcategory mappings
                subcategory_names = []
                for sub in subcategories:
                    cursor.execute('''
                        INSERT INTO subcategory_mappings (custom_category_id, subcategory_name, original_category)
                        VALUES (%s, %s, %s)
                    ''', (category_id, sub['name'], sub.get('original_category')))
                    subcategory_names.append(sub['name'])

                # Update all transactions with matching subcategories
                if subcategory_names:
                    cursor.execute('''
                        UPDATE truelayer_transactions
                        SET
                            transaction_category = %s,
                            metadata = jsonb_set(
                                COALESCE(metadata, '{}'::jsonb),
                                '{enrichment,primary_category}',
                                %s::jsonb
                            )
                        WHERE metadata->'enrichment'->>'subcategory' = ANY(%s)
                        RETURNING id
                    ''', (name, json.dumps(name), subcategory_names))
                    transactions_updated = cursor.rowcount
                else:
                    transactions_updated = 0

                conn.commit()

                # Invalidate transaction cache
                cache_manager.cache_invalidate_transactions()

                return {
                    'category_id': category_id,
                    'transactions_updated': transactions_updated
                }

            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                raise ValueError(f"Category '{name}' already exists")
            except Exception as e:
                conn.rollback()
                raise e


def hide_category(name, user_id=1):
    """
    Hide a category and reset its transactions for re-enrichment.

    Args:
        name: Name of the category to hide
        user_id: User ID (default 1)

    Returns:
        Dict with category_id and transactions_reset count
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                # Insert/update the hidden category
                cursor.execute('''
                    INSERT INTO custom_categories (user_id, name, category_type)
                    VALUES (%s, %s, 'hidden')
                    ON CONFLICT (user_id, name) DO UPDATE SET
                        category_type = 'hidden',
                        updated_at = NOW()
                    RETURNING id
                ''', (user_id, name))
                category_id = cursor.fetchone()['id']

                # Reset all transactions with this category for re-enrichment
                cursor.execute('''
                    UPDATE truelayer_transactions
                    SET
                        transaction_category = NULL,
                        metadata = metadata - 'enrichment'
                    WHERE transaction_category = %s
                    RETURNING id
                ''', (name,))
                transactions_reset = cursor.rowcount

                conn.commit()

                # Invalidate transaction cache
                cache_manager.cache_invalidate_transactions()

                return {
                    'category_id': category_id,
                    'transactions_reset': transactions_reset
                }

            except Exception as e:
                conn.rollback()
                raise e


def unhide_category(name, user_id=1):
    """
    Remove a category from the hidden list.

    Args:
        name: Name of the category to unhide
        user_id: User ID (default 1)

    Returns:
        True if successfully unhidden, False if not found
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                DELETE FROM custom_categories
                WHERE user_id = %s AND name = %s AND category_type = 'hidden'
            ''', (user_id, name))
            conn.commit()
            return cursor.rowcount > 0


def get_mapped_subcategories(category_name=None):
    """Get all subcategory mappings, optionally filtered by promoted category name."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if category_name:
                cursor.execute('''
                    SELECT sm.id, sm.subcategory_name, sm.original_category, cc.name as promoted_category
                    FROM subcategory_mappings sm
                    JOIN custom_categories cc ON sm.custom_category_id = cc.id
                    WHERE cc.name = %s AND cc.category_type = 'promoted'
                ''', (category_name,))
            else:
                cursor.execute('''
                    SELECT sm.id, sm.subcategory_name, sm.original_category, cc.name as promoted_category
                    FROM subcategory_mappings sm
                    JOIN custom_categories cc ON sm.custom_category_id = cc.id
                    WHERE cc.category_type = 'promoted'
                ''')
            return cursor.fetchall()


# ============================================================================


# ============================================================================
# RULES TESTING AND STATISTICS
# ============================================================================

def test_rule_pattern(pattern: str, pattern_type: str, limit: int = 10) -> dict:
    """
    Test a pattern against all transactions to see what would match.

    Args:
        pattern: The pattern to test
        pattern_type: Type of pattern (contains, starts_with, exact, regex)
        limit: Maximum number of sample transactions to return

    Returns:
        Dict with: match_count, sample_transactions
    """
    import re

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all transactions
            cursor.execute('''
                SELECT id, description, amount, timestamp as date
                FROM truelayer_transactions
                ORDER BY timestamp DESC
            ''')
            transactions = cursor.fetchall()

            matches = []
            pattern_upper = pattern.upper()

            for txn in transactions:
                description = txn['description'].upper() if txn['description'] else ''

                matched = False
                if pattern_type == 'contains':
                    matched = pattern_upper in description
                elif pattern_type == 'starts_with':
                    matched = description.startswith(pattern_upper)
                elif pattern_type == 'exact':
                    matched = description == pattern_upper
                elif pattern_type == 'regex':
                    try:
                        matched = bool(re.search(pattern, txn['description'] or '', re.IGNORECASE))
                    except re.error:
                        matched = False

                if matched:
                    matches.append({
                        'id': txn['id'],
                        'description': txn['description'],
                        'amount': float(txn['amount']) if txn['amount'] else 0,
                        'date': txn['date'].isoformat() if txn['date'] else None
                    })

            return {
                'match_count': len(matches),
                'sample_transactions': matches[:limit]
            }


def get_rules_statistics() -> dict:
    """
    Get comprehensive rule usage statistics and coverage metrics.

    Returns:
        Dict with:
            - category_rules_count: Total category rules
            - merchant_rules_count: Total merchant normalizations
            - total_usage: Sum of all rule usage counts
            - coverage_percentage: Percent of transactions with rule-based enrichment
            - rules_by_category: Dict mapping category to rule count
            - rules_by_source: Dict mapping source to rule count
            - top_used_rules: List of top 10 most used rules
            - unused_rules: List of rules with usage_count = 0
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Count category rules
            cursor.execute('SELECT COUNT(*) as count FROM category_rules WHERE is_active = true')
            category_rules_count = cursor.fetchone()['count']

            # Count merchant normalizations
            cursor.execute('SELECT COUNT(*) as count FROM merchant_normalizations')
            merchant_rules_count = cursor.fetchone()['count']

            # Get total usage
            cursor.execute('SELECT COALESCE(SUM(usage_count), 0) as total FROM category_rules')
            category_usage = cursor.fetchone()['total']
            cursor.execute('SELECT COALESCE(SUM(usage_count), 0) as total FROM merchant_normalizations')
            merchant_usage = cursor.fetchone()['total']
            total_usage = category_usage + merchant_usage

            # Get coverage: count transactions with rule-based enrichment
            cursor.execute('''
                SELECT COUNT(*) as total FROM truelayer_transactions
            ''')
            total_transactions = cursor.fetchone()['total']

            cursor.execute('''
                SELECT COUNT(*) as covered FROM truelayer_transactions
                WHERE metadata->'enrichment'->>'enrichment_source' = 'rule'
            ''')
            covered_transactions = cursor.fetchone()['covered']

            coverage_percentage = (covered_transactions / total_transactions * 100) if total_transactions > 0 else 0

            # Rules by category
            cursor.execute('''
                SELECT category, COUNT(*) as count
                FROM category_rules
                WHERE is_active = true
                GROUP BY category
                ORDER BY count DESC
            ''')
            rules_by_category = {row['category']: row['count'] for row in cursor.fetchall()}

            # Rules by source (combine both tables)
            cursor.execute('''
                SELECT source, COUNT(*) as count
                FROM (
                    SELECT source FROM category_rules WHERE is_active = true
                    UNION ALL
                    SELECT source FROM merchant_normalizations
                ) combined
                GROUP BY source
                ORDER BY count DESC
            ''')
            rules_by_source = {row['source']: row['count'] for row in cursor.fetchall()}

            # Top used rules (combine category rules and merchant normalizations)
            cursor.execute('''
                SELECT name, usage_count, type FROM (
                    SELECT rule_name as name, usage_count, 'category' as type
                    FROM category_rules
                    WHERE is_active = true
                    UNION ALL
                    SELECT pattern as name, usage_count, 'merchant' as type
                    FROM merchant_normalizations
                ) combined
                ORDER BY usage_count DESC
                LIMIT 10
            ''')
            top_used_rules = [
                {'name': row['name'], 'count': row['usage_count'], 'type': row['type']}
                for row in cursor.fetchall()
            ]

            # Unused rules
            cursor.execute('''
                SELECT name, type FROM (
                    SELECT rule_name as name, 'category' as type
                    FROM category_rules
                    WHERE is_active = true AND usage_count = 0
                    UNION ALL
                    SELECT pattern as name, 'merchant' as type
                    FROM merchant_normalizations
                    WHERE usage_count = 0
                ) combined
            ''')
            unused_rules = [
                {'name': row['name'], 'type': row['type']}
                for row in cursor.fetchall()
            ]

            return {
                'category_rules_count': category_rules_count,
                'merchant_rules_count': merchant_rules_count,
                'total_usage': total_usage,
                'total_transactions': total_transactions,
                'covered_transactions': covered_transactions,
                'coverage_percentage': round(coverage_percentage, 1),
                'rules_by_category': rules_by_category,
                'rules_by_source': rules_by_source,
                'top_used_rules': top_used_rules,
                'unused_rules': unused_rules,
                'unused_rules_count': len(unused_rules)
            }


def test_all_rules() -> dict:
    """
    Evaluate all rules against all transactions and return a coverage report.

    Returns detailed breakdown by category, identifies conflicts, and unused rules.
    """
    import re
    from collections import defaultdict

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all active category rules
            cursor.execute('''
                SELECT id, rule_name, description_pattern, pattern_type, category, subcategory
                FROM category_rules
                WHERE is_active = true
                ORDER BY priority DESC
            ''')
            category_rules = cursor.fetchall()

            # Get all merchant normalizations
            cursor.execute('''
                SELECT id, pattern, pattern_type, normalized_name, default_category
                FROM merchant_normalizations
                ORDER BY priority DESC
            ''')
            merchant_rules = cursor.fetchall()

            # Get all transactions
            cursor.execute('''
                SELECT id, description
                FROM truelayer_transactions
            ''')
            transactions = cursor.fetchall()

            # Track matches
            rule_matches = defaultdict(list)  # rule_id -> [txn_ids]
            txn_matches = defaultdict(list)   # txn_id -> [rule_ids]
            category_coverage = defaultdict(int)  # category -> count

            for txn in transactions:
                desc = txn['description'].upper() if txn['description'] else ''
                matched_any = False

                # Check category rules
                for rule in category_rules:
                    pattern = rule['description_pattern'].upper()
                    pattern_type = rule['pattern_type']

                    matched = False
                    if pattern_type == 'contains':
                        matched = pattern in desc
                    elif pattern_type == 'starts_with':
                        matched = desc.startswith(pattern)
                    elif pattern_type == 'exact':
                        matched = desc == pattern
                    elif pattern_type == 'regex':
                        try:
                            matched = bool(re.search(rule['description_pattern'], txn['description'] or '', re.IGNORECASE))
                        except re.error:
                            pass

                    if matched:
                        rule_key = f"cat_{rule['id']}"
                        rule_matches[rule_key].append(txn['id'])
                        txn_matches[txn['id']].append(rule_key)
                        category_coverage[rule['category']] += 1
                        matched_any = True

                # Check merchant rules
                for rule in merchant_rules:
                    pattern = rule['pattern'].upper()
                    pattern_type = rule['pattern_type']

                    matched = False
                    if pattern_type == 'contains':
                        matched = pattern in desc
                    elif pattern_type == 'starts_with':
                        matched = desc.startswith(pattern)
                    elif pattern_type == 'exact':
                        matched = desc == pattern
                    elif pattern_type == 'regex':
                        try:
                            matched = bool(re.search(rule['pattern'], txn['description'] or '', re.IGNORECASE))
                        except re.error:
                            pass

                    if matched:
                        rule_key = f"mer_{rule['id']}"
                        rule_matches[rule_key].append(txn['id'])
                        txn_matches[txn['id']].append(rule_key)
                        if rule['default_category']:
                            category_coverage[rule['default_category']] += 1
                        matched_any = True

            # Calculate statistics
            total_transactions = len(transactions)
            covered_transactions = len([t for t in txn_matches if txn_matches[t]])
            coverage_percentage = (covered_transactions / total_transactions * 100) if total_transactions > 0 else 0

            # Find unused rules
            unused_category_rules = [r for r in category_rules if f"cat_{r['id']}" not in rule_matches]
            unused_merchant_rules = [r for r in merchant_rules if f"mer_{r['id']}" not in rule_matches]

            # Find potential conflicts (transactions matching multiple rules)
            conflicts = []
            for txn_id, rules in txn_matches.items():
                if len(rules) > 1:
                    conflicts.append({
                        'transaction_id': txn_id,
                        'matching_rules': rules
                    })

            return {
                'total_transactions': total_transactions,
                'covered_transactions': covered_transactions,
                'coverage_percentage': round(coverage_percentage, 1),
                'category_coverage': dict(category_coverage),
                'unused_category_rules': [
                    {'id': r['id'], 'name': r['rule_name'], 'pattern': r['description_pattern']}
                    for r in unused_category_rules
                ],
                'unused_merchant_rules': [
                    {'id': r['id'], 'pattern': r['pattern'], 'name': r['normalized_name']}
                    for r in unused_merchant_rules
                ],
                'potential_conflicts_count': len(conflicts),
                'sample_conflicts': conflicts[:10]  # Limit to 10 examples
            }


def apply_all_rules_to_transactions() -> dict:
    """
    Re-enrich all transactions using current category rules and merchant normalizations.

    This applies the consistency engine to all transactions, updating enrichment data
    for transactions that match rules.

    Returns:
        Dict with: updated_count, rule_hits (dict of rule_name -> count)
    """
    from mcp.consistency_engine import apply_rules_to_transaction

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all rules
            cursor.execute('''
                SELECT * FROM category_rules
                WHERE is_active = true
                ORDER BY priority DESC
            ''')
            category_rules = cursor.fetchall()

            cursor.execute('''
                SELECT * FROM merchant_normalizations
                ORDER BY priority DESC
            ''')
            merchant_normalizations = cursor.fetchall()

            # Get all transactions
            cursor.execute('''
                SELECT id, description, amount, transaction_type, timestamp, metadata
                FROM truelayer_transactions
            ''')
            transactions = cursor.fetchall()

            updated_count = 0
            rule_hits = {}

            for txn in transactions:
                txn_dict = dict(txn)
                result = apply_rules_to_transaction(txn_dict, category_rules, merchant_normalizations)

                if result and result.get('primary_category'):
                    # Update the transaction with rule-based enrichment
                    metadata = txn['metadata'] or {}
                    metadata['enrichment'] = result

                    cursor.execute('''
                        UPDATE truelayer_transactions
                        SET metadata = %s
                        WHERE id = %s
                    ''', (json.dumps(metadata), txn['id']))

                    updated_count += 1

                    # Track rule hits
                    matched_rule = result.get('matched_rule', 'unknown')
                    rule_hits[matched_rule] = rule_hits.get(matched_rule, 0) + 1

            conn.commit()

            return {
                'updated_count': updated_count,
                'total_transactions': len(transactions),
                'rule_hits': rule_hits
            }


# ============================================================================


# ============================================================================
# NORMALIZED CATEGORIES & SUBCATEGORIES FUNCTIONS
# ============================================================================

def get_normalized_categories(active_only: bool = False, include_counts: bool = False):
    """Get all normalized categories.

    Args:
        active_only: If True, only return categories where is_active=TRUE
        include_counts: If True, include transaction and subcategory counts

    Returns:
        List of category dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if include_counts:
                cursor.execute('''
                    SELECT
                        nc.*,
                        COALESCE(txn_counts.transaction_count, 0) as transaction_count,
                        COALESCE(sub_counts.subcategory_count, 0) as subcategory_count
                    FROM normalized_categories nc
                    LEFT JOIN (
                        SELECT category_id, COUNT(*) as transaction_count
                        FROM truelayer_transactions
                        WHERE category_id IS NOT NULL
                        GROUP BY category_id
                    ) txn_counts ON nc.id = txn_counts.category_id
                    LEFT JOIN (
                        SELECT category_id, COUNT(*) as subcategory_count
                        FROM normalized_subcategories
                        GROUP BY category_id
                    ) sub_counts ON nc.id = sub_counts.category_id
                    WHERE (%s = FALSE OR nc.is_active = TRUE)
                    ORDER BY nc.display_order, nc.name
                ''', (active_only,))
            else:
                cursor.execute('''
                    SELECT * FROM normalized_categories
                    WHERE (%s = FALSE OR is_active = TRUE)
                    ORDER BY display_order, name
                ''', (active_only,))
            return cursor.fetchall()


def get_normalized_category_by_id(category_id: int):
    """Get a single normalized category by ID with subcategories."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get category
            cursor.execute('''
                SELECT
                    nc.*,
                    COALESCE(txn_counts.transaction_count, 0) as transaction_count
                FROM normalized_categories nc
                LEFT JOIN (
                    SELECT category_id, COUNT(*) as transaction_count
                    FROM truelayer_transactions
                    WHERE category_id IS NOT NULL
                    GROUP BY category_id
                ) txn_counts ON nc.id = txn_counts.category_id
                WHERE nc.id = %s
            ''', (category_id,))
            category = cursor.fetchone()

            if not category:
                return None

            # Get subcategories
            cursor.execute('''
                SELECT
                    ns.*,
                    COALESCE(txn_counts.transaction_count, 0) as transaction_count
                FROM normalized_subcategories ns
                LEFT JOIN (
                    SELECT subcategory_id, COUNT(*) as transaction_count
                    FROM truelayer_transactions
                    WHERE subcategory_id IS NOT NULL
                    GROUP BY subcategory_id
                ) txn_counts ON ns.id = txn_counts.subcategory_id
                WHERE ns.category_id = %s
                ORDER BY ns.display_order, ns.name
            ''', (category_id,))
            category['subcategories'] = cursor.fetchall()

            return category


def get_normalized_category_by_name(name: str):
    """Get a normalized category by name."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT * FROM normalized_categories WHERE name = %s
            ''', (name,))
            return cursor.fetchone()


def create_normalized_category(name: str, description: str = None, is_essential: bool = False, color: str = None):
    """Create a new normalized category.

    Returns:
        The created category dict, or None if name already exists
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                # Get next display order
                cursor.execute('SELECT COALESCE(MAX(display_order), 0) + 1 FROM normalized_categories')
                next_order = cursor.fetchone()['coalesce']

                cursor.execute('''
                    INSERT INTO normalized_categories (name, description, is_system, is_essential, display_order, color)
                    VALUES (%s, %s, FALSE, %s, %s, %s)
                    RETURNING *
                ''', (name, description, is_essential, next_order, color))
                conn.commit()
                return cursor.fetchone()
            except Exception as e:
                conn.rollback()
                if 'unique constraint' in str(e).lower():
                    return None
                raise


def update_normalized_category(category_id: int, name: str = None, description: str = None,
                               is_active: bool = None, is_essential: bool = None, color: str = None):
    """Update a normalized category and cascade changes if name changed.

    Returns:
        Dict with category and update counts, or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get current category
            cursor.execute('SELECT * FROM normalized_categories WHERE id = %s', (category_id,))
            current = cursor.fetchone()
            if not current:
                return None

            old_name = current['name']
            new_name = name if name is not None else old_name

            # Build update query dynamically
            updates = []
            params = []

            if name is not None:
                updates.append('name = %s')
                params.append(name)
            if description is not None:
                updates.append('description = %s')
                params.append(description)
            if is_active is not None:
                updates.append('is_active = %s')
                params.append(is_active)
            if is_essential is not None:
                updates.append('is_essential = %s')
                params.append(is_essential)
            if color is not None:
                updates.append('color = %s')
                params.append(color)

            if not updates:
                return {'category': current, 'transactions_updated': 0, 'rules_updated': 0}

            params.append(category_id)
            cursor.execute(f'''
                UPDATE normalized_categories
                SET {', '.join(updates)}
                WHERE id = %s
                RETURNING *
            ''', params)
            updated_category = cursor.fetchone()

            transactions_updated = 0
            rules_updated = 0

            # If name changed, cascade updates
            if name is not None and name != old_name:
                # Update transaction_category VARCHAR (for backwards compatibility)
                cursor.execute('''
                    UPDATE truelayer_transactions
                    SET transaction_category = %s
                    WHERE category_id = %s
                ''', (new_name, category_id))
                transactions_updated = cursor.rowcount

                # Update JSONB metadata
                cursor.execute('''
                    UPDATE truelayer_transactions
                    SET metadata = jsonb_set(
                        metadata,
                        '{enrichment,primary_category}',
                        %s::jsonb
                    )
                    WHERE category_id = %s
                      AND metadata->'enrichment' IS NOT NULL
                ''', (json.dumps(new_name), category_id))

                # Update category_rules VARCHAR
                cursor.execute('''
                    UPDATE category_rules
                    SET category = %s
                    WHERE category_id = %s
                ''', (new_name, category_id))
                rules_updated = cursor.rowcount

            conn.commit()

            # Invalidate cache
            try:
                from cache_manager import cache_invalidate_transactions
                cache_invalidate_transactions()
            except ImportError:
                pass

            return {
                'category': updated_category,
                'transactions_updated': transactions_updated,
                'rules_updated': rules_updated,
                'old_name': old_name,
                'new_name': new_name
            }


def delete_normalized_category(category_id: int, reassign_to_category_id: int = None):
    """Delete a normalized category.

    System categories cannot be deleted. Transactions are reassigned to 'Other' or specified category.

    Returns:
        Dict with deletion result, or None if not found or is system category
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check if category exists and is not system
            cursor.execute('SELECT * FROM normalized_categories WHERE id = %s', (category_id,))
            category = cursor.fetchone()

            if not category:
                return None
            if category['is_system']:
                return {'error': 'Cannot delete system category'}

            # Find reassignment target (default to 'Other')
            if reassign_to_category_id:
                target_id = reassign_to_category_id
            else:
                cursor.execute("SELECT id FROM normalized_categories WHERE name = 'Other'")
                other = cursor.fetchone()
                target_id = other['id'] if other else None

            # Reassign transactions
            transactions_reassigned = 0
            if target_id:
                cursor.execute('''
                    UPDATE truelayer_transactions
                    SET category_id = %s, subcategory_id = NULL
                    WHERE category_id = %s
                ''', (target_id, category_id))
                transactions_reassigned = cursor.rowcount

            # Delete the category (subcategories cascade)
            cursor.execute('DELETE FROM normalized_categories WHERE id = %s', (category_id,))

            conn.commit()

            return {
                'deleted_category': category['name'],
                'transactions_reassigned': transactions_reassigned,
                'reassigned_to_category_id': target_id
            }


def get_normalized_subcategories(category_id: int = None, include_counts: bool = False):
    """Get normalized subcategories, optionally filtered by category.

    Args:
        category_id: If provided, only return subcategories for this category
        include_counts: If True, include transaction counts
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if include_counts:
                if category_id:
                    cursor.execute('''
                        SELECT
                            ns.*,
                            nc.name as category_name,
                            COALESCE(txn_counts.transaction_count, 0) as transaction_count
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        LEFT JOIN (
                            SELECT subcategory_id, COUNT(*) as transaction_count
                            FROM truelayer_transactions
                            WHERE subcategory_id IS NOT NULL
                            GROUP BY subcategory_id
                        ) txn_counts ON ns.id = txn_counts.subcategory_id
                        WHERE ns.category_id = %s
                        ORDER BY ns.display_order, ns.name
                    ''', (category_id,))
                else:
                    cursor.execute('''
                        SELECT
                            ns.*,
                            nc.name as category_name,
                            COALESCE(txn_counts.transaction_count, 0) as transaction_count
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        LEFT JOIN (
                            SELECT subcategory_id, COUNT(*) as transaction_count
                            FROM truelayer_transactions
                            WHERE subcategory_id IS NOT NULL
                            GROUP BY subcategory_id
                        ) txn_counts ON ns.id = txn_counts.subcategory_id
                        ORDER BY nc.name, ns.display_order, ns.name
                    ''')
            else:
                if category_id:
                    cursor.execute('''
                        SELECT ns.*, nc.name as category_name
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        WHERE ns.category_id = %s
                        ORDER BY ns.display_order, ns.name
                    ''', (category_id,))
                else:
                    cursor.execute('''
                        SELECT ns.*, nc.name as category_name
                        FROM normalized_subcategories ns
                        JOIN normalized_categories nc ON ns.category_id = nc.id
                        ORDER BY nc.name, ns.display_order, ns.name
                    ''')
            return cursor.fetchall()


def get_normalized_subcategory_by_id(subcategory_id: int):
    """Get a single normalized subcategory by ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT
                    ns.*,
                    nc.name as category_name,
                    COALESCE(txn_counts.transaction_count, 0) as transaction_count
                FROM normalized_subcategories ns
                JOIN normalized_categories nc ON ns.category_id = nc.id
                LEFT JOIN (
                    SELECT subcategory_id, COUNT(*) as transaction_count
                    FROM truelayer_transactions
                    WHERE subcategory_id IS NOT NULL
                    GROUP BY subcategory_id
                ) txn_counts ON ns.id = txn_counts.subcategory_id
                WHERE ns.id = %s
            ''', (subcategory_id,))
            return cursor.fetchone()


def create_normalized_subcategory(category_id: int, name: str, description: str = None):
    """Create a new normalized subcategory.

    Returns:
        The created subcategory dict, or None if already exists
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            try:
                # Get next display order for this category
                cursor.execute('''
                    SELECT COALESCE(MAX(display_order), 0) + 1
                    FROM normalized_subcategories WHERE category_id = %s
                ''', (category_id,))
                next_order = cursor.fetchone()['coalesce']

                cursor.execute('''
                    INSERT INTO normalized_subcategories (category_id, name, description, display_order)
                    VALUES (%s, %s, %s, %s)
                    RETURNING *
                ''', (category_id, name, description, next_order))
                conn.commit()

                subcategory = cursor.fetchone()

                # Get category name
                cursor.execute('SELECT name FROM normalized_categories WHERE id = %s', (category_id,))
                cat = cursor.fetchone()
                subcategory['category_name'] = cat['name'] if cat else None

                return subcategory
            except Exception as e:
                conn.rollback()
                if 'unique constraint' in str(e).lower():
                    return None
                raise


def update_normalized_subcategory(subcategory_id: int, name: str = None, description: str = None,
                                   is_active: bool = None, category_id: int = None):
    """Update a normalized subcategory and cascade changes if name changed.

    Returns:
        Dict with subcategory and update counts, or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get current subcategory
            cursor.execute('''
                SELECT ns.*, nc.name as category_name
                FROM normalized_subcategories ns
                JOIN normalized_categories nc ON ns.category_id = nc.id
                WHERE ns.id = %s
            ''', (subcategory_id,))
            current = cursor.fetchone()
            if not current:
                return None

            old_name = current['name']
            old_category_id = current['category_id']
            new_name = name if name is not None else old_name

            # Build update query dynamically
            updates = []
            params = []

            if name is not None:
                updates.append('name = %s')
                params.append(name)
            if description is not None:
                updates.append('description = %s')
                params.append(description)
            if is_active is not None:
                updates.append('is_active = %s')
                params.append(is_active)
            if category_id is not None:
                updates.append('category_id = %s')
                params.append(category_id)

            if not updates:
                return {'subcategory': current, 'transactions_updated': 0}

            params.append(subcategory_id)
            cursor.execute(f'''
                UPDATE normalized_subcategories
                SET {', '.join(updates)}
                WHERE id = %s
                RETURNING *
            ''', params)
            updated_subcategory = cursor.fetchone()

            # Get new category name
            cursor.execute('SELECT name FROM normalized_categories WHERE id = %s',
                          (updated_subcategory['category_id'],))
            cat = cursor.fetchone()
            updated_subcategory['category_name'] = cat['name'] if cat else None

            transactions_updated = 0

            # If name changed, cascade updates to JSONB metadata
            if name is not None and name != old_name:
                cursor.execute('''
                    UPDATE truelayer_transactions
                    SET metadata = jsonb_set(
                        metadata,
                        '{enrichment,subcategory}',
                        %s::jsonb
                    )
                    WHERE subcategory_id = %s
                      AND metadata->'enrichment' IS NOT NULL
                ''', (json.dumps(new_name), subcategory_id))
                transactions_updated = cursor.rowcount

            conn.commit()

            # Invalidate cache
            try:
                from cache_manager import cache_invalidate_transactions
                cache_invalidate_transactions()
            except ImportError:
                pass

            return {
                'subcategory': updated_subcategory,
                'transactions_updated': transactions_updated,
                'old_name': old_name,
                'new_name': new_name
            }


def delete_normalized_subcategory(subcategory_id: int):
    """Delete a normalized subcategory.

    Transactions will have their subcategory_id set to NULL.

    Returns:
        Dict with deletion result, or None if not found
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get subcategory
            cursor.execute('''
                SELECT ns.*, nc.name as category_name
                FROM normalized_subcategories ns
                JOIN normalized_categories nc ON ns.category_id = nc.id
                WHERE ns.id = %s
            ''', (subcategory_id,))
            subcategory = cursor.fetchone()

            if not subcategory:
                return None

            # Clear subcategory_id from transactions
            cursor.execute('''
                UPDATE truelayer_transactions
                SET subcategory_id = NULL
                WHERE subcategory_id = %s
            ''', (subcategory_id,))
            transactions_cleared = cursor.rowcount

            # Delete the subcategory
            cursor.execute('DELETE FROM normalized_subcategories WHERE id = %s', (subcategory_id,))

            conn.commit()

            return {
                'deleted_subcategory': subcategory['name'],
                'category_name': subcategory['category_name'],
                'transactions_cleared': transactions_cleared
            }


def get_essential_category_names():
    """Get list of category names that are marked as essential.

    Used by consistency engine for Essential/Discretionary classification.
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT name FROM normalized_categories
                WHERE is_essential = TRUE AND is_active = TRUE
            ''')
            return {row['name'] for row in cursor.fetchall()}


# =============================================================================


def get_all_categories():
    """Get all categories from database."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT id, name, rule_pattern, ai_suggested FROM categories')
            return cursor.fetchall()
