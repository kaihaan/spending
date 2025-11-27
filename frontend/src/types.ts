export interface Transaction {
  id: number;
  date: string;
  description: string;
  amount: number;
  category: string;
  source_file: string | null;
  merchant: string | null;
  huququllah_classification: 'essential' | 'discretionary' | null;
  lookup_description: string | null;
  created_at: string;
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

