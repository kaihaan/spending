"""
PostgreSQL Database Layer for Personal Finance Tracker

This module provides database connection management and CRUD operations
for the PostgreSQL backend. It replaces the SQLite implementation.

Connection pooling is used for better performance with concurrent requests.
"""

import psycopg2
from psycopg2 import pool, extras
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import os
from dotenv import load_dotenv

# Load environment variables (override=True to prefer .env file over shell env)
load_dotenv(override=True)

# Database connection configuration
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'spending_db'),
    'user': os.getenv('POSTGRES_USER', 'spending_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'spending_password')
}

# Connection pool (min 1, max 10 connections)
connection_pool = None


def init_pool():
    """Initialize PostgreSQL connection pool"""
    global connection_pool
    try:
        connection_pool = psycopg2.pool.SimpleConnectionPool(
            1,  # Minimum connections
            10,  # Maximum connections
            **DB_CONFIG
        )
        if connection_pool:
            print("✓ PostgreSQL connection pool created successfully")
            # Create oauth_state table if it doesn't exist
            _create_oauth_state_table()
    except (Exception, psycopg2.Error) as error:
        print(f"✗ Error creating connection pool: {error}")
        raise


def _create_oauth_state_table():
    """Create oauth_state table if it doesn't exist."""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS oauth_state (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        state VARCHAR(255) UNIQUE NOT NULL,
                        code_verifier TEXT NOT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                    )
                ''')
                # Create index for faster state lookups
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_oauth_state_state ON oauth_state(state)')
                conn.commit()
    except Exception as e:
        print(f"⚠️  Warning: Could not create oauth_state table: {e}")


@contextmanager
def get_db():
    """Context manager for database connections from pool."""
    if connection_pool is None:
        init_pool()

    conn = connection_pool.getconn()
    try:
        yield conn
    finally:
        connection_pool.putconn(conn)


def get_all_transactions():
    """Get all transactions from database."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, date, description, amount, category, source_file,
                       merchant, huququllah_classification, created_at
                FROM transactions
                ORDER BY date DESC
            ''')
            return cursor.fetchall()


def add_transaction(date, description, amount, category='Other', source_file=None, merchant=None):
    """Add a single transaction to database."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO transactions (date, description, amount, category, source_file, merchant)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (date, description, amount, category, source_file, merchant))
            transaction_id = cursor.fetchone()[0]
            conn.commit()
            return transaction_id


def get_all_categories():
    """Get all categories from database."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT id, name, rule_pattern, ai_suggested FROM categories')
            return cursor.fetchall()


def get_transaction_by_id(transaction_id):
    """Get a single transaction by ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, date, description, amount, category, source_file,
                       merchant, huququllah_classification, created_at
                FROM transactions
                WHERE id = %s
            ''', (transaction_id,))
            return cursor.fetchone()


def get_transactions_by_merchant(merchant):
    """Get all transactions from a specific merchant."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, date, description, amount, category, source_file,
                       merchant, huququllah_classification, created_at
                FROM transactions
                WHERE merchant = %s
                ORDER BY date DESC
            ''', (merchant,))
            return cursor.fetchall()


def update_transaction_category(transaction_id, category):
    """Update the category of a specific transaction."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET category = %s
                WHERE id = %s
            ''', (category, transaction_id))
            conn.commit()
            return cursor.rowcount > 0


def update_transactions_by_merchant(merchant, category):
    """Update the category for all transactions from a specific merchant."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET category = %s
                WHERE merchant = %s
            ''', (category, merchant))
            conn.commit()
            return cursor.rowcount


def update_merchant(transaction_id, merchant):
    """Update the merchant name for a specific transaction."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET merchant = %s
                WHERE id = %s
            ''', (merchant, transaction_id))
            conn.commit()
            return cursor.rowcount > 0


def clear_all_transactions():
    """Delete all transactions from the database."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM transactions')
            count = cursor.fetchone()[0]
            cursor.execute('DELETE FROM transactions')
            conn.commit()
            return count


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


def bulk_update_transaction_categories(transaction_ids, category):
    """Update category for multiple transactions."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET category = %s
                WHERE id = ANY(%s)
            ''', (category, transaction_ids))
            conn.commit()
            return cursor.rowcount


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


def update_transaction_huququllah(transaction_id, classification):
    """Update the Huququllah classification of a specific transaction."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET huququllah_classification = %s
                WHERE id = %s
            ''', (classification, transaction_id))
            conn.commit()
            return cursor.rowcount > 0


def get_unclassified_transactions():
    """Get all expense transactions that have not been classified for Huququllah."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, date, description, amount, category, source_file,
                       merchant, huququllah_classification, created_at
                FROM transactions
                WHERE huququllah_classification IS NULL AND amount < 0
                ORDER BY date DESC
            ''')
            return cursor.fetchall()


def get_huququllah_summary(date_from=None, date_to=None):
    """Get summary of essential vs discretionary spending for Huququllah calculation."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = '''
                SELECT
                    SUM(CASE WHEN amount < 0 AND huququllah_classification = 'essential'
                        THEN ABS(amount) ELSE 0 END) as essential_expenses,
                    SUM(CASE WHEN amount < 0 AND huququllah_classification = 'discretionary'
                        THEN ABS(amount) ELSE 0 END) as discretionary_expenses,
                    COUNT(CASE WHEN huququllah_classification IS NULL AND amount < 0
                        THEN 1 END) as unclassified_count
                FROM transactions
                WHERE 1=1
            '''
            params = []

            if date_from:
                query += ' AND date >= %s'
                params.append(date_from)

            if date_to:
                query += ' AND date <= %s'
                params.append(date_to)

            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                essential = float(row['essential_expenses'] or 0)
                discretionary = float(row['discretionary_expenses'] or 0)
                unclassified = row['unclassified_count'] or 0
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


# ============================================================================
# Amazon Order Management Functions
# ============================================================================

def import_amazon_orders(orders, source_file):
    """Bulk import Amazon orders into database."""
    imported = 0
    duplicates = 0

    with get_db() as conn:
        with conn.cursor() as cursor:
            for order in orders:
                try:
                    cursor.execute('''
                        INSERT INTO amazon_orders
                        (order_id, order_date, website, currency, total_owed,
                         product_names, order_status, shipment_status, source_file)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        order['order_id'],
                        order['order_date'],
                        order['website'],
                        order['currency'],
                        order['total_owed'],
                        order['product_names'],
                        order.get('order_status'),
                        order.get('shipment_status'),
                        source_file
                    ))
                    imported += 1
                except psycopg2.IntegrityError:
                    duplicates += 1
                    continue

            conn.commit()
    return (imported, duplicates)


def get_amazon_orders(date_from=None, date_to=None, website=None):
    """Get Amazon orders with optional filters."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = 'SELECT * FROM amazon_orders WHERE 1=1'
            params = []

            if date_from:
                query += ' AND order_date >= %s'
                params.append(date_from)

            if date_to:
                query += ' AND order_date <= %s'
                params.append(date_to)

            if website:
                query += ' AND website = %s'
                params.append(website)

            query += ' ORDER BY order_date DESC'

            cursor.execute(query, params)
            return cursor.fetchall()


def get_amazon_order_by_id(order_id):
    """Get a single Amazon order by its Amazon order ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT * FROM amazon_orders WHERE order_id = %s', (order_id,))
            return cursor.fetchone()


def match_amazon_transaction(transaction_id, amazon_order_db_id, confidence):
    """Record a match between a transaction and an Amazon order."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO amazon_transaction_matches
                    (transaction_id, amazon_order_id, match_confidence)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (transaction_id) DO UPDATE
                    SET match_confidence = EXCLUDED.match_confidence
                ''', (transaction_id, amazon_order_db_id, confidence))
                conn.commit()
                return True
            except Exception as e:
                print(f"Error matching transaction: {e}")
                return False


def get_amazon_match_for_transaction(transaction_id):
    """Get the Amazon order match for a transaction if it exists."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT
                    m.id as match_id,
                    m.match_confidence,
                    m.matched_at,
                    o.id as amazon_order_id,
                    o.order_id,
                    o.order_date,
                    o.website,
                    o.currency,
                    o.total_owed,
                    o.product_names,
                    o.order_status,
                    o.shipment_status,
                    o.source_file,
                    o.created_at
                FROM amazon_transaction_matches m
                JOIN amazon_orders o ON m.amazon_order_id = o.id
                WHERE m.transaction_id = %s
            ''', (transaction_id,))
            return cursor.fetchone()


def get_unmatched_amazon_transactions():
    """Get all transactions with Amazon merchant that haven't been matched to orders."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT t.*
                FROM transactions t
                LEFT JOIN amazon_transaction_matches m ON t.id = m.transaction_id
                WHERE m.id IS NULL
                AND (
                    UPPER(t.merchant) LIKE '%AMAZON%'
                    OR UPPER(t.merchant) LIKE '%AMZN%'
                    OR UPPER(t.description) LIKE '%AMAZON%'
                    OR UPPER(t.description) LIKE '%AMZN%'
                )
                ORDER BY t.date DESC
            ''')
            return cursor.fetchall()


def check_amazon_coverage(date_from, date_to):
    """Check if Amazon order data exists for a date range."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Count Amazon transactions in range
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM transactions
                WHERE date >= %s AND date <= %s
                AND (
                    UPPER(merchant) LIKE '%AMAZON%'
                    OR UPPER(merchant) LIKE '%AMZN%'
                    OR UPPER(description) LIKE '%AMAZON%'
                    OR UPPER(description) LIKE '%AMZN%'
                )
            ''', (date_from, date_to))
            amazon_txn_count = cursor.fetchone()['count']

            # Count Amazon orders in range (with ±3 day buffer)
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM amazon_orders
                WHERE order_date >= (%s::date - interval '3 days')
                AND order_date <= (%s::date + interval '3 days')
            ''', (date_from, date_to))
            amazon_order_count = cursor.fetchone()['count']

            # Count matched transactions
            cursor.execute('''
                SELECT COUNT(*) as count
                FROM transactions t
                JOIN amazon_transaction_matches m ON t.id = m.transaction_id
                WHERE t.date >= %s AND t.date <= %s
            ''', (date_from, date_to))
            matched_count = cursor.fetchone()['count']

            return {
                'amazon_transactions': amazon_txn_count,
                'amazon_orders_available': amazon_order_count,
                'matched_count': matched_count,
                'has_coverage': amazon_order_count > 0,
                'match_rate': (matched_count / amazon_txn_count * 100) if amazon_txn_count > 0 else 0
            }


def get_amazon_statistics():
    """Get overall Amazon import and matching statistics."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Total orders imported
            cursor.execute('SELECT COUNT(*) as count FROM amazon_orders')
            total_orders = cursor.fetchone()['count']

            # Date range of orders
            cursor.execute('SELECT MIN(order_date) as min_date, MAX(order_date) as max_date FROM amazon_orders')
            date_range = cursor.fetchone()

            # Total matched transactions
            cursor.execute('SELECT COUNT(*) as count FROM amazon_transaction_matches')
            total_matched = cursor.fetchone()['count']

            # Total unmatched Amazon transactions
            unmatched = get_unmatched_amazon_transactions()

            return {
                'total_orders': total_orders,
                'min_order_date': date_range['min_date'],
                'max_order_date': date_range['max_date'],
                'total_matched': total_matched,
                'total_unmatched': len(unmatched)
            }


def clear_amazon_orders():
    """Delete all Amazon orders and matches from database."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Count before deletion
            cursor.execute('SELECT COUNT(*) FROM amazon_orders')
            orders_count = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM amazon_transaction_matches')
            matches_count = cursor.fetchone()[0]

            # Delete matches first (foreign key)
            cursor.execute('DELETE FROM amazon_transaction_matches')

            # Delete orders
            cursor.execute('DELETE FROM amazon_orders')

            conn.commit()
            return (orders_count, matches_count)


def update_transaction_description(transaction_id, new_description):
    """Update the description of a transaction."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE transactions
                SET description = %s
                WHERE id = %s
            ''', (new_description, transaction_id))
            conn.commit()
            return cursor.rowcount > 0


# ============================================================================
# Amazon Returns Management Functions
# ============================================================================

def import_amazon_returns(returns, source_file):
    """Bulk import Amazon returns into database."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            imported = 0
            duplicates = 0

            for ret in returns:
                try:
                    cursor.execute('''
                        INSERT INTO amazon_returns
                        (order_id, reversal_id, refund_completion_date, currency, amount_refunded,
                         status, disbursement_type, source_file)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        ret['order_id'],
                        ret['reversal_id'],
                        ret['refund_completion_date'],
                        ret['currency'],
                        ret['amount_refunded'],
                        ret.get('status'),
                        ret.get('disbursement_type'),
                        source_file
                    ))
                    imported += 1
                except psycopg2.IntegrityError:
                    duplicates += 1
                    continue

            conn.commit()
    return (imported, duplicates)


def get_amazon_returns(order_id=None):
    """Get Amazon returns with optional order ID filter."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if order_id:
                cursor.execute('SELECT * FROM amazon_returns WHERE order_id = %s', (order_id,))
            else:
                cursor.execute('SELECT * FROM amazon_returns ORDER BY refund_completion_date DESC')

            return cursor.fetchall()


def link_return_to_transactions(return_id, original_transaction_id, refund_transaction_id):
    """Link a return to its original purchase and refund transactions."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE amazon_returns
                SET original_transaction_id = %s,
                    refund_transaction_id = %s
                WHERE id = %s
            ''', (original_transaction_id, refund_transaction_id, return_id))
            conn.commit()
            return cursor.rowcount > 0


def mark_transaction_as_returned(transaction_id):
    """Mark a transaction as returned by updating its description with a label."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get current description
            cursor.execute('SELECT description FROM transactions WHERE id = %s', (transaction_id,))
            row = cursor.fetchone()

            if not row:
                return False

            current_desc = row['description']

            # Add [RETURNED] prefix if not already there
            if not current_desc.startswith('[RETURNED] '):
                new_desc = f'[RETURNED] {current_desc}'
                cursor.execute('''
                    UPDATE transactions
                    SET description = %s
                    WHERE id = %s
                ''', (new_desc, transaction_id))
                conn.commit()
                return True

            return False


def get_returns_statistics():
    """Get overall returns import and matching statistics."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Total returns imported
            cursor.execute('SELECT COUNT(*) as count FROM amazon_returns')
            total_returns = cursor.fetchone()['count']

            # Date range of returns
            cursor.execute('SELECT MIN(refund_completion_date) as min_date, MAX(refund_completion_date) as max_date FROM amazon_returns')
            date_range = cursor.fetchone()

            # Total amount refunded
            cursor.execute('SELECT SUM(amount_refunded) as total FROM amazon_returns')
            total_refunded = cursor.fetchone()['total'] or 0

            # Matched returns (those linked to transactions)
            cursor.execute('SELECT COUNT(*) as count FROM amazon_returns WHERE original_transaction_id IS NOT NULL')
            matched_returns = cursor.fetchone()['count']

            return {
                'total_returns': total_returns,
                'min_return_date': date_range['min_date'],
                'max_return_date': date_range['max_date'],
                'total_refunded': round(float(total_refunded), 2),
                'matched_returns': matched_returns,
                'unmatched_returns': total_returns - matched_returns
            }


def clear_amazon_returns():
    """Delete all Amazon returns from database. Also removes [RETURNED] labels from transactions."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Get all transactions marked as returned
            cursor.execute('SELECT id, description FROM transactions WHERE description LIKE %s', ('[RETURNED] %',))
            returned_txns = cursor.fetchall()

            # Remove [RETURNED] prefix
            for txn in returned_txns:
                new_desc = txn['description'].replace('[RETURNED] ', '', 1)
                cursor.execute('UPDATE transactions SET description = %s WHERE id = %s', (new_desc, txn['id']))

            # Count and delete returns
            cursor.execute('SELECT COUNT(*) FROM amazon_returns')
            return_count = cursor.fetchone()[0]

            cursor.execute('DELETE FROM amazon_returns')
            conn.commit()

            return return_count


# ============================================================================
# Apple Transactions Management Functions
# ============================================================================

def import_apple_transactions(transactions, source_file):
    """Bulk import Apple transactions from parsed HTML data."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            imported = 0
            duplicates = 0

            for txn in transactions:
                try:
                    cursor.execute('''
                        INSERT INTO apple_transactions (
                            order_id, order_date, total_amount, currency,
                            app_names, publishers, item_count, source_file
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (
                        txn['order_id'],
                        txn['order_date'],
                        txn['total_amount'],
                        txn.get('currency', 'GBP'),
                        txn['app_names'],
                        txn.get('publishers', ''),
                        txn.get('item_count', 1),
                        source_file
                    ))
                    imported += 1
                except psycopg2.IntegrityError:
                    # Duplicate order_id
                    duplicates += 1

            conn.commit()
    return imported, duplicates


def get_apple_transactions(date_from=None, date_to=None):
    """Get all Apple transactions, optionally filtered by date range."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = '''
                SELECT
                    a.*,
                    m.bank_transaction_id as matched_bank_transaction_id
                FROM apple_transactions a
                LEFT JOIN apple_transaction_matches m ON a.id = m.apple_transaction_id
                WHERE 1=1
            '''
            params = []

            if date_from:
                query += ' AND a.order_date >= %s'
                params.append(date_from)

            if date_to:
                query += ' AND a.order_date <= %s'
                params.append(date_to)

            query += ' ORDER BY a.order_date DESC'

            cursor.execute(query, params)
            return cursor.fetchall()


def get_apple_transaction_by_id(order_id):
    """Get a specific Apple transaction by database ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('SELECT * FROM apple_transactions WHERE id = %s', (order_id,))
            return cursor.fetchone()


def match_apple_transaction(bank_transaction_id, apple_transaction_db_id, confidence):
    """Record a match between a bank transaction and an Apple purchase."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check if transaction already matched
            cursor.execute('''
                SELECT id FROM apple_transaction_matches
                WHERE bank_transaction_id = %s
            ''', (bank_transaction_id,))

            existing = cursor.fetchone()
            if existing:
                # Update existing match
                cursor.execute('''
                    UPDATE apple_transaction_matches
                    SET apple_transaction_id = %s, confidence = %s, matched_at = CURRENT_TIMESTAMP
                    WHERE bank_transaction_id = %s
                ''', (apple_transaction_db_id, confidence, bank_transaction_id))
                conn.commit()
                return existing['id']
            else:
                # Insert new match
                cursor.execute('''
                    INSERT INTO apple_transaction_matches (
                        bank_transaction_id, apple_transaction_id, confidence
                    ) VALUES (%s, %s, %s)
                    RETURNING id
                ''', (bank_transaction_id, apple_transaction_db_id, confidence))
                match_id = cursor.fetchone()[0]
                conn.commit()
                return match_id


def get_apple_statistics():
    """Get statistics about imported Apple transactions."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Total transactions
            cursor.execute('SELECT COUNT(*) as count FROM apple_transactions')
            total = cursor.fetchone()['count']

            if total == 0:
                return {
                    'total_transactions': 0,
                    'min_transaction_date': None,
                    'max_transaction_date': None,
                    'total_spent': 0,
                    'matched_transactions': 0,
                    'unmatched_transactions': 0
                }

            # Date range
            cursor.execute('SELECT MIN(order_date) as min_date, MAX(order_date) as max_date FROM apple_transactions')
            date_result = cursor.fetchone()
            min_date = date_result['min_date']
            max_date = date_result['max_date']

            # Total spent
            cursor.execute('SELECT SUM(total_amount) as total FROM apple_transactions')
            total_spent = cursor.fetchone()['total'] or 0

            # Matched count
            cursor.execute('SELECT COUNT(*) as count FROM apple_transaction_matches')
            matched = cursor.fetchone()['count']

            return {
                'total_transactions': total,
                'min_transaction_date': min_date,
                'max_transaction_date': max_date,
                'total_spent': float(total_spent),
                'matched_transactions': matched,
                'unmatched_transactions': total - matched
            }


def clear_apple_transactions():
    """Delete all Apple transactions from database."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            # Count before deletion
            cursor.execute('SELECT COUNT(*) FROM apple_transactions')
            count = cursor.fetchone()[0]

            # Delete matches first (foreign key constraint)
            cursor.execute('DELETE FROM apple_transaction_matches')

            # Delete transactions
            cursor.execute('DELETE FROM apple_transactions')

            conn.commit()
            return count


# TrueLayer Bank Connection Functions

def get_user_connections(user_id):
    """Get all active TrueLayer bank connections for a user."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, user_id, provider_id, access_token, refresh_token,
                       token_expires_at, connection_status, last_synced_at, created_at
                FROM bank_connections
                WHERE user_id = %s AND connection_status = 'active'
                ORDER BY created_at DESC
            ''', (user_id,))
            return cursor.fetchall()


def get_connection(connection_id):
    """Get a specific TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, user_id, provider_id, access_token, refresh_token,
                       token_expires_at, connection_status, last_synced_at, created_at
                FROM bank_connections
                WHERE id = %s
            ''', (connection_id,))
            return cursor.fetchone()


def get_connection_accounts(connection_id):
    """Get all accounts linked to a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, connection_id, account_id, display_name, account_type,
                       currency, last_synced_at, created_at
                FROM truelayer_accounts
                WHERE connection_id = %s
                ORDER BY display_name
            ''', (connection_id,))
            return cursor.fetchall()


def get_account_by_truelayer_id(truelayer_account_id):
    """Get account from database by TrueLayer account ID."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, connection_id, account_id, display_name, account_type,
                       currency, created_at
                FROM truelayer_accounts
                WHERE account_id = %s
            ''', (truelayer_account_id,))
            return cursor.fetchone()


def save_bank_connection(user_id, provider_id, access_token, refresh_token, expires_at):
    """Save a new TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO bank_connections
                (user_id, provider_id, provider_name, access_token, refresh_token, token_expires_at, connection_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'active')
                RETURNING id
            ''', (user_id, provider_id, 'TrueLayer', access_token, refresh_token, expires_at))
            connection_id = cursor.fetchone()[0]
            conn.commit()
            return connection_id


def update_connection_status(connection_id, status):
    """Update the status of a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bank_connections
                SET connection_status = %s
                WHERE id = %s
            ''', (status, connection_id))
            conn.commit()
            return cursor.rowcount > 0


def update_connection_last_synced(connection_id, timestamp):
    """Update the last sync timestamp for a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bank_connections
                SET last_synced_at = %s
                WHERE id = %s
            ''', (timestamp, connection_id))
            conn.commit()
            return cursor.rowcount > 0


def update_connection_tokens(connection_id, access_token, refresh_token, expires_at):
    """Update tokens for a TrueLayer bank connection (after refresh)."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bank_connections
                SET access_token = %s, refresh_token = %s, token_expires_at = %s
                WHERE id = %s
            ''', (access_token, refresh_token, expires_at, connection_id))
            conn.commit()
            return cursor.rowcount > 0


def update_account_last_synced(account_id, timestamp):
    """Update the last sync timestamp for a specific TrueLayer account."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_accounts
                SET last_synced_at = %s, updated_at = NOW()
                WHERE id = %s
            ''', (timestamp, account_id))
            conn.commit()
            return cursor.rowcount > 0


def save_connection_account(connection_id, account_id, display_name, account_type, account_subtype=None, currency=None):
    """Save an account linked to a TrueLayer bank connection."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_accounts
                (connection_id, account_id, display_name, account_type, currency)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (connection_id, account_id) DO UPDATE
                SET display_name = EXCLUDED.display_name, account_type = EXCLUDED.account_type, updated_at = NOW()
                RETURNING id
            ''', (connection_id, account_id, display_name, account_type, currency))
            account_db_id = cursor.fetchone()[0]
            conn.commit()
            return account_db_id


def get_truelayer_transaction_by_id(normalised_provider_id):
    """Check if a TrueLayer transaction already exists (deduplication)."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT id, account_id, normalised_provider_id, timestamp,
                       description, amount, merchant_name, category
                FROM truelayer_transactions
                WHERE normalised_provider_id = %s
            ''', (normalised_provider_id,))
            return cursor.fetchone()


def insert_truelayer_transaction(account_id, transaction_id, normalised_provider_id,
                                 timestamp, description, amount, currency, transaction_type,
                                 transaction_category, merchant_name, running_balance, metadata):
    """Insert a new transaction from TrueLayer."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            try:
                cursor.execute('''
                    INSERT INTO truelayer_transactions
                    (account_id, transaction_id, normalised_provider_id, timestamp,
                     description, amount, currency, transaction_type, category,
                     merchant_name, running_balance, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (account_id, transaction_id, normalised_provider_id, timestamp,
                      description, amount, currency, transaction_type, transaction_category,
                      merchant_name, running_balance, str(metadata)))
                txn_id = cursor.fetchone()[0]
                conn.commit()
                return txn_id
            except Exception as e:
                conn.rollback()
                print(f"Error inserting TrueLayer transaction: {e}")
                return None


def get_all_truelayer_transactions(account_id=None):
    """Get all transactions synced from TrueLayer."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if account_id:
                cursor.execute('''
                    SELECT id, account_id, transaction_id, normalised_provider_id,
                           timestamp, description, amount, currency, transaction_type,
                           category, merchant_name, running_balance, metadata, created_at
                    FROM truelayer_transactions
                    WHERE account_id = %s
                    ORDER BY timestamp DESC
                ''', (account_id,))
            else:
                cursor.execute('''
                    SELECT id, account_id, transaction_id, normalised_provider_id,
                           timestamp, description, amount, currency, transaction_type,
                           category, merchant_name, running_balance, metadata, created_at
                    FROM truelayer_transactions
                    ORDER BY timestamp DESC
                ''')
            return cursor.fetchall()


def insert_webhook_event(event_id, event_type, payload, signature=None, processed=False):
    """Store an incoming TrueLayer webhook event for audit trail."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_webhook_events
                (event_id, event_type, payload, signature, processed)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            ''', (event_id, event_type, str(payload), signature, processed))
            webhook_id = cursor.fetchone()[0]
            conn.commit()
            return webhook_id


def mark_webhook_processed(event_id):
    """Mark a webhook event as processed."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE truelayer_webhook_events
                SET processed = true, processed_at = NOW()
                WHERE event_id = %s
            ''', (event_id,))
            conn.commit()
            return cursor.rowcount > 0


def get_webhook_events(processed_only=False):
    """Get webhook events from database."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if processed_only:
                cursor.execute('''
                    SELECT id, event_id, event_type, payload, signature,
                           processed, created_at, processed_at
                    FROM truelayer_webhook_events
                    WHERE processed = true
                    ORDER BY created_at DESC
                    LIMIT 100
                ''')
            else:
                cursor.execute('''
                    SELECT id, event_id, event_type, payload, signature,
                           processed, created_at, processed_at
                    FROM truelayer_webhook_events
                    ORDER BY created_at DESC
                    LIMIT 100
                ''')
            return cursor.fetchall()


def insert_balance_snapshot(account_id, current_balance, currency, snapshot_at):
    """Store a balance snapshot from TrueLayer."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO truelayer_balance_snapshots
                (account_id, current_balance, currency, snapshot_at)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            ''', (account_id, current_balance, currency, snapshot_at))
            snapshot_id = cursor.fetchone()[0]
            conn.commit()
            return snapshot_id


def get_latest_balance_snapshots(account_id=None, limit=10):
    """Get the latest balance snapshots."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if account_id:
                cursor.execute('''
                    SELECT id, account_id, current_balance, currency, snapshot_at
                    FROM truelayer_balance_snapshots
                    WHERE account_id = %s
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                ''', (account_id, limit))
            else:
                cursor.execute('''
                    SELECT id, account_id, current_balance, currency, snapshot_at
                    FROM truelayer_balance_snapshots
                    ORDER BY snapshot_at DESC
                    LIMIT %s
                ''', (limit,))
            return cursor.fetchall()


def store_oauth_state(user_id, state, code_verifier):
    """Store OAuth state and code_verifier temporarily for callback verification."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO oauth_state (user_id, state, code_verifier, expires_at)
                VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')
                ON CONFLICT (state) DO UPDATE SET
                  code_verifier = EXCLUDED.code_verifier,
                  expires_at = EXCLUDED.expires_at
            ''', (user_id, state, code_verifier))
            conn.commit()


def get_oauth_state(state):
    """Retrieve stored OAuth state and code_verifier."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT user_id, state, code_verifier
                FROM oauth_state
                WHERE state = %s AND expires_at > NOW()
            ''', (state,))
            return cursor.fetchone()


def delete_oauth_state(state):
    """Delete OAuth state after use."""
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM oauth_state WHERE state = %s', (state,))
            conn.commit()


# Initialize connection pool on import
init_pool()
