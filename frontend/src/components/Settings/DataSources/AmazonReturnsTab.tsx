/**
 * AmazonReturnsTab Component
 *
 * Displays detailed view of Amazon returns with metrics, date range,
 * and a paginated table of returns.
 */

import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import SourceMetrics from './components/SourceMetrics';
import DateRangeIndicator from './components/DateRangeIndicator';
import type { ReturnsStats, AmazonReturn } from './types';

const API_URL = 'http://localhost:5000/api';

interface AmazonReturnsTabProps {
  stats: ReturnsStats | null;
  onStatsUpdate: () => void;
}

export default function AmazonReturnsTab({ stats, onStatsUpdate }: AmazonReturnsTabProps) {
  const [returns, setReturns] = useState<AmazonReturn[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isMatching, setIsMatching] = useState(false);
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Import state
  const [showImport, setShowImport] = useState(false);
  const [fileContent, setFileContent] = useState<string>('');
  const [selectedFileName, setSelectedFileName] = useState<string>('');
  const [isImporting, setIsImporting] = useState(false);

  const fetchReturns = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await axios.get<{ returns: AmazonReturn[]; count: number }>(
        `${API_URL}/amazon/returns`
      );
      setReturns(response.data.returns ?? []);
    } catch (error) {
      console.error('Failed to fetch Amazon returns:', error);
      setReturns([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchReturns();
  }, [fetchReturns]);

  const handleMatch = async () => {
    setIsMatching(true);
    try {
      await axios.post(`${API_URL}/amazon/returns/match`);
      await fetchReturns();
      onStatsUpdate();
    } catch (error) {
      console.error('Failed to run returns matching:', error);
    } finally {
      setIsMatching(false);
    }
  };

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
      const response = await axios.post(`${API_URL}/amazon/returns/import`, {
        csv_content: fileContent,
        filename: selectedFileName,
      });

      // Reset import state
      setShowImport(false);
      setFileContent('');
      setSelectedFileName('');

      // Refresh data
      await fetchReturns();
      onStatsUpdate();
      window.dispatchEvent(new Event('transactions-updated'));

      // Show results
      const data = response.data;
      const importCount = data.returns_imported ?? 0;
      const duplicates = data.returns_duplicated ?? 0;
      const results = data.matching_results;

      alert(
        `Import Complete!\n\nImported: ${importCount}\nDuplicates: ${duplicates}\n\nMatching:\n- Processed: ${results.total_processed}\n- Matched: ${results.matched}\n- Unmatched: ${results.unmatched}`
      );
    } catch (err: unknown) {
      const error = err as { response?: { data?: { error?: string } }; message?: string };
      alert(`Import failed: ${error.response?.data?.error || error.message}`);
    } finally {
      setIsImporting(false);
    }
  };

  // Pagination
  const totalPages = Math.ceil(returns.length / pageSize);
  const paginatedReturns = returns.slice((page - 1) * pageSize, page * pageSize);

  return (
    <div className="space-y-6">
      {/* Header with actions */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Amazon Returns</h2>
        <div className="flex gap-2">
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setShowImport(!showImport)}
          >
            {showImport ? 'Cancel Import' : 'Import CSV'}
          </button>
          <button
            className={`btn btn-outline btn-sm ${isMatching ? 'loading' : ''}`}
            onClick={handleMatch}
            disabled={isMatching || returns.length === 0}
          >
            {isMatching ? 'Matching...' : 'Run Matching'}
          </button>
        </div>
      </div>

      {/* Import Section */}
      {showImport && (
        <div className="bg-base-200 border-l-4 border-primary p-4 rounded-r-lg">
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <p className="text-sm mb-2">
                Select an Amazon returns CSV file to import.
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

      {/* Metrics */}
      <SourceMetrics
        total={stats?.total_returns ?? 0}
        matched={stats?.matched_returns ?? 0}
        unmatched={stats?.unmatched_returns ?? 0}
        isLoading={!stats}
        labels={{ total: 'Returns', matched: 'Matched', unmatched: 'Unmatched' }}
      />

      {/* Date Range */}
      <DateRangeIndicator
        minDate={stats?.min_return_date ?? null}
        maxDate={stats?.max_return_date ?? null}
        isLoading={!stats}
      />

      {/* Returns Table */}
      <div className="overflow-x-auto">
        <table className="table table-zebra">
          <thead>
            <tr>
              <th>Order ID</th>
              <th>Refund Date</th>
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
            ) : paginatedReturns.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-center py-8 opacity-50">
                  No Amazon returns found. Click "Import CSV" to add returns.
                </td>
              </tr>
            ) : (
              paginatedReturns.map((ret) => (
                <tr key={ret.id}>
                  <td className="font-mono text-sm">{ret.order_id}</td>
                  <td className="whitespace-nowrap">
                    {new Date(ret.refund_completion_date).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="text-right font-mono text-success">
                    £{Number(ret.amount_refunded).toFixed(2)}
                  </td>
                  <td>
                    <span className="badge badge-ghost badge-sm">
                      {ret.status || 'Unknown'}
                    </span>
                  </td>
                  <td>
                    {ret.refund_transaction_id ? (
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
