export interface Transaction {
  id: number;
  date: string;
  description: string;
  amount: number;
  category: string;
  source_file: string | null;
  merchant: string | null;
  huququllah_classification: 'essential' | 'discretionary' | null;
  created_at: string;
}

export interface Category {
  id: number;
  name: string;
  rule_pattern: string | null;
  ai_suggested: boolean;
}

export interface ExcelFile {
  name: string;
  size: number;
  size_mb: number;
  modified: number;
  modified_readable: string;
  imported: boolean;
  path: string;
}

export interface ImportResponse {
  success: boolean;
  imported: number;
  filename: string;
}

export interface CategoryRules {
  rules: Record<string, string[]>;  // category -> keywords
  categories: string[];  // list of all category names
}

export interface TransactionChange {
  id: number;
  description: string;
  merchant: string | null;
  current_category: string;
  new_category: string;
  amount: number;
  date: string;
}

export interface PreviewResponse {
  changes: TransactionChange[];
  count: number;
}

export interface ApplyRulesRequest {
  transaction_ids: number[];
}

export interface ApplyRulesFilters {
  only_other?: boolean;
  all?: boolean;
  categories?: string[];
}

export interface KeywordSuggestion {
  keyword: string;
  frequency: number;
  suggested_category: string;
  confidence: number;
  sample_transactions: string[];
}

export interface SuggestionsResponse {
  suggestions: KeywordSuggestion[];
  total_other_transactions: number;
  analyzed_at: string;
  parameters: {
    min_frequency: number;
    min_confidence: number;
  };
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

export interface CategoryClassificationPattern {
  essential_count: number;
  discretionary_count: number;
  essential_percentage: number;
  discretionary_percentage: number;
  most_common: 'essential' | 'discretionary';
}
