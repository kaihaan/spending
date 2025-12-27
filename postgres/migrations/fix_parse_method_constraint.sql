-- Fix parse_method constraint to allow 'pending' for unparsed receipts
-- Run against spending_db
--
-- Root cause: gmail_sync.py sets parse_method = 'pending' for new receipts,
-- but the CHECK constraint only allowed 'schema_org', 'pattern', 'llm', 'manual'

BEGIN;

-- Drop existing constraint
ALTER TABLE gmail_receipts
DROP CONSTRAINT IF EXISTS gmail_receipts_parse_method_check;

-- Make column nullable (unparsed receipts don't have a parse method yet)
ALTER TABLE gmail_receipts
ALTER COLUMN parse_method DROP NOT NULL;

-- Add updated constraint allowing NULL and 'pending'
ALTER TABLE gmail_receipts
ADD CONSTRAINT gmail_receipts_parse_method_check
CHECK(parse_method IS NULL OR parse_method IN (
    'schema_org', 'pattern', 'llm', 'manual', 'pending',
    'vendor_apple', 'vendor_amazon', 'vendor_uber',
    'vendor_paypal', 'vendor_trainline', 'vendor_deliveroo'
));

COMMIT;
