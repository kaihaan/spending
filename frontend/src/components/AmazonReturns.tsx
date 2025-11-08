import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface ReturnsFile {
  filename: string;
  path: string;
}

interface ReturnsStats {
  total_returns: number;
  min_return_date: string | null;
  max_return_date: string | null;
  total_refunded: number;
  matched_returns: number;
  unmatched_returns: number;
}

interface Return {
  id: number;
  order_id: string;
  reversal_id: string;
  refund_completion_date: string;
  currency: string;
  amount_refunded: number;
  status: string | null;
  disbursement_type: string | null;
  source_file: string;
  original_transaction_id: number | null;
  refund_transaction_id: number | null;
  created_at: string;
}

export default function AmazonReturns() {
  const [files, setFiles] = useState<ReturnsFile[]>([]);
  const [stats, setStats] = useState<ReturnsStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [matching, setMatching] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [returns, setReturns] = useState<Return[]>([]);
  const [showReturns, setShowReturns] = useState(false);
  const [loadingReturns, setLoadingReturns] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);

      // Fetch available files and statistics in parallel
      const [filesRes, statsRes] = await Promise.all([
        axios.get<{files: ReturnsFile[], count: number}>(`${API_URL}/amazon/returns/files`),
        axios.get<ReturnsStats>(`${API_URL}/amazon/returns/statistics`)
      ]);

      setFiles(filesRes.data.files);
      setStats(statsRes.data);
    } catch (err) {
      console.error('Error fetching returns data:', err);
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

      const response = await axios.post(`${API_URL}/amazon/returns/import`, {
        filename: selectedFile
      });

      setShowImportDialog(false);
      setSelectedFile('');

      // Refresh statistics
      await fetchData();

      // Trigger refresh of transactions list
      window.dispatchEvent(new Event('transactions-updated'));

      // Show success message
      alert(`✓ Returns Import Complete!\n\nReturns Imported: ${response.data.returns_imported}\nDuplicates Skipped: ${response.data.returns_duplicated}\n\nMatching Results:\n- Processed: ${response.data.matching_results.total_processed}\n- Matched: ${response.data.matching_results.matched}\n- Unmatched: ${response.data.matching_results.unmatched}`);
    } catch (err: any) {
      alert(`Import failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setImporting(false);
    }
  };

  const handleRunMatching = async () => {
    try {
      setMatching(true);

      const response = await axios.post(`${API_URL}/amazon/returns/match`);
      const results = response.data.results;

      await fetchData();

      // Trigger refresh of transactions list
      window.dispatchEvent(new Event('transactions-updated'));

      alert(`✓ Matching Complete!\n\nProcessed: ${results.total_processed} returns\nMatched: ${results.matched}\nUnmatched: ${results.unmatched}`);
    } catch (err: any) {
      alert(`Matching failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setMatching(false);
    }
  };

  const handleClearData = async () => {
    if (!confirm('⚠️ Delete all Amazon returns data?\n\nThis will:\n- Remove all imported returns\n- Remove [RETURNED] labels from transactions\n- Remove [REFUND] labels from refund transactions\n\nThis cannot be undone!')) {
      return;
    }

    try {
      const response = await axios.delete(`${API_URL}/amazon/returns`);

      await fetchData();

      // Trigger refresh of transactions list
      window.dispatchEvent(new Event('transactions-updated'));

      alert(`✓ Cleared ${response.data.returns_deleted} returns`);
    } catch (err: any) {
      alert(`Clear failed: ${err.response?.data?.error || err.message}`);
    }
  };

  const handleToggleReturns = async () => {
    if (!showReturns && returns.length === 0) {
      // Fetch returns if not already loaded
      try {
        setLoadingReturns(true);
        const response = await axios.get<{returns: Return[], count: number}>(`${API_URL}/amazon/returns`);
        setReturns(response.data.returns);
      } catch (err: any) {
        console.error('Error fetching returns:', err);
        alert(`Failed to fetch returns: ${err.response?.data?.error || err.message}`);
        return;
      } finally {
        setLoadingReturns(false);
      }
    }
    setShowReturns(!showReturns);
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
        <h2 className="text-xl font-semibold mb-4">Amazon Returns</h2>
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
          <h2 className="text-xl font-semibold">Amazon Returns</h2>
          <p className="text-sm text-base-content/70">
            Import Amazon returns to mark original purchases and label refund transactions
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn btn-outline"
            onClick={handleRunMatching}
            disabled={matching || !stats || stats.total_returns === 0}
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
            + Import Returns
          </button>
        </div>
      </div>

      {/* Statistics Card */}
      {stats && stats.total_returns > 0 ? (
        <div className="card bg-base-200 shadow mb-4">
          <div className="card-body">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="stat">
                <div className="stat-title">Total Returns</div>
                <div className="stat-value text-primary">{stats.total_returns}</div>
                <div className="stat-desc">Imported from CSV files</div>
              </div>

              <div className="stat">
                <div className="stat-title">Total Refunded</div>
                <div className="stat-value text-sm text-success">{formatCurrency(stats.total_refunded)}</div>
                <div className="stat-desc">Money returned</div>
              </div>

              <div className="stat">
                <div className="stat-title">Matched</div>
                <div className="stat-value text-success">{stats.matched_returns}</div>
                <div className="stat-desc">Linked to transactions</div>
              </div>

              <div className="stat">
                <div className="stat-title">Unmatched</div>
                <div className="stat-value text-warning">{stats.unmatched_returns}</div>
                <div className="stat-desc">Returns without matches</div>
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <button
                className="btn btn-sm btn-primary btn-outline"
                onClick={handleToggleReturns}
                disabled={loadingReturns}
              >
                {loadingReturns ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Loading...
                  </>
                ) : showReturns ? (
                  'Hide Returns'
                ) : (
                  'View Returns'
                )}
              </button>
              <button
                className="btn btn-sm btn-error btn-outline"
                onClick={handleClearData}
              >
                Clear All Returns
              </button>
            </div>

            {/* Expandable Returns List */}
            {showReturns && returns.length > 0 && (
              <div className="mt-6">
                <h3 className="text-lg font-semibold mb-3">Returns List ({returns.length})</h3>
                <div className="overflow-x-auto">
                  <table className="table table-sm table-zebra">
                    <thead>
                      <tr>
                        <th>Order ID</th>
                        <th>Refund Date</th>
                        <th>Amount</th>
                        <th>Status</th>
                        <th>Matched</th>
                      </tr>
                    </thead>
                    <tbody>
                      {returns.map((ret) => (
                        <tr key={ret.id}>
                          <td className="font-mono text-xs">{ret.order_id}</td>
                          <td>{formatDate(ret.refund_completion_date)}</td>
                          <td className="text-success">{formatCurrency(ret.amount_refunded)}</td>
                          <td>
                            <span className="badge badge-sm">
                              {ret.status || 'N/A'}
                            </span>
                          </td>
                          <td>
                            {ret.original_transaction_id && ret.refund_transaction_id ? (
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
            No Amazon returns imported yet. Click "+ Import Returns" to get started!
          </span>
        </div>
      )}

      {/* Import Dialog */}
      {showImportDialog && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Import Amazon Returns</h3>

            <div className="py-4 space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Returns CSV File</span>
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
                    <span>No returns CSV files found in /sample folder</span>
                  </div>
                )}
                <label className="label">
                  <span className="label-text-alt">
                    Place Amazon returns CSV files (with "return" in filename) in the /sample folder
                  </span>
                </label>
              </div>

              <div className="alert alert-info">
                <div className="text-sm">
                  <p className="font-semibold mb-1">How to export returns from Amazon:</p>
                  <ol className="list-decimal list-inside text-xs space-y-1">
                    <li>Go to Amazon Orders page</li>
                    <li>Click "Download order reports"</li>
                    <li>Select "Returns & Refunds" report type</li>
                    <li>Download CSV and place in /sample folder</li>
                  </ol>
                </div>
              </div>
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
