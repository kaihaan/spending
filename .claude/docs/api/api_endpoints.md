# API Endpoints Reference

**Last Updated:** 2025-11-29
**Base URL:** `http://localhost:5000`
**Content-Type:** `application/json`
**Source:** `backend/app.py`

---

## Overview

This document is the **authoritative reference** for all backend API endpoints. Claude MUST consult this document before implementing or modifying any API-related code.

> ⚠️ **If an endpoint is not documented here, verify it exists in `backend/app.py` before using it.**

---

## Table of Contents

1. [Health](#health)
2. [Transactions](#transactions)
3. [Categories](#categories)
4. [Huququllah Classification](#huququllah-classification)
5. [Account Mappings](#account-mappings)
6. [Amazon Integration](#amazon-integration)
7. [Amazon Returns](#amazon-returns)
8. [Apple Integration](#apple-integration)
9. [TrueLayer Integration](#truelayer-integration)
10. [Migrations](#migrations)
11. [Error Responses](#error-responses)

---

## Health

### GET /api/health

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "message": "Backend is running"
}
```

---

## Transactions

### GET /api/transactions

Retrieve all transactions (both regular imports and TrueLayer synced).

**Note:** Returns combined list sorted by date descending. No query parameters currently implemented in code.

**Response:**
```json
[
  {
    "id": 1,
    "date": "2025-01-15",
    "description": "TESCO STORES 1234",
    "amount": -42.75,
    "category": "Groceries",
    "merchant": "Tesco",
    "source_file": "statement.xlsx",
    "huququllah_classification": "essential"
  }
]
```

---

### POST /api/transactions

Manually add a transaction (for testing only).

**Request:**
```json
{
  "date": "2025-01-15",
  "description": "TESCO STORES 1234",
  "amount": -42.75,
  "category": "Groceries",
  "source_file": "manual",
  "merchant": "Tesco"
}
```

**Required Fields:** `date`, `description`, `amount`

**Response (201):**
```json
{
  "id": 123,
  "date": "2025-01-15",
  "description": "TESCO STORES 1234",
  "amount": -42.75,
  "category": "Groceries"
}
```

---

### PUT /api/transactions/{transaction_id}/category

Update category for a specific transaction.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | integer | Transaction ID |

**Request:**
```json
{
  "category": "Groceries"
}
```

**Response:**
```json
{
  "success": true,
  "id": 123,
  "category": "Groceries"
}
```

---

### POST /api/transactions/{transaction_id}/category/smart

Smart category update with merchant learning. Updates transaction and optionally applies to all transactions from same merchant.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | integer | Transaction ID |

**Request:**
```json
{
  "category": "Groceries",
  "apply_to_merchant": true,
  "add_to_rules": true
}
```

**Response:**
```json
{
  "success": true,
  "updated_count": 15,
  "merchant": "Tesco",
  "rule_added": true,
  "category": "Groceries"
}
```

---

### GET /api/transactions/{transaction_id}/merchant-info

Get merchant information for a transaction.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | integer | Transaction ID |

**Response:**
```json
{
  "merchant": "Tesco",
  "merchant_transaction_count": 45,
  "current_category": "Groceries"
}
```

---

### DELETE /api/transactions/clear

Clear all transactions from database (for testing).

**Response:**
```json
{
  "success": true,
  "message": "Cleared 150 transaction(s)",
  "count": 150
}
```

---

## Categories

### GET /api/categories

Get all categories.

**Response:**
```json
[
  {
    "name": "Groceries",
    "rule_pattern": "TESCO|SAINSBURY|ASDA",
    "ai_suggested": false
  }
]
```

---

### GET /api/stats/categories

Get statistics about spending by category.

**Response:**
```json
{
  "Groceries": {
    "total": 450.00,
    "count": 25,
    "percentage": 30.0
  },
  "Transport": {
    "total": 200.00,
    "count": 15,
    "percentage": 13.3
  }
}
```

---

## Huququllah Classification

### PUT /api/transactions/{transaction_id}/huququllah

Update Huququllah classification for a transaction.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | integer | Transaction ID |

**Request:**
```json
{
  "classification": "essential"
}
```

**Valid Values:** `"essential"`, `"discretionary"`, `null`

**Response:**
```json
{
  "success": true,
  "transaction_id": 123,
  "classification": "essential"
}
```

---

### GET /api/huququllah/suggest/{transaction_id}

Get smart suggestion for classifying a transaction.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | integer | Transaction ID |

**Response:**
```json
{
  "suggestion": "essential",
  "confidence": 0.85,
  "reason": "Groceries are typically essential expenses"
}
```

---

### GET /api/huququllah/summary

Get Huququllah summary with essential vs discretionary totals.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | string (YYYY-MM-DD) | No | Start date |
| `date_to` | string (YYYY-MM-DD) | No | End date |

**Response:**
```json
{
  "essential_total": 1200.00,
  "discretionary_total": 800.00,
  "unclassified_total": 500.00,
  "huququllah_amount": 152.00,
  "huququllah_percentage": 19
}
```

---

### GET /api/huququllah/unclassified

Get all transactions not yet classified.

**Response:**
```json
[
  {
    "id": 123,
    "date": "2025-01-15",
    "description": "AMAZON PURCHASE",
    "amount": -25.99,
    "category": "Shopping",
    "merchant": "Amazon"
  }
]
```

---

## Account Mappings

### GET /api/settings/account-mappings

Get all account mappings.

**Response:**
```json
[
  {
    "id": 1,
    "sort_code": "123456",
    "account_number": "12345678",
    "friendly_name": "Joint Account"
  }
]
```

---

### POST /api/settings/account-mappings

Create a new account mapping.

**Request:**
```json
{
  "sort_code": "123456",
  "account_number": "12345678",
  "friendly_name": "Joint Account"
}
```

**Validation:**
- `sort_code`: Must be 6 digits (hyphens/spaces stripped)
- `account_number`: Must be 8 digits (spaces stripped)

**Response (201):**
```json
{
  "success": true,
  "id": 1
}
```

**Error (409):** Account mapping already exists

---

### PUT /api/settings/account-mappings/{mapping_id}

Update an existing account mapping.

**Request:**
```json
{
  "friendly_name": "Updated Name"
}
```

**Response:**
```json
{
  "success": true
}
```

---

### DELETE /api/settings/account-mappings/{mapping_id}

Delete an account mapping.

**Response:**
```json
{
  "success": true
}
```

---

### GET /api/settings/account-mappings/discover

Discover unmapped account patterns in transactions.

**Response:**
```json
[
  {
    "sort_code": "654321",
    "account_number": "87654321",
    "sample_description": "FP TO 654321 87654321",
    "count": 12
  }
]
```

---

## Amazon Integration

### POST /api/amazon/import

Import Amazon order history from CSV file.

**Request:**
```json
{
  "filename": "amazon-orders-2024.csv",
  "website": "Amazon.co.uk"
}
```

**Response (201):**
```json
{
  "success": true,
  "orders_imported": 150,
  "orders_duplicated": 5,
  "matching_results": {
    "matched": 120,
    "unmatched": 30
  },
  "filename": "amazon-orders-2024.csv"
}
```

---

### GET /api/amazon/orders

Get all Amazon orders with optional filters.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | string | No | Start date |
| `date_to` | string | No | End date |
| `website` | string | No | Filter by website |

**Response:**
```json
{
  "orders": [
    {
      "order_id": "123-456-789",
      "order_date": "2025-01-10",
      "product_name": "USB Cable",
      "total_owed": 9.99,
      "currency": "GBP",
      "order_status": "Delivered"
    }
  ],
  "count": 150
}
```

---

### DELETE /api/amazon/orders

Clear all Amazon orders and matches.

**Response:**
```json
{
  "success": true,
  "orders_deleted": 150,
  "matches_deleted": 120,
  "message": "Cleared 150 orders and 120 matches"
}
```

---

### GET /api/amazon/statistics

Get Amazon import and matching statistics.

**Response:**
```json
{
  "total_orders": 150,
  "matched_orders": 120,
  "unmatched_orders": 30,
  "total_amount": 2500.00,
  "date_range": {
    "earliest": "2024-01-01",
    "latest": "2025-01-15"
  }
}
```

---

### POST /api/amazon/match

Run or re-run Amazon matching on existing transactions.

**Response:**
```json
{
  "success": true,
  "results": {
    "matched": 25,
    "already_matched": 95,
    "unmatched": 30
  }
}
```

---

### POST /api/amazon/match/{transaction_id}

Re-match a specific transaction with Amazon orders.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `transaction_id` | integer | Transaction ID |

**Response:**
```json
{
  "success": true,
  "match": {
    "order_id": "123-456-789",
    "product_name": "USB Cable",
    "confidence": 0.95
  }
}
```

---

### GET /api/amazon/coverage

Check if Amazon order data exists for a date range.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `date_from` | string | Yes | Start date |
| `date_to` | string | Yes | End date |

**Response:**
```json
{
  "has_coverage": true,
  "coverage_start": "2024-01-01",
  "coverage_end": "2025-01-15",
  "gaps": []
}
```

---

### GET /api/amazon/unmatched

Get Amazon transactions not matched to orders.

**Response:**
```json
{
  "transactions": [...],
  "count": 30
}
```

---

### GET /api/amazon/files

List available Amazon CSV files in sample folder.

**Response:**
```json
{
  "files": [
    {
      "filename": "amazon-orders-2024.csv",
      "path": "../sample/amazon-orders-2024.csv"
    }
  ],
  "count": 2
}
```

---

### POST /api/amazon/upload

Upload an Amazon CSV file.

**Request:** `multipart/form-data` with `file` field

**Response (201):**
```json
{
  "success": true,
  "message": "File uploaded successfully: amazon-orders-2024.csv",
  "filename": "amazon-orders-2024.csv"
}
```

---

## Amazon Returns

### POST /api/amazon/returns/import

Import Amazon returns/refunds from CSV file.

**Request:**
```json
{
  "filename": "amazon-refunds-2024.csv"
}
```

**Response (201):**
```json
{
  "success": true,
  "returns_imported": 10,
  "returns_duplicated": 0,
  "matching_results": {...},
  "filename": "amazon-refunds-2024.csv"
}
```

---

### GET /api/amazon/returns

Get all Amazon returns.

**Response:**
```json
{
  "returns": [...],
  "count": 10
}
```

---

### DELETE /api/amazon/returns

Clear all Amazon returns.

**Response:**
```json
{
  "success": true,
  "returns_deleted": 10,
  "message": "Cleared 10 returns and removed [RETURNED] labels"
}
```

---

### GET /api/amazon/returns/statistics

Get Amazon returns statistics.

**Response:**
```json
{
  "total_returns": 10,
  "total_refunded": 150.00,
  "matched_to_orders": 8
}
```

---

### POST /api/amazon/returns/match

Run or re-run returns matching.

**Response:**
```json
{
  "success": true,
  "results": {...}
}
```

---

### GET /api/amazon/returns/files

List available Amazon returns CSV files.

**Response:**
```json
{
  "files": [...],
  "count": 1
}
```

---

## Apple Integration

### POST /api/apple/import

Import Apple transactions from HTML file.

**Request:**
```json
{
  "filename": "apple-purchases.html"
}
```

**Response (201):**
```json
{
  "success": true,
  "transactions_imported": 50,
  "transactions_duplicated": 2,
  "matching_results": {...},
  "filename": "apple-purchases.html"
}
```

---

### GET /api/apple

Get all Apple transactions.

**Response:**
```json
{
  "transactions": [
    {
      "order_id": "ABC123",
      "order_date": "2025-01-10",
      "total_amount": 4.99,
      "currency": "GBP",
      "app_names": "Spotify Premium",
      "publishers": "Spotify AB"
    }
  ],
  "count": 50
}
```

---

### DELETE /api/apple

Clear all Apple transactions.

**Response:**
```json
{
  "success": true,
  "transactions_deleted": 50,
  "message": "Cleared 50 Apple transactions"
}
```

---

### GET /api/apple/statistics

Get Apple transactions statistics.

**Response:**
```json
{
  "total_transactions": 50,
  "total_amount": 250.00,
  "matched": 45,
  "unmatched": 5
}
```

---

### POST /api/apple/match

Run or re-run Apple transaction matching.

**Response:**
```json
{
  "success": true,
  "results": {...}
}
```

---

### GET /api/apple/files

List available Apple HTML files.

**Response:**
```json
{
  "files": [...],
  "count": 1
}
```

---

### POST /api/apple/export-csv

Convert Apple HTML to CSV format.

**Request:**
```json
{
  "filename": "apple-purchases.html"
}
```

**Response:**
```json
{
  "success": true,
  "csv_filename": "apple-purchases.csv",
  "transactions_count": 50,
  "message": "Exported 50 transactions to apple-purchases.csv"
}
```

---

## TrueLayer Integration

### GET /api/truelayer/authorize

Initiate TrueLayer OAuth authorization flow.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_id` | integer | No | 1 | User ID |

**Response:**
```json
{
  "auth_url": "https://auth.truelayer.com/...",
  "state": "abc123def456",
  "code_verifier": "pkce_verifier_string"
}
```

---

### GET /api/truelayer/callback

Handle TrueLayer OAuth callback. Redirects to frontend.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `code` | string | Yes | Authorization code from TrueLayer |
| `state` | string | Yes | State parameter for CSRF protection |
| `code_verifier` | string | No | PKCE verifier (optional, retrieved from DB if not provided) |
| `user_id` | integer | No | User ID (default: 1) |

**Success Redirect:** `{FRONTEND_URL}/auth/callback?status=authorized&connection_id={id}`

**Error Redirect:** `{FRONTEND_URL}/auth/callback?error={message}`

---

### GET /api/truelayer/accounts

Get list of connected TrueLayer accounts.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_id` | integer | No | 1 | User ID |

**Response:**
```json
{
  "connections": [
    {
      "id": 1,
      "provider_id": "ob-santander",
      "connection_status": "active",
      "last_synced_at": "2025-01-15T14:30:00Z",
      "accounts": [
        {
          "id": 1,
          "account_id": "abc123",
          "display_name": "Current Account",
          "account_type": "TRANSACTION",
          "currency": "GBP",
          "last_synced_at": "2025-01-15T14:30:00Z"
        }
      ]
    }
  ]
}
```

---

### POST /api/truelayer/discover-accounts

Discover and sync accounts for a specific connection.

**Request:**
```json
{
  "connection_id": 1
}
```

**Response:**
```json
{
  "status": "success",
  "accounts_discovered": 3,
  "accounts_saved": 2,
  "accounts": [...]
}
```

---

### POST /api/truelayer/sync

Trigger manual sync of TrueLayer transactions.

**Request:**
```json
{
  "user_id": 1,
  "connection_id": 1
}
```

**Note:** If `connection_id` provided without `user_id`, user_id is looked up from connection.

**Response:**
```json
{
  "status": "completed",
  "summary": {
    "total_accounts": 2,
    "total_synced": 150,
    "total_duplicates": 10,
    "total_errors": 0
  },
  "result": {...}
}
```

---

### GET /api/truelayer/sync/status

Get sync status for all accounts.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_id` | integer | No | 1 | User ID |

**Response:**
```json
{
  "accounts": [
    {
      "account_id": "abc123",
      "last_synced": "2025-01-15T14:30:00Z",
      "transaction_count": 500,
      "status": "synced"
    }
  ]
}
```

---

### POST /api/truelayer/disconnect

Disconnect a TrueLayer bank account.

**Request:**
```json
{
  "connection_id": 1
}
```

**Response:**
```json
{
  "status": "disconnected",
  "connection_id": 1
}
```

---

### DELETE /api/truelayer/clear-transactions

Clear all TrueLayer transactions from database.

**Headers Required:**
| Header | Value | Description |
|--------|-------|-------------|
| `X-Confirm-Delete` | `yes` | Confirmation header |

**Response:**
```json
{
  "success": true,
  "message": "Deleted 500 TrueLayer transaction(s)",
  "deleted_count": 500
}
```

---

### POST /api/truelayer/fetch-accounts

On-demand fetch of TrueLayer account transactions.

**Request:**
```json
{
  "user_id": 1,
  "connection_id": 1
}
```

**Response:**
```json
{
  "status": "completed",
  "result": {...}
}
```

---

### POST /api/truelayer/fetch-cards

On-demand fetch of TrueLayer card transactions.

**Request:**
```json
{
  "user_id": 1,
  "connection_id": 1
}
```

**Response:**
```json
{
  "status": "completed",
  "result": {...}
}
```

---

### GET /api/truelayer/cards

Get all connected TrueLayer cards for a user.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_id` | integer | No | 1 | User ID |

**Response:**
```json
{
  "user_id": 1,
  "connections": [
    {
      "connection_id": 1,
      "provider_id": "ob-santander",
      "connection_status": "active",
      "last_synced_at": "2025-01-15T14:30:00Z",
      "cards": [...]
    }
  ]
}
```

---

### POST /api/truelayer/fetch-transactions

On-demand fetch of transactions for a specific account or card.

**Request:**
```json
{
  "account_id": "abc123",
  "from_date": "2024-01-01",
  "to_date": "2025-01-15"
}
```

OR

```json
{
  "card_id": "def456",
  "from_date": "2024-01-01",
  "to_date": "2025-01-15"
}
```

**Response:**
```json
{
  "status": "completed",
  "account_id": "abc123",
  "total_transactions": 150,
  "synced": 140,
  "duplicates": 10,
  "transactions": [...]
}
```

---

### POST /api/truelayer/import/plan

Plan an import job and provide estimates.

**Request:**
```json
{
  "user_id": 1,
  "connection_id": 1,
  "from_date": "2024-01-01",
  "to_date": "2025-01-15",
  "account_ids": ["abc123", "def456"],
  "auto_enrich": true,
  "batch_size": 50
}
```

**Required Fields:** `connection_id`, `from_date`, `to_date`

**Response (201):**
```json
{
  "job_id": 123,
  "status": "planned",
  "connection_id": 1,
  "from_date": "2024-01-01",
  "to_date": "2025-01-15",
  "accounts": [...],
  "estimated_transactions": 500
}
```

---

### POST /api/truelayer/import/start

Start an import job.

**Request:**
```json
{
  "job_id": 123
}
```

**Response:**
```json
{
  "job_id": 123,
  "status": "completed",
  "total_synced": 500,
  "total_duplicates": 10,
  "total_errors": 0,
  "accounts": [...]
}
```

---

### GET /api/truelayer/import/status/{job_id}

Get current import job status and progress.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | integer | Import job ID |

**Response:**
```json
{
  "job_id": 123,
  "status": "in_progress",
  "progress": {
    "total": 500,
    "completed": 250,
    "percentage": 50
  },
  "accounts": [...]
}
```

**Status Values:** `planned`, `in_progress`, `completed`, `failed`, `cancelled`

---

### GET /api/truelayer/import/history

Get import job history for user.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `user_id` | integer | No | 1 | User ID |
| `limit` | integer | No | 50 | Max results |

**Response:**
```json
{
  "user_id": 1,
  "imports": [
    {
      "job_id": 123,
      "status": "completed",
      "from_date": "2024-01-01",
      "to_date": "2025-01-15",
      "total_synced": 500,
      "created_at": "2025-01-15T10:00:00Z"
    }
  ]
}
```

---

### POST /api/truelayer/webhook

Handle incoming TrueLayer webhook events.

**Request:** TrueLayer webhook payload

**Response:**
```json
{
  "status": "processed",
  "event_type": "...",
  "result": {...}
}
```

---

## Migrations

These endpoints are for data migrations and maintenance tasks.

### GET /api/migrations/normalize-merchants/preview

Preview merchant normalization changes.

**Response:**
```json
{
  "would_update": 50,
  "sample_changes": [
    {
      "original": "TESCO STORES 1234",
      "normalized": "Tesco"
    }
  ]
}
```

---

### POST /api/migrations/normalize-merchants

Apply merchant normalization to all transactions.

**Response:**
```json
{
  "success": true,
  "updated_count": 50,
  "sample_changes": [...]
}
```

---

### Merchant Fix Endpoints

Each merchant type has preview (GET) and apply (POST) endpoints:

| Endpoint Pattern | Description |
|------------------|-------------|
| `/api/migrations/fix-paypal-merchants` | Extract merchants from PayPal transactions |
| `/api/migrations/fix-via-apple-pay-merchants` | Extract merchants from Apple Pay transactions |
| `/api/migrations/fix-zettle-merchants` | Extract merchants from Zettle transactions |
| `/api/migrations/fix-bill-payment-merchants` | Extract merchants from bill payments |
| `/api/migrations/fix-bank-giro-merchants` | Extract merchants from bank giro credits |
| `/api/migrations/fix-direct-debit-merchants` | Extract merchants from direct debits |
| `/api/migrations/fix-card-payment-merchants` | Extract merchants from card payments (POST only) |

---

### POST /api/migrations/reapply-account-mappings

Re-process transactions to apply account mappings.

**Response:**
```json
{
  "success": true,
  "transactions_updated": 25,
  "transactions_total": 500
}
```

---

### POST /api/migrations/add-huququllah-column

Migration to add huququllah_classification column.

**Response:**
```json
{
  "success": true,
  "column_added": true,
  "message": "Migration completed successfully"
}
```

---

### POST /api/migrations/refresh-lookup-descriptions

Refresh lookup_description field for matched transactions.

**Response:**
```json
{
  "success": true,
  "message": "Updated 120 lookup descriptions",
  "updated": {
    "total": 120,
    "amazon": 100,
    "apple": 20
  }
}
```

---

## Error Responses

All endpoints return errors in this format:

```json
{
  "error": "Human-readable error message"
}
```

**HTTP Status Codes:**
| Status | Description |
|--------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Resource not found |
| 409 | Conflict - Resource already exists |
| 500 | Internal Server Error |

---

## Changelog

| Date | Change |
|------|--------|
| 2025-11-29 | Comprehensive documentation from app.py |

---

## Notes for Claude

1. **Before implementing API calls:** Verify endpoint exists in this doc AND in `backend/app.py`
2. **Response schemas:** These are based on actual code - use exact field names
3. **Adding new endpoints:** Update this document IMMEDIATELY after adding
4. **Default user_id:** Most endpoints default to `user_id=1` when not specified
5. **Date formats:** Always use `YYYY-MM-DD` format for dates
6. **TrueLayer endpoints:** Many require a valid connection with active OAuth tokens