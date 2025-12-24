import { useState } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface RefreshResult {
  total: number;
  amazon: number;
  apple: number;
}

export default function LookupDescriptionRefresh() {
  const [refreshing, setRefreshing] = useState(false);
  const [result, setResult] = useState<RefreshResult | null>(null);
  const [showResult, setShowResult] = useState(false);

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      const response = await axios.post(`${API_URL}/migrations/refresh-lookup-descriptions`);

      setResult(response.data.updated);
      setShowResult(true);

      if (response.data.updated.total === 0) {
        alert('No lookup descriptions needed updating. All matched transactions are up to date!');
      } else {
        // Refresh transactions list if any were updated
        window.dispatchEvent(new Event('transactions-updated'));
      }
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to refresh lookup descriptions');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="mb-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Lookup Sync</h3>
        <button
          className="btn btn-sm btn-primary"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          {refreshing ? (
            <>
              <span className="loading loading-spinner loading-sm"></span>
              Syncing...
            </>
          ) : (
            'Sync Lookups'
          )}
        </button>
      </div>

      {showResult && result && result.total > 0 && (
        <div className="border border-base-300 rounded-lg p-4">
          <div className="flex items-center gap-4 text-sm mb-3">
            <span className="font-medium">Total:</span> <span className="text-primary font-semibold">{result.total}</span>
            <span className="text-base-content/50">|</span>
            <span className="font-medium">Amazon:</span> <span className="text-success">{result.amazon}</span>
            <span className="text-base-content/50">|</span>
            <span className="font-medium">Apple:</span> <span className="text-info">{result.apple}</span>
          </div>

          <div className="alert alert-success">
            <span>
              Updated {result.total} transaction{result.total !== 1 ? 's' : ''} with lookup descriptions.
            </span>
          </div>

          <button
            className="btn btn-ghost btn-xs mt-3"
            onClick={() => {
              setShowResult(false);
              setResult(null);
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {showResult && result && result.total === 0 && (
        <div className="alert alert-info">
          <span>All lookup descriptions are already synchronized.</span>
        </div>
      )}

      {!showResult && (
        <div className="alert alert-info">
          <span>Click "Sync Lookups" to update transaction lookups with Amazon and Apple product names.</span>
        </div>
      )}
    </div>
  );
}
