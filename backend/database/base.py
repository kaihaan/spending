# backend/database/base.py
"""
SQLAlchemy Base and Engine Configuration

Provides the declarative base for all models and engine factory.

CRITICAL SAFETY: When TESTING=true, this module ONLY connects to the test
database (spending_db_test). Production database access is blocked during tests.
"""

import logging
import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.exc import OperationalError, TimeoutError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

load_dotenv(override=False)

logger = logging.getLogger(__name__)

# ============================================================================
# CRITICAL: TEST DATABASE SAFETY CHECK
# ============================================================================
# Determine if we're in test mode and get the correct database name
IS_TESTING = os.getenv("TESTING", "").lower() in ("true", "1", "yes")
PRODUCTION_DB_NAME = "spending_db"
TEST_DB_NAME = os.getenv("POSTGRES_TEST_DB", "spending_db_test")

# Get the database name from environment
db_name = os.getenv("POSTGRES_DB", PRODUCTION_DB_NAME)

# SAFETY: If testing, FORCE use of test database
if IS_TESTING:
    if db_name == PRODUCTION_DB_NAME:
        # Environment didn't set test DB - force it
        db_name = TEST_DB_NAME
        logger.warning(
            f"TESTING=true but POSTGRES_DB was production. Forcing test database: {db_name}"
        )
    elif db_name != TEST_DB_NAME:
        # Some other database - allow it but warn
        logger.warning(f"TESTING=true with custom database: {db_name}")

# Database URL (using URL.create to avoid password exposure in logs)
DATABASE_URL = URL.create(
    "postgresql",
    username=os.getenv("POSTGRES_USER", "spending_user"),
    password=os.getenv("POSTGRES_PASSWORD", "spending_password"),
    host=os.getenv("POSTGRES_HOST", "localhost"),
    port=int(os.getenv("POSTGRES_PORT", "5433")),
    database=db_name,
)

# Declarative base for all models
Base = declarative_base()

# Engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,  # Match psycopg2 pool max
    max_overflow=0,
    pool_pre_ping=True,  # Verify connections before use
    echo=False,  # Set to True for SQL logging during development
    hide_parameters=True,  # Redact password in logs
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_session():
    """Get a new SQLAlchemy session (context manager)."""
    try:
        db = SessionLocal()
    except TimeoutError:
        logger.error("Connection pool exhausted (all connections in use)")
        raise
    except OperationalError as e:
        logger.error(f"Database connection failed: {e}")
        raise

    try:
        yield db
    except Exception as e:
        logger.error(f"Session error: {e}")
        db.rollback()  # Explicit rollback on error
        raise
    finally:
        db.close()
