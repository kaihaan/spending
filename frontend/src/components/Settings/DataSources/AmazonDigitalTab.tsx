/**
 * AmazonDigitalTab Component
 *
 * Displays detailed view of Amazon digital orders (Kindle, Video, Music, Prime)
 * with metrics, date range, and a paginated table of orders.
 */

import React, { useState, useEffect, useCallback } from 'react';
import apiClient from '../../../api/client';
import type { AmazonDigitalStats, AmazonDigitalOrder } from './types';
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

interface AmazonDigitalTabProps {
  stats: AmazonDigitalStats | null;
  onStatsUpdate: () => void;
}

export default function AmazonDigitalTab({ stats, onStatsUpdate }: AmazonDigitalTabProps) {
  const [orders, setOrders] = useState<AmazonDigitalOrder[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Import state
  const [showImport, setShowImport] = useState(false);
  const [fileContent, setFileContent] = useState<string>('');
  const [selectedFileName, setSelectedFileName] = useState<string>('');
  const [isImporting, setIsImporting] = useState(false);

  const { style: glassStyle, className: glassClassName } = useTableStyles();

  const fetchOrders = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get<{ orders: AmazonDigitalOrder[]; count: number }>(
        '/amazon/digital'
      );
      setOrders(response.data.orders ?? []);
    } catch (error) {
      console.error('Failed to fetch Amazon digital orders:', error);
      setOrders([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  // Handle file selection
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setSelectedFileName(file.name);
    const reader = new FileReader();
    reader.onload = (event) => {
      setFileContent(event.target?.result as string);
    };
    reader.readAsText(file);
  };

  // Handle CSV import
  const handleImport = async () => {
    if (!fileContent) return;

    try {
      setIsImporting(true);
      const response = await apiClient.post('/amazon/digital/import', {
        csv_content: fileContent,
        filename: selectedFileName,
      });

      // Reset import state
      setShowImport(false);
      setFileContent('');
      setSelectedFileName('');

      // Refresh data
      await fetchOrders();
      onStatsUpdate();

      // Show results
      const data = response.data;
      const importCount = data.orders_imported ?? 0;
      const duplicates = data.orders_duplicated ?? 0;

      alert(
        `Import Complete!\n\nImported: ${importCount}\nDuplicates: ${duplicates}`
      );
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
        <h2 className="text-xl font-semibold">Amazon Digital Orders</h2>
        <div className="flex gap-2">
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowImport(!showImport)}
          >
            {showImport ? 'Cancel Import' : 'Import CSV'}
          </button>
        </div>
      </div>

      {/* Import Section */}
      {showImport && (
        <div className="bg-base-200 border-l-4 border-primary p-4 rounded-r-lg">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <p className="text-sm mb-2">
                Select an Amazon "Digital Items.csv" file to import (from Amazon order history export).
              </p>
              <input
                type="file"
                accept=".csv"
                className="file-input file-input-bordered file-input-sm w-full max-w-md"
                onChange={handleFileSelect}
              />
              {selectedFileName && (
                <span className="ml-2 text-sm text-success">{selectedFileName}</span>
              )}
            </div>
            <div className="flex gap-2">
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => {
                  setShowImport(false);
                  setFileContent('');
                  setSelectedFileName('');
                }}
                disabled={isImporting}
              >
                Cancel
              </button>
              <button
                className="btn btn-sm btn-primary"
                onClick={handleImport}
                disabled={!fileContent || isImporting}
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
            </div>
          </div>
        </div>
      )}

      {/* Overview Panel */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Orders & Matched - stacked vertically */}
        <div className="bg-base-200 rounded-lg p-4 space-y-4">
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Digital Orders</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
            ) : (
              <div className="font-medium text-2xl">{stats.total_orders.toLocaleString()}</div>
            )}
          </div>
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Matched</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
            ) : (
              <div className="font-medium text-2xl text-success">{stats.matched_orders.toLocaleString()}</div>
            )}
          </div>
        </div>

        {/* Date Range - stacked vertically */}
        <div className="bg-base-200 rounded-lg p-4 space-y-4">
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Orders Date Range</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-48" />
            ) : stats.min_order_date && stats.max_order_date ? (
              <div className="font-medium">
                {formatDateRange(stats.min_order_date)} — {formatDateRange(stats.max_order_date)}
              </div>
            ) : (
              <div className="text-base-content/50">No data</div>
            )}
          </div>
          <div>
            <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Bank Overlap</div>
            {!stats ? (
              <div className="animate-pulse h-5 bg-base-300 rounded w-48" />
            ) : stats.overlap_start && stats.overlap_end ? (
              <div className="font-medium">
                {formatDateRange(stats.overlap_start)} — {formatDateRange(stats.overlap_end)}
              </div>
            ) : (
              <div className="text-base-content/50">No overlap</div>
            )}
          </div>
        </div>
      </div>

      {/* Orders Table */}
      <div className={`overflow-x-auto rounded-lg ${glassClassName}`} style={glassStyle}>
        <table className="table">
          <thead>
            <tr>
              <th>Product Name</th>
              <th>Order Date</th>
              <th className="text-right">Price</th>
              <th>Publisher</th>
              <th>Match Status</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td><div className="h-4 bg-base-300 rounded w-48" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16 ml-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-24" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                </tr>
              ))
            ) : paginatedOrders.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 opacity-50">
                  No Amazon digital orders found. Click "Import CSV" to add orders.
                </td>
              </tr>
            ) : (
              paginatedOrders.map((order) => (
                <tr key={order.id}>
                  <td className="max-w-xs truncate" title={order.product_name}>
                    {order.product_name}
                  </td>
                  <td className="whitespace-nowrap">
                    {new Date(order.order_date).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="text-right font-mono">
                    {order.currency === 'GBP' ? '£' : order.currency}
                    {Number(order.price).toFixed(2)}
                  </td>
                  <td className="text-sm text-base-content/70">
                    {order.publisher || '—'}
                  </td>
                  <td>
                    {order.matched_transaction_id ? (
                      <span className="badge badge-success badge-sm">Matched</span>
                    ) : (
                      <span className="badge badge-ghost badge-sm">Unmatched</span>
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
