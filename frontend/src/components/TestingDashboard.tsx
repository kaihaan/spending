import { useState } from 'react';
import apiClient from '../api/client';

interface DataTypeCheckbox {
  id: string;
  label: string;
  checked: boolean;
}

interface ClearResponse {
  success: boolean;
  cleared?: Record<string, number>;
  error?: string;
}

const DATA_TYPE_GROUPS = {
  'Bank Data': [
    { id: 'truelayer_transactions', label: 'TrueLayer Transactions' }
  ],
  'Linked Data': [
    { id: 'amazon_orders', label: 'Amazon Orders' },
    { id: 'truelayer_amazon_matches', label: 'Amazon Transaction Matches' },
    { id: 'apple_transactions', label: 'Apple Transactions' },
    { id: 'truelayer_apple_matches', label: 'Apple Transaction Matches' }
  ],
  'Gmail Data': [
    { id: 'gmail_receipts', label: 'Gmail Receipts (parsed data)' },
    { id: 'gmail_email_content', label: 'Gmail Email Content (raw emails)' },
    { id: 'gmail_transaction_matches', label: 'Gmail Transaction Matches' },
    { id: 'gmail_sync_jobs', label: 'Gmail Sync Job History' }
  ],
  'Metadata': [
    { id: 'enrichment_cache', label: 'LLM Enrichment Cache' },
    { id: 'import_history', label: 'Import Job History' },
    { id: 'category_rules', label: 'Category Rules' }
  ]
};

export default function TestingDashboard() {
  // Checkbox state
  const [checkboxes, setCheckboxes] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    Object.values(DATA_TYPE_GROUPS).forEach(group => {
      group.forEach(item => {
        initial[item.id] = false;
      });
    });
    return initial;
  });

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [successData, setSuccessData] = useState<Record<string, number> | null>(null);

  // Get selected types
  const getSelectedTypes = (): string[] => {
    return Object.entries(checkboxes)
      .filter(([_, checked]) => checked)
      .map(([id, _]) => id);
  };

  const selectedCount = getSelectedTypes().length;
  const isButtonEnabled = selectedCount > 0;

  // Handle checkbox change
  const handleCheckboxChange = (id: string) => {
    setCheckboxes(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
    setError(null);
  };

  // Get selected data type labels for confirmation
  const getSelectedLabels = (): string[] => {
    const selected: string[] = [];
    Object.values(DATA_TYPE_GROUPS).forEach(group => {
      group.forEach(item => {
        if (checkboxes[item.id]) {
          selected.push(item.label);
        }
      });
    });
    return selected;
  };

  // Handle clear operation
  const handleClearData = async () => {
    const selectedTypes = getSelectedTypes();
    if (selectedTypes.length === 0) {
      setError('Please select at least one data type');
      return;
    }

    setLoading(true);
    setError(null);
    setShowConfirmDialog(false);

    try {
      const typesParam = selectedTypes.join(',');
      const response = await apiClient.post<ClearResponse>(
        `/testing/clear?types=${typesParam}`
      );

      if (response.data.success && response.data.cleared) {
        setSuccessData(response.data.cleared);
        setShowSuccessModal(true);

        // Clear checkboxes after success
        setCheckboxes(prev => {
          const newState = { ...prev };
          Object.keys(newState).forEach(key => {
            newState[key] = false;
          });
          return newState;
        });
      } else {
        setError(response.data.error || 'An unexpected error occurred');
      }
    } catch (err: any) {
      const errorMessage =
        err.response?.data?.error ||
        err.message ||
        'Failed to clear data';
      setError(errorMessage);
      console.error('Clear data error:', err);
    } finally {
      setLoading(false);
    }
  };

  // Format data type name for display
  const formatDataTypeName = (dataType: string): string => {
    const labelMap: Record<string, string> = {
      'truelayer_transactions': 'TrueLayer Transactions',
      'amazon_orders': 'Amazon Orders',
      'truelayer_amazon_matches': 'Amazon Transaction Matches',
      'apple_transactions': 'Apple Transactions',
      'truelayer_apple_matches': 'Apple Transaction Matches',
      'gmail_receipts': 'Gmail Receipts',
      'gmail_email_content': 'Gmail Email Content',
      'gmail_transaction_matches': 'Gmail Transaction Matches',
      'gmail_sync_jobs': 'Gmail Sync Job History',
      'enrichment_cache': 'LLM Enrichment Cache',
      'import_history': 'Import Job History',
      'category_rules': 'Category Rules'
    };
    return labelMap[dataType] || dataType;
  };

  return (
    <div className="mb-8">
      <div className="border border-black/10 rounded-lg bg-base-100 p-4">
        <h3 className="text-xl font-medium mb-4">Dev Tools</h3>

        {/* Warning message */}
        <div className="alert alert-warning mb-4">
          <span>
            Warning: Clearing data is permanent and cannot be undone. Use for testing only.
          </span>
        </div>

        {/* Error message */}
        {error && (
          <div className="alert alert-error mb-4">
            <span>{error}</span>
          </div>
        )}

        {/* Checkbox groups */}
        <div className="space-y-4">
          {Object.entries(DATA_TYPE_GROUPS).map(([groupName, items]) => (
            <div key={groupName}>
              <h4 className="font-semibold text-sm mb-2">{groupName}</h4>
              <div className="space-y-2 pl-4">
                {items.map(item => (
                  <label key={item.id} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm"
                      checked={checkboxes[item.id]}
                      onChange={() => handleCheckboxChange(item.id)}
                      disabled={loading}
                    />
                    <span className="text-sm">{item.label}</span>
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Clear button */}
        <div className="mt-6 flex gap-2">
          <button
            className={`btn btn-sm btn-error ${!isButtonEnabled || loading ? 'btn-disabled' : ''}`}
            onClick={() => setShowConfirmDialog(true)}
            disabled={!isButtonEnabled || loading}
          >
            {loading ? (
              <>
                <span className="loading loading-spinner loading-sm"></span>
                Clearing...
              </>
            ) : (
              'Clear Selected Data'
            )}
          </button>
        </div>

        {/* Loading message */}
        {loading && (
          <div className="mt-4 flex items-center gap-2 text-sm text-base-content/70">
            <span className="loading loading-spinner loading-sm"></span>
            Clearing in progress...
          </div>
        )}
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Are you sure?</h3>
            <p className="py-4 text-sm">
              You are about to permanently delete:
            </p>
            <ul className="list-disc list-inside space-y-1 text-sm mb-4">
              {getSelectedLabels().map(label => (
                <li key={label}>{label}</li>
              ))}
            </ul>
            <p className="text-sm text-error font-semibold">
              This action cannot be undone.
            </p>
            <div className="modal-action">
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => setShowConfirmDialog(false)}
                disabled={loading}
              >
                Cancel
              </button>
              <button
                className="btn btn-sm btn-error"
                onClick={handleClearData}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <span className="loading loading-spinner loading-sm"></span>
                    Clearing...
                  </>
                ) : (
                  'Yes, Clear Data'
                )}
              </button>
            </div>
          </div>
          <div
            className="modal-backdrop"
            onClick={() => !loading && setShowConfirmDialog(false)}
          />
        </div>
      )}

      {/* Success Modal */}
      {showSuccessModal && successData && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg text-success">
              Data Cleared Successfully
            </h3>
            <div className="py-4 space-y-1 text-sm">
              {Object.entries(successData)
                .filter(([_, count]) => count > 0)
                .map(([dataType, count]) => (
                  <p key={dataType}>
                    <span className="font-medium">{formatDataTypeName(dataType)}:</span> {count} deleted
                  </p>
                ))}
            </div>
            {Object.values(successData).every(count => count === 0) && (
              <p className="text-sm text-base-content/70">
                No records found to delete for selected types.
              </p>
            )}
            <div className="modal-action">
              <button
                className="btn btn-sm btn-primary"
                onClick={() => setShowSuccessModal(false)}
              >
                Close
              </button>
            </div>
          </div>
          <div
            className="modal-backdrop"
            onClick={() => setShowSuccessModal(false)}
          />
        </div>
      )}
    </div>
  );
}
