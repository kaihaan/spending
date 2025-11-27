import { useState } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface BankGiroChange {
  transaction_id: number;
  description: string;
  current_merchant: string;
  new_merchant: string;
}

export default function BankGiroMigration() {
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [changes, setChanges] = useState<BankGiroChange[]>([]);
  const [showPreview, setShowPreview] = useState(false);

  const handlePreviewChanges = async () => {
    try {
      setPreviewing(true);
      const response = await axios.get(`${API_URL}/migrations/fix-bank-giro-merchants/preview`);
      setChanges(response.data.changes);
      setShowPreview(true);

      if (response.data.count === 0) {
        alert('No bank giro transactions need fixing. All merchants are correctly classified!');
      }
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to preview changes');
    } finally {
      setPreviewing(false);
    }
  };

  const handleApplyChanges = async () => {
    if (!confirm(`This will update ${changes.length} bank giro transaction(s) to use the correct merchant name. Continue?`)) {
      return;
    }

    try {
      setApplying(true);
      const response = await axios.post(`${API_URL}/migrations/fix-bank-giro-merchants`);

      alert(`Success! ${response.data.fixed_count} bank giro transaction(s) have been updated.`);

      // Reset state
      setShowPreview(false);
      setChanges([]);

      // Refresh transactions list
      window.dispatchEvent(new Event('transactions-updated'));
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to apply changes');
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="mb-8">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xl font-semibold">Bank Giro Merchant Extraction</h2>
          <p className="text-sm text-base-content/70">
            Extract merchant names from bank giro credit transactions (e.g., "BANK GIRO CREDIT REF CITI PAYROLL, SALARY" → "CITI PAYROLL, SALARY")
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={handlePreviewChanges}
          disabled={previewing || applying}
        >
          {previewing ? (
            <>
              <span className="loading loading-spinner loading-sm"></span>
              Previewing...
            </>
          ) : (
            '👀 Preview Changes'
          )}
        </button>
      </div>

      {showPreview && changes.length > 0 && (
        <div className="card bg-base-200 shadow">
          <div className="card-body">
            <h3 className="font-semibold mb-4">
              Found {changes.length} bank giro transaction{changes.length !== 1 ? 's' : ''} to fix
            </h3>

            <div className="overflow-x-auto max-h-96 overflow-y-auto mb-4">
              <table className="table table-sm">
                <thead>
                  <tr>
                    <th>Description</th>
                    <th>Current Merchant</th>
                    <th>→</th>
                    <th>New Merchant</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((change) => (
                    <tr key={change.transaction_id}>
                      <td className="max-w-xs truncate text-sm">
                        {change.description}
                      </td>
                      <td>
                        <span className="badge badge-outline">
                          {change.current_merchant || 'N/A'}
                        </span>
                      </td>
                      <td className="text-center">→</td>
                      <td>
                        <span className="badge badge-success">
                          {change.new_merchant}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="alert alert-info mb-4">
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
              </svg>
              <span>
                These changes will update your bank giro transactions to use the correct merchant names. This helps with accurate spending categorization and analysis.
              </span>
            </div>

            <div className="flex gap-2">
              <button
                className="btn btn-success flex-1"
                onClick={handleApplyChanges}
                disabled={applying}
              >
                {applying ? (
                  <>
                    <span className="loading loading-spinner loading-sm"></span>
                    Applying...
                  </>
                ) : (
                  `✓ Apply ${changes.length} Change${changes.length !== 1 ? 's' : ''}`
                )}
              </button>
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setShowPreview(false);
                  setChanges([]);
                }}
                disabled={applying}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {showPreview && changes.length === 0 && (
        <div className="alert alert-success">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>
            Perfect! All your bank giro transactions already have correct merchant classifications. No changes needed.
          </span>
        </div>
      )}

      {!showPreview && changes.length === 0 && (
        <div className="alert alert-info">
          <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <span>
            Click "Preview Changes" to see if any bank giro transactions need merchant classification updates.
          </span>
        </div>
      )}
    </div>
  );
}
