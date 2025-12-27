import { useState, useEffect } from 'react';
import axios from 'axios';
import { useFilters } from '../contexts/FilterContext';
import type { HuququllahSuggestion } from '../types';

const API_URL = 'http://localhost:5000/api';

export default function Huququllah() {
  const { filteredTransactions, loading, refreshTransactions } = useFilters();
  const [suggestions, setSuggestions] = useState<Record<number, HuququllahSuggestion>>({});
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);

  // Calculate Huququllah due from filtered transactions
  // Only DEBIT transactions classified as discretionary count
  const discretionaryExpenses = filteredTransactions
    .filter(txn => txn.huququllah_classification === 'discretionary' && txn.transaction_type === 'DEBIT')
    .reduce((sum, txn) => sum + parseFloat(String(txn.amount)), 0);

  const huququllahDue = discretionaryExpenses * 0.19;

  // Get unclassified DEBIT transactions from filtered set
  const unclassified = filteredTransactions.filter(
    txn => !txn.huququllah_classification && txn.transaction_type === 'DEBIT'
  );

  // Fetch suggestions for unclassified transactions
  useEffect(() => {
    const fetchSuggestions = async () => {
      if (unclassified.length === 0) {
        setSuggestions({});
        return;
      }

      setLoadingSuggestions(true);
      const suggestionsTemp: Record<number, HuququllahSuggestion> = {};

      for (const txn of unclassified.slice(0, 10)) {
        try {
          const response = await axios.get<HuququllahSuggestion>(
            `${API_URL}/huququllah/suggest/${txn.id}`
          );
          if (response.data.suggested_classification) {
            suggestionsTemp[txn.id] = response.data;
          }
        } catch (err) {
          console.error(`Failed to get suggestion for transaction ${txn.id}:`, err);
        }
      }
      setSuggestions(suggestionsTemp);
      setLoadingSuggestions(false);
    };

    void fetchSuggestions();
  }, [unclassified.map(t => t.id).join(',')]); // Re-fetch when unclassified IDs change

  const handleClassify = async (transactionId: number, classification: 'essential' | 'discretionary') => {
    try {
      await axios.put(`${API_URL}/transactions/${transactionId}/huququllah`, { classification });
      void refreshTransactions(); // Refresh from context
    } catch (err) {
      console.error('Failed to classify transaction:', err);
      alert('Failed to classify transaction');
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          {/* Huququllah Due & Unclassified Alert Row */}
          <div className="flex flex-wrap items-center gap-4 mb-6">
            <div className="alert alert-info">
              <span>Huququllah: £{huququllahDue.toFixed(2)}</span>
            </div>

            {unclassified.length > 0 && (
              <div className="alert alert-warning">
                <span>{unclassified.length} transaction(s) need classification</span>
                {loadingSuggestions && <span className="loading loading-spinner loading-sm ml-2"></span>}
              </div>
            )}
          </div>

          {/* Unclassified Transactions Table */}
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
                          <td className="text-error font-semibold">
                            £{parseFloat(String(txn.amount)).toFixed(2)}
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
                                onClick={() => void handleClassify(txn.id, 'essential')}
                                title="Mark as essential"
                              >
                                Essential
                              </button>
                              <button
                                className="btn btn-xs btn-secondary"
                                onClick={() => void handleClassify(txn.id, 'discretionary')}
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

          {unclassified.length === 0 && (
            <div className="alert alert-success">
              <span>All transactions in current filter have been classified!</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
