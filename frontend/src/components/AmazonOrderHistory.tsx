import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface AmazonFile {
  filename: string;
  path: string;
}

interface AmazonStats {
  total_orders: number;
  min_order_date: string | null;
  max_order_date: string | null;
  total_matched: number;
  total_unmatched: number;
}

interface AmazonOrder {
  id: number;
  order_id: string;
  order_date: string;
  website: string;
  currency: string;
  total_owed: number;
  product_names: string;
  order_status: string | null;
  shipment_status: string | null;
  source_file: string;
  created_at: string;
}

export default function AmazonOrderHistory() {
  const [files, setFiles] = useState<AmazonFile[]>([]);
  const [stats, setStats] = useState<AmazonStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const [matching, setMatching] = useState(false);
  const [selectedFile, setSelectedFile] = useState<string>('');
  const [selectedWebsite, setSelectedWebsite] = useState<string>('Amazon.co.uk');
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importResult, setImportResult] = useState<any>(null);
  const [showOrders, setShowOrders] = useState(false);
  const [orders, setOrders] = useState<AmazonOrder[]>([]);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);

      // Fetch available files and statistics in parallel
      const [filesRes, statsRes] = await Promise.all([
        axios.get<{files: AmazonFile[], count: number}>(`${API_URL}/amazon/files`),
        axios.get<AmazonStats>(`${API_URL}/amazon/statistics`)
      ]);

      setFiles(filesRes.data.files);
      setStats(statsRes.data);
    } catch (err) {
      console.error('Error fetching Amazon data:', err);
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
      setImportResult(null);

      const response = await axios.post(`${API_URL}/amazon/import`, {
        filename: selectedFile,
        website: selectedWebsite
      });

      setImportResult(response.data);
      setShowImportDialog(false);
      setSelectedFile('');

      // Refresh statistics
      await fetchData();

      // Show success message
      alert(`✓ Amazon Import Complete!\n\nOrders Imported: ${response.data.orders_imported}\nDuplicates Skipped: ${response.data.orders_duplicated}\n\nMatching Results:\n- Processed: ${response.data.matching_results.total_processed}\n- Matched: ${response.data.matching_results.matched}\n- Unmatched: ${response.data.matching_results.unmatched}`);
    } catch (err: any) {
      alert(`Import failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setImporting(false);
    }
  };

  const handleRunMatching = async () => {
    try {
      setMatching(true);

      const response = await axios.post(`${API_URL}/amazon/match`);
      const results = response.data.results;

      await fetchData();

      alert(`✓ Matching Complete!\n\nProcessed: ${results.total_processed} transactions\nMatched: ${results.matched}\nUnmatched: ${results.unmatched}`);
    } catch (err: any) {
      alert(`Matching failed: ${err.response?.data?.error || err.message}`);
    } finally {
      setMatching(false);
    }
  };

  const handleClearData = async () => {
    if (!confirm('⚠️ Delete all Amazon orders and matches?\n\nThis will:\n- Remove all imported Amazon order history\n- Clear all transaction matches\n- Restore original transaction descriptions\n\nThis cannot be undone!')) {
      return;
    }

    try {
      const response = await axios.delete(`${API_URL}/amazon/orders`);

      await fetchData();

      alert(`✓ Cleared ${response.data.orders_deleted} orders and ${response.data.matches_deleted} matches`);
    } catch (err: any) {
      alert(`Clear failed: ${err.response?.data?.error || err.message}`);
    }
  };

  const toggleShowOrders = async () => {
    if (!showOrders && orders.length === 0) {
      try {
        const response = await axios.get<{orders: AmazonOrder[], count: number}>(`${API_URL}/amazon/orders`);
        setOrders(response.data.orders);
      } catch (err) {
        console.error('Error fetching orders:', err);
      }
    }
    setShowOrders(!showOrders);
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
        <h2 className="text-xl font-semibold mb-4">Amazon Order History</h2>
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
          <h2 className="text-xl font-semibold">Amazon Order History</h2>
          <p className="text-sm text-base-content/70">
            Import Amazon order CSVs to enrich transaction descriptions with product details
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="btn btn-outline"
            onClick={handleRunMatching}
            disabled={matching || !stats || stats.total_orders === 0}
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
            + Import Amazon Orders
          </button>
        </div>
      </div>

      {/* Statistics Card */}
      {stats && stats.total_orders > 0 ? (
        <div className="card bg-base-200 shadow mb-4">
          <div className="card-body">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="stat">
                <div className="stat-title">Total Orders</div>
                <div className="stat-value text-primary">{stats.total_orders}</div>
                <div className="stat-desc">Imported from CSV files</div>
              </div>

              <div className="stat">
                <div className="stat-title">Date Range</div>
                <div className="stat-value text-sm">
                  {formatDate(stats.min_order_date)} - {formatDate(stats.max_order_date)}
                </div>
                <div className="stat-desc">Order coverage period</div>
              </div>

              <div className="stat">
                <div className="stat-title">Matched</div>
                <div className="stat-value text-success">{stats.total_matched}</div>
                <div className="stat-desc">Transactions enriched</div>
              </div>

              <div className="stat">
                <div className="stat-title">Unmatched</div>
                <div className="stat-value text-warning">{stats.total_unmatched}</div>
                <div className="stat-desc">Amazon transactions without order data</div>
              </div>
            </div>

            <div className="flex gap-2 mt-4">
              <button
                className="btn btn-sm btn-outline"
                onClick={toggleShowOrders}
              >
                {showOrders ? 'Hide Orders' : 'View Orders'}
              </button>
              <button
                className="btn btn-sm btn-error btn-outline"
                onClick={handleClearData}
              >
                Clear All Data
              </button>
            </div>

            {/* Orders table */}
            {showOrders && (
              <div className="mt-4 overflow-x-auto">
                <table className="table table-sm">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Order ID</th>
                      <th>Products</th>
                      <th>Amount</th>
                      <th>Website</th>
                    </tr>
                  </thead>
                  <tbody>
                    {orders.slice(0, 20).map((order) => (
                      <tr key={order.id}>
                        <td className="text-xs">{formatDate(order.order_date)}</td>
                        <td className="text-xs">{order.order_id}</td>
                        <td className="text-xs max-w-md truncate">{order.product_names}</td>
                        <td className="text-xs">{formatCurrency(order.total_owed)}</td>
                        <td className="text-xs">{order.website}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {orders.length > 20 && (
                  <div className="text-center text-sm text-base-content/70 mt-2">
                    Showing first 20 of {orders.length} orders
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="alert alert-info">
          <span>
            No Amazon order history imported yet. Click "+ Import Amazon Orders" to get started!
          </span>
        </div>
      )}

      {/* Import Dialog */}
      {showImportDialog && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Import Amazon Order History</h3>

            <div className="py-4 space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Amazon Website</span>
                </label>
                <select
                  className="select select-bordered"
                  value={selectedWebsite}
                  onChange={(e) => setSelectedWebsite(e.target.value)}
                >
                  <option value="Amazon.co.uk">Amazon.co.uk (UK)</option>
                  <option value="Amazon.com">Amazon.com (US)</option>
                  <option value="Amazon Digital">Amazon Digital</option>
                  <option value="Amazon Marketplace">Amazon Marketplace</option>
                </select>
                <label className="label">
                  <span className="label-text-alt">Select the Amazon website for this order history</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">CSV File</span>
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
                    <span>No Amazon CSV files found in /sample folder</span>
                  </div>
                )}
                <label className="label">
                  <span className="label-text-alt">
                    Place Amazon order history CSV files in the /sample folder
                  </span>
                </label>
              </div>

              <div className="alert alert-info">
                <div className="text-sm">
                  <p className="font-semibold mb-1">How to export from Amazon:</p>
                  <ol className="list-decimal list-inside text-xs space-y-1">
                    <li>Go to Amazon Orders page</li>
                    <li>Click "Download order reports"</li>
                    <li>Select date range and "Items" report type</li>
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
