# Database Schema Quick Reference

## CRITICAL: Always Consult Full Documentation!

**AUTHORITATIVE SOURCE**: `.claude/docs/database/DATABASE_SCHEMA.md`

This file contains:
- Complete column definitions
- Data types and constraints
- Relationships and foreign keys
- Change log

## Key Documentation Files

1. **DATABASE_SCHEMA.md** - Complete schema reference (ALWAYS READ THIS FIRST!)
2. **SCHEMA_ENFORCEMENT.md** - Code patterns and rules
3. **SCHEMA_CRITICAL_FIXES.md** - Past bugs to avoid

## Quick Table Overview

### Core Transactions
- `truelayer_transactions` - TrueLayer API transactions (PRIMARY)
- `transactions` - Santander Excel imports (LEGACY - NO LONGER USED)

### TrueLayer Integration
- `truelayer_accounts` - Connected bank accounts
- `truelayer_connections` - OAuth connections
- `truelayer_card_transactions` - Card transaction data

### Gmail Integration
- `gmail_connections` - OAuth tokens (encrypted)
- `gmail_receipts` - Parsed receipt metadata
- `gmail_email_content` - Raw email for re-parsing
- `pdf_attachments` - Links to MinIO storage

### Amazon Integration
- `amazon_business_connections` - OAuth tokens, marketplace config
- `amazon_business_orders` - Order summaries
- `amazon_business_line_items` - Individual items
- `truelayer_amazon_business_matches` - Links to bank transactions

### Apple Integration
- `apple_transactions` - Apple/iTunes purchases

### Enrichment
- `enrichment_cache` - LLM enrichment results
- `categories` - Category definitions
- `merchant_normalizations` - Merchant name mappings

### Matching
- `direct_debit_rules` - Automated payment matching

## Database Connection

**CRITICAL Settings:**
- **Host**: localhost (via Docker)
- **Port**: **5433** (NOT 5432!)
- **Database**: spending_db
- **User**: spending_user
- **Password**: Check `.env` file (NEVER assume defaults!)

## PostgreSQL Syntax Notes

PostgreSQL does NOT support `DELETE ... LIMIT`:

```sql
-- ❌ Wrong
DELETE FROM table WHERE condition LIMIT 1

-- ✅ Correct
DELETE FROM table
WHERE id = (SELECT id FROM table WHERE condition LIMIT 1)
```

## Common Workflows

### Before ANY database work:
1. Read `DATABASE_SCHEMA.md`
2. Check `SCHEMA_ENFORCEMENT.md`
3. Review `SCHEMA_CRITICAL_FIXES.md`
4. Verify column names exactly

### Database access:
```bash
# PostgreSQL shell
docker exec -it spending-postgres psql -U spending_user -d spending_db

# Backup
docker exec spending-postgres pg_dump -U spending_user spending_db > backup.sql
```

## Migration Pattern

Currently migrating from raw SQL to SQLAlchemy ORM:
- Use ORM for new code
- Check `models/` directory for ORM models
- Follow existing patterns in recent commits
