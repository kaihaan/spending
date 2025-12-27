import { useState } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface BillPaymentChange {
  transaction_id: number;
  description: string;
  current_merchant: string;
  new_merchant: string;
}

export default function BillPaymentMigration() {
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [changes, setChanges] = useState<BillPaymentChange[]>([]);
  const [showPreview, setShowPreview] = useState(false);

  const handlePreviewChanges = async () => {
    try {
      setPreviewing(true);
      const response = await axios.get(`${API_URL}/migrations/fix-bill-payment-merchants/preview`);
      setChanges(response.data.changes);
      setShowPreview(true);

      if (response.data.count === 0) {
        alert('No bill payment transactions need fixing. All merchants are correctly classified!');
      }
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to preview changes');
    } finally {
      setPreviewing(false);
    }
  };

  const handleApplyChanges = async () => {
    if (!confirm(`This will update ${changes.length} bill payment transaction(s) to use the correct merchant name. Continue?`)) {
      return;
    }

    try {
      setApplying(true);
      const response = await axios.post(`${API_URL}/migrations/fix-bill-payment-merchants`);

      alert(`Success! ${response.data.fixed_count} bill payment transaction(s) have been updated.`);

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
          <h2 className="text-xl font-semibold">Bill Payment Merchant Extraction</h2>
          <p className="text-sm text-base-content/70">
            Extract merchant names from bill payment via faster payment transactions (e.g., "BILL PAYMENT VIA FASTER PAYMENT TO BRITISH GAS REFE..." → "BRITISH GAS")
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => void handlePreviewChanges()}
          disabled={previewing || applying}
        >
          {previewing ? (
            <>
              <span className="loading loading-spinner loading-sm"></span>
              Previewing...
            </>
          ) : (
            'Preview Changes'
          )}
        </button>
      </div>

      {showPreview && changes.length > 0 && (
        <div className="card bg-base-200 shadow">
          <div className="card-body">
            <h3 className="font-semibold mb-4">
              Found {changes.length} bill payment transaction{changes.length !== 1 ? 's' : ''} to fix
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
              <span>
                These changes will update your bill payment transactions to use the correct merchant names. This helps with accurate spending categorization and analysis.
              </span>
            </div>

            <div className="flex gap-2">
              <button
                className="btn btn-success flex-1"
                onClick={() => void handleApplyChanges()}
                disabled={applying}
              >
                {applying ? (
                  <>
                    <span className="loading loading-spinner loading-sm"></span>
                    Applying...
                  </>
                ) : (
                  `Apply ${changes.length} Change${changes.length !== 1 ? 's' : ''}`
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
          <span>
            Perfect! All your bill payment transactions already have correct merchant classifications. No changes needed.
          </span>
        </div>
      )}

      {!showPreview && changes.length === 0 && (
        <div className="alert alert-info">
          <span>
            Click "Preview Changes" to see if any bill payment transactions need merchant classification updates.
          </span>
        </div>
      )}
    </div>
  );
}
