import { useState, useEffect } from 'react';
import axios from 'axios';
import type { Transaction, Category } from '../types';
import { getCategoryColor, ALL_CATEGORIES } from '../utils/categoryColors';
import CategoryUpdateModal from './CategoryUpdateModal';
import {
  loadFilters,
  saveFilters,
  getFilteredTransactions,
  getFilteredCountForCategory,
  type TransactionFilters
} from '../utils/filterUtils';

const API_URL = 'http://localhost:5000/api';

export default function TransactionList() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);

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
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const clearAllFilters = () => {
    setFilters({
      selectedCategory: 'All',
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
      <div className="flex flex-wrap gap-2">
        <button
          className={`btn btn-sm ${filters.selectedCategory === 'All' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => updateFilter('selectedCategory', 'All')}
        >
          All ({getFilteredCountForCategory(transactions, filters, 'All')})
        </button>
        {ALL_CATEGORIES.map(cat => {
          const count = getFilteredCountForCategory(transactions, filters, cat);
          if (count === 0) return null;
          return (
            <button
              key={cat}
              className={`btn btn-sm ${filters.selectedCategory === cat ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => updateFilter('selectedCategory', cat)}
            >
              {cat} ({count})
            </button>
          );
        })}
      </div>

      {/* Transactions Table */}
      <div className="overflow-x-auto">
        <table className="table table-zebra">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th>Amount</th>
              <th>Category</th>
              <th>Merchant</th>
              <th>Huququllah</th>
            </tr>
          </thead>
          <tbody>
            {filteredTransactions.map((txn) => (
              <tr key={txn.id}>
                <td>{txn.date}</td>
                <td className="max-w-md truncate">{txn.description}</td>
                <td className={txn.amount < 0 ? 'text-error font-semibold' : 'text-success font-semibold'}>
                  £{Math.abs(txn.amount).toFixed(2)}
                </td>
                <td>
                  <span
                    className={`badge ${getCategoryColor(txn.category)} cursor-pointer hover:badge-outline`}
                    onClick={() => setEditingTransaction(txn)}
                    title="Click to change category"
                  >
                    {txn.category}
                  </span>
                </td>
                <td className="text-sm text-base-content/70">{txn.merchant || '-'}</td>
                <td>
                  {txn.amount < 0 ? (
                    <div className="dropdown dropdown-end">
                      <label
                        tabIndex={0}
                        className={`badge cursor-pointer hover:badge-outline ${
                          txn.huququllah_classification === 'essential'
                            ? 'badge-success'
                            : txn.huququllah_classification === 'discretionary'
                            ? 'badge-secondary'
                            : 'badge-ghost'
                        }`}
                        title="Click to change classification"
                      >
                        {txn.huququllah_classification === 'essential'
                          ? 'Essential'
                          : txn.huququllah_classification === 'discretionary'
                          ? 'Discretionary'
                          : 'Unclassified'}
                      </label>
                      <ul
                        tabIndex={0}
                        className="dropdown-content z-[1] menu p-2 shadow bg-base-200 rounded-box w-52 mt-2"
                      >
                        <li>
                          <a onClick={() => handleClassificationChange(txn.id, 'essential')}>
                            ✓ Essential
                          </a>
                        </li>
                        <li>
                          <a onClick={() => handleClassificationChange(txn.id, 'discretionary')}>
                            💰 Discretionary
                          </a>
                        </li>
                        <li>
                          <a onClick={() => handleClassificationChange(txn.id, null)}>
                            Clear
                          </a>
                        </li>
                      </ul>
                    </div>
                  ) : (
                    <span className="badge badge-ghost">N/A (Income)</span>
                  )}
                </td>
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
