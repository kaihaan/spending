-- ============================================================================
-- Gmail Receipt Integration Schema
-- ============================================================================
-- Integrates Gmail receipts as a transaction enrichment source
-- Following patterns from TrueLayer OAuth and Amazon/Apple matchers

-- ============================================================================
-- GMAIL CONNECTIONS (OAuth Token Storage)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmail_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 1,
    email_address VARCHAR(255) NOT NULL,

    -- OAuth tokens (encrypted with Fernet)
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    token_expires_at TIMESTAMPTZ,
    encryption_version INTEGER DEFAULT 1,    -- For future key rotation
    scopes TEXT,                             -- Granted OAuth scopes

    -- Connection status
    connection_status VARCHAR(20) DEFAULT 'active'
        CHECK(connection_status IN ('active', 'expired', 'revoked', 'error')),

    -- Sync tracking
    history_id VARCHAR(50),                  -- Gmail historyId for incremental sync
    last_synced_at TIMESTAMPTZ,
    sync_from_date DATE,                     -- User-configured start date

    -- Error tracking
    error_count INTEGER DEFAULT 0,
    last_error TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT gmail_connections_user_email_unique UNIQUE (user_id, email_address)
);

CREATE INDEX IF NOT EXISTS idx_gmail_connections_user ON gmail_connections(user_id);
CREATE INDEX IF NOT EXISTS idx_gmail_connections_status ON gmail_connections(connection_status);

-- ============================================================================
-- GMAIL RECEIPTS (Parsed Receipt Data)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmail_receipts (
    id SERIAL PRIMARY KEY,
    connection_id INTEGER NOT NULL REFERENCES gmail_connections(id) ON DELETE CASCADE,

    -- Email identifiers
    message_id VARCHAR(255) UNIQUE NOT NULL,
    thread_id VARCHAR(255),

    -- Sender info
    sender_email VARCHAR(255) NOT NULL,
    sender_name VARCHAR(255),
    subject TEXT,
    received_at TIMESTAMPTZ NOT NULL,

    -- Parsed receipt data
    merchant_name VARCHAR(255),
    merchant_name_normalized VARCHAR(255),   -- Lowercase, cleaned
    merchant_domain VARCHAR(255),
    order_id VARCHAR(255),
    total_amount NUMERIC(12,2),
    currency_code VARCHAR(3) DEFAULT 'GBP',  -- ISO 4217
    receipt_date DATE,

    -- Item details (JSON array)
    line_items JSONB,                        -- [{name, quantity, unit_price, total}]

    -- Deduplication
    receipt_hash VARCHAR(64),                -- SHA256(merchant+amount+date+order_id)

    -- Parsing metadata
    parse_method VARCHAR(30)                 -- NULL for pending, then: schema_org, pattern, llm, manual, vendor_*
        CHECK(parse_method IS NULL OR parse_method IN (
            'schema_org', 'pattern', 'llm', 'manual', 'pending', 'pre_filter', 'unknown', 'generic_pdf', 'none',
            'vendor_apple', 'vendor_amazon', 'vendor_uber', 'vendor_paypal',
            'vendor_trainline', 'vendor_deliveroo', 'vendor_lyft', 'vendor_ebay',
            'vendor_microsoft', 'vendor_google', 'vendor_anthropic', 'vendor_airbnb',
            'vendor_atlassian', 'vendor_atlassian_pdf', 'vendor_charles_tyrwhitt', 'vendor_charles_tyrwhitt_pdf',
            'vendor_google_cloud_pdf', 'vendor_translink_pdf', 'vendor_xero_pdf',
            'vendor_netflix', 'vendor_spotify', 'vendor_ocado', 'vendor_citizens_of_soil', 'vendor_figma',
            'vendor_mindbody', 'vendor_vinted', 'vendor_fastspring'
        )),
    parse_confidence INTEGER NOT NULL        -- 0-100
        CHECK(parse_confidence >= 0 AND parse_confidence <= 100),
    raw_schema_data JSONB,                   -- Original Schema.org JSON
    llm_cost_cents INTEGER,                  -- Track LLM spend

    -- Status tracking
    parsing_status VARCHAR(20) DEFAULT 'pending'
        CHECK(parsing_status IN ('pending', 'parsed', 'failed', 'matched', 'unparseable')),
    parsing_error TEXT,
    retry_count INTEGER DEFAULT 0,

    -- GDPR compliance
    deleted_at TIMESTAMPTZ,                  -- Soft delete

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Performance indices
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_connection ON gmail_receipts(connection_id);
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_connection_date ON gmail_receipts(connection_id, receipt_date);
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_amount_date ON gmail_receipts(total_amount, receipt_date);
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_pending ON gmail_receipts(parsing_status) WHERE parsing_status = 'pending';
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_merchant ON gmail_receipts(merchant_name_normalized);
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_hash ON gmail_receipts(receipt_hash);
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_not_deleted ON gmail_receipts(id) WHERE deleted_at IS NULL;

-- ============================================================================
-- GMAIL TRANSACTION MATCHES (Many-to-Many Links)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmail_transaction_matches (
    id SERIAL PRIMARY KEY,
    truelayer_transaction_id INTEGER NOT NULL REFERENCES truelayer_transactions(id) ON DELETE CASCADE,
    gmail_receipt_id INTEGER NOT NULL REFERENCES gmail_receipts(id) ON DELETE CASCADE,

    -- Match quality
    match_confidence INTEGER NOT NULL        -- 0-100
        CHECK(match_confidence >= 0 AND match_confidence <= 100),
    match_type VARCHAR(20) DEFAULT 'standard'
        CHECK(match_type IN ('standard', 'split_payment', 'bundled_order')),
    match_method VARCHAR(30),                -- amount_date, merchant_amount, fuzzy_merchant

    -- Currency handling
    currency_converted BOOLEAN DEFAULT FALSE,
    conversion_rate NUMERIC(10,6),

    -- User confirmation
    user_confirmed BOOLEAN DEFAULT FALSE,    -- Required for low-confidence matches

    -- Timestamp
    matched_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT gmail_match_unique UNIQUE (truelayer_transaction_id, gmail_receipt_id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_matches_transaction ON gmail_transaction_matches(truelayer_transaction_id);
CREATE INDEX IF NOT EXISTS idx_gmail_matches_receipt ON gmail_transaction_matches(gmail_receipt_id);
CREATE INDEX IF NOT EXISTS idx_gmail_matches_unconfirmed ON gmail_transaction_matches(match_confidence)
    WHERE match_confidence < 80 AND user_confirmed = FALSE;

-- ============================================================================
-- GMAIL MERCHANT ALIASES (Merchant Name Normalization)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmail_merchant_aliases (
    id SERIAL PRIMARY KEY,
    bank_name VARCHAR(255) NOT NULL,         -- Name from bank statement
    receipt_name VARCHAR(255) NOT NULL,      -- Name from email receipt
    normalized_name VARCHAR(255) NOT NULL,   -- Canonical form
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gmail_merchant_aliases_bank ON gmail_merchant_aliases(LOWER(bank_name));
CREATE INDEX IF NOT EXISTS idx_gmail_merchant_aliases_receipt ON gmail_merchant_aliases(LOWER(receipt_name));

-- Seed common merchant aliases
INSERT INTO gmail_merchant_aliases (bank_name, receipt_name, normalized_name) VALUES
('AMAZON.CO.UK', 'Amazon', 'amazon'),
('AMAZON EU', 'Amazon', 'amazon'),
('AMZN MKTP', 'Amazon Marketplace', 'amazon'),
('AMZN*', 'Amazon', 'amazon'),
('PAYPAL *MERCHANT', 'PayPal', 'paypal'),
('PAYPAL *', 'PayPal', 'paypal'),
('UBER* TRIP', 'Uber', 'uber'),
('UBER EATS', 'Uber Eats', 'uber_eats'),
('DELIVEROO', 'Deliveroo', 'deliveroo'),
('JET2.COM', 'Jet2', 'jet2'),
('RYANAIR', 'Ryanair', 'ryanair'),
('TRAINLINE', 'Trainline', 'trainline'),
('BOOKING.COM', 'Booking.com', 'booking'),
('NETFLIX', 'Netflix', 'netflix'),
('SPOTIFY', 'Spotify', 'spotify'),
('APPLE.COM', 'Apple', 'apple'),
('TESCO', 'Tesco', 'tesco'),
('SAINSBURYS', 'Sainsburys', 'sainsburys')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- GMAIL SENDER PATTERNS (Known Receipt Senders)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmail_sender_patterns (
    id SERIAL PRIMARY KEY,
    sender_domain VARCHAR(255) NOT NULL,
    sender_pattern VARCHAR(255),             -- Regex pattern for sender address
    merchant_name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,

    -- Parsing configuration
    parse_type VARCHAR(20) NOT NULL          -- schema_org, pattern, llm
        CHECK(parse_type IN ('schema_org', 'pattern', 'llm')),
    pattern_config JSONB,                    -- Sender-specific regex patterns
    date_tolerance_days INTEGER DEFAULT 7,   -- How many days to search for matches

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gmail_sender_patterns_domain ON gmail_sender_patterns(sender_domain);
CREATE INDEX IF NOT EXISTS idx_gmail_sender_patterns_active ON gmail_sender_patterns(is_active) WHERE is_active = TRUE;

-- Seed known receipt sender patterns
INSERT INTO gmail_sender_patterns (sender_domain, merchant_name, normalized_name, parse_type, date_tolerance_days, pattern_config) VALUES
-- E-commerce
('amazon.co.uk', 'Amazon', 'amazon', 'schema_org', 14, '{"order_id_pattern": "Order #([0-9-]+)"}'),
('amazon.com', 'Amazon', 'amazon', 'schema_org', 14, '{}'),
('ebay.co.uk', 'eBay', 'ebay', 'pattern', 7, '{}'),
('ebay.com', 'eBay', 'ebay', 'pattern', 7, '{}'),
('apple.com', 'Apple', 'apple', 'schema_org', 5, '{}'),
-- Payment providers
('paypal.com', 'PayPal', 'paypal', 'pattern', 3, '{"amount_pattern": "Total\\s*[£$]([\\d,.]+)"}'),
('paypal.co.uk', 'PayPal', 'paypal', 'pattern', 3, '{}'),
-- Food delivery
('uber.com', 'Uber', 'uber', 'schema_org', 3, '{}'),
('deliveroo.com', 'Deliveroo', 'deliveroo', 'pattern', 3, '{}'),
('just-eat.co.uk', 'Just Eat', 'just_eat', 'pattern', 3, '{}'),
-- Travel (booking.com rejected - all marketing emails)
('trainline.com', 'Trainline', 'trainline', 'schema_org', 14, '{}'),
('hotels.com', 'Hotels.com', 'hotels', 'pattern', 30, '{}'),
('jet2.com', 'Jet2', 'jet2', 'pattern', 30, '{}'),
('ryanair.com', 'Ryanair', 'ryanair', 'pattern', 30, '{}'),
('easyjet.com', 'EasyJet', 'easyjet', 'pattern', 30, '{}'),
-- Subscriptions
('netflix.com', 'Netflix', 'netflix', 'pattern', 3, '{}'),
('spotify.com', 'Spotify', 'spotify', 'pattern', 3, '{}'),
('adobe.com', 'Adobe', 'adobe', 'pattern', 3, '{}'),
('microsoft.com', 'Microsoft', 'microsoft', 'schema_org', 3, '{}'),
-- UK Utilities
('britishgas.co.uk', 'British Gas', 'british_gas', 'pattern', 7, '{}'),
('edfenergy.com', 'EDF Energy', 'edf', 'pattern', 7, '{}'),
('thameswater.co.uk', 'Thames Water', 'thames_water', 'pattern', 7, '{}'),
('octopus.energy', 'Octopus Energy', 'octopus', 'pattern', 7, '{}'),
-- UK Supermarkets
('tesco.com', 'Tesco', 'tesco', 'pattern', 3, '{}'),
('sainsburys.co.uk', 'Sainsburys', 'sainsburys', 'pattern', 3, '{}'),
('ocado.com', 'Ocado', 'ocado', 'schema_org', 3, '{}'),
('asda.com', 'Asda', 'asda', 'pattern', 3, '{}'),
-- Additional Travel (sg.booking.com rejected - marketing emails)
('crm.ba.com', 'British Airways', 'british_airways', 'pattern', 14, '{}'),
('translink.co.uk', 'Translink', 'translink', 'pattern', 7, '{}'),
-- Tech & Electronics (bmail.sony-europe.com rejected - marketing emails)
('novationmusic.com', 'Novation Music', 'novation_music', 'pattern', 7, '{}'),
-- Hosting & Web
('account.bluehost.com', 'Bluehost', 'bluehost', 'pattern', 7, '{}'),
('post.xero.com', 'Xero', 'xero', 'pattern', 7, '{}'),
-- Retail
('ctshirts.com', 'Charles Tyrwhitt', 'charles_tyrwhitt', 'pattern', 7, '{}'),
('designacable.com', 'Designacable', 'designacable', 'pattern', 7, '{}'),
('mattbcustoms.com', 'MattB Customs', 'mattbcustoms', 'pattern', 7, '{}'),
('citizensofsoil.com', 'Citizens of Soil', 'citizensofsoil', 'pattern', 7, '{}'),
('leavetheherdbehind.com', 'Leave The Herd Behind', 'leavetheherdbehind', 'pattern', 7, '{}')
ON CONFLICT DO NOTHING;

-- ============================================================================
-- GMAIL SYNC JOBS (Async Job Tracking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmail_sync_jobs (
    id SERIAL PRIMARY KEY,
    connection_id INTEGER NOT NULL REFERENCES gmail_connections(id) ON DELETE CASCADE,

    -- Job status
    status VARCHAR(20) DEFAULT 'queued'
        CHECK(status IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    job_type VARCHAR(20) DEFAULT 'full'
        CHECK(job_type IN ('full', 'incremental')),

    -- Progress tracking
    total_messages INTEGER DEFAULT 0,
    processed_messages INTEGER DEFAULT 0,
    parsed_receipts INTEGER DEFAULT 0,
    failed_messages INTEGER DEFAULT 0,

    -- Error handling
    error_message TEXT,

    -- Timestamps
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gmail_sync_jobs_connection ON gmail_sync_jobs(connection_id);
CREATE INDEX IF NOT EXISTS idx_gmail_sync_jobs_status ON gmail_sync_jobs(status) WHERE status IN ('queued', 'running');

-- ============================================================================
-- OAUTH STATE (Temporary - for CSRF prevention)
-- ============================================================================
-- Note: If oauth_state table doesn't exist, create it here
-- This table stores temporary OAuth state for CSRF protection

CREATE TABLE IF NOT EXISTS gmail_oauth_state (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    state VARCHAR(255) UNIQUE NOT NULL,
    code_verifier VARCHAR(255) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gmail_oauth_state_state ON gmail_oauth_state(state);
CREATE INDEX IF NOT EXISTS idx_gmail_oauth_state_expires ON gmail_oauth_state(expires_at);

-- Cleanup function for expired OAuth states (run periodically)
-- DELETE FROM gmail_oauth_state WHERE expires_at < NOW();
