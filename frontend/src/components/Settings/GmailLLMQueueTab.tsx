import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

// Types
interface QueuedReceipt {
  id: number;
  message_id: string;
  subject: string;
  sender_email: string;
  sender_name: string | null;
  merchant_domain: string;
  received_at: string;
  snippet: string | null;
  parsing_error: string | null;
  llm_parse_status: string | null;
  estimated_cost_cents: number;
  connection_id: number;
}

interface QueueSummary {
  total_count: number;
  available_count: number;
  pending_count: number;
  processing_count: number;
  completed_count: number;
  failed_count: number;
  total_estimated_cost_cents: number;
  total_actual_cost_cents: number;
  provider: string;
  model: string;
  is_free_provider: boolean;
}

interface ProcessingProgress {
  status: string;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  total_cost_cents: number;
  current_receipt?: {
    id: number;
    success: boolean;
    error?: string;
  };
}

export default function GmailLLMQueueTab() {
  const [receipts, setReceipts] = useState<QueuedReceipt[]>([]);
  const [summary, setSummary] = useState<QueueSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

  // Processing state
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState<ProcessingProgress | null>(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  // Cost estimate for selection
  const selectedCost = receipts
    .filter(r => selectedIds.has(r.id))
    .reduce((sum, r) => sum + (r.estimated_cost_cents || 0), 0);

  // Fetch queue data
  const fetchQueue = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(`${API_URL}/gmail/llm-queue`);

      setReceipts(response.data.receipts || []);
      setSummary(response.data.summary || null);
    } catch (err) {
      console.error('Failed to fetch LLM queue:', err);
      setError('Failed to load LLM queue. Make sure Gmail is connected.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchQueue();
  }, [fetchQueue]);

  // Toggle single selection
  const toggleSelect = (id: number) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  // Select all / none
  const toggleSelectAll = () => {
    if (selectedIds.size === receipts.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(receipts.map(r => r.id)));
    }
  };

  // Format cost in dollars
  const formatCost = (cents: number) => {
    if (cents === 0) return 'Free';
    return `$${(cents / 100).toFixed(2)}`;
  };

  // Format date
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  // Process selected receipts
  const processSelected = async () => {
    if (selectedIds.size === 0) return;

    setShowConfirmModal(false);
    setProcessing(true);
    setProgress({
      status: 'starting',
      total: selectedIds.size,
      processed: 0,
      succeeded: 0,
      failed: 0,
      total_cost_cents: 0,
    });

    try {
      const response = await fetch(`${API_URL}/gmail/llm-queue/process`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ receipt_ids: Array.from(selectedIds) }),
      });

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              setProgress(data);
            } catch {
              // Ignore parse errors
            }
          }
        }
      }

      // Refresh data after completion
      await fetchQueue();
      setSelectedIds(new Set());
    } catch (err) {
      console.error('Processing error:', err);
      setError('Failed to process receipts. Check console for details.');
    } finally {
      setProcessing(false);
    }
  };

  // Render loading state
  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Render error state
  if (error) {
    return (
      <div className="alert alert-error">
        <span>{error}</span>
        <button className="btn btn-sm" onClick={fetchQueue}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <div className="stats stats-horizontal shadow w-full">
        <div className="stat">
          <div className="stat-title">Unparseable</div>
          <div className="stat-value text-2xl">{summary?.available_count || 0}</div>
          <div className="stat-desc">Available for LLM parsing</div>
        </div>

        <div className="stat">
          <div className="stat-title">Completed</div>
          <div className="stat-value text-2xl text-success">{summary?.completed_count || 0}</div>
          <div className="stat-desc">Successfully parsed</div>
        </div>

        <div className="stat">
          <div className="stat-title">Failed</div>
          <div className="stat-value text-2xl text-error">{summary?.failed_count || 0}</div>
          <div className="stat-desc">LLM also failed</div>
        </div>

        <div className="stat">
          <div className="stat-title">Provider</div>
          <div className="stat-value text-lg">{summary?.provider || 'N/A'}</div>
          <div className="stat-desc">{summary?.model || ''}</div>
        </div>
      </div>

      {/* Action Bar */}
      {receipts.length > 0 && (
        <div className="flex items-center justify-between bg-base-200 p-4 rounded-lg">
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="checkbox checkbox-sm"
                checked={selectedIds.size === receipts.length && receipts.length > 0}
                onChange={toggleSelectAll}
                disabled={processing}
              />
              <span className="text-sm">
                {selectedIds.size === receipts.length ? 'Deselect All' : 'Select All'}
              </span>
            </label>

            {selectedIds.size > 0 && (
              <span className="text-sm text-base-content/70">
                {selectedIds.size} selected
              </span>
            )}
          </div>

          <div className="flex items-center gap-4">
            {selectedIds.size > 0 && (
              <div className="text-sm">
                Est. Cost: <span className="font-semibold">{formatCost(selectedCost)}</span>
                {summary?.is_free_provider && (
                  <span className="badge badge-success badge-sm ml-2">Free Provider</span>
                )}
              </div>
            )}

            <button
              className="btn btn-primary btn-sm"
              disabled={selectedIds.size === 0 || processing}
              onClick={() => setShowConfirmModal(true)}
            >
              {processing ? (
                <>
                  <span className="loading loading-spinner loading-xs"></span>
                  Processing...
                </>
              ) : (
                `Parse Selected (${selectedIds.size})`
              )}
            </button>
          </div>
        </div>
      )}

      {/* Progress Bar */}
      {processing && progress && (
        <div className="bg-base-200 p-4 rounded-lg space-y-2">
          <div className="flex justify-between text-sm">
            <span>Processing {progress.processed} of {progress.total}</span>
            <span>
              {progress.succeeded} succeeded, {progress.failed} failed
            </span>
          </div>
          <progress
            className="progress progress-primary w-full"
            value={progress.processed}
            max={progress.total}
          ></progress>
          {progress.current_receipt && (
            <div className="text-xs text-base-content/60">
              {progress.current_receipt.success
                ? `Parsed receipt #${progress.current_receipt.id}`
                : `Failed: ${progress.current_receipt.error || 'Unknown error'}`}
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {receipts.length === 0 && !loading && (
        <div className="text-center py-12 text-base-content/60">
          <div className="text-4xl mb-4">🎉</div>
          <p className="text-lg">No unparseable receipts!</p>
          <p className="text-sm mt-2">
            All Gmail receipts have been successfully parsed using schema.org,
            vendor templates, or pattern matching.
          </p>
        </div>
      )}

      {/* Receipts Table */}
      {receipts.length > 0 && (
        <div className="overflow-x-auto">
          <table className="table table-sm">
            <thead>
              <tr>
                <th className="w-8"></th>
                <th>Subject</th>
                <th>Sender</th>
                <th>Date</th>
                <th className="text-right">Est. Cost</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {receipts.map((receipt) => (
                <tr
                  key={receipt.id}
                  className={`hover ${selectedIds.has(receipt.id) ? 'bg-primary/10' : ''}`}
                >
                  <td>
                    <input
                      type="checkbox"
                      className="checkbox checkbox-xs"
                      checked={selectedIds.has(receipt.id)}
                      onChange={() => toggleSelect(receipt.id)}
                      disabled={processing}
                    />
                  </td>
                  <td>
                    <div className="font-medium truncate max-w-xs" title={receipt.subject}>
                      {receipt.subject}
                    </div>
                    {receipt.snippet && (
                      <div className="text-xs text-base-content/50 truncate max-w-xs">
                        {receipt.snippet}
                      </div>
                    )}
                  </td>
                  <td>
                    <div className="text-sm">{receipt.merchant_domain}</div>
                    <div className="text-xs text-base-content/50">{receipt.sender_email}</div>
                  </td>
                  <td className="text-sm">
                    {formatDate(receipt.received_at)}
                  </td>
                  <td className="text-right text-sm">
                    {formatCost(receipt.estimated_cost_cents)}
                  </td>
                  <td>
                    {receipt.llm_parse_status === 'completed' ? (
                      <span className="badge badge-success badge-sm">Parsed</span>
                    ) : receipt.llm_parse_status === 'failed' ? (
                      <span className="badge badge-error badge-sm">Failed</span>
                    ) : receipt.llm_parse_status === 'processing' ? (
                      <span className="badge badge-warning badge-sm">Processing</span>
                    ) : (
                      <span className="badge badge-ghost badge-sm">Pending</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Confirmation Modal */}
      {showConfirmModal && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Confirm LLM Processing</h3>
            <div className="py-4 space-y-4">
              <p>
                You're about to parse <strong>{selectedIds.size}</strong> receipts using LLM.
              </p>

              <div className="bg-base-200 p-4 rounded-lg">
                <div className="flex justify-between">
                  <span>Provider:</span>
                  <span className="font-semibold">{summary?.provider}</span>
                </div>
                <div className="flex justify-between">
                  <span>Model:</span>
                  <span className="font-semibold">{summary?.model}</span>
                </div>
                <div className="flex justify-between">
                  <span>Estimated Cost:</span>
                  <span className="font-semibold text-lg">{formatCost(selectedCost)}</span>
                </div>
              </div>

              {summary?.is_free_provider && (
                <div className="alert alert-success">
                  <span>Using a free provider - no charges will apply.</span>
                </div>
              )}

              <p className="text-sm text-base-content/70">
                Each receipt will be re-fetched from Gmail and processed with the LLM.
                Actual cost may vary slightly from estimate.
              </p>
            </div>
            <div className="modal-action">
              <button
                className="btn btn-ghost"
                onClick={() => setShowConfirmModal(false)}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={processSelected}
              >
                Confirm & Process
              </button>
            </div>
          </div>
          <div className="modal-backdrop" onClick={() => setShowConfirmModal(false)}></div>
        </div>
      )}
    </div>
  );
}
