import { useState } from 'react';
import axios from 'axios';
import FileList from '../components/FileList';

const API_URL = 'http://localhost:5000/api';

export default function Import() {
  const [clearing, setClearing] = useState(false);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const handleClearDatabase = async () => {
    try {
      setClearing(true);
      const response = await axios.delete(`${API_URL}/transactions/clear`);

      if (response.data.success) {
        // Dispatch event to refresh transaction list
        window.dispatchEvent(new Event('transactions-updated'));

        // Show success message
        alert(`Successfully cleared ${response.data.count} transaction(s)`);
      }
    } catch (err) {
      console.error('Failed to clear database:', err);
      alert('Failed to clear database. Please try again.');
    } finally {
      setClearing(false);
      setShowConfirmDialog(false);
    }
  };

  return (
    <div className="container mx-auto p-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h2 className="card-title text-2xl">📂 Import Bank Statements</h2>
              <p className="text-sm text-base-content/70 mt-2">
                Import Santander Excel bank statements (.xls or .xlsx files)
              </p>
            </div>

            <button
              className="btn btn-error btn-sm"
              onClick={() => setShowConfirmDialog(true)}
              disabled={clearing}
            >
              Clear Database
            </button>
          </div>

          <FileList />
        </div>
      </div>

      {/* Confirmation Dialog */}
      {showConfirmDialog && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Clear All Transactions?</h3>
            <p className="py-4">
              This will permanently delete all imported transactions from the database.
              This action cannot be undone.
            </p>
            <div className="modal-action">
              <button
                className="btn btn-ghost"
                onClick={() => setShowConfirmDialog(false)}
                disabled={clearing}
              >
                Cancel
              </button>
              <button
                className="btn btn-error"
                onClick={handleClearDatabase}
                disabled={clearing}
              >
                {clearing ? 'Clearing...' : 'Clear Database'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
