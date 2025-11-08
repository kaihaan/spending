import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface AppleFile {
  filename: string;
  path: string;
}

interface AppleStats {
  total_transactions: number;
  min_transaction_date: string | null;
  max_transaction_date: string | null;
  total_spent: number;
  matched_transactions: number;
  unmatched_transactions: number;
}

interface AppleTransaction {
  id: number;
  order_id: string;
  order_date: string;
  total_amount: number;
  currency: string;
  app_names: string;
  publishers: string | null;
  item_count: number;
  source_file: string;
  created_at: string;
  matched_bank_transaction_id: number | null;
}

export default function AppleTransactions() {
  const [files, setFiles] = useState<AppleFile[]>([]);
  const [stats, setStats] = useState<AppleStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [matching, setMatching] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [transactions, setTransactions] = useState<AppleTransaction[]>([]);
  const [showTransactions, setShowTransactions] = useState(false);
  const [loadingTransactions, setLoadingTransactions] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);

      // Fetch available files and statistics in parallel
      const [filesRes, statsRes] = await Promise.all([
        axios.get<{files: AppleFile[], count: number}>(`${API_URL}/apple/files`),
        axios.get<AppleStats>(`${API_URL}/apple/statistics`)
      ]);

      setFiles(filesRes.data.files);
      setStats(statsRes.data);
    } catch (err) {
      console.error('Error fetching Apple data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    if (!selectedFile) {
      alert('Please select a file to import');
      return;
    }

    try {
      setImporting(true);

      const response = await axios.post(`${API_URL}/apple/import`, {
        filename: selectedFile
      });

      setShowImportDialog(false);
      setSelectedFile('');

      // Refresh statistics
      await fetchData();

      // Trigger refresh of transactions list
      window.dispatchEvent(new Event('transactions-updated'));

      // Show success message
      alert(`✓ Apple Transactions Import Complete!\n\nTransactions Imported: ${response.data.transactions_imported}\nDuplicates Skipped: ${response.data.transactions_duplicated}\n\nMatching Results:\n- Processed: ${response.data.matching_results.total_processed}\n- Matched: ${response.data.matching_results.matched}\n- Unmatched: ${response.data.matching_results.unmatched}`);
    } catch (err: any) {
      alert(`Import failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setImporting(false);
    }
  };

  const handleExportToCsv = async () => {
    if (!selectedFile) {
      alert('Please select a file to export');
      return;
    }

    try {
      setExporting(true);

      const response = await axios.post(`${API_URL}/apple/export-csv`, {
        filename: selectedFile
      });

      alert(`✓ CSV Export Complete!\n\nExported ${response.data.transactions_count} transactions to:\n${response.data.csv_file}`);
    } catch (err: any) {
      alert(`Export failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setExporting(false);
    }
  };

  const handleRunMatching = async () => {
    try {
      setMatching(true);

      const response = await axios.post(`${API_URL}/apple/match`);
      const results = response.data.results;

      await fetchData();

      // Trigger refresh of transactions list
      window.dispatchEvent(new Event('transactions-updated'));

      alert(`✓ Matching Complete!\n\nProcessed: ${results.total_processed} transactions\nMatched: ${results.matched}\nUnmatched: ${results.unmatched}`);
    } catch (err: any) {
      alert(`Matching failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setMatching(false);
    }
  };

  const handleClearData = async () => {
    if (!confirm('⚠️ Delete all Apple transactions data?\n\nThis will:\n- Remove all imported Apple transactions\n- Remove enhanced descriptions from matched bank transactions\n\nThis cannot be undone!')) {
      return;
    }

    try {
      const response = await axios.delete(`${API_URL}/apple`);

      await fetchData();

      // Trigger refresh of transactions list
      window.dispatchEvent(new Event('transactions-updated'));

      alert(`✓ Cleared ${response.data.transactions_deleted} transactions`);
    } catch (err: any) {
      alert(`Clear failed: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleToggleTransactions = async () => {
    if (!showTransactions && transactions.length === 0) {
      // Fetch transactions if not already loaded
      try {
        setLoadingTransactions(true);
        const response = await axios.get<{transactions: AppleTransaction[], count: number}>(`${API_URL}/apple`);
        setTransactions(response.data.transactions);
      } catch (err: any) {
        console.error('Error fetching transactions:', err);
        alert(`Failed to fetch transactions: ${err.response?.data?.error || err.message}`);
        return;
      } finally {
        setLoadingTransactions(false);
      }
    }
    setShowTransactions(!showTransactions);
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-GB');
  };

  const formatCurrency = (amount: number) => {
    return `£${Math.abs(amount).toFixed(2)}`;
  };

  if (loading) {
    return (
      <div className="mb-8">
        <h2 className="text-xl font-semibold mb-4">Apple Transactions</h2>
        <div className="flex justify-center items-center p-8">
          <span className="loading loading-spinner loading-lg"></span>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-8">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-xl font-semibold">Apple Transactions</h2>
          <p className="text-sm text-base-content/70">
            Import Apple/App Store purchase history to enhance bank transaction descriptions
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn btn-outline"
            onClick={handleRunMatching}
            disabled={matching || !stats || stats.total_transactions === 0}
          >
            {matching ? (
              <>
                <span className="loading loading-spinner loading-sm"></span>
                Matching...
              </>
            ) : (
              '🔄 Re-run Matching'
            )}
          </button>
          <button
            className="btn btn-primary"
            onClick={() => setShowImportDialog(true)}
          >
            + Import Apple Transactions
          </button>
        </div>
      </div>

      {/* Statistics Card */}
      {stats && stats.total_transactions > 0 ? (
        <div className="card bg-base-200 shadow mb-4">
          <div className="card-body">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="stat">
                <div className="stat-title">Total Transactions</div>
                <div className="stat-value text-primary">{stats.total_transactions}</div>
                <div className="stat-desc">Imported from Apple</div>
              </div>

              <div className="stat">
                <div className="stat-title">Total Spent</div>
                <div className="stat-value text-sm text-warning">{formatCurrency(stats.total_spent)}</div>
                <div className="stat-desc">App purchases</div>
              </div>

              <div className="stat">
                <div className="stat-title">Matched</div>
                <div className="stat-value text-success">{stats.matched_transactions}</div>
                <div className="stat-desc">Linked to bank transactions</div>
              </div>

              <div className="stat">
                <div className="stat-title">Unmatched</div>
                <div className="stat-value text-warning">{stats.unmatched_transactions}</div>
                <div className="stat-desc">Not yet matched</div>
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <button
                className="btn btn-sm btn-primary btn-outline"
                onClick={handleToggleTransactions}
                disabled={loadingTransactions}
              >
                {loadingTransactions ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Loading...
                  </>
                ) : showTransactions ? (
                  'Hide Transactions'
                ) : (
                  'View Transactions'
                )}
              </button>
              <button
                className="btn btn-sm btn-error btn-outline"
                onClick={handleClearData}
              >
                Clear All Data
              </button>
            </div>

            {/* Expandable Transactions List */}
            {showTransactions && transactions.length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold mb-3">Transactions List ({transactions.length})</h3>
                <div className="overflow-x-auto">
                  <table className="table table-sm table-zebra">
                    <thead>
                      <tr>
                        <th>Date</th>
                        <th>App Name(s)</th>
                        <th>Publisher</th>
                        <th>Amount</th>
                        <th>Items</th>
                        <th>Matched</th>
                      </tr>
                    </thead>
                    <tbody>
                      {transactions.map((txn) => (
                        <tr key={txn.id}>
                          <td>{formatDate(txn.order_date)}</td>
                          <td className="max-w-xs truncate" title={txn.app_names}>
                            {txn.app_names}
                          </td>
                          <td className="text-sm text-base-content/70">
                            {txn.publishers || 'N/A'}
                          </td>
                          <td className="text-warning">{formatCurrency(txn.total_amount)}</td>
                          <td className="text-center">{txn.item_count}</td>
                          <td>
                            {txn.matched_bank_transaction_id ? (
                              <span className="badge badge-success badge-sm">Yes</span>
                            ) : (
                              <span className="badge badge-warning badge-sm">No</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="alert alert-info">
          <span>
            No Apple transactions imported yet. Click "+ Import Apple Transactions" to get started!
          </span>
        </div>
      )}

      {/* Import Dialog */}
      {showImportDialog && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Import Apple Transactions</h3>

            <div className="py-4 space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Apple HTML File</span>
                </label>
                {files.length > 0 ? (
                  <select
                    className="select select-bordered"
                    value={selectedFile}
                    onChange={(e) => setSelectedFile(e.target.value)}
                  >
                    <option value="">Select a file...</option>
                    {files.map((file) => (
                      <option key={file.filename} value={file.filename}>
                        {file.filename}
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="alert alert-warning">
                    <span>No Apple HTML files found in /sample folder</span>
                  </div>
                )}
                <label className="label">
                  <span className="label-text-alt">
                    Place Apple "Report a Problem" HTML files in the /sample folder
                  </span>
                </label>
              </div>

              <div className="alert alert-info">
                <div className="text-sm">
                  <p className="font-semibold mb-1">How to export from Apple:</p>
                  <ol className="list-decimal list-inside text-xs space-y-1">
                    <li>Go to reportaproblem.apple.com</li>
                    <li>Sign in with your Apple ID</li>
                    <li>View your purchase history</li>
                    <li>Save the page as HTML (File → Save As → Web Page, Complete)</li>
                    <li>Place the HTML file in /sample folder</li>
                  </ol>
                </div>
              </div>

              {selectedFile && (
                <div className="flex gap-2">
                  <button
                    className="btn btn-sm btn-outline flex-1"
                    onClick={handleExportToCsv}
                    disabled={exporting}
                  >
                    {exporting ? (
                      <>
                        <span className="loading loading-spinner loading-xs"></span>
                        Exporting...
                      </>
                    ) : (
                      '📄 Export to CSV (Preview)'
                    )}
                  </button>
                </div>
              )}
            </div>

            <div className="modal-action">
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setShowImportDialog(false);
                  setSelectedFile('');
                }}
                disabled={importing}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleImport}
                disabled={!selectedFile || importing}
              >
                {importing ? (
                  <>
                    <span className="loading loading-spinner loading-sm"></span>
                    Importing...
                  </>
                ) : (
                  'Import'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
