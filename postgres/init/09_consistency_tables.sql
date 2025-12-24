-- ============================================================================
-- Consistency Tables for LLM Categorization
-- ============================================================================
-- These tables store rules and patterns to ensure consistent categorization
-- across transactions, reducing LLM variability and costs.

-- Merchant Normalization Table
-- Maps patterns in transaction descriptions to normalized merchant names
CREATE TABLE IF NOT EXISTS merchant_normalizations (
    id SERIAL PRIMARY KEY,
    pattern VARCHAR(255) NOT NULL,              -- Pattern to match (e.g., 'GAILS', 'STARBUCKS')
    pattern_type VARCHAR(20) DEFAULT 'contains', -- 'contains', 'starts_with', 'exact', 'regex'
    normalized_name VARCHAR(255) NOT NULL,      -- Standardized name (e.g., "Gail's Bakery")
    merchant_type VARCHAR(100),                 -- Type (e.g., 'bakery', 'supermarket', 'coffee_shop')
    default_category VARCHAR(100),              -- Default category if matched
    priority INT DEFAULT 0,                     -- Higher priority = checked first
    source VARCHAR(50) DEFAULT 'manual',        -- 'manual', 'learned', 'llm'
    usage_count INT DEFAULT 0,                  -- How many times this rule was applied
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(pattern, pattern_type)
);

-- Category Rules Table
-- Pattern-based rules for categorizing transactions (especially inbound)
CREATE TABLE IF NOT EXISTS category_rules (
    id SERIAL PRIMARY KEY,
    rule_name VARCHAR(100) NOT NULL,            -- Human-readable name
    transaction_type VARCHAR(10),               -- 'CREDIT', 'DEBIT', or NULL (both)
    description_pattern VARCHAR(255) NOT NULL,  -- Pattern to match in description
    pattern_type VARCHAR(20) DEFAULT 'contains', -- 'contains', 'starts_with', 'exact', 'regex'
    category VARCHAR(100) NOT NULL,             -- Category to assign
    subcategory VARCHAR(100),                   -- Optional subcategory
    priority INT DEFAULT 0,                     -- Higher priority = checked first
    is_active BOOLEAN DEFAULT TRUE,             -- Enable/disable rule
    source VARCHAR(50) DEFAULT 'manual',        -- 'manual', 'learned', 'llm'
    usage_count INT DEFAULT 0,                  -- How many times this rule was applied
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_merchant_norm_pattern ON merchant_normalizations(pattern);
CREATE INDEX IF NOT EXISTS idx_merchant_norm_priority ON merchant_normalizations(priority DESC);
CREATE INDEX IF NOT EXISTS idx_category_rules_pattern ON category_rules(description_pattern);
CREATE INDEX IF NOT EXISTS idx_category_rules_priority ON category_rules(priority DESC);
CREATE INDEX IF NOT EXISTS idx_category_rules_type ON category_rules(transaction_type);

-- ============================================================================
-- Seed Initial Category Rules
-- ============================================================================
-- These rules are derived from manual SQL fixes for inbound transactions

INSERT INTO category_rules (rule_name, transaction_type, description_pattern, category, subcategory, priority) VALUES
-- Income rules (highest priority)
('Salary', 'CREDIT', 'SALARY', 'Income', 'Salary', 100),
('Payroll', 'CREDIT', 'PAYROLL', 'Income', 'Salary', 100),
('Interest', 'CREDIT', 'INTEREST PAID', 'Interest', NULL, 90),
('Bank Giro Credit', 'CREDIT', 'BANK GIRO CREDIT', 'Income', NULL, 40),

-- Transfer rules
('Faster Payment Receipt', 'CREDIT', 'FASTER PAYMENTS RECEIPT', 'Transfer', 'Personal', 80),
('Transfer From', 'CREDIT', 'TRANSFER FROM', 'Transfer', 'Personal', 30),
('Transfer Generic', 'CREDIT', 'TRANSFER', 'Transfer', NULL, 20),

-- Refund rules
('Amazon Marketplace Refund', 'CREDIT', 'AMZNMKTPLACE', 'Refund', 'Amazon', 70),
('Amazon Refund', 'CREDIT', 'AMAZON', 'Refund', 'Amazon', 60),
('Generic Refund', 'CREDIT', 'CREDIT FROM', 'Refund', NULL, 50)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- Seed Initial Merchant Normalizations
-- ============================================================================
-- Common merchants with consistent naming

INSERT INTO merchant_normalizations (pattern, normalized_name, merchant_type, default_category, priority) VALUES
-- Coffee shops
('STARBUCKS', 'Starbucks', 'coffee_shop', 'Dining', 100),
('COSTA COFFEE', 'Costa Coffee', 'coffee_shop', 'Dining', 100),
('PRET A MANGER', 'Pret A Manger', 'cafe', 'Dining', 100),
('PRET%MANGER', 'Pret A Manger', 'cafe', 'Dining', 90),
('CAFFE NERO', 'Caffè Nero', 'coffee_shop', 'Dining', 100),

-- Bakeries
('GAILS', 'Gail''s Bakery', 'bakery', 'Dining', 100),
('GAIL''S', 'Gail''s Bakery', 'bakery', 'Dining', 100),
('GREGGS', 'Greggs', 'bakery', 'Dining', 100),

-- Supermarkets
('TESCO', 'Tesco', 'supermarket', 'Groceries', 100),
('SAINSBURY', 'Sainsbury''s', 'supermarket', 'Groceries', 100),
('WAITROSE', 'Waitrose', 'supermarket', 'Groceries', 100),
('ASDA', 'Asda', 'supermarket', 'Groceries', 100),
('MORRISONS', 'Morrisons', 'supermarket', 'Groceries', 100),
('ALDI', 'Aldi', 'supermarket', 'Groceries', 100),
('LIDL', 'Lidl', 'supermarket', 'Groceries', 100),
('M&S', 'Marks & Spencer', 'supermarket', 'Groceries', 90),
('MARKS AND SPENCER', 'Marks & Spencer', 'supermarket', 'Groceries', 100),

-- Transport
('TFL', 'Transport for London', 'public_transport', 'Transportation', 100),
('UBER', 'Uber', 'rideshare', 'Transportation', 100),
('BOLT', 'Bolt', 'rideshare', 'Transportation', 100),

-- Online retail
('AMAZON', 'Amazon', 'online_retail', 'Shopping', 50),
('AMZN', 'Amazon', 'online_retail', 'Shopping', 50)
ON CONFLICT (pattern, pattern_type) DO NOTHING;
