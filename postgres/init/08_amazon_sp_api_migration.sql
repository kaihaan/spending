-- =============================================================================
-- Amazon Selling Partner API (SP-API) Migration
-- =============================================================================
-- Adds SP-API specific fields to existing amazon_business_connections table
-- to support sandbox/production modes and marketplace-specific requests
--
-- Run with:
-- docker exec -i spending-postgres psql -U spending_user -d spending_db < postgres/init/08_amazon_sp_api_migration.sql
-- =============================================================================

-- Add SP-API specific fields to connections table
ALTER TABLE amazon_business_connections
ADD COLUMN IF NOT EXISTS is_sandbox BOOLEAN DEFAULT TRUE;

ALTER TABLE amazon_business_connections
ADD COLUMN IF NOT EXISTS marketplace_id VARCHAR(20) DEFAULT 'A1F83G8C2ARO7P';

ALTER TABLE amazon_business_connections
ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP WITH TIME ZONE;

-- Add index for faster order lookups by order_id
CREATE INDEX IF NOT EXISTS idx_ab_orders_order_id
ON amazon_business_orders(order_id);

-- Add comments for documentation
COMMENT ON COLUMN amazon_business_connections.is_sandbox IS 'TRUE for sandbox environment, FALSE for production';
COMMENT ON COLUMN amazon_business_connections.marketplace_id IS 'Amazon marketplace ID (e.g., A1F83G8C2ARO7P for UK)';
COMMENT ON COLUMN amazon_business_connections.last_synced_at IS 'Timestamp of last successful order sync';
COMMENT ON INDEX idx_ab_orders_order_id IS 'Index for fast duplicate checking by AmazonOrderId';
