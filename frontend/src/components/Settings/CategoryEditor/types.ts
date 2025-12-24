// TypeScript interfaces for Normalized Categories API (v2)

export interface NormalizedCategory {
  id: number;
  name: string;
  description: string | null;
  is_system: boolean;
  is_active: boolean;
  is_essential: boolean;
  display_order: number;
  color: string | null;
  created_at: string;
  updated_at: string;
  transaction_count?: number;
  subcategory_count?: number;
}

export interface NormalizedSubcategory {
  id: number;
  category_id: number;
  category_name?: string;
  name: string;
  description: string | null;
  is_active: boolean;
  display_order: number;
  created_at: string;
  updated_at: string;
  transaction_count?: number;
}

export interface CategoryWithSubcategories extends NormalizedCategory {
  subcategories: NormalizedSubcategory[];
}

export interface CategoriesResponse {
  categories: NormalizedCategory[];
}

export interface CategoryResponse {
  category: CategoryWithSubcategories;
}

export interface SubcategoriesResponse {
  subcategories: NormalizedSubcategory[];
}

export interface SubcategoryResponse {
  subcategory: NormalizedSubcategory;
}

export interface UpdateCategoryRequest {
  name?: string;
  description?: string | null;
  is_active?: boolean;
  is_essential?: boolean;
  display_order?: number;
  color?: string | null;
}

export interface UpdateSubcategoryRequest {
  name?: string;
  description?: string | null;
  is_active?: boolean;
  display_order?: number;
}

export interface CreateCategoryRequest {
  name: string;
  description?: string;
  is_essential?: boolean;
  color?: string;
}

export interface CreateSubcategoryRequest {
  name: string;
  description?: string;
}

export interface UpdateResponse {
  success: boolean;
  category?: NormalizedCategory;
  subcategory?: NormalizedSubcategory;
  transactions_updated?: number;
  rules_updated?: number;
  message: string;
}

export interface DeleteResponse {
  success: boolean;
  message: string;
  transactions_reassigned?: number;
}
