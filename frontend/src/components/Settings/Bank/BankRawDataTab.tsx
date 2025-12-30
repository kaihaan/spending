/**
 * BankRawDataTab Component
 *
 * Displays a paginated table of raw TrueLayer transaction data.
 * Shows all fields from the TrueLayer ingest to help users understand their data sources.
 */

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../../api/client';

interface RawTransaction {
  id: number;
  transaction_id: string;
  timestamp: string | null;
  description: string;
  amount: number;
  currency: string;
  transaction_type: string;
  transaction_category: string | null;
  merchant_name: string | null;
  running_balance: number | null;
}

interface PaginatedResponse {
  transactions: RawTransaction[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export default function BankRawDataTab() {
  const [data, setData] = useState<PaginatedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.get<PaginatedResponse>('/truelayer/transactions/raw', {
        params: { page, page_size: pageSize },
      });
      setData(response.data);
    } catch (err) {
      console.error('Failed to fetch raw transactions:', err);
      setError('Failed to load raw transaction data');
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  const formatDateTime = (timestamp: string | null): string => {
    if (!timestamp) return '—';
    const date = new Date(timestamp);
    return date.toLocaleString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatAmount = (amount: number, currency: string): string => {
    const symbol = currency === 'GBP' ? '£' : currency === 'USD' ? '$' : currency === 'EUR' ? '€' : currency;
    const absAmount = Math.abs(amount);
    const formatted = absAmount.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return amount < 0 ? `-${symbol}${formatted}` : `${symbol}${formatted}`;
  };

  const formatBalance = (balance: number | null, currency: string): string => {
    if (balance === null) return '—';
    return formatAmount(balance, currency);
  };

  if (error) {
    return (
      <div className="alert alert-error">
        <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span>{error}</span>
        <button className="btn btn-sm" onClick={() => void fetchData()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">TrueLayer Raw Transactions</h3>
          <p className="text-sm text-base-content/60">
            Raw data from your connected bank accounts
          </p>
        </div>
        {data && (
          <div className="badge badge-neutral badge-lg">
            {data.total.toLocaleString()} transactions
          </div>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-base-300 rounded-lg">
        <table className="table table-sm">
          <thead className="bg-base-200">
            <tr>
              <th className="w-36">Date/Time</th>
              <th>Description</th>
              <th className="w-24 text-right">Amount</th>
              <th className="w-16 text-center">Type</th>
              <th className="w-32">Merchant</th>
              <th className="w-24 text-right">Balance</th>
              <th className="w-28">Category</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Loading skeleton
              Array.from({ length: 10 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td><div className="h-4 bg-base-300 rounded w-28" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-48" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16 ml-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-12 mx-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-24" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16 ml-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                </tr>
              ))
            ) : data?.transactions.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-base-content/60">
                  No transactions found. Connect a bank account to see raw data.
                </td>
              </tr>
            ) : (
              data?.transactions.map((txn) => (
                <tr key={txn.id} className="hover">
                  <td className="text-xs whitespace-nowrap">
                    {formatDateTime(txn.timestamp)}
                  </td>
                  <td className="max-w-xs truncate" title={txn.description}>
                    {txn.description}
                  </td>
                  <td className={`text-right font-mono text-sm ${txn.amount < 0 ? 'text-error' : 'text-success'}`}>
                    {formatAmount(txn.amount, txn.currency)}
                  </td>
                  <td className="text-center">
                    <span className={`badge badge-xs ${txn.transaction_type === 'DEBIT' ? 'badge-error' : 'badge-success'}`}>
                      {txn.transaction_type === 'DEBIT' ? 'OUT' : 'IN'}
                    </span>
                  </td>
                  <td className="text-sm truncate max-w-[8rem]" title={txn.merchant_name || ''}>
                    {txn.merchant_name || '—'}
                  </td>
                  <td className="text-right font-mono text-xs text-base-content/60">
                    {formatBalance(txn.running_balance, txn.currency)}
                  </td>
                  <td className="text-xs text-base-content/60 truncate max-w-[7rem]" title={txn.transaction_category || ''}>
                    {txn.transaction_category || '—'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-base-content/60">
            Showing {((page - 1) * pageSize) + 1}–{Math.min(page * pageSize, data.total)} of {data.total.toLocaleString()}
          </div>
          <div className="join">
            <button
              className="join-item btn btn-sm"
              disabled={page === 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <button className="join-item btn btn-sm btn-disabled">
              Page {page} of {data.total_pages}
            </button>
            <button
              className="join-item btn btn-sm"
              disabled={page >= data.total_pages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
