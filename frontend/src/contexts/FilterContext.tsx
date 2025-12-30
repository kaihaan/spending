import type { ReactNode } from 'react';
import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import apiClient from '../api/client';
import { useAuth } from './AuthContext';
import type { Transaction } from '../types';
import type {
  TransactionFilters} from '../utils/filterUtils';
import {
  loadFilters,
  saveFilters,
  DEFAULT_FILTERS,
  getFilteredTransactions,
  getFilteredCountForCategory,
  getUniqueCategories,
  getSubcategoriesForCategory
} from '../utils/filterUtils';

interface FilterContextType {
  // Filter state
  filters: TransactionFilters;
  updateFilter: <K extends keyof TransactionFilters>(key: K, value: TransactionFilters[K]) => void;
  clearAllFilters: () => void;

  // Category drawer state
  categoryDrawerOpen: boolean;
  setCategoryDrawerOpen: (open: boolean) => void;

  // Transaction data
  transactions: Transaction[];
  filteredTransactions: Transaction[];
  loading: boolean;
  error: string | null;
  refreshTransactions: () => Promise<void>;

  // Derived data for filter UI
  uniqueCategories: string[];
  getSubcategoriesForCategory: (category: string) => string[];
  getFilteredCountForCategory: (category: string) => number;
}

const FilterContext = createContext<FilterContextType | undefined>(undefined);

export function FilterProvider({ children }: { children: ReactNode }) {
  const { user, loading: authLoading } = useAuth();
  const [filters, setFilters] = useState<TransactionFilters>(() => loadFilters());
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryDrawerOpen, setCategoryDrawerOpen] = useState(false);

  // Persist filters to localStorage
  useEffect(() => {
    saveFilters(filters);
  }, [filters]);

  // Fetch transactions - only when authenticated
  const fetchTransactions = useCallback(async () => {
    // Don't fetch if not authenticated
    if (!user) {
      setTransactions([]);
      setLoading(false);
      setError(null);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.get<Transaction[]>('/transactions');
      setTransactions(response.data);
    } catch (err) {
      // Don't show error for 401 - auth interceptor handles redirect
      const axiosError = err as { response?: { status?: number } };
      if (axiosError.response?.status !== 401) {
        setError('Failed to load transactions');
        console.error(err);
      }
    } finally {
      setLoading(false);
    }
  }, [user]);

  // Fetch when user changes (login/logout) or auth check completes
  useEffect(() => {
    // Wait for auth check to complete
    if (authLoading) return;

    void fetchTransactions();

    // Listen for transaction updates
    const handleUpdate = () => void fetchTransactions();
    window.addEventListener('transactions-updated', handleUpdate);
    return () => window.removeEventListener('transactions-updated', handleUpdate);
  }, [fetchTransactions, authLoading]);

  // Derived state
  const filteredTransactions = getFilteredTransactions(transactions, filters);
  const uniqueCategories = getUniqueCategories(transactions);

  const updateFilter = <K extends keyof TransactionFilters>(key: K, value: TransactionFilters[K]) => {
    setFilters(prev => {
      const newFilters = { ...prev, [key]: value };
      if (key === 'selectedCategory') {
        newFilters.selectedSubcategory = '';
      }
      return newFilters;
    });
  };

  const clearAllFilters = () => setFilters(DEFAULT_FILTERS);

  const getSubcategoriesForCategoryFn = (category: string) => {
    return getSubcategoriesForCategory(transactions, category);
  };

  const getFilteredCountForCategoryFn = (category: string) => {
    return getFilteredCountForCategory(transactions, filters, category);
  };

  return (
    <FilterContext.Provider value={{
      filters,
      updateFilter,
      clearAllFilters,
      categoryDrawerOpen,
      setCategoryDrawerOpen,
      transactions,
      filteredTransactions,
      loading,
      error,
      refreshTransactions: fetchTransactions,
      uniqueCategories,
      getSubcategoriesForCategory: getSubcategoriesForCategoryFn,
      getFilteredCountForCategory: getFilteredCountForCategoryFn
    }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  const context = useContext(FilterContext);
  if (!context) {
    throw new Error('useFilters must be used within a FilterProvider');
  }
  return context;
}
