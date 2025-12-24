-- Migration: Category Normalization
-- Normalizes categories and subcategories into dedicated tables with FK relationships
-- Adds descriptions for LLM enrichment context

-- ============================================================================
-- PHASE 1: Create New Tables
-- ============================================================================

-- Normalized categories table (replaces inline VARCHAR storage)
CREATE TABLE IF NOT EXISTS normalized_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,                    -- For LLM enrichment context
    is_system BOOLEAN DEFAULT FALSE,     -- TRUE for BASE_CATEGORIES (cannot be deleted)
    is_active BOOLEAN DEFAULT TRUE,      -- FALSE = hidden from LLM prompts
    is_essential BOOLEAN DEFAULT FALSE,  -- TRUE = Essential for Huququllah
    display_order INTEGER DEFAULT 0,
    color VARCHAR(30),                   -- Badge color class (e.g., 'badge-success')
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Normalized subcategories table (FK to categories)
CREATE TABLE IF NOT EXISTS normalized_subcategories (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES normalized_categories(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,                    -- For LLM enrichment context
    is_active BOOLEAN DEFAULT TRUE,
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(category_id, name)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_normalized_categories_active ON normalized_categories(is_active);
CREATE INDEX IF NOT EXISTS idx_normalized_categories_system ON normalized_categories(is_system);
CREATE INDEX IF NOT EXISTS idx_normalized_categories_name ON normalized_categories(name);
CREATE INDEX IF NOT EXISTS idx_normalized_subcategories_category ON normalized_subcategories(category_id);
CREATE INDEX IF NOT EXISTS idx_normalized_subcategories_name ON normalized_subcategories(name);

-- ============================================================================
-- PHASE 2: Seed System Categories (BASE_CATEGORIES)
-- ============================================================================

INSERT INTO normalized_categories (name, is_system, is_essential, description, display_order, color) VALUES
    ('Groceries', TRUE, TRUE, 'Food and household essentials from supermarkets and grocery stores', 1, 'badge-success'),
    ('Transportation', TRUE, TRUE, 'Public transport, fuel, taxis, rideshare services', 2, 'badge-info'),
    ('Clothing', TRUE, FALSE, 'Apparel, footwear, and fashion accessories', 3, 'badge-secondary'),
    ('Dining', TRUE, FALSE, 'Restaurants, cafes, takeaway, food delivery services', 4, 'badge-warning'),
    ('Entertainment', TRUE, FALSE, 'Movies, concerts, streaming services, games, hobbies', 5, 'badge-primary'),
    ('Shopping', TRUE, FALSE, 'General retail purchases, online marketplaces', 6, 'badge-accent'),
    ('Healthcare', TRUE, TRUE, 'Medical expenses, pharmacy, dental, health services', 7, 'badge-error'),
    ('Utilities', TRUE, TRUE, 'Gas, electricity, water, internet, phone bills', 8, 'badge-info'),
    ('Income', TRUE, FALSE, 'Salary, wages, payments received, refunds', 9, 'badge-success'),
    ('Taxes', TRUE, TRUE, 'Income tax, council tax, national insurance, VAT', 10, 'badge-neutral'),
    ('Subscriptions', TRUE, FALSE, 'Recurring digital and physical subscription services', 11, 'badge-primary'),
    ('Insurance', TRUE, TRUE, 'Home, car, health, life, travel insurance premiums', 12, 'badge-neutral'),
    ('Education', TRUE, TRUE, 'School fees, courses, training, educational materials', 13, 'badge-info'),
    ('Travel', TRUE, FALSE, 'Flights, hotels, holiday expenses, travel bookings', 14, 'badge-accent'),
    ('Personal Care', TRUE, FALSE, 'Haircuts, cosmetics, grooming, spa, wellness', 15, 'badge-secondary'),
    ('Gifts', TRUE, FALSE, 'Presents, charitable donations, gift cards', 16, 'badge-primary'),
    ('Pet Care', TRUE, FALSE, 'Pet food, veterinary services, pet supplies', 17, 'badge-warning'),
    ('Home & Garden', TRUE, FALSE, 'Furniture, home decor, gardening, DIY supplies', 18, 'badge-accent'),
    ('Electronics', TRUE, FALSE, 'Computers, phones, gadgets, tech accessories', 19, 'badge-info'),
    ('Sports & Outdoors', TRUE, FALSE, 'Gym memberships, sports equipment, outdoor activities', 20, 'badge-success'),
    ('Books & Media', TRUE, FALSE, 'Books, magazines, music, digital media purchases', 21, 'badge-secondary'),
    ('Office Supplies', TRUE, FALSE, 'Stationery, office equipment, work supplies', 22, 'badge-neutral'),
    ('Automotive', TRUE, FALSE, 'Car maintenance, repairs, MOT, car accessories', 23, 'badge-warning'),
    ('Banking Fees', TRUE, TRUE, 'Account fees, overdraft charges, interest payments', 24, 'badge-error'),
    ('Other', TRUE, FALSE, 'Miscellaneous and uncategorized transactions', 25, 'badge-ghost')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- PHASE 3: Add FK Columns to Existing Tables
-- ============================================================================

-- Add category_id and subcategory_id to truelayer_transactions
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'truelayer_transactions' AND column_name = 'category_id'
    ) THEN
        ALTER TABLE truelayer_transactions
            ADD COLUMN category_id INTEGER REFERENCES normalized_categories(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'truelayer_transactions' AND column_name = 'subcategory_id'
    ) THEN
        ALTER TABLE truelayer_transactions
            ADD COLUMN subcategory_id INTEGER REFERENCES normalized_subcategories(id);
    END IF;
END $$;

-- Add category_id and subcategory_id to category_rules
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'category_rules' AND column_name = 'category_id'
    ) THEN
        ALTER TABLE category_rules
            ADD COLUMN category_id INTEGER REFERENCES normalized_categories(id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'category_rules' AND column_name = 'subcategory_id'
    ) THEN
        ALTER TABLE category_rules
            ADD COLUMN subcategory_id INTEGER REFERENCES normalized_subcategories(id);
    END IF;
END $$;

-- Indexes for FK columns
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_category_id ON truelayer_transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_truelayer_transactions_subcategory_id ON truelayer_transactions(subcategory_id);
CREATE INDEX IF NOT EXISTS idx_category_rules_category_id ON category_rules(category_id);
CREATE INDEX IF NOT EXISTS idx_category_rules_subcategory_id ON category_rules(subcategory_id);

-- ============================================================================
-- PHASE 4: Data Migration - Populate category_id from transaction_category
-- ============================================================================

-- Link existing transactions to normalized categories
UPDATE truelayer_transactions t
SET category_id = nc.id
FROM normalized_categories nc
WHERE t.transaction_category = nc.name
  AND t.category_id IS NULL;

-- Also check metadata enrichment primary_category for any that don't have transaction_category
UPDATE truelayer_transactions t
SET category_id = nc.id
FROM normalized_categories nc
WHERE t.metadata->'enrichment'->>'primary_category' = nc.name
  AND t.category_id IS NULL
  AND t.transaction_category IS NULL;

-- ============================================================================
-- PHASE 5: Extract and Normalize Subcategories from JSONB Metadata
-- ============================================================================

-- Insert unique subcategories grouped by their parent category
INSERT INTO normalized_subcategories (category_id, name)
SELECT DISTINCT nc.id, t.metadata->'enrichment'->>'subcategory'
FROM truelayer_transactions t
JOIN normalized_categories nc ON t.category_id = nc.id
WHERE t.metadata->'enrichment'->>'subcategory' IS NOT NULL
  AND t.metadata->'enrichment'->>'subcategory' != ''
  AND t.metadata->'enrichment'->>'subcategory' != 'null'
ON CONFLICT (category_id, name) DO NOTHING;

-- Link transactions to normalized subcategories
UPDATE truelayer_transactions t
SET subcategory_id = ns.id
FROM normalized_subcategories ns
WHERE t.category_id = ns.category_id
  AND t.metadata->'enrichment'->>'subcategory' = ns.name
  AND t.subcategory_id IS NULL;

-- ============================================================================
-- PHASE 6: Migrate category_rules to use FK
-- ============================================================================

-- Link category_rules to normalized_categories
UPDATE category_rules cr
SET category_id = nc.id
FROM normalized_categories nc
WHERE cr.category = nc.name
  AND cr.category_id IS NULL;

-- Link category_rules subcategories
UPDATE category_rules cr
SET subcategory_id = ns.id
FROM normalized_subcategories ns
JOIN normalized_categories nc ON ns.category_id = nc.id
WHERE cr.category = nc.name
  AND cr.subcategory = ns.name
  AND cr.subcategory_id IS NULL;

-- ============================================================================
-- PHASE 7: Migrate custom_categories (promoted/hidden) status
-- ============================================================================

-- Mark categories from custom_categories table as hidden if applicable
UPDATE normalized_categories nc
SET is_active = FALSE
FROM custom_categories cc
WHERE cc.name = nc.name
  AND cc.category_type = 'hidden';

-- Add any promoted custom categories that don't exist yet
INSERT INTO normalized_categories (name, is_system, is_active, display_order)
SELECT cc.name, FALSE, TRUE, 100 + cc.display_order
FROM custom_categories cc
WHERE cc.category_type = 'promoted'
  AND NOT EXISTS (
    SELECT 1 FROM normalized_categories nc WHERE nc.name = cc.name
  );

-- ============================================================================
-- HELPER FUNCTION: Update timestamps on modification
-- ============================================================================

CREATE OR REPLACE FUNCTION update_normalized_category_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_normalized_categories_updated ON normalized_categories;
CREATE TRIGGER trigger_normalized_categories_updated
    BEFORE UPDATE ON normalized_categories
    FOR EACH ROW
    EXECUTE FUNCTION update_normalized_category_timestamp();

DROP TRIGGER IF EXISTS trigger_normalized_subcategories_updated ON normalized_subcategories;
CREATE TRIGGER trigger_normalized_subcategories_updated
    BEFORE UPDATE ON normalized_subcategories
    FOR EACH ROW
    EXECUTE FUNCTION update_normalized_category_timestamp();
