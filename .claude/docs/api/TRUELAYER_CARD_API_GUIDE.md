# TrueLayer Card & Account Integration - API Guide

## Overview

This guide documents the on-demand transaction fetching system for both TrueLayer accounts and credit cards.

## Architecture

### Database Schema

**truelayer_cards** - Stores card metadata
```
- id (PK)
- connection_id (FK to bank_connections)
- card_id (TrueLayer card ID)
- card_name, card_type, last_four, issuer
- status, last_synced_at
- created_at, updated_at
```

**truelayer_card_transactions** - Stores card transactions
```
- id (PK)
- card_id (FK to truelayer_cards)
- transaction_id, normalised_provider_id (UNIQUE for deduplication)
- timestamp, description, amount, currency
- transaction_type, category, merchant_name
- running_balance, metadata
- created_at
```

**truelayer_card_balance_snapshots** - Card balance history
```
- id (PK)
- card_id (FK to truelayer_cards)
- current_balance, currency, snapshot_at
- created_at
```

### TrueLayer Client (mcp/truelayer_client.py)

New methods:
- `get_cards()` - List all connected cards
- `get_card(card_id)` - Get specific card details
- `get_card_balance(card_id)` - Get card balance
- `get_card_transactions(card_id, from_date, to_date)` - Fetch transactions
- `normalize_card_transaction(txn)` - Normalize card transaction format
- `fetch_all_card_transactions(card_id, days_back)` - Convenience method

### Sync Module (mcp/truelayer_sync.py)

New functions:
- `sync_card_transactions()` - Sync single card with incremental support
- `sync_all_cards(user_id)` - Discover and sync all cards for user

Features:
- Automatic card discovery from `/data/v3/cards` endpoint
- Incremental syncing based on `last_synced_at`
- Deduplication using `normalised_provider_id`
- Transaction normalization to app format
- Error handling and logging

## API Endpoints

### 1. GET /api/truelayer/cards

Lists all connected cards for a user.

**Parameters:**
- `user_id` (query, optional): User ID (defaults to 1)

**Response:**
```json
{
  "user_id": 1,
  "connections": [
    {
      "connection_id": 3,
      "provider_id": "truelayer",
      "connection_status": "active",
      "last_synced_at": "2024-11-25T10:30:00",
      "cards": [
        {
          "id": 5,
          "card_id": "card_xyz",
          "card_name": "Chase Visa",
          "card_type": "CREDIT_CARD",
          "last_four": "4242",
          "issuer": "Chase",
          "status": "active",
          "last_synced_at": "2024-11-25T10:30:00",
          "created_at": "2024-11-20T15:00:00"
        }
      ]
    }
  ]
}
```

**Example:**
```bash
curl "http://localhost:5000/api/truelayer/cards?user_id=1"
```

---

### 2. POST /api/truelayer/fetch-accounts

Triggers on-demand sync of all account transactions for a user.

**Request Body:**
```json
{
  "user_id": 1
}
```

Or with connection_id:
```json
{
  "connection_id": 3
}
```

**Response:**
```json
{
  "status": "completed",
  "result": {
    "user_id": 1,
    "total_accounts": 2,
    "total_synced": 45,
    "total_duplicates": 3,
    "total_errors": 0,
    "accounts": [
      {
        "account_id": "acc_123",
        "synced": 25,
        "duplicates": 1,
        "errors": 0,
        "total_processed": 26
      },
      {
        "account_id": "acc_456",
        "synced": 20,
        "duplicates": 2,
        "errors": 0,
        "total_processed": 22
      }
    ]
  }
}
```

**Example:**
```bash
curl -X POST "http://localhost:5000/api/truelayer/fetch-accounts" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'
```

---

### 3. POST /api/truelayer/fetch-cards

Triggers on-demand discovery and sync of all cards for a user.

**Request Body:**
```json
{
  "user_id": 1
}
```

Or with connection_id:
```json
{
  "connection_id": 3
}
```

**Response:**
```json
{
  "status": "completed",
  "result": {
    "user_id": 1,
    "total_cards": 2,
    "total_synced": 15,
    "total_duplicates": 1,
    "total_errors": 0,
    "cards": [
      {
        "card_id": "card_123",
        "synced": 8,
        "duplicates": 0,
        "errors": 0,
        "total_processed": 8
      },
      {
        "card_id": "card_456",
        "synced": 7,
        "duplicates": 1,
        "errors": 0,
        "total_processed": 8
      }
    ]
  }
}
```

**Key Features:**
- Auto-discovers cards from TrueLayer API each time
- Discovers new cards and updates existing ones
- Automatically syncs transactions for each discovered card
- Returns aggregate statistics

**Example:**
```bash
curl -X POST "http://localhost:5000/api/truelayer/fetch-cards" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'
```

---

### 4. POST /api/truelayer/fetch-transactions

On-demand fetch of transactions for a specific account or card with optional date filtering.

**Request Body (for account):**
```json
{
  "account_id": "acc_123",
  "from_date": "2024-11-01",
  "to_date": "2024-11-30"
}
```

**Request Body (for card):**
```json
{
  "card_id": "card_123",
  "from_date": "2024-11-01",
  "to_date": "2024-11-30"
}
```

**Response:**
```json
{
  "status": "completed",
  "account_id": "acc_123",
  "total_transactions": 42,
  "synced": 40,
  "duplicates": 2,
  "transactions": [
    {
      "date": "2024-11-25",
      "description": "SAINSBURY'S STORE",
      "merchant_name": "Sainsburys",
      "transaction_type": "DEBIT",
      "amount": 45.67,
      "currency": "GBP",
      "category": "GROCERIES",
      "transaction_id": "txn_abc123",
      "normalised_provider_id": "norm_123",
      "running_balance": 1234.56
    }
  ]
}
```

**Error Handling:**
```json
{
  "error": "Must provide either account_id or card_id"
}
```

```json
{
  "error": "Account invalid-id not found"
}
```

```json
{
  "error": "Card invalid-id not found"
}
```

**Example (Account):**
```bash
curl -X POST "http://localhost:5000/api/truelayer/fetch-transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": "acc_123",
    "from_date": "2024-11-01",
    "to_date": "2024-11-30"
  }'
```

**Example (Card with date range):**
```bash
curl -X POST "http://localhost:5000/api/truelayer/fetch-transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "card_456",
    "from_date": "2024-10-01",
    "to_date": "2024-11-30"
  }'
```

---

## Implementation Details

### Incremental Syncing

Both accounts and cards track `last_synced_at` timestamps to enable efficient incremental syncing:

1. First sync: Fetches full 90 days of history
2. Subsequent syncs: Only fetches data since last sync (with 1-day buffer)
3. Reduces API calls and improves performance

### Deduplication

All transactions are deduplicated using `normalised_provider_id`:

- Unique constraint prevents duplicate inserts
- Safe to retry failed syncs without data corruption
- Supports partial imports and recovery scenarios

### Transaction Normalization

Both account and card transactions use identical internal format for consistency:

```python
{
    'date': '2024-11-25',
    'description': 'Payment to Vendor',
    'merchant_name': 'Vendor Name',
    'transaction_type': 'DEBIT',  # or CREDIT
    'amount': 99.99,
    'currency': 'GBP',
    'transaction_id': 'txn_123',
    'normalised_provider_id': 'norm_123',
    'category': 'Shopping',
    'running_balance': 1234.56,
    'metadata': {
        'provider_id': 'provider_123',
        'provider_transaction_id': 'prov_txn_456',
        'meta': {}
    }
}
```

### Error Handling

All endpoints include comprehensive error handling:

- **400 Bad Request**: Missing required parameters
- **404 Not Found**: Account or card not found
- **500 Internal Server Error**: API or database errors (logs detailed error)

### Sync Result Format

All sync endpoints return consistent result format:

```python
{
    'synced': 45,           # New transactions imported
    'duplicates': 3,        # Transactions already in database
    'errors': 0,            # Failed imports
    'total_processed': 48   # synced + duplicates
}
```

---

## Database Functions

### Card Operations

```python
# Save/update card
save_connection_card(connection_id, card_id, card_name, card_type, last_four, issuer)

# Get cards for connection
get_connection_cards(connection_id)

# Get card by TrueLayer ID
get_card_by_truelayer_id(card_id)

# Update card sync timestamp
update_card_last_synced(card_id, timestamp)
```

### Card Transaction Operations

```python
# Insert card transaction
insert_truelayer_card_transaction(card_id, transaction_id, normalised_provider_id, ...)

# Get card transactions
get_all_truelayer_card_transactions(card_id=None)

# Check if transaction exists (deduplication)
get_card_transaction_by_id(normalised_provider_id)
```

### Card Balance Operations

```python
# Record balance snapshot
insert_card_balance_snapshot(card_id, current_balance, currency, snapshot_at)

# Get balance history
get_latest_card_balance_snapshots(card_id=None, limit=10)
```

---

## Usage Examples

### Sync all cards for a user

```bash
curl -X POST "http://localhost:5000/api/truelayer/fetch-cards" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'
```

### List all cards

```bash
curl "http://localhost:5000/api/truelayer/cards?user_id=1"
```

### Fetch transactions for a specific card (last 30 days)

```bash
curl -X POST "http://localhost:5000/api/truelayer/fetch-transactions" \
  -H "Content-Type: application/json" \
  -d '{
    "card_id": "card_123",
    "from_date": "2024-10-27",
    "to_date": "2024-11-25"
  }'
```

### Sync both accounts and cards

```bash
# Sync accounts
curl -X POST "http://localhost:5000/api/truelayer/fetch-accounts" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'

# Sync cards
curl -X POST "http://localhost:5000/api/truelayer/fetch-cards" \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'
```

---

## Notes

- All timestamps are in UTC ISO format
- Card transactions sync fetches last 90 days by default (configurable)
- Incremental sync uses connection-level last_synced_at for efficiency
- Deduplication works across multiple sync attempts
- On-demand fetching means transactions are only synced when explicitly requested
- No automatic background syncing (use webhooks for event-driven syncing)

