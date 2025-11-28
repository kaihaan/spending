# TrueLayer Transaction Import & Enrichment Workflow Analysis

**Date:** 2025-11-28
**Status:** Complete
**Scope:** End-to-end workflow from OAuth to transaction enrichment

---

## 1. Complete Workflow Overview

### 1.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                    USER INITIATES CONNECTION                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  GET /api/truelayer/authorize       │
        │  - Generate OAuth URL with PKCE     │
        │  - Create state & code_verifier     │
        │  - Store PKCE in database           │
        │  - Return auth URL to frontend      │
        └──────────────────┬──────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  TrueLayer OAuth Login              │
        │  - User authenticates               │
        │  - Grants permission to app         │
        └──────────────────┬──────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  GET /api/truelayer/callback        │
        │  - Receive auth code & state        │
        │  - Validate PKCE state              │
        │  - Exchange code for tokens         │
        │  - Encrypt & store tokens           │
        │  - Discover accounts from API       │
        │  - Save accounts to database        │
        └──────────────────┬──────────────────┘
                           │
                           ▼
        ┌─────────────────────────────────────┐
        │  Connection Established ✓           │
        │  - Bank accounts ready for sync     │
        │  - OAuth tokens securely stored     │
        └─────────────────────────────────────┘
```

### 1.2 Transaction Sync & Enrichment Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│              POST /api/truelayer/sync OR Webhook Event             │
│              (Manual trigger or automatic via webhook)              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
        ┌──────────────────┴──────────────────┐
        │  For each user connection:          │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  1. Refresh Token if Needed         │
        │     - Check expiration              │
        │     - Refresh within 5min buffer    │
        │     - Update encrypted tokens       │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  2. Decrypt Access Token            │
        │     - Retrieve from DB              │
        │     - Decrypt using Fernet key      │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────┐
        │  3. For each account:               │
        │     - Calculate sync window         │
        │     - Incremental or full sync      │
        └──────────────────┬──────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────┐
        │  4. Fetch Transactions from TrueLayer API       │
        │     client.fetch_all_transactions(              │
        │       account_id, days_back=sync_days           │
        │     )                                            │
        │     Returns:                                     │
        │     - Normalized transaction objects            │
        │     - Debit/Credit classifications              │
        │     - Running balance                           │
        │     - Metadata from provider                    │
        └──────────────────┬──────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────┐
        │  5. Normalize Transactions                      │
        │     TrueLayer format ──▶ App schema             │
        │     {                                            │
        │       'date': ISO 8601                          │
        │       'description': str                        │
        │       'amount': Decimal (absolute)              │
        │       'transaction_type': DEBIT|CREDIT          │
        │       'running_balance': Decimal                │
        │       'merchant_name': extracted or from API    │
        │       'category': 'Other' (placeholder)         │
        │       'normalised_provider_id': unique key      │
        │       'metadata': {...}                         │
        │     }                                            │
        └──────────────────┬──────────────────────────────┘
                           │
        ┌──────────────────▼──────────────────────────────┐
        │  6. Deduplication Check                         │
        │     - Query DB by normalised_provider_id        │
        │     - Skip if exists (count as duplicate)       │
        │     - UNIQUE constraint on DB level             │
        └──────────────────┬──────────────────────────────┘
        │ (Duplicates)     │ (New)
        │                  │
        │     Skip          ▼
        │              ┌──────────────────────────────┐
        │              │  7. Insert into DB           │
        │              │     truelayer_transactions   │
        │              │     INSERT transaction       │
        │              │     + Update timestamps      │
        │              └──────────────┬───────────────┘
        │                             │
        └─────────────┬───────────────┘
                      │
                      ▼
        ┌────────────────────────────────────┐
        │  8. Sync Complete Summary          │
        │     - Count synced transactions    │
        │     - Count duplicates             │
        │     - Count errors                 │
        │     - Update last_synced_at        │
        └────────────────┬───────────────────┘
                         │
                         ▼
        ┌────────────────────────────────────┐
        │  Return Sync Result                │
        │  {                                  │
        │    status: 'completed',             │
        │    summary: {                       │
        │      total_accounts,                │
        │      total_synced,                  │
        │      total_duplicates,              │
        │      total_errors                   │
        │    }                                │
        │  }                                  │
        └────────────────────────────────────┘
```

### 1.3 Transaction Enrichment Workflow (Separate Process)

> **⚠️ IMPORTANT:** TrueLayer sync does NOT auto-trigger enrichment. Enrichment must be called separately or manually triggered.

```
┌─────────────────────────────────────────────────────────────────┐
│  LLM Enrichment Process (Manual or Scheduled)                   │
│  Note: Currently only auto-triggers for Santander Excel imports │
└────────────────┬────────────────────────────────────────────────┘
                 │
    ┌────────────▼────────────┐
    │  1. Query Unenriched     │
    │     Transactions         │
    │     - Load TrueLayer     │
    │       transactions       │
    │     - With category=     │
    │       'Other'            │
    └────────────┬─────────────┘
                 │
    ┌────────────▼────────────────────────────────┐
    │  2. Check Enrichment Cache                  │
    │     - Query enrichment_cache table          │
    │     - By description & direction            │
    │     - Skip if cache hit (saves API cost)    │
    └────────────┬─────────────────────────────────┘
                 │
    ┌────────────▼────────────────────────────────┐
    │  3. Separate Transactions by Status         │
    │     ├─ Already enriched in DB (skip)        │
    │     ├─ Cache hits (use cached result)       │
    │     └─ Need enrichment (send to LLM)        │
    └────────────┬─────────────────────────────────┘
                 │
    ┌────────────▼──────────────────────────────────────┐
    │  4. Calculate Dynamic Batch Size                  │
    │     - Base: 20 transactions                       │
    │     - Adjust by provider limits:                  │
    │       Anthropic: 20                               │
    │       OpenAI: 15                                  │
    │       Google: 5 (free tier)                       │
    │       Deepseek: 25                                │
    │       Ollama: 5 (local inference)                 │
    │     - Reduce for expensive models (e.g., Opus)    │
    └────────────┬──────────────────────────────────────┘
                 │
    ┌────────────▼──────────────────────────────────────┐
    │  5. Process Batches to LLM                        │
    │     For each batch:                               │
    │     ├─ Build request with transaction data        │
    │     ├─ Include lookup_description if available    │
    │     │  (from Amazon/Apple matching)               │
    │     ├─ Query LLM API                              │
    │     └─ Collect stats (tokens, cost)               │
    │                                                   │
    │     Returned enrichment for each transaction:     │
    │     {                                             │
    │       primary_category: str,                      │
    │       subcategory: str,                           │
    │       merchant_clean_name: str,                   │
    │       merchant_type: str,                         │
    │       essential_discretionary: str,               │
    │       payment_method: str,                        │
    │       confidence_score: float,                    │
    │       llm_provider: str,                          │
    │       llm_model: str                              │
    │     }                                             │
    └────────────┬──────────────────────────────────────┘
                 │
    ┌────────────▼────────────────────────────────────────┐
    │  6. Cache Enrichment Results (if enabled)           │
    │     - Store in enrichment_cache table               │
    │     - Key: (description, direction, provider)       │
    │     - For future reuse on similar transactions      │
    └────────────┬─────────────────────────────────────────┘
                 │
    ┌────────────▼─────────────────────────────────────────┐
    │  7. Update Transactions with Enrichment              │
    │     - Update transaction_enrichments table           │
    │     - Set transaction category                       │
    │     - Update merchant name                           │
    │     - Record enrichment source (LLM or cache)        │
    │     - Track cost & token usage                       │
    └────────────┬──────────────────────────────────────────┘
                 │
    ┌────────────▼──────────────────────────────────────────┐
    │  8. Return Enrichment Statistics                      │
    │     {                                                 │
    │       total_transactions: int,                        │
    │       successful_enrichments: int,                    │
    │       failed_enrichments: int,                        │
    │       cached_hits: int,                               │
    │       api_calls_made: int,                            │
    │       total_tokens_used: int,                         │
    │       total_cost: float                               │
    │     }                                                 │
    └──────────────────────────────────────────────────────┘
```

---

## 2. Data Flow Details

### 2.1 OAuth Token Flow

**Storage:** `bank_connections` table

```python
{
  'id': 1,                          # Primary key
  'user_id': 1,                     # Foreign key to users
  'provider_id': 'truelayer',       # Provider name
  'provider_name': 'TrueLayer',     # Display name
  'access_token': '...encrypted...', # Encrypted with Fernet
  'refresh_token': '...encrypted...', # Encrypted with Fernet
  'token_expires_at': '2025-12-05T14:30:00Z', # UTC timestamp
  'refresh_token_expires_at': '2025-12-20T14:30:00Z',
  'connection_status': 'active',    # 'active', 'expired', 'authorization_required'
  'last_synced_at': '2025-11-28T21:30:00Z', # Last sync timestamp
  'created_at': '2025-11-01T10:00:00Z',
  'updated_at': '2025-11-28T21:30:00Z'
}
```

**Token Refresh Logic:**
1. Before each sync, check token expiration
2. If expires within 5 minutes, refresh immediately
3. Decrypt refresh token → Call TrueLayer API → Encrypt new tokens
4. Update database with new token and expiration

### 2.2 Account Discovery

**Storage:** `truelayer_accounts` table

```python
{
  'id': 1,                           # Primary key
  'connection_id': 1,                # Foreign key to bank_connections
  'account_id': 'acc_a1b2c3d4e5',   # TrueLayer account ID
  'account_type': 'TRANSACTION',     # Account type from API
  'display_name': 'Current Account', # User-friendly name
  'currency': 'GBP',                 # Transaction currency
  'account_number_json': {...},      # Account number details (JSONB)
  'provider_data': {...},            # Additional metadata (JSONB)
  'last_synced_at': '2025-11-28T21:30:00Z',
  'created_at': '2025-11-01T10:00:00Z',
  'updated_at': '2025-11-28T21:30:00Z'
}
```

### 2.3 Transaction Storage

**Storage:** `truelayer_transactions` table

```python
{
  'id': 1,
  'account_id': 1,                          # FK to truelayer_accounts
  'transaction_id': 'txn_abc123',           # TrueLayer transaction ID
  'normalised_provider_transaction_id': 'norm_abc123_def456', # Dedup key (UNIQUE)
  'timestamp': '2025-11-28T14:30:00Z',      # ISO 8601 UTC
  'description': 'TESCO STORES 1234',       # Merchant/transaction text
  'amount': 42.75,                          # Absolute value (Decimal)
  'currency': 'GBP',
  'transaction_type': 'DEBIT',              # DEBIT or CREDIT
  'transaction_category': 'Other',          # Initial: 'Other' until enriched
  'merchant_name': 'TESCO STORES',          # Extracted merchant
  'running_balance': 1234.56,               # Account balance after txn
  'metadata': {                             # JSONB
    'provider_id': 'truelayer',
    'provider_transaction_id': 'txn_abc123',
    'meta': {...}
  },
  'created_at': '2025-11-28T21:30:00Z'
}
```

### 2.4 Enrichment Storage

**Storage:** `transaction_enrichments` table

```python
{
  'id': 1,
  'transaction_id': 1,                      # FK to truelayer_transactions
  'primary_category': 'Groceries',          # Main category
  'subcategory': 'Supermarket',             # Sub-category
  'merchant_clean_name': 'Tesco',           # Cleaned merchant name
  'merchant_type': 'Retail',                # Merchant type
  'essential_discretionary': 'Essential',   # Essential vs Discretionary
  'payment_method': 'Card Debit',           # Payment method
  'confidence_score': 0.95,                 # 0.0 - 1.0
  'llm_provider': 'anthropic',              # Provider used
  'llm_model': 'claude-3-5-sonnet',         # Model used
  'enrichment_source': 'llm',               # 'llm' or 'cache'
  'created_at': '2025-11-28T21:30:00Z'
}
```

**Cache Storage:** `enrichment_cache` table

```python
{
  'id': 1,
  'description_hash': 'abc123hash',         # Hash of description for indexing
  'description': 'TESCO STORES 1234',       # Original transaction description
  'direction': 'out',                       # 'in' (income) or 'out' (expense)
  'enrichment': {...},                      # Full enrichment object (JSONB)
  'provider': 'anthropic',                  # Provider that cached this
  'model': 'claude-3-5-sonnet',             # Model used
  'hit_count': 5,                           # Number of times used
  'created_at': '2025-11-28T21:30:00Z',
  'updated_at': '2025-11-28T21:30:00Z'
}
```

---

## 3. Performance Analysis

### 3.1 Current Bottlenecks

#### A. **Sequential Processing of Accounts** ⚠️ HIGH IMPACT
- **Current:** Sync processes accounts sequentially
- **Location:** `sync_all_accounts()` in `truelayer_sync.py:301-396`
- **Issue:**
  - User with 3 accounts takes 3x longer than 1 account
  - Each account waits for previous account API call to complete
  - No parallelization of independent account syncs
- **Impact:** For user with 5 accounts × 100 txns each:
  - Sequential: ~5 seconds (assuming 1 sec per account)
  - Parallel: ~1 second

#### B. **Enrichment Not Auto-Triggered After TrueLayer Sync** ⚠️ MEDIUM IMPACT
- **Current:** TrueLayer sync stores transactions with category='Other'
  - No automatic enrichment trigger post-sync
  - Only Santander Excel imports auto-enrich (see `app.py:206-230`)
  - Users must manually trigger enrichment or wait for scheduled job
- **Impact:**
  - TrueLayer transactions remain unenriched until manual action
  - User sees "Other" category for hours/days
  - Inconsistent UX vs Santander imports

#### C. **Inefficient Incremental Sync Window Calculation** ⚠️ MEDIUM IMPACT
- **Current:** Uses `last_synced_at` from connection, then adds 1-day buffer
  - Location: `truelayer_sync.py:94-128`
- **Logic:**
  ```python
  days_since_sync = (now_utc - last_sync).days  # e.g., 2 days
  sync_days = max(1, days_since_sync + 1)       # Requests 3 days of data
  ```
- **Problem:**
  - Adds unnecessary 1-day buffer (fetches redundant data)
  - Account-level `last_synced_at` not tracked separately
  - Could miss transactions posted just before sync time
- **Impact:** ~15-20% unnecessary API calls

#### D. **No Connection-Level Sync Status Tracking** ⚠️ LOW-MEDIUM IMPACT
- **Current:** Only updates `bank_connections.last_synced_at` once per full sync
  - Per-account timestamps exist but not reliably used
  - Cannot query which accounts still need syncing
- **Impact:**
  - Hard to resume failed syncs
  - Cannot implement per-account retry logic
  - Webhook processing doesn't track per-account sync status

#### E. **Batch Size Limitations** ⚠️ LOW IMPACT
- **Current:** Dynamic batch sizing in enricher, but conservative limits
  - Google: 5 (due to free tier)
  - Ollama: 5 (local inference)
  - Anthropic: 20
- **For enrichment:** 100 transactions needs 5-20 API calls vs 1-2 for larger batch
- **Impact:** 5-10x more API calls than necessary for Google/Ollama

#### F. **Manual Token Refresh Before Sync** ⚠️ LOW IMPACT
- **Current:** Manually decrypt, check, and refresh tokens
  - Error handling for parse failures
  - No async execution
- **Impact:** 100-200ms per connection per sync
  - Minor for single user, adds up with many users

### 3.2 Database Query Inefficiencies

#### A. **Deduplication Check Per Transaction**
- **Current:** Separate DB query per transaction during sync
  - `database.get_truelayer_transaction_by_id(normalised_id)` called 100+ times
  - Location: `truelayer_sync.py:147`
- **Alternative:** Batch deduplication check
- **Impact:** 100 queries vs 1 query = 500-1000ms savings

#### B. **Account Lookup During Webhook Processing**
- **Current:** Webhook triggers account lookup by TrueLayer ID
  - `database.get_account_by_truelayer_id()` - linear search
  - Location: `truelayer_sync.py:635`
- **Alternative:** Webhook payload should include database account ID
- **Impact:** Single query vs linear search, minor (< 50ms)

#### C. **No Index on Enrichment Cache**
- **Current:** Cache lookups by description + direction
  - Could be slow with large cache (100K+ entries)
  - No index on (description_hash, direction)
- **Alternative:** Add composite index
- **Impact:** Cache misses improve from O(n) to O(log n)

---

## 4. Optimization Roadmap

### Priority 1: High Impact (Do First)

#### 1.1 Enable Automatic Enrichment After TrueLayer Sync
```
Effort: Medium (4-6 hours)
Impact: High (improved user experience)
Complexity: Medium

Changes:
- Modify sync_all_accounts() to return list of newly synced transaction IDs
- Call enricher.enrich_transactions(imported_transaction_ids) after sync
- Return enrichment stats in sync response
- Add skip_enrichment parameter to sync endpoint (like Santander import)
```

**Benefit:** Users see properly categorized transactions immediately after sync

#### 1.2 Parallelize Account Syncing
```
Effort: Medium (6-8 hours)
Impact: High (3-5x faster for multi-account users)
Complexity: Medium (async/threading)

Changes:
- Use ThreadPoolExecutor or asyncio for concurrent account syncs
- Keep token refresh sequential (avoid race conditions)
- Limit concurrency to 3-5 threads to avoid API rate limiting
- Proper error handling per account (1 failed account doesn't break others)
```

**Benefit:** Multi-account users sync 3-5x faster

### Priority 2: Medium Impact (Do Next)

#### 2.1 Batch Deduplication Checks
```
Effort: Small (2-3 hours)
Impact: Medium (500-1000ms per sync)
Complexity: Low

Changes:
- Query all normalised_ids from batch at once
- Build set for O(1) lookup
- Replace per-transaction queries with set membership check
- Location: truelayer_sync.py:143-153
```

**Benefit:** Reduces DB query overhead by 100x

#### 2.2 Improve Incremental Sync Window
```
Effort: Small (2-3 hours)
Impact: Medium (15-20% fewer API calls)
Complexity: Low

Changes:
- Track per-account last_synced_at separately
- Remove the "+1 day buffer" (use exact timestamp)
- Ensure timezone consistency (all UTC)
- Add 1 minute buffer only (not 1 day)
```

**Benefit:** Fewer API calls, faster syncs

#### 2.3 Add Connection-Level Sync Status
```
Effort: Medium (4-6 hours)
Impact: Medium (better operational visibility)
Complexity: Medium

Changes:
- Add columns to bank_connections:
  - last_account_synced_at (most recent account)
  - next_sync_required (boolean)
- Track per-account sync status separately
- Implement /api/truelayer/sync/accounts endpoint
```

**Benefit:** Can resume failed syncs, implement per-account retry

### Priority 3: Lower Impact (Optimize Later)

#### 3.1 Webhook Payload Optimization
```
Effort: Small (1-2 hours)
Impact: Low (< 50ms)
Complexity: Low

Changes:
- Webhook payload should include both:
  - truelayer_account_id (from TrueLayer)
  - database_account_id (for direct lookup)
- Avoids lookup in webhook handler
```

#### 3.2 Add Database Indexes
```
Effort: Small (< 1 hour)
Impact: Low (but good for scale)
Complexity: Low

Add indexes:
- truelayer_transactions(normalised_provider_transaction_id) - UNIQUE (exists)
- enrichment_cache(description_hash, direction) - composite
- truelayer_accounts(connection_id, account_id) - composite
```

#### 3.3 Batch Size Tuning
```
Effort: Small (1-2 hours)
Impact: Low (10-15% improvement for Google/Ollama)
Complexity: Low

Changes:
- Test larger batch sizes (10, 25, 50) for each provider
- Document actual rate limits from testing
- Update provider_limits dictionary
```

---

## 5. Detailed Optimization Examples

### 5.1 Parallel Account Sync Implementation

```python
# BEFORE: Sequential
def sync_all_accounts(user_id: int) -> dict:
    for connection in connections:
        for account in accounts:
            result = sync_account_transactions(...)  # Waits for completion
            account_results.append(result)

# AFTER: Parallel
from concurrent.futures import ThreadPoolExecutor, as_completed

def sync_all_accounts(user_id: int) -> dict:
    account_tasks = []

    # Collect all account sync tasks
    with ThreadPoolExecutor(max_workers=3) as executor:
        for connection in connections:
            for account in accounts:
                task = executor.submit(
                    sync_account_transactions,
                    connection_id, account_id, db_account_id, access_token
                )
                account_tasks.append((account_id, task))

        # Wait for all tasks and collect results
        for account_id, task in account_tasks:
            try:
                result = task.result(timeout=60)
                account_results.append(result)
            except Exception as e:
                account_results.append({'error': str(e)})

    return aggregate_results(account_results)
```

**Expected Performance:**
- Before: 5 seconds for 5 accounts
- After: ~1-1.5 seconds for 5 accounts (3-4x faster)

### 5.2 Automatic Enrichment After Sync

```python
# In sync_truelayer_transactions endpoint (app.py:1523)

result = sync_all_accounts(user_id)

# NEW: Auto-enrich newly synced transactions
if result.get('newly_synced_transaction_ids'):
    try:
        enricher = get_enricher()
        if enricher:
            enrich_stats = enricher.enrich_transactions(
                transaction_ids=result['newly_synced_transaction_ids'],
                direction='out',  # Most TrueLayer syncs are expenses
                force_refresh=False
            )
            result['enrichment_stats'] = enrich_stats
    except Exception as e:
        logger.error(f"Enrichment failed (non-fatal): {e}")

return jsonify(result)
```

**Expected Performance:**
- Enrichment adds 2-5 seconds to sync (depends on LLM provider)
- BUT: Users get properly categorized transactions immediately

### 5.3 Batch Deduplication

```python
# BEFORE: Per-transaction queries
for idx, txn in enumerate(transactions):
    normalised_id = txn.get('normalised_provider_id')
    existing = database.get_truelayer_transaction_by_id(normalised_id)  # 1 query per txn
    if existing:
        duplicate_count += 1
        continue

# AFTER: Batch query
normalised_ids = [t.get('normalised_provider_id') for t in transactions]
existing_ids = database.get_existing_transaction_ids_batch(normalised_ids)  # 1 query
existing_ids_set = set(existing_ids)  # O(1) lookup

for idx, txn in enumerate(transactions):
    normalised_id = txn.get('normalised_provider_id')
    if normalised_id in existing_ids_set:  # O(1) check
        duplicate_count += 1
        continue
```

**Expected Performance:**
- Before: 100 queries for 100 transactions
- After: 1 query for 100 transactions
- Savings: ~500-1000ms per sync

---

## 6. Operational Insights

### 6.1 Current Flow Issues

**Issue:** TrueLayer transactions remain uncategorized
- Transactions synced with `category='Other'`
- Enrichment only runs for Santander imports
- No scheduled enrichment for TrueLayer transactions
- Users see inconsistent UX

**Resolution:** Implement auto-enrichment as part of sync workflow (Priority 1.1)

### 6.2 Token Management

**Current:** Working correctly
- Tokens properly encrypted (Fernet)
- Auto-refresh within 5-minute buffer
- Handles both string and datetime formats
- Good error handling for parse failures

**Potential Improvement:** Pre-compute token expiry, refresh in background task

### 6.3 Webhook Processing

**Current:** Working but could be optimized
- Stores webhook events for audit
- Processes `transactions_available` events
- Stores balance snapshots

**Improvements:**
- Include database account ID in webhook payload
- Implement per-account sync status tracking
- Add webhook signature validation (currently not validated)

### 6.4 Error Handling

**Current:** Good at sync level
- Per-transaction errors don't fail whole sync
- Per-account errors don't fail whole connection
- Comprehensive logging with emoji indicators

**Gaps:**
- No retry queue for failed transactions
- Enrichment failures just logged, not queued
- No way to retry specific failed accounts

---

## 7. Monitoring & Metrics

### Current Tracking

✓ Synced transaction count
✓ Duplicate count
✓ Error count
✓ Last sync timestamp
✓ Token expiration

### Recommended Additions

- **Per-account sync duration** (identify slow accounts)
- **API call count per sync** (detect inefficiencies)
- **Enrichment success rate** (identify problem descriptions)
- **Cache hit rate** (measure enrichment efficiency)
- **Token refresh frequency** (validate 5-min buffer logic)
- **Webhook processing latency** (vs manual sync)
- **Database query count per sync** (identify N+1 queries)

---

## 8. Security Considerations

### Current State

✓ Tokens encrypted with Fernet
✓ PKCE flow for OAuth
✓ State parameter validation
✓ Token expiry tracking

### Recommendations

- Webhook signature validation (HMAC-SHA256)
- Rate limiting on sync endpoint
- Per-user sync rate limits (prevent abuse)
- Audit logging for token refresh
- Encryption key rotation strategy

---

## 9. Summary of Optimization Opportunities

| Priority | Feature | Effort | Impact | Status |
|----------|---------|--------|--------|--------|
| 1 | Auto-enrich after sync | Medium | High | Not Started |
| 1 | Parallel account sync | Medium | High | Not Started |
| 2 | Batch deduplication | Small | Medium | Not Started |
| 2 | Incremental sync window | Small | Medium | Not Started |
| 2 | Connection sync status | Medium | Medium | Not Started |
| 3 | Webhook optimization | Small | Low | Not Started |
| 3 | Database indexing | Small | Low | Not Started |
| 3 | Batch size tuning | Small | Low | Not Started |

**Estimated Total Impact if all implemented:**
- **Performance:** 3-5x faster syncs for multi-account users
- **UX:** Consistent categorization immediately after sync
- **Reliability:** Better error handling and recovery
- **Scalability:** Can handle 10-50 accounts per user efficiently

---

## 10. Related Documentation

- `/mnt/c/dev/spending/.claude/docs/architecture/TRUELAYER_INTEGRATION.md` - Core integration details
- `/mnt/c/dev/spending/.claude/docs/database/DATABASE_SCHEMA.md` - Database schema reference
- `/mnt/c/dev/spending/backend/mcp/truelayer_sync.py` - Sync implementation
- `/mnt/c/dev/spending/backend/mcp/llm_enricher.py` - Enrichment implementation
- `/mnt/c/dev/spending/backend/app.py` - API endpoints (lines 1340-1854)

