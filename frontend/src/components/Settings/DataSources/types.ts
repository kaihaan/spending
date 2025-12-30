/**
 * Shared types for DataSources components
 *
 * These types define the data structures used across all source detail tabs
 * (Amazon, Returns, Business, Apple, Gmail).
 */

// =============================================================================
// Sub-Tab Navigation
// =============================================================================

export type SourceTabId =
  | 'summary'
  | 'amazon'
  | 'returns'
  | 'business'
  | 'apple'
  | 'gmail'
  | 'digital'
  | 'matches';

export interface SourceTab {
  id: SourceTabId;
  label: string;
  path: string;
  count?: number;
}

// =============================================================================
// Statistics Types (from API responses)
// =============================================================================

export interface AmazonStats {
  total_orders: number;
  total_matched: number;
  total_unmatched: number;
  min_order_date: string | null;
  max_order_date: string | null;
  min_bank_date: string | null;
  max_bank_date: string | null;
  overlap_start: string | null;
  overlap_end: string | null;
}

export interface ReturnsStats {
  total_returns: number;
  matched_returns: number;
  unmatched_returns: number;
  min_return_date: string | null;
  max_return_date: string | null;
}

export interface AppleStats {
  total_transactions: number;
  matched_transactions: number;
  unmatched_transactions: number;
  min_transaction_date: string | null;
  max_transaction_date: string | null;
}

export interface AmazonBusinessStats {
  total_orders: number;
  total_matched: number;
  total_unmatched: number;
  min_order_date: string | null;
  max_order_date: string | null;
}

export interface GmailStats {
  total_receipts: number;
  parsed_receipts: number;
  matched_receipts: number;
  pending_receipts: number;
  failed_receipts: number;
  min_receipt_date: string | null;
  max_receipt_date: string | null;
}

export interface AmazonDigitalStats {
  total_orders: number;
  matched_orders: number;
  unmatched_orders: number;
  min_order_date: string | null;
  max_order_date: string | null;
  min_bank_date: string | null;
  max_bank_date: string | null;
  overlap_start: string | null;
  overlap_end: string | null;
}

// =============================================================================
// Data Item Types
// =============================================================================

export interface AmazonOrder {
  id: number;
  order_id: string;
  order_date: string;
  product_names: string;
  total_owed: number;
  website: string;
  matched_transaction_id?: number | null;
}

export interface AmazonReturn {
  id: number;
  order_id: string;
  refund_completion_date: string;
  amount_refunded: number;
  status: string | null;
  original_transaction_id: number | null;
  refund_transaction_id: number | null;
}

export interface AppleTransaction {
  id: number;
  order_date: string;
  app_names: string;
  publishers: string | null;
  total_amount: number;
  item_count: number;
  matched_bank_transaction_id: number | null;
}

export interface AmazonBusinessOrder {
  id: number;
  order_id: string;
  order_date: string;
  total_amount: number;
  status: string;
  matched_transaction_id?: number | null;
}

export interface GmailReceipt {
  id: number;
  message_id: string;
  sender_email: string;
  subject: string;
  received_at: string;
  merchant_name: string | null;
  total_amount: number | null;
  receipt_date: string | null;
  parsing_status: string;
  matched_transaction_id: number | null;
}

export interface AmazonDigitalOrder {
  id: number;
  asin: string;
  product_name: string;
  order_id: string;
  digital_order_item_id: string;
  order_date: string;
  fulfilled_date: string | null;
  price: number;
  price_tax: number | null;
  currency: string;
  publisher: string | null;
  seller_of_record: string | null;
  marketplace: string | null;
  source_file: string | null;
  matched_transaction_id: number | null;
  created_at: string | null;
}

// =============================================================================
// Connection Types
// =============================================================================

export interface GmailConnection {
  id: number;
  email_address: string;
  connection_status: string;
  last_synced_at: string | null;
}

export interface AmazonBusinessConnection {
  connected: boolean;
  connection_id?: number;
  region?: string;
  status?: string;
}

// =============================================================================
// Matching Job Types
// =============================================================================

export type MatchingJobType = 'amazon' | 'returns' | 'apple' | 'amazon-business';

export interface MatchingJob {
  id: number;
  job_type: MatchingJobType;
  status: 'queued' | 'running' | 'completed' | 'failed';
  total_items: number;
  processed_items: number;
  matched_items: number;
  failed_items: number;
  progress_percentage: number;
  error_message?: string;
}

// =============================================================================
// Shared Component Props
// =============================================================================

export interface SourceMetricsProps {
  total: number;
  matched: number;
  unmatched: number;
  matchPercentage: number;
  isLoading?: boolean;
}

export interface DateRangeIndicatorProps {
  minDate: string | null;
  maxDate: string | null;
  isLoading?: boolean;
}

// =============================================================================
// API Response Types
// =============================================================================

export interface SourceCoverageData {
  bank_transactions: {
    max_date: string | null;
    count: number;
  };
  amazon: {
    max_date: string | null;
    count: number;
  };
  apple: {
    max_date: string | null;
    count: number;
  };
  gmail: {
    max_date: string | null;
    count: number;
  };
  stale_sources: string[];
  has_stale_sources: boolean;
}

export interface PreEnrichmentSummary {
  Apple: number;
  AMZN: number;
  'AMZN RTN': number;
  total: number;
}
