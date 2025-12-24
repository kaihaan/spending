# Database Schema Documentation

**Last Updated:** 2025-12-24
**Database Type:** PostgreSQL (via Docker)
**ORM:** Direct SQL via `psycopg2` with cursor factory for dict conversion

## Overview

This document provides a comprehensive reference for the Personal Finance application's PostgreSQL database schema. All tables, columns, relationships, and data types are documented here.

### Schema Evolution

**IMPORTANT:** Any changes to the database schema MUST be:
1. First documented in this file with the change date
2. Added to the "Schema Changes" section below
3. Applied via migration scripts (when applicable)
4. Code that uses the schema must adhere to this documentation

---

## Schema Changes Log

### 2025-12-24: Gmail Integration Tables Documentation
- **Change:** Added documentation for 4 Gmail-related tables (gmail_connections, gmail_receipts, gmail_email_content, pdf_attachments)
- **Reason:** These tables were created incrementally but not documented in DATABASE_SCHEMA.md
- **Architecture:**
  - `gmail_connections` - OAuth credentials for Gmail API access (encrypted tokens)
  - `gmail_receipts` - Parsed receipt metadata with merchant/amount/line_items
  - `gmail_email_content` - Raw email storage (HTML, text, headers) for re-parsing
  - `pdf_attachments` - Links to PDF receipts stored in MinIO object storage
- **Storage:** PDF files stored in MinIO S3-compatible storage (bucket: `receipts`)
- **Migration:** `postgres/init/11_gmail_integration.sql`

### 2025-12-21: Remove lookup_description Column
- **Change:** Removed `lookup_description` column from `transactions` and `truelayer_transactions` tables
- **Reason:** Data is now stored in `transaction_enrichment_sources` table with proper foreign key references (polymorphic via `source_type` + `source_id`)
- **Benefits:**
  - Proper relational structure instead of denormalized text
  - Supports multiple enrichment sources per transaction
  - Tracks match confidence, method, and user verification
  - Links to full source records (Amazon orders, Apple transactions, Gmail receipts)
- **Migration:** `postgres/migrations/remove_lookup_description.sql`
- **Files Updated:**
  - `backend/database_postgres.py` (removed from SELECT queries)
  - `backend/mcp/llm_enricher.py` (uses `enrichment_sources` instead)
  - `backend/mcp/llm_providers/base_provider.py` (removed fallback)
  - `backend/app.py` (removed deprecated endpoints)
  - `frontend/src/types.ts` (removed from Transaction interface)
  - `frontend/src/components/TransactionRow.tsx` (removed fallback logic)

### 2025-12-06: Amazon Business API Integration
- **Change:** Added 4 new tables for Amazon Business order import via API
- **Tables Added:**
  - `amazon_business_connections` - OAuth connection tokens
  - `amazon_business_orders` - Imported order summaries
  - `amazon_business_line_items` - Order line item details
  - `truelayer_amazon_business_matches` - Matching to bank transactions
- **Reason:** Enable import of business purchase data via Amazon Business Reporting API with OAuth authentication
- **Migration:** `postgres/init/08_amazon_business.sql`
- **Files Updated:**
  - `backend/database_postgres.py` (12 functions)
  - `backend/mcp/amazon_business_auth.py` (NEW)
  - `backend/mcp/amazon_business_client.py` (NEW)
  - `backend/mcp/amazon_business_matcher.py` (NEW)
  - `backend/app.py` (8 endpoints)
  - `frontend/src/components/Settings/DataSourcesTab.tsx`

### 2025-12-05: Pre-Enrichment Status Column
- **Change:** Added `pre_enrichment_status` column to `truelayer_transactions` table
- **Reason:** Track whether transactions come from matchable sources (Apple/Amazon) and their matching status before LLM enrichment
- **Values:** `None` (default), `Matched`, `Apple`, `AMZN`, `AMZN RTN`
- **Migration:** `postgres/init/07_pre_enrichment_status.sql`
- **Files Updated:** `backend/database_postgres.py`, `backend/mcp/truelayer_sync.py`, `backend/mcp/amazon_matcher.py`, `backend/mcp/apple_matcher.py`, `backend/mcp/amazon_returns_matcher.py`, `backend/app.py`

### 2025-11-30: Amazon Matching for TrueLayer Transactions
- **Change:** Added `lookup_description` column to `transactions` and `truelayer_transactions` tables (**REMOVED 2025-12-21** - see above)
- **Change:** Created `truelayer_amazon_transaction_matches` table with proper relational structure
- **Reason:** Enable Amazon order matching for TrueLayer transactions with persistent storage instead of JSONB metadata
- **Migration:** `postgres/init/05_truelayer_amazon_matching.sql`
- **Files Updated:** `backend/database_postgres.py` (3 functions), `backend/mcp/amazon_matcher.py` (2 functions), `backend/app.py` (2 endpoints)

### 2025-11-27: TrueLayer Transaction Fixes
- **Change:** Fixed `truelayer_transactions.metadata` column to store JSON as JSONB type
- **Reason:** Support proper JSON handling for provider metadata
- **Migration:** Python code changed to use `json.dumps()` instead of `str()` for serialization
- **Files Updated:** `backend/database_postgres.py:1237`, `backend/mcp/truelayer_client.py`

### 2025-11-27: Running Balance Type Correction
- **Change:** `running_balance` columns changed from dict to numeric/float
- **Reason:** TrueLayer API returns running_balance as object with `{amount, currency}`; code must extract the `amount` field
- **Migration:** Updated `normalize_transaction()` and `normalize_card_transaction()` to extract scalar value
- **Files Updated:** `backend/mcp/truelayer_client.py:303-325`

### 2025-11-27: Column Name Corrections
- **Change:** Fixed SQL column references in `database_postgres.py`
  - `normalised_provider_id` → `normalised_provider_transaction_id` (truelayer_transactions table)
  - `category` → `transaction_category` (truelayer_transactions table)
- **Reason:** Code was using wrong column names, causing database errors
- **Migration:** Updated SQL queries in 3 functions
- **Files Updated:** `backend/database_postgres.py:1207, 1220-1244, 1246-1270`

---

## Core Tables

### 1. `users`
User accounts for the personal finance application.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key, auto-increment |
| email | VARCHAR | NO | | User email address (unique) |
| created_at | TIMESTAMP+TZ | YES | NOW() | Account creation timestamp |
| updated_at | TIMESTAMP+TZ | YES | NOW() | Last account update timestamp |

**Primary Key:** `id`
**Constraints:** `email` should be unique (not enforced in schema, validate in code)

---

### 2. `transactions`
Regular transactions imported from Santander Excel bank statements.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| date | DATE | NO | | Transaction date (YYYY-MM-DD) |
| description | TEXT | NO | | Original merchant/transaction description from statement |
| amount | NUMERIC | NO | | Transaction amount (negative=debit, positive=credit) |
| category | VARCHAR | YES | 'Other' | Transaction category (e.g., 'Groceries', 'Transport') |
| source_file | VARCHAR | YES | | Original Excel filename |
| merchant | VARCHAR | YES | | Extracted/normalized merchant name |
| huququllah_classification | VARCHAR | YES | | Islamic spending classification |
| created_at | TIMESTAMP+TZ | YES | NOW() | Record creation timestamp |

**Primary Key:** `id`
**Usage:** For Santander bank statement imports only
**Sorting:** By `date DESC` for chronological order (most recent first)

---

### 3. `truelayer_transactions`
Bank transactions synced from TrueLayer API in real-time.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| account_id | INTEGER | NO | | Foreign key to `truelayer_accounts.id` |
| transaction_id | VARCHAR | NO | | TrueLayer transaction ID |
| normalised_provider_transaction_id | VARCHAR | NO | | **UNIQUE** - Deduplication key (from TrueLayer `normalised_provider_transaction_id`) |
| timestamp | TIMESTAMP+TZ | NO | | Transaction timestamp (ISO 8601) |
| description | TEXT | NO | | Merchant/transaction description from TrueLayer API |
| amount | NUMERIC | NO | | Transaction amount (absolute value, positive) |
| currency | VARCHAR | NO | | ISO 4217 currency code (e.g., 'GBP') |
| transaction_type | VARCHAR | NO | | 'DEBIT' or 'CREDIT' from TrueLayer |
| transaction_category | VARCHAR | YES | | TrueLayer-provided transaction category |
| merchant_name | VARCHAR | YES | | Extracted merchant name |
| running_balance | NUMERIC | YES | | Account balance after transaction (MUST be scalar, extracted from API dict) |
| pre_enrichment_status | VARCHAR(20) | YES | 'None' | Pre-enrichment status: `None`, `Matched`, `Apple`, `AMZN`, `AMZN RTN` |
| metadata | JSONB | YES | | Provider metadata: `{provider_id, provider_transaction_id, meta}` |
| created_at | TIMESTAMP+TZ | YES | NOW() | Record creation timestamp |

**Primary Key:** `id`
**Foreign Keys:** `account_id` → `truelayer_accounts.id`
**Unique Constraint:** `normalised_provider_transaction_id` (prevents duplicate imports)
**Important Notes:**
- `running_balance` field from TrueLayer API is returned as `{amount: number, currency: string}` but must be stored as scalar
- `metadata` is stored as JSONB (NOT as string) - use `json.dumps()` when inserting
- All timestamps from TrueLayer are timezone-aware (UTC)

**CRITICAL IMPLEMENTATION RULE:**
```python
# CORRECT - Extract amount from running_balance dict
running_balance = txn.get('running_balance')
if isinstance(running_balance, dict):
    running_balance = running_balance.get('amount')

# CORRECT - Use json.dumps() for JSONB metadata
cursor.execute(..., (..., json.dumps(metadata)))

# WRONG - These will cause "can't adapt type 'dict'" errors
cursor.execute(..., (..., txn.get('running_balance')))  # dict passed directly
cursor.execute(..., (..., str(metadata)))  # string instead of JSON
```

---

### 4. `truelayer_accounts`
Bank accounts discovered from TrueLayer API.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| connection_id | INTEGER | NO | | Foreign key to `bank_connections.id` |
| account_id | VARCHAR | NO | | TrueLayer account ID (unique identifier from API) |
| account_type | VARCHAR | NO | | 'TRANSACTION' or 'PAYMENT' (from TrueLayer) |
| display_name | VARCHAR | NO | | User-friendly account name (e.g., 'Current Account') |
| currency | VARCHAR | NO | | ISO 4217 currency code |
| account_number_json | JSONB | YES | | Account number details from API |
| provider_data | JSONB | YES | | Additional provider-specific data |
| created_at | TIMESTAMP+TZ | YES | NOW() | Discovery timestamp |
| updated_at | TIMESTAMP+TZ | YES | NOW() | Last sync timestamp |
| last_synced_at | TIMESTAMP+TZ | YES | | Most recent transaction sync timestamp |

**Primary Key:** `id`
**Foreign Key:** `connection_id` → `bank_connections.id`
**Usage:** Discovered when user authorizes TrueLayer connection

---

### 5. `bank_connections`
OAuth connections to TrueLayer API (replaces legacy `truelayer_connections`).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| user_id | INTEGER | NO | | Foreign key to `users.id` |
| provider_id | VARCHAR | NO | | 'truelayer' (future: support other providers) |
| provider_name | VARCHAR | NO | | Display name of provider |
| access_token | TEXT | YES | | **ENCRYPTED** OAuth access token (decrypt before use) |
| refresh_token | TEXT | YES | | **ENCRYPTED** OAuth refresh token |
| token_expires_at | TIMESTAMP+TZ | YES | | Access token expiry time (UTC) |
| refresh_token_expires_at | TIMESTAMP+TZ | YES | | Refresh token expiry time |
| connection_status | VARCHAR | YES | 'authorization_required' | 'active', 'expired', 'authorization_required', 'inactive' |
| last_synced_at | TIMESTAMP+TZ | YES | | Most recent sync timestamp (all accounts) |
| created_at | TIMESTAMP+TZ | YES | NOW() | Connection creation timestamp |
| updated_at | TIMESTAMP+TZ | YES | NOW() | Last status update |

**Primary Key:** `id`
**Foreign Key:** `user_id` → `users.id`
**Encryption:** `access_token` and `refresh_token` use Fernet encryption (see `truelayer_auth.py`)

**CRITICAL IMPLEMENTATION RULES:**
- Always check `token_expires_at` before API calls; implement automatic refresh if expiring within 5 minutes
- Tokens must be decrypted before use with `decrypt_token()`
- New tokens must be encrypted before storage with `encrypt_token()`
- `last_synced_at` should be timezone-aware (datetime.now(timezone.utc))

---

### 6. `truelayer_balances`
Historical snapshots of account balances.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| account_id | INTEGER | NO | | Foreign key to `truelayer_accounts.id` |
| current_balance | NUMERIC | NO | | Current account balance |
| available_balance | NUMERIC | YES | | Available balance (may differ from current) |
| overdraft | NUMERIC | YES | | Overdraft limit (if applicable) |
| currency | VARCHAR | NO | | ISO currency code |
| snapshot_at | TIMESTAMP+TZ | NO | | Time balance was fetched (UTC) |
| created_at | TIMESTAMP+TZ | YES | NOW() | Record creation timestamp |

**Primary Key:** `id`
**Foreign Key:** `account_id` → `truelayer_accounts.id`

---

### 7. `truelayer_cards`
Credit/debit cards from TrueLayer API.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| connection_id | INTEGER | NO | | Foreign key to `bank_connections.id` |
| card_id | VARCHAR | NO | | TrueLayer card ID |
| card_name | VARCHAR | YES | | User-friendly card name |
| card_type | VARCHAR | YES | | 'CREDIT' or 'DEBIT' |
| last_four | VARCHAR | YES | | Last 4 digits (e.g., '1234') |
| issuer | VARCHAR | YES | | Card issuer name |
| status | VARCHAR | YES | | Card status |
| last_synced_at | TIMESTAMP | YES | | Most recent transaction sync |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP | Discovery timestamp |
| updated_at | TIMESTAMP | YES | CURRENT_TIMESTAMP | Last update timestamp |

**Primary Key:** `id`
**Foreign Key:** `connection_id` → `bank_connections.id`

---

### 8. `truelayer_card_transactions`
Card transactions from TrueLayer API.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| card_id | INTEGER | NO | | Foreign key to `truelayer_cards.id` |
| transaction_id | VARCHAR | YES | | TrueLayer transaction ID |
| normalised_provider_id | VARCHAR | YES | | Deduplication key |
| timestamp | TIMESTAMP | YES | | Transaction timestamp |
| description | TEXT | YES | | Merchant/transaction description |
| amount | NUMERIC | YES | | Transaction amount |
| currency | VARCHAR | YES | | ISO currency code |
| transaction_type | VARCHAR | YES | | 'DEBIT' or 'CREDIT' |
| category | VARCHAR | YES | | Transaction category |
| merchant_name | VARCHAR | YES | | Merchant name |
| running_balance | NUMERIC | YES | | Card balance after transaction |
| metadata | TEXT | YES | | Provider metadata (stored as string, not JSONB) |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP | Record creation timestamp |

**Primary Key:** `id`
**Foreign Key:** `card_id` → `truelayer_cards.id`

**NOTE:** Card transactions use TEXT for metadata (inconsistent with `truelayer_transactions` which uses JSONB). Future migration should standardize this.

---

### 9. `truelayer_card_balance_snapshots`
Historical balance snapshots for cards.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| card_id | INTEGER | NO | | Foreign key to `truelayer_cards.id` |
| current_balance | NUMERIC | YES | | Current card balance |
| currency | VARCHAR | YES | | ISO currency code |
| snapshot_at | TIMESTAMP | YES | | Time balance was fetched |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP | Record creation timestamp |

**Primary Key:** `id`
**Foreign Key:** `card_id` → `truelayer_cards.id`

---

### 10. `categories`
Transaction categories for classification.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| name | VARCHAR | NO | | Category name (e.g., 'Groceries', 'Transport') |
| rule_pattern | TEXT | YES | | Regex pattern for auto-classification |
| ai_suggested | BOOLEAN | YES | FALSE | Whether AI suggested this category |

**Primary Key:** `id`
**Unique Constraint:** `name` should be unique (validate in code if not enforced)

---

### 11. `category_keywords`
Keywords for category matching.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| category_name | VARCHAR | NO | | Associated category (e.g., 'Groceries') |
| keyword | VARCHAR | NO | | Keyword to match in descriptions |
| created_at | TIMESTAMP+TZ | YES | NOW() | Creation timestamp |

**Primary Key:** `id`
**Usage:** Matches keywords in transaction descriptions for auto-classification

---

### 12. `amazon_orders`
Amazon orders imported from statement.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| order_id | VARCHAR | NO | | Amazon order ID |
| order_date | DATE | NO | | Order placement date |
| website | VARCHAR | NO | | Amazon website (e.g., 'amazon.co.uk') |
| currency | VARCHAR | NO | | ISO currency code |
| total_owed | NUMERIC | NO | | Order total amount |
| product_names | TEXT | NO | | Comma-separated product names |
| order_status | VARCHAR | YES | | Order status |
| shipment_status | VARCHAR | YES | | Shipment status |
| source_file | VARCHAR | YES | | Source statement filename |
| created_at | TIMESTAMP+TZ | YES | NOW() | Import timestamp |

**Primary Key:** `id`
**Unique Constraint:** `order_id`

---

### 13. `amazon_returns`
Amazon returns/refunds.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| order_id | VARCHAR | NO | | Original order ID |
| reversal_id | VARCHAR | NO | | Return/refund ID |
| refund_completion_date | DATE | NO | | Date refund was completed |
| currency | VARCHAR | NO | | ISO currency code |
| amount_refunded | NUMERIC | NO | | Refund amount |
| status | VARCHAR | YES | | Refund status |
| disbursement_type | VARCHAR | YES | | How refund was disbursed |
| source_file | VARCHAR | YES | | Source file |
| original_transaction_id | INTEGER | YES | | FK to `transactions.id` if matched |
| refund_transaction_id | INTEGER | YES | | FK to `transactions.id` for refund entry |
| created_at | TIMESTAMP+TZ | YES | NOW() | Record creation timestamp |

**Primary Key:** `id`
**Foreign Keys:** `original_transaction_id`, `refund_transaction_id` → `transactions.id`

---

### 14. `amazon_transaction_matches`
Linking Amazon orders to bank transactions.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| transaction_id | INTEGER | NO | | FK to `transactions.id` |
| amazon_order_id | INTEGER | NO | | FK to `amazon_orders.id` |
| match_confidence | NUMERIC | NO | | Confidence score (0.0-1.0) |
| matched_at | TIMESTAMP+TZ | YES | NOW() | Match timestamp |

**Primary Key:** `id`
**Foreign Keys:**
- `transaction_id` → `transactions.id`
- `amazon_order_id` → `amazon_orders.id`

---

### 15. `apple_transactions`
Apple purchases imported from statement.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| order_id | VARCHAR | NO | | Apple order ID |
| order_date | DATE | NO | | Purchase date |
| total_amount | NUMERIC | NO | | Total amount spent |
| currency | VARCHAR | NO | | ISO currency code |
| app_names | TEXT | NO | | App/product names (comma-separated) |
| publishers | TEXT | YES | | Publisher names |
| item_count | INTEGER | YES | 1 | Number of items |
| source_file | VARCHAR | YES | | Source statement filename |
| created_at | TIMESTAMP+TZ | YES | NOW() | Import timestamp |

**Primary Key:** `id`
**Unique Constraint:** `order_id`

---

### 16. `apple_transaction_matches`
Linking Apple purchases to bank transactions.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| apple_transaction_id | INTEGER | NO | | FK to `apple_transactions.id` |
| bank_transaction_id | INTEGER | NO | | FK to `transactions.id` |
| confidence | INTEGER | NO | | Confidence score (0-100) |
| matched_at | TIMESTAMP+TZ | YES | NOW() | Match timestamp |

**Primary Key:** `id`
**Foreign Keys:**
- `apple_transaction_id` → `apple_transactions.id`
- `bank_transaction_id` → `transactions.id`

---

### 17. `truelayer_amazon_transaction_matches`
Linking TrueLayer transactions to Amazon orders (replaces metadata-based matching).

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key, auto-increment |
| truelayer_transaction_id | INTEGER | NO | | FK to `truelayer_transactions.id` |
| amazon_order_id | INTEGER | NO | | FK to `amazon_orders.id` |
| match_confidence | NUMERIC(5,2) | NO | | Confidence score (0.00-100.00) |
| matched_at | TIMESTAMP+TZ | YES | NOW() | Match timestamp |

**Primary Key:** `id`
**Foreign Keys:**
- `truelayer_transaction_id` → `truelayer_transactions.id` (ON DELETE CASCADE)
- `amazon_order_id` → `amazon_orders.id` (ON DELETE CASCADE)
**Unique Constraint:** `truelayer_transaction_id` (one match per transaction)

**Important Notes:**
- Replaces previous metadata-based matching approach
- Enables efficient relational queries for enrichment
- Populated by `match_truelayer_amazon_transaction()` function
- Linked to transaction display via `transaction_enrichment_sources` table

---

### 18. `amazon_business_connections`
OAuth connections for Amazon Business API.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| user_id | INTEGER | YES | 1 | User ID |
| access_token | TEXT | NO | | OAuth access token |
| refresh_token | TEXT | NO | | OAuth refresh token |
| token_expires_at | TIMESTAMP+TZ | YES | | Token expiry time |
| region | VARCHAR(10) | YES | 'UK' | Amazon region (UK, US, DE, etc.) |
| status | VARCHAR(20) | YES | 'active' | Connection status |
| created_at | TIMESTAMP+TZ | YES | NOW() | Creation timestamp |
| updated_at | TIMESTAMP+TZ | YES | NOW() | Last update timestamp |

**Primary Key:** `id`

---

### 19. `amazon_business_orders`
Amazon Business orders imported from API.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| order_id | VARCHAR(50) | NO | | Amazon order ID (unique) |
| order_date | DATE | NO | | Order date |
| region | VARCHAR(10) | YES | | Amazon region |
| purchase_order_number | VARCHAR(100) | YES | | PO number if used |
| order_status | VARCHAR(50) | YES | | Order status |
| buyer_name | VARCHAR(255) | YES | | Buyer name |
| buyer_email | VARCHAR(255) | YES | | Buyer email |
| subtotal | NUMERIC(12,2) | YES | | Order subtotal |
| tax | NUMERIC(12,2) | YES | | Tax amount |
| shipping | NUMERIC(12,2) | YES | | Shipping amount |
| net_total | NUMERIC(12,2) | YES | | Net total (used for matching) |
| currency | VARCHAR(10) | YES | 'GBP' | ISO currency code |
| item_count | INTEGER | YES | 1 | Number of items |
| product_summary | TEXT | YES | | Concatenated product titles (for enrichment sources) |
| created_at | TIMESTAMP+TZ | YES | NOW() | Import timestamp |

**Primary Key:** `id`
**Unique Constraint:** `order_id`
**Indexes:** `order_date`, `net_total`

---

### 20. `amazon_business_line_items`
Line item details for Amazon Business orders.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| order_id | VARCHAR(50) | NO | | FK to `amazon_business_orders.order_id` |
| line_item_id | VARCHAR(50) | YES | | Amazon line item ID |
| asin | VARCHAR(20) | YES | | Amazon product ASIN |
| title | TEXT | YES | | Product title |
| brand | VARCHAR(255) | YES | | Product brand |
| category | VARCHAR(255) | YES | | Product category |
| quantity | INTEGER | YES | | Quantity ordered |
| unit_price | NUMERIC(12,2) | YES | | Price per unit |
| total_price | NUMERIC(12,2) | YES | | Line item total |
| seller_name | VARCHAR(255) | YES | | Seller name |
| created_at | TIMESTAMP+TZ | YES | NOW() | Import timestamp |

**Primary Key:** `id`
**Foreign Keys:**
- `order_id` → `amazon_business_orders.order_id`
**Indexes:** `order_id`, `asin`

---

### 21. `truelayer_amazon_business_matches`
Linking TrueLayer transactions to Amazon Business orders.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| truelayer_transaction_id | INTEGER | NO | | FK to `truelayer_transactions.id` |
| amazon_business_order_id | INTEGER | NO | | FK to `amazon_business_orders.id` |
| match_confidence | INTEGER | NO | | Confidence score (0-100) |
| matched_at | TIMESTAMP+TZ | YES | NOW() | Match timestamp |

**Primary Key:** `id`
**Foreign Keys:**
- `truelayer_transaction_id` → `truelayer_transactions.id`
- `amazon_business_order_id` → `amazon_business_orders.id`
**Unique Constraint:** `truelayer_transaction_id` (one match per transaction)
**Index:** `amazon_business_order_id`

**Important Notes:**
- Separate from consumer `truelayer_amazon_transaction_matches` - for business purchases only
- Populated by `match_truelayer_amazon_business_transaction()` function
- Creates entries in `transaction_enrichment_sources` with `product_summary` from orders

---

### 22. `account_mappings`
Mapping of Santander account details to friendly names.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| sort_code | VARCHAR | NO | | Bank sort code |
| account_number | VARCHAR | NO | | Account number |
| friendly_name | VARCHAR | NO | | User-friendly account name |
| created_at | TIMESTAMP+TZ | YES | NOW() | Creation timestamp |

**Primary Key:** `id`

---

### 19. `oauth_state`
OAuth state parameters for CSRF protection.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| user_id | INTEGER | NO | | FK to `users.id` |
| state | VARCHAR | NO | | OAuth state token |
| code_verifier | TEXT | NO | | PKCE code verifier |
| expires_at | TIMESTAMP | NO | | State expiry time (must check before callback) |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP | Creation timestamp |

**Primary Key:** `id`
**Foreign Key:** `user_id` → `users.id`
**SECURITY:** Validate `state` token in callback handler; check `expires_at` before accepting

---

### 20. `connection_logs`
Audit logs for OAuth connections.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| connection_id | INTEGER | YES | | FK to `bank_connections.id` |
| event_type | VARCHAR | NO | | 'authorized', 'token_refreshed', 'sync_started', 'sync_completed', 'sync_failed', 'disconnected' |
| details | JSONB | YES | | Event-specific metadata |
| created_at | TIMESTAMP+TZ | YES | NOW() | Event timestamp |

**Primary Key:** `id`
**Foreign Key:** `connection_id` → `bank_connections.id` (optional)

---

### 21. `webhook_events`
Incoming webhook events from TrueLayer.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| event_id | VARCHAR | NO | | Unique webhook event ID |
| event_type | VARCHAR | NO | | Type of webhook event |
| payload | JSONB | NO | | Webhook payload data |
| signature | TEXT | NO | | HMAC signature for verification |
| processed | BOOLEAN | YES | FALSE | Whether event was processed |
| processed_at | TIMESTAMP+TZ | YES | | Event processing timestamp |
| received_at | TIMESTAMP+TZ | YES | NOW() | Event receipt timestamp |

**Primary Key:** `id`
**Unique Constraint:** `event_id` (prevent duplicate processing)
**SECURITY:** Always verify signature before processing

---

### 22. `truelayer_connections` (LEGACY)
**Status:** DEPRECATED - Use `bank_connections` instead

This table is no longer used. Kept for historical reference. All new code must use `bank_connections`.

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| user_id | INTEGER | NO | | FK to `users.id` |
| provider_id | VARCHAR | YES | | Provider identifier |
| access_token | TEXT | NO | | **ENCRYPTED** OAuth token |
| refresh_token | TEXT | YES | | **ENCRYPTED** refresh token |
| token_expires_at | TIMESTAMP | YES | | Token expiry |
| connection_status | VARCHAR | YES | 'active' | Connection status |
| last_synced_at | TIMESTAMP | YES | | Last sync time |
| created_at | TIMESTAMP | YES | CURRENT_TIMESTAMP | Creation timestamp |

**DO NOT USE IN NEW CODE** - All references should be migrated to `bank_connections`

---

## Gmail Integration Tables

The Gmail integration uses 4 tables to store OAuth credentials, parsed receipts, raw email content, and PDF attachments.

### 23. `gmail_connections`
**Purpose:** OAuth credentials for Gmail API access

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| user_id | INTEGER | NO | 1 | FK to `users.id` |
| email_address | VARCHAR(255) | NO | | Gmail address |
| access_token | TEXT | NO | | **ENCRYPTED** OAuth token |
| refresh_token | TEXT | NO | | **ENCRYPTED** refresh token |
| token_expires_at | TIMESTAMP+TZ | YES | | Token expiry |
| encryption_version | INTEGER | YES | 1 | Token encryption version |
| scopes | TEXT | YES | | OAuth scopes granted |
| connection_status | VARCHAR(20) | YES | 'active' | Status: active, expired, revoked, error |
| history_id | VARCHAR(50) | YES | | Gmail history ID for incremental sync |
| last_synced_at | TIMESTAMP+TZ | YES | | Last successful sync |
| sync_from_date | DATE | YES | | Oldest date to sync from |
| error_count | INTEGER | YES | 0 | Consecutive error count |
| last_error | TEXT | YES | | Last error message |
| created_at | TIMESTAMP+TZ | YES | NOW() | Creation timestamp |
| updated_at | TIMESTAMP+TZ | YES | NOW() | Last update timestamp |

**Primary Key:** `id`
**Unique Constraint:** `(user_id, email_address)`
**Check Constraint:** `connection_status` IN ('active', 'expired', 'revoked', 'error')
**SECURITY:** Tokens are encrypted with `ENCRYPTION_KEY` env var

---

### 24. `gmail_receipts`
**Purpose:** Parsed receipt metadata from Gmail

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| connection_id | INTEGER | NO | | FK to `gmail_connections.id` |
| message_id | VARCHAR(255) | NO | | Gmail message ID (unique) |
| thread_id | VARCHAR(255) | YES | | Gmail thread ID |
| sender_email | VARCHAR(255) | NO | | Email sender address |
| sender_name | VARCHAR(255) | YES | | Email sender display name |
| subject | TEXT | YES | | Email subject line |
| received_at | TIMESTAMP+TZ | NO | | Email receipt timestamp |
| merchant_name | VARCHAR(255) | YES | | Extracted merchant name |
| merchant_name_normalized | VARCHAR(255) | YES | | Normalised merchant for matching |
| merchant_domain | VARCHAR(255) | YES | | Merchant domain from sender |
| order_id | VARCHAR(255) | YES | | Order/reference number |
| total_amount | NUMERIC(12,2) | YES | | Extracted total amount |
| currency_code | VARCHAR(3) | YES | 'GBP' | Currency code (ISO 4217) |
| receipt_date | DATE | YES | | Purchase date (if different from email) |
| line_items | JSONB | YES | | Parsed line items array |
| receipt_hash | VARCHAR(64) | YES | | Deduplication hash |
| parse_method | VARCHAR(30) | YES | | How receipt was parsed (see CHECK) |
| parse_confidence | INTEGER | NO | | Confidence 0-100 |
| raw_schema_data | JSONB | YES | | Raw Schema.org data if found |
| llm_cost_cents | INTEGER | YES | | LLM parsing cost |
| parsing_status | VARCHAR(20) | YES | 'pending' | Status: pending, parsed, failed, matched, unparseable |
| parsing_error | TEXT | YES | | Error message if failed |
| retry_count | INTEGER | YES | 0 | Number of parse retries |
| deleted_at | TIMESTAMP+TZ | YES | | Soft delete timestamp |
| created_at | TIMESTAMP+TZ | YES | NOW() | Creation timestamp |
| updated_at | TIMESTAMP+TZ | YES | NOW() | Last update timestamp |
| llm_parse_status | VARCHAR(20) | YES | NULL | LLM queue status: pending, processing, completed, failed |
| llm_estimated_cost_cents | INTEGER | YES | | Estimated LLM cost |
| llm_actual_cost_cents | INTEGER | YES | | Actual LLM cost incurred |
| llm_parsed_at | TIMESTAMP+TZ | YES | | When LLM parsing completed |
| body_html | TEXT | YES | | Email HTML body (optional cache) |
| body_text | TEXT | YES | | Email text body (optional cache) |

**Primary Key:** `id`
**Unique Constraint:** `message_id`
**Foreign Key:** `connection_id` → `gmail_connections.id` (CASCADE DELETE)
**Check Constraints:**
- `parse_confidence` BETWEEN 0 AND 100
- `parsing_status` IN ('pending', 'parsed', 'failed', 'matched', 'unparseable')
- `parse_method` IN ('schema_org', 'pattern', 'llm', 'manual', 'pending', 'pre_filter', 'unknown', 'generic_pdf', 'none', 'vendor_*')
- `llm_parse_status` IN (NULL, 'pending', 'processing', 'completed', 'failed')

**Indexes:**
- `idx_gmail_receipts_connection` ON (connection_id)
- `idx_gmail_receipts_connection_date` ON (connection_id, receipt_date)
- `idx_gmail_receipts_merchant` ON (merchant_name_normalized)
- `idx_gmail_receipts_amount_date` ON (total_amount, receipt_date)
- `idx_gmail_receipts_not_deleted` ON (id) WHERE deleted_at IS NULL

---

### 25. `gmail_email_content`
**Purpose:** Raw email content for re-parsing (separate from parsed data)

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| message_id | VARCHAR(255) | NO | | Gmail message ID (unique) |
| thread_id | VARCHAR(255) | YES | | Gmail thread ID |
| subject | TEXT | YES | | Email subject |
| from_header | TEXT | YES | | From header (raw) |
| to_header | TEXT | YES | | To header (raw) |
| date_header | TEXT | YES | | Date header (raw) |
| list_unsubscribe | TEXT | YES | | List-Unsubscribe header |
| x_mailer | TEXT | YES | | X-Mailer header |
| body_html | TEXT | YES | | Full HTML body |
| body_text | TEXT | YES | | Plain text body |
| snippet | TEXT | YES | | Gmail snippet preview |
| attachments | JSONB | YES | | Attachment metadata array |
| size_estimate | INTEGER | YES | | Email size in bytes |
| received_at | TIMESTAMP+TZ | YES | | Email receipt timestamp |
| fetched_at | TIMESTAMP+TZ | YES | NOW() | When content was fetched |

**Primary Key:** `id`
**Unique Constraint:** `message_id`
**Indexes:**
- `idx_gmail_email_content_message_id` ON (message_id)
- `idx_gmail_email_content_received` ON (received_at)

**Usage:** This table stores raw email content separately from parsed receipt data in `gmail_receipts`. This allows:
- Re-parsing emails with updated vendor parsers without re-fetching from Gmail
- Debugging parsing issues by examining original content
- Reducing Gmail API calls for emails already fetched

---

### 26. `pdf_attachments`
**Purpose:** Metadata for PDF attachments stored in MinIO object storage

| Column | Type | Nullable | Default | Notes |
|--------|------|----------|---------|-------|
| id | INTEGER | NO | AUTO | Primary key |
| gmail_receipt_id | INTEGER | YES | | FK to `gmail_receipts.id` |
| message_id | VARCHAR(255) | NO | | Gmail message ID |
| bucket_name | VARCHAR(100) | YES | 'receipts' | MinIO bucket name |
| object_key | VARCHAR(500) | NO | | MinIO object key (unique) |
| filename | VARCHAR(255) | NO | | Original filename |
| content_hash | VARCHAR(64) | NO | | SHA-256 hash for deduplication |
| size_bytes | INTEGER | NO | | File size |
| mime_type | VARCHAR(100) | YES | 'application/pdf' | MIME type |
| etag | VARCHAR(64) | YES | | MinIO ETag |
| created_at | TIMESTAMP+TZ | YES | NOW() | Upload timestamp |

**Primary Key:** `id`
**Unique Constraints:**
- `object_key`
- `(message_id, filename)`

**Foreign Key:** `gmail_receipt_id` → `gmail_receipts.id` (CASCADE DELETE)
**Indexes:**
- `idx_pdf_attachments_receipt` ON (gmail_receipt_id)
- `idx_pdf_attachments_hash` ON (content_hash)

**Object Key Format:** `{year}/{month:02d}/{day:02d}/{message_id}/{filename}`

**MinIO Storage:**
- Bucket: `receipts` (configurable via `MINIO_BUCKET` env var)
- Endpoint: `localhost:9000` (host) or `minio:9000` (Docker network)
- Web Console: `http://localhost:9001`
- API: S3-compatible (use `minio` Python package)

---

## Data Type Guidelines

### Date/Time Fields
- **Timestamps with timezone:** Use `TIMESTAMP WITH TIME ZONE` (or `TIMESTAMP+TZ`)
  - Always store in UTC
  - Use `datetime.now(timezone.utc)` in Python
  - Convert to user's timezone on frontend

- **Timestamps without timezone:** Use `TIMESTAMP WITHOUT TIME ZONE`
  - Legacy - avoid in new tables
  - Assume UTC if used

- **Date only:** Use `DATE` type
  - No timezone information
  - For date-only data (e.g., transaction date from statement)

### Amounts/Financial Data
- **Use `NUMERIC` for all monetary amounts** (NOT FLOAT/DOUBLE)
  - Prevents floating-point precision errors
  - Example: `NUMERIC(15,2)` for GBP transactions
  - Always use database's numeric type, not Python float

### Token Storage
- **Access tokens:** Store in `TEXT` column, **ALWAYS ENCRYPTED**
  - Use `encrypt_token(token)` before INSERT
  - Use `decrypt_token(encrypted)` before use
  - NEVER log or display tokens

### JSON Data
- **Use `JSONB` for structured metadata** (not TEXT)
  - Allows efficient querying with PostgreSQL operators
  - Validates JSON on insertion
  - Use `json.dumps(dict)` in Python before INSERT
  - PostgreSQL automatically handles validation

- **Use `TEXT` only for free-form data** (legacy, avoid)
  - Cannot be queried efficiently
  - Should be migrated to JSONB

---

## Foreign Key Relationships

```
users
  ├─ bank_connections (user_id)
  │   ├─ truelayer_accounts (connection_id)
  │   │   ├─ truelayer_transactions (account_id)
  │   │   │   ├─ transaction_enrichment_sources (truelayer_transaction_id)
  │   │   │   │   └─ [polymorphic: amazon_orders, apple_transactions, gmail_receipts]
  │   │   │   └─ truelayer_amazon_transaction_matches (truelayer_transaction_id)
  │   │   └─ truelayer_balances (account_id)
  │   ├─ truelayer_cards (connection_id)
  │   │   ├─ truelayer_card_transactions (card_id)
  │   │   └─ truelayer_card_balance_snapshots (card_id)
  │   └─ connection_logs (connection_id)
  ├─ oauth_state (user_id)
  └─ transactions (implicit user via bank_connections)

transactions
  ├─ amazon_transaction_matches (transaction_id)
  │   └─ amazon_orders (amazon_order_id)
  └─ apple_transaction_matches (bank_transaction_id)
      └─ apple_transactions (apple_transaction_id)

transaction_enrichment_sources (unified enrichment)
  └─ Polymorphic references via source_type + source_id:
      ├─ amazon_orders (source_type='amazon')
      ├─ amazon_business_orders (source_type='amazon_business')
      ├─ apple_transactions (source_type='apple')
      └─ gmail_receipts (source_type='gmail')
```

---

## API Endpoint Data Format Rules

### Combining Transaction Sources

The `/api/transactions` endpoint returns both `transactions` and `truelayer_transactions` combined:

```python
# Backend (app.py)
regular_transactions = database.get_all_transactions() or []
truelayer_transactions = database.get_all_truelayer_transactions() or []
all_transactions = regular_transactions + truelayer_transactions
all_transactions.sort(key=lambda t: t.get('date') or t.get('timestamp'), reverse=True)
```

**Field Mapping Issues:**
- Regular transactions use: `date`, `description`, `amount`, `category`, `merchant`
- TrueLayer transactions use: `timestamp`, `description`, `amount`, `transaction_category`, `merchant_name`

**Frontend must handle both field names** - Use:
```javascript
const transactionDate = transaction.date || transaction.timestamp;
const category = transaction.category || transaction.transaction_category;
const merchant = transaction.merchant || transaction.merchant_name;
```

---

## Best Practices for Code

### When Adding New Columns

1. **Document in this file FIRST**
   - Add to the table section
   - Include Column, Type, Nullable, Default, Notes
   - Explain the purpose and data constraints

2. **Create a migration script** (if schema change is permanent)
   - File: `backend/db/migrations/YYYY-MM-DD_description.sql`
   - Include both UP and DOWN migrations

3. **Update database functions** in `database_postgres.py`
   - Add new column to SELECT statements
   - Add new column to INSERT statements
   - Update corresponding getter functions

4. **Update this documentation**
   - Add entry to "Schema Changes" section with date
   - Update the table's column list
   - Note any code changes required

### When Modifying Column Types

1. **Never modify in production without migration**
2. **Always create a migration that:**
   - Creates backup/copy of data
   - Converts to new type
   - Tests conversion integrity
3. **Update documentation** with migration details

### When Writing SQL Queries

```python
# GOOD - Explicit column selection
cursor.execute('''
    SELECT id, description, amount, currency, timestamp
    FROM truelayer_transactions
    WHERE account_id = %s
''', (account_id,))

# BAD - SELECT * (breaks if columns change)
cursor.execute('SELECT * FROM truelayer_transactions WHERE account_id = %s', (account_id,))

# CORRECT - Use RealDictCursor for dict results
with conn.cursor(cursor_factory=RealDictCursor) as cursor:
    cursor.execute(...select..., params)
    results = cursor.fetchall()  # Returns list of dicts
```

### When Inserting TrueLayer Data

```python
# CRITICAL RULES:
# 1. Extract scalar values from API dicts
running_balance = txn.get('running_balance')
if isinstance(running_balance, dict):
    running_balance = running_balance.get('amount')

# 2. Use json.dumps() for JSONB columns
metadata = {'provider_id': ..., 'meta': ...}
cursor.execute(..., (..., json.dumps(metadata)))

# 3. Use timezone-aware datetimes
from datetime import datetime, timezone
expires_at = datetime.now(timezone.utc)

# 4. Encrypt tokens before storage
from mcp.truelayer_auth import encrypt_token
encrypted_token = encrypt_token(access_token)
```

---

## Common Queries

### Get all transactions for a user (newest first)
```python
# Both regular and TrueLayer transactions combined
transactions = database.get_all_transactions()  # Regular
transactions.extend(database.get_all_truelayer_transactions())  # Add TrueLayer
transactions.sort(key=lambda t: t.get('date') or t.get('timestamp'), reverse=True)
```

### Check if token needs refresh
```python
from datetime import datetime, timedelta, timezone

connection = database.get_connection(connection_id)
expires_at = connection.get('token_expires_at')

# Convert to timezone-aware if needed
if isinstance(expires_at, str):
    expires_at = datetime.fromisoformat(expires_at)
elif expires_at.tzinfo is None:
    expires_at = expires_at.replace(tzinfo=timezone.utc)

# Check if expires within 5 minutes
if expires_at < datetime.now(timezone.utc) + timedelta(minutes=5):
    # Refresh token
```

### Deduplicate TrueLayer transactions
```python
# Check if transaction already exists (by normalised ID)
existing = database.get_truelayer_transaction_by_id(
    normalised_provider_transaction_id
)
if not existing:
    # Insert new transaction
    database.insert_truelayer_transaction(...)
```

---

## Security Considerations

1. **Token Storage:**
   - Always encrypt before storage
   - Always decrypt before use
   - NEVER log token values
   - Use environment variable for encryption key

2. **OAuth State:**
   - Verify `state` parameter matches stored value
   - Check `expires_at` timestamp
   - Use `secrets.compare_digest()` for timing-safe comparison

3. **Webhook Signatures:**
   - Always verify HMAC signature
   - Do not process unverified events
   - Log verification failures

4. **SQL Injection:**
   - Use parameterized queries with `%s` placeholders
   - NEVER use string formatting for SQL
   - Always pass values as separate tuple to execute()

---

## Migration Procedures

### When Adding a Column

```python
# 1. Create migration SQL file
# File: backend/db/migrations/2025-11-27_add_column.sql

# 2. Migration UP (adding column)
ALTER TABLE truelayer_transactions ADD COLUMN new_field VARCHAR;

# 3. Migration DOWN (removing column)
ALTER TABLE truelayer_transactions DROP COLUMN new_field;

# 4. Run migration on database
docker exec spending-postgres psql -U spending_user -d spending_db -f /path/to/migration.sql

# 5. Update database_postgres.py functions
# Add new_field to SELECT, INSERT statements

# 6. Update this documentation
# Add entry to Schema Changes, update table definition
```

---

## Maintenance

- **Last Reviewed:** 2025-11-27
- **Maintenance Window:** Weekly (every Monday)
- **Backup Frequency:** Daily (via Docker volume)
- **Reindex Frequency:** Monthly

### How to Update This Document

When making schema changes:
1. Add entry to "Schema Changes" section (at top)
2. Update or add table definition
3. Note any code files that need updating
4. Update "Last Reviewed" date at bottom
5. Commit documentation and code changes together
