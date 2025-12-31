/**
 * GmailReceiptsTab Component
 *
 * Displays detailed view of Gmail receipts with metrics (including parsing status),
 * date range, and a paginated table of receipts.
 */

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../../api/client';
import { GmailDateRangeSelector, getDefaultDateRange } from '../../GmailDateRangeSelector';
import { GmailSyncProgressBar } from '../../GmailSyncProgressBar';
import type { GmailStats, GmailReceipt, GmailConnection } from './types';
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

const API_URL = 'http://localhost:5000/api'; // Keep for OAuth redirect URLs

interface GmailReceiptsTabProps {
  stats: GmailStats | null;
  onStatsUpdate: () => void;
}

interface BankStats {
  min_date: string | null;
  max_date: string | null;
  transaction_count: number;
}

export default function GmailReceiptsTab({ stats, onStatsUpdate }: GmailReceiptsTabProps) {
  const [receipts, setReceipts] = useState<GmailReceipt[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isMatching, setIsMatching] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Connection state
  const [connection, setConnection] = useState<GmailConnection | null>(null);
  const [connectionLoading, setConnectionLoading] = useState(true);

  // Bank stats for overlap calculation
  const [bankStats, setBankStats] = useState<BankStats | null>(null);

  // Sync state
  const [showSync, setShowSync] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isParsing, setIsParsing] = useState(false);
  const [syncJobId, setSyncJobId] = useState<number | null>(null);
  const [fromDate, setFromDate] = useState(() => getDefaultDateRange().fromDate);
  const [toDate, setToDate] = useState(() => getDefaultDateRange().toDate);
  const [syncResult, setSyncResult] = useState<{
    parsed: number;
    duplicates: number;
    failed: number;
  } | null>(null);

  const { style: glassStyle, className: glassClassName } = useTableStyles();

  const fetchReceipts = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get<GmailReceipt[]>('/gmail/receipts?user_id=1');
      setReceipts(response.data);
    } catch (error) {
      console.error('Failed to fetch Gmail receipts:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchConnection = useCallback(async () => {
    setConnectionLoading(true);
    try {
      const response = await apiClient.get('/gmail/connection');
      // Backend returns connection object directly, or null if not connected
      if (response.data?.id) {
        setConnection(response.data);
      } else {
        setConnection(null);
      }
    } catch (error) {
      console.error('Failed to fetch Gmail connection:', error);
      setConnection(null);
    } finally {
      setConnectionLoading(false);
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
    fetchReceipts();
    fetchConnection();
    fetchBankStats();
  }, [fetchReceipts, fetchConnection, fetchBankStats]);

  // Calculate overlap between Gmail receipts and bank transactions
  const getOverlapDateRange = (): { start: string; end: string } | null => {
    if (!stats?.min_receipt_date || !stats?.max_receipt_date) return null;
    if (!bankStats?.min_date || !bankStats?.max_date) return null;

    const gmailStart = new Date(stats.min_receipt_date);
    const gmailEnd = new Date(stats.max_receipt_date);
    const bankStart = new Date(bankStats.min_date);
    const bankEnd = new Date(bankStats.max_date);

    // Calculate overlap: max of starts, min of ends
    const overlapStart = gmailStart > bankStart ? gmailStart : bankStart;
    const overlapEnd = gmailEnd < bankEnd ? gmailEnd : bankEnd;

    // If no overlap, return null
    if (overlapStart > overlapEnd) return null;

    return {
      start: overlapStart.toISOString(),
      end: overlapEnd.toISOString(),
    };
  };

  // Check for saved Gmail sync job on mount and resume if still active
  useEffect(() => {
    const checkSavedJob = async () => {
      const savedJobId = localStorage.getItem('preai_gmail_job_id');
      if (!savedJobId) return;

      try {
        const response = await apiClient.get(`/gmail/sync/${savedJobId}`);
        const job = response.data;

        if (job.status === 'queued' || job.status === 'running') {
          setSyncJobId(parseInt(savedJobId));
          setIsSyncing(true);
          setShowSync(true);
        } else {
          localStorage.removeItem('preai_gmail_job_id');
        }
      } catch (err) {
        localStorage.removeItem('preai_gmail_job_id');
      }
    };

    checkSavedJob();
  }, []);

  // Handle Gmail OAuth callback
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const gmailStatus = params.get('gmail_status');
    const gmailError = params.get('gmail_error');
    const email = params.get('email');

    if (gmailStatus === 'connected') {
      alert(`Gmail connected successfully! Email: ${email || 'Unknown'}`);
      fetchConnection();
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
    } else if (gmailError) {
      alert(`Gmail connection failed: ${gmailError.replace(/\+/g, ' ')}`);
      window.history.replaceState({}, '', window.location.pathname + window.location.hash);
    }
  }, [fetchConnection]);

  const handleMatch = async () => {
    setIsMatching(true);
    try {
      await apiClient.post('/gmail/match', { user_id: 1 });
      await fetchReceipts();
      onStatsUpdate();
    } catch (error) {
      console.error('Failed to run Gmail matching:', error);
    } finally {
      setIsMatching(false);
    }
  };

  // Connection handlers
  const handleConnect = () => {
    window.location.href = `${API_URL}/gmail/authorize`;
  };

  const handleDisconnect = async () => {
    if (!connection) return;
    if (!confirm('Are you sure you want to disconnect Gmail? All synced receipts will be deleted.')) return;

    try {
      await apiClient.post('/gmail/disconnect', {
        connection_id: connection.id,
      });
      setConnection(null);
      await fetchReceipts();
      onStatsUpdate();
      window.dispatchEvent(new Event('transactions-updated'));
      alert('Gmail disconnected successfully');
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      alert(`Disconnect failed: ${error.response?.data?.error || error.message}`);
    }
  };

  // Sync handlers
  const handleSync = async () => {
    if (!connection) return;

    try {
      setIsSyncing(true);
      setSyncResult(null);
      setSyncJobId(null);

      const response = await apiClient.post('/gmail/sync', {
        connection_id: connection.id,
        sync_type: 'full',
        from_date: fromDate,
        to_date: toDate,
      });

      if (response.data.job_id) {
        setSyncJobId(response.data.job_id);
        localStorage.setItem('preai_gmail_job_id', response.data.job_id.toString());
      } else {
        // Sync was synchronous (rare case)
        setSyncResult(response.data);
        setIsSyncing(false);
        await fetchReceipts();
        onStatsUpdate();
        window.dispatchEvent(new Event('transactions-updated'));
      }
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      alert(`Sync failed: ${error.response?.data?.error || error.message}`);
      setIsSyncing(false);
    }
  };

  const handleSyncComplete = async (result: {
    parsed_receipts: number;
    total_messages: number;
    failed_messages: number;
  }) => {
    setSyncJobId(null);
    setIsSyncing(false);
    localStorage.removeItem('preai_gmail_job_id');
    setSyncResult({
      parsed: result.parsed_receipts,
      duplicates: result.total_messages - result.parsed_receipts - result.failed_messages,
      failed: result.failed_messages,
    });
    await fetchReceipts();
    onStatsUpdate();
    window.dispatchEvent(new Event('transactions-updated'));
  };

  const handleSyncError = (error: string) => {
    setSyncJobId(null);
    setIsSyncing(false);
    localStorage.removeItem('preai_gmail_job_id');
    alert(`Sync failed: ${error}`);
  };

  const handleParse = async () => {
    if (!connection) return;

    try {
      setIsParsing(true);
      const response = await apiClient.post('/gmail/parse', {
        connection_id: connection.id,
      });
      alert(`Parsed ${response.data.parsed} receipts successfully`);
      await fetchReceipts();
      onStatsUpdate();
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      alert(`Parsing failed: ${error.response?.data?.error || error.message}`);
    } finally {
      setIsParsing(false);
    }
  };

  // Pagination
  const totalPages = Math.ceil(receipts.length / pageSize);
  const paginatedReceipts = receipts.slice((page - 1) * pageSize, page * pageSize);

  // Parsing status badge
  const getParsingBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case 'parsed':
        return <span className="badge badge-success badge-sm">Parsed</span>;
      case 'pending':
        return <span className="badge badge-info badge-sm">Pending</span>;
      case 'failed':
        return <span className="badge badge-error badge-sm">Failed</span>;
      default:
        return <span className="badge badge-ghost badge-sm">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Header with actions */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Gmail Receipts</h2>
        <div className="flex gap-2">
          {connection ? (
            <>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setShowSync(!showSync)}
              >
                {showSync ? 'Cancel Sync' : 'Sync Receipts'}
              </button>
              <button
                className="btn btn-outline btn-sm"
                onClick={handleParse}
                disabled={isParsing}
              >
                {isParsing ? 'Parsing...' : 'Re-Parse'}
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
              {connectionLoading ? 'Loading...' : 'Connect Gmail'}
            </button>
          )}
          <button
            className={`btn btn-outline btn-sm ${isMatching ? 'loading' : ''}`}
            onClick={handleMatch}
            disabled={isMatching || receipts.length === 0}
          >
            {isMatching ? 'Matching...' : 'Run Matching'}
          </button>
        </div>
      </div>

      {/* Connection Status */}
      {connection && (
        <div className="flex items-center gap-2 text-sm text-success">
          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
          </svg>
          <span>Connected to {connection.email_address}</span>
          {connection.last_synced_at && (
            <span className="text-base-content/50">
              • Last synced: {new Date(connection.last_synced_at).toLocaleDateString()}
            </span>
          )}
        </div>
      )}

      {/* Sync Section */}
      {showSync && connection && (
        <div className="bg-base-200 border-l-4 border-primary p-4 rounded-r-lg">
          <div className="space-y-4">
            <div>
              <h3 className="font-medium mb-2">Sync Gmail Receipts</h3>
              <p className="text-sm text-base-content/70 mb-4">
                Select a date range to sync receipts from Gmail.
              </p>

              {/* Date Range Selector */}
              <div className="mb-4">
                <GmailDateRangeSelector
                  fromDate={fromDate}
                  toDate={toDate}
                  onFromDateChange={setFromDate}
                  onToDateChange={setToDate}
                  disabled={isSyncing}
                />
              </div>

              {/* Progress Bar */}
              {syncJobId && (
                <div className="mb-4">
                  <GmailSyncProgressBar
                    jobId={syncJobId}
                    onComplete={handleSyncComplete}
                    onError={handleSyncError}
                  />
                </div>
              )}

              {/* Sync Result */}
              {syncResult && (
                <div className="alert alert-success py-2 px-3 text-sm mb-4">
                  <div>
                    <strong>Sync Complete!</strong>
                    <p>
                      Parsed: {syncResult.parsed} | Skipped: {syncResult.duplicates} | Failed: {syncResult.failed}
                    </p>
                  </div>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex gap-2 justify-end">
                <button
                  className="btn btn-sm btn-ghost"
                  onClick={() => {
                    setShowSync(false);
                    setSyncResult(null);
                  }}
                  disabled={isSyncing}
                >
                  Close
                </button>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={handleSync}
                  disabled={isSyncing}
                >
                  {isSyncing ? (
                    <>
                      <span className="loading loading-spinner loading-xs"></span>
                      Syncing...
                    </>
                  ) : (
                    'Start Sync'
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Overview Panel */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Metrics - 2x2 grid */}
        <div className="bg-base-200 rounded-lg p-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-4">
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Receipts</div>
                {!stats ? (
                  <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
                ) : (
                  <div className="font-medium text-2xl">{stats.total_receipts.toLocaleString()}</div>
                )}
              </div>
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Matched</div>
                {!stats ? (
                  <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
                ) : (
                  <div className="font-medium text-2xl text-success">{stats.matched_receipts.toLocaleString()}</div>
                )}
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Parsed</div>
                {!stats ? (
                  <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
                ) : (
                  <div className="font-medium text-2xl text-success">{stats.parsed_receipts.toLocaleString()}</div>
                )}
              </div>
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Unmatched</div>
                {!stats ? (
                  <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
                ) : (
                  <div className="font-medium text-2xl text-warning">
                    {((stats.total_receipts ?? 0) - (stats.matched_receipts ?? 0)).toLocaleString()}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Date Ranges - stacked vertically */}
        <div className="bg-base-200 rounded-lg p-4 space-y-4">
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Receipts Date Range</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-48" />
            ) : stats.min_receipt_date && stats.max_receipt_date ? (
              <div className="font-medium">
                {formatDateRange(stats.min_receipt_date)} — {formatDateRange(stats.max_receipt_date)}
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

      {/* Receipts Table */}
      <div className={`overflow-x-auto rounded-lg ${glassClassName}`} style={glassStyle}>
        <table className="table">
          <thead>
            <tr>
              <th>Received</th>
              <th>Sender</th>
              <th>Subject</th>
              <th>Merchant</th>
              <th className="text-right">Amount</th>
              <th>Parse</th>
              <th>Match</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-32" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-48" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-24" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16 ml-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16" /></td>
                </tr>
              ))
            ) : paginatedReceipts.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 opacity-50">
                  {connection
                    ? 'No Gmail receipts found. Click "Sync Receipts" to fetch receipt emails.'
                    : 'Connect your Gmail account to sync receipt emails.'}
                </td>
              </tr>
            ) : (
              paginatedReceipts.map((receipt) => (
                <tr key={receipt.id}>
                  <td className="whitespace-nowrap">
                    {new Date(receipt.received_at).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="max-w-xs truncate" title={receipt.sender_email}>
                    {receipt.sender_email}
                  </td>
                  <td className="max-w-xs truncate" title={receipt.subject}>
                    {receipt.subject}
                  </td>
                  <td className="max-w-xs truncate" title={receipt.merchant_name || 'Unknown'}>
                    {receipt.merchant_name || <span className="opacity-50">Unknown</span>}
                  </td>
                  <td className="text-right font-mono">
                    {receipt.total_amount !== null ? (
                      `£${Number(receipt.total_amount).toFixed(2)}`
                    ) : (
                      <span className="opacity-50">-</span>
                    )}
                  </td>
                  <td>{getParsingBadge(receipt.parsing_status)}</td>
                  <td>
                    {receipt.matched_transaction_id ? (
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
