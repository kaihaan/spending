-- Migration: Category Promotion Feature
-- Creates tables for custom/promoted categories and subcategory mappings

-- Custom categories table (stores promoted and hidden categories)
CREATE TABLE IF NOT EXISTS custom_categories (
    id SERIAL PRIMARY KEY,
    user_id INTEGER DEFAULT 1,  -- Ready for multi-user future
    name VARCHAR(100) NOT NULL,
    category_type VARCHAR(20) NOT NULL CHECK(category_type IN ('promoted', 'hidden')),
    display_order INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, name)
);

-- Subcategory mappings table (maps subcategories to promoted categories)
CREATE TABLE IF NOT EXISTS subcategory_mappings (
    id SERIAL PRIMARY KEY,
    custom_category_id INTEGER NOT NULL REFERENCES custom_categories(id) ON DELETE CASCADE,
    subcategory_name VARCHAR(255) NOT NULL,
    original_category VARCHAR(100),  -- The primary category this subcategory came from
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(custom_category_id, subcategory_name)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_custom_categories_user ON custom_categories(user_id);
CREATE INDEX IF NOT EXISTS idx_custom_categories_type ON custom_categories(category_type);
CREATE INDEX IF NOT EXISTS idx_subcategory_mappings_category ON subcategory_mappings(custom_category_id);
CREATE INDEX IF NOT EXISTS idx_subcategory_mappings_subcategory ON subcategory_mappings(subcategory_name);
