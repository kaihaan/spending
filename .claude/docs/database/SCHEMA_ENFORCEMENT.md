# Database Schema Enforcement Guide

**Purpose:** Ensure all code strictly adheres to the documented database schema and prevents schema violations.

**Document Location:** `/docs/DATABASE_SCHEMA.md` (source of truth)

---

## Pre-Commit Checklist

Before submitting any code that modifies the database, run through this checklist:

### 1. Schema Changes
- [ ] Have I modified any database table structure?
  - Added columns?
  - Removed columns?
  - Changed column types?
  - Changed nullable constraints?
  - Added/removed indexes?

If YES to any above:
- [ ] Updated `DATABASE_SCHEMA.md` with change details
- [ ] Added entry to "Schema Changes" section with date
- [ ] Created migration script (if permanent change)
- [ ] Tested migration on local database
- [ ] Updated all database functions in `database_postgres.py`

### 2. Code Changes Affecting Schema Usage
- [ ] Am I reading from the database?
  - [ ] Are all columns in SELECT statements documented?
  - [ ] Are field names correct (no typos)?
  - [ ] Using `RealDictCursor` for dict-based access?

- [ ] Am I writing to the database?
  - [ ] All INSERT column names match schema?
  - [ ] All data types match documented types?
  - [ ] For JSONB: using `json.dumps()` not `str()`?
  - [ ] For encrypted fields: using `encrypt_token()` not storing raw?
  - [ ] For timestamps: using `datetime.now(timezone.utc)` not `datetime.utcnow()`?

- [ ] Am I filtering/querying?
  - [ ] Are column names spelled correctly?
  - [ ] Using parameterized queries (`%s` placeholders)?
  - [ ] Never using string formatting for SQL?

### 3. TrueLayer Integration Specific
- [ ] Handling running_balance correctly?
  - [ ] Extracting scalar from dict if needed?
  - [ ] Not passing dict directly to INSERT?

- [ ] Handling metadata correctly?
  - [ ] Using `json.dumps(metadata)` for JSONB?
  - [ ] Not using `str(metadata)`?

- [ ] Token handling?
  - [ ] Encrypting before storage?
  - [ ] Decrypting before use?
  - [ ] Checking expiry before use?
  - [ ] Never logging token values?

### 4. Documentation
- [ ] Updated `DATABASE_SCHEMA.md`?
- [ ] Added change log entry?
- [ ] Documented new columns/tables?
- [ ] Noted any breaking changes?
- [ ] Updated code examples if changed?

---

## Schema Violation Detection

### Common Errors and Solutions

#### Error: "column does not exist"
**Cause:** Using incorrect column name (typo or outdated schema)
**Solution:**
1. Check `DATABASE_SCHEMA.md` for correct column name
2. Check table definition section
3. Update code with correct name
4. Example fix:
```python
# WRONG
cursor.execute('SELECT normalised_provider_id FROM truelayer_transactions')

# CORRECT (check schema!)
cursor.execute('SELECT normalised_provider_transaction_id FROM truelayer_transactions')
```

#### Error: "can't adapt type 'dict'"
**Cause:** Passing Python dict to database when it expects scalar/JSON string
**Solutions:**

For JSONB columns:
```python
# WRONG
cursor.execute('INSERT INTO truelayer_transactions (..., metadata) VALUES (..., %s)',
    (..., metadata_dict))

# CORRECT
import json
cursor.execute('INSERT INTO truelayer_transactions (..., metadata) VALUES (..., %s)',
    (..., json.dumps(metadata_dict)))
```

For scalar columns (running_balance):
```python
# WRONG - running_balance from API is a dict
running_balance = txn.get('running_balance')  # {amount: 123, currency: "GBP"}
cursor.execute('INSERT INTO truelayer_transactions (..., running_balance) VALUES (..., %s)',
    (..., running_balance))  # ERROR: can't adapt dict

# CORRECT - extract the amount scalar
running_balance = txn.get('running_balance')
if isinstance(running_balance, dict):
    running_balance = running_balance.get('amount')
cursor.execute('INSERT INTO truelayer_transactions (..., running_balance) VALUES (..., %s)',
    (..., running_balance))
```

#### Error: "can't subtract offset-naive and offset-aware datetimes"
**Cause:** Mixing timezone-aware and timezone-naive datetime objects
**Solution:**
```python
from datetime import datetime, timezone

# WRONG
now = datetime.utcnow()  # Naive datetime
expires_at = datetime.fromisoformat(db_value)  # Might be aware
diff = expires_at - now  # ERROR!

# CORRECT - always use timezone-aware
from datetime import timezone
now = datetime.now(timezone.utc)  # Always aware

# If database value is naive, make it aware:
if expires_at.tzinfo is None:
    expires_at = expires_at.replace(tzinfo=timezone.utc)

diff = expires_at - now  # OK
```

#### Error: "duplicate key value violates unique constraint"
**Cause:** Trying to insert duplicate data (usually by normalised_provider_transaction_id)
**Solution:**
```python
# WRONG - No deduplication check
cursor.execute('INSERT INTO truelayer_transactions (...) VALUES (...)')

# CORRECT - Check for existing first
existing = database.get_truelayer_transaction_by_id(normalised_id)
if not existing:
    database.insert_truelayer_transaction(...)
else:
    # Handle duplicate (log, skip, or update)
    pass
```

---

## Query Validation Rules

### Rule 1: Column Names Must Match Schema Exactly
```python
# Read the table definition in DATABASE_SCHEMA.md FIRST
# Table: truelayer_transactions

# Valid columns (from schema):
# - id
# - account_id
# - transaction_id
# - normalised_provider_transaction_id  ← NOTE: "transaction" not "provider"
# - timestamp
# - description
# - amount
# - currency
# - transaction_type
# - transaction_category          ← NOTE: NOT "category"
# - merchant_name
# - running_balance
# - metadata
# - created_at

# CORRECT - Using exact column names from schema
cursor.execute('''
    SELECT id, description, amount, currency, timestamp,
           normalised_provider_transaction_id, transaction_category
    FROM truelayer_transactions
    WHERE account_id = %s
''', (account_id,))

# WRONG - Using "normalised_provider_id" (missing "transaction")
cursor.execute('''
    SELECT normalised_provider_id FROM truelayer_transactions
    WHERE account_id = %s
''', (account_id,))

# WRONG - Using "category" instead of "transaction_category"
cursor.execute('''
    SELECT category FROM truelayer_transactions
    WHERE account_id = %s
''', (account_id,))
```

### Rule 2: Data Types Must Match Schema

```python
# From DATABASE_SCHEMA.md:
# - id: INTEGER (auto-increment, don't provide)
# - timestamp: TIMESTAMP WITH TIME ZONE (use datetime.now(timezone.utc))
# - amount: NUMERIC (never use float)
# - metadata: JSONB (use json.dumps(), not str())
# - access_token: TEXT (must be ENCRYPTED with encrypt_token())

from datetime import datetime, timezone
import json
from mcp.truelayer_auth import encrypt_token

# CORRECT type usage
cursor.execute('''
    INSERT INTO truelayer_transactions
    (account_id, transaction_id, timestamp, amount, metadata, ...)
    VALUES (%s, %s, %s, %s, %s, ...)
''', (
    3,                                  # account_id: INTEGER ✓
    'txn-123',                         # transaction_id: VARCHAR ✓
    datetime.now(timezone.utc),        # timestamp: TIMESTAMP+TZ ✓
    Decimal('123.45'),                 # amount: NUMERIC ✓
    json.dumps(metadata_dict),         # metadata: JSONB ✓
    # ... more params
))

# WRONG type usage
cursor.execute('''
    INSERT INTO truelayer_transactions
    (timestamp, amount, metadata)
    VALUES (%s, %s, %s)
''', (
    datetime.utcnow(),                 # WRONG: naive datetime, should be timezone-aware
    123.45,                            # WRONG: float, should use Decimal
    str(metadata_dict),                # WRONG: string, should use json.dumps()
))
```

### Rule 3: Foreign Keys Must Reference Valid Tables

```python
# From DATABASE_SCHEMA.md:
# truelayer_transactions:
#   - account_id: INTEGER - Foreign key to truelayer_accounts.id
#   - Constraint: referenced account_id must exist

# CORRECT - Check account exists before inserting
account = database.get_connection_account(account_id)
if account:
    database.insert_truelayer_transaction(account_id=account_id, ...)
else:
    raise ValueError(f"Account {account_id} not found")

# WRONG - Blindly insert with potentially invalid FK
database.insert_truelayer_transaction(account_id=999, ...)  # 999 may not exist
```

### Rule 4: Nullable Constraints Must Be Respected

```python
# From DATABASE_SCHEMA.md - truelayer_transactions table:
# - account_id: NOT NULL  (required)
# - transaction_id: NOT NULL (required)
# - amount: NOT NULL (required)
# - merchant_name: NULLABLE (optional)
# - transaction_category: NULLABLE (optional)

# CORRECT - Required fields always provided
insert_truelayer_transaction(
    account_id=3,                    # Required ✓
    transaction_id='txn-123',        # Required ✓
    amount=Decimal('100.00'),        # Required ✓
    merchant_name='Tesco',           # Optional (can be None) ✓
    transaction_category=None        # Optional (can be None) ✓
)

# WRONG - Missing required field
insert_truelayer_transaction(
    account_id=3,
    # Missing: transaction_id (REQUIRED!)
    amount=Decimal('100.00'),
    merchant_name='Tesco'
)

# WRONG - Null for required field
insert_truelayer_transaction(
    account_id=None,                 # WRONG: account_id is NOT NULL
    transaction_id='txn-123',
    amount=Decimal('100.00')
)
```

---

## Adding New Functionality

### Step 1: Check Schema First

Before writing ANY code that touches the database:
1. Open `DATABASE_SCHEMA.md`
2. Find the relevant table(s)
3. Read the column names and types carefully
4. Note any constraints or special handling

### Step 2: Does Schema Need Updating?

- **If using existing columns:** Just use them (schema is already documented)
- **If needing new columns:**
  - First update `DATABASE_SCHEMA.md`
  - Document the column definition
  - Create migration script
  - Update code to use new column

### Step 3: Write Code to Match Schema

Example: Adding support for storing transaction category from TrueLayer API

**Step 3a: Check schema**
```markdown
# From DATABASE_SCHEMA.md - truelayer_transactions table:
transaction_category: VARCHAR, NULLABLE

# OK - This column exists and can be NULL
```

**Step 3b: Write code**
```python
def normalize_transaction(self, truelayer_txn: Dict) -> Dict:
    """Normalize TrueLayer transaction."""
    return {
        'description': truelayer_txn.get('description', ''),
        'amount': abs(float(truelayer_txn.get('amount', 0))),
        'category': truelayer_txn.get('transaction_category'),  # ← Maps to transaction_category in DB
        # ... other fields
    }

def insert_truelayer_transaction(
    account_id, transaction_id, ..., transaction_category, ...
):
    """Insert transaction - column names match schema exactly."""
    cursor.execute('''
        INSERT INTO truelayer_transactions
        (account_id, transaction_id, ..., transaction_category, ...)
        VALUES (%s, %s, ..., %s, ...)
    ''', (account_id, transaction_id, ..., transaction_category, ...))
```

### Step 4: Test Against Schema

Create a test to verify your code matches schema:

```python
def test_transaction_schema_compliance():
    """Verify transaction data matches DATABASE_SCHEMA.md"""
    # Get from database
    txn = database.get_truelayer_transaction_by_id(some_id)

    # Verify all REQUIRED fields are present
    required_fields = [
        'id', 'account_id', 'transaction_id',
        'normalised_provider_transaction_id', 'timestamp',
        'description', 'amount', 'currency', 'transaction_type'
    ]
    for field in required_fields:
        assert field in txn, f"Missing required field: {field}"
        assert txn[field] is not None, f"Required field is None: {field}"

    # Verify data types
    assert isinstance(txn['id'], int), "id must be integer"
    assert isinstance(txn['amount'], (int, float, Decimal)), "amount must be numeric"
    assert isinstance(txn['timestamp'], (datetime, str)), "timestamp must be datetime or ISO string"

    # Verify optional fields are present (may be None)
    optional_fields = ['transaction_category', 'merchant_name', 'running_balance', 'metadata']
    for field in optional_fields:
        assert field in txn, f"Optional field missing: {field}"
        # Value can be None, but key must exist
```

---

## Code Review Checklist for Schema Compliance

When reviewing pull requests with database changes:

- [ ] **Column Names**
  - [ ] All column names match `DATABASE_SCHEMA.md` exactly (including case)
  - [ ] No typos like "normalised_provider_id" vs "normalised_provider_transaction_id"

- [ ] **Data Types**
  - [ ] Numeric amounts use `Decimal` or `NUMERIC`, not `float`
  - [ ] Timestamps use `datetime.now(timezone.utc)`, not `datetime.utcnow()`
  - [ ] JSON data uses `json.dumps()`, not `str()`
  - [ ] Encrypted tokens use `encrypt_token()`, not stored raw

- [ ] **Nullable Constraints**
  - [ ] All NOT NULL columns have values
  - [ ] NULLABLE columns can safely be None
  - [ ] Default values are applied correctly

- [ ] **Foreign Keys**
  - [ ] All FK references point to correct tables
  - [ ] FK values are validated before insert
  - [ ] No orphaned records possible

- [ ] **Unique Constraints**
  - [ ] Deduplication checks done before insert (e.g., `normalised_provider_transaction_id`)
  - [ ] Proper error handling for constraint violations

- [ ] **Documentation**
  - [ ] `DATABASE_SCHEMA.md` updated if schema changed
  - [ ] Schema changes logged with date and reason
  - [ ] Code comments explain non-obvious schema usage

- [ ] **SQL Safety**
  - [ ] All queries use parameterized statements (`%s`)
  - [ ] No string concatenation for SQL
  - [ ] No `SELECT *` (explicit column lists)

---

## Migration Workflow

### When You Need to Change the Schema

1. **Create migration file**
   ```bash
   # File: backend/db/migrations/2025-11-27_add_field.sql

   -- UP: Add field
   ALTER TABLE truelayer_transactions ADD COLUMN new_field VARCHAR;

   -- DOWN: Remove field (for rollback)
   ALTER TABLE truelayer_transactions DROP COLUMN new_field;
   ```

2. **Update DATABASE_SCHEMA.md**
   ```markdown
   ### 2025-11-27: Added New Field
   - **Change:** Added `new_field` to `truelayer_transactions` table
   - **Reason:** Need to store new data from API
   - **Migration:** `backend/db/migrations/2025-11-27_add_field.sql`
   - **Code Changes:** Update `database_postgres.py` lines X-Y
   ```

3. **Update database_postgres.py**
   ```python
   # Update all SELECT statements to include new column
   cursor.execute('''
       SELECT id, ..., new_field  # ← Add here
       FROM truelayer_transactions
   ''')

   # Update INSERT statements to include new column
   cursor.execute('''
       INSERT INTO truelayer_transactions (..., new_field)
       VALUES (..., %s)
   ''', (..., new_field_value))
   ```

4. **Test locally**
   ```bash
   # Apply migration
   docker exec spending-postgres psql -U spending_user -d spending_db -f backend/db/migrations/2025-11-27_add_field.sql

   # Test code works with new column
   python -m pytest tests/test_database.py
   ```

5. **Commit together**
   ```bash
   git add docs/DATABASE_SCHEMA.md
   git add backend/db/migrations/2025-11-27_add_field.sql
   git add backend/database_postgres.py
   git commit -m "Add new_field to truelayer_transactions table"
   ```

---

## Summary

**Golden Rule:** Always check `DATABASE_SCHEMA.md` BEFORE writing any database code.

**Key Principles:**
1. Documentation is the source of truth
2. Code must match documentation exactly
3. Schema changes must be documented immediately
4. All data types must match schema definitions
5. All column names must match schema exactly
6. Migrations must be created for permanent changes
7. Code reviews must verify schema compliance

**When in doubt:** Check the schema documentation first!
