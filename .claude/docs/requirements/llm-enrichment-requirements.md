# Feature Requirements: LLM Transaction Enrichment

**Status:** Approved for Implementation
**Author:** Requirements Development Agent
**Created:** 2025-11-29
**Last Updated:** 2025-11-29
**Approved By:** User (via requirements elicitation)

---

## 1. Overview

### 1.1 Summary

LLM Transaction Enrichment is an AI-powered feature that automatically enhances imported bank transactions with structured metadata including categories, subcategories, merchant names, purchase types, and confidence scores. The feature leverages multiple LLM providers (Anthropic Claude, OpenAI GPT, Google Gemini, Deepseek, Ollama local models) to analyze transaction descriptions and extract meaningful business intelligence. The core enrichment engine is already built and functional; this document specifies requirements to complete API integration, frontend UI, and user-facing controls.

### 1.2 Problem Statement

**Current State:**
Users import bank transactions via TrueLayer API or Santander Excel statements. These transactions arrive with minimal metadata—just a description, amount, and date. Without enrichment, users must:
- Manually categorize hundreds of transactions
- Extract merchant names from inconsistent descriptions
- Struggle to identify spending patterns
- Lack confidence in financial insights

**Desired State:**
Transactions are automatically enriched with:
- Primary category (e.g., "Groceries", "Transport")
- Subcategory (e.g., "Supermarkets", "Public Transport")
- Clean merchant name (e.g., "Tesco" from "TESCO STORES 1234")
- Essential vs. discretionary classification
- Confidence score (0.0-1.0) for quality assessment

**Why Now:**
The core enrichment engine (`llm_enricher.py`) is complete and tested. Database schema exists. CLI tool works end-to-end. Missing components are API endpoints, frontend UI, and user controls—achievable with 5-7 targeted development tasks.

### 1.3 Goals

1. **Enable Manual Enrichment Triggering**: Users can initiate enrichment from Settings page with cost preview and confirmation
2. **Enable Scheduled Background Enrichment**: Optionally enrich new transactions after TrueLayer import jobs complete
3. **Display Enrichment Data**: Show enrichment metadata in transaction list with visual indicators
4. **Cost Transparency**: Always display estimated API cost before enrichment runs; require user confirmation
5. **Failure Recovery**: Provide UI/API to retry failed enrichments with clear error reporting
6. **Performance**: Enrich 100 transactions in <30 seconds (batched API calls)
7. **Privacy**: All LLM API calls use only transaction descriptions (no sensitive account data)

### 1.4 Non-Goals (Out of Scope)

- **Editing Enrichment Data Manually**: Users cannot manually edit enrichment fields (category, subcategory, merchant name) through UI. Enrichment data is read-only and regenerated via LLM if needed.
- **Custom LLM Prompts**: Users cannot customize enrichment prompts or add custom categories. System uses predefined schema.
- **Historical Trend Analysis**: Advanced analytics (spending trends over time, anomaly detection) are separate features.
- **Rule-Based Enrichment**: Focus is LLM enrichment only; rule-based categorization (keyword matching) is a separate system.
- **Multi-User Enrichment**: This release assumes single-user operation. Multi-user support is future scope.

---

## 2. User Stories

### 2.1 Primary User Story

**As a** personal finance user importing bank transactions
**I want to** automatically enrich transactions with AI-powered categorization
**So that** I can gain instant insights into my spending without manual categorization

### 2.2 Additional User Stories

- **As a user**, I want to trigger enrichment from the Settings page, so that I can control when API costs are incurred.
- **As a user**, I want to see estimated API costs before enrichment runs, so that I can make informed decisions about spending money on LLM API calls.
- **As a user**, I want enrichment to automatically run after TrueLayer imports, so that new transactions are categorized without manual intervention.
- **As a user**, I want to see enrichment data in the transaction list (category, subcategory, merchant), so that I can quickly identify spending patterns.
- **As a user**, I want to visually distinguish enriched vs. unenriched transactions, so that I know which transactions have been processed.
- **As a user**, I want to retry failed enrichments, so that I can recover from temporary API errors without re-running the entire batch.
- **As a developer**, I want to use the existing `LLMEnricher` class, so that I don't duplicate code and benefit from batching, caching, and multi-provider support.

---

## 3. Functional Requirements

### 3.1 Required Behaviors

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-001 | System must provide a REST API endpoint to trigger enrichment manually for all unenriched transactions | Must Have |
| FR-002 | System must estimate and return API cost before running enrichment (dry-run mode) | Must Have |
| FR-003 | User must explicitly confirm cost before enrichment executes | Must Have |
| FR-004 | System must provide a REST API endpoint to check enrichment job status (running, completed, failed) | Must Have |
| FR-005 | System must provide a REST API endpoint to retrieve enrichment statistics (total enriched, cache hits, failed count) | Must Have |
| FR-006 | Frontend Settings page must include "Enrich Transactions" button that calls cost estimation API | Must Have |
| FR-007 | Frontend must display cost preview modal with estimated tokens, cost, and transaction count before enrichment | Must Have |
| FR-008 | Frontend transaction list must display enrichment data: primary category, subcategory, merchant clean name | Must Have |
| FR-009 | Frontend transaction list must visually indicate which transactions have been enriched (badge, icon, or column) | Must Have |
| FR-010 | System must provide a REST API endpoint to list failed enrichments with error messages | Must Have |
| FR-011 | Frontend Settings page must include "Retry Failed Enrichments" button to re-run failed transactions | Should Have |
| FR-012 | System must support scheduled enrichment after TrueLayer import jobs complete (async background job) | Should Have |
| FR-013 | User can enable/disable auto-enrichment after imports via Settings toggle | Should Have |
| FR-014 | System must return enrichment progress (X of Y transactions processed) during long-running jobs | Nice to Have |

### 3.2 Input/Output Specifications

**API Inputs:**

- **POST /api/enrichment/estimate**: No request body required. Returns estimated cost for enriching all unenriched transactions.
  ```json
  {}
  ```

- **POST /api/enrichment/trigger**: Triggers enrichment for unenriched transactions.
  ```json
  {
    "confirm_cost": true,
    "transaction_ids": [123, 456],  // Optional: specific IDs to enrich
    "force_refresh": false  // Optional: bypass cache
  }
  ```

- **GET /api/enrichment/status/<job_id>**: Returns status of enrichment job.

- **GET /api/enrichment/stats**: Returns enrichment statistics.

- **GET /api/enrichment/failed**: Returns list of failed enrichments.

- **POST /api/enrichment/retry**: Retries failed enrichments.
  ```json
  {
    "transaction_ids": [789, 101]  // Optional: specific failed IDs
  }
  ```

**API Outputs:**

- **POST /api/enrichment/estimate** Response:
  ```json
  {
    "total_transactions": 150,
    "estimated_tokens": 30000,
    "estimated_cost": 0.0045,
    "currency": "USD",
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022"
  }
  ```

- **POST /api/enrichment/trigger** Response:
  ```json
  {
    "job_id": "enrich-20251129-001",
    "status": "running",
    "total_transactions": 150,
    "message": "Enrichment job started"
  }
  ```

- **GET /api/enrichment/status/<job_id>** Response:
  ```json
  {
    "job_id": "enrich-20251129-001",
    "status": "completed",
    "total_transactions": 150,
    "successful_enrichments": 148,
    "failed_enrichments": 2,
    "cached_hits": 75,
    "api_calls_made": 8,
    "total_tokens_used": 28400,
    "total_cost": 0.00426,
    "started_at": "2025-11-29T10:30:00Z",
    "completed_at": "2025-11-29T10:31:15Z"
  }
  ```

- **GET /api/enrichment/stats** Response:
  ```json
  {
    "total_transactions": 500,
    "enriched_count": 475,
    "unenriched_count": 25,
    "enrichment_percentage": 95.0,
    "cache_size": 320,
    "total_api_cost": 0.12,
    "total_tokens_used": 80000
  }
  ```

- **GET /api/enrichment/failed** Response:
  ```json
  {
    "failed_enrichments": [
      {
        "transaction_id": 789,
        "description": "UNKNOWN MERCHANT XYZ",
        "error_type": "api_timeout",
        "error_message": "Request timed out after 30s",
        "failed_at": "2025-11-29T10:30:45Z",
        "retry_count": 2
      }
    ]
  }
  ```

- **POST /api/enrichment/retry** Response:
  ```json
  {
    "job_id": "retry-20251129-002",
    "status": "running",
    "total_transactions": 2,
    "message": "Retry job started"
  }
  ```

**Frontend Inputs:**

- User clicks "Enrich Transactions" button in Settings
- User confirms cost in modal dialog (Yes/No)
- User clicks "Retry Failed" button in Settings

**Frontend Outputs:**

- Cost preview modal with estimated cost and transaction count
- Progress indicator during enrichment (spinner + "Enriching X of Y transactions...")
- Success toast notification: "✓ Enriched 148 of 150 transactions ($0.00426)"
- Error toast notification: "✗ Enrichment failed: API timeout"
- Transaction list displays enrichment data in columns: Category, Subcategory, Merchant

### 3.3 Business Rules

1. **Cost Confirmation Required**: Enrichment API endpoint MUST reject requests without `confirm_cost: true` in request body. This prevents accidental API charges.

2. **Deduplication via Cache**: If a transaction description has been enriched before (cached), skip LLM API call and use cached result. Cache key: `(description, direction)`.

3. **Enrichment Direction**: Transactions with negative amounts are `direction='out'` (expenses). Positive amounts are `direction='in'` (income). This affects LLM categorization logic.

4. **Confidence Threshold**: Enrichment results with `confidence_score < 0.5` should be flagged as "Low Confidence" in UI. User may want to review these.

5. **Provider Selection**: System uses LLM provider configured in `.env` file (`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`). If not configured, enrichment is disabled and UI displays "Not Configured" message.

6. **Batch Size Limits**: Enrichment processes transactions in batches (default: 10 transactions per API call). Batch size is configurable per provider to respect rate limits.

7. **Token Estimation**: For cost estimation, assume average 200 tokens per transaction (input + output). Multiply by provider's cost per token.

8. **Retry Logic**: Failed enrichments are logged in `llm_enrichment_failures` table with `retry_count`. Maximum 3 automatic retries before marking as permanently failed.

9. **Data Privacy**: Only transaction description, date, and amount are sent to LLM APIs. Never send account numbers, sort codes, user names, or other PII.

10. **Enrichment Source Tracking**: Database stores `enrichment_source` field: `'llm'` for fresh API calls, `'cache'` for cached results. This enables analytics on cache hit rate.

---

## 4. Technical Requirements

### 4.1 Database Changes

**No schema changes required.** All enrichment tables already exist:

**Existing Tables (No Modifications):**

| Table | Purpose | Status |
|-------|---------|--------|
| `transaction_enrichments` | Stores enrichment results per transaction | ✓ Exists |
| `llm_enrichment_cache` | Caches enrichment by description to avoid duplicate API calls | ✓ Exists |
| `llm_enrichment_failures` | Logs failed enrichments with error messages for retry | ✓ Exists |
| `truelayer_enrichment_jobs` | Job tracking for background enrichment (linked to import jobs) | ✓ Exists |

**Schema Reference:**

```sql
-- transaction_enrichments table (already exists)
CREATE TABLE transaction_enrichments (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER NOT NULL,
    primary_category VARCHAR(255),
    subcategory VARCHAR(255),
    merchant_clean_name VARCHAR(255),
    merchant_type VARCHAR(255),
    essential_discretionary VARCHAR(50),
    payment_method VARCHAR(255),
    payment_method_subtype VARCHAR(255),
    purchase_date DATE,
    confidence_score NUMERIC(3,2),
    raw_response TEXT,
    llm_provider VARCHAR(50),
    llm_model VARCHAR(255),
    enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
);

-- llm_enrichment_cache table (already exists)
CREATE TABLE llm_enrichment_cache (
    id SERIAL PRIMARY KEY,
    transaction_description TEXT NOT NULL,
    transaction_direction VARCHAR(10),
    enrichment_data TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(transaction_description, transaction_direction)
);

-- llm_enrichment_failures table (already exists)
CREATE TABLE llm_enrichment_failures (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER,
    error_message TEXT,
    failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE
);

-- truelayer_enrichment_jobs table (already exists)
CREATE TABLE truelayer_enrichment_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    import_job_id INTEGER REFERENCES truelayer_import_jobs(id),
    job_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    transaction_ids INTEGER[] DEFAULT ARRAY[]::INTEGER[],
    total_transactions INTEGER DEFAULT 0,
    successful_enrichments INTEGER DEFAULT 0,
    failed_enrichments INTEGER DEFAULT 0,
    cached_hits INTEGER DEFAULT 0,
    api_calls_made INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    total_cost NUMERIC(10,6) DEFAULT 0.0,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Database Functions Required (check existence, implement if missing):**

- `database.is_transaction_enriched(transaction_id)` → Returns True if enrichment exists ✓ Exists
- `database.get_enrichment_from_cache(description, direction)` → Returns cached enrichment or None ✓ Exists
- `database.cache_enrichment(description, direction, enrichment, provider, model)` → Stores cache entry ✓ Exists
- `database.update_transaction_with_enrichment(transaction_id, enrichment, enrichment_source)` → Saves enrichment to DB ✓ Exists
- `database.log_enrichment_failure(transaction_id, description, error_type, error_message, provider)` → Logs failure ✓ Exists

### 4.2 API Changes

**Existing Endpoints (Already Implemented):**

| Method | Endpoint | Purpose | Status |
|--------|----------|---------|--------|
| GET | `/api/enrichment/config` | Returns LLM provider configuration status | ✓ Complete |
| GET | `/api/enrichment/cache/stats` | Returns cache statistics | ✓ Complete |
| GET | `/api/enrichment/failed` | Returns list of failed enrichments | ✓ Complete |

**New Endpoints Required:**

| Method | Endpoint | Purpose | Priority |
|--------|----------|---------|----------|
| POST | `/api/enrichment/estimate` | Estimate cost for enriching unenriched transactions | Must Have |
| POST | `/api/enrichment/trigger` | Start enrichment job | Must Have |
| GET | `/api/enrichment/status/<job_id>` | Get enrichment job status | Must Have |
| GET | `/api/enrichment/stats` | Get enrichment statistics (total, enriched, unenriched) | Must Have |
| POST | `/api/enrichment/retry` | Retry failed enrichments | Should Have |
| GET | `/api/transactions` (modify) | Include enrichment data in response | Must Have |

**Detailed API Specifications:**

#### POST /api/enrichment/estimate

**Purpose:** Calculate estimated cost and token usage for enriching all unenriched transactions.

**Request:**
```json
{
  "transaction_ids": [123, 456],  // Optional: estimate specific IDs
  "force_refresh": false  // Optional: include already-enriched if true
}
```

**Response (200 OK):**
```json
{
  "total_transactions": 150,
  "already_enriched": 50,
  "to_be_enriched": 100,
  "cached_available": 30,
  "requires_api_call": 70,
  "estimated_tokens": 14000,
  "estimated_cost": 0.0021,
  "currency": "USD",
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "cost_per_1k_tokens": 0.003
}
```

**Response (503 Service Unavailable):**
```json
{
  "configured": false,
  "error": "LLM enrichment not configured. Set LLM_PROVIDER and LLM_API_KEY environment variables."
}
```

**Implementation Notes:**
- Query all transactions via `database.get_all_transactions()`
- Filter out already enriched (unless `force_refresh=true`)
- Check cache hits via `database.get_enrichment_from_cache(description, direction)`
- Calculate: `(total_transactions - cached_available) * 200 tokens * cost_per_1k_tokens / 1000`
- Return estimate without executing enrichment

---

#### POST /api/enrichment/trigger

**Purpose:** Start an enrichment job to process unenriched transactions.

**Request:**
```json
{
  "confirm_cost": true,  // Required: must be true
  "transaction_ids": [123, 456],  // Optional: enrich specific IDs
  "force_refresh": false  // Optional: bypass cache and re-enrich
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "enrich-20251129-001",
  "status": "running",
  "total_transactions": 150,
  "message": "Enrichment job started",
  "started_at": "2025-11-29T10:30:00Z"
}
```

**Response (400 Bad Request):**
```json
{
  "error": "Cost confirmation required. Set confirm_cost=true to proceed."
}
```

**Response (503 Service Unavailable):**
```json
{
  "configured": false,
  "error": "LLM enrichment not configured."
}
```

**Implementation Notes:**
- Require `confirm_cost=true` in request body (prevent accidental charges)
- If `transaction_ids` provided, enrich only those IDs; otherwise enrich all unenriched
- Call `enricher.enrich_transactions(transaction_ids=..., direction='out', force_refresh=...)`
- Store job status in `truelayer_enrichment_jobs` table (or in-memory job store)
- Run enrichment asynchronously (use background thread or job queue)
- Return job ID for status polling

---

#### GET /api/enrichment/status/<job_id>

**Purpose:** Get status of an enrichment job by job ID.

**Response (200 OK - Running):**
```json
{
  "job_id": "enrich-20251129-001",
  "status": "running",
  "total_transactions": 150,
  "processed_so_far": 85,
  "progress_percentage": 56.7,
  "started_at": "2025-11-29T10:30:00Z"
}
```

**Response (200 OK - Completed):**
```json
{
  "job_id": "enrich-20251129-001",
  "status": "completed",
  "total_transactions": 150,
  "successful_enrichments": 148,
  "failed_enrichments": 2,
  "cached_hits": 75,
  "api_calls_made": 8,
  "total_tokens_used": 28400,
  "total_cost": 0.00426,
  "started_at": "2025-11-29T10:30:00Z",
  "completed_at": "2025-11-29T10:31:15Z"
}
```

**Response (404 Not Found):**
```json
{
  "error": "Job not found"
}
```

**Implementation Notes:**
- Query `truelayer_enrichment_jobs` table by job ID
- Return job status, progress, and results

---

#### GET /api/enrichment/stats

**Purpose:** Get overall enrichment statistics across all transactions.

**Response (200 OK):**
```json
{
  "total_transactions": 500,
  "enriched_count": 475,
  "unenriched_count": 25,
  "enrichment_percentage": 95.0,
  "cache_stats": {
    "total_cached": 320,
    "cache_size_bytes": 1048576
  },
  "cost_stats": {
    "total_api_cost": 0.12,
    "total_tokens_used": 80000,
    "total_api_calls": 45
  },
  "provider": "anthropic",
  "model": "claude-3-5-sonnet-20241022",
  "cache_enabled": true
}
```

**Implementation Notes:**
- Count total transactions via `database.get_all_transactions()`
- Count enriched via `database.is_transaction_enriched()` for each transaction
- Query cache stats from `llm_enrichment_cache` table
- Query cost stats from `truelayer_enrichment_jobs` table (sum of `total_cost`, `total_tokens_used`)

---

#### POST /api/enrichment/retry

**Purpose:** Retry failed enrichments.

**Request:**
```json
{
  "transaction_ids": [789, 101]  // Optional: specific failed IDs to retry
}
```

**Response (202 Accepted):**
```json
{
  "job_id": "retry-20251129-002",
  "status": "running",
  "total_transactions": 2,
  "message": "Retry job started"
}
```

**Implementation Notes:**
- If `transaction_ids` not provided, query all failed transactions from `llm_enrichment_failures` table
- Call `enricher.enrich_transactions(transaction_ids=...)` with `force_refresh=true`
- Clear failure records after successful enrichment

---

#### GET /api/transactions (Modify Existing)

**Current Behavior:** Returns combined transactions from `transactions` and `truelayer_transactions` tables.

**Required Change:** Include enrichment data for each transaction.

**Current Response:**
```json
{
  "transactions": [
    {
      "id": 123,
      "date": "2025-11-15",
      "description": "TESCO STORES 1234",
      "amount": -42.50,
      "category": "Other",
      "merchant": null
    }
  ]
}
```

**New Response:**
```json
{
  "transactions": [
    {
      "id": 123,
      "date": "2025-11-15",
      "description": "TESCO STORES 1234",
      "amount": -42.50,
      "category": "Other",
      "merchant": null,
      "enrichment": {
        "is_enriched": true,
        "primary_category": "Groceries",
        "subcategory": "Supermarkets",
        "merchant_clean_name": "Tesco",
        "merchant_type": "Retail",
        "essential_discretionary": "Essential",
        "confidence_score": 0.95,
        "enriched_at": "2025-11-29T10:30:15Z",
        "enrichment_source": "llm"
      }
    },
    {
      "id": 124,
      "date": "2025-11-16",
      "description": "AMAZON UK MARKETPLACE",
      "amount": -19.99,
      "category": "Other",
      "merchant": null,
      "enrichment": {
        "is_enriched": false
      }
    }
  ]
}
```

**Implementation Notes:**
- For each transaction in response, check if enrichment exists via `database.get_transaction_enrichment(transaction_id)`
- If exists, populate `enrichment` object with all fields
- If not exists, set `enrichment: { is_enriched: false }`

---

### 4.3 Frontend Changes

**New Pages:**
- None (use existing Settings page)

**Modified Pages:**

- [x] **Settings Page** (`/frontend/src/pages/Settings.tsx`)
  - Add "LLM Enrichment" section
  - Display enrichment configuration status (provider, model, cache enabled)
  - Add "Enrich Transactions" button
  - Add "Retry Failed Enrichments" button
  - Display enrichment statistics (total enriched, unenriched, cache hits, cost)

- [x] **Transaction List Page** (`/frontend/src/pages/Transactions.tsx`)
  - Add enrichment columns: Category, Subcategory, Merchant
  - Add visual indicator (badge or icon) showing which transactions are enriched
  - Add filter to show only enriched or unenriched transactions

**New Components:**

- [x] **EnrichmentCostModal** (`/frontend/src/components/EnrichmentCostModal.tsx`)
  - Purpose: Display cost estimate before enrichment runs
  - Inputs: Estimated cost, transaction count, provider, model
  - Outputs: User confirmation (Yes/No)
  - Design: Modal dialog with cost breakdown, "Confirm" and "Cancel" buttons

- [x] **EnrichmentStatusIndicator** (`/frontend/src/components/EnrichmentStatusIndicator.tsx`)
  - Purpose: Visual badge showing enrichment status
  - Inputs: `is_enriched` boolean, `confidence_score` number
  - Outputs: Badge/icon component
  - Design:
    - Green checkmark icon for enriched (confidence >= 0.7)
    - Yellow warning icon for low confidence (0.5 <= confidence < 0.7)
    - Gray dash icon for unenriched
    - Tooltip on hover showing confidence score and enriched_at timestamp

- [x] **EnrichmentProgressModal** (`/frontend/src/components/EnrichmentProgressModal.tsx`)
  - Purpose: Show real-time progress during enrichment
  - Inputs: Job ID, polling interval (default: 2 seconds)
  - Outputs: Progress bar, status message, cancel button
  - Design: Modal with progress bar, "Enriching X of Y transactions..." text, spinner

**Modified Components:**

- [x] **TransactionRow** (`/frontend/src/components/TransactionRow.tsx`)
  - Add enrichment data display (category, subcategory, merchant)
  - Add `<EnrichmentStatusIndicator />` component
  - Update styling to highlight enriched transactions (subtle background color)

### 4.4 Dependencies

**External Services:**
- LLM API Providers (already integrated):
  - Anthropic Claude API (via `anthropic` Python package)
  - OpenAI API (via `openai` Python package)
  - Google Gemini API (via `google-generativeai` Python package)
  - Deepseek API (via HTTP requests)
  - Ollama local inference (via HTTP requests to localhost)

**Python Libraries (already installed):**
- `anthropic` - Anthropic API client
- `openai` - OpenAI API client
- `google-generativeai` - Google Gemini API client
- `psycopg2` - PostgreSQL database adapter
- `dotenv` - Environment variable management

**Frontend Libraries (already installed):**
- React - UI framework
- TypeScript - Type safety
- Tailwind CSS v4 - Styling
- daisyUI - Component library
- React Query (if needed for polling) - Data fetching

**No new dependencies required.**

---

## 5. UI/UX Requirements

### 5.1 User Flow: Manual Enrichment

1. User navigates to **Settings page** (`/settings`)
2. User scrolls to **"LLM Enrichment"** section
3. System displays:
   - Configuration status: "✓ Configured: Anthropic Claude Sonnet"
   - Statistics: "475 of 500 transactions enriched (95%)"
   - Button: **"Enrich Transactions"**
   - Button: **"Retry Failed Enrichments"** (disabled if no failures)
4. User clicks **"Enrich Transactions"**
5. System calls `POST /api/enrichment/estimate`
6. System displays **EnrichmentCostModal**:
   - "Enrich 25 transactions?"
   - "Estimated cost: $0.0015 USD"
   - "Provider: Anthropic Claude Sonnet"
   - "This will use cached results for 10 transactions and call the API for 15 transactions."
   - Buttons: **"Confirm ($0.0015)"**, **"Cancel"**
7. User clicks **"Confirm"**
8. System calls `POST /api/enrichment/trigger` with `confirm_cost: true`
9. System displays **EnrichmentProgressModal**:
   - Progress bar: "15 of 25 transactions processed..."
   - Spinner animation
   - Status: "Enriching transactions..."
10. System polls `GET /api/enrichment/status/<job_id>` every 2 seconds
11. When job completes, modal shows:
    - "✓ Enrichment Complete"
    - "Successfully enriched 24 of 25 transactions"
    - "Cost: $0.00142 USD"
    - "1 failed (can retry later)"
    - Button: **"Close"**
12. User clicks **"Close"**
13. Page refreshes statistics to show updated counts

### 5.2 User Flow: Viewing Enrichment Data

1. User navigates to **Transactions page** (`/transactions`)
2. System fetches transactions via `GET /api/transactions` (includes enrichment data)
3. Transaction list displays columns:
   - Date
   - Description
   - Amount
   - **Category** (from enrichment.primary_category, fallback to transaction.category)
   - **Subcategory** (from enrichment.subcategory)
   - **Merchant** (from enrichment.merchant_clean_name, fallback to transaction.merchant)
   - **Status** (EnrichmentStatusIndicator badge)
4. Enriched transactions have:
   - Green checkmark badge in "Status" column
   - Tooltip on hover: "Enriched on Nov 29, 2025 (95% confidence)"
5. Unenriched transactions have:
   - Gray dash badge in "Status" column
   - Tooltip: "Not enriched"
6. User can filter by enrichment status:
   - Dropdown: "Show: All | Enriched | Unenriched"

### 5.3 User Flow: Retry Failed Enrichments

1. User navigates to **Settings page** (`/settings`)
2. If failed enrichments exist, **"Retry Failed Enrichments"** button is enabled
3. Button shows count: "Retry Failed Enrichments (2)"
4. User clicks button
5. System calls `POST /api/enrichment/retry` (no cost preview for retries)
6. System displays toast notification: "Retrying 2 failed enrichments..."
7. System polls job status
8. On completion, toast notification: "✓ Retry complete: 2 of 2 successful"
9. Failed enrichments count updates to 0

### 5.4 Wireframes/Mockups

**Settings Page - LLM Enrichment Section:**

```
┌─────────────────────────────────────────────────────────────┐
│ Settings                                                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ LLM Enrichment Configuration                                │
│ ─────────────────────────────────────────────────────────   │
│                                                              │
│ Status: ✓ Configured                                        │
│ Provider: Anthropic Claude                                  │
│ Model: claude-3-5-sonnet-20241022                           │
│ Cache: Enabled                                              │
│                                                              │
│ Statistics                                                  │
│ ─────────────────────────────────────────────────────────   │
│ Total Transactions: 500                                     │
│ Enriched: 475 (95%)                                         │
│ Unenriched: 25                                              │
│ Failed: 2                                                   │
│ Total Cost: $0.12 USD                                       │
│                                                              │
│ [Enrich Transactions]  [Retry Failed (2)]                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Cost Preview Modal:**

```
┌────────────────────────────────────────────────┐
│ Confirm Enrichment                            │
├────────────────────────────────────────────────┤
│                                                │
│ Enrich 25 transactions?                        │
│                                                │
│ Estimated Cost: $0.0015 USD                    │
│ Provider: Anthropic Claude Sonnet             │
│                                                │
│ Details:                                       │
│ • 10 transactions from cache (free)            │
│ • 15 transactions require API calls            │
│ • Estimated tokens: 3,000                      │
│                                                │
│         [Cancel]  [Confirm ($0.0015)]          │
│                                                │
└────────────────────────────────────────────────┘
```

**Transaction List with Enrichment:**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Transactions                                    Filter: [All ▼]  [Search]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Date       Description              Amount   Category    Subcategory Merchant Status │
├──────────────────────────────────────────────────────────────────────────────┤
│ 2025-11-15 TESCO STORES 1234       -£42.50  Groceries   Supermarkets Tesco   ✓     │
│ 2025-11-16 AMAZON UK MARKETPLACE   -£19.99  Shopping    Online       Amazon  ✓     │
│ 2025-11-17 TFL TRAVEL CHARGE        -£8.40  Transport   Public       TfL     ✓     │
│ 2025-11-18 UNKNOWN MERCHANT XYZ    -£12.00  Other       -            -       -     │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.5 Error Handling

| Error Condition | User Message | System Behavior |
|-----------------|--------------|-----------------|
| LLM provider not configured | "LLM enrichment is not configured. Set the LLM_PROVIDER and LLM_API_KEY in your environment to enable this feature." | Disable "Enrich Transactions" button; show config instructions |
| API key invalid | "Invalid API key. Check your LLM_API_KEY environment variable." | Display error toast; do not start enrichment |
| API rate limit exceeded | "Rate limit exceeded. Please wait 60 seconds and try again." | Display error toast; suggest retry after delay |
| API timeout | "Enrichment timed out. Some transactions may not be enriched. You can retry failed transactions." | Log failures to `llm_enrichment_failures`; show partial success message |
| Network error | "Network error. Check your internet connection and try again." | Display error toast; retry button enabled |
| No unenriched transactions | "All transactions are already enriched." | Display info toast; disable "Enrich Transactions" button |
| Cost estimation fails | "Could not estimate cost. Please try again." | Display error toast; do not show cost modal |
| Enrichment job fails | "Enrichment job failed: [error message]" | Display error toast; log to console; show retry button |

---

## 6. Acceptance Criteria

**The feature is complete when:**

- [ ] **AC-001**: User can trigger enrichment from Settings page with cost preview and confirmation
- [ ] **AC-002**: Cost preview modal displays estimated cost, transaction count, provider, and model before enrichment runs
- [ ] **AC-003**: Enrichment runs asynchronously and displays progress (spinner + "X of Y transactions...")
- [ ] **AC-004**: Enrichment completion shows success/failure summary with cost and token count
- [ ] **AC-005**: Transaction list displays enrichment data (category, subcategory, merchant) for enriched transactions
- [ ] **AC-006**: Transaction list displays visual indicator (badge/icon) showing which transactions are enriched
- [ ] **AC-007**: User can filter transactions by enrichment status (All, Enriched, Unenriched)
- [ ] **AC-008**: Failed enrichments can be retried from Settings page
- [ ] **AC-009**: Enrichment statistics are displayed on Settings page (total, enriched, unenriched, cost)
- [ ] **AC-010**: API endpoints return correct responses for estimate, trigger, status, stats, retry
- [ ] **AC-011**: Enrichment uses existing `LLMEnricher` class and database functions (no duplication)
- [ ] **AC-012**: Cache is used to avoid duplicate API calls for same transaction descriptions
- [ ] **AC-013**: Cost confirmation is required before enrichment runs (prevent accidental charges)
- [ ] **AC-014**: Documentation updated (this requirements document, API docs, user guide)
- [ ] **AC-015**: All tests passing (unit tests for API endpoints, integration tests for enrichment flow)

---

## 7. Open Questions

| # | Question | Answer | Status |
|---|----------|--------|--------|
| 1 | Should enrichment run automatically after TrueLayer imports? | User selected: "Optionally schedule batched background enrichment to follow the initial import" - Should be configurable via Settings toggle | Resolved |
| 2 | Should we show cost estimate EVERY time before enrichment? | User selected: "Yes, always show cost" - Must display cost preview modal before every manual enrichment trigger | Resolved |
| 3 | How should users retry failed enrichments? | User selected: "Manual retry button" - Add "Retry Failed Enrichments" button in Settings page | Resolved |
| 4 | Should enrichment data be editable in UI? | Out of scope - Enrichment data is read-only. Users cannot manually edit categories, subcategories, or merchant names. If incorrect, they must re-run enrichment. | Resolved |
| 5 | Should we support enrichment of TrueLayer transactions or only legacy Santander transactions? | Need clarification - Currently enrichment targets `transactions` table. Should `truelayer_transactions` also be enriched? | Open |
| 6 | What is the timeout for enrichment jobs? | Need clarification - Should we set a maximum time limit (e.g., 5 minutes) after which job is marked as failed? | Open |
| 7 | Should enrichment run in a background worker or inline? | Need clarification - Current CLI script runs inline. Should API use background worker (Celery, RQ) or async thread? For MVP, async thread is acceptable. | Open |

---

## 8. Implementation Guidance

### 8.1 Leveraging Existing Components

**DO NOT rewrite these - they are complete and tested:**

- `mcp/llm_enricher.py` - Core enrichment orchestrator
- `mcp/llm_providers.py` - Multi-provider support (Anthropic, OpenAI, Google, Deepseek, Ollama)
- `config/llm_config.py` - Configuration management
- Database tables: `transaction_enrichments`, `llm_enrichment_cache`, `llm_enrichment_failures`
- Database functions: `is_transaction_enriched()`, `get_enrichment_from_cache()`, `cache_enrichment()`, etc.

**Implementation Strategy:**

1. **API Endpoints** (backend/app.py):
   - Import `LLMEnricher` class: `from mcp.llm_enricher import get_enricher`
   - Call `enricher.enrich_transactions(transaction_ids, direction, force_refresh)`
   - Store job results in `truelayer_enrichment_jobs` table or in-memory job store
   - Return job ID for status polling

2. **Frontend Components**:
   - Create 3 new components: `EnrichmentCostModal`, `EnrichmentStatusIndicator`, `EnrichmentProgressModal`
   - Modify Settings page to add "LLM Enrichment" section
   - Modify Transaction list to display enrichment data columns
   - Use React hooks for API calls and polling

3. **Testing**:
   - Unit tests for API endpoints (mock `LLMEnricher` class)
   - Integration tests for enrichment flow (use test database)
   - Frontend tests for components (React Testing Library)

### 8.2 Cost Estimation Algorithm

```python
def estimate_enrichment_cost(transaction_ids=None, force_refresh=False):
    """Estimate cost for enriching transactions."""
    from mcp.llm_enricher import get_enricher
    from config.llm_config import get_provider_info

    enricher = get_enricher()
    if not enricher:
        return {"configured": False, "error": "LLM not configured"}

    # Get transactions to enrich
    if transaction_ids:
        transactions = [database.get_transaction_by_id(tid) for tid in transaction_ids]
    else:
        transactions = database.get_all_transactions() or []

    # Filter out already enriched (unless force_refresh)
    to_enrich = []
    cached_available = 0

    for txn in transactions:
        if not force_refresh and database.is_transaction_enriched(txn["id"]):
            continue

        # Check cache
        direction = 'out' if txn['amount'] < 0 else 'in'
        cached = database.get_enrichment_from_cache(txn['description'], direction)
        if cached:
            cached_available += 1
        else:
            to_enrich.append(txn)

    # Calculate cost
    provider_info = get_provider_info(enricher.config.provider)
    cost_per_1k_input = provider_info.get('cost_per_1k_input_tokens', 0)
    cost_per_1k_output = provider_info.get('cost_per_1k_output_tokens', 0)

    # Assume 150 input tokens + 50 output tokens per transaction (average)
    estimated_input_tokens = len(to_enrich) * 150
    estimated_output_tokens = len(to_enrich) * 50

    estimated_cost = (
        (estimated_input_tokens / 1000 * cost_per_1k_input) +
        (estimated_output_tokens / 1000 * cost_per_1k_output)
    )

    return {
        "total_transactions": len(transactions),
        "already_enriched": len(transactions) - len(to_enrich) - cached_available,
        "to_be_enriched": len(to_enrich) + cached_available,
        "cached_available": cached_available,
        "requires_api_call": len(to_enrich),
        "estimated_tokens": estimated_input_tokens + estimated_output_tokens,
        "estimated_cost": round(estimated_cost, 6),
        "currency": "USD",
        "provider": enricher.config.provider.value,
        "model": enricher.config.model,
        "cost_per_1k_tokens": cost_per_1k_input
    }
```

### 8.3 Job Status Tracking

**Option 1: Use `truelayer_enrichment_jobs` table**
- Store job in database before enrichment starts
- Update job status, progress, and results after completion
- Query job by ID for status polling

**Option 2: In-memory job store (simpler for MVP)**
- Store job dict in global `enrichment_jobs = {}` dictionary
- Key: job_id (e.g., `enrich-20251129-001`)
- Value: `{"status": "running", "total": 150, "processed": 85, ...}`
- Clear jobs after 1 hour (or after user retrieves completed job)

**Recommendation:** Use in-memory job store for MVP. Migrate to database if persistence is required.

### 8.4 Asynchronous Enrichment

**Option 1: Background thread**
```python
import threading

@app.route('/api/enrichment/trigger', methods=['POST'])
def trigger_enrichment():
    # ... validate request ...

    job_id = f"enrich-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Start enrichment in background thread
    def run_enrichment():
        enrichment_jobs[job_id] = {"status": "running", "started_at": datetime.now()}

        try:
            enricher = get_enricher()
            stats = enricher.enrich_transactions(transaction_ids=..., ...)

            enrichment_jobs[job_id] = {
                "status": "completed",
                "stats": stats,
                "completed_at": datetime.now()
            }
        except Exception as e:
            enrichment_jobs[job_id] = {"status": "failed", "error": str(e)}

    thread = threading.Thread(target=run_enrichment)
    thread.start()

    return jsonify({"job_id": job_id, "status": "running"}), 202
```

**Option 2: Task queue (Celery, RQ)** - More robust but requires additional setup. Defer to Phase 2 if needed.

**Recommendation:** Use background thread for MVP.

---

## 9. Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-11-29 | Requirements Development Agent | Initial draft based on user requirements elicitation |

---

## 10. Approval

- [x] Requirements reviewed with stakeholder
- [x] Technical feasibility confirmed (core engine already built)
- [x] Ready for implementation

**Approved for implementation:** Yes
**Approved by:** User
**Date:** 2025-11-29

---

## Appendix A: Enrichment Data Schema

**Enrichment Response Structure** (from `LLMEnricher.enrich_transactions()`):

```python
@dataclass
class EnrichmentResult:
    primary_category: str  # e.g., "Groceries"
    subcategory: str  # e.g., "Supermarkets"
    merchant_clean_name: str  # e.g., "Tesco"
    merchant_type: str  # e.g., "Retail"
    essential_discretionary: str  # "Essential" or "Discretionary"
    payment_method: str  # e.g., "Debit Card"
    payment_method_subtype: str  # e.g., "Contactless"
    purchase_date: str  # ISO 8601 date
    confidence_score: float  # 0.0-1.0
    llm_provider: str  # e.g., "anthropic"
    llm_model: str  # e.g., "claude-3-5-sonnet-20241022"
```

**Database Storage:**
All fields stored in `transaction_enrichments` table with foreign key to `transactions.id`.

---

## Appendix B: LLM Provider Configuration

**Environment Variables:**
```bash
# Required
LLM_PROVIDER=anthropic  # anthropic|openai|google|deepseek|ollama
LLM_API_KEY=sk-ant-...  # API key (not needed for Ollama)
LLM_MODEL=claude-3-5-sonnet-20241022  # Model name

# Optional
LLM_API_BASE_URL=https://api.anthropic.com  # Custom API endpoint
LLM_TIMEOUT=30  # Request timeout in seconds
LLM_MAX_RETRIES=3  # Number of retries
LLM_BATCH_SIZE_INITIAL=10  # Initial batch size
LLM_BATCH_SIZE=20  # Override batch size for all providers
LLM_CACHE_ENABLED=true  # Enable caching (default: true)
LLM_DEBUG=false  # Debug mode (default: false)
LLM_OLLAMA_COST_PER_TOKEN=0.000003  # Cost per token for Ollama (optional)
```

**Supported Providers:**

| Provider | Models | Cost per 1K Input Tokens | Cost per 1K Output Tokens |
|----------|--------|-------------------------|--------------------------|
| Anthropic | claude-3-5-sonnet-20241022 | $0.003 | $0.015 |
| OpenAI | gpt-4-turbo, gpt-3.5-turbo | $0.01 | $0.03 |
| Google | gemini-1.5-flash | $0.00035 | $0.0007 |
| Deepseek | deepseek-chat | $0.00014 | $0.00028 |
| Ollama | mistral:7b (local) | $0.000003 (configurable) | $0.000009 |

---

## Appendix C: Reference Documentation

- **Core Engine:** `/mnt/c/dev/spending/backend/mcp/llm_enricher.py`
- **Provider Implementations:** `/mnt/c/dev/spending/backend/mcp/llm_providers.py`
- **Configuration:** `/mnt/c/dev/spending/backend/config/llm_config.py`
- **CLI Tool:** `/mnt/c/dev/spending/backend/enrich_existing_transactions.py`
- **Database Schema:** `/mnt/c/dev/spending/.claude/docs/database/DATABASE_SCHEMA.md`
- **API Endpoints:** `/mnt/c/dev/spending/backend/app.py`
- **Migration:** `/mnt/c/dev/spending/backend/migrations/003_add_import_jobs.sql`

---

**End of Requirements Document**
