"""
Database Module Initializer

This module provides conditional imports to switch between SQLite and PostgreSQL
based on the DB_TYPE environment variable.

Usage:
    import database_init as database
    # Then use database.get_db(), database.get_all_transactions(), etc.
    # The correct backend is automatically selected.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Determine which database backend to use
DB_TYPE = os.getenv('DB_TYPE', 'sqlite').lower()

if DB_TYPE == 'postgres':
    # Use PostgreSQL backend
    from database_postgres import *
    print(f"✓ Using PostgreSQL database backend")
elif DB_TYPE == 'sqlite':
    # Use SQLite backend (default)
    from database import *
    print(f"✓ Using SQLite database backend")
else:
    raise ValueError(f"Unknown DB_TYPE: {DB_TYPE}. Must be 'postgres' or 'sqlite'")
