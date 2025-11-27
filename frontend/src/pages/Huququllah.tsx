import { useState, useEffect } from 'react';
import axios from 'axios';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import type { Transaction, HuququllahSummary, HuququllahSuggestion } from '../types';

const API_URL = 'http://localhost:5000/api';

export default function Huququllah() {
  const [summary, setSummary] = useState<HuququllahSummary | null>(null);
  const [unclassified, setUnclassified] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [suggestions, setSuggestions] = useState<Record<number, HuququllahSuggestion>>({});

  useEffect(() => {
    fetchData();
  }, [dateFrom, dateTo]);

  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch summary
      const params = new URLSearchParams();
      if (dateFrom) params.append('date_from', dateFrom);
      if (dateTo) params.append('date_to', dateTo);

      const summaryResponse = await axios.get<HuququllahSummary>(`${API_URL}/huququllah/summary?${params}`);
      setSummary(summaryResponse.data);

      // Fetch unclassified transactions
      const unclassifiedResponse = await axios.get<Transaction[]>(`${API_URL}/huququllah/unclassified`);
      setUnclassified(unclassifiedResponse.data);

      // Fetch suggestions for unclassified transactions
      const suggestionsTemp: Record<number, HuququllahSuggestion> = {};
      for (const txn of unclassifiedResponse.data.slice(0, 10)) { // Get suggestions for first 10 only
        try {
          const suggestionResponse = await axios.get<HuququllahSuggestion>(
            `${API_URL}/huququllah/suggest/${txn.id}`
          );
          if (suggestionResponse.data.suggested_classification) {
            suggestionsTemp[txn.id] = suggestionResponse.data;
          }
        } catch (err) {
          console.error(`Failed to get suggestion for transaction ${txn.id}:`, err);
        }
      }
      setSuggestions(suggestionsTemp);
    } catch (err) {
      console.error('Failed to fetch Huququllah data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleClassify = async (transactionId: number, classification: 'essential' | 'discretionary') => {
    try {
      await axios.put(`${API_URL}/transactions/${transactionId}/huququllah`, { classification });
      fetchData(); // Refresh data
    } catch (err) {
      console.error('Failed to classify transaction:', err);
      alert('Failed to classify transaction');
    }
  };

  const clearDateFilters = () => {
    setDateFrom('');
    setDateTo('');
  };

  if (loading && !summary) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  const pieData = summary
    ? [
        { name: 'Essential', value: summary.essential_expenses, color: '#4ade80' },
        { name: 'Discretionary', value: summary.discretionary_expenses, color: '#a78bfa' }
      ].filter(item => item.value > 0)
    : [];

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <h2 className="card-title text-2xl">💝 Huququllah Tracker</h2>
          <p className="text-sm text-base-content/70 mb-4">
            Classify your expenses as essential or discretionary. Huququllah is calculated as 19% of discretionary expenses only (income is not included).
          </p>

          {/* Date Range Filter */}
          <div className="flex flex-wrap gap-2 items-center mb-6">
            <span className="text-sm font-semibold">Filter by Date Range:</span>
            <input
              type="date"
              className="input input-bordered input-sm"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              placeholder="From"
            />
            <span className="text-sm">to</span>
            <input
              type="date"
              className="input input-bordered input-sm"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              placeholder="To"
            />
            {(dateFrom || dateTo) && (
              <button className="btn btn-ghost btn-sm" onClick={clearDateFilters}>
                Clear Dates
              </button>
            )}
          </div>

          {/* Summary Cards */}
          {summary && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <div className="stats shadow">
                <div className="stat">
                  <div className="stat-title">Essential Expenses</div>
                  <div className="stat-value text-success">£{summary.essential_expenses.toFixed(2)}</div>
                  <div className="stat-desc">Not subject to Huququllah</div>
                </div>
              </div>

              <div className="stats shadow">
                <div className="stat">
                  <div className="stat-title">Discretionary Expenses</div>
                  <div className="stat-value text-secondary">£{summary.discretionary_expenses.toFixed(2)}</div>
                  <div className="stat-desc">Subject to 19% Huququllah</div>
                </div>
              </div>

              <div className="stats shadow bg-primary text-primary-content">
                <div className="stat">
                  <div className="stat-title text-primary-content/80">Huququllah Due (19%)</div>
                  <div className="stat-value">£{summary.huququllah_due.toFixed(2)}</div>
                  <div className="stat-desc text-primary-content/60">of discretionary spending</div>
                </div>
              </div>
            </div>
          )}

          {/* Pie Chart */}
          {summary && pieData.length > 0 && (
            <div className="bg-base-100 p-4 rounded-lg mb-6">
              <h3 className="text-lg font-semibold mb-4">Essential vs Discretionary Spending</h3>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    labelLine={false}
                    label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(1)}%`}
                    outerRadius={100}
                    fill="#8884d8"
                    dataKey="value"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value: number) => `£${value.toFixed(2)}`} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Unclassified Transactions */}
          {summary && summary.unclassified_count > 0 && (
            <div className="alert alert-warning mb-4">
              <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <span>{summary.unclassified_count} transaction(s) need classification</span>
            </div>
          )}

          {unclassified.length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-4">Unclassified Transactions</h3>
              <div className="overflow-x-auto">
                <table className="table table-zebra">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Description</th>
                      <th>Amount</th>
                      <th>Merchant</th>
                      <th>Suggestion</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {unclassified.map((txn) => {
                      const suggestion = suggestions[txn.id];
                      return (
                        <tr key={txn.id}>
                          <td>{txn.date}</td>
                          <td className="max-w-md truncate">{txn.description}</td>
                          <td className={txn.amount < 0 ? 'text-error font-semibold' : 'text-success font-semibold'}>
                            £{Math.abs(txn.amount).toFixed(2)}
                          </td>
                          <td className="text-sm text-base-content/70">{txn.merchant || '-'}</td>
                          <td>
                            {suggestion ? (
                              <div className="tooltip" data-tip={suggestion.reason}>
                                <span className={`badge whitespace-nowrap ${
                                  suggestion.suggested_classification === 'essential' ? 'badge-success' : 'badge-secondary'
                                }`}>
                                  {suggestion.suggested_classification} ({Math.round(suggestion.confidence * 100)}%)
                                </span>
                              </div>
                            ) : (
                              <span className="text-sm text-base-content/50">No suggestion</span>
                            )}
                          </td>
                          <td>
                            <div className="flex gap-2">
                              <button
                                className="btn btn-xs btn-success"
                                onClick={() => handleClassify(txn.id, 'essential')}
                                title="Mark as essential"
                              >
                                Essential
                              </button>
                              <button
                                className="btn btn-xs btn-secondary"
                                onClick={() => handleClassify(txn.id, 'discretionary')}
                                title="Mark as discretionary"
                              >
                                Discretionary
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {unclassified.length === 0 && summary && (
            <div className="alert alert-success">
              <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>All transactions have been classified!</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
