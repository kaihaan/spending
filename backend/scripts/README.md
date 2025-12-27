# Backend Utility Scripts

This directory contains one-off scripts, debugging tools, and maintenance utilities that are not part of the core application.

## Categories

### Gmail/Email Processing
- **`analyze_vendor_emails.py`** - Analyze vendor email patterns for parser development
- **`qa_gmail_receipts.py`** - Quality assurance checks for Gmail receipt parsing
- **`flag_non_purchase_emails.py`** - Identify and flag non-purchase emails (e.g., marketing)
- **`improve_vendor_parsers.py`** - Tools for improving vendor-specific email parsers
- **`reparse_deliveroo.py`** - Re-parse Deliveroo receipts with updated parser

### PDF Processing
- **`backfill_pdf_data.py`** - Backfill PDF attachment data into MinIO storage
- **`debug_ct_pdf.py`** - Debug PDF parsing issues (likely for a specific vendor)
- **`parse_bax_pdf.py`** - Parse BAX shop PDF receipts

### Data Quality & Maintenance
- **`detect_duplicates.py`** - Find and report duplicate transactions/receipts
- **`check_vendor_brand_metadata.py`** - Verify vendor brand metadata accuracy

### Transaction Enrichment
- **`enrich_existing_transactions.py`** - Backfill LLM enrichment for existing transactions

### Testing & Performance
- **`test_gmail_sync_performance.py`** - Performance testing for Gmail sync operations
- **`test_merchant_classification.py`** - Test merchant classification logic
- **`test_pdf_tasks.py`** - Test PDF processing Celery tasks
- **`test_sync_debug.py`** - Debug TrueLayer sync issues
- **`test_amazon_date_fix.py`** - Test Amazon date parsing fixes
- **`test_brand_extraction.py`** - Test brand extraction logic

### Migration & Setup
- **`migrate_to_postgres.py`** - Migration script from SQLite to PostgreSQL

### Backup
- **`app.py.backup`** - Backup of main Flask application

## Usage

Most scripts can be run directly with Python:

```bash
# Activate virtual environment first
source ../venv/bin/activate

# Set database type environment variable
export DB_TYPE=postgres

# Run a script
python3 scripts/analyze_vendor_emails.py
```

**Note:** Some scripts may require additional environment variables or command-line arguments. Check the script source for details.

## Important Notes

- These scripts are **not** part of the production application
- They may modify database state - **use with caution** in production
- Many scripts are designed for one-time use or debugging specific issues
- Scripts may become outdated as the codebase evolves
- Always review script source before running on production data
