-- Migration: Multi-Source Enrichment Architecture
-- Stores all enrichment sources separately instead of overwriting lookup_description
-- Preserves Amazon, Apple, Gmail, and manual enrichment data

-- ============================================================================
-- PHASE 1: Create New Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS transaction_enrichment_sources (
    id SERIAL PRIMARY KEY,
    truelayer_transaction_id INTEGER NOT NULL REFERENCES truelayer_transactions(id) ON DELETE CASCADE,

    -- Source identification
    source_type VARCHAR(20) NOT NULL CHECK(source_type IN ('amazon', 'amazon_business', 'apple', 'gmail', 'manual')),
    source_id INTEGER,  -- FK to source table (amazon_orders.id, apple_transactions.id, gmail_receipts.id)

    -- Enrichment content
    description TEXT NOT NULL,          -- Product/service description from source
    order_id VARCHAR(100),              -- Original order/receipt ID
    line_items JSONB,                   -- Detailed items [{name, quantity, price}]

    -- Match metadata
    match_confidence INTEGER NOT NULL DEFAULT 100 CHECK(match_confidence >= 0 AND match_confidence <= 100),
    match_method VARCHAR(50),           -- How the match was determined

    -- User control
    is_primary BOOLEAN DEFAULT FALSE,   -- User-selected primary source for display
    user_verified BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Ensure unique source per transaction (same source can't be added twice)
    CONSTRAINT enrichment_source_unique UNIQUE (truelayer_transaction_id, source_type, source_id)
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_enrichment_sources_txn ON transaction_enrichment_sources(truelayer_transaction_id);
CREATE INDEX IF NOT EXISTS idx_enrichment_sources_type ON transaction_enrichment_sources(source_type);
CREATE INDEX IF NOT EXISTS idx_enrichment_sources_primary ON transaction_enrichment_sources(truelayer_transaction_id) WHERE is_primary = TRUE;

-- ============================================================================
-- PHASE 2: Migrate Existing Amazon Matches
-- ============================================================================

INSERT INTO transaction_enrichment_sources
    (truelayer_transaction_id, source_type, source_id, description, order_id, match_confidence, match_method, is_primary)
SELECT
    tam.truelayer_transaction_id,
    'amazon',
    tam.amazon_order_id,
    ao.product_names,
    ao.order_id,
    COALESCE(tam.match_confidence, 100)::INTEGER,
    'amount_date_match',
    TRUE  -- Amazon is primary by default (has product names)
FROM truelayer_amazon_transaction_matches tam
JOIN amazon_orders ao ON ao.id = tam.amazon_order_id
WHERE ao.product_names IS NOT NULL AND ao.product_names != ''
ON CONFLICT (truelayer_transaction_id, source_type, source_id) DO NOTHING;

-- ============================================================================
-- PHASE 3: Migrate Existing Amazon Business Matches
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'truelayer_amazon_business_matches') THEN
        INSERT INTO transaction_enrichment_sources
            (truelayer_transaction_id, source_type, source_id, description, order_id, match_confidence, match_method, is_primary)
        SELECT
            tabm.truelayer_transaction_id,
            'amazon_business',
            tabm.amazon_business_order_id,
            abo.product_summary,
            abo.order_id,
            COALESCE(tabm.match_confidence, 100)::INTEGER,
            'amount_date_match',
            -- Only primary if no regular Amazon match exists
            NOT EXISTS (
                SELECT 1 FROM transaction_enrichment_sources tes
                WHERE tes.truelayer_transaction_id = tabm.truelayer_transaction_id
                AND tes.source_type = 'amazon'
            )
        FROM truelayer_amazon_business_matches tabm
        JOIN amazon_business_orders abo ON abo.id = tabm.amazon_business_order_id
        WHERE abo.product_summary IS NOT NULL AND abo.product_summary != ''
        ON CONFLICT (truelayer_transaction_id, source_type, source_id) DO NOTHING;
    END IF;
END $$;

-- ============================================================================
-- PHASE 4: Migrate Existing Apple Matches
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'truelayer_apple_transaction_matches') THEN
        INSERT INTO transaction_enrichment_sources
            (truelayer_transaction_id, source_type, source_id, description, order_id, match_confidence, match_method, is_primary)
        SELECT
            tapm.truelayer_transaction_id,
            'apple',
            tapm.apple_transaction_id,
            at.app_names || COALESCE(' (' || at.publishers || ')', ''),
            at.order_id,
            COALESCE(tapm.match_confidence, 100)::INTEGER,
            'amount_date_match',
            -- Only primary if no Amazon match exists
            NOT EXISTS (
                SELECT 1 FROM transaction_enrichment_sources tes
                WHERE tes.truelayer_transaction_id = tapm.truelayer_transaction_id
                AND tes.source_type IN ('amazon', 'amazon_business')
            )
        FROM truelayer_apple_transaction_matches tapm
        JOIN apple_transactions at ON at.id = tapm.apple_transaction_id
        WHERE at.app_names IS NOT NULL AND at.app_names != ''
        ON CONFLICT (truelayer_transaction_id, source_type, source_id) DO NOTHING;
    END IF;
END $$;

-- ============================================================================
-- PHASE 5: Migrate Existing Gmail Matches
-- ============================================================================

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'gmail_transaction_matches') THEN
        INSERT INTO transaction_enrichment_sources
            (truelayer_transaction_id, source_type, source_id, description, order_id, line_items, match_confidence, match_method, is_primary)
        SELECT
            gtm.truelayer_transaction_id,
            'gmail',
            gtm.gmail_receipt_id,
            -- Build description from merchant + line items or order ID
            COALESCE(gr.merchant_name, 'Receipt') || ': ' ||
                COALESCE(
                    (SELECT string_agg(item->>'name', ', ')
                     FROM jsonb_array_elements(gr.line_items) item
                     WHERE item->>'name' IS NOT NULL
                     LIMIT 3),
                    'Order #' || COALESCE(gr.order_id, 'unknown')
                ),
            gr.order_id,
            gr.line_items,
            COALESCE(gtm.match_confidence, 80)::INTEGER,
            COALESCE(gtm.match_method, 'amount_date_match'),
            -- Only primary if no other sources exist
            NOT EXISTS (
                SELECT 1 FROM transaction_enrichment_sources tes
                WHERE tes.truelayer_transaction_id = gtm.truelayer_transaction_id
            )
        FROM gmail_transaction_matches gtm
        JOIN gmail_receipts gr ON gr.id = gtm.gmail_receipt_id
        ON CONFLICT (truelayer_transaction_id, source_type, source_id) DO NOTHING;
    END IF;
END $$;

-- ============================================================================
-- PHASE 6: Update Trigger for timestamps
-- ============================================================================

CREATE OR REPLACE FUNCTION update_enrichment_source_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_enrichment_source_updated ON transaction_enrichment_sources;
CREATE TRIGGER trigger_enrichment_source_updated
    BEFORE UPDATE ON transaction_enrichment_sources
    FOR EACH ROW
    EXECUTE FUNCTION update_enrichment_source_timestamp();

-- ============================================================================
-- PHASE 7: Helper function to ensure only one primary per transaction
-- ============================================================================

CREATE OR REPLACE FUNCTION ensure_single_primary_enrichment()
RETURNS TRIGGER AS $$
BEGIN
    -- If setting this source as primary, unset others for same transaction
    IF NEW.is_primary = TRUE THEN
        UPDATE transaction_enrichment_sources
        SET is_primary = FALSE
        WHERE truelayer_transaction_id = NEW.truelayer_transaction_id
          AND id != NEW.id
          AND is_primary = TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_single_primary_enrichment ON transaction_enrichment_sources;
CREATE TRIGGER trigger_single_primary_enrichment
    BEFORE INSERT OR UPDATE OF is_primary ON transaction_enrichment_sources
    FOR EACH ROW
    WHEN (NEW.is_primary = TRUE)
    EXECUTE FUNCTION ensure_single_primary_enrichment();
