import { useState, useEffect } from 'react';
import axios from 'axios';
import type { Transaction, Category } from '../types';
import { getCategoryColor } from '../utils/categoryColors';
import CategoryUpdateModal from './CategoryUpdateModal';
import {
  loadFilters,
  saveFilters,
  getFilteredTransactions,
  getFilteredCountForCategory,
  getUniqueCategories,
  getSubcategoriesForCategory,
  type TransactionFilters
} from '../utils/filterUtils';

const API_URL = 'http://localhost:5000/api';

interface ColumnVisibility {
  date: boolean;
  description: boolean;
  lookup_details: boolean;
  amount: boolean;
  category: boolean;
  merchant_clean_name: boolean;
  subcategory: boolean;
  merchant_type: boolean;
  essential_discretionary: boolean;
  payment_method: boolean;
  payment_method_subtype: boolean;
  purchase_date: boolean;
  confidence_score: boolean;
  enrichment_source: boolean;
}

const DEFAULT_COLUMN_VISIBILITY: ColumnVisibility = {
  date: true,
  description: true,
  lookup_details: true,
  amount: true,
  category: true,
  merchant_clean_name: true,
  subcategory: true,
  merchant_type: false,
  essential_discretionary: true,
  payment_method: false,
  payment_method_subtype: false,
  purchase_date: false,
  confidence_score: true,
  enrichment_source: true
};

const loadColumnVisibility = (): ColumnVisibility => {
  const saved = localStorage.getItem('transactionColumnVisibility');
  return saved ? JSON.parse(saved) : DEFAULT_COLUMN_VISIBILITY;
};

const saveColumnVisibility = (visibility: ColumnVisibility) => {
  localStorage.setItem('transactionColumnVisibility', JSON.stringify(visibility));
};

export default function TransactionList() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibility>(loadColumnVisibility());

  // Load filters from localStorage
  const initialFilters = loadFilters();
  const [filters, setFilters] = useState<TransactionFilters>(initialFilters);

  useEffect(() => {
    fetchTransactions();
    fetchCategories();

    // Listen for import events from FileList component
    const handleTransactionsUpdated = () => {
      fetchTransactions();
    };

    window.addEventListener('transactions-updated', handleTransactionsUpdated);

    return () => {
      window.removeEventListener('transactions-updated', handleTransactionsUpdated);
    };
  }, []);

  // Save filters to localStorage whenever they change
  useEffect(() => {
    saveFilters(filters);
  }, [filters]);

  // Save column visibility to localStorage whenever it changes
  useEffect(() => {
    saveColumnVisibility(columnVisibility);
  }, [columnVisibility]);

  const toggleColumnVisibility = (column: keyof ColumnVisibility) => {
    setColumnVisibility(prev => ({
      ...prev,
      [column]: !prev[column]
    }));
  };

  const resetColumnVisibility = () => {
    setColumnVisibility(DEFAULT_COLUMN_VISIBILITY);
  };

  const fetchTransactions = async () => {
    try {
      setLoading(true);
      const response = await axios.get<Transaction[]>(`${API_URL}/transactions`);
      setTransactions(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch transactions');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await axios.get<Category[]>(`${API_URL}/categories`);
      setCategories(response.data);
    } catch (err) {
      console.error('Failed to fetch categories:', err);
    }
  };

  const handleModalSuccess = () => {
    // Refresh transactions after successful update
    fetchTransactions();
  };

  // Apply all filters
  const filteredTransactions = getFilteredTransactions(transactions, filters);

  const updateFilter = (key: keyof TransactionFilters, value: string) => {
    const newFilters = { ...filters, [key]: value };
    // Clear subcategory when category changes
    if (key === 'selectedCategory') {
      newFilters.selectedSubcategory = '';
    }
    setFilters(newFilters);
  };

  const clearAllFilters = () => {
    setFilters({
      selectedCategory: 'All',
      selectedSubcategory: '',
      dateFrom: '',
      dateTo: '',
      searchKeyword: ''
    });
  };

  const handleClassificationChange = async (transactionId: number, classification: 'essential' | 'discretionary' | null) => {
    try {
      await axios.put(`${API_URL}/transactions/${transactionId}/huququllah`, {
        classification
      });
      // Refresh transactions to show updated classification
      fetchTransactions();
    } catch (err) {
      console.error('Failed to update classification:', err);
      alert('Failed to update classification');
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>{error}</span>
      </div>
    );
  }

  if (transactions.length === 0) {
    return (
      <div className="alert alert-info">
        <span>No transactions yet. Import bank statements to get started!</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Search Filter */}
      <div className="flex gap-2">
        <div className="flex-1">
          <input
            type="text"
            placeholder="🔍 Search transactions (description, merchant, amount)..."
            className="input input-bordered w-full"
            value={filters.searchKeyword}
            onChange={(e) => updateFilter('searchKeyword', e.target.value)}
          />
        </div>
        {filters.searchKeyword && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => updateFilter('searchKeyword', '')}
          >
            Clear Search
          </button>
        )}
      </div>

      {/* Date Range Filter */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-sm font-semibold">Date Range:</span>
        <input
          type="date"
          className="input input-bordered input-sm"
          value={filters.dateFrom}
          onChange={(e) => updateFilter('dateFrom', e.target.value)}
          placeholder="From"
        />
        <span className="text-sm">to</span>
        <input
          type="date"
          className="input input-bordered input-sm"
          value={filters.dateTo}
          onChange={(e) => updateFilter('dateTo', e.target.value)}
          placeholder="To"
        />
        {(filters.dateFrom || filters.dateTo) && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              updateFilter('dateFrom', '');
              updateFilter('dateTo', '');
            }}
          >
            Clear Dates
          </button>
        )}
        {(filters.selectedCategory !== 'All' || filters.dateFrom || filters.dateTo || filters.searchKeyword) && (
          <button
            className="btn btn-error btn-sm ml-auto"
            onClick={clearAllFilters}
          >
            Clear All Filters
          </button>
        )}
      </div>

      {/* Category Filter */}
      <div className="flex flex-wrap gap-2 items-center">
        <span
          onClick={() => updateFilter('selectedCategory', 'All')}
          className={`badge badge-lg cursor-pointer px-3 py-2 transition-all ${
            filters.selectedCategory === 'All'
              ? 'badge-primary scale-110'
              : 'badge-ghost hover:scale-105'
          }`}
        >
          All ({getFilteredCountForCategory(transactions, filters, 'All')})
        </span>
        {getUniqueCategories(transactions).map(cat => {
          const count = getFilteredCountForCategory(transactions, filters, cat);
          if (count === 0) return null;
          return (
            <span
              key={cat}
              onClick={() => updateFilter('selectedCategory', cat)}
              className={`badge badge-lg cursor-pointer px-3 py-2 transition-all ${getCategoryColor(cat)} ${
                filters.selectedCategory === cat ? 'scale-110' : 'hover:scale-105'
              }`}
            >
              {cat} ({count})
            </span>
          );
        })}
      </div>

      {/* Subcategory Filter (shown when a category is selected) */}
      {filters.selectedCategory !== 'All' && (
        <div className="flex flex-wrap gap-2 ml-4 items-center">
          <span className="text-sm font-semibold">Subcategories:</span>
          <span
            onClick={() => updateFilter('selectedSubcategory', '')}
            className={`badge badge-md cursor-pointer px-2 py-1 transition-all ${
              !filters.selectedSubcategory
                ? 'badge-primary scale-105'
                : 'badge-ghost hover:scale-105'
            }`}
          >
            All
          </span>
          {getSubcategoriesForCategory(transactions, filters.selectedCategory).map(subcat => {
            const subcount = transactions.filter(
              txn =>
                txn.category === filters.selectedCategory &&
                txn.subcategory === subcat
            ).length;
            if (subcount === 0) return null;
            return (
              <span
                key={subcat}
                onClick={() => updateFilter('selectedSubcategory', subcat)}
                className={`badge badge-md cursor-pointer px-2 py-1 transition-all ${
                  getCategoryColor(filters.selectedCategory)
                } ${filters.selectedSubcategory === subcat ? 'scale-105' : 'hover:scale-105'}`}
              >
                {subcat} ({subcount})
              </span>
            );
          })}
        </div>
      )}

      {/* Column Visibility Toggle */}
      <div className="flex flex-wrap gap-2">
        <div className="ml-auto dropdown dropdown-end">
          <label tabIndex={0} className="btn btn-sm btn-outline">
            ⚙️ Columns
          </label>
          <ul
            tabIndex={0}
            className="dropdown-content z-[1] menu p-3 shadow bg-base-200 rounded-box w-56 space-y-1"
          >
            <li className="menu-title"><span>Transaction Info</span></li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.date} onChange={() => toggleColumnVisibility('date')} className="checkbox checkbox-sm" />
                <span className="text-sm">Date</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.description} onChange={() => toggleColumnVisibility('description')} className="checkbox checkbox-sm" />
                <span className="text-sm">Description</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.lookup_details} onChange={() => toggleColumnVisibility('lookup_details')} className="checkbox checkbox-sm" />
                <span className="text-sm">Lookup Details (Amazon/Apple)</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.amount} onChange={() => toggleColumnVisibility('amount')} className="checkbox checkbox-sm" />
                <span className="text-sm">Amount</span>
              </label>
            </li>

            <li className="menu-title mt-3"><span>LLM Enrichment</span></li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.category} onChange={() => toggleColumnVisibility('category')} className="checkbox checkbox-sm" />
                <span className="text-sm">Primary Category</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.subcategory} onChange={() => toggleColumnVisibility('subcategory')} className="checkbox checkbox-sm" />
                <span className="text-sm">Subcategory</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.merchant_clean_name} onChange={() => toggleColumnVisibility('merchant_clean_name')} className="checkbox checkbox-sm" />
                <span className="text-sm">Clean Merchant</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.merchant_type} onChange={() => toggleColumnVisibility('merchant_type')} className="checkbox checkbox-sm" />
                <span className="text-sm">Merchant Type</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.essential_discretionary} onChange={() => toggleColumnVisibility('essential_discretionary')} className="checkbox checkbox-sm" />
                <span className="text-sm">Essential/Discretionary</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.payment_method} onChange={() => toggleColumnVisibility('payment_method')} className="checkbox checkbox-sm" />
                <span className="text-sm">Payment Method</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.payment_method_subtype} onChange={() => toggleColumnVisibility('payment_method_subtype')} className="checkbox checkbox-sm" />
                <span className="text-sm">Payment Subtype</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.purchase_date} onChange={() => toggleColumnVisibility('purchase_date')} className="checkbox checkbox-sm" />
                <span className="text-sm">Purchase Date</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.confidence_score} onChange={() => toggleColumnVisibility('confidence_score')} className="checkbox checkbox-sm" />
                <span className="text-sm">Confidence Score</span>
              </label>
            </li>
            <li>
              <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                <input type="checkbox" checked={columnVisibility.enrichment_source} onChange={() => toggleColumnVisibility('enrichment_source')} className="checkbox checkbox-sm" />
                <span className="text-sm">Enrichment Source</span>
              </label>
            </li>
            <li className="divider my-1"></li>
            <li>
              <button className="btn btn-ghost btn-xs w-full" onClick={resetColumnVisibility}>
                Reset to Default
              </button>
            </li>
          </ul>
        </div>
      </div>

      {/* Transactions Table */}
      <div className="overflow-x-auto">
        <table className="table table-zebra">
          <thead>
            <tr>
              {columnVisibility.date && <th>Date</th>}
              {columnVisibility.description && <th>Description</th>}
              {columnVisibility.lookup_details && <th>Lookup Details</th>}
              {columnVisibility.amount && <th>Amount</th>}
              {columnVisibility.category && <th>Primary Category</th>}
              {columnVisibility.subcategory && <th>Subcategory</th>}
              {columnVisibility.merchant_clean_name && <th>Clean Merchant</th>}
              {columnVisibility.merchant_type && <th>Merchant Type</th>}
              {columnVisibility.essential_discretionary && <th>Essential/Discretionary</th>}
              {columnVisibility.payment_method && <th>Payment Method</th>}
              {columnVisibility.payment_method_subtype && <th>Payment Subtype</th>}
              {columnVisibility.purchase_date && <th>Purchase Date</th>}
              {columnVisibility.confidence_score && <th>Confidence</th>}
              {columnVisibility.enrichment_source && <th>Enrichment Source</th>}
            </tr>
          </thead>
          <tbody>
            {filteredTransactions.map((txn) => (
              <tr key={txn.id}>
                {columnVisibility.date && <td>{txn.date}</td>}
                {columnVisibility.description && (
                  <td className="text-sm whitespace-normal break-words" title={txn.description}>{txn.description}</td>
                )}
                {columnVisibility.lookup_details && (
                  <td className="text-sm whitespace-normal break-words" title={txn.lookup_description || ''}>
                    {txn.lookup_description ? (
                      <span className="text-base-content font-medium italic">{txn.lookup_description}</span>
                    ) : (
                      <span className="text-base-content/30">-</span>
                    )}
                  </td>
                )}
                {columnVisibility.amount && (
                  <td className={txn.amount < 0 ? 'text-error font-semibold' : 'text-success font-semibold'}>
                    £{Math.abs(txn.amount).toFixed(2)}
                  </td>
                )}
                {columnVisibility.category && (
                  <td className="text-sm">
                    <span className={`badge ${getCategoryColor(txn.category)}`}>
                      {txn.category || '-'}
                    </span>
                  </td>
                )}
                {columnVisibility.subcategory && (
                  <td className="text-sm text-base-content/70">{txn.subcategory || '-'}</td>
                )}
                {columnVisibility.merchant_clean_name && (
                  <td className="text-sm text-base-content/70 font-medium">{txn.merchant_clean_name || '-'}</td>
                )}
                {columnVisibility.merchant_type && (
                  <td className="text-sm text-base-content/70">{txn.merchant_type || '-'}</td>
                )}
                {columnVisibility.essential_discretionary && (
                  <td className="text-sm text-center">
                    {txn.essential_discretionary ? (
                      <span className={`badge ${txn.essential_discretionary === 'Essential' ? 'badge-success' : 'badge-secondary'}`}>
                        {txn.essential_discretionary}
                      </span>
                    ) : <span className="text-base-content/40">-</span>}
                  </td>
                )}
                {columnVisibility.payment_method && (
                  <td className="text-sm text-base-content/70">{txn.payment_method || '-'}</td>
                )}
                {columnVisibility.payment_method_subtype && (
                  <td className="text-sm text-base-content/70">{txn.payment_method_subtype || '-'}</td>
                )}
                {columnVisibility.purchase_date && (
                  <td className="text-sm text-base-content/70">{txn.purchase_date || '-'}</td>
                )}
                {columnVisibility.confidence_score && (
                  <td className="text-sm text-center">
                    {txn.confidence_score ? (
                      <span className={`badge ${txn.confidence_score >= 0.9 ? 'badge-success' : txn.confidence_score >= 0.7 ? 'badge-warning' : 'badge-error'}`}>
                        {(txn.confidence_score * 100).toFixed(0)}%
                      </span>
                    ) : <span className="text-base-content/40">-</span>}
                  </td>
                )}
                {columnVisibility.enrichment_source && (
                  <td className="text-sm text-center">
                    {txn.enrichment_source ? (
                      <span className={`badge badge-sm ${
                        txn.enrichment_source === 'llm' ? 'badge-info' :
                        txn.enrichment_source === 'lookup' ? 'badge-primary' :
                        txn.enrichment_source === 'regex' ? 'badge-warning' :
                        txn.enrichment_source === 'manual' ? 'badge-success' :
                        'badge-ghost'
                      }`}>
                        {txn.enrichment_source}
                      </span>
                    ) : <span className="text-base-content/40">-</span>}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {filteredTransactions.length === 0 && filters.selectedCategory !== 'All' && (
        <div className="alert alert-info">
          <span>No transactions in category: {filters.selectedCategory}</span>
        </div>
      )}

      {/* Summary */}
      <div className="text-sm text-base-content/60">
        Showing {filteredTransactions.length} of {transactions.length} transactions
      </div>

      {/* Category Update Modal */}
      {editingTransaction && (
        <CategoryUpdateModal
          transactionId={editingTransaction.id}
          currentCategory={editingTransaction.category}
          merchant={editingTransaction.merchant}
          onClose={() => setEditingTransaction(null)}
          onSuccess={handleModalSuccess}
        />
      )}
    </div>
  );
}
