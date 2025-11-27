# TrueLayer Bank Integration Guide

## Overview

TrueLayer integration enables real-time transaction synchronization directly from connected bank accounts. This documentation covers the implementation, configuration, and usage of the TrueLayer integration.

## Architecture

The TrueLayer integration consists of three main components:

### Backend (Python)

#### 1. **truelayer_auth.py** - OAuth 2.0 Authentication
- **Location:** `backend/mcp/truelayer_auth.py`
- **Functions:**
  - `get_authorization_url()` - Generates TrueLayer OAuth URL with PKCE
  - `exchange_code_for_token()` - Exchanges auth code for access token
  - `refresh_access_token()` - Refreshes expired tokens
  - `encrypt_token()` / `decrypt_token()` - Encrypts tokens for storage
  - `save_bank_connection()` - Persists connection data
  - `validate_authorization_state()` - CSRF protection

**Security Features:**
- PKCE (Proof Key for Code Exchange) for OAuth security
- Fernet encryption for token storage
- State validation for CSRF prevention
- Token expiration tracking

#### 2. **truelayer_client.py** - API Client
- **Location:** `backend/mcp/truelayer_client.py`
- **Class:** `TrueLayerClient`
- **Key Methods:**
  - `get_accounts()` - List connected bank accounts
  - `get_account_balance()` - Fetch current account balance
  - `get_transactions()` - Retrieve transactions with date filtering
  - `get_pending_transactions()` - Get pending transactions
  - `normalize_transaction()` - Convert TrueLayer format to app schema
  - `fetch_all_transactions()` - Batch fetch with configurable date range

**Transaction Normalization:**
```python
{
    'date': 'YYYY-MM-DD',
    'description': 'Transaction description',
    'merchant_name': 'Merchant name',
    'amount': float,
    'currency': 'GBP',
    'transaction_type': 'DEBIT|CREDIT',
    'transaction_id': 'ID',
    'normalised_provider_id': 'Provider ID for deduplication',
    'category': 'Optional transaction category',
    'running_balance': float,
    'metadata': {
        'provider_id': 'Bank provider ID',
        'provider_transaction_id': 'Raw transaction ID',
        'meta': {}
    }
}
```

#### 3. **truelayer_sync.py** - Transaction Synchronization
- **Location:** `backend/mcp/truelayer_sync.py`
- **Key Functions:**
  - `sync_account_transactions()` - Sync single account
  - `sync_all_accounts()` - Sync all user accounts
  - `handle_webhook_event()` - Process webhook events
  - `get_sync_status()` - Get sync status for user accounts

**Webhook Event Types:**
- `transactions_available` - New transactions ready to sync
- `balance_updated` - Account balance changed
- Custom event handling framework for future extensions

#### 4. **Database Functions** (database_postgres.py)
- **Location:** `backend/database_postgres.py` (lines 964-1227)

**Bank Connection Management (6 functions):**
- `get_user_connections()` - Get active connections for user
- `get_connection()` - Get specific connection details
- `save_bank_connection()` - Create new connection
- `update_connection_status()` - Update connection status
- `update_connection_last_synced()` - Track sync timestamps
- `update_connection_tokens()` - Refresh tokens after renewal

**Account Management (2 functions):**
- `get_connection_accounts()` - List accounts for connection
- `save_connection_account()` - Store/upsert account with conflict handling

**Transaction Management (3 functions):**
- `get_truelayer_transaction_by_id()` - Deduplication check
- `insert_truelayer_transaction()` - Insert new transaction with error handling
- `get_all_truelayer_transactions()` - Query transactions by account

**Webhook Management (3 functions):**
- `insert_webhook_event()` - Store event for audit trail
- `mark_webhook_processed()` - Track processed events
- `get_webhook_events()` - Query event history

**Balance Tracking (2 functions):**
- `insert_balance_snapshot()` - Store balance snapshot
- `get_latest_balance_snapshots()` - Query balance history

#### 5. **API Routes** (app.py)
- **Location:** `backend/app.py`

**Endpoints:**
```
GET  /api/truelayer/authorize
     - Initiate OAuth flow
     - Returns: auth_url, state, code_verifier

GET  /api/truelayer/callback
     - Handle OAuth callback
     - Params: code, state, code_verifier
     - Returns: status, connection_id

GET  /api/truelayer/accounts
     - Get connected accounts and sync status
     - Returns: connections[], sync_status[]

POST /api/truelayer/sync
     - Trigger manual sync
     - Body: { connection_id: number }
     - Returns: sync result with transaction counts

GET  /api/truelayer/sync/status
     - Get current sync status
     - Returns: sync status for all user accounts

POST /api/truelayer/disconnect
     - Disconnect bank account
     - Body: { connection_id: number }
     - Returns: success status

POST /api/truelayer/webhook
     - Receive webhook events from TrueLayer
     - Body: webhook event payload
     - Returns: event processing result
```

### Frontend (React/TypeScript)

#### 1. **TrueLayerIntegration.tsx** - Main Component
- **Location:** `frontend/src/components/TrueLayerIntegration.tsx`
- **Features:**
  - OAuth connection button with flow initiation
  - Display of connected accounts with status badges
  - Manual sync trigger with loading states
  - Account disconnection with confirmation
  - Sync status overview with timestamps
  - Error handling and user feedback

#### 2. **TrueLayerCallbackHandler.tsx** - OAuth Callback Handler
- **Location:** `frontend/src/components/TrueLayerCallbackHandler.tsx`
- **Features:**
  - OAuth response processing
  - State and code verifier validation
  - Success/error feedback with animations
  - Automatic redirection to settings
  - Session storage for PKCE flow

#### 3. **Integration Points**
- **App.tsx:** Route for `/auth/callback`
- **Settings.tsx:** Added TrueLayerIntegration component
- **Navigation.tsx:** Hidden callback route (not shown in nav)

## Configuration

### Environment Variables
```env
# TrueLayer Configuration
TRUELAYER_CLIENT_ID=your_client_id
TRUELAYER_CLIENT_SECRET=your_client_secret
TRUELAYER_REDIRECT_URI=http://localhost:3000/auth/callback
TRUELAYER_ENVIRONMENT=sandbox  # or 'production'

# Token Encryption
ENCRYPTION_KEY=your_fernet_key
```

### Database Schema
The following tables are required (created by Docker PostgreSQL initialization):

```sql
-- Bank connections
CREATE TABLE truelayer_connections (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL,
    provider_id VARCHAR(255),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP,
    connection_status VARCHAR(50),
    last_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Linked accounts
CREATE TABLE truelayer_accounts (
    id SERIAL PRIMARY KEY,
    connection_id INT NOT NULL,
    account_id VARCHAR(255),
    display_name VARCHAR(255),
    account_type VARCHAR(50),
    account_subtype VARCHAR(50),
    currency VARCHAR(3),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(connection_id, account_id),
    FOREIGN KEY(connection_id) REFERENCES truelayer_connections(id)
);

-- Synced transactions
CREATE TABLE truelayer_transactions (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255),
    transaction_id VARCHAR(255),
    normalised_provider_id VARCHAR(255) UNIQUE,
    timestamp TIMESTAMP,
    description TEXT,
    amount DECIMAL(15, 2),
    currency VARCHAR(3),
    transaction_type VARCHAR(50),
    category VARCHAR(255),
    merchant_name VARCHAR(255),
    running_balance DECIMAL(15, 2),
    metadata TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Webhook events
CREATE TABLE truelayer_webhook_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE,
    event_type VARCHAR(50),
    payload TEXT,
    signature TEXT,
    processed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- Balance snapshots
CREATE TABLE truelayer_balance_snapshots (
    id SERIAL PRIMARY KEY,
    account_id VARCHAR(255),
    current_balance DECIMAL(15, 2),
    currency VARCHAR(3),
    snapshot_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Usage Flow

### 1. User Initiates Connection
1. User navigates to Settings page
2. User clicks "Connect Bank Account" button
3. Frontend calls `GET /api/truelayer/authorize`
4. Backend generates OAuth URL with PKCE challenge
5. Frontend stores state and code_verifier in sessionStorage
6. User is redirected to TrueLayer authorization

### 2. Bank Authorization
1. User logs into their bank on TrueLayer
2. User grants permission to access accounts
3. TrueLayer redirects to frontend callback URL with authorization code

### 3. Token Exchange
1. Frontend processes callback with code and stored verifier
2. Frontend calls `GET /api/truelayer/callback?code=...&state=...`
3. Backend exchanges code for access token using PKCE
4. Backend stores encrypted tokens in database
5. Frontend shows success and redirects to settings

### 4. Transaction Sync
1. User can manually trigger sync via "Sync Now" button
2. Frontend calls `POST /api/truelayer/sync`
3. Backend fetches transactions from TrueLayer API
4. Backend deduplicates using `normalised_provider_id`
5. Backend stores transactions and updates last_synced_at
6. Frontend displays sync results (synced, duplicates, errors)

### 5. Webhook Processing
1. TrueLayer sends webhook on transaction or balance update
2. Backend receives at `POST /api/truelayer/webhook`
3. Backend processes and stores webhook event
4. Backend triggers sync if transactions_available
5. Frontend can be notified via window events

## Error Handling

### Token Expiration
```python
# truelayer_sync.py automatically handles:
# 1. Check token_expires_at before API call
# 2. If expired, call refresh_access_token()
# 3. Update tokens in database
# 4. Retry API call with new token
```

### Duplicate Detection
```python
# Uses normalised_provider_id for deduplication
# Transactions with same normalised_provider_id are skipped
# Prevents duplicate entries during multiple syncs
```

### Transaction Normalization
```python
# Handles different date formats:
# - ISO format: 2024-01-15
# - UK format: 15/01/2024
# - US format: 01/15/2024

# Normalizes merchant names and categories
# Converts amounts to absolute values
# Preserves running balance for reconciliation
```

## Security Considerations

### Token Storage
- All tokens encrypted with Fernet (symmetric encryption)
- Encryption key stored in environment variable
- Encrypted tokens stored in database
- Decrypted only when needed for API calls

### OAuth Flow
- PKCE (RFC 7636) prevents authorization code interception
- State parameter prevents CSRF attacks
- Code verifier stored in session (not transmitted)
- Callback validates state before token exchange

### API Security
- Bearer token authentication
- HTTPS only in production
- Token expiration tracking
- Automatic refresh before expiration

### Data Protection
- Transactions stored securely in PostgreSQL
- User authentication required for access
- Webhook signature verification (optional)
- Audit trail via webhook_events table

## Monitoring & Maintenance

### Sync Status Queries
```python
# Check last sync for user
GET /api/truelayer/sync/status
Returns: {
    'user_id': 123,
    'total_accounts': 2,
    'accounts': [
        {
            'account_id': 'acc_123',
            'display_name': 'Checking Account',
            'last_synced_at': '2024-01-15T10:30:00',
            'connection_status': 'active'
        }
    ]
}
```

### Database Queries
```sql
-- Recent syncs
SELECT * FROM truelayer_connections
ORDER BY last_synced_at DESC
LIMIT 10;

-- Sync statistics
SELECT
    COUNT(*) as total_transactions,
    COUNT(DISTINCT account_id) as accounts,
    MAX(timestamp) as latest_transaction
FROM truelayer_transactions;

-- Webhook history
SELECT * FROM truelayer_webhook_events
WHERE processed = true
ORDER BY processed_at DESC
LIMIT 50;

-- Balance history
SELECT * FROM truelayer_balance_snapshots
WHERE account_id = 'acc_123'
ORDER BY snapshot_at DESC
LIMIT 30;
```

## Testing

### OAuth Flow Testing
1. Start backend: `python app.py`
2. Start frontend: `npm run dev`
3. Navigate to Settings
4. Click "Connect Bank Account"
5. Use TrueLayer sandbox credentials
6. Verify connection appears in account list
7. Click "Sync Now" to fetch transactions

### Webhook Testing (Future)
```python
# Example webhook payload
POST /api/truelayer/webhook
{
    "event_id": "evt_123",
    "event_type": "transactions_available",
    "connection_id": 1,
    "account_id": "acc_123",
    "timestamp": "2024-01-15T10:30:00"
}
```

## Future Enhancements

1. **Automatic Scheduled Syncs** - Background job to sync periodically
2. **Webhook Signature Verification** - Validate webhook authenticity
3. **Transaction Categorization** - Auto-categorize using TrueLayer categories
4. **Balance Reconciliation** - Verify balance matches app balance
5. **Multi-currency Support** - Handle non-GBP accounts
6. **Bank Provider Branding** - Display bank logos in UI
7. **Connection Health Monitoring** - Alert on expired tokens
8. **Sync Rate Limiting** - Prevent excessive API calls

## Troubleshooting

### OAuth Flow Not Starting
- Check TRUELAYER_CLIENT_ID and TRUELAYER_CLIENT_SECRET in .env
- Verify TRUELAYER_REDIRECT_URI matches frontend callback URL
- Check browser console for errors

### Sync Fails with "Invalid Token"
- Token may be expired
- Check token_expires_at in database
- Verify encryption key is set
- Try manually refreshing connection

### Duplicate Transactions
- Check normalised_provider_id field
- Ensure database has UNIQUE constraint
- Clear cache if transactions appear multiple times

### Webhook Not Received
- Verify webhook URL is accessible from internet
- Check firewall/proxy blocking webhooks
- Verify TrueLayer webhook configuration
- Check webhook_events table for failed attempts

## References

- [TrueLayer API Documentation](https://docs.truelayer.com/)
- [OAuth 2.0 with PKCE (RFC 7636)](https://tools.ietf.org/html/rfc7636)
- [Fernet (symmetric encryption)](https://cryptography.io/en/latest/fernet/)
- [PostgreSQL Python Driver (psycopg2)](https://www.psycopg.org/)
