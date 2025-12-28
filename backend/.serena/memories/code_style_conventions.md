# Code Style & Conventions - Personal Spending App

## Python Style

### Linting & Formatting
- **Ruff**: Primary linter with default + pyupgrade rules
- **Black**: Code must be Black-compatible (no manual formatting needed, Ruff handles it)
- **Pyright**: Type checking

### Code Quality Rules
1. **No unused imports or variables** - Ruff will catch these
2. **Explicit return types** for public functions
3. **Modern Python syntax** (>=3.10):
   - Use `|` instead of `Union` (e.g., `str | None`)
   - List/dict comprehensions where appropriate
   - Dataclasses or Pydantic models instead of ad-hoc dicts
4. **Avoid overly clever constructs** - prefer readability
5. **PEP 8 naming and structure**
6. **Docstrings** for public modules, classes, and functions
7. **Specific exceptions** - do not use bare `except`
8. **No lint rule suppression** unless explicitly requested

### File Organization
- **Target file length**: 200-500 lines (sweet spot for maintainability)
- **Maximum**: Under 1000 lines before considering splitting
- **Single responsibility** - each file/module does one thing well
- **Clear module boundaries** - group related functionality
- **Flat is better than nested** - avoid deep directory structures

### Example Structure
```python
from typing import Optional

def get_transaction_by_id(transaction_id: int) -> dict | None:
    """
    Retrieve a transaction by its ID.

    Args:
        transaction_id: The ID of the transaction to retrieve

    Returns:
        Transaction dict if found, None otherwise
    """
    # Implementation
    pass
```

## Database Patterns

### CRITICAL: Always check schema documentation first!
- **Authoritative source**: `.claude/docs/database/DATABASE_SCHEMA.md`
- **Enforcement patterns**: `.claude/docs/database/SCHEMA_ENFORCEMENT.md`
- **Past bugs to avoid**: `.claude/docs/database/SCHEMA_CRITICAL_FIXES.md`

### Database Rules
1. **PostgreSQL is primary** (NOT SQLite)
2. **Non-standard port**: 5433 (NOT 5432)
3. **Password**: Always check `.env` (never assume defaults)
4. **PostgreSQL syntax**: Does NOT support `DELETE ... LIMIT`
   ```sql
   -- ❌ Wrong
   DELETE FROM table WHERE condition LIMIT 1

   -- ✅ Correct
   DELETE FROM table WHERE id = (SELECT id FROM table WHERE condition LIMIT 1)
   ```

## Architecture Patterns

1. **Async Tasks**: Gmail sync, enrichment run in Celery workers
2. **API Integration**: TrueLayer, Amazon SP-API, Gmail API
3. **LLM Enrichment**: Multiple providers (Anthropic, OpenAI, Google, DeepSeek, Ollama)
4. **SQLAlchemy ORM**: Ongoing migration from raw SQL

## Security Practices

1. **No security vulnerabilities**: Command injection, XSS, SQL injection, OWASP top 10
2. **Token encryption**: Fernet cipher for OAuth tokens
3. **Environment variables**: Sensitive data in `.env`, never committed

## Error Handling

1. **Specific exceptions** over generic
2. **Logging**: Use Python logging module
3. **No bare except**: Always specify exception type

## Documentation

1. **Update docs** when schema/API changes
2. **Add to change log** for database changes
3. **Verify code matches documentation**
