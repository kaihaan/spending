/**
 * GmailReceiptsTab Component
 *
 * Displays detailed view of Gmail receipts with metrics (including parsing status),
 * date range, and a paginated table of receipts.
 */

import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import SourceMetrics from './components/SourceMetrics';
import DateRangeIndicator from './components/DateRangeIndicator';
import type { GmailStats, GmailReceipt } from './types';

const API_URL = 'http://localhost:5000/api';

interface GmailReceiptsTabProps {
  stats: GmailStats | null;
  onStatsUpdate: () => void;
}

export default function GmailReceiptsTab({ stats, onStatsUpdate }: GmailReceiptsTabProps) {
  const [receipts, setReceipts] = useState<GmailReceipt[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isMatching, setIsMatching] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const fetchReceipts = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await axios.get<GmailReceipt[]>(`${API_URL}/gmail/receipts?user_id=1`);
      setReceipts(response.data);
    } catch (error) {
      console.error('Failed to fetch Gmail receipts:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReceipts();
  }, [fetchReceipts]);

  const handleMatch = async () => {
    setIsMatching(true);
    try {
      await axios.post(`${API_URL}/gmail/match`, { user_id: 1 });
      await fetchReceipts();
      onStatsUpdate();
    } catch (error) {
      console.error('Failed to run Gmail matching:', error);
    } finally {
      setIsMatching(false);
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
          <button
            className={`btn btn-primary btn-sm ${isMatching ? 'loading' : ''}`}
            onClick={handleMatch}
            disabled={isMatching}
          >
            {isMatching ? 'Matching...' : 'Run Matching'}
          </button>
        </div>
      </div>

      {/* Metrics - two rows for Gmail (includes parsing status) */}
      <div className="space-y-4">
        <SourceMetrics
          total={stats?.total_receipts ?? 0}
          matched={stats?.matched_receipts ?? 0}
          unmatched={(stats?.total_receipts ?? 0) - (stats?.matched_receipts ?? 0)}
          isLoading={!stats}
          labels={{ total: 'Receipts', matched: 'Matched', unmatched: 'Unmatched' }}
        />

        {/* Parsing Status Row */}
        {stats && (
          <div className="grid grid-cols-3 gap-4">
            <div className="stat bg-base-200 rounded-lg">
              <div className="stat-title">Parsed</div>
              <div className="stat-value text-xl text-success">
                {stats.parsed_receipts.toLocaleString()}
              </div>
            </div>
            <div className="stat bg-base-200 rounded-lg">
              <div className="stat-title">Pending</div>
              <div className="stat-value text-xl text-info">
                {stats.pending_receipts.toLocaleString()}
              </div>
            </div>
            <div className="stat bg-base-200 rounded-lg">
              <div className="stat-title">Failed</div>
              <div className="stat-value text-xl text-error">
                {stats.failed_receipts.toLocaleString()}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Date Range */}
      <DateRangeIndicator
        minDate={stats?.min_receipt_date ?? null}
        maxDate={stats?.max_receipt_date ?? null}
        isLoading={!stats}
      />

      {/* Receipts Table */}
      <div className="overflow-x-auto">
        <table className="table table-zebra">
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
                  No Gmail receipts found
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
                      `£${receipt.total_amount.toFixed(2)}`
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
