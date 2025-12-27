# Database Layer Refactoring

## Overview

This directory contains the refactored database layer, split from the monolithic `database_postgres.py` (8,008 lines, 246 functions) into focused, domain-specific modules.

## Architecture

### Design Principles

1. **Single Responsibility**: Each module handles one business domain
2. **Domain Boundaries**: Clear separation (Gmail, TrueLayer, Amazon, etc.)
3. **Shared Infrastructure**: Common utilities in `base.py`
4. **Public API**: All exports through `__init__.py`
5. **Backward Compatibility**: Facade pattern during migration

### Module Structure

```
backend/database/
├── __init__.py                  # Public API exports (COMPLETE)
├── base.py                      # Connection pool & utilities (COMPLETE)
├── gmail.py                     # Gmail receipts & sync (4,050 lines, 101 functions) - ✅ COMPLETE
├── truelayer.py                 # TrueLayer bank sync (882 lines, 47 functions) - ✅ COMPLETE
├── categories.py                # Categories & rules (1,221 lines, 23 functions) - ✅ COMPLETE
├── apple.py                     # Apple transactions (159 lines, 6 functions) - ✅ COMPLETE
├── amazon.py                    # Amazon orders (1,031 lines, 30 functions) - ✅ COMPLETE
├── enrichment.py                # Transaction enrichment (531 lines, 13 functions) - ✅ COMPLETE
├── matching.py                  # Consistency & matching (278 lines, 10 functions) - ✅ COMPLETE
├── direct_debit.py              # Direct debit mapping (359 lines, 6 functions) - ✅ COMPLETE
├── pdf.py                       # PDF attachments (107 lines, 6 functions) - ✅ COMPLETE
└── transactions.py              # Core transactions (559 lines, 22 functions) - ✅ COMPLETE
```

**Note**: Webhooks are in truelayer.py, merchant normalization in matching.py,
and statistics functions are distributed across their respective domain modules.

## Current Status

### ✅ Complete - Database Layer Fully Refactored!

- **base.py**: Connection pool, `get_db()` context manager, core utilities
- **__init__.py**: Public API structure, backward compatibility layer

### 🚧 In Progress

- Extracting domain modules from `database_postgres.py`

### ⏳ TODO

- 13 domain modules to extract
- Update imports across codebase
- Remove legacy `database_postgres.py`

## Usage Patterns

### Using the Database Layer

```python
# Always import from the database package
from database import get_db, save_gmail_receipt, get_truelayer_accounts

# Use the context manager pattern
with get_db() as conn:
    with conn.cursor() as cursor:
        cursor.execute("SELECT * FROM table")
        result = cursor.fetchall()

# Or use the convenience function
from database import execute_query

user = execute_query(
    "SELECT * FROM users WHERE id = %s",
    (user_id,),
    fetch_one=True
)
```

### Creating a New Domain Module

1. Create `backend/database/your_domain.py`
2. Import base utilities: `from .base import get_db, execute_query`
3. Implement domain functions
4. Export functions in `__init__.py`
5. Update `__all__` list
6. Document in this README

Example module structure:

```python
"""
Your Domain - Database Operations

Handles all database operations for Your Domain.
"""

from .base import get_db, execute_query
from psycopg2.extras import RealDictCursor


def get_your_domain_data(user_id: int) -> list[dict]:
    """
    Get data for a specific user.

    Args:
        user_id: User ID

    Returns:
        List of records as dicts
    """
    return execute_query(
        "SELECT * FROM your_table WHERE user_id = %s",
        (user_id,),
        fetch_all=True
    )
```

## Migration Strategy

### Phase 1: Foundation (COMPLETE ✅)

- Created directory structure
- Extracted connection pool to `base.py`
- Set up public API in `__init__.py`
- Established backward compatibility

### Phase 2: Extract Domain Modules (IN PROGRESS 🚧)

Extract functions from `database_postgres.py` domain by domain:

1. **Gmail** (~700 lines): All `*gmail*` functions
2. **TrueLayer** (~600 lines): All `*truelayer*` functions
3. **Categories** (~500 lines): All `*category*`, `*rule*` functions
4. **Transactions** (~400 lines): All `*transaction*` functions
5. **Statistics** (~400 lines): Analytics queries
6. **Amazon** (~300 lines): Amazon order functions
7. **Matching** (~300 lines): Cross-source matching
8. **Apple** (~200 lines): Apple transaction functions
9. **Import Jobs** (~250 lines): Import tracking
10. **Direct Debit** (~200 lines): Direct debit mappings
11. **Webhooks** (~150 lines): Webhook handling
12. **Merchant Normalization** (~350 lines): Merchant name utilities

### Phase 3: Cleanup

- Update all imports to use `from database import ...`
- Remove facade functions from `database_postgres.py`
- Delete `database_postgres.py`
- Update documentation

## File Size Guidelines

- **Target**: 200-500 lines per file
- **Maximum**: 800 lines
- **Reason**: Easier to understand, maintain, and test

## Testing

Each domain module should have:
- Unit tests for individual functions
- Integration tests for database operations
- Test fixtures for common data

## Documentation

Each module must include:
- Module-level docstring explaining its purpose
- Function docstrings with Args, Returns, Raises
- Usage examples where helpful

## Questions?

See the refactoring plan: `/.claude/plans/curried-inventing-lovelace.md`
