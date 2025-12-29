/**
 * AmazonBusinessTab Component
 *
 * Displays detailed view of Amazon Business orders with metrics, date range,
 * and a paginated table of orders.
 */

import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import SourceMetrics from './components/SourceMetrics';
import DateRangeIndicator from './components/DateRangeIndicator';
import type { AmazonBusinessStats, AmazonBusinessOrder, AmazonBusinessConnection } from './types';

const API_URL = 'http://localhost:5000/api';

interface AmazonBusinessTabProps {
  stats: AmazonBusinessStats | null;
  onStatsUpdate: () => void;
}

export default function AmazonBusinessTab({ stats, onStatsUpdate }: AmazonBusinessTabProps) {
  const [orders, setOrders] = useState<AmazonBusinessOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isMatching, setIsMatching] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Connection state
  const [connection, setConnection] = useState<AmazonBusinessConnection | null>(null);
  const [connectionLoading, setConnectionLoading] = useState(true);

  // Import state
  const [showImport, setShowImport] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [importResult, setImportResult] = useState<{
    orders_imported: number;
    matching_results?: { matched: number; unmatched: number };
  } | null>(null);

  const fetchOrders = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await axios.get<AmazonBusinessOrder[]>(`${API_URL}/amazon-business/orders`);
      setOrders(response.data);
    } catch (error) {
      console.error('Failed to fetch Amazon Business orders:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchConnection = useCallback(async () => {
    setConnectionLoading(true);
    try {
      const response = await axios.get<AmazonBusinessConnection>(`${API_URL}/amazon-business/connection`);
      setConnection(response.data);
    } catch (error) {
      console.error('Failed to fetch Amazon Business connection:', error);
      setConnection(null);
    } finally {
      setConnectionLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
    fetchConnection();
  }, [fetchOrders, fetchConnection]);

  // Set default date range when opening import
  useEffect(() => {
    if (showImport && !dateFrom && !dateTo) {
      const today = new Date();
      const thirtyDaysAgo = new Date(today);
      thirtyDaysAgo.setDate(today.getDate() - 30);
      setDateFrom(thirtyDaysAgo.toISOString().split('T')[0]);
      setDateTo(today.toISOString().split('T')[0]);
    }
  }, [showImport, dateFrom, dateTo]);

  const handleMatch = async () => {
    setIsMatching(true);
    try {
      await axios.post(`${API_URL}/amazon-business/match`);
      await fetchOrders();
      onStatsUpdate();
    } catch (error) {
      console.error('Failed to run Amazon Business matching:', error);
    } finally {
      setIsMatching(false);
    }
  };

  // Connection handlers
  const handleConnect = async () => {
    try {
      const response = await axios.get(`${API_URL}/amazon-business/authorize`);
      if (response.data.success) {
        window.open(response.data.authorization_url, '_blank', 'width=600,height=700');
      } else {
        alert(`Connection failed: ${response.data.error}`);
      }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      alert(`Connection failed: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect Amazon Business?')) return;

    try {
      await axios.post(`${API_URL}/amazon-business/disconnect`);
      setConnection(null);
      await fetchConnection();
      onStatsUpdate();
      alert('Amazon Business disconnected');
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      alert(`Disconnect failed: ${error.response?.data?.error || error.message}`);
    }
  };

  const handleImport = async () => {
    if (!dateFrom || !dateTo) {
      alert('Please select date range');
      return;
    }

    try {
      setIsImporting(true);
      setImportResult(null);
      const response = await axios.post(`${API_URL}/amazon-business/import`, {
        start_date: dateFrom,
        end_date: dateTo,
        run_matching: true,
      });

      if (response.data.success) {
        setImportResult(response.data);
        await fetchOrders();
        onStatsUpdate();
        window.dispatchEvent(new Event('transactions-updated'));
      } else {
        alert(`Import failed: ${response.data.error}`);
      }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      alert(`Import failed: ${error.response?.data?.error || error.message}`);
    } finally {
      setIsImporting(false);
    }
  };

  // Pagination
  const totalPages = Math.ceil(orders.length / pageSize);
  const paginatedOrders = orders.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6">
      {/* Header with actions */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Amazon Business</h2>
        <div className="flex gap-2">
          {connection?.connected ? (
            <>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setShowImport(!showImport)}
              >
                {showImport ? 'Cancel Import' : 'Import Orders'}
              </button>
              <button
                className="btn btn-outline btn-sm btn-error"
                onClick={handleDisconnect}
              >
                Disconnect
              </button>
            </>
          ) : (
            <button
              className="btn btn-primary btn-sm"
              onClick={handleConnect}
              disabled={connectionLoading}
            >
              {connectionLoading ? 'Loading...' : 'Connect Amazon Business'}
            </button>
          )}
          <button
            className={`btn btn-outline btn-sm ${isMatching ? 'loading' : ''}`}
            onClick={handleMatch}
            disabled={isMatching || orders.length === 0}
          >
            {isMatching ? 'Matching...' : 'Run Matching'}
          </button>
        </div>
      </div>

      {/* Connection Status */}
      {connection?.connected && (
        <div className="flex items-center gap-2 text-sm text-success">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          <span>Connected to Amazon Business ({connection.region || 'UK'})</span>
        </div>
      )}

      {/* Import Section */}
      {showImport && connection?.connected && (
        <div className="bg-base-200 border-l-4 border-primary p-4 rounded-r-lg">
          <div className="space-y-4">
            <div>
              <h3 className="font-medium mb-2">Import Orders from API</h3>
              <p className="text-sm text-base-content/70 mb-4">
                Select a date range to import orders from Amazon Business.
              </p>

              <div className="flex items-end gap-4">
                <div>
                  <label className="label label-text text-sm">From</label>
                  <input
                    type="date"
                    className="input input-bordered input-sm"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                  />
                </div>
                <div>
                  <label className="label label-text text-sm">To</label>
                  <input
                    type="date"
                    className="input input-bordered input-sm"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                  />
                </div>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={handleImport}
                  disabled={isImporting || !dateFrom || !dateTo}
                >
                  {isImporting ? (
                    <>
                      <span className="loading loading-spinner loading-xs"></span>
                      Importing...
                    </>
                  ) : (
                    'Import'
                  )}
                </button>
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => {
                    setShowImport(false);
                    setImportResult(null);
                  }}
                  disabled={isImporting}
                >
                  Cancel
                </button>
              </div>
            </div>

            {importResult && (
              <div className="alert alert-success py-2 px-3 text-sm">
                <div>
                  <strong>Import Complete!</strong>
                  <p>
                    Orders imported: {importResult.orders_imported}
                    {importResult.matching_results && (
                      <> | Matched: {importResult.matching_results.matched} | Unmatched: {importResult.matching_results.unmatched}</>
                    )}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Metrics */}
      <SourceMetrics
        total={stats?.total_orders ?? 0}
        matched={stats?.total_matched ?? 0}
        unmatched={stats?.total_unmatched ?? 0}
        isLoading={!stats}
        labels={{ total: 'Orders', matched: 'Matched', unmatched: 'Unmatched' }}
      />

      {/* Date Range */}
      <DateRangeIndicator
        minDate={stats?.min_order_date ?? null}
        maxDate={stats?.max_order_date ?? null}
        isLoading={!stats}
      />

      {/* Orders Table */}
      <div className="overflow-x-auto">
        <table className="table table-zebra">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Date</th>
              <th className="text-right">Amount</th>
              <th>Status</th>
              <th>Match Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td><div className="h-4 bg-base-300 rounded w-24" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16 ml-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                </tr>
              ))
            ) : paginatedOrders.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 opacity-50">
                  {connection?.connected
                    ? 'No Amazon Business orders found. Click "Import Orders" to fetch orders.'
                    : 'Connect your Amazon Business account to import orders.'}
                </td>
              </tr>
            ) : (
              paginatedOrders.map((order) => (
                <tr key={order.id}>
                  <td className="font-mono text-sm">{order.order_id}</td>
                  <td className="whitespace-nowrap">
                    {new Date(order.order_date).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="text-right font-mono">
                    £{order.total_amount.toFixed(2)}
                  </td>
                  <td>
                    <span className="badge badge-ghost badge-sm">
                      {order.status || 'Unknown'}
                    </span>
                  </td>
                  <td>
                    {order.matched_transaction_id ? (
                      <span className="badge badge-success badge-sm">Matched</span>
                    ) : (
                      <span className="badge badge-warning badge-sm">Unmatched</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            className="btn btn-sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            Previous
          </button>
          <span className="flex items-center px-4">
            Page {page} of {totalPages}
          </span>
          <button
            className="btn btn-sm"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page === totalPages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
