-- Amazon Business API Integration
-- Migration: 08_amazon_business.sql
-- Description: Tables for Amazon Business order import and matching

-- Amazon Business OAuth connections (like truelayer_connections)
CREATE TABLE IF NOT EXISTS amazon_business_connections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER DEFAULT 1,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    region VARCHAR(10) DEFAULT 'UK',
    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Amazon Business orders (aggregated for matching)
CREATE TABLE IF NOT EXISTS amazon_business_orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    order_date DATE NOT NULL,
    region VARCHAR(10),
    purchase_order_number VARCHAR(100),
    order_status VARCHAR(50),
    buyer_name VARCHAR(255),
    buyer_email VARCHAR(255),
    subtotal NUMERIC(12,2),
    tax NUMERIC(12,2),
    shipping NUMERIC(12,2),
    net_total NUMERIC(12,2),
    currency VARCHAR(10) DEFAULT 'GBP',
    item_count INTEGER DEFAULT 1,
    product_summary TEXT,  -- Concatenated product titles for lookup_description
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Amazon Business line items (detailed product info)
CREATE TABLE IF NOT EXISTS amazon_business_line_items (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL REFERENCES amazon_business_orders(order_id),
    line_item_id VARCHAR(50),
    asin VARCHAR(20),
    title TEXT,
    brand VARCHAR(255),
    category VARCHAR(255),
    quantity INTEGER,
    unit_price NUMERIC(12,2),
    total_price NUMERIC(12,2),
    seller_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Matching table (like truelayer_amazon_transaction_matches)
CREATE TABLE IF NOT EXISTS truelayer_amazon_business_matches (
    id SERIAL PRIMARY KEY,
    truelayer_transaction_id INTEGER NOT NULL REFERENCES truelayer_transactions(id),
    amazon_business_order_id INTEGER NOT NULL REFERENCES amazon_business_orders(id),
    match_confidence INTEGER NOT NULL,
    matched_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT truelayer_amazon_business_unique UNIQUE (truelayer_transaction_id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_ab_orders_date ON amazon_business_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_ab_orders_net_total ON amazon_business_orders(net_total);
CREATE INDEX IF NOT EXISTS idx_ab_line_items_order ON amazon_business_line_items(order_id);
CREATE INDEX IF NOT EXISTS idx_ab_line_items_asin ON amazon_business_line_items(asin);
CREATE INDEX IF NOT EXISTS idx_ab_matches_order ON truelayer_amazon_business_matches(amazon_business_order_id);
