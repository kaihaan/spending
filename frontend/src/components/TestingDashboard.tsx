import { useState } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

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
    { id: 'truelayer_transactions', label: 'TrueLayer Transactions' },
    { id: 'legacy_transactions', label: 'Legacy Transactions' }
  ],
  'Linked Data': [
    { id: 'amazon_orders', label: 'Amazon Orders' },
    { id: 'amazon_matches', label: 'Amazon Matches' },
    { id: 'apple_transactions', label: 'Apple Transactions' },
    { id: 'apple_matches', label: 'Apple Matches' }
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
  const [isExpanded, setIsExpanded] = useState(false);
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
      const response = await axios.post<ClearResponse>(
        `${API_URL}/testing/clear?types=${typesParam}`
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
      'legacy_transactions': 'Legacy Transactions',
      'amazon_orders': 'Amazon Orders',
      'amazon_matches': 'Amazon Matches',
      'apple_transactions': 'Apple Transactions',
      'apple_matches': 'Apple Matches',
      'enrichment_cache': 'LLM Enrichment Cache',
      'import_history': 'Import Job History',
      'category_rules': 'Category Rules'
    };
    return labelMap[dataType] || dataType;
  };

  return (
    <div className="mb-8">
      <div className="collapse collapse-arrow border border-base-300 bg-base-100">
        <input
          type="checkbox"
          checked={isExpanded}
          onChange={(e) => setIsExpanded(e.target.checked)}
        />
        <div className="collapse-title text-xl font-medium">
          Dev Tools
        </div>
        <div className="collapse-content">
          {/* Warning message */}
          <div className="alert alert-warning mb-4">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 shrink-0 stroke-current" fill="none" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4v2m0 0v2m0-6v2m0-6v2m0-6v2M7 20h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v11a2 2 0 002 2z" />
            </svg>
            <span>
              Warning: Clearing data is permanent and cannot be undone. Use for testing only.
            </span>
          </div>

          {/* Error message */}
          {error && (
            <div className="alert alert-error mb-4">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 shrink-0 stroke-current" fill="none" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l-2-2m0 0l-2-2m2 2l2-2m-2 2l-2 2m2-2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
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
              className={`btn btn-error ${!isButtonEnabled || loading ? 'btn-disabled' : ''}`}
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
                className="btn btn-ghost"
                onClick={() => setShowConfirmDialog(false)}
                disabled={loading}
              >
                Cancel
              </button>
              <button
                className="btn btn-error"
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
                className="btn btn-primary"
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
