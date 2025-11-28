# TrueLayer Integration - Component Architecture & Dependencies

**Date:** 2025-11-28
**Purpose:** Visual reference for system components and their interactions

---

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React/TypeScript)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │ TrueLayerIntegration │  │ TrueLayerCallback    │  │ BankAccountDetails
│  │      .tsx            │  │ Handler.tsx          │  │      .tsx        │  │
│  │                      │  │                      │  │                  │  │
│  │ - Connect button     │  │ - OAuth callback     │  │ - Account list   │  │
│  │ - Account list       │  │ - State validation   │  │ - Card list      │  │
│  │ - Sync trigger       │  │ - PKCE validation    │  │ - Sync status    │  │
│  │ - Disconnect         │  │ - Success animation  │  │                  │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                         HTTP API (REST/JSON)
                                     │
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND API LAYER (Flask)                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ Routes: app.py:1340-1854                                            │  │
│  ├─────────────────────────────────────────────────────────────────────┤  │
│  │                                                                      │  │
│  │  GET  /api/truelayer/authorize                                      │  │
│  │  ├─→ imports truelayer_auth.get_authorization_url()               │  │
│  │  └─→ Response: {auth_url, state, code_verifier}                   │  │
│  │                                                                      │  │
│  │  GET  /api/truelayer/callback                                       │  │
│  │  ├─→ imports exchange_code_for_token()                             │  │
│  │  ├─→ imports save_bank_connection()                                │  │
│  │  ├─→ imports discover_and_save_accounts()                          │  │
│  │  └─→ Redirect: /auth/callback?status=authorized                   │  │
│  │                                                                      │  │
│  │  GET  /api/truelayer/accounts                                       │  │
│  │  ├─→ database.get_user_connections()                               │  │
│  │  ├─→ database.get_connection_accounts()                            │  │
│  │  └─→ Response: {connections[], sync_status[]}                      │  │
│  │                                                                      │  │
│  │  POST /api/truelayer/sync                                           │  │
│  │  ├─→ imports sync_all_accounts()                                   │  │
│  │  ├─→ [NEW] Call enricher.enrich_transactions()                    │  │
│  │  └─→ Response: {status, summary, enrichment_stats}                │  │
│  │                                                                      │  │
│  │  POST /api/truelayer/disconnect                                     │  │
│  │  ├─→ database.update_connection_status()                           │  │
│  │  └─→ Response: {status}                                            │  │
│  │                                                                      │  │
│  │  POST /api/truelayer/webhook                                        │  │
│  │  ├─→ imports handle_webhook_event()                                │  │
│  │  └─→ Response: {event_id, status}                                  │  │
│  │                                                                      │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
          ┌──────────────────────────┼──────────────────────────┐
          │                          │                          │
          ▼                          ▼                          ▼
   ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
   │ TrueLayer Auth  │       │ TrueLayer Sync  │       │  LLM Enricher   │
   │ (truelayer_     │       │ (truelayer_     │       │ (llm_enricher.  │
   │  auth.py)       │       │  sync.py)       │       │  py)            │
   └─────────────────┘       └─────────────────┘       └─────────────────┘
```

---

## Component Details

### 1. Authentication Component (truelayer_auth.py)

```
┌────────────────────────────────────────────────────────────────┐
│ TrueLayer Auth Module: mcp/truelayer_auth.py                   │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Functions:                                                      │
│ ├─ get_authorization_url(user_id)                              │
│ │  ├─ Generate PKCE challenge & verifier                       │
│ │  ├─ Generate state token                                     │
│ │  └─ Build OAuth URL                                          │
│ │                                                               │
│ ├─ exchange_code_for_token(code, code_verifier)               │
│ │  ├─ Call TrueLayer token endpoint                            │
│ │  ├─ Validate code & verifier                                 │
│ │  └─ Return {access_token, refresh_token, expires_at}        │
│ │                                                               │
│ ├─ refresh_access_token(refresh_token)                         │
│ │  ├─ Call TrueLayer refresh endpoint                          │
│ │  └─ Return new tokens                                        │
│ │                                                               │
│ ├─ save_bank_connection(user_id, token_data)                  │
│ │  ├─ Encrypt tokens with Fernet                               │
│ │  ├─ Store in bank_connections table                          │
│ │  └─ Return {connection_id, ...}                              │
│ │                                                               │
│ ├─ discover_and_save_accounts(connection_id, access_token)    │
│ │  ├─ Call client.get_accounts()                               │
│ │  ├─ Save each to truelayer_accounts table                    │
│ │  └─ Return {accounts_discovered, accounts_saved}             │
│ │                                                               │
│ ├─ encrypt_token(token) / decrypt_token(encrypted)             │
│ │  └─ Use Fernet symmetric encryption                          │
│ │                                                               │
│ └─ validate_authorization_state(state)                         │
│    └─ CSRF protection check                                    │
│                                                                 │
│ Dependencies:                                                   │
│ └─ database_postgres.py (store/retrieve connection state)      │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 2. Client Component (truelayer_client.py)

```
┌────────────────────────────────────────────────────────────────┐
│ TrueLayer Client: mcp/truelayer_client.py                      │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Class: TrueLayerClient(access_token)                            │
│                                                                 │
│ Account Methods:                                                │
│ ├─ get_accounts() → [{id, type, display_name, currency}]      │
│ ├─ get_account(account_id) → {account_details}                │
│ └─ get_account_balance(account_id) → {balance}                │
│                                                                 │
│ Transaction Methods:                                            │
│ ├─ get_transactions(account_id, from_date, to_date)            │
│ ├─ get_pending_transactions() → [pending_txns]                │
│ └─ fetch_all_transactions(account_id, days=90)                 │
│    ├─ Iterate through date ranges                              │
│    ├─ Call get_transactions() for each range                   │
│    ├─ Normalize each transaction                               │
│    └─ Return [{normalized_txn}, ...]                           │
│                                                                 │
│ Card Methods:                                                   │
│ ├─ get_cards() → [{id, type, display_name}]                   │
│ ├─ get_card_transactions(card_id) → [txns]                    │
│ └─ fetch_all_card_transactions(card_id, days=90)              │
│                                                                 │
│ Normalization:                                                  │
│ └─ normalize_transaction(raw_txn)                              │
│    ├─ Extract standard fields                                   │
│    ├─ Handle running_balance (extract from dict)               │
│    ├─ Create normalised_provider_id (dedup key)               │
│    └─ Return {date, description, amount, ...}                 │
│                                                                 │
│ Dependencies:                                                   │
│ └─ requests library (HTTP calls to TrueLayer API)             │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 3. Sync Component (truelayer_sync.py)

```
┌────────────────────────────────────────────────────────────────┐
│ TrueLayer Sync: mcp/truelayer_sync.py                          │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Main Functions:                                                 │
│                                                                 │
│ sync_all_accounts(user_id)                                     │
│ ├─ Get all connections for user                                │
│ ├─ For each connection:                                        │
│ │  ├─ refresh_token_if_needed()                                │
│ │  ├─ Get all accounts for connection                          │
│ │  └─ Call sync_account_transactions() for each                │
│ │      [SEQUENTIAL - opportunity for parallelization]          │
│ ├─ Aggregate results                                           │
│ └─ Return {total_accounts, total_synced, accounts[]}           │
│                                                                 │
│ sync_account_transactions(connection_id, account_id, ...)      │
│ ├─ Calculate sync window (incremental or full)                 │
│ ├─ Decrypt access token                                        │
│ ├─ Fetch transactions from TrueLayer API                       │
│ ├─ For each transaction:                                       │
│ │  ├─ Check deduplication (INEFFICIENT - per-txn query)       │
│ │  ├─ Normalize transaction                                    │
│ │  └─ Insert into truelayer_transactions                       │
│ ├─ Update account last_synced_at                               │
│ └─ Return {synced, duplicates, errors}                         │
│                                                                 │
│ sync_card_transactions(connection_id, card_id, ...)            │
│ └─ Similar to sync_account_transactions()                      │
│                                                                 │
│ sync_all_cards(user_id)                                        │
│ └─ Similar to sync_all_accounts()                              │
│                                                                 │
│ Utility Functions:                                              │
│ ├─ identify_merchant(description, merchant_from_api)           │
│ ├─ identify_transaction_merchant(txn_dict)                     │
│ ├─ refresh_token_if_needed(connection_id, connection)          │
│ └─ handle_webhook_event(event_payload)                         │
│    ├─ Store event for audit trail                              │
│    ├─ Trigger sync for affected account                        │
│    └─ Update balance if balance_updated event                  │
│                                                                 │
│ Dependencies:                                                   │
│ ├─ truelayer_auth.py (decrypt_token, refresh_access_token)    │
│ ├─ truelayer_client.py (TrueLayerClient)                       │
│ └─ database_postgres.py (all DB operations)                    │
│                                                                 │
│ [ENHANCEMENT] To add enrichment auto-trigger:                  │
│ └─ After sync_all_accounts(): Call llm_enricher.enrich_txns()│
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 4. Enrichment Component (llm_enricher.py)

```
┌────────────────────────────────────────────────────────────────┐
│ LLM Enricher: mcp/llm_enricher.py                              │
├────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Class: LLMEnricher(config)                                      │
│                                                                 │
│ Main Methods:                                                   │
│ ├─ enrich_transactions(transaction_ids, direction, force)      │
│ │  ├─ Query unenriched transactions                            │
│ │  ├─ Check enrichment_cache for hits                          │
│ │  ├─ Separate already_enriched, cached, and new               │
│ │  ├─ Calculate dynamic batch_size                             │
│ │  ├─ Process batches:                                         │
│ │  │  ├─ Build batch_data with descriptions                    │
│ │  │  ├─ Call LLM provider                                     │
│ │  │  ├─ Cache results (if enabled)                            │
│ │  │  └─ Map back to transactions                              │
│ │  ├─ Update transactions with enrichment                      │
│ │  └─ Return EnrichmentStats                                   │
│ │                                                               │
│ ├─ validate_configuration() → bool                              │
│ └─ get_status() → {provider, model, cache_enabled}             │
│                                                                 │
│ Helper Methods:                                                 │
│ └─ _calculate_batch_size(num_txns) → batch_size                │
│    └─ Adjust based on provider limits                          │
│                                                                 │
│ Provider Configuration:                                         │
│ ├─ Anthropic: batch_size=20, cost-based                        │
│ ├─ OpenAI: batch_size=15, cost-based                           │
│ ├─ Google: batch_size=5, free tier limited                     │
│ ├─ Deepseek: batch_size=25, cost-based                         │
│ └─ Ollama: batch_size=5, local inference                       │
│                                                                 │
│ Dependencies:                                                   │
│ ├─ llm_providers/*.py (provider implementations)               │
│ ├─ database_postgres.py (get/cache enrichments)                │
│ └─ config/llm_config.py (configuration loading)                │
│                                                                 │
│ [ENHANCEMENT] Called after TrueLayer sync:                     │
│ └─ enrich_transactions(transaction_ids=newly_synced_ids)       │
│                                                                 │
└────────────────────────────────────────────────────────────────┘
```

### 5. LLM Provider Implementations

```
┌─────────────────────────────────────────────────────┐
│ LLM Provider Base: mcp/llm_providers/base_provider.py
├─────────────────────────────────────────────────────┤
│                                                     │
│ Class: BaseLLMProvider                              │
│ └─ abstract enrich_transactions(batch_data)         │
│                                                     │
└─────────────────────────────────────────────────────┘
     △            △            △            △
     │            │            │            │
┌────┴──────┐ ┌──┴──────────┐ ┌──┴──────┐ ┌──┴──────┐
│ Anthropic │ │ OpenAI      │ │ Google  │ │Deepseek │ ... Ollama
└───────────┘ └─────────────┘ └─────────┘ └─────────┘
```

---

## Database Schema Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    PostgreSQL Database                        │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│ OAuth & Connection Management:                               │
│ ┌─────────────────────────────────────────┐                 │
│ │ bank_connections                        │                 │
│ ├─────────────────────────────────────────┤                 │
│ │ id (PK)                                 │                 │
│ │ user_id (FK users)                      │                 │
│ │ provider_id ('truelayer')                │                 │
│ │ access_token (encrypted)                │                 │
│ │ refresh_token (encrypted)               │                 │
│ │ token_expires_at                        │                 │
│ │ connection_status                       │                 │
│ │ last_synced_at ← UPDATED BY SYNC        │                 │
│ └─────────────────────────────────────────┘                 │
│                    │                                          │
│                    │ 1..N                                     │
│                    ▼                                          │
│ ┌─────────────────────────────────────────┐                 │
│ │ truelayer_accounts                      │                 │
│ ├─────────────────────────────────────────┤                 │
│ │ id (PK)                                 │                 │
│ │ connection_id (FK bank_connections)     │                 │
│ │ account_id (TrueLayer ID)               │                 │
│ │ account_type                            │                 │
│ │ display_name                            │                 │
│ │ currency                                │                 │
│ │ last_synced_at ← UPDATED BY SYNC        │                 │
│ └─────────────────────────────────────────┘                 │
│                    │                                          │
│                    │ 1..N                                     │
│                    ▼                                          │
│ ┌──────────────────────────────────────────┐                │
│ │ truelayer_transactions                   │                │
│ ├──────────────────────────────────────────┤                │
│ │ id (PK)                                  │                │
│ │ account_id (FK truelayer_accounts)       │                │
│ │ transaction_id                           │                │
│ │ normalised_provider_transaction_id (UNI) │← DEDUP KEY     │
│ │ timestamp                                │                │
│ │ description                              │                │
│ │ amount                                   │                │
│ │ transaction_type (DEBIT|CREDIT)          │                │
│ │ transaction_category ('Other' initially) │← SET BY ENRICHER
│ │ merchant_name                            │                │
│ │ running_balance                          │                │
│ │ metadata (JSONB)                         │                │
│ └──────────────────────────────────────────┘                │
│                    │                                          │
│                    │ 1..1                                     │
│                    ▼                                          │
│ ┌──────────────────────────────────────────┐                │
│ │ transaction_enrichments                  │                │
│ ├──────────────────────────────────────────┤                │
│ │ id (PK)                                  │                │
│ │ transaction_id (FK transactions)         │                │
│ │ primary_category                         │                │
│ │ subcategory                              │                │
│ │ merchant_clean_name                      │                │
│ │ merchant_type                            │                │
│ │ essential_discretionary                  │                │
│ │ confidence_score                         │                │
│ │ llm_provider                             │                │
│ │ llm_model                                │                │
│ │ enrichment_source ('llm' or 'cache')     │                │
│ └──────────────────────────────────────────┘                │
│                                                               │
│ Card Management (Similar structure):                          │
│ ├─ truelayer_cards                                            │
│ └─ truelayer_card_transactions                               │
│                                                               │
│ Caching & Optimization:                                      │
│ ├─ enrichment_cache (description → enrichment mapping)      │
│ └─ truelayer_webhook_events (audit trail)                    │
│                                                               │
│ Balance History:                                              │
│ └─ truelayer_balances (historical snapshots)                │
│                                                               │
└──────────────────────────────────────────────────────────────┘
```

---

## Data Flow: From TrueLayer API to Database

```
TrueLayer API
    │
    ├─ /data/accounts ────────────────────────┐
    │                                         │
    ├─ /data/accounts/{account}/transactions │
    │  Response: [{transaction_json}, ...]   │
    │                                         │
    └─ /data/cards/{card}/transactions ──────┘
            │
            │ HTTP Response (normalized format)
            ▼
    ┌─────────────────────────────────┐
    │ truelayer_client.py             │
    │ normalize_transaction()          │
    ├─────────────────────────────────┤
    │ Input:  {raw_truelayer_json}    │
    │ Output: {                       │
    │   date,                         │
    │   description,                  │
    │   amount,                       │
    │   transaction_type,             │
    │   running_balance,              │
    │   merchant_name,                │
    │   normalised_provider_id,       │
    │   metadata,                     │
    │   ...                           │
    │ }                               │
    └─────────────────────────────────┘
            │
            │ Normalized transaction
            ▼
    ┌─────────────────────────────────┐
    │ truelayer_sync.py               │
    │ - Deduplication check           │
    │ - Merchant identification       │
    │ - Set category='Other'          │
    └─────────────────────────────────┘
            │
            │ Prepared transaction
            ▼
    ┌──────────────────────────────────────┐
    │ database_postgres.py                 │
    │ insert_truelayer_transaction()       │
    └──────────────────────────────────────┘
            │
            │ SQL INSERT
            ▼
    ┌──────────────────────────────────────┐
    │ truelayer_transactions table         │
    │ (Transaction stored with category=  │
    │  'Other', awaiting enrichment)      │
    └──────────────────────────────────────┘
            │
            │ [ENHANCEMENT] Auto-enrich
            ▼
    ┌──────────────────────────────────────┐
    │ llm_enricher.py                      │
    │ enrich_transactions()                │
    └──────────────────────────────────────┘
            │
            │ Check cache / Call LLM API
            ▼
    ┌──────────────────────────────────────┐
    │ LLM Provider                         │
    │ (Anthropic, OpenAI, Google, etc.)   │
    └──────────────────────────────────────┘
            │
            │ Enrichment: {category, confidence, ...}
            ▼
    ┌──────────────────────────────────────┐
    │ database_postgres.py                 │
    │ update_transaction_with_enrichment()│
    └──────────────────────────────────────┘
            │
            │ SQL UPDATE + INSERT to enrichments table
            ▼
    ┌──────────────────────────────────────┐
    │ truelayer_transactions                │
    │ (category updated to proper value)  │
    │                                      │
    │ transaction_enrichments              │
    │ (enrichment details stored)          │
    └──────────────────────────────────────┘
```

---

## API Endpoint Dependency Map

```
┌──────────────────────────────────────────────────────────────┐
│ Frontend Initiates OAuth Flow                                │
└──────────────────────────────────────────────────────────────┘
    │
    ├─ 1. GET /api/truelayer/authorize
    │  ├─ truelayer_auth.get_authorization_url()
    │  └─ Response: {auth_url, state, code_verifier}
    │
    ├─ 2. Redirect to TrueLayer OAuth (external)
    │
    └─ 3. GET /api/truelayer/callback?code=...&state=...
       ├─ truelayer_auth.exchange_code_for_token()
       ├─ truelayer_auth.save_bank_connection()
       ├─ truelayer_auth.discover_and_save_accounts()
       └─ Redirect: /auth/callback?status=authorized

┌──────────────────────────────────────────────────────────────┐
│ Frontend Views Accounts and Triggers Sync                    │
└──────────────────────────────────────────────────────────────┘
    │
    ├─ GET /api/truelayer/accounts
    │  ├─ database.get_user_connections()
    │  ├─ database.get_connection_accounts() [for each]
    │  └─ Response: {connections[], accounts[]}
    │
    └─ POST /api/truelayer/sync
       ├─ truelayer_sync.sync_all_accounts()
       │  ├─ [For each connection]:
       │  │  ├─ truelayer_sync.refresh_token_if_needed()
       │  │  └─ [For each account]:
       │  │     └─ truelayer_sync.sync_account_transactions()
       │  │        ├─ truelayer_client.fetch_all_transactions()
       │  │        ├─ truelayer_sync.identify_transaction_merchant()
       │  │        └─ database.insert_truelayer_transaction()
       │  │
       │  └─ Return: {synced_count, duplicates, errors}
       │
       ├─ [NEW] llm_enricher.enrich_transactions()
       │  ├─ database.get_enrichment_from_cache()
       │  ├─ llm_provider.enrich_transactions()
       │  ├─ database.cache_enrichment()
       │  └─ database.update_transaction_with_enrichment()
       │
       └─ Response: {status, summary, enrichment_stats}

┌──────────────────────────────────────────────────────────────┐
│ Webhook Processing (Automatic, from TrueLayer)               │
└──────────────────────────────────────────────────────────────┘
    │
    └─ POST /api/truelayer/webhook?signature=...
       ├─ database.insert_webhook_event()
       ├─ truelayer_sync.handle_webhook_event()
       │  ├─ IF transactions_available:
       │  │  ├─ truelayer_sync.sync_account_transactions()
       │  │  └─ [Could trigger enrichment here]
       │  │
       │  └─ IF balance_updated:
       │     └─ database.insert_balance_snapshot()
       │
       └─ database.mark_webhook_processed()
```

---

## Dependency Resolution Order

**For transaction to be ready for viewing:**

1. `bank_connections` - User must have authorized
2. `truelayer_accounts` - Discovered during callback
3. `truelayer_transactions` - Populated during sync
4. `transaction_enrichments` - Populated during enrichment (or manually)

**Dependencies can be checked with:**
```python
has_connections = database.get_user_connections(user_id)
has_accounts = database.get_connection_accounts(connection_id)
has_transactions = database.get_truelayer_transactions(account_id)
has_enrichments = database.get_transaction_enrichments(transaction_id)
```

---

## Critical Paths

### Path 1: Account Sync Latency
```
User clicks "Sync Now"
    │
    ├─ [SEQUENTIAL] For each account:
    │  ├─ API call to TrueLayer (network: 1-2 sec)
    │  ├─ Normalize transactions (CPU: 100-500ms)
    │  ├─ Dedup check per transaction (DB: 100-500ms) ← INEFFICIENCY
    │  └─ Insert to DB (DB: 500-1000ms)
    │
    ├─ Total for 5 accounts: 5-15 seconds
    │
    └─ [OPPORTUNITY] Parallelize account processing: 1-3 seconds
```

### Path 2: Enrichment Latency
```
Transactions stored in DB
    │
    ├─ [MISSING] No auto-trigger currently
    │
    ├─ Manual: User clicks "Enrich" (if button exists)
    │  OR Scheduled job runs
    │
    ├─ Load unenriched transactions
    │
    ├─ Check cache for each (100-200ms)
    │
    ├─ [BATCH] Send to LLM (1-2 sec per 20 txns)
    │
    └─ Update DB with enrichment (1-2 sec)
```

---

## Testing Checklist

- [ ] Single account sync
- [ ] Multiple accounts (3, 5, 10) - test parallelization
- [ ] Duplicate transaction handling
- [ ] Token refresh during sync
- [ ] Webhook event processing
- [ ] Enrichment cache hits/misses
- [ ] Error handling (network, API, DB)
- [ ] Concurrent operations (2 users syncing simultaneously)
- [ ] Large transaction sets (1000+ txns)
- [ ] Timezone handling (UTC consistency)

