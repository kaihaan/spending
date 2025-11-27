-- ============================================================================
-- Seed Data for Personal Finance Tracker
-- ============================================================================

-- Default Categories
INSERT INTO categories (name) VALUES
    ('Groceries'),
    ('Transport'),
    ('Dining'),
    ('Entertainment'),
    ('Utilities'),
    ('Shopping'),
    ('Health'),
    ('Income'),
    ('Other')
ON CONFLICT (name) DO NOTHING;

-- Default User (for single-user setup)
INSERT INTO users (email) VALUES
    ('default@local.app')
ON CONFLICT (email) DO NOTHING;

-- ============================================================================
-- Sample Category Keywords (Optional - uncomment if needed)
-- ============================================================================

/*
INSERT INTO category_keywords (category_name, keyword) VALUES
    ('Groceries', 'tesco'),
    ('Groceries', 'sainsbury'),
    ('Groceries', 'asda'),
    ('Groceries', 'morrisons'),
    ('Groceries', 'aldi'),
    ('Groceries', 'lidl'),
    ('Groceries', 'waitrose'),
    ('Groceries', 'co-op'),

    ('Transport', 'tfl'),
    ('Transport', 'uber'),
    ('Transport', 'trainline'),
    ('Transport', 'national rail'),
    ('Transport', 'shell'),
    ('Transport', 'bp'),
    ('Transport', 'esso'),

    ('Dining', 'restaurant'),
    ('Dining', 'cafe'),
    ('Dining', 'pizza'),
    ('Dining', 'mcdonalds'),
    ('Dining', 'kfc'),
    ('Dining', 'nandos'),
    ('Dining', 'subway'),

    ('Entertainment', 'cinema'),
    ('Entertainment', 'spotify'),
    ('Entertainment', 'netflix'),
    ('Entertainment', 'amazon prime'),
    ('Entertainment', 'disney'),

    ('Utilities', 'thames water'),
    ('Utilities', 'british gas'),
    ('Utilities', 'edf'),
    ('Utilities', 'vodafone'),
    ('Utilities', 'ee'),
    ('Utilities', 'bt'),

    ('Shopping', 'amazon'),
    ('Shopping', 'ebay'),
    ('Shopping', 'argos'),
    ('Shopping', 'john lewis'),
    ('Shopping', 'zara'),
    ('Shopping', 'h&m')
ON CONFLICT (category_name, keyword) DO NOTHING;
*/

-- ============================================================================
-- Database Statistics
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully!';
    RAISE NOTICE 'Categories seeded: %', (SELECT COUNT(*) FROM categories);
    RAISE NOTICE 'Default user created: %', (SELECT email FROM users WHERE email = 'default@local.app');
END $$;
