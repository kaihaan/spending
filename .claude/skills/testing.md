---
name: testing
description: Use when user says "test" or after implementing new features - runs pytest with correct test database
---

# Testing Skill

## When to Use This Skill

**Trigger automatically when:**
1. User says "test", "run tests", "check tests"
2. After implementing new features or code changes
3. After fixing bugs
4. After modifying database schema
5. After changing API endpoints

## Testing Workflow

### Step 1: Identify Test Scope

Determine what needs testing:
- New feature → Create new test file or add to existing
- Bug fix → Run related existing tests
- API change → Run API tests
- Database change → Run database tests
- Full suite → Run all tests

### Step 2: Run Tests with Correct Environment

**CRITICAL: Always use PYTHONPATH prefix**

```bash
# Template
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest [test_file] [options]

# Examples
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest backend/tests/test_auth.py -v
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest -k "test_user_registration" -v
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest -x  # Stop on first failure
```

**Common pytest options:**
- `-v` - Verbose output (show test names)
- `-s` - Show print statements
- `-x` - Stop on first failure
- `-k "pattern"` - Run tests matching pattern
- `--tb=short` - Shorter traceback format

### Step 3: Interpret Results

**Success:**
```
======================== 5 passed in 2.34s =========================
```
✅ All tests passed - implementation is correct

**Failure:**
```
FAILED backend/tests/test_auth.py::test_user_registration - AssertionError: ...
======================== 1 failed, 4 passed in 2.34s =========================
```
❌ Test failed - fix the implementation or test

**Database Errors:**
If tests fail with database connection errors, test database may need reset:
```bash
PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -p 5433 -U spending_user -d postgres -c "DROP DATABASE IF EXISTS spending_db_test;"
```

### Step 4: Report to User

Provide:
1. Number of tests run
2. Pass/fail status
3. If failed: specific error details and file:line references
4. Next steps (fix code or tests)

## Safety Rules

**NEVER during testing:**
- ❌ Use `curl` commands to test API endpoints
- ❌ Use `psql` to manually insert test data
- ❌ Connect to production database (`spending_db`, port 5433)
- ❌ Use hardcoded `user_id=1` in test scenarios

**ALWAYS during testing:**
- ✅ Use pytest framework
- ✅ Let conftest.py handle database setup
- ✅ Use test fixtures for data creation
- ✅ Verify test database (`spending_db_test`, port 5432)

## Persistent Test Database

**Key Concept:** Test database persists between runs

**Advantages:**
- Faster test iterations (no DB recreation overhead)
- Can inspect test data between runs
- Reuse test data (e.g., test users persist)

**Managing Test Data:**

```python
def test_with_persistent_user(client, db):
    """Example: Check if test user exists, create if needed."""
    from sqlalchemy import text

    result = db.execute(text("SELECT id FROM users WHERE email = 'test@example.com'"))
    user = result.fetchone()

    if user is None:
        # Create test user (only first run)
        client.post('/api/auth/register', json={
            'email': 'test@example.com',
            'password': 'testpass123',
            'username': 'testuser'
        })
```

**Resetting Test Database:**

When test database needs reset (schema changes, data corruption):
```bash
PGPASSWORD=$POSTGRES_PASSWORD psql -h localhost -p 5433 -U spending_user -d postgres -c "DROP DATABASE IF EXISTS spending_db_test;"
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest  # Recreates from production
```

## Writing New Tests

If tests don't exist for new feature:

### Step 1: Choose Test File Location

```
backend/tests/
├── test_auth.py          # Authentication endpoints
├── test_truelayer_*.py   # TrueLayer integration
├── test_gmail.py         # Gmail integration
├── test_amazon.py        # Amazon integration
├── test_database.py      # Database operations
└── test_[feature].py     # New feature tests
```

### Step 2: Follow Existing Patterns

```python
import pytest
from sqlalchemy import text

def test_feature_name(client, db):
    """Test description."""
    # Arrange - Set up test data
    # Act - Perform the operation
    # Assert - Verify the result

def test_api_endpoint(client):
    """Test API endpoint."""
    response = client.post('/api/endpoint', json={
        'key': 'value'
    })
    assert response.status_code == 200
    assert response.json['key'] == 'expected_value'

def test_database_operation(db):
    """Test database function."""
    from backend.database import function_name
    result = function_name(db, ...)
    assert result is not None
```

### Step 3: Run New Tests

```bash
# Run just the new test file
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest backend/tests/test_[feature].py -v

# Run full suite to ensure no regressions
PYTHONPATH=/home/kaihaan/prj/spending/backend pytest
```

## Multi-User Testing Pattern

For testing data isolation between users:

```python
def test_multi_user_data_isolation(client, db):
    """Verify users only see their own data."""
    # Create user1
    client.post('/api/auth/register', json={
        'email': 'user1@test.com',
        'password': 'password123',
        'username': 'user1'
    })

    # Add data for user1
    # ...

    # Logout
    client.post('/api/auth/logout')

    # Create user2
    client.post('/api/auth/register', json={
        'email': 'user2@test.com',
        'password': 'password123',
        'username': 'user2'
    })

    # Login as user2 (auto-login after registration)

    # Verify user2 sees ZERO data from user1
    response = client.get('/api/transactions')
    assert len(response.json['transactions']) == 0
```

## Checklist

Before completing this skill:
- [ ] Identified what needs testing
- [ ] Ran tests with correct PYTHONPATH
- [ ] Used test database (`spending_db_test`)
- [ ] Reported results to user with file:line references
- [ ] If new feature: created or updated test file
- [ ] If tests failed: analyzed and reported errors with specific locations
- [ ] If tests passed: confirmed implementation is correct

## Success Criteria

✅ Tests run successfully using pytest
✅ Test database used (not production)
✅ Clear pass/fail results reported
✅ No manual curl or database commands used
✅ User understands test results and next steps
