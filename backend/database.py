import sqlite3
from contextlib import contextmanager

DATABASE_PATH = 'finance.db'


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize database schema."""
    with get_db() as conn:
        c = conn.cursor()

        # Transactions table
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT DEFAULT 'Other',
                source_file TEXT,
                merchant TEXT,
                huququllah_classification TEXT CHECK(huququllah_classification IN ('essential', 'discretionary', NULL)),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Categories table
        c.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                rule_pattern TEXT,
                ai_suggested BOOLEAN DEFAULT 0
            )
        ''')

        # Category keywords table - stores custom keyword rules
        c.execute('''
            CREATE TABLE IF NOT EXISTS category_keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_name TEXT NOT NULL,
                keyword TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(category_name, keyword)
            )
        ''')

        # Account mappings table - maps account details to friendly names
        c.execute('''
            CREATE TABLE IF NOT EXISTS account_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sort_code TEXT NOT NULL,
                account_number TEXT NOT NULL,
                friendly_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sort_code, account_number)
            )
        ''')

        # Amazon orders table - stores imported Amazon order history
        c.execute('''
            CREATE TABLE IF NOT EXISTS amazon_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                order_date TEXT NOT NULL,
                website TEXT NOT NULL,
                currency TEXT NOT NULL,
                total_owed REAL NOT NULL,
                product_names TEXT NOT NULL,
                order_status TEXT,
                shipment_status TEXT,
                source_file TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Amazon transaction matches table - tracks which transactions matched to orders
        c.execute('''
            CREATE TABLE IF NOT EXISTS amazon_transaction_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL,
                amazon_order_id INTEGER NOT NULL,
                match_confidence REAL NOT NULL,
                matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transaction_id) REFERENCES transactions(id),
                FOREIGN KEY (amazon_order_id) REFERENCES amazon_orders(id),
                UNIQUE(transaction_id)
            )
        ''')

        # Amazon returns table - stores imported return/refund data
        c.execute('''
            CREATE TABLE IF NOT EXISTS amazon_returns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                reversal_id TEXT UNIQUE NOT NULL,
                refund_completion_date TEXT NOT NULL,
                currency TEXT NOT NULL,
                amount_refunded REAL NOT NULL,
                status TEXT,
                disbursement_type TEXT,
                source_file TEXT,
                original_transaction_id INTEGER,
                refund_transaction_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (original_transaction_id) REFERENCES transactions(id),
                FOREIGN KEY (refund_transaction_id) REFERENCES transactions(id)
            )
        ''')

        # Apple transactions table - stores imported Apple/App Store purchases
        c.execute('''
            CREATE TABLE IF NOT EXISTS apple_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE NOT NULL,
                order_date TEXT NOT NULL,
                total_amount REAL NOT NULL,
                currency TEXT NOT NULL,
                app_names TEXT NOT NULL,
                publishers TEXT,
                item_count INTEGER DEFAULT 1,
                source_file TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Apple transaction matches table - tracks which transactions matched to Apple purchases
        c.execute('''
            CREATE TABLE IF NOT EXISTS apple_transaction_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apple_transaction_id INTEGER NOT NULL,
                bank_transaction_id INTEGER NOT NULL,
                confidence INTEGER NOT NULL,
                matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (apple_transaction_id) REFERENCES apple_transactions(id),
                FOREIGN KEY (bank_transaction_id) REFERENCES transactions(id),
                UNIQUE(bank_transaction_id)
            )
        ''')

        # Seed default categories
        default_categories = [
            'Groceries', 'Transport', 'Dining', 'Entertainment',
            'Utilities', 'Shopping', 'Health', 'Income', 'Other'
        ]

        for cat in default_categories:
            c.execute('INSERT OR IGNORE INTO categories (name) VALUES (?)', (cat,))

        conn.commit()
        print("✓ Database initialized successfully")


def get_all_transactions():
    """Get all transactions from database."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, date, description, amount, category, source_file, merchant, huququllah_classification, created_at
            FROM transactions
            ORDER BY date DESC
        ''')
        rows = c.fetchall()
        return [dict(row) for row in rows]


def add_transaction(date, description, amount, category='Other', source_file=None, merchant=None):
    """Add a single transaction to database."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO transactions (date, description, amount, category, source_file, merchant)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (date, description, amount, category, source_file, merchant))
        conn.commit()
        return c.lastrowid


def get_all_categories():
    """Get all categories from database."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, rule_pattern, ai_suggested FROM categories')
        rows = c.fetchall()
        return [dict(row) for row in rows]


def get_transaction_by_id(transaction_id):
    """
    Get a single transaction by ID.

    Args:
        transaction_id: ID of the transaction

    Returns:
        Transaction dictionary or None if not found
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, date, description, amount, category, source_file, merchant, huququllah_classification, created_at
            FROM transactions
            WHERE id = ?
        ''', (transaction_id,))
        row = c.fetchone()
        return dict(row) if row else None


def get_transactions_by_merchant(merchant):
    """
    Get all transactions from a specific merchant.

    Args:
        merchant: Merchant name to search for

    Returns:
        List of transaction dictionaries
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, date, description, amount, category, source_file, merchant, huququllah_classification, created_at
            FROM transactions
            WHERE merchant = ?
            ORDER BY date DESC
        ''', (merchant,))
        rows = c.fetchall()
        return [dict(row) for row in rows]


def update_transaction_category(transaction_id, category):
    """
    Update the category of a specific transaction.

    Args:
        transaction_id: ID of the transaction
        category: New category name

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE transactions
            SET category = ?
            WHERE id = ?
        ''', (category, transaction_id))
        conn.commit()
        return c.rowcount > 0


def update_transactions_by_merchant(merchant, category):
    """
    Update the category for all transactions from a specific merchant.

    Args:
        merchant: Merchant name
        category: New category name

    Returns:
        Number of transactions updated
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE transactions
            SET category = ?
            WHERE merchant = ?
        ''', (category, merchant))
        conn.commit()
        return c.rowcount


def clear_all_transactions():
    """
    Delete all transactions from the database.
    Useful for testing and resetting imports.

    Returns:
        Number of transactions deleted
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM transactions')
        count = c.fetchone()[0]
        c.execute('DELETE FROM transactions')
        conn.commit()
        return count


def get_category_keywords():
    """
    Get all custom keywords from database grouped by category.

    Returns:
        Dictionary of category_name -> list of keywords
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT category_name, keyword FROM category_keywords ORDER BY category_name, keyword')
        rows = c.fetchall()

        keywords_by_category = {}
        for row in rows:
            category = row['category_name']
            keyword = row['keyword']
            if category not in keywords_by_category:
                keywords_by_category[category] = []
            keywords_by_category[category].append(keyword)

        return keywords_by_category


def add_category_keyword(category_name, keyword):
    """
    Add a keyword to a category.

    Args:
        category_name: Category name
        keyword: Keyword to add

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO category_keywords (category_name, keyword)
                VALUES (?, ?)
            ''', (category_name, keyword.lower()))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Keyword already exists for this category
            return False


def remove_category_keyword(category_name, keyword):
    """
    Remove a keyword from a category.

    Args:
        category_name: Category name
        keyword: Keyword to remove

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            DELETE FROM category_keywords
            WHERE category_name = ? AND keyword = ?
        ''', (category_name, keyword.lower()))
        conn.commit()
        return c.rowcount > 0


def create_custom_category(name):
    """
    Create a new custom category.

    Args:
        name: Category name

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('INSERT INTO categories (name) VALUES (?)', (name,))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Category already exists
            return False


def delete_custom_category(name):
    """
    Delete a custom category and all its keywords.

    Args:
        name: Category name

    Returns:
        Boolean indicating success
    """
    # Don't allow deletion of default categories
    default_categories = [
        'Groceries', 'Transport', 'Dining', 'Entertainment',
        'Utilities', 'Shopping', 'Health', 'Income', 'Other'
    ]

    if name in default_categories:
        return False

    with get_db() as conn:
        c = conn.cursor()
        # Delete keywords first
        c.execute('DELETE FROM category_keywords WHERE category_name = ?', (name,))
        # Delete category
        c.execute('DELETE FROM categories WHERE name = ?', (name,))
        conn.commit()
        return c.rowcount > 0


def bulk_update_transaction_categories(transaction_ids, category):
    """
    Update category for multiple transactions.

    Args:
        transaction_ids: List of transaction IDs
        category: New category name

    Returns:
        Number of transactions updated
    """
    with get_db() as conn:
        c = conn.cursor()
        placeholders = ','.join('?' * len(transaction_ids))
        c.execute(f'''
            UPDATE transactions
            SET category = ?
            WHERE id IN ({placeholders})
        ''', [category] + transaction_ids)
        conn.commit()
        return c.rowcount


def get_all_account_mappings():
    """
    Get all account mappings from database.

    Returns:
        List of account mapping dictionaries
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, sort_code, account_number, friendly_name, created_at
            FROM account_mappings
            ORDER BY friendly_name
        ''')
        rows = c.fetchall()
        return [dict(row) for row in rows]


def add_account_mapping(sort_code, account_number, friendly_name):
    """
    Add a new account mapping.

    Args:
        sort_code: Bank sort code (6 digits)
        account_number: Bank account number (8 digits)
        friendly_name: Human-readable name for this account

    Returns:
        ID of created mapping or None if duplicate
    """
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO account_mappings (sort_code, account_number, friendly_name)
                VALUES (?, ?, ?)
            ''', (sort_code, account_number, friendly_name))
            conn.commit()
            return c.lastrowid
        except sqlite3.IntegrityError:
            # Duplicate account mapping
            return None


def update_account_mapping(mapping_id, friendly_name):
    """
    Update the friendly name for an account mapping.

    Args:
        mapping_id: ID of the mapping
        friendly_name: New friendly name

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE account_mappings
            SET friendly_name = ?
            WHERE id = ?
        ''', (friendly_name, mapping_id))
        conn.commit()
        return c.rowcount > 0


def delete_account_mapping(mapping_id):
    """
    Delete an account mapping.

    Args:
        mapping_id: ID of the mapping

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM account_mappings WHERE id = ?', (mapping_id,))
        conn.commit()
        return c.rowcount > 0


def get_account_mapping_by_details(sort_code, account_number):
    """
    Look up account mapping by sort code and account number.

    Args:
        sort_code: Bank sort code (6 digits)
        account_number: Bank account number (8 digits)

    Returns:
        Account mapping dictionary or None if not found
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, sort_code, account_number, friendly_name, created_at
            FROM account_mappings
            WHERE sort_code = ? AND account_number = ?
        ''', (sort_code, account_number))
        row = c.fetchone()
        return dict(row) if row else None


def update_transaction_huququllah(transaction_id, classification):
    """
    Update the Huququllah classification of a specific transaction.

    Args:
        transaction_id: ID of the transaction
        classification: 'essential', 'discretionary', or None

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE transactions
            SET huququllah_classification = ?
            WHERE id = ?
        ''', (classification, transaction_id))
        conn.commit()
        return c.rowcount > 0


def get_unclassified_transactions():
    """
    Get all expense transactions that have not been classified for Huququllah.
    Only returns expenses (negative amounts) as income should not be classified.

    Returns:
        List of transaction dictionaries where huququllah_classification is NULL and amount < 0
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT id, date, description, amount, category, source_file, merchant, huququllah_classification, created_at
            FROM transactions
            WHERE huququllah_classification IS NULL AND amount < 0
            ORDER BY date DESC
        ''')
        rows = c.fetchall()
        return [dict(row) for row in rows]


def get_huququllah_summary(date_from=None, date_to=None):
    """
    Get summary of essential vs discretionary spending for Huququllah calculation.
    Huququllah is calculated as 19% of discretionary expenses only.

    Args:
        date_from: Optional start date filter (YYYY-MM-DD)
        date_to: Optional end date filter (YYYY-MM-DD)

    Returns:
        Dictionary with essential_expenses, discretionary_expenses, huququllah_due, unclassified_count
    """
    with get_db() as conn:
        c = conn.cursor()

        # Build query with optional date filters - only consider expenses (amount < 0)
        query = '''
            SELECT
                SUM(CASE WHEN amount < 0 AND huququllah_classification = 'essential' THEN ABS(amount) ELSE 0 END) as essential_expenses,
                SUM(CASE WHEN amount < 0 AND huququllah_classification = 'discretionary' THEN ABS(amount) ELSE 0 END) as discretionary_expenses,
                COUNT(CASE WHEN huququllah_classification IS NULL AND amount < 0 THEN 1 END) as unclassified_count
            FROM transactions
            WHERE 1=1
        '''
        params = []

        if date_from:
            query += ' AND date >= ?'
            params.append(date_from)

        if date_to:
            query += ' AND date <= ?'
            params.append(date_to)

        c.execute(query, params)
        row = c.fetchone()

        if row:
            essential = row['essential_expenses'] or 0
            discretionary = row['discretionary_expenses'] or 0
            unclassified = row['unclassified_count'] or 0
            huququllah = discretionary * 0.19  # 19% of discretionary spending

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


def migrate_add_huququllah_column():
    """
    Migration to add huququllah_classification column to existing databases.
    This is safe to run multiple times - it will only add the column if it doesn't exist.

    Returns:
        Boolean indicating whether migration was needed and executed
    """
    with get_db() as conn:
        c = conn.cursor()

        # Check if column already exists
        c.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in c.fetchall()]

        if 'huququllah_classification' not in columns:
            # Add the column
            c.execute('''
                ALTER TABLE transactions
                ADD COLUMN huququllah_classification TEXT CHECK(huququllah_classification IN ('essential', 'discretionary', NULL))
            ''')
            conn.commit()
            print("✓ Added huququllah_classification column to transactions table")
            return True

        return False


# ============================================================================
# Amazon Order Management Functions
# ============================================================================

def import_amazon_orders(orders, source_file):
    """
    Bulk import Amazon orders into database.

    Args:
        orders: List of order dictionaries
        source_file: Name of the source CSV file

    Returns:
        Tuple of (imported_count, duplicate_count)
    """
    with get_db() as conn:
        c = conn.cursor()
        imported = 0
        duplicates = 0

        for order in orders:
            try:
                c.execute('''
                    INSERT INTO amazon_orders
                    (order_id, order_date, website, currency, total_owed,
                     product_names, order_status, shipment_status, source_file)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            except sqlite3.IntegrityError:
                # Order ID already exists
                duplicates += 1
                continue

        conn.commit()
        return (imported, duplicates)


def get_amazon_orders(date_from=None, date_to=None, website=None):
    """
    Get Amazon orders with optional filters.

    Args:
        date_from: Optional start date filter (YYYY-MM-DD)
        date_to: Optional end date filter (YYYY-MM-DD)
        website: Optional website filter (e.g., 'Amazon.co.uk')

    Returns:
        List of order dictionaries
    """
    with get_db() as conn:
        c = conn.cursor()

        query = 'SELECT * FROM amazon_orders WHERE 1=1'
        params = []

        if date_from:
            query += ' AND order_date >= ?'
            params.append(date_from)

        if date_to:
            query += ' AND order_date <= ?'
            params.append(date_to)

        if website:
            query += ' AND website = ?'
            params.append(website)

        query += ' ORDER BY order_date DESC'

        c.execute(query, params)
        rows = c.fetchall()
        return [dict(row) for row in rows]


def get_amazon_order_by_id(order_id):
    """
    Get a single Amazon order by its Amazon order ID.

    Args:
        order_id: Amazon order ID string

    Returns:
        Order dictionary or None if not found
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM amazon_orders WHERE order_id = ?', (order_id,))
        row = c.fetchone()
        return dict(row) if row else None


def match_amazon_transaction(transaction_id, amazon_order_db_id, confidence):
    """
    Record a match between a transaction and an Amazon order.

    Args:
        transaction_id: ID of the bank transaction
        amazon_order_db_id: Database ID of the Amazon order
        confidence: Match confidence score (0-100)

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('''
                INSERT OR REPLACE INTO amazon_transaction_matches
                (transaction_id, amazon_order_id, match_confidence)
                VALUES (?, ?, ?)
            ''', (transaction_id, amazon_order_db_id, confidence))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error matching transaction: {e}")
            return False


def get_amazon_match_for_transaction(transaction_id):
    """
    Get the Amazon order match for a transaction if it exists.

    Args:
        transaction_id: ID of the transaction

    Returns:
        Dictionary with match and order info, or None if no match
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT
                m.id as match_id,
                m.match_confidence,
                m.matched_at,
                o.*
            FROM amazon_transaction_matches m
            JOIN amazon_orders o ON m.amazon_order_id = o.id
            WHERE m.transaction_id = ?
        ''', (transaction_id,))
        row = c.fetchone()
        return dict(row) if row else None


def get_unmatched_amazon_transactions():
    """
    Get all transactions with Amazon merchant that haven't been matched to orders.

    Returns:
        List of transaction dictionaries
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
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
        rows = c.fetchall()
        return [dict(row) for row in rows]


def check_amazon_coverage(date_from, date_to):
    """
    Check if Amazon order data exists for a date range.
    Returns info about coverage gaps.

    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)

    Returns:
        Dictionary with coverage info
    """
    with get_db() as conn:
        c = conn.cursor()

        # Count Amazon transactions in range
        c.execute('''
            SELECT COUNT(*) as count
            FROM transactions
            WHERE date >= ? AND date <= ?
            AND (
                UPPER(merchant) LIKE '%AMAZON%'
                OR UPPER(merchant) LIKE '%AMZN%'
                OR UPPER(description) LIKE '%AMAZON%'
                OR UPPER(description) LIKE '%AMZN%'
            )
        ''', (date_from, date_to))
        amazon_txn_count = c.fetchone()['count']

        # Count Amazon orders in range (with ±3 day buffer)
        c.execute('''
            SELECT COUNT(*) as count
            FROM amazon_orders
            WHERE date(order_date) >= date(?, '-3 days')
            AND date(order_date) <= date(?, '+3 days')
        ''', (date_from, date_to))
        amazon_order_count = c.fetchone()['count']

        # Count matched transactions
        c.execute('''
            SELECT COUNT(*) as count
            FROM transactions t
            JOIN amazon_transaction_matches m ON t.id = m.transaction_id
            WHERE t.date >= ? AND t.date <= ?
        ''', (date_from, date_to))
        matched_count = c.fetchone()['count']

        return {
            'amazon_transactions': amazon_txn_count,
            'amazon_orders_available': amazon_order_count,
            'matched_count': matched_count,
            'has_coverage': amazon_order_count > 0,
            'match_rate': (matched_count / amazon_txn_count * 100) if amazon_txn_count > 0 else 0
        }


def get_amazon_statistics():
    """
    Get overall Amazon import and matching statistics.

    Returns:
        Dictionary with statistics
    """
    with get_db() as conn:
        c = conn.cursor()

        # Total orders imported
        c.execute('SELECT COUNT(*) as count FROM amazon_orders')
        total_orders = c.fetchone()['count']

        # Date range of orders
        c.execute('SELECT MIN(order_date) as min_date, MAX(order_date) as max_date FROM amazon_orders')
        date_range = c.fetchone()

        # Total matched transactions
        c.execute('SELECT COUNT(*) as count FROM amazon_transaction_matches')
        total_matched = c.fetchone()['count']

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
    """
    Delete all Amazon orders and matches from database.
    Useful for testing and reimporting.

    Returns:
        Tuple of (orders_deleted, matches_deleted)
    """
    with get_db() as conn:
        c = conn.cursor()

        # Count before deletion
        c.execute('SELECT COUNT(*) FROM amazon_orders')
        orders_count = c.fetchone()[0]

        c.execute('SELECT COUNT(*) FROM amazon_transaction_matches')
        matches_count = c.fetchone()[0]

        # Delete matches first (foreign key)
        c.execute('DELETE FROM amazon_transaction_matches')

        # Delete orders
        c.execute('DELETE FROM amazon_orders')

        conn.commit()
        return (orders_count, matches_count)


def update_transaction_description(transaction_id, new_description):
    """
    Update the description of a transaction.
    Used when enriching with Amazon product names.

    Args:
        transaction_id: ID of the transaction
        new_description: New description text

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE transactions
            SET description = ?
            WHERE id = ?
        ''', (new_description, transaction_id))
        conn.commit()
        return c.rowcount > 0


# ============================================================================
# Amazon Returns Management Functions
# ============================================================================

def import_amazon_returns(returns, source_file):
    """
    Bulk import Amazon returns into database.

    Args:
        returns: List of return dictionaries
        source_file: Name of the source CSV file

    Returns:
        Tuple of (imported_count, duplicate_count)
    """
    with get_db() as conn:
        c = conn.cursor()
        imported = 0
        duplicates = 0

        for ret in returns:
            try:
                c.execute('''
                    INSERT INTO amazon_returns
                    (order_id, reversal_id, refund_completion_date, currency, amount_refunded,
                     status, disbursement_type, source_file)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            except sqlite3.IntegrityError:
                # Reversal ID already exists
                duplicates += 1
                continue

        conn.commit()
        return (imported, duplicates)


def get_amazon_returns(order_id=None):
    """
    Get Amazon returns with optional order ID filter.

    Args:
        order_id: Optional order ID filter

    Returns:
        List of return dictionaries
    """
    with get_db() as conn:
        c = conn.cursor()

        if order_id:
            c.execute('SELECT * FROM amazon_returns WHERE order_id = ?', (order_id,))
        else:
            c.execute('SELECT * FROM amazon_returns ORDER BY refund_completion_date DESC')

        rows = c.fetchall()
        return [dict(row) for row in rows]


def link_return_to_transactions(return_id, original_transaction_id, refund_transaction_id):
    """
    Link a return to its original purchase and refund transactions.

    Args:
        return_id: Database ID of the return
        original_transaction_id: ID of original purchase transaction
        refund_transaction_id: ID of refund transaction

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE amazon_returns
            SET original_transaction_id = ?,
                refund_transaction_id = ?
            WHERE id = ?
        ''', (original_transaction_id, refund_transaction_id, return_id))
        conn.commit()
        return c.rowcount > 0


def mark_transaction_as_returned(transaction_id):
    """
    Mark a transaction as returned by updating its description with a label.

    Args:
        transaction_id: ID of the transaction

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()

        # Get current description
        c.execute('SELECT description FROM transactions WHERE id = ?', (transaction_id,))
        row = c.fetchone()

        if not row:
            return False

        current_desc = row['description']

        # Add [RETURNED] prefix if not already there
        if not current_desc.startswith('[RETURNED] '):
            new_desc = f'[RETURNED] {current_desc}'
            c.execute('''
                UPDATE transactions
                SET description = ?
                WHERE id = ?
            ''', (new_desc, transaction_id))
            conn.commit()
            return True

        return False


def get_returns_statistics():
    """
    Get overall returns import and matching statistics.

    Returns:
        Dictionary with statistics
    """
    with get_db() as conn:
        c = conn.cursor()

        # Total returns imported
        c.execute('SELECT COUNT(*) as count FROM amazon_returns')
        total_returns = c.fetchone()['count']

        # Date range of returns
        c.execute('SELECT MIN(refund_completion_date) as min_date, MAX(refund_completion_date) as max_date FROM amazon_returns')
        date_range = c.fetchone()

        # Total amount refunded
        c.execute('SELECT SUM(amount_refunded) as total FROM amazon_returns')
        total_refunded = c.fetchone()['total'] or 0

        # Matched returns (those linked to transactions)
        c.execute('SELECT COUNT(*) as count FROM amazon_returns WHERE original_transaction_id IS NOT NULL')
        matched_returns = c.fetchone()['count']

        return {
            'total_returns': total_returns,
            'min_return_date': date_range['min_date'],
            'max_return_date': date_range['max_date'],
            'total_refunded': round(total_refunded, 2),
            'matched_returns': matched_returns,
            'unmatched_returns': total_returns - matched_returns
        }


def clear_amazon_returns():
    """
    Delete all Amazon returns from database.
    Also removes [RETURNED] labels from transactions.

    Returns:
        Number of returns deleted
    """
    with get_db() as conn:
        c = conn.cursor()

        # Get all transactions marked as returned
        c.execute('SELECT id, description FROM transactions WHERE description LIKE "[RETURNED] %"')
        returned_txns = c.fetchall()

        # Remove [RETURNED] prefix
        for txn in returned_txns:
            new_desc = txn['description'].replace('[RETURNED] ', '', 1)
            c.execute('UPDATE transactions SET description = ? WHERE id = ?', (new_desc, txn['id']))

        # Count before deletion
        c.execute('SELECT COUNT(*) FROM amazon_returns')
        count = c.fetchone()[0]

        # Delete returns
        c.execute('DELETE FROM amazon_returns')

        conn.commit()
        return count


# ============================================================================
# Apple Transactions Functions
# ============================================================================

def import_apple_transactions(transactions, source_file):
    """
    Bulk import Apple transactions from parsed HTML data.

    Args:
        transactions: List of transaction dictionaries
        source_file: Name of source HTML file

    Returns:
        Tuple of (imported_count, duplicates_count)
    """
    with get_db() as conn:
        c = conn.cursor()
        imported = 0
        duplicates = 0

        for txn in transactions:
            try:
                c.execute('''
                    INSERT INTO apple_transactions (
                        order_id, order_date, total_amount, currency,
                        app_names, publishers, item_count, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            except sqlite3.IntegrityError:
                # Duplicate order_id
                duplicates += 1

        conn.commit()
        return imported, duplicates


def get_apple_transactions(date_from=None, date_to=None):
    """
    Get all Apple transactions, optionally filtered by date range.

    Args:
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)

    Returns:
        List of Apple transaction dictionaries with matched_bank_transaction_id
    """
    with get_db() as conn:
        c = conn.cursor()

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
            query += ' AND a.order_date >= ?'
            params.append(date_from)

        if date_to:
            query += ' AND a.order_date <= ?'
            params.append(date_to)

        query += ' ORDER BY a.order_date DESC'

        c.execute(query, params)
        rows = c.fetchall()
        return [dict(row) for row in rows]


def get_apple_transaction_by_id(order_id):
    """
    Get a specific Apple transaction by order ID.

    Args:
        order_id: Apple order ID (database ID)

    Returns:
        Apple transaction dictionary or None
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM apple_transactions WHERE id = ?', (order_id,))
        row = c.fetchone()
        return dict(row) if row else None


def match_apple_transaction(bank_transaction_id, apple_transaction_db_id, confidence):
    """
    Record a match between a bank transaction and an Apple purchase.

    Args:
        bank_transaction_id: ID of bank transaction
        apple_transaction_db_id: Database ID of Apple transaction
        confidence: Match confidence percentage (0-100)

    Returns:
        Match ID
    """
    with get_db() as conn:
        c = conn.cursor()

        # Check if transaction already matched
        c.execute('''
            SELECT id FROM apple_transaction_matches
            WHERE bank_transaction_id = ?
        ''', (bank_transaction_id,))

        existing = c.fetchone()
        if existing:
            # Update existing match
            c.execute('''
                UPDATE apple_transaction_matches
                SET apple_transaction_id = ?, confidence = ?, matched_at = CURRENT_TIMESTAMP
                WHERE bank_transaction_id = ?
            ''', (apple_transaction_db_id, confidence, bank_transaction_id))
            conn.commit()
            return existing['id']
        else:
            # Insert new match
            c.execute('''
                INSERT INTO apple_transaction_matches (
                    bank_transaction_id, apple_transaction_id, confidence
                ) VALUES (?, ?, ?)
            ''', (bank_transaction_id, apple_transaction_db_id, confidence))
            conn.commit()
            return c.lastrowid


def get_apple_statistics():
    """
    Get statistics about imported Apple transactions.

    Returns:
        Dictionary with statistics
    """
    with get_db() as conn:
        c = conn.cursor()

        # Total transactions
        c.execute('SELECT COUNT(*) FROM apple_transactions')
        total = c.fetchone()[0]

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
        c.execute('SELECT MIN(order_date), MAX(order_date) FROM apple_transactions')
        min_date, max_date = c.fetchone()

        # Total spent
        c.execute('SELECT SUM(total_amount) FROM apple_transactions')
        total_spent = c.fetchone()[0] or 0

        # Matched count
        c.execute('SELECT COUNT(*) FROM apple_transaction_matches')
        matched = c.fetchone()[0]

        return {
            'total_transactions': total,
            'min_transaction_date': min_date,
            'max_transaction_date': max_date,
            'total_spent': total_spent,
            'matched_transactions': matched,
            'unmatched_transactions': total - matched
        }


def clear_apple_transactions():
    """
    Delete all Apple transactions from database.

    Returns:
        Number of transactions deleted
    """
    with get_db() as conn:
        c = conn.cursor()

        # Count before deletion
        c.execute('SELECT COUNT(*) FROM apple_transactions')
        count = c.fetchone()[0]

        # Delete matches first (foreign key constraint)
        c.execute('DELETE FROM apple_transaction_matches')

        # Delete transactions
        c.execute('DELETE FROM apple_transactions')

        conn.commit()
        return count
