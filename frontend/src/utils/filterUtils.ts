import type { Transaction } from '../types';

export interface TransactionFilters {
  selectedCategory: string;
  selectedSubcategory: string; // empty string means no subcategory filter
  dateFrom: string;
  dateTo: string;
  searchKeyword: string;
}

export const DEFAULT_FILTERS: TransactionFilters = {
  selectedCategory: 'All',
  selectedSubcategory: '',
  dateFrom: '',
  dateTo: '',
  searchKeyword: ''
};

/**
 * Load filters from localStorage or return defaults
 */
export const loadFilters = (): TransactionFilters => {
  try {
    const saved = localStorage.getItem('transactionFilters');
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (e) {
    console.error('Failed to load filters from localStorage:', e);
  }
  return DEFAULT_FILTERS;
};

/**
 * Save filters to localStorage
 */
export const saveFilters = (filters: TransactionFilters): void => {
  try {
    localStorage.setItem('transactionFilters', JSON.stringify(filters));
  } catch (e) {
    console.error('Failed to save filters to localStorage:', e);
  }
};

/**
 * Apply all filters to a transaction (AND logic)
 */
export const applyFilters = (txn: Transaction, filters: TransactionFilters): boolean => {
  // Category filter
  if (filters.selectedCategory !== 'All' && txn.category !== filters.selectedCategory) {
    return false;
  }

  // Subcategory filter (only applies if category is selected and subcategory is set)
  if (filters.selectedSubcategory && txn.subcategory !== filters.selectedSubcategory) {
    return false;
  }

  // Date from filter
  if (filters.dateFrom && txn.date < filters.dateFrom) {
    return false;
  }

  // Date to filter
  if (filters.dateTo && txn.date > filters.dateTo) {
    return false;
  }

  // Keyword search filter (searches description, merchant, amount)
  if (filters.searchKeyword) {
    const lower = filters.searchKeyword.toLowerCase();
    const matchesDescription = txn.description.toLowerCase().includes(lower);
    const matchesMerchant = txn.merchant?.toLowerCase().includes(lower);
    const matchesAmount = Math.abs(txn.amount).toFixed(2).includes(lower);

    if (!matchesDescription && !matchesMerchant && !matchesAmount) {
      return false;
    }
  }

  return true;
};

/**
 * Get filtered transactions
 */
export const getFilteredTransactions = (
  transactions: Transaction[],
  filters: TransactionFilters
): Transaction[] => {
  return transactions.filter(txn => applyFilters(txn, filters));
};

/**
 * Get count for a specific category considering other active filters
 */
export const getFilteredCountForCategory = (
  transactions: Transaction[],
  filters: TransactionFilters,
  category: string
): number => {
  const categoryFilters = { ...filters, selectedCategory: category };
  return transactions.filter(txn => applyFilters(txn, categoryFilters)).length;
};

/**
 * Extract all unique primary categories from transactions (sorted alphabetically)
 */
export const getUniqueCategories = (transactions: Transaction[]): string[] => {
  const categories = new Set<string>();

  transactions.forEach(txn => {
    if (txn.category) {
      categories.add(txn.category);
    }
  });

  return Array.from(categories).sort();
};

/**
 * Extract all unique subcategories from transactions (sorted alphabetically)
 */
export const getUniqueSubcategories = (transactions: Transaction[]): string[] => {
  const subcategories = new Set<string>();

  transactions.forEach(txn => {
    if (txn.subcategory) {
      subcategories.add(txn.subcategory);
    }
  });

  return Array.from(subcategories).sort();
};

/**
 * Get subcategories for a specific category (sorted alphabetically)
 */
export const getSubcategoriesForCategory = (
  transactions: Transaction[],
  category: string
): string[] => {
  const subcategories = new Set<string>();

  transactions.forEach(txn => {
    if (txn.category === category && txn.subcategory) {
      subcategories.add(txn.subcategory);
    }
  });

  return Array.from(subcategories).sort();
};
