# Bug Tracker

This file tracks discovered bugs in the spending application.

---

## BUG-001: Multi-User Data Isolation Failure in Transactions API

**Date Discovered**: 2025-12-29 (Current session)
**Severity**: 🔴 **CRITICAL** - Security/Privacy Violation
**Status**: ⏳ Open
**Component**: Backend API (`/api/transactions` endpoint)
**Discovered By**: Multi-user data isolation test (`backend/tests/test_auth.py::test_multi_user_data_isolation`)

### Description

The `/api/transactions` GET endpoint returns ALL transactions from ALL users, regardless of which user is currently logged in. This is a critical data leak that violates user privacy and data isolation requirements.

### Impact

- **Privacy Violation**: Users can see other users' financial transaction data
- **Data Leak**: Complete transaction history including amounts, merchants, dates visible to unauthorized users
- **Compliance Risk**: Violates GDPR, data protection regulations
- **User Trust**: Completely undermines the multi-user authentication system

### Steps to Reproduce

1. User 1 registers and creates a transaction
2. User 1 logs out
3. User 2 registers
4. User 2 calls `GET /api/transactions`
5. **Result**: User 2 sees User 1's transaction data ❌
6. **Expected**: User 2 should see empty list ✅

### Evidence

Test output from `test_multi_user_data_isolation`:
```
AssertionError: User 2 should see 0 transactions but sees 1!
assert 1 == len([{'account_id': 112, 'amount': -50.0, ...}])
```

### Root Cause

The `/api/transactions` endpoint likely queries all transactions without filtering by `current_user.id`.

**Expected behavior**:
- Query should filter: `WHERE user_id = current_user.id` (or via relationship chain)
- Should use Flask-Login's `@login_required` decorator
- Should respect user session context

**Actual behavior**:
- Returns all transactions from database
- No user-specific filtering applied

### Technical Details

**Database Schema**:
```
users → bank_connections → truelayer_accounts → truelayer_transactions
```

**Correct query pattern**:
```python
# Get transactions for current user only
transactions = db.query(TrueLayerTransaction)\
    .join(TrueLayerAccount)\
    .join(BankConnection)\
    .filter(BankConnection.user_id == current_user.id)\
    .all()
```

### Files Affected

- `backend/app.py` - `/api/transactions` endpoint (location TBD - need to find exact line)
- Potentially other endpoints with similar patterns

### Fix Requirements

1. ✅ Add `@login_required` decorator to endpoint
2. ✅ Filter query by current user ID via relationship chain
3. ✅ Add test coverage to verify fix
4. ⏸️ Audit ALL other endpoints for similar issues
5. ⏸️ Add integration test for multi-user scenarios across all endpoints

### Related Issues

- Test infrastructure now properly validates multi-user isolation
- Persistent test database makes regression testing faster

### Notes

- This bug was discovered during implementation of testing infrastructure improvements
- The test correctly identified the issue on first run
- Similar bugs may exist in other endpoints that return user-specific data

---

## Bug Report Template

```markdown
## BUG-XXX: [Title]

**Date Discovered**: YYYY-MM-DD
**Severity**: 🔴 Critical / 🟡 High / 🟢 Medium / ⚪ Low
**Status**: ⏳ Open / 🔧 In Progress / ✅ Fixed / ❌ Won't Fix
**Component**: [Backend/Frontend/Database/etc.]

### Description
[Clear description of the bug]

### Impact
[What is affected and how severe]

### Steps to Reproduce
1. Step 1
2. Step 2
3. Expected vs Actual

### Root Cause
[Why the bug occurs]

### Fix Requirements
- [ ] Requirement 1
- [ ] Requirement 2

### Notes
[Additional context]
```
