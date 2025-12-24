// TypeScript interfaces for Category Promotion feature

export interface Category {
  name: string;
  total_spend: number;
  transaction_count: number;
  is_custom: boolean;
}

export interface HiddenCategory {
  name: string;
  id: number;
}

export interface Subcategory {
  name: string;
  total_spend: number;
  transaction_count: number;
  already_mapped: boolean;
}

export interface SelectedSubcategory {
  name: string;
  total_spend: number;
  original_category: string;
}

export interface CategorySummaryResponse {
  categories: Category[];
  hidden_categories: HiddenCategory[];
}

export interface SubcategoryResponse {
  category: string;
  subcategories: Subcategory[];
}

export interface PromoteResponse {
  success: boolean;
  category_id: number;
  transactions_updated: number;
  message: string;
}

export interface HideResponse {
  success: boolean;
  category_id: number;
  transactions_reset: number;
  message: string;
}

export interface UnhideResponse {
  success: boolean;
  message: string;
}
