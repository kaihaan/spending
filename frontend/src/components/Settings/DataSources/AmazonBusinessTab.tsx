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
import type { AmazonBusinessStats, AmazonBusinessOrder } from './types';

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

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

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

  // Pagination
  const totalPages = Math.ceil(orders.length / pageSize);
  const paginatedOrders = orders.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6">
      {/* Header with actions */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Amazon Business</h2>
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
                  No Amazon Business orders found
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
