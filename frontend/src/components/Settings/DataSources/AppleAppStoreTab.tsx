/**
 * AppleAppStoreTab Component
 *
 * Displays detailed view of Apple App Store transactions with metrics,
 * date range, and a paginated table of transactions.
 */

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../../api/client';
import type { AppleStats, AppleTransaction } from './types';
import { useTableStyles } from '../../../hooks/useTableStyles';

/** Format date string to readable format like "01 Jan 2025" */
function formatDateRange(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

interface AppleAppStoreTabProps {
  stats: AppleStats | null;
  onStatsUpdate: () => void;
}

interface BankStats {
  min_date: string | null;
  max_date: string | null;
}

export default function AppleAppStoreTab({ stats, onStatsUpdate }: AppleAppStoreTabProps) {
  const [transactions, setTransactions] = useState<AppleTransaction[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isMatching, setIsMatching] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Bank stats for overlap calculation
  const [bankStats, setBankStats] = useState<BankStats | null>(null);

  const { style: glassStyle, className: glassClassName } = useTableStyles();

  // Browser import state
  const [showImport, setShowImport] = useState(false);
  const [browserStatus, setBrowserStatus] = useState<'idle' | 'launching' | 'ready' | 'scrolling' | 'capturing'>('idle');
  const [browserError, setBrowserError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<{
    imported: number;
    duplicates: number;
    matched: number;
  } | null>(null);

  const fetchTransactions = useCallback(async () => {
    setIsLoading(true);
    try {
      // API endpoint is /api/apple (not /api/apple/transactions)
      const response = await apiClient.get<{ transactions: AppleTransaction[]; count: number }>(
        '/apple'
      );
      setTransactions(response.data.transactions ?? []);
    } catch (error) {
      console.error('Failed to fetch Apple transactions:', error);
      setTransactions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchBankStats = useCallback(async () => {
    try {
      const response = await apiClient.get<BankStats>('/truelayer/statistics');
      setBankStats(response.data);
    } catch (error) {
      console.error('Failed to fetch bank stats:', error);
      setBankStats(null);
    }
  }, []);

  useEffect(() => {
    fetchTransactions();
    fetchBankStats();
  }, [fetchTransactions, fetchBankStats]);

  // Calculate overlap between Apple transactions and bank transactions
  const getOverlapDateRange = (): { start: string; end: string } | null => {
    if (!stats?.min_transaction_date || !stats?.max_transaction_date) return null;
    if (!bankStats?.min_date || !bankStats?.max_date) return null;

    const appleStart = new Date(stats.min_transaction_date);
    const appleEnd = new Date(stats.max_transaction_date);
    const bankStart = new Date(bankStats.min_date);
    const bankEnd = new Date(bankStats.max_date);

    const overlapStart = appleStart > bankStart ? appleStart : bankStart;
    const overlapEnd = appleEnd < bankEnd ? appleEnd : bankEnd;

    if (overlapStart > overlapEnd) return null;

    return { start: overlapStart.toISOString(), end: overlapEnd.toISOString() };
  };

  const handleMatch = async () => {
    setIsMatching(true);
    try {
      await apiClient.post('/apple/match');
      await fetchTransactions();
      onStatsUpdate();
    } catch (error) {
      console.error('Failed to run Apple matching:', error);
    } finally {
      setIsMatching(false);
    }
  };

  // Browser import handlers
  const handleBrowserStart = async () => {
    try {
      setBrowserStatus('launching');
      setBrowserError(null);
      setImportResult(null);

      await apiClient.post('/apple/import/browser-start');
      setBrowserStatus('ready');
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      setBrowserError(error.response?.data?.error || error.message || 'Failed to start browser');
      setBrowserStatus('idle');
    }
  };

  const handleBrowserCapture = async () => {
    try {
      setBrowserStatus('scrolling');
      setBrowserError(null);

      const response = await apiClient.post('/apple/import/browser-capture');
      const data = response.data;

      setImportResult({
        imported: data.transactions_imported,
        duplicates: data.transactions_duplicated,
        matched: data.matching_results?.matched || 0,
      });

      await fetchTransactions();
      onStatsUpdate();
      window.dispatchEvent(new Event('transactions-updated'));
      setBrowserStatus('idle');
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      setBrowserError(error.response?.data?.error || error.message || 'Failed to capture');
      setBrowserStatus('idle');
    }
  };

  const handleBrowserCancel = async () => {
    try {
      await apiClient.post('/apple/import/browser-cancel');
    } catch (err) {
      console.error('Error cancelling browser session:', err);
    }
    setBrowserStatus('idle');
    setBrowserError(null);
    setImportResult(null);
    setShowImport(false);
  };

  const handleImportClose = () => {
    if (browserStatus === 'ready') {
      handleBrowserCancel();
    } else {
      setShowImport(false);
      setBrowserStatus('idle');
      setBrowserError(null);
      setImportResult(null);
    }
  };

  // Pagination
  const totalPages = Math.ceil(transactions.length / pageSize);
  const paginatedTransactions = transactions.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6">
      {/* Header with actions */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Apple App Store</h2>
        <div className="flex gap-2">
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowImport(!showImport)}
          >
            {showImport ? 'Cancel Import' : 'Import from Browser'}
          </button>
          <button
            className={`btn btn-outline btn-sm ${isMatching ? 'loading' : ''}`}
            onClick={handleMatch}
            disabled={isMatching || transactions.length === 0}
          >
            {isMatching ? 'Matching...' : 'Run Matching'}
          </button>
        </div>
      </div>

      {/* Browser Import Section */}
      {showImport && (
        <div className="bg-base-200 border-l-4 border-primary p-4 rounded-r-lg">
          <div className="space-y-4">
            <div className="flex items-start gap-4">
              <div className="flex-1">
                <h3 className="font-medium mb-2">Browser-Based Import</h3>
                <p className="text-sm text-base-content/70 mb-4">
                  This will open a browser to Apple's purchase history page.
                  Log in if needed, then click "Capture" to import your transactions.
                </p>

                {/* Status display */}
                {browserStatus === 'launching' && (
                  <div className="flex items-center gap-2 text-info">
                    <span className="loading loading-spinner loading-sm"></span>
                    <span>Launching browser...</span>
                  </div>
                )}
                {browserStatus === 'ready' && (
                  <div className="flex items-center gap-2 text-success">
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Browser ready. Navigate to your purchase history, then click Capture.</span>
                  </div>
                )}
                {browserStatus === 'scrolling' && (
                  <div className="flex items-center gap-2 text-info">
                    <span className="loading loading-spinner loading-sm"></span>
                    <span>Scrolling and capturing transactions...</span>
                  </div>
                )}
                {browserError && (
                  <div className="alert alert-error py-2 px-3 text-sm">
                    {browserError}
                  </div>
                )}
                {importResult && (
                  <div className="alert alert-success py-2 px-3 text-sm">
                    <div>
                      <strong>Import Complete!</strong>
                      <p>Imported: {importResult.imported} | Duplicates: {importResult.duplicates} | Matched: {importResult.matched}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Action buttons */}
            <div className="flex gap-2 justify-end">
              <button
                className="btn btn-sm btn-ghost"
                onClick={handleImportClose}
                disabled={browserStatus === 'launching' || browserStatus === 'scrolling'}
              >
                {browserStatus === 'ready' ? 'Cancel & Close Browser' : 'Close'}
              </button>
              {browserStatus === 'idle' && !importResult && (
                <button
                  className="btn btn-sm btn-primary"
                  onClick={handleBrowserStart}
                >
                  Open Browser
                </button>
              )}
              {browserStatus === 'ready' && (
                <button
                  className="btn btn-sm btn-success"
                  onClick={handleBrowserCapture}
                >
                  Capture Transactions
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Overview Panel */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Transactions & Matched - stacked vertically */}
        <div className="bg-base-200 rounded-lg p-4 space-y-4">
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Transactions</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
            ) : (
              <div className="font-medium text-2xl">{stats.total_transactions.toLocaleString()}</div>
            )}
          </div>
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Matched</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
            ) : (
              <div className="font-medium text-2xl text-success">{stats.matched_transactions.toLocaleString()}</div>
            )}
          </div>
        </div>

        {/* Date Range - stacked vertically */}
        <div className="bg-base-200 rounded-lg p-4 space-y-4">
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Transactions Date Range</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-48" />
            ) : stats.min_transaction_date && stats.max_transaction_date ? (
              <div className="font-medium">
                {formatDateRange(stats.min_transaction_date)} — {formatDateRange(stats.max_transaction_date)}
              </div>
            ) : (
              <div className="text-base-content/50">No data</div>
            )}
          </div>
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Bank Overlap</div>
            {!stats || !bankStats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-48" />
            ) : (() => {
              const overlap = getOverlapDateRange();
              return overlap ? (
                <div className="font-medium">
                  {formatDateRange(overlap.start)} — {formatDateRange(overlap.end)}
                </div>
              ) : (
                <div className="text-base-content/50">No overlap</div>
              );
            })()}
          </div>
        </div>
      </div>

      {/* Transactions Table */}
      <div className={`overflow-x-auto rounded-lg ${glassClassName}`} style={glassStyle}>
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Apps</th>
              <th>Publisher</th>
              <th className="text-right">Amount</th>
              <th className="text-center">Items</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-32" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-24" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16 ml-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-8 mx-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                </tr>
              ))
            ) : paginatedTransactions.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-8 opacity-50">
                  No Apple transactions found. Click "Import from Browser" to add transactions.
                </td>
              </tr>
            ) : (
              paginatedTransactions.map((txn) => (
                <tr key={txn.id}>
                  <td className="whitespace-nowrap">
                    {new Date(txn.order_date).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="max-w-xs truncate" title={txn.app_names}>
                    {txn.app_names}
                  </td>
                  <td className="max-w-xs truncate" title={txn.publishers || 'Unknown'}>
                    {txn.publishers || 'Unknown'}
                  </td>
                  <td className="text-right font-mono">
                    £{Number(txn.total_amount).toFixed(2)}
                  </td>
                  <td className="text-center">
                    <span className="badge badge-ghost badge-sm">{txn.item_count}</span>
                  </td>
                  <td>
                    {txn.matched_bank_transaction_id ? (
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
