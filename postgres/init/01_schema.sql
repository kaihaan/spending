-- ============================================================================
-- PostgreSQL Schema for Personal Finance Tracker + TrueLayer Integration
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- EXISTING TABLES (Migrated from SQLite)
-- ============================================================================

-- Core Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,  -- Negative for expenses, positive for income
    category VARCHAR(100) DEFAULT 'Other',
    source_file VARCHAR(255),
    merchant VARCHAR(255),
    huququllah_classification VARCHAR(20) CHECK(huququllah_classification IN ('essential', 'discretionary')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Categories Table
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    rule_pattern TEXT,
    ai_suggested BOOLEAN DEFAULT FALSE
);

-- Category Keywords Table
CREATE TABLE IF NOT EXISTS category_keywords (
    id SERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(category_name, keyword)
);

-- Account Mappings Table
CREATE TABLE IF NOT EXISTS account_mappings (
    id SERIAL PRIMARY KEY,
    sort_code VARCHAR(10) NOT NULL,
    account_number VARCHAR(20) NOT NULL,
    friendly_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(sort_code, account_number)
);

-- Amazon Orders Table
CREATE TABLE IF NOT EXISTS amazon_orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(100) UNIQUE NOT NULL,
    order_date DATE NOT NULL,
    website VARCHAR(100) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    total_owed NUMERIC(12,2) NOT NULL,
    product_names TEXT NOT NULL,
    order_status VARCHAR(50),
    shipment_status VARCHAR(50),
    source_file VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Amazon Transaction Matches Table
CREATE TABLE IF NOT EXISTS amazon_transaction_matches (
    id SERIAL PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    amazon_order_id INTEGER NOT NULL REFERENCES amazon_orders(id) ON DELETE CASCADE,
    match_confidence NUMERIC(5,2) NOT NULL,
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(transaction_id)
);

-- Amazon Returns Table
CREATE TABLE IF NOT EXISTS amazon_returns (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(100) NOT NULL,
    reversal_id VARCHAR(100) UNIQUE NOT NULL,
    refund_completion_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL,
    amount_refunded NUMERIC(12,2) NOT NULL,
    status VARCHAR(50),
    disbursement_type VARCHAR(50),
    source_file VARCHAR(255),
    original_transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    refund_transaction_id INTEGER REFERENCES transactions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Apple Transactions Table
CREATE TABLE IF NOT EXISTS apple_transactions (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(100) UNIQUE NOT NULL,
    order_date DATE NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    app_names TEXT NOT NULL,
    publishers TEXT,
    item_count INTEGER DEFAULT 1,
    source_file VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Apple Transaction Matches Table
CREATE TABLE IF NOT EXISTS apple_transaction_matches (
    id SERIAL PRIMARY KEY,
    apple_transaction_id INTEGER NOT NULL REFERENCES apple_transactions(id) ON DELETE CASCADE,
    bank_transaction_id INTEGER NOT NULL REFERENCES transactions(id) ON DELETE CASCADE,
    confidence INTEGER NOT NULL,
    matched_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bank_transaction_id)
);

-- ============================================================================
-- NEW TABLES (TrueLayer Integration)
-- ============================================================================

-- Users Table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Bank Connections Table (OAuth & Token Management)
CREATE TABLE IF NOT EXISTS bank_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id VARCHAR(100) NOT NULL,  -- e.g., "ob-natwest", "ob-hsbc"
    provider_name VARCHAR(255) NOT NULL,
    access_token TEXT,  -- Encrypted in application layer
    refresh_token TEXT,  -- Encrypted in application layer
    token_expires_at TIMESTAMPTZ,
    refresh_token_expires_at TIMESTAMPTZ,
    connection_status VARCHAR(20) CHECK(connection_status IN ('active', 'expired', 'inactive', 'authorization_required')) DEFAULT 'authorization_required',
    last_synced_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, provider_id)
);

-- TrueLayer Accounts Table
CREATE TABLE IF NOT EXISTS truelayer_accounts (
    id SERIAL PRIMARY KEY,
    connection_id INTEGER NOT NULL REFERENCES bank_connections(id) ON DELETE CASCADE,
    account_id VARCHAR(255) UNIQUE NOT NULL,  -- TrueLayer's account_id
    account_type VARCHAR(50) NOT NULL,  -- TRANSACTION, SAVINGS, BUSINESS_TRANSACTION, BUSINESS_SAVINGS
    display_name VARCHAR(255) NOT NULL,
    currency VARCHAR(3) NOT NULL,
    account_number_json JSONB,  -- Stores IBAN, sort_code, number, SWIFT BIC, etc.
    provider_data JSONB,  -- Additional provider-specific metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- TrueLayer Transactions Table
CREATE TABLE IF NOT EXISTS truelayer_transactions (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES truelayer_accounts(id) ON DELETE CASCADE,
    transaction_id VARCHAR(255) NOT NULL,  -- TrueLayer's transaction_id
    normalised_provider_transaction_id VARCHAR(255) UNIQUE NOT NULL,  -- Recommended unique ID
    timestamp TIMESTAMPTZ NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,  -- Positive = incoming, Negative = outgoing
    currency VARCHAR(3) NOT NULL,
    transaction_type VARCHAR(20) CHECK(transaction_type IN ('CREDIT', 'DEBIT')) NOT NULL,
    transaction_category VARCHAR(50),  -- ATM, PURCHASE, DIRECT_DEBIT, STANDING_ORDER, TRANSFER, etc.
    merchant_name VARCHAR(255),
    running_balance NUMERIC(12,2),
    metadata JSONB,  -- Full transaction metadata from TrueLayer
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- TrueLayer Balance History Table
CREATE TABLE IF NOT EXISTS truelayer_balances (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES truelayer_accounts(id) ON DELETE CASCADE,
    current_balance NUMERIC(12,2) NOT NULL,
    available_balance NUMERIC(12,2),
    overdraft NUMERIC(12,2),
    currency VARCHAR(3) NOT NULL,
    snapshot_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Webhook Events Table
CREATE TABLE IF NOT EXISTS webhook_events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,  -- TrueLayer's event_id for deduplication
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    signature TEXT NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ DEFAULT NOW()
);

-- Connection Logs Table (Audit Trail)
CREATE TABLE IF NOT EXISTS connection_logs (
    id SERIAL PRIMARY KEY,
    connection_id INTEGER REFERENCES bank_connections(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,  -- token_refresh, sync_start, sync_complete, error, etc.
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- INDEXES
-- ============================================================================

-- Existing Tables Indexes
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_merchant ON transactions(merchant);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_transactions_source_file ON transactions(source_file);
CREATE INDEX IF NOT EXISTS idx_transactions_amount ON transactions(amount);

CREATE INDEX IF NOT EXISTS idx_category_keywords_category ON category_keywords(category_name);

CREATE INDEX IF NOT EXISTS idx_amazon_orders_date ON amazon_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_amazon_orders_website ON amazon_orders(website);

CREATE INDEX IF NOT EXISTS idx_apple_transactions_date ON apple_transactions(order_date);

-- TrueLayer Tables Indexes
CREATE INDEX IF NOT EXISTS idx_bank_connections_user_id ON bank_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_bank_connections_status ON bank_connections(connection_status);
CREATE INDEX IF NOT EXISTS idx_bank_connections_user_status ON bank_connections(user_id, connection_status);

CREATE INDEX IF NOT EXISTS idx_truelayer_accounts_connection_id ON truelayer_accounts(connection_id);
CREATE INDEX IF NOT EXISTS idx_truelayer_accounts_account_id ON truelayer_accounts(account_id);

CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_account_id ON truelayer_transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_timestamp ON truelayer_transactions(timestamp);
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_merchant ON truelayer_transactions(merchant_name);
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_category ON truelayer_transactions(transaction_category);

-- JSONB GIN Indexes for flexible queries
CREATE INDEX IF NOT EXISTS idx_truelayer_accounts_account_number_gin ON truelayer_accounts USING GIN (account_number_json);
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_metadata_gin ON truelayer_transactions USING GIN (metadata);

CREATE INDEX IF NOT EXISTS idx_truelayer_balances_account_id ON truelayer_balances(account_id);
CREATE INDEX IF NOT EXISTS idx_truelayer_balances_snapshot_at ON truelayer_balances(snapshot_at);

-- Partial index for unprocessed webhooks (performance optimization)
CREATE INDEX IF NOT EXISTS idx_webhook_events_unprocessed ON webhook_events(received_at) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_webhook_events_event_id ON webhook_events(event_id);

CREATE INDEX IF NOT EXISTS idx_connection_logs_connection_id ON connection_logs(connection_id);
CREATE INDEX IF NOT EXISTS idx_connection_logs_created_at ON connection_logs(created_at);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_bank_connections_updated_at BEFORE UPDATE ON bank_connections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_truelayer_accounts_updated_at BEFORE UPDATE ON truelayer_accounts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- COMMENTS (Documentation)
-- ============================================================================

COMMENT ON TABLE transactions IS 'Bank transactions imported from Santander Excel statements';
COMMENT ON TABLE truelayer_transactions IS 'Transactions synced from TrueLayer Data API';
COMMENT ON TABLE bank_connections IS 'OAuth connections to banks via TrueLayer';
COMMENT ON TABLE webhook_events IS 'TrueLayer webhook events for asynchronous processing';

COMMENT ON COLUMN bank_connections.access_token IS 'Encrypted OAuth access token (1-hour lifetime)';
COMMENT ON COLUMN bank_connections.refresh_token IS 'Encrypted OAuth refresh token (90-day lifetime)';
COMMENT ON COLUMN truelayer_transactions.normalised_provider_transaction_id IS 'Recommended unique ID for transaction identification across API calls';
