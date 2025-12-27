"""
Database Connection Pool and Base Utilities

This module provides the core database connection management for the refactored
database layer. It handles:
- PostgreSQL connection pooling
- Context manager for database connections
- Database configuration
- Schema initialization

All domain-specific database operations are in separate modules (gmail.py,
truelayer.py, etc.) that use these base utilities.
"""

import os
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv
from psycopg2 import pool
from psycopg2.extras import RealDictCursor

# Load environment variables (don't override existing for Docker compatibility)
load_dotenv(override=False)

# Database connection configuration
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "database": os.getenv("POSTGRES_DB", "spending_db"),
    "user": os.getenv("POSTGRES_USER", "spending_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "spending_password"),
}

# Global connection pool
connection_pool = None


def init_pool():
    """
    Initialize PostgreSQL connection pool.

    Creates a ThreadedConnectionPool with 1-10 connections.
    Thread-safe pool required for Flask multi-threaded environment.
    Called automatically by get_db() if pool doesn't exist.

    Raises:
        psycopg2.Error: If connection pool creation fails
    """
    global connection_pool
    try:
        connection_pool = pool.ThreadedConnectionPool(
            1,  # Minimum connections
            10,  # Maximum connections
            **DB_CONFIG,
        )
        if connection_pool:
            print("✓ PostgreSQL connection pool created successfully")
            # Initialize schema (domain-specific tables created on demand)
            _init_core_schema()
    except (Exception, psycopg2.Error) as error:
        print(f"✗ Error creating connection pool: {error}")
        raise


def _init_core_schema():
    """
    Initialize core database schema that doesn't belong to a specific domain.

    Domain-specific tables (Gmail, TrueLayer, etc.) are created in their
    respective modules.
    """
    # Import domain modules to trigger their schema initialization
    # This will be populated as modules are created


@contextmanager
def get_db():
    """
    Context manager for database connections from pool.

    Usage:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM table")

    Automatically rolls back on exceptions and returns connection to pool.

    Yields:
        psycopg2.connection: Database connection from pool
    """
    if connection_pool is None:
        init_pool()

    # Get connection with explicit thread key for ThreadedConnectionPool
    import threading

    key = threading.get_ident()
    conn = connection_pool.getconn(key)
    try:
        yield conn
    except Exception:
        # Rollback on any exception to reset transaction state
        conn.rollback()
        raise
    finally:
        # Always return connection to pool with the same key
        connection_pool.putconn(conn, key)


def close_pool():
    """
    Close all connections in the pool.

    Should be called on application shutdown.
    """
    global connection_pool
    if connection_pool:
        connection_pool.closeall()
        connection_pool = None
        print("✓ Database connection pool closed")


# Utility function for common cursor operations
def execute_query(
    query: str,
    params: tuple = None,
    fetch_one: bool = False,
    fetch_all: bool = False,
    commit: bool = False,
):
    """
    Execute a database query with common patterns.

    Args:
        query: SQL query string
        params: Query parameters (optional)
        fetch_one: If True, return single row as dict
        fetch_all: If True, return all rows as list of dicts
        commit: If True, commit transaction

    Returns:
        dict | list[dict] | None depending on fetch parameters

    Example:
        # Fetch single row
        user = execute_query(
            "SELECT * FROM users WHERE id = %s",
            (user_id,),
            fetch_one=True
        )

        # Fetch all rows
        users = execute_query(
            "SELECT * FROM users",
            fetch_all=True
        )

        # Insert/Update
        execute_query(
            "UPDATE users SET name = %s WHERE id = %s",
            (name, user_id),
            commit=True
        )
    """
    with get_db() as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        cursor.execute(query, params or ())

        if fetch_one:
            result = cursor.fetchone()
            return dict(result) if result else None
        if fetch_all:
            return [dict(row) for row in cursor.fetchall()]

        if commit:
            conn.commit()

    return None
