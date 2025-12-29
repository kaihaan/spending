/**
 * AppleAppStoreTab Component
 *
 * Displays detailed view of Apple App Store transactions with metrics,
 * date range, and a paginated table of transactions.
 */

import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import SourceMetrics from './components/SourceMetrics';
import DateRangeIndicator from './components/DateRangeIndicator';
import type { AppleStats, AppleTransaction } from './types';

const API_URL = 'http://localhost:5000/api';

interface AppleAppStoreTabProps {
  stats: AppleStats | null;
  onStatsUpdate: () => void;
}

export default function AppleAppStoreTab({ stats, onStatsUpdate }: AppleAppStoreTabProps) {
  const [transactions, setTransactions] = useState<AppleTransaction[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isMatching, setIsMatching] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const fetchTransactions = useCallback(async () => {
    setIsLoading(true);
    try {
      // API endpoint is /api/apple (not /api/apple/transactions)
      const response = await axios.get<{ transactions: AppleTransaction[]; count: number }>(
        `${API_URL}/apple`
      );
      setTransactions(response.data.transactions ?? []);
    } catch (error) {
      console.error('Failed to fetch Apple transactions:', error);
      setTransactions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const handleMatch = async () => {
    setIsMatching(true);
    try {
      await axios.post(`${API_URL}/apple/match`);
      await fetchTransactions();
      onStatsUpdate();
    } catch (error) {
      console.error('Failed to run Apple matching:', error);
    } finally {
      setIsMatching(false);
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
            className={`btn btn-primary btn-sm ${isMatching ? 'loading' : ''}`}
            onClick={handleMatch}
            disabled={isMatching}
          >
            {isMatching ? 'Matching...' : 'Run Matching'}
          </button>
        </div>
      </div>

      {/* Metrics */}
      <SourceMetrics
        total={stats?.total_transactions ?? 0}
        matched={stats?.matched_transactions ?? 0}
        unmatched={stats?.unmatched_transactions ?? 0}
        isLoading={!stats}
        labels={{ total: 'Transactions', matched: 'Matched', unmatched: 'Unmatched' }}
      />

      {/* Date Range */}
      <DateRangeIndicator
        minDate={stats?.min_transaction_date ?? null}
        maxDate={stats?.max_transaction_date ?? null}
        isLoading={!stats}
      />

      {/* Transactions Table */}
      <div className="overflow-x-auto">
        <table className="table table-zebra">
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
                  No Apple transactions found
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
                    £{txn.total_amount.toFixed(2)}
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
