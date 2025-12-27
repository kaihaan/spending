-- ============================================================================
-- Fix Gmail Parsing Status Bug
-- ============================================================================
-- Problem: parsing_status was being used to track TWO independent dimensions:
--   1. Parsing outcome (did we extract data successfully?)
--   2. Match status (is it linked to a bank transaction?)
--
-- This caused parsed totals to decrease when receipts were matched, because
-- parsing_status changed from 'parsed' to 'matched'.
--
-- Solution: Remove 'matched' from parsing_status values. Matching state is
-- already tracked independently in the gmail_transaction_matches table.
-- ============================================================================

-- Step 1: Remove 'matched' from the CHECK constraint
-- This allows only: 'pending', 'parsed', 'failed', 'unparseable'
ALTER TABLE gmail_receipts
DROP CONSTRAINT IF EXISTS gmail_receipts_parsing_status_check;

ALTER TABLE gmail_receipts
ADD CONSTRAINT gmail_receipts_parsing_status_check
CHECK(parsing_status IN ('pending', 'parsed', 'failed', 'unparseable'));

-- Step 2: Migrate existing data - change 'matched' back to 'parsed'
-- These receipts were successfully parsed, so they should remain in parsed status
-- Their match status is preserved in the gmail_transaction_matches table
UPDATE gmail_receipts
SET parsing_status = 'parsed', updated_at = NOW()
WHERE parsing_status = 'matched';

-- Step 3: Add performance index for parsed receipts
-- This improves query performance when filtering by parsing_status = 'parsed'
CREATE INDEX IF NOT EXISTS idx_gmail_receipts_parsed
ON gmail_receipts(parsing_status)
WHERE parsing_status = 'parsed';

-- Step 4: Verify migration results
DO $$
DECLARE
    migrated_count INTEGER;
    remaining_matched INTEGER;
BEGIN
    -- Count how many receipts were migrated
    GET DIAGNOSTICS migrated_count = ROW_COUNT;

    -- Verify no 'matched' status remains
    SELECT COUNT(*) INTO remaining_matched
    FROM gmail_receipts
    WHERE parsing_status = 'matched';

    -- Log results
    RAISE NOTICE 'Migration complete:';
    RAISE NOTICE '  - Receipts migrated from matched to parsed: %', migrated_count;
    RAISE NOTICE '  - Remaining receipts with matched status: %', remaining_matched;

    IF remaining_matched > 0 THEN
        RAISE WARNING 'Migration incomplete: % receipts still have matched status', remaining_matched;
    END IF;
END $$;
