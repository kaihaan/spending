-- ============================================================================
-- Enrichment Required Column
-- ============================================================================
-- Adds a column to track which transactions need LLM enrichment.
-- Users can toggle this flag to queue/dequeue transactions for enrichment.

-- Add the enrichment_required column
ALTER TABLE truelayer_transactions
ADD COLUMN IF NOT EXISTS enrichment_required BOOLEAN DEFAULT TRUE;

-- Create index for faster filtering of required transactions
CREATE INDEX IF NOT EXISTS idx_truelayer_enrichment_required
ON truelayer_transactions(enrichment_required)
WHERE enrichment_required = TRUE;

-- Backfill: Set FALSE for already-enriched transactions, TRUE for unenriched
UPDATE truelayer_transactions
SET enrichment_required = CASE
    WHEN metadata->'enrichment' IS NOT NULL THEN FALSE
    ELSE TRUE
END
WHERE enrichment_required IS NULL OR enrichment_required = TRUE;

-- Add comment for documentation
COMMENT ON COLUMN truelayer_transactions.enrichment_required IS
'Flag indicating if transaction needs LLM enrichment. TRUE = needs enrichment, FALSE = skip. Users can toggle via UI.';
