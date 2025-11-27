# Critical Schema Issues & Fixes

**Purpose:** Document specific schema-related bugs that occurred and how to prevent them in the future.

**Last Updated:** 2025-11-27
**Severity:** HIGH - These bugs prevented entire feature from working

---

## Issue #1: Running Balance Dict vs Scalar

### The Problem
TrueLayer API returns `running_balance` as a **dictionary object**, but the database column expects a **scalar number**.

```javascript
// What TrueLayer API returns:
{
  "running_balance": {
    "amount": 1234.56,
    "currency": "GBP"
  }
}
```

```python
# What code was doing (WRONG):
running_balance = txn.get('running_balance')  # Gets the ENTIRE dict
cursor.execute('INSERT INTO truelayer_transactions (..., running_balance) VALUES (..., %s)',
    (..., running_balance))  # Tries to insert dict to numeric column
# ERROR: can't adapt type 'dict'
```

### The Fix

**File:** `backend/mcp/truelayer_client.py` - `normalize_transaction()` function

```python
# Lines 303-306: CORRECT approach
running_balance = truelayer_txn.get('running_balance')
if isinstance(running_balance, dict):
    running_balance = running_balance.get('amount')  # Extract the scalar value
```

### Prevention Checklist
- [ ] When handling API response: Check if field is dict when expecting scalar
- [ ] Extract the value needed: `dict.get('amount')` not the whole dict
- [ ] Add type check: `isinstance(value, dict)` before extraction
- [ ] Test with real API data to catch these mismatches

### To Apply to New APIs
Whenever you're importing data from external APIs:
1. Print actual API response structure during development
2. If field appears to be object/dict but schema expects scalar, extract the value
3. Add defensive type checking

---

## Issue #2: JSON Serialization (str vs json.dumps)

### The Problem
PostgreSQL `JSONB` columns require proper JSON serialization, not Python's `str()` function.

```python
# What code was doing (WRONG):
metadata = {'provider_id': '...', 'meta': {...}}
cursor.execute('INSERT INTO truelayer_transactions (..., metadata) VALUES (..., %s)',
    (..., str(metadata)))  # str() produces Python dict syntax, not JSON
# Result: psycopg2 can't convert the string to JSONB
# ERROR: can't adapt type 'dict'
```

### The Fix

**File:** `backend/database_postgres.py` - `insert_truelayer_transaction()` function

```python
# Line 1237: CORRECT approach
import json

cursor.execute('''
    INSERT INTO truelayer_transactions
    (..., metadata)
    VALUES (..., %s)
''', (..., json.dumps(metadata)))  # Use json.dumps() for JSONB columns
```

### Prevention Checklist
- [ ] Check column type in `DATABASE_SCHEMA.md`
- [ ] If JSONB: Always use `json.dumps(dict)` before INSERT
- [ ] If TEXT: Use `str()` (but prefer JSONB for new code)
- [ ] Test with actual dict data

### Rule
```
JSONB Column → json.dumps(dict)
TEXT Column → str(dict) or dict.get('value')
Scalar Column → Extract value, never pass dict
```

---

## Issue #3: Column Name Typos

### The Problem
Code used incorrect column names that didn't match the actual schema.

```python
# WRONG: Using "normalised_provider_id" instead of "normalised_provider_transaction_id"
cursor.execute('SELECT normalised_provider_id FROM truelayer_transactions')
# ERROR: column "normalised_provider_id" does not exist

# WRONG: Using "category" instead of "transaction_category"
cursor.execute('SELECT category FROM truelayer_transactions')
# ERROR: column "category" does not exist
```

### The Fix

**File:** `backend/database_postgres.py` - Multiple functions:
- `get_truelayer_transaction_by_id()` - Line 1207
- `insert_truelayer_transaction()` - Line 1230-1232
- `get_all_truelayer_transactions()` - Lines 1253-1255, 1261-1263

```python
# CORRECT column names (from DATABASE_SCHEMA.md)
cursor.execute('''
    SELECT id, account_id, transaction_id,
           normalised_provider_transaction_id,  # ← CORRECT (includes "transaction")
           timestamp, description, amount, currency, transaction_type,
           transaction_category,               # ← CORRECT (includes "transaction_")
           merchant_name, running_balance, metadata
    FROM truelayer_transactions
    WHERE account_id = %s
''', (account_id,))
```

### Prevention Checklist
- [ ] Copy exact column names from `DATABASE_SCHEMA.md`
- [ ] Do NOT guess or abbreviate column names
- [ ] Run SELECT queries locally first to verify columns exist
- [ ] Use `\d table_name` in psql to see actual columns
- [ ] Code review: Compare column names to schema doc

### Column Name Reference

| Table | Column | Correct | Wrong |
|-------|--------|---------|-------|
| truelayer_transactions | Running balance dedup key | `normalised_provider_transaction_id` | `normalised_provider_id` |
| truelayer_transactions | Category from API | `transaction_category` | `category` |
| truelayer_card_transactions | Category from API | `category` | `transaction_category` |

---

## Issue #4: Timezone-Aware vs Naive Datetimes

### The Problem
Mixing timezone-aware and timezone-naive datetime objects caused arithmetic errors.

```python
# WRONG: utcnow() returns NAIVE datetime
from datetime import datetime
now = datetime.utcnow()  # ← Naive (no timezone info)

# Database value might be AWARE (with timezone)
expires_at = datetime.fromisoformat(db_value)  # ← Aware from DB

# ERROR: can't subtract offset-naive and offset-aware datetimes
if expires_at > now:
    print("Token expired")
```

### The Fix

**File:** `backend/mcp/truelayer_sync.py` - `refresh_token_if_needed()` function

```python
# CORRECT: Use timezone-aware datetimes everywhere
from datetime import datetime, timezone

now = datetime.now(timezone.utc)  # ← Always timezone-aware
expires_at = datetime.fromisoformat(db_value)

# If database returned naive datetime, make it aware:
if expires_at.tzinfo is None:
    expires_at = expires_at.replace(tzinfo=timezone.utc)

# Now arithmetic works
if expires_at > now:
    print("Token expired")
```

### Prevention Checklist
- [ ] Never use `datetime.utcnow()` - always use `datetime.now(timezone.utc)`
- [ ] Check if datetime is aware: `dt.tzinfo is None`
- [ ] If naive, add timezone: `dt.replace(tzinfo=timezone.utc)`
- [ ] When storing in DB: Always use timezone-aware
- [ ] When retrieving from DB: Ensure awareness matches code

### Rule
```
✓ GOOD:   datetime.now(timezone.utc)          # Aware, current time
✓ GOOD:   datetime.fromisoformat(iso_string)  # Aware if iso_string has Z or ±HH:MM
✗ BAD:    datetime.utcnow()                   # Naive (NEVER USE)
✗ BAD:    datetime.now()                      # Naive (NEVER USE)
```

---

## Issue #5: Missing Import Statement

### The Problem
Code used function `decrypt_token()` without importing it.

```python
# WRONG: No import statement
from mcp.truelayer_sync import sync_all_accounts  # Only this imported

def sync_account_transactions(...):
    encrypted_token = connection['access_token']
    access_token = decrypt_token(encrypted_token)  # ERROR: NameError
    # ERROR: name 'decrypt_token' is not defined
```

### The Fix

**File:** `backend/mcp/truelayer_sync.py` - Line 10

```python
# CORRECT: Import all needed functions
from .truelayer_auth import decrypt_token, refresh_access_token, encrypt_token

def sync_account_transactions(...):
    encrypted_token = connection['access_token']
    access_token = decrypt_token(encrypted_token)  # ✓ Now defined
```

### Prevention Checklist
- [ ] When using a function: Ensure it's imported at top of file
- [ ] Check function definition in source file
- [ ] Use relative imports for same package: `from .module import func`
- [ ] Test: Run code with `python -m py_compile module.py` to catch import errors
- [ ] Code review: Verify all functions are imported

---

## Issue #6: Token Expiry Not Checked

### The Problem
OAuth tokens expire, but code didn't check expiry before using them.

```python
# WRONG: No expiry check
def sync_account_transactions(...):
    encrypted_token = connection['access_token']
    access_token = decrypt_token(encrypted_token)

    # Using potentially EXPIRED token!
    client = TrueLayerClient(access_token)
    transactions = client.fetch_all_transactions(...)
    # ERROR: 401 Unauthorized - The token expired at '2025-11-25T23:58:43.000Z'
```

### The Fix

**File:** `backend/mcp/truelayer_sync.py` - `refresh_token_if_needed()` function

```python
# CORRECT: Check and refresh token before use
from datetime import datetime, timezone, timedelta

def refresh_token_if_needed(connection_id, connection):
    """Refresh token if expiring within 5 minutes."""
    expires_at = connection.get('token_expires_at')

    # Handle both string and datetime formats
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)

    # Make timezone-aware if needed
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    # Check expiry (refresh if less than 5 minutes left)
    now = datetime.now(timezone.utc)
    if expires_at < now + timedelta(minutes=5):
        # Token is expired or expiring soon - refresh it
        old_refresh_token = decrypt_token(connection['refresh_token'])
        new_tokens = refresh_access_token(old_refresh_token)

        # Store new tokens (encrypted)
        database.update_connection_tokens(
            connection_id,
            encrypt_token(new_tokens['access_token']),
            encrypt_token(new_tokens['refresh_token']),
            new_tokens['expires_at']
        )

        return new_tokens['access_token']

    # Token still valid
    return decrypt_token(connection['access_token'])
```

### Prevention Checklist
- [ ] For OAuth connections: Check token expiry before API calls
- [ ] Compare `token_expires_at` with current time
- [ ] Add buffer (5-10 minutes) to avoid edge cases
- [ ] Implement automatic refresh when expiring
- [ ] Handle case where refresh token is also expired
- [ ] Test with actual expired tokens

### Rule
```
BEFORE any API call with OAuth token:
1. Get expires_at from database
2. Compare with current time + buffer
3. If expiring: Call refresh_token()
4. Encrypt new tokens before storing
5. Only then make API call with fresh token
```

---

## Combined Fix Example

This is how all 6 issues were fixed together in the TrueLayer sync feature:

```python
# backend/mcp/truelayer_sync.py

# Issue #5: Import all needed functions
from .truelayer_auth import decrypt_token, refresh_access_token, encrypt_token

# Issue #4: Use timezone-aware datetimes
from datetime import datetime, timezone, timedelta

def sync_account_transactions(connection_id, truelayer_account_id, db_account_id, access_token):
    """Sync transactions from TrueLayer."""

    try:
        # Issue #6: Check token expiry before use
        connection = database.get_connection(connection_id)

        # Refresh if expiring (handles Issue #4: timezone awareness)
        if refresh_token_if_needed(connection_id, connection):
            # Token was refreshed, get fresh one
            connection = database.get_connection(connection_id)
            access_token = decrypt_token(connection['access_token'])

        # Make API call with valid token
        client = TrueLayerClient(access_token)

        # Fetch transactions
        transactions = client.fetch_all_transactions(truelayer_account_id)

        # Process transactions
        for txn in transactions:
            try:
                # Normalize (fixes Issue #1: running_balance dict extraction)
                normalized = client.normalize_transaction(txn)

                # Check for duplicates before insert
                if database.get_truelayer_transaction_by_id(
                    normalized['normalised_provider_id']  # Issue #3: Correct column name
                ):
                    continue  # Already exists

                # Insert (fixes Issue #2: JSON serialization)
                database.insert_truelayer_transaction(
                    account_id=db_account_id,
                    transaction_id=normalized['transaction_id'],
                    normalised_provider_id=normalized['normalised_provider_id'],
                    timestamp=normalized['date'],
                    description=normalized['description'],
                    amount=normalized['amount'],
                    currency=normalized['currency'],
                    transaction_type=normalized['transaction_type'],
                    transaction_category=normalized.get('category'),
                    merchant_name=normalized.get('merchant_name'),
                    running_balance=normalized['running_balance'],  # Now scalar, not dict
                    metadata=normalized['metadata']  # Will use json.dumps() in DB function
                )

            except Exception as e:
                print(f"Error processing transaction: {e}")
                error_count += 1

    except Exception as e:
        print(f"Sync failed: {e}")
        raise
```

---

## Testing Checklist

After making schema-related changes, test these scenarios:

```python
def test_truelayer_sync():
    """Test TrueLayer sync with all schema fixes applied."""

    # Test 1: Running balance extraction (Issue #1)
    txn = {'running_balance': {'amount': 100.00, 'currency': 'GBP'}}
    normalized = client.normalize_transaction(txn)
    assert normalized['running_balance'] == 100.00  # Scalar, not dict
    assert isinstance(normalized['running_balance'], (int, float, Decimal))

    # Test 2: JSON metadata (Issue #2)
    import json
    metadata = {'provider_id': '...', 'meta': {...}}
    db_insert(metadata=json.dumps(metadata))  # Should succeed

    # Test 3: Column names (Issue #3)
    cursor.execute('SELECT normalised_provider_transaction_id, transaction_category FROM truelayer_transactions')
    # Should succeed (no "column does not exist" errors)

    # Test 4: Timezone handling (Issue #4)
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromisoformat(db_expires_string)
    diff = expires_at - now  # Should not raise TypeError
    assert diff.total_seconds() > 0  # Token still valid

    # Test 5: Import statement (Issue #5)
    from mcp.truelayer_sync import sync_account_transactions
    # Should succeed without NameError

    # Test 6: Token refresh (Issue #6)
    expired_connection = {
        'token_expires_at': '2020-01-01T00:00:00+00:00'  # Old date
    }
    refresh_token_if_needed(1, expired_connection)
    # Should refresh and update database

    print("✅ All schema fixes validated")
```

---

## Quick Reference

When you encounter a database error:

| Error | Likely Cause | Fix |
|-------|--------------|-----|
| `column "X" does not exist` | Wrong column name (Issue #3) | Check `DATABASE_SCHEMA.md` for exact name |
| `can't adapt type 'dict'` | Passing dict to scalar/JSONB (Issues #1, #2) | Extract scalar or use `json.dumps()` |
| `can't subtract offset-naive and offset-aware` | DateTime mismatch (Issue #4) | Use `datetime.now(timezone.utc)` |
| `NameError: name 'X' is not defined` | Missing import (Issue #5) | Add import statement at top |
| `401 Unauthorized: token expired` | Token not refreshed (Issue #6) | Check and refresh before API call |
| `duplicate key value violates unique constraint` | Not deduplicating (related) | Check for existing before insert |

---

## Takeaway

These 6 issues were interconnected and showed the importance of:
1. ✓ Knowing your schema (read `DATABASE_SCHEMA.md` first)
2. ✓ Type safety (dict vs scalar, aware vs naive datetimes)
3. ✓ Error handling (check expiry, handle both formats)
4. ✓ Testing (catch these with automated tests)
5. ✓ Documentation (prevent repeating mistakes)

**Future developers:** If you encounter any of these errors, come back to this document!
