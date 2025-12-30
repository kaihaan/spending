-- ============================================================================
-- Migration: Enrichment Architecture Refactor
--
-- Creates dedicated tables for rule-based and LLM enrichment results,
-- replacing the metadata['enrichment'] pattern that caused data overwrites.
--
-- Each enrichment source now stores its data independently:
-- - rule_enrichment_results: Category rules, merchant rules, direct debit mappings
-- - llm_enrichment_results: LLM-based categorization
-- - transaction_enrichment_sources: External sources (Amazon, Apple, Gmail) [existing]
-- ============================================================================

-- ============================================================================
-- TABLE 1: Rule Enrichment Results
-- Stores enrichment derived from consistency rules
-- ============================================================================

CREATE TABLE IF NOT EXISTS rule_enrichment_results (
    id SERIAL PRIMARY KEY,
    truelayer_transaction_id INTEGER NOT NULL UNIQUE
        REFERENCES truelayer_transactions(id) ON DELETE CASCADE,

    -- Categorization result
    primary_category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    essential_discretionary VARCHAR(20), -- 'Essential' or 'Discretionary'

    -- Merchant info
    merchant_clean_name VARCHAR(255),
    merchant_type VARCHAR(100),

    -- Rule match metadata
    rule_type VARCHAR(30) NOT NULL, -- 'category_rule', 'merchant_rule', 'direct_debit'
    matched_rule_id INTEGER,        -- FK to category_rules.id (if applicable)
    matched_rule_name VARCHAR(100), -- Denormalized for display
    matched_merchant_id INTEGER,    -- FK to merchant_normalizations.id (if applicable)
    matched_merchant_name VARCHAR(255), -- Denormalized for display

    -- Confidence (rules are deterministic, so always 1.0)
    confidence_score NUMERIC(3,2) NOT NULL DEFAULT 1.00,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT rule_enrichment_rule_type_check
        CHECK (rule_type IN ('category_rule', 'merchant_rule', 'direct_debit')),
    CONSTRAINT rule_enrichment_confidence_check
        CHECK (confidence_score >= 0 AND confidence_score <= 1)
);

-- Indexes for rule_enrichment_results
CREATE INDEX IF NOT EXISTS idx_rule_enrichment_txn
    ON rule_enrichment_results(truelayer_transaction_id);
CREATE INDEX IF NOT EXISTS idx_rule_enrichment_category
    ON rule_enrichment_results(primary_category);
CREATE INDEX IF NOT EXISTS idx_rule_enrichment_type
    ON rule_enrichment_results(rule_type);
CREATE INDEX IF NOT EXISTS idx_rule_enrichment_rule_id
    ON rule_enrichment_results(matched_rule_id) WHERE matched_rule_id IS NOT NULL;

-- ============================================================================
-- TABLE 2: LLM Enrichment Results
-- Stores enrichment derived from LLM inference
-- ============================================================================

CREATE TABLE IF NOT EXISTS llm_enrichment_results (
    id SERIAL PRIMARY KEY,
    truelayer_transaction_id INTEGER NOT NULL UNIQUE
        REFERENCES truelayer_transactions(id) ON DELETE CASCADE,

    -- Categorization result
    primary_category VARCHAR(100) NOT NULL,
    subcategory VARCHAR(100),
    essential_discretionary VARCHAR(20), -- 'Essential' or 'Discretionary'

    -- Merchant info
    merchant_clean_name VARCHAR(255),
    merchant_type VARCHAR(100),

    -- Payment info (LLM can infer these)
    payment_method VARCHAR(50),
    payment_method_subtype VARCHAR(50),
    purchase_date DATE,

    -- LLM metadata
    llm_provider VARCHAR(50) NOT NULL,
    llm_model VARCHAR(100) NOT NULL,
    confidence_score NUMERIC(3,2),

    -- Cache linkage (optional - for deduplication tracking)
    cache_id INTEGER REFERENCES llm_enrichment_cache(id) ON DELETE SET NULL,

    -- Source tracking
    enrichment_source VARCHAR(20) NOT NULL DEFAULT 'llm', -- 'llm' or 'cache'

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    CONSTRAINT llm_enrichment_confidence_check
        CHECK (confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)),
    CONSTRAINT llm_enrichment_source_check
        CHECK (enrichment_source IN ('llm', 'cache'))
);

-- Indexes for llm_enrichment_results
CREATE INDEX IF NOT EXISTS idx_llm_enrichment_txn
    ON llm_enrichment_results(truelayer_transaction_id);
CREATE INDEX IF NOT EXISTS idx_llm_enrichment_category
    ON llm_enrichment_results(primary_category);
CREATE INDEX IF NOT EXISTS idx_llm_enrichment_provider
    ON llm_enrichment_results(llm_provider);
CREATE INDEX IF NOT EXISTS idx_llm_enrichment_cache
    ON llm_enrichment_results(cache_id) WHERE cache_id IS NOT NULL;

-- ============================================================================
-- TRIGGERS: Auto-update timestamps
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_enrichment_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for rule_enrichment_results
DROP TRIGGER IF EXISTS trigger_rule_enrichment_updated ON rule_enrichment_results;
CREATE TRIGGER trigger_rule_enrichment_updated
    BEFORE UPDATE ON rule_enrichment_results
    FOR EACH ROW
    EXECUTE FUNCTION update_enrichment_timestamp();

-- Trigger for llm_enrichment_results
DROP TRIGGER IF EXISTS trigger_llm_enrichment_updated ON llm_enrichment_results;
CREATE TRIGGER trigger_llm_enrichment_updated
    BEFORE UPDATE ON llm_enrichment_results
    FOR EACH ROW
    EXECUTE FUNCTION update_enrichment_timestamp();

-- ============================================================================
-- VIEW: Combined Enrichment (for easy querying)
-- Combines all enrichment sources with priority: Rule > LLM > External
-- ============================================================================

CREATE OR REPLACE VIEW v_transaction_enrichment AS
SELECT
    t.id AS truelayer_transaction_id,
    t.description,
    t.amount,
    t.transaction_type,

    -- Primary category with priority: Rule > LLM > External
    COALESCE(
        r.primary_category,
        l.primary_category,
        (SELECT tes.description
         FROM transaction_enrichment_sources tes
         WHERE tes.truelayer_transaction_id = t.id AND tes.is_primary = TRUE
         LIMIT 1)
    ) AS primary_category,

    -- Subcategory
    COALESCE(r.subcategory, l.subcategory) AS subcategory,

    -- Essential/Discretionary
    COALESCE(r.essential_discretionary, l.essential_discretionary) AS essential_discretionary,

    -- Merchant name
    COALESCE(r.merchant_clean_name, l.merchant_clean_name, t.merchant_name) AS merchant_clean_name,

    -- Source identification
    CASE
        WHEN r.id IS NOT NULL THEN 'rule'
        WHEN l.id IS NOT NULL THEN 'llm'
        WHEN EXISTS (SELECT 1 FROM transaction_enrichment_sources tes
                     WHERE tes.truelayer_transaction_id = t.id) THEN 'external'
        ELSE NULL
    END AS enrichment_source,

    -- Rule details (if applicable)
    r.id AS rule_enrichment_id,
    r.rule_type,
    r.matched_rule_name,
    r.confidence_score AS rule_confidence,

    -- LLM details (if applicable)
    l.id AS llm_enrichment_id,
    l.llm_provider,
    l.llm_model,
    l.confidence_score AS llm_confidence,

    -- External source count
    (SELECT COUNT(*) FROM transaction_enrichment_sources tes
     WHERE tes.truelayer_transaction_id = t.id) AS external_source_count,

    -- Timestamps
    COALESCE(r.updated_at, l.updated_at) AS enrichment_updated_at

FROM truelayer_transactions t
LEFT JOIN rule_enrichment_results r ON r.truelayer_transaction_id = t.id
LEFT JOIN llm_enrichment_results l ON l.truelayer_transaction_id = t.id;

-- ============================================================================
-- DATA MIGRATION: Migrate existing metadata['enrichment'] to new tables
-- This is safe to run multiple times (idempotent)
-- ============================================================================

-- Migrate LLM enrichments (where llm_model indicates LLM source)
INSERT INTO llm_enrichment_results (
    truelayer_transaction_id,
    primary_category,
    subcategory,
    essential_discretionary,
    merchant_clean_name,
    merchant_type,
    payment_method,
    llm_provider,
    llm_model,
    confidence_score,
    enrichment_source,
    created_at
)
SELECT
    t.id,
    t.metadata->'enrichment'->>'primary_category',
    t.metadata->'enrichment'->>'subcategory',
    t.metadata->'enrichment'->>'essential_discretionary',
    t.metadata->'enrichment'->>'merchant_clean_name',
    t.metadata->'enrichment'->>'merchant_type',
    t.metadata->'enrichment'->>'payment_method',
    COALESCE(t.metadata->'enrichment'->>'llm_provider', 'unknown'),
    COALESCE(t.metadata->'enrichment'->>'llm_model', 'unknown'),
    (t.metadata->'enrichment'->>'confidence_score')::NUMERIC(3,2),
    COALESCE(t.metadata->'enrichment'->>'enrichment_source', 'llm'),
    COALESCE((t.metadata->'enrichment'->>'enriched_at')::TIMESTAMPTZ, NOW())
FROM truelayer_transactions t
WHERE t.metadata->'enrichment'->>'primary_category' IS NOT NULL
  AND t.metadata->'enrichment'->>'enrichment_source' IN ('llm', 'cache')
  AND NOT EXISTS (
      SELECT 1 FROM llm_enrichment_results e
      WHERE e.truelayer_transaction_id = t.id
  );

-- Migrate Rule enrichments (where enrichment_source = 'rule')
INSERT INTO rule_enrichment_results (
    truelayer_transaction_id,
    primary_category,
    subcategory,
    essential_discretionary,
    merchant_clean_name,
    merchant_type,
    rule_type,
    matched_rule_name,
    confidence_score,
    created_at
)
SELECT
    t.id,
    t.metadata->'enrichment'->>'primary_category',
    t.metadata->'enrichment'->>'subcategory',
    t.metadata->'enrichment'->>'essential_discretionary',
    t.metadata->'enrichment'->>'merchant_clean_name',
    t.metadata->'enrichment'->>'merchant_type',
    CASE
        WHEN t.metadata->'enrichment'->>'llm_model' = 'direct_debit_rule' THEN 'direct_debit'
        WHEN t.metadata->'enrichment'->>'llm_model' = 'consistency_rule' THEN 'category_rule'
        ELSE 'category_rule'
    END,
    t.metadata->'enrichment'->>'matched_rule',
    COALESCE((t.metadata->'enrichment'->>'confidence_score')::NUMERIC(3,2), 1.00),
    NOW()
FROM truelayer_transactions t
WHERE t.metadata->'enrichment'->>'primary_category' IS NOT NULL
  AND t.metadata->'enrichment'->>'enrichment_source' = 'rule'
  AND NOT EXISTS (
      SELECT 1 FROM rule_enrichment_results e
      WHERE e.truelayer_transaction_id = t.id
  );

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE rule_enrichment_results IS
    'Stores enrichment results from consistency rules (category rules, merchant normalizations, direct debit mappings)';

COMMENT ON TABLE llm_enrichment_results IS
    'Stores enrichment results from LLM inference (Claude, GPT, etc.)';

COMMENT ON VIEW v_transaction_enrichment IS
    'Combined view of all enrichment sources with priority: Rule > LLM > External';

-- ============================================================================
-- Migration complete
-- ============================================================================
