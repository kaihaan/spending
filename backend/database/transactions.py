"""
Core Transactions - Database Operations

Handles core transaction operations, Huququllah classification, account mappings,
and general transaction utilities.
"""

from .base import get_db
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


# ============================================================================
# CORE TRANSACTION FUNCTIONS
# ============================================================================

def get_all_categories():
    """Get all categories from database."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT id, name, rule_pattern, ai_suggested FROM categories')
            return cursor.fetchall()


def update_transaction_with_enrichment(transaction_id, enrichment_data, enrichment_source='llm'):
    """
    Update TrueLayer transaction with LLM enrichment data.

    Args:
        transaction_id: ID of TrueLayer transaction to update
        enrichment_data: Dict or object with enrichment fields
        enrichment_source: 'llm' or 'cache'
    """
    # Convert object to dict if needed
    if not isinstance(enrichment_data, dict):
        enrichment_data = {
            'primary_category': getattr(enrichment_data, 'primary_category', 'Other'),
            'subcategory': getattr(enrichment_data, 'subcategory', None),
            'merchant_clean_name': getattr(enrichment_data, 'merchant_clean_name', None),
            'merchant_type': getattr(enrichment_data, 'merchant_type', None),
            'essential_discretionary': getattr(enrichment_data, 'essential_discretionary', None),
            'payment_method': getattr(enrichment_data, 'payment_method', None),
            'payment_method_subtype': getattr(enrichment_data, 'payment_method_subtype', None),
            'confidence_score': getattr(enrichment_data, 'confidence_score', None),
            'llm_model': getattr(enrichment_data, 'llm_model', 'unknown'),
        }

    with get_db() as conn:
        with conn.cursor() as cursor:
            # Extract category from enrichment
            primary_category = enrichment_data.get('primary_category', 'Other')

            # Update TrueLayer transaction with enrichment in metadata
            enrichment_metadata = {
                'enrichment': {
                    'primary_category': enrichment_data.get('primary_category', 'Other'),
                    'subcategory': enrichment_data.get('subcategory'),
                    'merchant_clean_name': enrichment_data.get('merchant_clean_name'),
                    'merchant_type': enrichment_data.get('merchant_type'),
                    'essential_discretionary': enrichment_data.get('essential_discretionary'),
                    'payment_method': enrichment_data.get('payment_method'),
                    'payment_method_subtype': enrichment_data.get('payment_method_subtype'),
                    'confidence_score': enrichment_data.get('confidence_score'),
                    'llm_provider': enrichment_source,
                    'llm_model': enrichment_data.get('llm_model', 'unknown'),
                    'enriched_at': 'now()'
                }
            }

            # Update merchant_name if enriched merchant_clean_name is available
            merchant_clean_name = enrichment_data.get('merchant_clean_name')

            if merchant_clean_name:
                cursor.execute('''
                    UPDATE truelayer_transactions
                    SET transaction_category = %s,
                        merchant_name = %s,
                        metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{enrichment}', %s::jsonb),
                        enrichment_required = FALSE
                    WHERE id = %s
                ''', (
                    primary_category,
                    merchant_clean_name,
                    json.dumps(enrichment_metadata['enrichment']),
                    transaction_id
                ))
            else:
                cursor.execute('''
                    UPDATE truelayer_transactions
                    SET transaction_category = %s,
                        metadata = jsonb_set(COALESCE(metadata, '{}'::jsonb), '{enrichment}', %s::jsonb),
                        enrichment_required = FALSE
                    WHERE id = %s
                ''', (
                    primary_category,
                    json.dumps(enrichment_metadata['enrichment']),
                    transaction_id
                ))

            conn.commit()
            return cursor.rowcount > 0


def is_transaction_enriched(transaction_id):
    """
    Check if a transaction has enrichment data.
    Checks both TrueLayer transactions (metadata.enrichment) and legacy transactions.

    Args:
        transaction_id: ID of the transaction

    Returns:
        bool: True if transaction has enrichment data
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Check if TrueLayer transaction with enrichment
            # Must check for primary_category specifically, not just enrichment object existence
            # (empty enrichment objects {} should not count as enriched)
            cursor.execute('''
                SELECT id FROM truelayer_transactions
                WHERE id = %s AND metadata->'enrichment'->>'primary_category' IS NOT NULL
                LIMIT 1
            ''', (transaction_id,))
            return cursor.fetchone() is not None


def get_enrichment_from_cache(description, direction):
    """
    Retrieve cached enrichment for a transaction description.

    Args:
        description: Transaction description to look up
        direction: Transaction direction ('in' or 'out')

    Returns:
        Enrichment object or None if not cached
    """
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT enrichment_data
                FROM llm_enrichment_cache
                WHERE transaction_description = %s AND transaction_direction = %s
                LIMIT 1
            ''', (description, direction))

            row = cursor.fetchone()
            if row and row['enrichment_data']:
                try:
                    import json
                    from mcp.llm_enricher import EnrichmentResult
                    data = json.loads(row['enrichment_data'])
                    return EnrichmentResult(**data)
                except (json.JSONDecodeError, Exception):
                    return None
    return None


def cache_enrichment(description, direction, enrichment, provider, model):
    """
    Cache enrichment result for a transaction description.

    Args:
        description: Transaction description
        direction: Transaction direction ('in' or 'out')
        enrichment: EnrichmentResult object with enrichment data
        provider: LLM provider name
        model: LLM model name
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                import json
                enrichment_json = json.dumps({
                    'primary_category': enrichment.primary_category,
                    'subcategory': enrichment.subcategory,
                    'merchant_clean_name': enrichment.merchant_clean_name,
                    'merchant_type': enrichment.merchant_type,
                    'essential_discretionary': enrichment.essential_discretionary,
                    'payment_method': enrichment.payment_method,
                    'payment_method_subtype': enrichment.payment_method_subtype,
                    'confidence_score': enrichment.confidence_score,
                    'llm_provider': provider,
                    'llm_model': model
                })

                cursor.execute('''
                    INSERT INTO llm_enrichment_cache
                    (transaction_description, transaction_direction, enrichment_data)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (transaction_description, transaction_direction) DO UPDATE SET
                        enrichment_data = EXCLUDED.enrichment_data,
                        cached_at = CURRENT_TIMESTAMP
                ''', (description, direction, enrichment_json))

                conn.commit()
            except Exception as e:
                # Silently fail on cache errors
                pass


def log_enrichment_failure(transaction_id, error_message, retry_count=0, **kwargs):
    """
    Log enrichment failure for a transaction.

    Args:
        transaction_id: ID of transaction that failed
        error_message: Error message explaining the failure
        retry_count: Number of retry attempts already made
        **kwargs: Additional optional parameters (description, error_type, provider) for compatibility
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO llm_enrichment_failures
                    (transaction_id, error_message, retry_count)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (transaction_id) DO UPDATE SET
                        error_message = EXCLUDED.error_message,
                        retry_count = EXCLUDED.retry_count,
                        failed_at = CURRENT_TIMESTAMP
                ''', (transaction_id, str(error_message)[:500], retry_count))

                conn.commit()
            except Exception as e:
                # Silently fail on logging errors
                pass


def get_category_keywords():
    """Get all custom keywords from database grouped by category."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT category_name, keyword
                FROM category_keywords
                ORDER BY category_name, keyword
            ''')
            rows = cursor.fetchall()

            keywords_by_category = {}
            for row in rows:
                category = row['category_name']
                keyword = row['keyword']
                if category not in keywords_by_category:
                    keywords_by_category[category] = []
                keywords_by_category[category].append(keyword)

            return keywords_by_category


def add_category_keyword(category_name, keyword):
    """Add a keyword to a category."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO category_keywords (category_name, keyword)
                    VALUES (%s, %s)
                ''', (category_name, keyword.lower()))
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                conn.rollback()
                return False


def remove_category_keyword(category_name, keyword):
    """Remove a keyword from a category."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                DELETE FROM category_keywords
                WHERE category_name = %s AND keyword = %s
            ''', (category_name, keyword.lower()))
            conn.commit()
            return cursor.rowcount > 0


def create_custom_category(name):
    """Create a new custom category."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('INSERT INTO categories (name) VALUES (%s)', (name,))
                conn.commit()
                return True
            except psycopg2.IntegrityError:
                conn.rollback()
                return False


def delete_custom_category(name):
    """Delete a custom category and all its keywords."""
    # Don't allow deletion of default categories
    default_categories = [
        'Groceries', 'Transport', 'Dining', 'Entertainment',
        'Utilities', 'Shopping', 'Health', 'Income', 'Other'
    ]

    if name in default_categories:
        return False

    with get_db() as conn:
        with conn.cursor() as cursor:
            # Delete keywords first
            cursor.execute('DELETE FROM category_keywords WHERE category_name = %s', (name,))
            # Delete category
            cursor.execute('DELETE FROM categories WHERE name = %s', (name,))
            conn.commit()
            return cursor.rowcount > 0


def get_all_account_mappings():
    """Get all account mappings from database."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, sort_code, account_number, friendly_name, created_at
                FROM account_mappings
                ORDER BY friendly_name
            ''')
            return cursor.fetchall()


def add_account_mapping(sort_code, account_number, friendly_name):
    """Add a new account mapping."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO account_mappings (sort_code, account_number, friendly_name)
                    VALUES (%s, %s, %s)
                    RETURNING id
                ''', (sort_code, account_number, friendly_name))
                mapping_id = cursor.fetchone()[0]
                conn.commit()
                return mapping_id
            except psycopg2.IntegrityError:
                conn.rollback()
                return None


def update_account_mapping(mapping_id, friendly_name):
    """Update the friendly name for an account mapping."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE account_mappings
                SET friendly_name = %s
                WHERE id = %s
            ''', (friendly_name, mapping_id))
            conn.commit()
            return cursor.rowcount > 0


def delete_account_mapping(mapping_id):
    """Delete an account mapping."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM account_mappings WHERE id = %s', (mapping_id,))
            conn.commit()
            return cursor.rowcount > 0


def get_account_mapping_by_details(sort_code, account_number):
    """Look up account mapping by sort code and account number."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, sort_code, account_number, friendly_name, created_at
                FROM account_mappings
                WHERE sort_code = %s AND account_number = %s
            ''', (sort_code, account_number))
            return cursor.fetchone()


def update_truelayer_transaction_merchant(transaction_id, merchant_name):
    """Update merchant_name for a TrueLayer transaction."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_transactions
                SET merchant_name = %s
                WHERE id = %s
            ''', (merchant_name, transaction_id))
            conn.commit()
            return cursor.rowcount > 0


def update_transaction_huququllah(transaction_id, classification):
    """Update Huququllah classification for TrueLayer transaction in metadata."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get current metadata
            cursor.execute('SELECT metadata FROM truelayer_transactions WHERE id = %s', (transaction_id,))
            row = cursor.fetchone()
            if not row:
                return False

            # Update metadata
            metadata = row['metadata'] or {}
            if not isinstance(metadata, dict):
                metadata = {}
            metadata['huququllah_classification'] = classification

            cursor.execute('''
                UPDATE truelayer_transactions
                SET metadata = %s
                WHERE id = %s
            ''', (json.dumps(metadata), transaction_id))
            conn.commit()
            return cursor.rowcount > 0


def get_unclassified_transactions():
    """Get TrueLayer transactions without Huququllah classification."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, timestamp as date, description, amount, currency,
                       merchant_name as merchant, metadata
                FROM truelayer_transactions
                WHERE transaction_type = 'DEBIT'
                AND amount > 0
                AND (metadata->>'huququllah_classification' IS NULL
                     OR metadata->>'huququllah_classification' = '')
                ORDER BY timestamp DESC
            ''')
            return cursor.fetchall()


def get_huququllah_summary(date_from=None, date_to=None):
    """Calculate Huququllah obligations from TrueLayer transactions."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = '''
                SELECT
                    SUM(CASE
                        WHEN COALESCE(
                            metadata->>'huququllah_classification',
                            LOWER(metadata->'enrichment'->>'essential_discretionary')
                        ) = 'essential'
                        THEN amount ELSE 0 END) as essential_expenses,
                    SUM(CASE
                        WHEN COALESCE(
                            metadata->>'huququllah_classification',
                            LOWER(metadata->'enrichment'->>'essential_discretionary')
                        ) = 'discretionary'
                        THEN amount ELSE 0 END) as discretionary_expenses,
                    COUNT(CASE
                        WHEN COALESCE(
                            metadata->>'huququllah_classification',
                            LOWER(metadata->'enrichment'->>'essential_discretionary')
                        ) IS NULL
                        THEN 1 END) as unclassified_count
                FROM truelayer_transactions
                WHERE transaction_type = 'DEBIT' AND amount > 0
            '''
            params = []

            if date_from:
                query += ' AND timestamp >= %s'
                params.append(date_from)

            if date_to:
                query += ' AND timestamp <= %s'
                params.append(date_to)

            cursor.execute(query, params)
            result = cursor.fetchone()

            if result:
                essential = float(result['essential_expenses'] or 0)
                discretionary = float(result['discretionary_expenses'] or 0)
                unclassified = result['unclassified_count'] or 0
                huququllah = discretionary * 0.19

                return {
                    'essential_expenses': round(essential, 2),
                    'discretionary_expenses': round(discretionary, 2),
                    'huququllah_due': round(huququllah, 2),
                    'unclassified_count': unclassified
                }

            return {
                'essential_expenses': 0,
                'discretionary_expenses': 0,
                'huququllah_due': 0,
                'unclassified_count': 0
            }


def get_transaction_by_id(transaction_id):
    """Get a single transaction by ID with computed huququllah_classification."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT
                    id,
                    timestamp,
                    description,
                    amount,
                    currency,
                    transaction_type,
                    transaction_category as category,
                    merchant_name as merchant,
                    metadata,
                    COALESCE(
                        metadata->>'huququllah_classification',
                        LOWER(metadata->'enrichment'->>'essential_discretionary')
                    ) as huququllah_classification
                FROM truelayer_transactions
                WHERE id = %s
            ''', (transaction_id,))
            return cursor.fetchone()


def get_all_transactions():
    """Get all transactions with computed huququllah_classification."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT
                    id,
                    timestamp,
                    description,
                    amount,
                    currency,
                    transaction_type,
                    transaction_category as category,
                    merchant_name as merchant,
                    metadata,
                    COALESCE(
                        metadata->>'huququllah_classification',
                        LOWER(metadata->'enrichment'->>'essential_discretionary')
                    ) as huququllah_classification
                FROM truelayer_transactions
                ORDER BY timestamp DESC
            ''')
            return cursor.fetchall()


# ============================================================================
