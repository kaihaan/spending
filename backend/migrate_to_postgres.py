"""
SQLite to PostgreSQL Migration Script

This script migrates data from the existing SQLite database (finance.db)
to the new PostgreSQL database running in Docker.

Usage:
    python migrate_to_postgres.py

Prerequisites:
    1. Docker PostgreSQL container must be running (docker-compose up -d)
    2. SQLite database (finance.db) must exist in backend directory
    3. .env file must be configured with PostgreSQL credentials
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_batch
import os
from dotenv import load_dotenv
from decimal import Decimal
from datetime import datetime

# Load environment variables
load_dotenv()

# Database connection parameters
SQLITE_DB_PATH = 'finance.db'

POSTGRES_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'spending_db'),
    'user': os.getenv('POSTGRES_USER', 'spending_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'spending_password')
}


def connect_sqlite():
    """Connect to SQLite database"""
    if not os.path.exists(SQLITE_DB_PATH):
        raise FileNotFoundError(f"SQLite database not found at {SQLITE_DB_PATH}")

    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def connect_postgres():
    """Connect to PostgreSQL database"""
    try:
        conn = psycopg2.connect(**POSTGRES_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"❌ Error connecting to PostgreSQL: {e}")
        raise


def convert_value(value, target_type='default'):
    """Convert SQLite value to PostgreSQL compatible format"""
    if value is None:
        return None

    if target_type == 'numeric':
        # Convert REAL to NUMERIC
        return Decimal(str(value))
    elif target_type == 'boolean':
        # Convert 0/1 to TRUE/FALSE
        return bool(value)
    elif target_type == 'timestamp':
        # Convert TEXT timestamp to proper timestamp with multiple format support
        if isinstance(value, str):
            # Try multiple date formats
            formats = [
                '%Y-%m-%d %H:%M:%S',  # ISO format with time
                '%Y-%m-%d',            # ISO date only
                '%Y-%m-%dT%H:%M:%S',   # ISO 8601
                '%d/%m/%Y',            # UK date format
                '%m/%d/%Y',            # US date format
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            # If no format matched, try fromisoformat as last resort
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                print(f"⚠️  Could not parse date value: {value}")
                return None
        return value

    return value


def validate_pre_migration(sqlite_conn, postgres_conn):
    """
    Perform pre-migration validation checks.

    Returns:
        Boolean indicating if migration can proceed
    """
    print("\n🔎 Running pre-migration validation checks...")

    all_valid = True

    # Check SQLite database is readable
    try:
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions")
        txn_count = cursor.fetchone()[0]
        print(f"  ✅ SQLite readable: {txn_count} transactions found")
    except Exception as e:
        print(f"  ❌ Cannot read SQLite database: {e}")
        return False

    # Check PostgreSQL database is empty (or warn if not)
    try:
        cursor = postgres_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions")
        pgcount = cursor.fetchone()[0]

        if pgcount > 0:
            print(f"  ⚠️  WARNING: PostgreSQL already has {pgcount} transactions!")
            response = input("  Continue anyway? (yes/no): ").lower().strip()
            if response != 'yes':
                print("  ❌ Migration aborted by user")
                return False
        else:
            print(f"  ✅ PostgreSQL database is empty and ready")
    except Exception as e:
        print(f"  ❌ Cannot access PostgreSQL database: {e}")
        return False

    # Check for date format issues
    try:
        cursor = sqlite_conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transactions WHERE date IS NULL")
        null_dates = cursor.fetchone()[0]

        if null_dates > 0:
            print(f"  ⚠️  WARNING: {null_dates} transactions have NULL dates")
        else:
            print(f"  ✅ All transactions have dates")
    except Exception as e:
        print(f"  ℹ️  Could not check dates: {e}")

    print("  ✅ Pre-migration validation passed!\n")
    return True


def ask_confirmation(message):
    """Ask user for confirmation"""
    response = input(f"\n{message} (yes/no): ").lower().strip()
    return response == 'yes'


def migrate_table(sqlite_conn, postgres_conn, table_name, columns, transformations=None):
    """
    Generic function to migrate a table from SQLite to PostgreSQL

    Args:
        sqlite_conn: SQLite connection
        postgres_conn: PostgreSQL connection
        table_name: Name of table to migrate
        columns: List of column names
        transformations: Dict of column_name -> type for value conversion
    """
    transformations = transformations or {}

    # Fetch data from SQLite
    sqlite_cursor = sqlite_conn.cursor()
    sqlite_cursor.execute(f"SELECT {', '.join(columns)} FROM {table_name}")
    rows = sqlite_cursor.fetchall()

    if not rows:
        print(f"  ℹ️  No data found in {table_name}")
        return 0

    # Prepare data for PostgreSQL
    data = []
    for row in rows:
        converted_row = []
        for idx, col in enumerate(columns):
            value = row[idx]
            if col in transformations:
                value = convert_value(value, transformations[col])
            converted_row.append(value)
        data.append(tuple(converted_row))

    # Insert into PostgreSQL
    postgres_cursor = postgres_conn.cursor()
    placeholders = ', '.join(['%s'] * len(columns))
    insert_query = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"

    try:
        execute_batch(postgres_cursor, insert_query, data, page_size=100)
        postgres_conn.commit()
        print(f"  ✅ Migrated {len(data)} rows to {table_name}")
        return len(data)
    except psycopg2.Error as e:
        postgres_conn.rollback()
        print(f"  ❌ Error migrating {table_name}: {e}")
        raise


def reset_sequence(postgres_conn, table_name, column='id'):
    """Reset PostgreSQL sequence after bulk insert"""
    cursor = postgres_conn.cursor()
    cursor.execute(f"""
        SELECT setval(pg_get_serial_sequence('{table_name}', '{column}'),
        COALESCE((SELECT MAX({column}) FROM {table_name}), 1), false)
    """)
    postgres_conn.commit()


def verify_migration(sqlite_conn, postgres_conn, table_name):
    """Verify row counts match between SQLite and PostgreSQL"""
    sqlite_cursor = sqlite_conn.cursor()
    postgres_cursor = postgres_conn.cursor()

    sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    sqlite_count = sqlite_cursor.fetchone()[0]

    postgres_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    postgres_count = postgres_cursor.fetchone()[0]

    if sqlite_count == postgres_count:
        print(f"  ✅ Verification passed: {table_name} ({postgres_count} rows)")
        return True
    else:
        print(f"  ⚠️  Verification failed: {table_name} - SQLite: {sqlite_count}, PostgreSQL: {postgres_count}")
        return False


def main():
    """Main migration process"""
    print("=" * 70)
    print("SQLite to PostgreSQL Migration")
    print("=" * 70)

    # Connect to databases
    print("\n📡 Connecting to databases...")
    try:
        sqlite_conn = connect_sqlite()
        print("  ✅ Connected to SQLite")
    except Exception as e:
        print(f"  ❌ Failed to connect to SQLite: {e}")
        return

    try:
        postgres_conn = connect_postgres()
        print("  ✅ Connected to PostgreSQL")
    except Exception as e:
        print(f"  ❌ Failed to connect to PostgreSQL: {e}")
        return

    # Pre-migration validation
    if not validate_pre_migration(sqlite_conn, postgres_conn):
        print("\n❌ Pre-migration validation failed. Aborting.")
        sqlite_conn.close()
        postgres_conn.close()
        return

    # Ask for final confirmation
    if not ask_confirmation("Ready to migrate data. Continue?"):
        print("\n❌ Migration cancelled by user.")
        sqlite_conn.close()
        postgres_conn.close()
        return

    # Migration tasks
    migrations = [
        # Table migrations in order (respecting foreign key dependencies)
        {
            'name': 'categories',
            'columns': ['name', 'rule_pattern', 'ai_suggested'],
            'transformations': {'ai_suggested': 'boolean'}
        },
        {
            'name': 'category_keywords',
            'columns': ['category_name', 'keyword', 'created_at'],
            'transformations': {'created_at': 'timestamp'}
        },
        {
            'name': 'account_mappings',
            'columns': ['sort_code', 'account_number', 'friendly_name', 'created_at'],
            'transformations': {'created_at': 'timestamp'}
        },
        {
            'name': 'transactions',
            'columns': ['date', 'description', 'amount', 'category', 'source_file',
                       'merchant', 'huququllah_classification', 'created_at'],
            'transformations': {
                'amount': 'numeric',
                'created_at': 'timestamp'
            }
        },
        {
            'name': 'amazon_orders',
            'columns': ['order_id', 'order_date', 'website', 'currency', 'total_owed',
                       'product_names', 'order_status', 'shipment_status', 'source_file', 'created_at'],
            'transformations': {
                'total_owed': 'numeric',
                'created_at': 'timestamp'
            }
        },
        {
            'name': 'amazon_transaction_matches',
            'columns': ['transaction_id', 'amazon_order_id', 'match_confidence', 'matched_at'],
            'transformations': {
                'match_confidence': 'numeric',
                'matched_at': 'timestamp'
            }
        },
        {
            'name': 'amazon_returns',
            'columns': ['order_id', 'reversal_id', 'refund_completion_date', 'currency',
                       'amount_refunded', 'status', 'disbursement_type', 'source_file',
                       'original_transaction_id', 'refund_transaction_id', 'created_at'],
            'transformations': {
                'amount_refunded': 'numeric',
                'created_at': 'timestamp'
            }
        },
        {
            'name': 'apple_transactions',
            'columns': ['order_id', 'order_date', 'total_amount', 'currency', 'app_names',
                       'publishers', 'item_count', 'source_file', 'created_at'],
            'transformations': {
                'total_amount': 'numeric',
                'created_at': 'timestamp'
            }
        },
        {
            'name': 'apple_transaction_matches',
            'columns': ['apple_transaction_id', 'bank_transaction_id', 'confidence', 'matched_at'],
            'transformations': {'matched_at': 'timestamp'}
        },
    ]

    print("\n📦 Starting data migration...")
    total_rows = 0

    for migration in migrations:
        print(f"\n🔄 Migrating {migration['name']}...")
        try:
            count = migrate_table(
                sqlite_conn,
                postgres_conn,
                migration['name'],
                migration['columns'],
                migration.get('transformations')
            )
            total_rows += count

            # Reset sequence
            reset_sequence(postgres_conn, migration['name'])

        except Exception as e:
            print(f"  ❌ Migration failed for {migration['name']}: {e}")
            print("\n⚠️  Migration aborted. Rolling back...")
            postgres_conn.rollback()
            return

    print(f"\n✅ Migration completed successfully! Total rows migrated: {total_rows}")

    # Verification
    print("\n🔍 Verifying migration...")
    all_verified = True
    for migration in migrations:
        if not verify_migration(sqlite_conn, postgres_conn, migration['name']):
            all_verified = False

    if all_verified:
        print("\n🎉 All tables verified successfully!")
    else:
        print("\n⚠️  Some tables failed verification. Please review the logs above.")

    # Close connections
    sqlite_conn.close()
    postgres_conn.close()

    print("\n" + "=" * 70)
    print("Migration complete. You can now update backend/database.py to use PostgreSQL.")
    print("=" * 70)


if __name__ == "__main__":
    main()
