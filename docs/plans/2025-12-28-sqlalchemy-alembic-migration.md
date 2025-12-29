# SQLAlchemy & Alembic Migration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Migrate from raw psycopg2 + SQL to SQLAlchemy ORM with Alembic migrations for better schema management and type safety.

**Architecture:** Incremental phased migration maintaining backward compatibility. Current database_postgres.py (8845 lines, 242 functions) will be gradually refactored to use SQLAlchemy models while keeping existing functions working. Alembic will manage schema changes going forward.

**Tech Stack:** SQLAlchemy 2.0+, Alembic 1.15.2 (already installed), Python 3.12, PostgreSQL 16

**Migration Scope:**
- **26+ database tables** across domains (TrueLayer, Amazon, Apple, Gmail, etc.)
- **242 database functions** in database_postgres.py
- **218 MCP/task files** that use these functions
- **Threading support** (ThreadedConnectionPool → SQLAlchemy engine pooling)

**Strategy:**
1. **Coexistence** - SQLAlchemy and psycopg2 run side-by-side during migration
2. **Incremental** - Migrate one domain at a time (start with core tables)
3. **Test-driven** - Write tests before migrating each component
4. **Backward compatible** - No API changes to existing functions
5. **Alembic adoption** - Generate initial migration from models, then manage schema changes

---

## Pre-Migration Analysis

**Current State:**
- ✅ Alembic 1.15.2 installed but not configured
- ❌ No SQLAlchemy in requirements.txt
- ✅ Connection pooling via psycopg2.pool.ThreadedConnectionPool
- ✅ RealDictCursor for dict-based results
- ✅ Comprehensive DATABASE_SCHEMA.md documentation
- ⚠️ Large monolithic database_postgres.py file (needs modularization)

**Database Tables by Domain:**
1. **Core** (5 tables): users, categories, category_keywords, account_mappings, oauth_state
2. **TrueLayer** (6 tables): bank_connections, truelayer_accounts, truelayer_transactions, truelayer_balances, truelayer_cards, truelayer_card_transactions
3. **Amazon** (6 tables): amazon_orders, amazon_returns, amazon_business_connections, amazon_business_orders, amazon_business_line_items, truelayer_amazon_transaction_matches
4. **Apple** (2 tables): apple_transactions, apple_transaction_matches
5. **Gmail** (4 tables): gmail_connections, gmail_receipts, gmail_email_content, pdf_attachments
6. **Enrichment** (2 tables): transaction_enrichment_sources, enrichment_cache
7. **Legacy** (2 tables): transactions (Santander), truelayer_connections (deprecated)
8. **System** (3 tables): connection_logs, webhook_events, sync_jobs

---

## Phase 0: Foundation & Setup

### Task 0.1: Install SQLAlchemy

**Files:**
- Modify: `backend/requirements.txt`

**Step 1: Add SQLAlchemy dependency**

```bash
# Add to requirements.txt after psycopg2-binary
echo "SQLAlchemy>=2.0.25" >> backend/requirements.txt
```

**Step 2: Install in virtual environment**

Run: `source backend/venv/bin/activate && pip install SQLAlchemy>=2.0.25`
Expected: Package installed successfully

**Step 3: Verify installation**

Run: `python3 -c "import sqlalchemy; print(sqlalchemy.__version__)"`
Expected: Version 2.0.25 or higher

**Step 4: Commit**

```bash
git add backend/requirements.txt
git commit -m "feat(db): add SQLAlchemy 2.0 dependency"
```

---

### Task 0.2: Initialize Alembic

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/` directory structure
- Create: `backend/alembic/env.py`

**Step 1: Initialize Alembic in backend directory**

Run: `cd backend && alembic init alembic`
Expected: Directory structure created with alembic.ini and alembic/ folder

**Step 2: Configure database URL in alembic.ini**

Edit `backend/alembic.ini` to use environment variables:

```ini
# alembic.ini (line ~38)
# Replace: sqlalchemy.url = driver://user:pass@localhost/dbname
# With:
sqlalchemy.url = postgresql://%(POSTGRES_USER)s:%(POSTGRES_PASSWORD)s@%(POSTGRES_HOST)s:%(POSTGRES_PORT)s/%(POSTGRES_DB)s
```

**Step 3: Update alembic/env.py to load environment**

```python
# backend/alembic/env.py
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv(override=False)

# Update config with env vars
config.set_main_option("POSTGRES_USER", os.getenv("POSTGRES_USER", "spending_user"))
config.set_main_option("POSTGRES_PASSWORD", os.getenv("POSTGRES_PASSWORD", ""))
config.set_main_option("POSTGRES_HOST", os.getenv("POSTGRES_HOST", "localhost"))
config.set_main_option("POSTGRES_PORT", os.getenv("POSTGRES_PORT", "5433"))
config.set_main_option("POSTGRES_DB", os.getenv("POSTGRES_DB", "spending_db"))
```

**Step 4: Test Alembic connection**

Run: `cd backend && alembic current`
Expected: Shows current migration state (empty initially)

**Step 5: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat(db): initialize Alembic for schema migrations"
```

---

### Task 0.3: Create SQLAlchemy Base and Engine

**Files:**
- Create: `backend/database/base.py`
- Create: `backend/database/__init__.py`

**Step 1: Create database package**

```bash
mkdir -p backend/database
touch backend/database/__init__.py
```

**Step 2: Create base.py with declarative base**

```python
# backend/database/base.py
"""
SQLAlchemy Base and Engine Configuration

Provides the declarative base for all models and engine factory.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool
from dotenv import load_dotenv

load_dotenv(override=False)

# Database URL
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'spending_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'spending_password')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5433')}/"
    f"{os.getenv('POSTGRES_DB', 'spending_db')}"
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
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session():
    """Get a new SQLAlchemy session (context manager)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

**Step 3: Update __init__.py**

```python
# backend/database/__init__.py
"""
Database package with SQLAlchemy models and utilities.
"""
from .base import Base, engine, SessionLocal, get_session

__all__ = ["Base", "engine", "SessionLocal", "get_session"]
```

**Step 4: Test database connection**

Run:
```bash
cd backend && python3 -c "
from database.base import engine
print('Testing connection...')
with engine.connect() as conn:
    result = conn.execute('SELECT 1')
    print('✓ Connection successful')
"
```
Expected: Connection successful message

**Step 5: Commit**

```bash
git add backend/database/
git commit -m "feat(db): create SQLAlchemy base and engine configuration"
```

---

### Task 0.4: Update Alembic env.py to Import Models

**Files:**
- Modify: `backend/alembic/env.py`

**Step 1: Update env.py to use our Base**

```python
# backend/alembic/env.py
import os
import sys
from dotenv import load_dotenv

# Add backend to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

# Load environment
load_dotenv(override=False)

# Import Base and all models
from database.base import Base
# Models will be imported here as we create them
# from database.models.user import User
# from database.models.transaction import Transaction
# etc.

# this is the Alembic Config object
config = context.config

# Update config with env vars
config.set_main_option("sqlalchemy.url",
    f"postgresql://{os.getenv('POSTGRES_USER', 'spending_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD', '')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5433')}/"
    f"{os.getenv('POSTGRES_DB', 'spending_db')}"
)

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate
target_metadata = Base.metadata


# rest of env.py remains the same...
def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 2: Test Alembic can import Base**

Run: `cd backend && alembic current`
Expected: No import errors

**Step 3: Commit**

```bash
git add backend/alembic/env.py
git commit -m "feat(db): configure Alembic to use SQLAlchemy Base"
```

---

## Phase 1: Core Models (High Priority Tables)

### Task 1.1: Create User Model

**Files:**
- Create: `backend/database/models/__init__.py`
- Create: `backend/database/models/user.py`
- Create: `tests/test_models/test_user.py`

**Step 1: Create models package**

```bash
mkdir -p backend/database/models
touch backend/database/models/__init__.py
```

**Step 2: Write failing test**

```python
# tests/test_models/test_user.py
import pytest
from datetime import datetime, timezone
from database.base import SessionLocal, engine, Base
from database.models.user import User


@pytest.fixture(scope="function")
def db_session():
    """Create fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_create_user(db_session):
    """Test creating a user."""
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.email == "test@example.com"
    assert user.created_at is not None
    assert user.updated_at is not None


def test_user_email_unique(db_session):
    """Test email uniqueness constraint."""
    user1 = User(email="test@example.com")
    db_session.add(user1)
    db_session.commit()

    user2 = User(email="test@example.com")
    db_session.add(user2)

    with pytest.raises(Exception):  # IntegrityError
        db_session.commit()
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_models/test_user.py -v`
Expected: FAIL with "No module named 'database.models.user'"

**Step 4: Implement User model**

```python
# backend/database/models/user.py
"""
User model for authentication and account management.

Maps to: users table
See: .claude/docs/database/DATABASE_SCHEMA.md#1-users
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from database.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email})>"
```

**Step 5: Update models __init__.py**

```python
# backend/database/models/__init__.py
"""SQLAlchemy models for all database tables."""
from .user import User

__all__ = ["User"]
```

**Step 6: Run test to verify it passes**

Run: `pytest tests/test_models/test_user.py -v`
Expected: PASS (2 tests)

**Step 7: Commit**

```bash
git add backend/database/models/ tests/test_models/
git commit -m "feat(models): add User SQLAlchemy model with tests"
```

---

### Task 1.2: Create Category Models

**Files:**
- Create: `backend/database/models/category.py`
- Create: `tests/test_models/test_category.py`

**Step 1: Write failing test**

```python
# tests/test_models/test_category.py
import pytest
from database.base import SessionLocal, engine, Base
from database.models.category import Category, CategoryKeyword


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_create_category(db_session):
    """Test creating a category."""
    category = Category(
        name="Groceries",
        rule_pattern="(?i)(tesco|sainsbury|asda)",
        ai_suggested=False
    )
    db_session.add(category)
    db_session.commit()

    assert category.id is not None
    assert category.name == "Groceries"
    assert category.rule_pattern is not None


def test_create_category_keyword(db_session):
    """Test creating a category keyword."""
    keyword = CategoryKeyword(
        category_name="Groceries",
        keyword="tesco"
    )
    db_session.add(keyword)
    db_session.commit()

    assert keyword.id is not None
    assert keyword.category_name == "Groceries"
    assert keyword.keyword == "tesco"
    assert keyword.created_at is not None


def test_category_keywords_relationship(db_session):
    """Test relationship between Category and CategoryKeyword."""
    category = Category(name="Groceries")
    keyword1 = CategoryKeyword(category_name="Groceries", keyword="tesco")
    keyword2 = CategoryKeyword(category_name="Groceries", keyword="sainsbury")

    db_session.add_all([category, keyword1, keyword2])
    db_session.commit()

    # Test relationship (if we add one later)
    assert category.id is not None
```

**Step 2: Run test**

Run: `pytest tests/test_models/test_category.py -v`
Expected: FAIL - models don't exist

**Step 3: Implement Category models**

```python
# backend/database/models/category.py
"""
Category models for transaction classification.

Maps to:
- categories table
- category_keywords table

See: .claude/docs/database/DATABASE_SCHEMA.md#10-categories
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from database.base import Base


class Category(Base):
    """Transaction category for classification."""
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    rule_pattern = Column(Text, nullable=True)
    ai_suggested = Column(Boolean, default=False, nullable=False)

    def __repr__(self):
        return f"<Category(id={self.id}, name={self.name})>"


class CategoryKeyword(Base):
    """Keywords for category matching."""
    __tablename__ = "category_keywords"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_name = Column(String, nullable=False)
    keyword = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<CategoryKeyword(id={self.id}, category={self.category_name}, keyword={self.keyword})>"
```

**Step 4: Update models __init__.py**

```python
# backend/database/models/__init__.py
from .user import User
from .category import Category, CategoryKeyword

__all__ = ["User", "Category", "CategoryKeyword"]
```

**Step 5: Run tests**

Run: `pytest tests/test_models/test_category.py -v`
Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/database/models/category.py tests/test_models/test_category.py
git commit -m "feat(models): add Category and CategoryKeyword models with tests"
```

---

### Task 1.3: Create TrueLayer Core Models

**Files:**
- Create: `backend/database/models/truelayer.py`
- Create: `tests/test_models/test_truelayer.py`

**Step 1: Write failing test**

```python
# tests/test_models/test_truelayer.py
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from database.base import SessionLocal, engine, Base
from database.models.user import User
from database.models.truelayer import (
    BankConnection, TrueLayerAccount, TrueLayerTransaction
)


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_create_bank_connection(db_session):
    """Test creating a bank connection."""
    user = User(email="test@example.com")
    db_session.add(user)
    db_session.commit()

    connection = BankConnection(
        user_id=user.id,
        provider_id="truelayer",
        provider_name="TrueLayer",
        access_token="encrypted_token",
        refresh_token="encrypted_refresh",
        connection_status="active"
    )
    db_session.add(connection)
    db_session.commit()

    assert connection.id is not None
    assert connection.user_id == user.id
    assert connection.provider_id == "truelayer"


def test_create_truelayer_account(db_session):
    """Test creating a TrueLayer account."""
    user = User(email="test@example.com")
    connection = BankConnection(
        user_id=1,
        provider_id="truelayer",
        provider_name="TrueLayer"
    )
    db_session.add_all([user, connection])
    db_session.commit()

    account = TrueLayerAccount(
        connection_id=connection.id,
        account_id="acc_123",
        account_type="TRANSACTION",
        display_name="Current Account",
        currency="GBP"
    )
    db_session.add(account)
    db_session.commit()

    assert account.id is not None
    assert account.account_id == "acc_123"


def test_create_truelayer_transaction(db_session):
    """Test creating a TrueLayer transaction."""
    user = User(email="test@example.com")
    connection = BankConnection(user_id=1, provider_id="truelayer", provider_name="TL")
    account = TrueLayerAccount(
        connection_id=1,
        account_id="acc_123",
        account_type="TRANSACTION",
        display_name="Account",
        currency="GBP"
    )
    db_session.add_all([user, connection, account])
    db_session.commit()

    txn = TrueLayerTransaction(
        account_id=account.id,
        transaction_id="txn_123",
        normalised_provider_transaction_id="norm_123",
        timestamp=datetime.now(timezone.utc),
        description="Test purchase",
        amount=Decimal("10.50"),
        currency="GBP",
        transaction_type="DEBIT"
    )
    db_session.add(txn)
    db_session.commit()

    assert txn.id is not None
    assert txn.amount == Decimal("10.50")
```

**Step 2: Run test**

Run: `pytest tests/test_models/test_truelayer.py -v`
Expected: FAIL - models don't exist

**Step 3: Implement TrueLayer models**

```python
# backend/database/models/truelayer.py
"""
TrueLayer integration models for bank connections and transactions.

Maps to:
- bank_connections table
- truelayer_accounts table
- truelayer_transactions table
- truelayer_balances table

See: .claude/docs/database/DATABASE_SCHEMA.md#5-bank_connections
"""
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, DateTime,
    ForeignKey, Boolean, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database.base import Base


class BankConnection(Base):
    """OAuth connections to TrueLayer API."""
    __tablename__ = "bank_connections"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    provider_id = Column(String, nullable=False)
    provider_name = Column(String, nullable=False)
    access_token = Column(Text, nullable=True)  # ENCRYPTED
    refresh_token = Column(Text, nullable=True)  # ENCRYPTED
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    connection_status = Column(String, nullable=True, default="authorization_required")
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    accounts = relationship("TrueLayerAccount", back_populates="connection", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BankConnection(id={self.id}, provider={self.provider_id}, status={self.connection_status})>"


class TrueLayerAccount(Base):
    """Bank accounts discovered from TrueLayer API."""
    __tablename__ = "truelayer_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    connection_id = Column(Integer, ForeignKey("bank_connections.id"), nullable=False)
    account_id = Column(String, nullable=False)  # TrueLayer account ID
    account_type = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    currency = Column(String, nullable=False)
    account_number_json = Column(JSONB, nullable=True)
    provider_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_synced_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    connection = relationship("BankConnection", back_populates="accounts")
    transactions = relationship("TrueLayerTransaction", back_populates="account", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TrueLayerAccount(id={self.id}, name={self.display_name})>"


class TrueLayerTransaction(Base):
    """Bank transactions synced from TrueLayer API."""
    __tablename__ = "truelayer_transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("truelayer_accounts.id"), nullable=False)
    transaction_id = Column(String, nullable=False)
    normalised_provider_transaction_id = Column(String, nullable=False, unique=True)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    description = Column(Text, nullable=False)
    amount = Column(Numeric, nullable=False)
    currency = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)
    transaction_category = Column(String, nullable=True)
    merchant_name = Column(String, nullable=True)
    running_balance = Column(Numeric, nullable=True)
    pre_enrichment_status = Column(String(20), nullable=True, default="None")
    metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    account = relationship("TrueLayerAccount", back_populates="transactions")

    # Indexes
    __table_args__ = (
        Index("idx_truelayer_txn_account", "account_id"),
        Index("idx_truelayer_txn_timestamp", "timestamp"),
        Index("idx_truelayer_txn_normalised_id", "normalised_provider_transaction_id", unique=True),
    )

    def __repr__(self):
        return f"<TrueLayerTransaction(id={self.id}, amount={self.amount}, desc={self.description[:30]})>"


class TrueLayerBalance(Base):
    """Historical snapshots of account balances."""
    __tablename__ = "truelayer_balances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(Integer, ForeignKey("truelayer_accounts.id"), nullable=False)
    current_balance = Column(Numeric, nullable=False)
    available_balance = Column(Numeric, nullable=True)
    overdraft = Column(Numeric, nullable=True)
    currency = Column(String, nullable=False)
    snapshot_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<TrueLayerBalance(account_id={self.account_id}, balance={self.current_balance})>"
```

**Step 4: Update models __init__.py and Alembic env.py**

```python
# backend/database/models/__init__.py
from .user import User
from .category import Category, CategoryKeyword
from .truelayer import (
    BankConnection, TrueLayerAccount, TrueLayerTransaction, TrueLayerBalance
)

__all__ = [
    "User", "Category", "CategoryKeyword",
    "BankConnection", "TrueLayerAccount", "TrueLayerTransaction", "TrueLayerBalance"
]
```

```python
# backend/alembic/env.py (add import after Base import)
from database.models import (
    User, Category, CategoryKeyword,
    BankConnection, TrueLayerAccount, TrueLayerTransaction, TrueLayerBalance
)
```

**Step 5: Run tests**

Run: `pytest tests/test_models/test_truelayer.py -v`
Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add backend/database/models/truelayer.py tests/test_models/test_truelayer.py
git commit -m "feat(models): add TrueLayer core models (connections, accounts, transactions)"
```

---

## Phase 2: Integration-Specific Models

### Task 2.1: Create Amazon Models

**Files:**
- Create: `backend/database/models/amazon.py`
- Create: `tests/test_models/test_amazon.py`

**Step 1-6:** Follow same pattern as Task 1.3:
1. Write failing test for AmazonOrder, AmazonReturn, AmazonBusinessConnection, etc.
2. Run test → FAIL
3. Implement models with proper columns, indexes, relationships
4. Update __init__.py
5. Run test → PASS
6. Commit

**Models to create:**
- `AmazonOrder` (maps to amazon_orders)
- `AmazonReturn` (maps to amazon_returns)
- `AmazonBusinessConnection` (maps to amazon_business_connections)
- `AmazonBusinessOrder` (maps to amazon_business_orders)
- `AmazonBusinessLineItem` (maps to amazon_business_line_items)
- `TrueLayerAmazonTransactionMatch` (maps to truelayer_amazon_transaction_matches)

**Commit message:** `feat(models): add Amazon models for orders, returns, and business integration`

---

### Task 2.2: Create Apple Models

**Files:**
- Create: `backend/database/models/apple.py`
- Create: `tests/test_models/test_apple.py`

**Models to create:**
- `AppleTransaction` (maps to apple_transactions)
- `AppleTransactionMatch` (maps to apple_transaction_matches)

**Commit message:** `feat(models): add Apple models for App Store purchases and matching`

---

### Task 2.3: Create Gmail Models

**Files:**
- Create: `backend/database/models/gmail.py`
- Create: `tests/test_models/test_gmail.py`

**Models to create:**
- `GmailConnection` (maps to gmail_connections)
- `GmailReceipt` (maps to gmail_receipts)
- `GmailEmailContent` (maps to gmail_email_content)
- `PDFAttachment` (maps to pdf_attachments)

**Commit message:** `feat(models): add Gmail models for receipt parsing and PDF storage`

---

### Task 2.4: Create Enrichment Models

**Files:**
- Create: `backend/database/models/enrichment.py`
- Create: `tests/test_models/test_enrichment.py`

**Models to create:**
- `TransactionEnrichmentSource` (maps to transaction_enrichment_sources)
- `EnrichmentCache` (maps to enrichment_cache)

**Commit message:** `feat(models): add enrichment models for LLM categorization`

---

## Phase 3: Generate Initial Alembic Migration

### Task 3.1: Generate Migration from Models

**Files:**
- Create: `backend/alembic/versions/XXXX_initial_schema.py`

**Step 1: Ensure all models are imported in alembic/env.py**

Check that all model imports are present.

**Step 2: Generate migration**

Run: `cd backend && alembic revision --autogenerate -m "Initial schema from SQLAlchemy models"`
Expected: Migration file created in alembic/versions/

**Step 3: Review generated migration**

Review the generated SQL to ensure:
- All tables are included
- Column types match DATABASE_SCHEMA.md
- Indexes and constraints are correct
- No tables are missing

**Step 4: DO NOT APPLY migration yet**

This migration is for NEW databases only. Existing database already has schema.

**Step 5: Mark current database as migrated**

Run: `cd backend && alembic stamp head`
Expected: Database marked as at current migration level

**Step 6: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(db): generate initial Alembic migration from SQLAlchemy models"
```

---

## Phase 4: Migrate database_postgres.py Functions (Incremental)

**Strategy:** Create parallel SQLAlchemy-based functions alongside existing psycopg2 functions. Gradually migrate callers to new functions.

### Task 4.1: Create SQLAlchemy Helper Functions

**Files:**
- Create: `backend/database/operations/__init__.py`
- Create: `backend/database/operations/category.py`

**Step 1: Create operations package**

```bash
mkdir -p backend/database/operations
touch backend/database/operations/__init__.py
```

**Step 2: Write test for get_all_categories**

```python
# tests/test_operations/test_category.py
import pytest
from database.base import SessionLocal, engine, Base
from database.models.category import Category
from database.operations.category import get_all_categories


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()

    # Seed test data
    categories = [
        Category(name="Groceries", rule_pattern="tesco"),
        Category(name="Transport", rule_pattern="uber"),
    ]
    session.add_all(categories)
    session.commit()

    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


def test_get_all_categories(db_session):
    """Test retrieving all categories."""
    categories = get_all_categories(db_session)

    assert len(categories) == 2
    assert categories[0]["name"] == "Groceries"
    assert categories[1]["name"] == "Transport"
```

**Step 3: Run test**

Run: `pytest tests/test_operations/test_category.py -v`
Expected: FAIL - function doesn't exist

**Step 4: Implement SQLAlchemy version**

```python
# backend/database/operations/category.py
"""
Category operations using SQLAlchemy.

These functions replace the psycopg2-based category operations
in database_postgres.py.
"""
from sqlalchemy.orm import Session
from database.models.category import Category, CategoryKeyword


def get_all_categories(session: Session) -> list[dict]:
    """
    Get all categories from database.

    Returns list of dicts to match existing API.
    """
    categories = session.query(Category).all()
    return [
        {
            "id": cat.id,
            "name": cat.name,
            "rule_pattern": cat.rule_pattern,
            "ai_suggested": cat.ai_suggested
        }
        for cat in categories
    ]


def get_category_keywords(session: Session) -> list[dict]:
    """Get all category keywords."""
    keywords = session.query(CategoryKeyword).all()
    return [
        {
            "id": kw.id,
            "category_name": kw.category_name,
            "keyword": kw.keyword,
            "created_at": kw.created_at.isoformat() if kw.created_at else None
        }
        for kw in keywords
    ]


def add_category_keyword(
    session: Session,
    category_name: str,
    keyword: str
) -> dict:
    """Add a keyword to a category."""
    kw = CategoryKeyword(category_name=category_name, keyword=keyword)
    session.add(kw)
    session.commit()

    return {
        "id": kw.id,
        "category_name": kw.category_name,
        "keyword": kw.keyword
    }


# More functions...
```

**Step 5: Run test**

Run: `pytest tests/test_operations/test_category.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/database/operations/ tests/test_operations/
git commit -m "feat(db): add SQLAlchemy-based category operations"
```

---

### Task 4.2: Create Adapter in database_postgres.py

**Files:**
- Modify: `backend/database_postgres.py`

**Step 1: Add SQLAlchemy imports**

```python
# backend/database_postgres.py (add at top after existing imports)
from database.base import SessionLocal
from database.operations import category as category_ops
```

**Step 2: Add session context manager**

```python
# backend/database_postgres.py (add after get_db())
@contextmanager
def get_sqlalchemy_session():
    """Get SQLAlchemy session (new approach)."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Step 3: Add adapter function**

```python
# backend/database_postgres.py (modify existing function)
def get_all_categories():
    """
    Get all categories from database.

    Now uses SQLAlchemy instead of raw psycopg2.
    """
    with get_sqlalchemy_session() as session:
        return category_ops.get_all_categories(session)
```

**Step 4: Test existing code still works**

Run Flask app and verify `/api/categories` endpoint works

**Step 5: Commit**

```bash
git add backend/database_postgres.py
git commit -m "refactor(db): migrate get_all_categories to SQLAlchemy"
```

---

### Task 4.3-4.N: Migrate Remaining Functions

**Pattern:** For each of the 242 functions in database_postgres.py:

1. **Group by domain** (TrueLayer, Amazon, Gmail, etc.)
2. **Create operations module** (e.g., `operations/truelayer.py`)
3. **Write tests** for SQLAlchemy versions
4. **Implement** SQLAlchemy operations
5. **Update adapter** in database_postgres.py
6. **Test** existing code still works
7. **Commit** per domain

**Domains to migrate (in order):**
- ✅ Category operations (Task 4.1-4.2)
- Enrichment operations
- Transaction operations
- TrueLayer operations
- Amazon operations
- Apple operations
- Gmail operations
- Legacy operations (mark as deprecated)

**Estimated commits:** ~12-15 (one per domain group)

---

## Phase 5: Update MCP Components

### Task 5.1: Update Celery Tasks to Use SQLAlchemy

**Files:**
- Modify: `backend/tasks/*.py` (enrichment_tasks.py, matching_tasks.py, etc.)

**Pattern for each file:**
1. Import SQLAlchemy session instead of psycopg2
2. Replace database.get_db() with get_sqlalchemy_session()
3. Use operations functions instead of raw SQL
4. Test task execution

**Commit per task file:** `refactor(tasks): migrate {task_name} to SQLAlchemy`

---

### Task 5.2: Update MCP Components to Use SQLAlchemy

**Files:**
- Modify: `backend/mcp/*.py` (all MCP components)

**Pattern:**
1. Update imports
2. Replace database calls
3. Test component functionality

**Commit per MCP domain:** `refactor(mcp): migrate {component} to SQLAlchemy`

---

## Phase 6: Final Migration & Cleanup

### Task 6.1: Remove psycopg2 Code from database_postgres.py

**Files:**
- Modify: `backend/database_postgres.py`

**Step 1: Verify all callers migrated**

Search codebase for usage of old functions.

**Step 2: Remove raw SQL functions**

Replace with thin wrappers to operations modules.

**Step 3: Remove connection pool**

Keep only for legacy code if needed.

**Step 4: Rename file**

Rename `database_postgres.py` to `database_legacy.py` or remove entirely.

**Step 5: Commit**

```bash
git commit -m "refactor(db): complete migration to SQLAlchemy, remove raw psycopg2 code"
```

---

### Task 6.2: Update DATABASE_SCHEMA.md

**Files:**
- Modify: `.claude/docs/database/DATABASE_SCHEMA.md`

**Step 1: Add migration note**

Add section about SQLAlchemy migration at top.

**Step 2: Update ORM reference**

Change "Direct SQL via psycopg2" to "SQLAlchemy 2.0 ORM".

**Step 3: Add model reference**

Link to model files for each table.

**Step 4: Commit**

```bash
git commit -m "docs(db): update DATABASE_SCHEMA.md to reflect SQLAlchemy migration"
```

---

### Task 6.3: Update SCHEMA_ENFORCEMENT.md

**Files:**
- Modify: `.claude/docs/database/SCHEMA_ENFORCEMENT.md`

**Step 1: Add Alembic migration guidelines**

Document how to create migrations going forward.

**Step 2: Add SQLAlchemy best practices**

Document model creation patterns.

**Step 3: Commit**

```bash
git commit -m "docs(db): add SQLAlchemy and Alembic guidelines to SCHEMA_ENFORCEMENT.md"
```

---

## Phase 7: Advanced Features (Optional)

### Task 7.1: Add Async SQLAlchemy Support

For high-performance async operations with asyncio.

### Task 7.2: Add Query Result Caching

Integrate with Redis for query caching.

### Task 7.3: Add Database Monitoring

Add SQLAlchemy event listeners for performance monitoring.

---

## Testing Strategy

### Unit Tests
- ✅ Test each model independently
- ✅ Test all operations functions
- ✅ Test relationships and cascades

### Integration Tests
- Test full workflows (sync, match, enrich)
- Test MCP server operations
- Test API endpoints

### Migration Validation
- Compare old vs new results for same queries
- Verify data integrity after migration
- Performance benchmarks (should be comparable or better)

---

## Rollback Plan

If migration causes issues:

1. **Partial rollback:** Revert specific domain operations
2. **Full rollback:** Revert to psycopg2-only code
3. **Database rollback:** Use Alembic downgrade
4. **Emergency:** Restore database from backup

---

## Success Criteria

- ✅ All 242 database functions migrated to SQLAlchemy
- ✅ All tests passing (unit + integration)
- ✅ All MCP components working with SQLAlchemy
- ✅ All Celery tasks working with SQLAlchemy
- ✅ Alembic configured and generating migrations
- ✅ Documentation updated
- ✅ No performance regression
- ✅ psycopg2 code removed (except legacy if needed)

---

## Timeline Estimate

**Phase 0:** 2-4 hours (setup)
**Phase 1:** 6-8 hours (core models)
**Phase 2:** 8-12 hours (integration models)
**Phase 3:** 2-3 hours (Alembic migration)
**Phase 4:** 20-30 hours (migrate 242 functions)
**Phase 5:** 15-20 hours (update MCP components)
**Phase 6:** 4-6 hours (cleanup & docs)

**Total:** 57-83 hours (~7-10 full working days)

**Recommendation:** Spread over 2-3 weeks with incremental commits.

---

## Migration Best Practices

1. **Never break existing code** - Always maintain backward compatibility
2. **Test early, test often** - Write tests BEFORE migrating each function
3. **Commit frequently** - Small, focused commits per domain
4. **Document as you go** - Update docs alongside code changes
5. **Monitor performance** - Compare query performance old vs new
6. **Pair operations** - Keep old and new side-by-side during transition
7. **Use type hints** - Add type annotations to all new code
8. **Follow DRY** - Extract common patterns into utilities

---

## ★ Key Insights ──────────────────────────────────────

**Architecture Decisions:**
- **Coexistence pattern** allows zero-downtime migration - psycopg2 and SQLAlchemy run side-by-side
- **Adapter pattern** in database_postgres.py preserves existing API surface while switching implementation
- **Operations modules** provide clean separation between models (schema) and operations (business logic)

**Why this approach:**
- **242 functions + 218 caller files** = high-risk big-bang migration would likely fail
- **Domain-driven incremental migration** reduces risk and allows continuous deployment
- **TDD approach** ensures no regressions during migration

**Critical details:**
- Must use **RealDictCursor equivalents** (convert to dicts) to maintain API compatibility
- **JSONB columns** require special handling in SQLAlchemy (use postgresql.JSONB type)
- **Timezone-aware datetimes** critical for TrueLayer data (DateTime(timezone=True))

─────────────────────────────────────────────────────────
