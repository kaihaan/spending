"""
Transaction Matching - Database Operations

Handles consistency checking and matching logic across different transaction sources.
"""

from .base import get_db
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


# ============================================================================
# SOURCE COVERAGE & STALENESS DETECTION
# ============================================================================


def get_source_coverage_dates(user_id: int = 1) -> dict:
    """
    Get the max date coverage for each enrichment source vs bank transactions.

    Used to detect when source data is stale (bank transactions are newer
    than the last synced source data).

    Args:
        user_id: User ID to check coverage for

    Returns:
        dict with date ranges and list of stale sources needing refresh
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get max bank transaction date
            cursor.execute('''
                SELECT MAX(timestamp::date) as max_date,
                       MIN(timestamp::date) as min_date,
                       COUNT(*) as count
                FROM truelayer_transactions
            ''')
            bank_result = cursor.fetchone()
            bank_max = bank_result['max_date'] if bank_result else None
            bank_min = bank_result['min_date'] if bank_result else None
            bank_count = bank_result['count'] if bank_result else 0

            # Get max Amazon order date
            cursor.execute('''
                SELECT MAX(order_date) as max_date,
                       MIN(order_date) as min_date,
                       COUNT(*) as count
                FROM amazon_orders
            ''')
            amazon_result = cursor.fetchone()
            amazon_max = amazon_result['max_date'] if amazon_result else None
            amazon_min = amazon_result['min_date'] if amazon_result else None
            amazon_count = amazon_result['count'] if amazon_result else 0

            # Get max Apple transaction date
            cursor.execute('''
                SELECT MAX(order_date) as max_date,
                       MIN(order_date) as min_date,
                       COUNT(*) as count
                FROM apple_transactions
            ''')
            apple_result = cursor.fetchone()
            apple_max = apple_result['max_date'] if apple_result else None
            apple_min = apple_result['min_date'] if apple_result else None
            apple_count = apple_result['count'] if apple_result else 0

            # Get max Gmail receipt date
            cursor.execute('''
                SELECT MAX(receipt_date) as max_date,
                       MIN(receipt_date) as min_date,
                       COUNT(*) as count
                FROM gmail_receipts r
                JOIN gmail_connections c ON r.connection_id = c.id
                WHERE c.user_id = %s AND r.deleted_at IS NULL
            ''', (user_id,))
            gmail_result = cursor.fetchone()
            gmail_max = gmail_result['max_date'] if gmail_result else None
            gmail_min = gmail_result['min_date'] if gmail_result else None
            gmail_count = gmail_result['count'] if gmail_result else 0

            # Determine which sources are stale (> 7 days behind bank data)
            stale_sources = []
            stale_threshold_days = 7

            if bank_max:
                from datetime import timedelta
                threshold_date = bank_max - timedelta(days=stale_threshold_days)

                if amazon_count > 0 and amazon_max and amazon_max < threshold_date:
                    stale_sources.append('amazon')
                if apple_count > 0 and apple_max and apple_max < threshold_date:
                    stale_sources.append('apple')
                if gmail_count > 0 and gmail_max and gmail_max < threshold_date:
                    stale_sources.append('gmail')

            # Convert dates to strings for JSON serialization
            def date_to_str(d):
                return d.isoformat() if d else None

            return {
                'bank_transactions': {
                    'max_date': date_to_str(bank_max),
                    'min_date': date_to_str(bank_min),
                    'count': bank_count
                },
                'amazon': {
                    'max_date': date_to_str(amazon_max),
                    'min_date': date_to_str(amazon_min),
                    'count': amazon_count,
                    'is_stale': 'amazon' in stale_sources
                },
                'apple': {
                    'max_date': date_to_str(apple_max),
                    'min_date': date_to_str(apple_min),
                    'count': apple_count,
                    'is_stale': 'apple' in stale_sources
                },
                'gmail': {
                    'max_date': date_to_str(gmail_max),
                    'min_date': date_to_str(gmail_min),
                    'count': gmail_count,
                    'is_stale': 'gmail' in stale_sources
                },
                'stale_sources': stale_sources,
                'stale_threshold_days': stale_threshold_days
            }


# ============================================================================
# CONSISTENCY ENGINE FUNCTIONS
# ============================================================================


def get_category_rules(active_only: bool = True) -> list:
    """Fetch category rules sorted by priority (highest first).

    Args:
        active_only: If True, only return active rules

    Returns:
        List of rule dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = '''
                SELECT id, rule_name, transaction_type, description_pattern,
                       pattern_type, category, subcategory, priority, is_active,
                       source, usage_count, created_at
                FROM category_rules
            '''
            if active_only:
                query += ' WHERE is_active = TRUE'
            query += ' ORDER BY priority DESC, id ASC'

            cursor.execute(query)
            return [dict(row) for row in cursor.fetchall()]


def get_merchant_normalizations() -> list:
    """Fetch merchant normalizations sorted by priority (highest first).

    Returns:
        List of normalization dictionaries
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, pattern, pattern_type, normalized_name, merchant_type,
                       default_category, priority, source, usage_count,
                       created_at, updated_at
                FROM merchant_normalizations
                ORDER BY priority DESC, id ASC
            ''')
            return [dict(row) for row in cursor.fetchall()]


def increment_rule_usage(rule_id: int) -> bool:
    """Increment usage count for a category rule.

    Args:
        rule_id: ID of the rule to update

    Returns:
        True if updated successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE category_rules
                SET usage_count = usage_count + 1
                WHERE id = %s
            ''', (rule_id,))
            conn.commit()
            return cursor.rowcount > 0


def increment_merchant_normalization_usage(normalization_id: int) -> bool:
    """Increment usage count for a merchant normalization.

    Args:
        normalization_id: ID of the normalization to update

    Returns:
        True if updated successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE merchant_normalizations
                SET usage_count = usage_count + 1,
                    updated_at = NOW()
                WHERE id = %s
            ''', (normalization_id,))
            conn.commit()
            return cursor.rowcount > 0


def add_category_rule(rule_name: str, description_pattern: str, category: str,
                      transaction_type: str = None, subcategory: str = None,
                      pattern_type: str = 'contains', priority: int = 0,
                      source: str = 'manual') -> int:
    """Add a new category rule.

    Args:
        rule_name: Human-readable name for the rule
        description_pattern: Pattern to match in description
        category: Category to assign
        transaction_type: 'CREDIT', 'DEBIT', or None (both)
        subcategory: Optional subcategory
        pattern_type: 'contains', 'starts_with', 'exact', 'regex'
        priority: Higher = checked first
        source: 'manual', 'learned', 'llm'

    Returns:
        ID of the created rule
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO category_rules
                (rule_name, transaction_type, description_pattern, pattern_type,
                 category, subcategory, priority, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (rule_name, transaction_type, description_pattern, pattern_type,
                  category, subcategory, priority, source))
            rule_id = cursor.fetchone()[0]
            conn.commit()
            return rule_id


def add_merchant_normalization(pattern: str, normalized_name: str,
                               merchant_type: str = None, default_category: str = None,
                               pattern_type: str = 'contains', priority: int = 0,
                               source: str = 'manual') -> int:
    """Add a new merchant normalization.

    Args:
        pattern: Pattern to match in description
        normalized_name: Standardized merchant name
        merchant_type: Type (e.g., 'bakery', 'supermarket')
        default_category: Default category if matched
        pattern_type: 'contains', 'starts_with', 'exact', 'regex'
        priority: Higher = checked first
        source: 'manual', 'learned', 'llm'

    Returns:
        ID of the created normalization
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO merchant_normalizations
                (pattern, pattern_type, normalized_name, merchant_type,
                 default_category, priority, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pattern, pattern_type) DO UPDATE SET
                    normalized_name = EXCLUDED.normalized_name,
                    merchant_type = EXCLUDED.merchant_type,
                    default_category = EXCLUDED.default_category,
                    priority = EXCLUDED.priority,
                    updated_at = NOW()
                RETURNING id
            ''', (pattern, pattern_type, normalized_name, merchant_type,
                  default_category, priority, source))
            norm_id = cursor.fetchone()[0]
            conn.commit()
            return norm_id


def delete_category_rule(rule_id: int) -> bool:
    """Delete a category rule.

    Args:
        rule_id: ID of the rule to delete

    Returns:
        True if deleted successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM category_rules WHERE id = %s', (rule_id,))
            conn.commit()
            return cursor.rowcount > 0


def delete_merchant_normalization(normalization_id: int) -> bool:
    """Delete a merchant normalization.

    Args:
        normalization_id: ID of the normalization to delete

    Returns:
        True if deleted successfully
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM merchant_normalizations WHERE id = %s', (normalization_id,))
            conn.commit()
            return cursor.rowcount > 0


def update_category_rule(rule_id: int, **kwargs) -> bool:
    """Update a category rule.

    Args:
        rule_id: ID of the rule to update
        **kwargs: Fields to update (rule_name, description_pattern, category, etc.)

    Returns:
        True if updated successfully
    """
    allowed_fields = {'rule_name', 'transaction_type', 'description_pattern',
                      'pattern_type', 'category', 'subcategory', 'priority',
                      'is_active', 'source'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return False

    with get_db() as conn:
        with conn.cursor() as cursor:
            set_clause = ', '.join(f'{k} = %s' for k in updates.keys())
            values = list(updates.values()) + [rule_id]
            cursor.execute(f'''
                UPDATE category_rules
                SET {set_clause}
                WHERE id = %s
            ''', values)
            conn.commit()
            return cursor.rowcount > 0


def update_merchant_normalization(normalization_id: int, **kwargs) -> bool:
    """Update a merchant normalization.

    Args:
        normalization_id: ID of the normalization to update
        **kwargs: Fields to update (pattern, normalized_name, etc.)

    Returns:
        True if updated successfully
    """
    allowed_fields = {'pattern', 'pattern_type', 'normalized_name', 'merchant_type',
                      'default_category', 'priority', 'source'}
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

    if not updates:
        return False

    updates['updated_at'] = 'NOW()'

    with get_db() as conn:
        with conn.cursor() as cursor:
            set_parts = []
            values = []
            for k, v in updates.items():
                if v == 'NOW()':
                    set_parts.append(f'{k} = NOW()')
                else:
                    set_parts.append(f'{k} = %s')
                    values.append(v)
            values.append(normalization_id)

            cursor.execute(f'''
                UPDATE merchant_normalizations
                SET {', '.join(set_parts)}
                WHERE id = %s
            ''', values)
            conn.commit()
            return cursor.rowcount > 0


# ============================================================================
