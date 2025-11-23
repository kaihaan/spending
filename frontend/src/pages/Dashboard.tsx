import { useState, useEffect } from 'react';
import axios from 'axios';
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { Transaction, Category } from '../types';
import { getCategoryColor, ALL_CATEGORIES } from '../utils/categoryColors';
import {
  loadFilters,
  saveFilters,
  getFilteredTransactions,
  getFilteredCountForCategory,
  type TransactionFilters
} from '../utils/filterUtils';

const API_URL = 'http://localhost:5000/api';

type ChartView = 'category' | 'timeline';

export default function Dashboard() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [chartView, setChartView] = useState<ChartView>('category');
  const [huququllahFilter, setHuququllahFilter] = useState<'all' | 'essential' | 'discretionary'>('all');

  // Load filters from localStorage
  const initialFilters = loadFilters();
  const [filters, setFilters] = useState<TransactionFilters>(initialFilters);

  useEffect(() => {
    fetchTransactions();
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

  // Apply filters
  let filteredTransactions = getFilteredTransactions(transactions, filters);

  // Apply Huququllah filter
  if (huququllahFilter !== 'all') {
    filteredTransactions = filteredTransactions.filter(
      txn => txn.huququllah_classification === huququllahFilter
    );
  }

  // Process data for category bar chart
  const categoryData = ALL_CATEGORIES
    .map(category => {
      const categoryTransactions = filteredTransactions.filter(
        txn => txn.category === category && txn.amount < 0
      );
      const total = categoryTransactions.reduce((sum, txn) => sum + Math.abs(txn.amount), 0);

      return {
        category,
        total: parseFloat(total.toFixed(2)),
        count: categoryTransactions.length
      };
    })
    .filter(item => item.total > 0)
    .sort((a, b) => b.total - a.total);

  // Process data for timeline chart
  const timelineData = (() => {
    const dailySpending: Record<string, number> = {};

    filteredTransactions
      .filter(txn => txn.amount < 0)
      .forEach(txn => {
        if (!dailySpending[txn.date]) {
          dailySpending[txn.date] = 0;
        }
        dailySpending[txn.date] += Math.abs(txn.amount);
      });

    return Object.entries(dailySpending)
      .map(([date, total]) => ({
        date,
        total: parseFloat(total.toFixed(2))
      }))
      .sort((a, b) => a.date.localeCompare(b.date));
  })();

  // Calculate total spending
  const totalSpending = filteredTransactions
    .filter(txn => txn.amount < 0)
    .reduce((sum, txn) => sum + Math.abs(txn.amount), 0);

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
    <div className="container mx-auto p-4 space-y-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <h2 className="card-title text-2xl">📊 Dashboard</h2>
          <p className="text-sm text-base-content/70 mb-4">
            Visual spending analysis with interactive filters
          </p>

          {/* Filters Section */}
          <div className="space-y-4 mb-6">
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
          </div>

          {/* Chart View Toggle */}
          <div className="flex gap-2 mb-4">
            <button
              className={`btn btn-sm ${chartView === 'category' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setChartView('category')}
            >
              📊 By Category
            </button>
            <button
              className={`btn btn-sm ${chartView === 'timeline' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setChartView('timeline')}
            >
              📈 Timeline
            </button>
          </div>

          {/* Huququllah Filter */}
          <div className="flex gap-2 mb-4">
            <span className="text-sm font-semibold mr-2">Huququllah Filter:</span>
            <button
              className={`btn btn-sm ${huququllahFilter === 'all' ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setHuququllahFilter('all')}
            >
              All Spending
            </button>
            <button
              className={`btn btn-sm ${huququllahFilter === 'essential' ? 'btn-success' : 'btn-ghost'}`}
              onClick={() => setHuququllahFilter('essential')}
            >
              Essential Only
            </button>
            <button
              className={`btn btn-sm ${huququllahFilter === 'discretionary' ? 'btn-secondary' : 'btn-ghost'}`}
              onClick={() => setHuququllahFilter('discretionary')}
            >
              Discretionary Only
            </button>
          </div>

          {/* Summary Stats */}
          <div className="stats shadow mb-6">
            <div className="stat">
              <div className="stat-title">Total Spending</div>
              <div className="stat-value text-error">£{totalSpending.toFixed(2)}</div>
              <div className="stat-desc">{filteredTransactions.filter(t => t.amount < 0).length} transactions</div>
            </div>
          </div>

          {/* Chart Display */}
          {filteredTransactions.length === 0 ? (
            <div className="alert alert-info">
              <span>No transactions match the current filters</span>
            </div>
          ) : (
            <div className="bg-base-100 p-4 rounded-lg">
              {chartView === 'category' && categoryData.length > 0 && (
                <ResponsiveContainer width="100%" height={400}>
                  <BarChart data={categoryData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="category"
                      angle={-45}
                      textAnchor="end"
                      height={100}
                      interval={0}
                    />
                    <YAxis
                      label={{ value: 'Amount (£)', angle: -90, position: 'insideLeft' }}
                    />
                    <Tooltip
                      formatter={(value: number) => `£${value.toFixed(2)}`}
                      contentStyle={{ backgroundColor: 'var(--fallback-b1,oklch(var(--b1)/1))' }}
                    />
                    <Legend />
                    <Bar
                      dataKey="total"
                      fill="#f87171"
                      name="Spending"
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}

              {chartView === 'timeline' && timelineData.length > 0 && (
                <ResponsiveContainer width="100%" height={400}>
                  <LineChart data={timelineData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="date"
                      angle={-45}
                      textAnchor="end"
                      height={100}
                      interval={Math.floor(timelineData.length / 10)}
                    />
                    <YAxis
                      label={{ value: 'Daily Spending (£)', angle: -90, position: 'insideLeft' }}
                    />
                    <Tooltip
                      formatter={(value: number) => `£${value.toFixed(2)}`}
                      contentStyle={{ backgroundColor: 'var(--fallback-b1,oklch(var(--b1)/1))' }}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey="total"
                      stroke="#f87171"
                      strokeWidth={2}
                      name="Daily Spending"
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}

              {chartView === 'category' && categoryData.length === 0 && (
                <div className="alert alert-info">
                  <span>No spending data for selected filters</span>
                </div>
              )}

              {chartView === 'timeline' && timelineData.length === 0 && (
                <div className="alert alert-info">
                  <span>No timeline data for selected filters</span>
                </div>
              )}
            </div>
          )}

          {/* Footer Info */}
          <div className="text-sm text-base-content/60 mt-4">
            Showing {filteredTransactions.length} of {transactions.length} transactions
          </div>
        </div>
      </div>
    </div>
  );
}
