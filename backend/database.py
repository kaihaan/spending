import sqlite3
from contextlib import contextmanager
from typing import Optional

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

        # Transactions table - stores original data from bank imports only
        c.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                source_file TEXT,
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

        # Merchants table - stores merchant to category mappings
        c.execute('''
            CREATE TABLE IF NOT EXISTS merchants (
                merchant_name TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

        # Transaction Enrichments table - stores all LLM enrichment data
        c.execute('''
            CREATE TABLE IF NOT EXISTS transaction_enrichments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER NOT NULL UNIQUE,
                primary_category TEXT,
                subcategory TEXT,
                merchant_clean_name TEXT,
                merchant_type TEXT,
                essential_discretionary TEXT CHECK(essential_discretionary IN ('Essential', 'Discretionary', NULL)),
                payment_method TEXT,
                payment_method_subtype TEXT,
                payee TEXT,
                purchase_date TEXT,
                confidence_score REAL,
                raw_response TEXT,
                llm_provider TEXT,
                llm_model TEXT,
                enrichment_source TEXT CHECK(enrichment_source IN ('lookup', 'llm', 'regex', 'manual', NULL)),
                enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
            )
        ''')

        # LLM Enrichment Cache table - stores enriched data to avoid re-querying
        c.execute('''
            CREATE TABLE IF NOT EXISTS llm_enrichment_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_description TEXT NOT NULL UNIQUE,
                direction TEXT NOT NULL CHECK(direction IN ('in', 'out')),
                primary_category TEXT,
                subcategory TEXT,
                merchant_clean_name TEXT,
                merchant_type TEXT,
                essential_discretionary TEXT,
                payment_method TEXT,
                payment_method_subtype TEXT,
                payee TEXT,
                purchase_date TEXT,
                confidence_score REAL,
                llm_provider TEXT,
                llm_model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # LLM Enrichment Failures table - tracks failed enrichment attempts
        c.execute('''
            CREATE TABLE IF NOT EXISTS llm_enrichment_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_id INTEGER,
                transaction_description TEXT NOT NULL,
                error_type TEXT,
                error_message TEXT,
                llm_provider TEXT,
                attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending_retry' CHECK(status IN ('pending_retry', 'ignored', 'manual_review')),
                FOREIGN KEY (transaction_id) REFERENCES transactions(id)
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

    # Run migrations
    add_lookup_description_column()
    add_transaction_pattern_columns()
    add_enrichment_source_column()
    populate_lookup_descriptions()
    create_llm_model_config_table()


def get_all_transactions():
    """Get all transactions from database with their LLM enrichment data."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT
                t.id, t.date, t.description, t.amount, t.source_file, t.created_at,
                te.primary_category as category,
                te.merchant_clean_name,
                te.subcategory,
                te.merchant_type,
                te.essential_discretionary,
                te.payment_method,
                te.payment_method_subtype,
                te.payee,
                te.purchase_date,
                te.confidence_score,
                te.enrichment_source,
                te.llm_provider,
                te.llm_model,
                t.lookup_description
            FROM transactions t
            LEFT JOIN transaction_enrichments te ON t.id = te.transaction_id
            ORDER BY t.date DESC
        ''')
        rows = c.fetchall()
        return [dict(row) for row in rows]


def add_transaction(
    date, description, amount, source_file=None, category=None, merchant=None,
    provider=None, variant=None, payee=None, reference=None, mandate_number=None,
    branch=None, entity=None, trip_date=None, sender=None, rate=None, tax=None,
    payment_count=None, extraction_confidence=None
):
    """
    Add a single transaction to database.

    Note: category and merchant parameters are deprecated - enrichment data is now
    stored in the transaction_enrichments table. These parameters are accepted for
    backwards compatibility but ignored.
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            INSERT INTO transactions (
                date, description, amount, source_file
            )
            VALUES (?, ?, ?, ?)
        ''', (date, description, amount, source_file))
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


# ============================================================================
# Merchant Management Functions
# ============================================================================

def get_all_merchants():
    """
    Get all unique merchants from transactions with their transaction counts
    and assigned categories (if any).

    Returns:
        List of dictionaries with merchant_name, transaction_count, assigned_category, and most_common_category
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT
                t.merchant,
                COUNT(*) as transaction_count,
                m.category as assigned_category,
                (
                    SELECT category FROM transactions
                    WHERE merchant = t.merchant
                    GROUP BY category
                    ORDER BY COUNT(*) DESC
                    LIMIT 1
                ) as most_common_category
            FROM transactions t
            LEFT JOIN merchants m ON t.merchant = m.merchant_name
            WHERE t.merchant IS NOT NULL AND t.merchant != ''
            GROUP BY t.merchant
            ORDER BY transaction_count DESC
        ''')
        rows = c.fetchall()
        return [dict(row) for row in rows]


def get_merchant_category(merchant_name):
    """
    Get the assigned category for a merchant.

    Args:
        merchant_name: Name of the merchant

    Returns:
        Category name or None if not assigned
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT category FROM merchants WHERE merchant_name = ?', (merchant_name,))
        row = c.fetchone()
        return row['category'] if row else None


def set_merchant_category(merchant_name, category):
    """
    Assign a category to a merchant and update all existing transactions.

    Args:
        merchant_name: Name of the merchant
        category: Category name to assign

    Returns:
        Number of transactions updated
    """
    with get_db() as conn:
        c = conn.cursor()

        # Insert or update merchant mapping
        c.execute('''
            INSERT OR REPLACE INTO merchants (merchant_name, category, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
        ''', (merchant_name, category))

        # Update all transactions from this merchant
        c.execute('''
            UPDATE transactions
            SET category = ?
            WHERE merchant = ?
        ''', (category, merchant_name))

        conn.commit()
        return c.rowcount


def delete_merchant_mapping(merchant_name):
    """
    Delete the category mapping for a merchant.

    Args:
        merchant_name: Name of the merchant

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM merchants WHERE merchant_name = ?', (merchant_name,))
        conn.commit()
        return c.rowcount > 0


def fix_paypal_merchants_preview():
    """
    Preview what PayPal merchant fixes would be applied.

    Returns:
        List of changes that would be made
    """
    import re

    transactions = get_all_transactions()
    changes = []

    for txn in transactions:
        description = txn.get('description', '')
        merchant = txn.get('merchant', '')

        if not description or 'PAYPAL' not in description.upper():
            continue

        # Extract PayPal merchant from description
        match = re.search(r'\*([A-Z0-9\s]+?)(?:\s+ON\s+\d{1,2}|\s+[A-Z]{2}(?:\s|$)|\s*$)', description, re.IGNORECASE)

        if match:
            extracted_merchant = match.group(1).strip()
            # Clean up trailing numbers
            extracted_merchant = re.sub(r'\s+\d+$', '', extracted_merchant)

            if extracted_merchant and extracted_merchant != merchant:
                changes.append({
                    'transaction_id': txn['id'],
                    'description': description[:60],
                    'current_merchant': merchant,
                    'new_merchant': extracted_merchant
                })

    return changes


def fix_paypal_merchants():
    """
    Fix PayPal transactions by extracting real merchant names from descriptions.

    Returns:
        Dictionary with fix statistics
    """
    import re

    transactions = get_all_transactions()
    fixed_count = 0
    changes = []

    with get_db() as conn:
        c = conn.cursor()

        for txn in transactions:
            description = txn.get('description', '')
            merchant = txn.get('merchant', '')

            if not description or 'PAYPAL' not in description.upper():
                continue

            # Extract PayPal merchant from description
            match = re.search(r'\*([A-Z0-9\s]+?)(?:\s+ON\s+\d{1,2}|\s+[A-Z]{2}(?:\s|$)|\s*$)', description, re.IGNORECASE)

            if match:
                extracted_merchant = match.group(1).strip()
                # Clean up trailing numbers
                extracted_merchant = re.sub(r'\s+\d+$', '', extracted_merchant)

                if extracted_merchant and extracted_merchant != merchant:
                    c.execute('''
                        UPDATE transactions
                        SET merchant = ?
                        WHERE id = ?
                    ''', (extracted_merchant, txn['id']))

                    fixed_count += 1
                    changes.append({
                        'transaction_id': txn['id'],
                        'old_merchant': merchant,
                        'new_merchant': extracted_merchant
                    })

        conn.commit()

    return {
        'success': True,
        'fixed_count': fixed_count,
        'sample_changes': changes[:20]  # Show first 20 examples
    }


def fix_via_apple_pay_merchants_preview():
    """
    Preview what VIA APPLE PAY merchant fixes would be applied.

    Returns:
        List of changes that would be made
    """
    import re

    transactions = get_all_transactions()
    changes = []

    for txn in transactions:
        description = txn.get('description', '')
        merchant = txn.get('merchant', '')

        if not description or 'VIA APPLE PAY' not in description.upper():
            continue

        # Extract VIA APPLE PAY merchant from description
        match = re.search(r'^(.+?)\s*\(VIA APPLE PAY\)', description, re.IGNORECASE)

        if match:
            extracted_merchant = match.group(1).strip()
            # Clean up trailing numbers
            extracted_merchant = re.sub(r'\s+\d+$', '', extracted_merchant)

            if extracted_merchant and extracted_merchant != merchant:
                changes.append({
                    'transaction_id': txn['id'],
                    'description': description[:60],
                    'current_merchant': merchant,
                    'new_merchant': extracted_merchant
                })

    return changes


def fix_via_apple_pay_merchants():
    """
    Fix VIA APPLE PAY transactions by extracting real merchant names from descriptions.

    Returns:
        Dictionary with fix statistics
    """
    import re

    transactions = get_all_transactions()
    fixed_count = 0
    changes = []

    with get_db() as conn:
        c = conn.cursor()

        for txn in transactions:
            description = txn.get('description', '')
            merchant = txn.get('merchant', '')

            if not description or 'VIA APPLE PAY' not in description.upper():
                continue

            # Extract VIA APPLE PAY merchant from description
            match = re.search(r'^(.+?)\s*\(VIA APPLE PAY\)', description, re.IGNORECASE)

            if match:
                extracted_merchant = match.group(1).strip()
                # Clean up trailing numbers
                extracted_merchant = re.sub(r'\s+\d+$', '', extracted_merchant)

                if extracted_merchant and extracted_merchant != merchant:
                    c.execute('''
                        UPDATE transactions
                        SET merchant = ?
                        WHERE id = ?
                    ''', (extracted_merchant, txn['id']))

                    fixed_count += 1
                    changes.append({
                        'transaction_id': txn['id'],
                        'old_merchant': merchant,
                        'new_merchant': extracted_merchant
                    })

        conn.commit()

    return {
        'success': True,
        'fixed_count': fixed_count,
        'sample_changes': changes[:20]  # Show first 20 examples
    }


def fix_zettle_merchants_preview():
    """
    Preview what Zettle merchant fixes would be applied.

    Returns:
        List of changes that would be made
    """
    import re

    transactions = get_all_transactions()
    changes = []

    for txn in transactions:
        description = txn.get('description', '')
        merchant = txn.get('merchant', '')

        if not description or 'ZETTLE' not in description.upper():
            continue

        # Extract Zettle merchant from description
        match = re.search(r'ZETTLE_\*([A-Z0-9\s]+?)(?:\s+ON\s+\d{1,2}|\s+[A-Z]{2}(?:\s|$)|\s*$)', description, re.IGNORECASE)

        if match:
            extracted_merchant = match.group(1).strip()
            # Clean up trailing numbers
            extracted_merchant = re.sub(r'\s+\d+$', '', extracted_merchant)

            if extracted_merchant and extracted_merchant != merchant:
                changes.append({
                    'transaction_id': txn['id'],
                    'description': description[:60],
                    'current_merchant': merchant,
                    'new_merchant': extracted_merchant
                })

    return changes


def fix_zettle_merchants():
    """
    Fix Zettle transactions by extracting real merchant names from descriptions.

    Returns:
        Dictionary with fix statistics
    """
    import re

    transactions = get_all_transactions()
    fixed_count = 0
    changes = []

    with get_db() as conn:
        c = conn.cursor()

        for txn in transactions:
            description = txn.get('description', '')
            merchant = txn.get('merchant', '')

            if not description or 'ZETTLE' not in description.upper():
                continue

            # Extract Zettle merchant from description
            match = re.search(r'ZETTLE_\*([A-Z0-9\s]+?)(?:\s+ON\s+\d{1,2}|\s+[A-Z]{2}(?:\s|$)|\s*$)', description, re.IGNORECASE)

            if match:
                extracted_merchant = match.group(1).strip()
                # Clean up trailing numbers
                extracted_merchant = re.sub(r'\s+\d+$', '', extracted_merchant)

                if extracted_merchant and extracted_merchant != merchant:
                    c.execute('''
                        UPDATE transactions
                        SET merchant = ?
                        WHERE id = ?
                    ''', (extracted_merchant, txn['id']))

                    fixed_count += 1
                    changes.append({
                        'transaction_id': txn['id'],
                        'old_merchant': merchant,
                        'new_merchant': extracted_merchant
                    })

        conn.commit()

    return {
        'success': True,
        'fixed_count': fixed_count,
        'sample_changes': changes[:20]  # Show first 20 examples
    }


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


def add_lookup_description_column():
    """
    Add lookup_description column to transactions table if it doesn't exist.
    This column stores product/service descriptions from lookups (Apple, Amazon, etc.).

    This is safe to run multiple times - it will only add the column if it doesn't exist.

    Returns:
        Boolean indicating whether migration was needed and executed
    """
    with get_db() as conn:
        c = conn.cursor()

        # Check if column already exists
        c.execute("PRAGMA table_info(transactions)")
        columns = [col[1] for col in c.fetchall()]

        if 'lookup_description' not in columns:
            # Add the column
            c.execute('''
                ALTER TABLE transactions
                ADD COLUMN lookup_description TEXT
            ''')
            conn.commit()
            print("✓ Added lookup_description column to transactions table")
            return True

        return False


def add_transaction_pattern_columns():
    """
    Add provider, variant, and extracted variable columns to transactions table.

    This migration adds columns for structured data extracted from transaction descriptions:
    - provider: The payment/transaction provider (Apple Pay, Card Payment, etc.)
    - variant: Sub-type or variant (e.g., AIRBNB for Card Payment, Marketplace for Amazon)
    - payee: The recipient/merchant of the transaction
    - reference: Reference code or transaction reference number
    - mandate_number: For Direct Debit transactions
    - branch: Branch or location information
    - entity: Additional entity information (e.g., number of rides)
    - trip_date: Date of a trip (for transport services)
    - sender: For transfers, the source person/entity
    - rate: Interest rate or cashback rate
    - tax: Tax amount
    - payment_count: Number of payments (for aggregated entries)
    - extraction_confidence: Confidence score of the extraction (0-100)

    This is safe to run multiple times - it will only add columns that don't exist.

    Returns:
        Dictionary with counts of added columns
    """
    with get_db() as conn:
        c = conn.cursor()

        # Check existing columns
        c.execute("PRAGMA table_info(transactions)")
        existing_columns = {col[1] for col in c.fetchall()}

        columns_to_add = {
            'provider': 'TEXT',
            'variant': 'TEXT',
            'payee': 'TEXT',
            'reference': 'TEXT',
            'mandate_number': 'TEXT',
            'branch': 'TEXT',
            'entity': 'TEXT',
            'trip_date': 'TEXT',
            'sender': 'TEXT',
            'rate': 'TEXT',
            'tax': 'TEXT',
            'payment_count': 'INTEGER',
            'extraction_confidence': 'INTEGER'
        }

        added_count = 0
        for col_name, col_type in columns_to_add.items():
            if col_name not in existing_columns:
                c.execute(f'''
                    ALTER TABLE transactions
                    ADD COLUMN {col_name} {col_type}
                ''')
                added_count += 1

        if added_count > 0:
            conn.commit()
            print(f"✓ Added {added_count} pattern extraction columns to transactions table")

        return added_count


def add_enrichment_source_column():
    """
    Add enrichment_source column to transaction_enrichments table if it doesn't exist.
    This column tracks the source of enrichment data: 'lookup', 'llm', 'regex', 'manual', or NULL.

    This is safe to run multiple times - it will only add the column if it doesn't exist.

    Returns:
        Boolean indicating whether migration was needed and executed
    """
    with get_db() as conn:
        c = conn.cursor()

        # Check if column already exists
        c.execute("PRAGMA table_info(transaction_enrichments)")
        columns = [col[1] for col in c.fetchall()]

        if 'enrichment_source' not in columns:
            # Add the column
            c.execute('''
                ALTER TABLE transaction_enrichments
                ADD COLUMN enrichment_source TEXT CHECK(enrichment_source IN ('lookup', 'llm', 'regex', 'manual', NULL))
            ''')
            conn.commit()
            print("✓ Added enrichment_source column to transaction_enrichments table")
            return True

        return False


def populate_lookup_descriptions():
    """
    Populate lookup_description column for transactions that have matches to Amazon or Apple purchases.

    For transactions matched to Amazon orders, use the product_names from the order.
    For transactions matched to Apple transactions, use the app_names.

    This function is safe to run multiple times - it will update existing lookup_description values.

    Returns:
        Dictionary with counts of updated transactions
    """
    with get_db() as conn:
        c = conn.cursor()

        updated_amazon = 0
        updated_apple = 0

        # Update lookup_description for Amazon matches
        try:
            c.execute('''
                UPDATE transactions
                SET lookup_description = (
                    SELECT ao.product_names
                    FROM amazon_transaction_matches atm
                    JOIN amazon_orders ao ON atm.amazon_order_id = ao.id
                    WHERE atm.transaction_id = transactions.id
                    LIMIT 1
                )
                WHERE id IN (
                    SELECT t.id FROM transactions t
                    WHERE EXISTS (
                        SELECT 1 FROM amazon_transaction_matches atm
                        WHERE atm.transaction_id = t.id
                    )
                )
            ''')
            updated_amazon = c.rowcount

            # Update lookup_description for Apple matches (don't overwrite Amazon data)
            c.execute('''
                UPDATE transactions
                SET lookup_description = (
                    SELECT COALESCE(
                        NULLIF(lookup_description, ''),
                        at.app_names
                    )
                    FROM apple_transaction_matches atm
                    JOIN apple_transactions at ON atm.apple_transaction_id = at.id
                    WHERE atm.bank_transaction_id = transactions.id
                    LIMIT 1
                )
                WHERE id IN (
                    SELECT t.id FROM transactions t
                    WHERE EXISTS (
                        SELECT 1 FROM apple_transaction_matches atm
                        WHERE atm.bank_transaction_id = t.id
                    )
                )
            ''')
            updated_apple = c.rowcount

            conn.commit()

            total_updated = updated_amazon + updated_apple
            if total_updated > 0:
                print(f"✓ Populated lookup_description for {total_updated} transactions")
                print(f"  - {updated_amazon} from Amazon matches")
                print(f"  - {updated_apple} from Apple matches")

            return {
                'total': total_updated,
                'amazon': updated_amazon,
                'apple': updated_apple
            }
        except Exception as e:
            print(f"✗ Error populating lookup descriptions: {e}")
            return {
                'total': 0,
                'amazon': 0,
                'apple': 0
            }


def create_llm_model_config_table():
    """
    Create llm_model_config table to store user-selected and custom LLM models.

    This table tracks which models users have configured for each provider,
    and allows adding custom Ollama models at runtime.

    This is safe to run multiple times - it will only create the table if it doesn't exist.

    Returns:
        Boolean indicating whether table was created
    """
    with get_db() as conn:
        c = conn.cursor()

        # Check if table already exists
        c.execute('''
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='llm_model_config'
        ''')

        if not c.fetchone():
            # Create the table
            c.execute('''
                CREATE TABLE llm_model_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    is_custom BOOLEAN DEFAULT 0,
                    is_selected BOOLEAN DEFAULT 0,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(provider, model_name)
                )
            ''')
            conn.commit()
            print("✓ Created llm_model_config table")
            return True

        return False


def add_llm_model(provider: str, model_name: str, is_custom: bool = False) -> bool:
    """
    Add or update an LLM model in the configuration.

    Args:
        provider: LLM provider name (ollama, anthropic, openai, etc.)
        model_name: Model name/identifier
        is_custom: Whether this is a user-added custom model

    Returns:
        True if model was added, False if it already existed
    """
    with get_db() as conn:
        c = conn.cursor()

        try:
            c.execute('''
                INSERT INTO llm_model_config (provider, model_name, is_custom)
                VALUES (?, ?, ?)
            ''', (provider, model_name, int(is_custom)))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Model already exists
            return False


def set_selected_model(provider: str, model_name: str) -> bool:
    """
    Set the currently selected model for a provider.

    Args:
        provider: LLM provider name
        model_name: Model name to select

    Returns:
        True if model was selected, False if model not found
    """
    with get_db() as conn:
        c = conn.cursor()

        # Deselect all models for this provider
        c.execute('''
            UPDATE llm_model_config
            SET is_selected = 0
            WHERE provider = ?
        ''', (provider,))

        # Select the specified model
        c.execute('''
            UPDATE llm_model_config
            SET is_selected = 1
            WHERE provider = ? AND model_name = ?
        ''', (provider, model_name))

        conn.commit()
        return c.rowcount > 0


def get_selected_model(provider: str) -> Optional[str]:
    """
    Get the currently selected model for a provider.

    Args:
        provider: LLM provider name

    Returns:
        Model name if one is selected, None otherwise
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT model_name
            FROM llm_model_config
            WHERE provider = ? AND is_selected = 1
            LIMIT 1
        ''', (provider,))

        result = c.fetchone()
        return result[0] if result else None


def get_provider_models(provider: str) -> dict:
    """
    Get all models for a provider (both built-in and custom).

    Args:
        provider: LLM provider name

    Returns:
        Dict with 'built_in' and 'custom' lists of models
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT model_name, is_custom, is_selected
            FROM llm_model_config
            WHERE provider = ?
            ORDER BY is_custom ASC, model_name ASC
        ''', (provider,))

        models = {
            'built_in': [],
            'custom': []
        }
        selected = None

        for row in c.fetchall():
            model_info = {
                'name': row['model_name'],
                'selected': bool(row['is_selected'])
            }
            if row['is_custom']:
                models['custom'].append(model_info)
            else:
                models['built_in'].append(model_info)

            if row['is_selected']:
                selected = row['model_name']

        models['selected'] = selected
        return models


def delete_custom_model(provider: str, model_name: str) -> bool:
    """
    Delete a custom model from configuration.

    Args:
        provider: LLM provider name
        model_name: Model name to delete

    Returns:
        True if model was deleted, False if not found or is built-in
    """
    with get_db() as conn:
        c = conn.cursor()

        c.execute('''
            DELETE FROM llm_model_config
            WHERE provider = ? AND model_name = ? AND is_custom = 1
        ''', (provider, model_name))

        conn.commit()
        return c.rowcount > 0


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
    Get all transactions with Amazon references that haven't been matched to orders.

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
                UPPER(t.description) LIKE '%AMAZON%'
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
                UPPER(description) LIKE '%AMAZON%'
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


def update_transaction_lookup_description(transaction_id, lookup_description):
    """
    Update the lookup_description field of a transaction.
    Used to populate lookup information from Amazon/Apple matches.

    Args:
        transaction_id: ID of the transaction
        lookup_description: New lookup description text

    Returns:
        Boolean indicating success
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            UPDATE transactions
            SET lookup_description = ?
            WHERE id = ?
        ''', (lookup_description, transaction_id))
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


def fix_bill_payment_merchants_preview():
    """
    Preview what bill payment merchant fixes would be applied.

    Returns:
        List of changes that would be made
    """
    from mcp.excel_parser import extract_bill_payment_merchant

    transactions = get_all_transactions()
    changes = []

    for txn in transactions:
        description = txn.get('description', '')
        merchant = txn.get('merchant', '')

        if not description or 'BILL PAYMENT VIA FASTER PAYMENT TO' not in description.upper():
            continue

        # Extract bill payment merchant from description
        extracted_merchant = extract_bill_payment_merchant(description)

        if extracted_merchant and extracted_merchant != merchant:
            changes.append({
                'transaction_id': txn['id'],
                'description': description[:60],
                'current_merchant': merchant,
                'new_merchant': extracted_merchant
            })

    return changes


def fix_bill_payment_merchants():
    """
    Fix bill payment transactions by extracting merchant names from descriptions.

    Returns:
        Dictionary with fix statistics
    """
    from mcp.excel_parser import extract_bill_payment_merchant

    transactions = get_all_transactions()
    fixed_count = 0
    changes = []

    with get_db() as conn:
        c = conn.cursor()

        for txn in transactions:
            description = txn.get('description', '')
            merchant = txn.get('merchant', '')

            if not description or 'BILL PAYMENT VIA FASTER PAYMENT TO' not in description.upper():
                continue

            # Extract bill payment merchant from description
            extracted_merchant = extract_bill_payment_merchant(description)

            if extracted_merchant and extracted_merchant != merchant:
                c.execute('''
                    UPDATE transactions
                    SET merchant = ?
                    WHERE id = ?
                ''', (extracted_merchant, txn['id']))

                fixed_count += 1
                changes.append({
                    'transaction_id': txn['id'],
                    'old_merchant': merchant,
                    'new_merchant': extracted_merchant
                })

        conn.commit()

    return {
        'success': True,
        'fixed_count': fixed_count,
        'sample_changes': changes[:20]  # Show first 20 examples
    }


def fix_bank_giro_merchants_preview():
    """
    Preview what bank giro merchant fixes would be applied.

    Returns:
        List of changes that would be made
    """
    from mcp.excel_parser import extract_bank_giro_merchant

    transactions = get_all_transactions()
    changes = []

    for txn in transactions:
        description = txn.get('description', '')
        merchant = txn.get('merchant', '')

        if not description or 'BANK GIRO CREDIT' not in description.upper():
            continue

        # Extract bank giro merchant from description
        extracted_merchant = extract_bank_giro_merchant(description)

        if extracted_merchant and extracted_merchant != merchant:
            changes.append({
                'transaction_id': txn['id'],
                'description': description[:60],
                'current_merchant': merchant,
                'new_merchant': extracted_merchant
            })

    return changes


def fix_bank_giro_merchants():
    """
    Fix bank giro transactions by extracting merchant names from descriptions.

    Returns:
        Dictionary with fix statistics
    """
    from mcp.excel_parser import extract_bank_giro_merchant

    transactions = get_all_transactions()
    fixed_count = 0
    changes = []

    with get_db() as conn:
        c = conn.cursor()

        for txn in transactions:
            description = txn.get('description', '')
            merchant = txn.get('merchant', '')

            if not description or 'BANK GIRO CREDIT' not in description.upper():
                continue

            # Extract bank giro merchant from description
            extracted_merchant = extract_bank_giro_merchant(description)

            if extracted_merchant and extracted_merchant != merchant:
                c.execute('''
                    UPDATE transactions
                    SET merchant = ?
                    WHERE id = ?
                ''', (extracted_merchant, txn['id']))

                fixed_count += 1
                changes.append({
                    'transaction_id': txn['id'],
                    'old_merchant': merchant,
                    'new_merchant': extracted_merchant
                })

        conn.commit()

    return {
        'success': True,
        'fixed_count': fixed_count,
        'sample_changes': changes[:20]  # Show first 20 examples
    }


def fix_direct_debit_merchants_preview():
    """
    Preview what direct debit merchant fixes would be applied.

    Returns:
        List of changes that would be made
    """
    from mcp.excel_parser import extract_direct_debit_merchant

    transactions = get_all_transactions()
    changes = []

    for txn in transactions:
        description = txn.get('description', '')
        merchant = txn.get('merchant', '')

        if not description or 'DIRECT DEBIT PAYMENT TO' not in description.upper():
            continue

        # Extract direct debit merchant from description
        extracted_merchant = extract_direct_debit_merchant(description)

        if extracted_merchant and extracted_merchant != merchant:
            changes.append({
                'transaction_id': txn['id'],
                'description': description[:60],
                'current_merchant': merchant,
                'new_merchant': extracted_merchant
            })

    return changes


def fix_direct_debit_merchants():
    """
    Fix direct debit transactions by extracting real merchant names from descriptions.

    Returns:
        Dictionary with fix statistics
    """
    from mcp.excel_parser import extract_direct_debit_merchant

    transactions = get_all_transactions()
    fixed_count = 0
    changes = []

    with get_db() as conn:
        c = conn.cursor()

        for txn in transactions:
            description = txn.get('description', '')
            merchant = txn.get('merchant', '')

            if not description or 'DIRECT DEBIT PAYMENT TO' not in description.upper():
                continue

            # Extract direct debit merchant from description
            extracted_merchant = extract_direct_debit_merchant(description)

            if extracted_merchant and extracted_merchant != merchant:
                c.execute('''
                    UPDATE transactions
                    SET merchant = ?
                    WHERE id = ?
                ''', (extracted_merchant, txn['id']))

                fixed_count += 1
                changes.append({
                    'transaction_id': txn['id'],
                    'old_merchant': merchant,
                    'new_merchant': extracted_merchant
                })

        conn.commit()

    return {
        'success': True,
        'fixed_count': fixed_count,
        'sample_changes': changes[:20]  # Show first 20 examples
    }


def fix_card_payment_merchants_preview():
    """
    Preview what card payment merchant fixes would be applied.

    Returns:
        List of changes that would be made
    """
    from mcp.excel_parser import extract_merchant

    transactions = get_all_transactions()
    changes = []

    for txn in transactions:
        description = txn.get('description', '')
        merchant = txn.get('merchant', '')

        if not description or 'CARD PAYMENT TO' not in description.upper():
            continue

        # Extract merchant from description using full extract_merchant function
        # This includes special handling for PayPal and other nested payment services
        extracted_merchant = extract_merchant(description)

        if extracted_merchant and extracted_merchant != merchant:
            changes.append({
                'transaction_id': txn['id'],
                'description': description[:60],
                'current_merchant': merchant,
                'new_merchant': extracted_merchant
            })

    return changes


def fix_card_payment_merchants():
    """
    Fix card payment transactions by extracting real merchant names from descriptions.

    Returns:
        Dictionary with fix statistics
    """
    from mcp.excel_parser import extract_merchant

    transactions = get_all_transactions()
    fixed_count = 0
    changes = []

    with get_db() as conn:
        c = conn.cursor()

        for txn in transactions:
            description = txn.get('description', '')
            merchant = txn.get('merchant', '')

            if not description or 'CARD PAYMENT TO' not in description.upper():
                continue

            # Extract merchant from description using full extract_merchant function
            # This includes special handling for PayPal and other nested payment services
            extracted_merchant = extract_merchant(description)

            if extracted_merchant and extracted_merchant != merchant:
                c.execute('''
                    UPDATE transactions
                    SET merchant = ?
                    WHERE id = ?
                ''', (extracted_merchant, txn['id']))

                fixed_count += 1
                changes.append({
                    'transaction_id': txn['id'],
                    'old_merchant': merchant,
                    'new_merchant': extracted_merchant
                })

        conn.commit()

    return {
        'success': True,
        'fixed_count': fixed_count,
        'sample_changes': changes[:20]  # Show first 20 examples
    }


# ============================================================================
# LLM Enrichment Functions
# ============================================================================

def get_enrichment_from_cache(description: str, direction: str):
    """
    Get cached enrichment for a transaction description.

    Args:
        description: Transaction description
        direction: "in" or "out"

    Returns:
        Cached enrichment dict or None if not found
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT
                primary_category, subcategory, merchant_clean_name, merchant_type,
                essential_discretionary, payment_method, payment_method_subtype,
                payee, purchase_date, confidence_score
            FROM llm_enrichment_cache
            WHERE transaction_description = ? AND direction = ?
            LIMIT 1
        ''', (description, direction))

        row = c.fetchone()
        if row:
            return dict(row)
        return None


def cache_enrichment(
    description: str,
    direction: str,
    enrichment,
    provider: str,
    model: str
) -> bool:
    """Cache enrichment result for a transaction."""
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('''
                INSERT OR REPLACE INTO llm_enrichment_cache (
                    transaction_description, direction,
                    primary_category, subcategory, merchant_clean_name, merchant_type,
                    essential_discretionary, payment_method, payment_method_subtype,
                    payee, purchase_date, confidence_score, llm_provider, llm_model
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                description, direction,
                enrichment.primary_category,
                enrichment.subcategory,
                enrichment.merchant_clean_name,
                enrichment.merchant_type,
                enrichment.essential_discretionary,
                enrichment.payment_method,
                enrichment.payment_method_subtype,
                enrichment.merchant_clean_name,  # Use merchant_clean_name for payee
                enrichment.purchase_date,
                enrichment.confidence_score,
                provider,
                model
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error caching enrichment: {e}")
            return False


def log_enrichment_failure(
    transaction_id,
    description: str,
    error_type: str,
    error_message: str,
    provider: str
) -> bool:
    """Log a failed enrichment attempt."""
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO llm_enrichment_failures (
                    transaction_id, transaction_description, error_type,
                    error_message, llm_provider, status
                )
                VALUES (?, ?, ?, ?, ?, 'pending_retry')
            ''', (transaction_id, description, error_type, error_message, provider))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error logging enrichment failure: {e}")
            return False


def update_transaction_with_enrichment(transaction_id: int, enrichment, enrichment_source: str = None) -> bool:
    """
    Insert enrichment data for a transaction.

    Args:
        transaction_id: The transaction ID
        enrichment: TransactionEnrichment object with enrichment fields
        enrichment_source: Source of enrichment - 'lookup', 'llm', 'regex', 'manual'
    """
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('''
                INSERT OR REPLACE INTO transaction_enrichments (
                    transaction_id, primary_category, subcategory,
                    merchant_clean_name, merchant_type, essential_discretionary,
                    payment_method, payment_method_subtype, payee, purchase_date,
                    confidence_score, raw_response, llm_provider, llm_model,
                    enrichment_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                transaction_id,
                enrichment.primary_category,
                enrichment.subcategory,
                enrichment.merchant_clean_name,
                enrichment.merchant_type,
                enrichment.essential_discretionary,
                enrichment.payment_method,
                enrichment.payment_method_subtype,
                enrichment.merchant_clean_name,  # Use merchant_clean_name for payee
                enrichment.purchase_date,
                enrichment.confidence_score,
                enrichment.raw_response,
                enrichment.llm_provider,
                enrichment.llm_model,
                enrichment_source or getattr(enrichment, 'enrichment_source', None)
            ))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error storing enrichment for transaction {transaction_id}: {e}")
            return False


def is_transaction_enriched(transaction_id: int) -> bool:
    """Check if a transaction already has enrichment data."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) as count FROM transaction_enrichments
            WHERE transaction_id = ? AND primary_category IS NOT NULL
        ''', (transaction_id,))
        result = c.fetchone()
        return result['count'] > 0 if result else False


def clear_all_enrichments() -> dict:
    """Clear all enrichment data from transaction_enrichments table."""
    with get_db() as conn:
        c = conn.cursor()
        try:
            c.execute('DELETE FROM transaction_enrichments')
            conn.commit()
            c.execute('SELECT COUNT(*) as count FROM transactions')
            total_txns = c.fetchone()['count']
            return {
                'success': True,
                'message': 'All enrichment data cleared',
                'total_transactions': total_txns,
                'enrichments_cleared': total_txns
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


def refresh_lookup_descriptions() -> dict:
    """Manually refresh lookup_description for all transactions from Amazon/Apple matches."""
    with get_db() as conn:
        c = conn.cursor()
        try:
            # Clear existing lookup_description values
            c.execute('UPDATE transactions SET lookup_description = NULL')

            # Update for Amazon matches
            c.execute('''
                UPDATE transactions
                SET lookup_description = (
                    SELECT product_names FROM amazon_orders
                    WHERE amazon_orders.id = (
                        SELECT amazon_order_id FROM amazon_transaction_matches
                        WHERE amazon_transaction_matches.transaction_id = transactions.id
                    )
                )
                WHERE id IN (
                    SELECT transaction_id FROM amazon_transaction_matches
                )
            ''')
            amazon_updated = c.rowcount

            # Update for Apple matches
            c.execute('''
                UPDATE transactions
                SET lookup_description = (
                    SELECT app_names FROM apple_transactions
                    WHERE apple_transactions.id = (
                        SELECT apple_transaction_id FROM apple_transaction_matches
                        WHERE apple_transaction_matches.bank_transaction_id = transactions.id
                    )
                )
                WHERE id IN (
                    SELECT bank_transaction_id FROM apple_transaction_matches
                )
            ''')
            apple_updated = c.rowcount

            conn.commit()
            return {
                'success': True,
                'message': 'Lookup descriptions refreshed',
                'amazon_updated': amazon_updated,
                'apple_updated': apple_updated,
                'total_updated': amazon_updated + apple_updated
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }


def get_failed_enrichments(limit: int = 100) -> list:
    """Get list of failed enrichments pending retry."""
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT
                id, transaction_id, transaction_description, error_type,
                error_message, llm_provider, attempted_at, retry_count
            FROM llm_enrichment_failures
            WHERE status = 'pending_retry'
            ORDER BY attempted_at DESC
            LIMIT ?
        ''', (limit,))
        return [dict(row) for row in c.fetchall()]


def get_cache_stats() -> dict:
    """Get statistics about the enrichment cache."""
    with get_db() as conn:
        c = conn.cursor()

        c.execute("SELECT COUNT(*) as count FROM llm_enrichment_cache")
        cache_size = c.fetchone()['count']

        c.execute('''
            SELECT llm_provider, COUNT(*) as count
            FROM llm_enrichment_cache
            GROUP BY llm_provider
        ''')
        provider_stats = {row['llm_provider']: row['count'] for row in c.fetchall()}

        c.execute("SELECT COUNT(*) as count FROM llm_enrichment_failures WHERE status = 'pending_retry'")
        pending_retries = c.fetchone()['count']

        # Estimate cache size in bytes (approximately 500-1000 bytes per cached item)
        cache_size_bytes = cache_size * 750

        return {
            'cache_size': cache_size,
            'provider_breakdown': provider_stats,
            'pending_retries': pending_retries,
            'cache_size_bytes': cache_size_bytes,
        }


def get_enrichment_analytics() -> dict:
    """Get comprehensive enrichment analytics and coverage metrics."""
    with get_db() as conn:
        c = conn.cursor()

        # Total transactions
        c.execute("SELECT COUNT(*) as count FROM transactions")
        total_txns = c.fetchone()['count']

        # Enriched vs unenriched
        c.execute('''
            SELECT COUNT(*) as count FROM transaction_enrichments
            WHERE primary_category IS NOT NULL
        ''')
        enriched_txns = c.fetchone()['count']
        unenriched_txns = total_txns - enriched_txns

        # Enrichment by source
        c.execute('''
            SELECT enrichment_source, COUNT(*) as count
            FROM transaction_enrichments
            WHERE enrichment_source IS NOT NULL
            GROUP BY enrichment_source
        ''')
        by_source = {row['enrichment_source']: row['count'] for row in c.fetchall()}

        # Enrichment by confidence band
        c.execute('''
            SELECT
                CASE
                    WHEN confidence_score >= 0.9 THEN 'high'
                    WHEN confidence_score >= 0.7 THEN 'medium'
                    ELSE 'low'
                END as band,
                COUNT(*) as count
            FROM transaction_enrichments
            WHERE confidence_score IS NOT NULL
            GROUP BY band
        ''')
        by_confidence = {row['band']: row['count'] for row in c.fetchall()}

        # Category distribution
        c.execute('''
            SELECT primary_category, COUNT(*) as count
            FROM transaction_enrichments
            WHERE primary_category IS NOT NULL
            GROUP BY primary_category
            ORDER BY count DESC
        ''')
        categories = {row['primary_category']: row['count'] for row in c.fetchall()}

        # Essential vs Discretionary
        c.execute('''
            SELECT essential_discretionary, COUNT(*) as count
            FROM transaction_enrichments
            WHERE essential_discretionary IS NOT NULL
            GROUP BY essential_discretionary
        ''')
        by_class = {row['essential_discretionary']: row['count'] for row in c.fetchall()}

        return {
            'total_transactions': total_txns,
            'enriched_transactions': enriched_txns,
            'unenriched_transactions': unenriched_txns,
            'enrichment_percentage': round((enriched_txns / total_txns * 100) if total_txns > 0 else 0, 1),
            'by_source': by_source,
            'by_confidence_band': by_confidence,
            'categories': categories,
            'essential_vs_discretionary': by_class
        }


def get_enrichment_quality_report() -> dict:
    """Get detailed enrichment quality report with confidence distribution."""
    with get_db() as conn:
        c = conn.cursor()

        # Confidence score distribution
        c.execute('''
            SELECT
                ROUND(confidence_score, 1) as score_band,
                COUNT(*) as count
            FROM transaction_enrichments
            WHERE confidence_score IS NOT NULL
            GROUP BY ROUND(confidence_score, 1)
            ORDER BY score_band DESC
        ''')
        confidence_dist = {row['score_band']: row['count'] for row in c.fetchall()}

        # Coverage by category
        c.execute('''
            SELECT
                primary_category,
                COUNT(*) as enriched_count,
                ROUND(AVG(confidence_score), 2) as avg_confidence
            FROM transaction_enrichments
            WHERE primary_category IS NOT NULL
            GROUP BY primary_category
            ORDER BY enriched_count DESC
        ''')
        coverage_by_cat = {}
        for row in c.fetchall():
            coverage_by_cat[row['primary_category']] = {
                'count': row['enriched_count'],
                'avg_confidence': row['avg_confidence']
            }

        # Failed enrichments summary
        c.execute('''
            SELECT error_type, COUNT(*) as count
            FROM llm_enrichment_failures
            WHERE status = 'pending_retry'
            GROUP BY error_type
        ''')
        failures_by_type = {row['error_type']: row['count'] for row in c.fetchall()}

        # Overall metrics
        c.execute("SELECT AVG(confidence_score) as avg, MIN(confidence_score) as min, MAX(confidence_score) as max FROM transaction_enrichments WHERE confidence_score IS NOT NULL")
        conf_stats = c.fetchone()

        return {
            'confidence_distribution': confidence_dist,
            'coverage_by_category': coverage_by_cat,
            'confidence_metrics': {
                'average': round(conf_stats['avg'], 3) if conf_stats['avg'] else 0,
                'minimum': round(conf_stats['min'], 3) if conf_stats['min'] else 0,
                'maximum': round(conf_stats['max'], 3) if conf_stats['max'] else 0
            },
            'failed_enrichments_by_type': failures_by_type
        }


def get_enrichment_cost_tracking(days_back: int = None) -> dict:
    """Get cost tracking and efficiency metrics for enrichment."""
    with get_db() as conn:
        c = conn.cursor()

        # Total cost and usage stats
        c.execute('''
            SELECT
                COUNT(DISTINCT transaction_id) as enriched_txns,
                COUNT(*) as total_entries,
                SUM(CAST(raw_response as INTEGER)) as token_estimate
            FROM transaction_enrichments
            WHERE enriched_at IS NOT NULL AND llm_provider IS NOT NULL
        ''')
        usage = c.fetchone()

        # Get cost from cache if available (would need to add cost tracking to cache table)
        c.execute('''
            SELECT
                llm_provider,
                llm_model,
                COUNT(*) as queries,
                COUNT(DISTINCT transaction_description) as unique_descriptions
            FROM llm_enrichment_cache
            GROUP BY llm_provider, llm_model
        ''')
        provider_usage = {}
        for row in c.fetchall():
            key = f"{row['llm_provider']} ({row['llm_model']})"
            provider_usage[key] = {
                'queries': row['queries'],
                'cache_hits': row['unique_descriptions']
            }

        # Cache efficiency
        c.execute('''
            SELECT
                COUNT(*) as total_cached,
                COUNT(DISTINCT transaction_description) as unique_descriptions
            FROM llm_enrichment_cache
        ''')
        cache_info = c.fetchone()

        return {
            'enriched_transactions': usage['enriched_txns'] if usage['enriched_txns'] else 0,
            'total_enrichment_entries': usage['total_entries'] if usage['total_entries'] else 0,
            'provider_usage': provider_usage,
            'cache_stats': {
                'total_cached_items': cache_info['total_cached'] if cache_info['total_cached'] else 0,
                'unique_descriptions': cache_info['unique_descriptions'] if cache_info['unique_descriptions'] else 0
            }
        }


def get_enrichment_by_source() -> dict:
    """Get data source attribution for enrichment."""
    with get_db() as conn:
        c = conn.cursor()

        # Source breakdown
        c.execute('''
            SELECT enrichment_source, COUNT(*) as count
            FROM transaction_enrichments
            GROUP BY enrichment_source
        ''')
        by_source = {}
        total = 0
        for row in c.fetchall():
            source = row['enrichment_source'] or 'unknown'
            count = row['count']
            by_source[source] = count
            total += count

        # Convert to percentages
        by_source_pct = {}
        for source, count in by_source.items():
            by_source_pct[source] = {
                'count': count,
                'percentage': round(count / total * 100, 1) if total > 0 else 0
            }

        # Details for each source
        c.execute('''
            SELECT
                enrichment_source,
                COUNT(*) as count,
                AVG(confidence_score) as avg_confidence,
                MIN(confidence_score) as min_confidence,
                MAX(confidence_score) as max_confidence
            FROM transaction_enrichments
            WHERE enrichment_source IS NOT NULL
            GROUP BY enrichment_source
        ''')
        source_details = {}
        for row in c.fetchall():
            source_details[row['enrichment_source']] = {
                'count': row['count'],
                'avg_confidence': round(row['avg_confidence'], 2) if row['avg_confidence'] else 0,
                'min_confidence': round(row['min_confidence'], 2) if row['min_confidence'] else 0,
                'max_confidence': round(row['max_confidence'], 2) if row['max_confidence'] else 0
            }

        return {
            'by_source': by_source_pct,
            'source_details': source_details,
            'total_enriched': total
        }
