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
    <div className="mb-8">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xl font-semibold">Lookup Description Sync</h2>
          <p className="text-sm text-base-content/70">
            Synchronize lookup descriptions from Amazon and Apple purchases. When you import Amazon orders or Apple transaction history, the Lookup column shows what you purchased.
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={handleRefresh}
          disabled={refreshing}
        >
          {refreshing ? (
            <>
              <span className="loading loading-spinner loading-sm"></span>
              Syncing...
            </>
          ) : (
            '🔄 Sync Lookups'
          )}
        </button>
      </div>

      {showResult && result && result.total > 0 && (
        <div className="card bg-base-200 shadow">
          <div className="card-body">
            <h3 className="font-semibold mb-4">Lookup Sync Complete</h3>

            <div className="grid grid-cols-3 gap-4 mb-4">
              <div className="stat bg-base-100 rounded-lg p-4">
                <div className="stat-title text-sm">Total Updated</div>
                <div className="stat-value text-2xl text-primary">{result.total}</div>
              </div>
              <div className="stat bg-base-100 rounded-lg p-4">
                <div className="stat-title text-sm">Amazon</div>
                <div className="stat-value text-2xl text-success">{result.amazon}</div>
              </div>
              <div className="stat bg-base-100 rounded-lg p-4">
                <div className="stat-title text-sm">Apple</div>
                <div className="stat-value text-2xl text-info">{result.apple}</div>
              </div>
            </div>

            <div className="alert alert-success">
              <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>
                Successfully updated {result.total} transaction{result.total !== 1 ? 's' : ''} with lookup descriptions. Your Lookup column is now synchronized!
              </span>
            </div>

            <button
              className="btn btn-ghost btn-sm mt-4"
              onClick={() => {
                setShowResult(false);
                setResult(null);
              }}
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {showResult && result && result.total === 0 && (
        <div className="alert alert-info">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>
            All matched transactions already have their lookup descriptions synchronized. No updates needed.
          </span>
        </div>
      )}

      {!showResult && (
        <div className="alert alert-info">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>
            Click "Sync Lookups" to update the Lookup column with product names from your imported Amazon orders and Apple purchases.
          </span>
        </div>
      )}
    </div>
  );
}
