---
name: database-migration
description: Ensure ultimate engineering quality for SQLAlchemy + Alembic database migrations with automated documentation
invocation: Use when creating, modifying, or validating database schema migrations
---

# Database Migration Quality Skill

**Purpose:** Guide safe, tested, documented database migrations with paranoid stepwise thinking.

**When to use:**
- Creating new Alembic migrations
- Modifying existing schema
- Adding/changing columns, constraints, indexes
- Data type transformations

**Safety level:** Balanced (critical checks + fast iteration)

---

## Pre-Migration Checklist (Phase 0)

**Before starting any migration, validate:**

### 1. Schema Understanding
- [ ] Read `.claude/docs/database/DATABASE_SCHEMA.md` for current schema
- [ ] Understand affected tables and relationships
- [ ] Check for existing indexes, constraints, and triggers

### 2. Risk Assessment
Categorize your operation:

**HIGH RISK** (extra validation required):
- Changing column data types
- Adding NOT NULL constraints
- Adding UNIQUE constraints
- Dropping columns/tables
- Changing foreign key relationships

**LOW RISK** (standard workflow):
- Adding nullable columns
- Adding indexes
- Creating new tables

### 3. Requirement Clarity
- [ ] Understand WHY the change is needed
- [ ] Confirm expected behavior with user if ambiguous
- [ ] Document the business requirement

### 4. Code Impact Analysis
```bash
# Find all files that query affected tables
grep -r "SELECT.*FROM table_name" --include="*.py"
grep -r "INSERT INTO table_name" --include="*.py"
grep -r "TableName" --include="*.py"  # SQLAlchemy model references
```

---

## Phase 1: Generate Migration

### 1.1 Update SQLAlchemy Models
- Modify `backend/database/models/<domain>.py`
- Ensure model is imported in `backend/database/models/__init__.py`
- Use correct column types:
  - `sa.Numeric(precision, scale)` for decimals (NOT Float)
  - `sa.DateTime(timezone=True)` for timestamps
  - `postgresql.JSONB()` for JSON data (NOT Text)
  - `sa.String(length)` for bounded text

**Example:**
```python
from sqlalchemy import Column, String, Numeric, DateTime
from sqlalchemy.dialects import postgresql

class TrueLayerTransaction(Base):
    __tablename__ = 'truelayer_transactions'

    # Add new column
    pre_enrichment_status = Column(String(50), nullable=True)
```

### 1.2 Generate Alembic Migration
```bash
cd backend
source venv/bin/activate
alembic revision --autogenerate -m "add_pre_enrichment_status_column"
```

### 1.3 Review Generated Migration

**CRITICAL: Never trust autogenerate blindly**

Open `backend/alembic/versions/<revision>_*.py` and verify:

- [ ] **Correct upgrade() operations** - Does it match your model changes?
- [ ] **NO `downgrade() = pass`** - Must implement proper rollback
- [ ] **Correct column types** - NUMERIC not FLOAT, JSONB not TEXT
- [ ] **No unexpected operations** - Autogenerate sometimes detects unintended changes
- [ ] **Proper table names** - Match DATABASE_SCHEMA.md exactly

**Common autogenerate issues:**
- Type changes detected when none intended (check server_default, nullable)
- Missing `import sqlalchemy as sa` statements
- Incorrect PostgreSQL-specific types

---

## Phase 2: Implement Rollback Safety

**MANDATORY:** Every migration MUST have a working `downgrade()` function.

### Common Templates

#### Adding a column:
```python
def upgrade():
    op.add_column('truelayer_transactions',
                  sa.Column('pre_enrichment_status', sa.String(50), nullable=True))

def downgrade():
    op.drop_column('truelayer_transactions', 'pre_enrichment_status')
```

#### Changing column type (HIGH RISK):
```python
def upgrade():
    # Multi-step: add temp, copy data, drop old, rename
    op.add_column('table_name', sa.Column('temp_col', sa.Integer(), nullable=True))
    op.execute("UPDATE table_name SET temp_col = CAST(old_col AS INTEGER)")
    # Verify conversion succeeded
    op.execute("SELECT COUNT(*) FROM table_name WHERE old_col IS NOT NULL AND temp_col IS NULL")
    op.drop_column('table_name', 'old_col')
    op.alter_column('table_name', 'temp_col', new_column_name='old_col')

def downgrade():
    # Reverse with data conversion
    op.add_column('table_name', sa.Column('temp_col', sa.String(50), nullable=True))
    op.execute("UPDATE table_name SET temp_col = CAST(old_col AS TEXT)")
    op.drop_column('table_name', 'old_col')
    op.alter_column('table_name', 'temp_col', new_column_name='old_col')
```

#### Adding a unique constraint (HIGH RISK):
```python
def upgrade():
    # Pre-check: ensure no duplicates exist
    # SELECT col, COUNT(*) FROM table GROUP BY col HAVING COUNT(*) > 1
    op.create_unique_constraint('uq_table_col', 'table_name', ['column_name'])

def downgrade():
    op.drop_constraint('uq_table_col', 'table_name', type_='unique')
```

#### Adding a foreign key (MEDIUM RISK):
```python
def upgrade():
    # Add nullable FK column first
    op.add_column('child_table', sa.Column('parent_id', sa.Integer(), nullable=True))
    # Backfill existing data
    op.execute("UPDATE child_table SET parent_id = ...")
    # Add constraint
    op.create_foreign_key('fk_child_parent', 'child_table', 'parent_table',
                          ['parent_id'], ['id'])
    # Make NOT NULL only after backfill
    op.alter_column('child_table', 'parent_id', nullable=False)

def downgrade():
    op.drop_constraint('fk_child_parent', 'child_table', type_='foreignkey')
    op.drop_column('child_table', 'parent_id')
```

### Test Rollback Locally

**CRITICAL:** Test the up/down/up cycle before committing:

```bash
alembic upgrade head     # Apply migration
alembic downgrade -1     # Roll back
alembic upgrade head     # Re-apply (must succeed)
```

If any step fails, fix the migration before proceeding.

---

## Phase 3: Add Tests

### Test File Location
`backend/tests/test_migrations/test_<revision>_<description>.py`

**Example:** `test_a1b2c3d4_add_pre_enrichment_status.py`

### Required Tests

Every migration MUST have these 4 tests:

1. **test_upgrade_creates_expected_schema()** - Verify upgrade() works
2. **test_downgrade_removes_changes()** - Verify rollback works
3. **test_migration_idempotency()** - Verify up → down → up cycle
4. **test_data_preservation()** - For data transformations (type changes, etc.)

### Test Template

```python
"""Test migration a1b2c3d4: add pre_enrichment_status column"""
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from database.base import engine


@pytest.fixture(scope="module")
def alembic_config():
    """Load Alembic configuration."""
    config = Config("backend/alembic.ini")
    return config


def test_upgrade_creates_expected_schema(alembic_config):
    """Test that upgrade() adds the new column."""
    # Apply migration
    command.upgrade(alembic_config, "a1b2c3d4")

    # Verify schema change
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('truelayer_transactions')]

    assert 'pre_enrichment_status' in columns, "Column should exist after upgrade"

    # Verify column type
    col_info = next(c for c in inspector.get_columns('truelayer_transactions')
                    if c['name'] == 'pre_enrichment_status')
    assert col_info['type'].__class__.__name__ == 'VARCHAR'
    assert col_info['nullable'] is True


def test_downgrade_removes_changes(alembic_config):
    """Test that downgrade() removes the column."""
    # Ensure migration is applied
    command.upgrade(alembic_config, "a1b2c3d4")

    # Downgrade
    command.downgrade(alembic_config, "-1")

    # Verify column removed
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('truelayer_transactions')]

    assert 'pre_enrichment_status' not in columns, "Column should not exist after downgrade"


def test_migration_idempotency(alembic_config):
    """Test that up → down → up cycle works correctly."""
    # Start clean
    command.downgrade(alembic_config, "base")

    # Apply migration
    command.upgrade(alembic_config, "a1b2c3d4")

    # Rollback
    command.downgrade(alembic_config, "-1")

    # Re-apply (should not fail)
    command.upgrade(alembic_config, "a1b2c3d4")

    # Final verification
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('truelayer_transactions')]
    assert 'pre_enrichment_status' in columns


def test_data_preservation(alembic_config):
    """Test that existing data is preserved during migration (if applicable)."""
    # Only needed for type changes or data transformations
    # For simple column additions, this test can be skipped

    # Insert test data before migration
    with engine.connect() as conn:
        conn.execute(text(
            "INSERT INTO truelayer_transactions (id, amount, ...) VALUES (...)"
        ))
        conn.commit()

    # Apply migration
    command.upgrade(alembic_config, "a1b2c3d4")

    # Verify data still exists and is correct
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM truelayer_transactions"))
        count = result.scalar()
        assert count > 0, "Data should be preserved"
```

### Run Migration Tests

```bash
cd backend
source venv/bin/activate
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest tests/test_migrations/test_a1b2c3d4_*.py -v
```

**All tests must pass before proceeding to Phase 4.**

---

## Phase 4: Update Documentation

### 4.1 Update DATABASE_SCHEMA.md

**Location:** `.claude/docs/database/DATABASE_SCHEMA.md`

#### Add to Schema Changes Log (top of file)

```markdown
### 2025-12-28: Add pre_enrichment_status tracking

- **Change:** Added `pre_enrichment_status` column to `truelayer_transactions`
- **Reason:** Track whether transactions have pre-enrichment data from receipts/orders
- **Tables Affected:** `truelayer_transactions`
- **Columns Modified:** Added `pre_enrichment_status VARCHAR(50) NULL`
- **Migration:** `backend/alembic/versions/a1b2c3d4_add_pre_enrichment_status.py`
- **Alembic Revision:** `a1b2c3d4`
- **Impact:** Non-breaking (nullable column)
- **Files Updated:**
  - `backend/database/models/truelayer.py`
  - `backend/mcp/truelayer_sync.py` (sets status during sync)
```

#### Update Table Definition

Find the relevant table section and add the new column:

```markdown
### 4. `truelayer_transactions`

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | SERIAL | NO | nextval | Primary key |
| ... | ... | ... | ... | ... |
| pre_enrichment_status | VARCHAR(50) | YES | NULL | Tracks source of pre-enrichment data |

**Changes:**
- 2025-12-28: Added `pre_enrichment_status` for tracking receipt/order matches
```

### 4.2 Update Code Files

Find all files that query the affected table:

```bash
grep -r "SELECT.*FROM truelayer_transactions" --include="*.py"
grep -r "INSERT INTO truelayer_transactions" --include="*.py"
grep -r "TrueLayerTransaction" --include="*.py"
```

**For each file:**
- [ ] Update SELECT statements to include new column if needed
- [ ] Update INSERT statements to provide value for new column if needed
- [ ] Update SQLAlchemy ORM queries
- [ ] Update related tests

### 4.3 Commit Migration with Documentation

```bash
git add backend/alembic/versions/a1b2c3d4_*.py
git add .claude/docs/database/DATABASE_SCHEMA.md
git add backend/database/models/truelayer.py
git add backend/tests/test_migrations/test_a1b2c3d4_*.py
git add backend/mcp/truelayer_sync.py  # Or other affected files

git commit -m "feat(db): add pre_enrichment_status column to truelayer_transactions

- Add migration a1b2c3d4: add pre_enrichment_status tracking
- Update DATABASE_SCHEMA.md with changelog and table definition
- Add migration tests (upgrade, downgrade, idempotency)
- Update truelayer_sync to set status during sync

Migration reversible: Yes
Data loss risk: None
Tests: 4/4 passing"
```

---

## Phase 5: Post-Migration Validation

### 5.1 Verify Migration Execution

```bash
# Check current migration version
alembic current

# Expected output: a1b2c3d4 (head)
```

**Inspect schema in PostgreSQL:**
```bash
docker exec -it spending-postgres psql -U spending_user -d spending_db

\d truelayer_transactions
# Should show new column with correct type and constraints

\q
```

### 5.2 Run Full Test Suite

```bash
cd backend
source venv/bin/activate
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest -v
```

**All tests must pass.**

### 5.3 Prevent the 6 Critical Bugs

**Validate your migration avoids these common bugs:**

#### 1. Dict vs Scalar
❌ **Bad:** Inserting Python dict into scalar column
```python
# Don't do this!
txn.metadata_field = {"key": "value"}  # If column is TEXT
```

✅ **Good:** Use JSONB column type OR serialize to JSON string
```python
import json
txn.metadata_field = json.dumps({"key": "value"})
# Or use JSONB column: postgresql.JSONB()
```

#### 2. JSON Serialization
❌ **Bad:** Using str(dict) for JSON
```python
metadata = str({"key": "value"})  # Results in "{'key': 'value'}" (invalid JSON)
```

✅ **Good:** Use json.dumps()
```python
import json
metadata = json.dumps({"key": "value"})  # Results in '{"key":"value"}' (valid JSON)
```

#### 3. Column Name Typos
❌ **Bad:** Typo in column name
```python
op.add_column('table', sa.Column('pre_enrchment_status', ...))  # Typo!
```

✅ **Good:** Verify against DATABASE_SCHEMA.md
```python
op.add_column('table', sa.Column('pre_enrichment_status', ...))
```

**Verification:**
```bash
grep -i "pre_enrichment_status" .claude/docs/database/DATABASE_SCHEMA.md
```

#### 4. Timezone Handling
❌ **Bad:** Naive datetime without timezone
```python
from datetime import datetime
created_at = Column(DateTime)  # No timezone=True
# Later: datetime.now()  # Naive datetime
```

✅ **Good:** Timezone-aware datetimes
```python
from datetime import datetime, timezone
created_at = Column(DateTime(timezone=True))
# Later: datetime.now(timezone.utc)
```

#### 5. Missing Imports
❌ **Bad:** Forgetting to import new model
```python
# backend/database/models/__init__.py missing import
```

✅ **Good:** Add import and verify
```python
from .truelayer import TrueLayerTransaction  # Add to __init__.py

# Verify:
python3 -m py_compile backend/database/models/truelayer.py
```

#### 6. Token Expiry
❌ **Bad:** No OAuth token refresh logic
```python
# Use access_token without checking expiry
```

✅ **Good:** Implement refresh before API calls
```python
if connection.token_expires_at < datetime.now(timezone.utc):
    refresh_token(connection)
```

### Final Checklist

- [ ] No dict objects assigned to scalar columns
- [ ] No str(dict) for JSONB (use json.dumps())
- [ ] Column names verified against DATABASE_SCHEMA.md
- [ ] All DateTime columns use timezone=True
- [ ] All datetime values use datetime.now(timezone.utc)
- [ ] All imports compile without errors
- [ ] OAuth token refresh implemented (if applicable)

---

## Expert Resources

**Consult these resources when:**

### Design Questions
- "Should I normalize this?" → [Relational Design Patterns](https://www.odbms.org/wp-content/uploads/2013/11/PP2.pdf)
- "How to model temporal data?" → [Anchor Modeling](https://en.wikipedia.org/wiki/Anchor_modeling)
- "Best SQLAlchemy pattern?" → [SQLAlchemy Architectural Patterns](https://techspot.zzzeek.org/2012/02/07/patterns-implemented-by-sqlalchemy/)
- "Advanced modeling?" → [Advanced Data Modeling Techniques](https://dataengineeracademy.com/blog/advanced-data-modeling-techniques/)

### Migration Questions
- "How to handle backfills?" → [Alembic Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html)
- "Zero-downtime migrations?" → [Alembic Best Practices](https://www.pingcap.com/article/best-practices-alembic-schema-migration/)
- "Complex transformations?" → [Alembic Developer Guide](https://medium.com/@tejpal.abhyuday/alembic-database-migrations-the-complete-developers-guide-d3fc852a6a9e)

### Anti-Patterns
- "What to avoid?" → [SQL Anti-Patterns](https://pragprog.com/titles/bksap/sql-antipatterns/)
- "Database refactoring?" → [Database Refactoring](https://en.wikipedia.org/wiki/Database_refactoring)

### SQLAlchemy Documentation
- "Core reference?" → [SQLAlchemy Docs](https://docs.sqlalchemy.org)
- "Performance tips?" → [SQLAlchemy Performance](https://deepnote.com/blog/ultimate-guide-to-sqlalchemy-library-in-python)

---

## Common Scenarios

### Scenario 1: Adding Simple Column
**Risk:** LOW (nullable column)

**Steps:**
1. Update model: Add `sa.Column('col_name', sa.String(100), nullable=True)`
2. Generate migration: `alembic revision --autogenerate -m "add_col_name"`
3. Review and implement downgrade()
4. Test rollback: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
5. Write tests (upgrade, downgrade, idempotency)
6. Update DATABASE_SCHEMA.md
7. Commit with migration, tests, and docs

**Time:** ~20 minutes

---

### Scenario 2: Changing Column Type
**Risk:** HIGH (data conversion)

**Required:** Multi-step migration, data validation, precision checks

**Template:**
```python
def upgrade():
    # Step 1: Add temporary column
    op.add_column('table', sa.Column('temp_col', sa.Integer(), nullable=True))

    # Step 2: Copy and convert data
    op.execute("UPDATE table SET temp_col = CAST(old_col AS INTEGER)")

    # Step 3: Verify conversion (check for NULLs where shouldn't be)
    result = op.get_bind().execute(
        "SELECT COUNT(*) FROM table WHERE old_col IS NOT NULL AND temp_col IS NULL"
    )
    if result.scalar() > 0:
        raise Exception("Data conversion failed - NULL values detected")

    # Step 4: Drop old column
    op.drop_column('table', 'old_col')

    # Step 5: Rename temp to final name
    op.alter_column('table', 'temp_col', new_column_name='old_col')
```

**Time:** ~45 minutes (with validation)

---

### Scenario 3: Adding Unique Constraint
**Risk:** HIGH (may fail if duplicates exist)

**Pre-Check:**
```sql
SELECT col, COUNT(*)
FROM table
GROUP BY col
HAVING COUNT(*) > 1;
```

**Steps:**
1. Run pre-check query to find duplicates
2. If duplicates exist, clean them up first (separate migration)
3. Create unique index (can be done online in PostgreSQL)
4. Add constraint

**Template:**
```python
def upgrade():
    # Pre-check (will fail migration if duplicates found)
    result = op.get_bind().execute(
        "SELECT COUNT(*) FROM (SELECT col FROM table GROUP BY col HAVING COUNT(*) > 1) AS dupes"
    )
    if result.scalar() > 0:
        raise Exception("Duplicate values exist - clean up before adding constraint")

    # Create unique constraint
    op.create_unique_constraint('uq_table_col', 'table', ['col'])

def downgrade():
    op.drop_constraint('uq_table_col', 'table', type_='unique')
```

**Time:** ~30 minutes (+ cleanup time if duplicates exist)

---

### Scenario 4: Adding Foreign Key
**Risk:** MEDIUM (orphan check required)

**Pre-Check:**
```sql
SELECT COUNT(*)
FROM child_table
LEFT JOIN parent_table ON child_table.parent_id = parent_table.id
WHERE child_table.parent_id IS NOT NULL
  AND parent_table.id IS NULL;
```

**Steps:**
1. Add nullable FK column
2. Backfill existing data
3. Verify no orphans
4. Add FK constraint
5. Make NOT NULL (if required)

**Template:**
```python
def upgrade():
    # Step 1: Add nullable column
    op.add_column('child_table', sa.Column('parent_id', sa.Integer(), nullable=True))

    # Step 2: Backfill (adjust logic as needed)
    op.execute("UPDATE child_table SET parent_id = ...")

    # Step 3: Check for orphans
    result = op.get_bind().execute(
        """SELECT COUNT(*) FROM child_table
           LEFT JOIN parent_table ON child_table.parent_id = parent_table.id
           WHERE child_table.parent_id IS NOT NULL AND parent_table.id IS NULL"""
    )
    if result.scalar() > 0:
        raise Exception("Orphan records detected - fix backfill logic")

    # Step 4: Add constraint
    op.create_foreign_key('fk_child_parent', 'child_table', 'parent_table',
                          ['parent_id'], ['id'])

    # Step 5: Make NOT NULL (if appropriate)
    # op.alter_column('child_table', 'parent_id', nullable=False)

def downgrade():
    op.drop_constraint('fk_child_parent', 'child_table', type_='foreignkey')
    op.drop_column('child_table', 'parent_id')
```

**Time:** ~40 minutes (with backfill and validation)

---

## Summary

This skill ensures every database migration is:
- ✅ **Safe** - Tested rollback, no data loss
- ✅ **Tested** - Upgrade, downgrade, idempotency verified
- ✅ **Documented** - DATABASE_SCHEMA.md updated with changelog
- ✅ **Bug-free** - 6 critical bugs prevented by checklist

**Follow all 5 phases rigorously** to maintain engineering quality and prevent production issues.
