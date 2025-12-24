export interface Enrichment {
  is_enriched: boolean;
  primary_category?: string;
  subcategory?: string;
  merchant_clean_name?: string;
  merchant_type?: string;
  essential_discretionary?: 'Essential' | 'Discretionary';
  confidence_score?: number;
  enrichment_source?: string;
  payment_method?: string;
  payment_method_subtype?: string;
  llm_provider?: string;
  llm_model?: string;
  enriched_at?: string;
}

export interface EnrichmentSource {
  id?: number;  // ID from transaction_enrichment_sources table (for fetching details)
  source_type: 'amazon' | 'amazon_business' | 'apple' | 'gmail' | 'manual';
  source_id?: number;  // FK to the source table (amazon_orders, etc.)
  description: string;
  order_id?: string;
  confidence?: number;
  match_method?: string;
  is_primary: boolean;
  user_verified?: boolean;
  line_items?: Array<{ name: string; quantity?: number; price?: number }>;
  created_at?: string;
}

export interface Transaction {
  id: number;
  date: string;
  description: string;
  amount: number;
  category: string;
  merchant: string | null;
  huququllah_classification: 'essential' | 'discretionary' | null;
  pre_enrichment_status?: 'None' | 'Matched' | 'Apple' | 'AMZN' | 'AMZN RTN' | 'AMZN BIZ' | 'Gmail' | null;
  created_at: string;
  transaction_type?: 'DEBIT' | 'CREDIT';
  currency?: string;
  // Enrichment data
  subcategory?: string;
  merchant_clean_name?: string;
  essential_discretionary?: 'Essential' | 'Discretionary';
  confidence_score?: number;
  enrichment_source?: string;
  enrichment_required?: boolean;
  payment_method?: string;
  payment_method_subtype?: string;
  enrichment?: Enrichment;
  // Multi-source enrichment
  enrichment_sources?: EnrichmentSource[];
  // Pattern extraction fields
  provider: string | null;
  variant: string | null;
  payee: string | null;
  reference: string | null;
  mandate_number: string | null;
  branch: string | null;
  entity: string | null;
  trip_date: string | null;
  sender: string | null;
  rate: string | null;
  tax: string | null;
  payment_count: number | null;
  extraction_confidence: number | null;
}

export interface Category {
  id: number;
  name: string;
  rule_pattern: string | null;
  ai_suggested: boolean;
}

export interface HuququllahSuggestion {
  suggested_classification: 'essential' | 'discretionary' | null;
  confidence: number;
  reason: string;
}

export interface HuququllahSummary {
  essential_expenses: number;
  discretionary_expenses: number;
  huququllah_due: number;
  unclassified_count: number;
}

// Direct Debit Mapping types
export interface DirectDebitPayee {
  payee: string;
  transaction_count: number;
  sample_description: string;
  current_category: string | null;
  current_subcategory: string | null;
  mapping_id: number | null;
  mapped_name: string | null;
  mapped_category: string | null;
  mapped_subcategory: string | null;
}

export interface DirectDebitMapping {
  id: number;
  pattern: string;
  pattern_type: string;
  normalized_name: string;
  merchant_type: string | null;
  default_category: string;
  priority: number;
  source: string;
  usage_count: number;
  created_at: string;
  updated_at: string;
}

// Enrichment Rules Types
export interface CategoryRule {
  id: number;
  rule_name: string;
  transaction_type: 'CREDIT' | 'DEBIT' | null;
  description_pattern: string;
  pattern_type: 'contains' | 'starts_with' | 'exact' | 'regex';
  category: string;
  subcategory: string | null;
  priority: number;
  is_active: boolean;
  source: 'manual' | 'learned' | 'llm';
  usage_count: number;
  created_at: string;
}

export interface MerchantNormalization {
  id: number;
  pattern: string;
  pattern_type: 'contains' | 'starts_with' | 'exact' | 'regex';
  normalized_name: string;
  merchant_type: string | null;
  default_category: string | null;
  priority: number;
  source: 'manual' | 'learned' | 'llm' | 'direct_debit';
  usage_count: number;
  created_at: string;
  updated_at: string;
}

export interface RuleTestResult {
  match_count: number;
  sample_transactions: Array<{
    id: number;
    description: string;
    amount: number;
    date: string;
  }>;
}

export interface RulesStatistics {
  category_rules_count: number;
  merchant_rules_count: number;
  total_usage: number;
  total_transactions: number;
  covered_transactions: number;
  coverage_percentage: number;
  rules_by_category: Record<string, number>;
  rules_by_source: Record<string, number>;
  top_used_rules: Array<{ name: string; count: number; type: string }>;
  unused_rules: Array<{ name: string; type: string }>;
  unused_rules_count: number;
}

export interface TestAllRulesResult {
  total_transactions: number;
  covered_transactions: number;
  coverage_percentage: number;
  category_coverage: Record<string, number>;
  unused_category_rules: Array<{ id: number; name: string; pattern: string }>;
  unused_merchant_rules: Array<{ id: number; pattern: string; name: string }>;
  potential_conflicts_count: number;
  sample_conflicts: Array<{ transaction_id: number; matching_rules: string[] }>;
}

// Unified rule type for display
export type UnifiedRule =
  | { type: 'category'; rule: CategoryRule }
  | { type: 'merchant'; rule: MerchantNormalization };

// Gmail Merchants types
export interface GmailMerchant {
  merchant_domain: string;
  merchant_name: string;
  receipt_count: number;
  parsed_count: number;
  matched_count: number;
  pending_count: number;
  failed_count: number;
  has_template: boolean;
  template_type: 'schema_org' | 'vendor' | 'pattern' | 'llm' | 'none';
  has_vendor_parser: boolean;
  potential_transaction_matches: number;
  amazon_coverage: number;
  apple_coverage: number;
  earliest_receipt: string | null;
  latest_receipt: string | null;
  llm_cost_cents: number;
  schema_parsed_count: number;
  pattern_parsed_count: number;
  llm_parsed_count: number;
}

export interface GmailMerchantsSummary {
  total_merchants: number;
  with_template: number;
  without_template: number;
  with_vendor_parser: number;
  total_receipts: number;
  total_parsed: number;
  total_matched: number;
  total_pending: number;
  total_failed: number;
  total_llm_cost_cents: number;
  total_potential_matches: number;
}

export interface GmailReceipt {
  id: number;
  message_id: string;
  sender_email: string;
  sender_name: string | null;
  subject: string;
  received_at: string;
  merchant_name: string | null;
  merchant_domain: string | null;
  order_id: string | null;
  total_amount: number | null;
  currency_code: string;
  receipt_date: string | null;
  line_items: unknown[];
  parse_method: string | null;
  parse_confidence: number;
  parsing_status: string;
  parsing_error: string | null;
  llm_cost_cents: number | null;
  match_id: number | null;
  match_confidence: number | null;
  transaction_id: number | null;
  transaction_description: string | null;
  transaction_amount: number | null;
}

export interface GmailEnrichmentResult {
  success: boolean;
  processed: number;
  parsed: number;
  failed: number;
  llm_cost_cents: number;
  domain: string;
  message?: string;
}

export interface GmailSenderPattern {
  id: number;
  sender_domain: string;
  sender_pattern: string | null;
  merchant_name: string;
  normalized_name: string;
  parse_type: 'schema_org' | 'pattern' | 'llm';
  pattern_config: Record<string, unknown> | null;
  date_tolerance_days: number;
  is_active: boolean;
  usage_count: number;
  last_used_at: string | null;
  created_at: string;
}
