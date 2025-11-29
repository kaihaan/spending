import { useState } from 'react';

interface CostEstimate {
  total_transactions: number;
  cached_available: number;
  requires_api_call: number;
  estimated_tokens: number;
  estimated_cost: number;
  currency: string;
  provider: string;
  model: string;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  estimate: CostEstimate | null;
  loading: boolean;
}

export default function EnrichmentCostModal({
  isOpen,
  onClose,
  onConfirm,
  estimate,
  loading
}: Props) {
  if (!isOpen) return null;

  return (
    <div className="modal modal-open">
      <div className="modal-box w-11/12 max-w-md">
        <h3 className="font-bold text-lg mb-4">Confirm Enrichment</h3>

        {loading ? (
          <div className="py-8 flex flex-col items-center gap-4">
            <span className="loading loading-spinner loading-lg"></span>
            <p className="text-sm text-base-content/70">Calculating cost...</p>
          </div>
        ) : estimate ? (
          <>
            <div className="space-y-4">
              <p className="text-base">
                Enrich <span className="font-semibold">{estimate.total_transactions}</span> transaction{estimate.total_transactions !== 1 ? 's' : ''}?
              </p>

              <div className="stats shadow bg-base-200 w-full">
                <div className="stat place-items-center">
                  <div className="stat-title text-sm">Estimated Cost</div>
                  <div className="stat-value text-3xl text-primary">
                    ${estimate.estimated_cost.toFixed(4)}
                  </div>
                  <div className="stat-desc text-xs">{estimate.currency}</div>
                </div>
              </div>

              <div className="bg-base-200 rounded-lg p-4 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-base-content/70">From cache (free):</span>
                  <span className="font-medium">{estimate.cached_available}</span>
                </div>
                <div className="divider my-2"></div>
                <div className="flex justify-between">
                  <span className="text-base-content/70">Require API calls:</span>
                  <span className="font-medium">{estimate.requires_api_call}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-base-content/70">Estimated tokens:</span>
                  <span className="font-medium">{estimate.estimated_tokens.toLocaleString()}</span>
                </div>
              </div>

              <div className="text-xs text-base-content/60 space-y-1">
                <p>Provider: <span className="font-medium">{estimate.provider}</span></p>
                <p>Model: <span className="font-medium">{estimate.model}</span></p>
              </div>
            </div>
          </>
        ) : (
          <p className="py-4 text-error text-center">Failed to estimate cost</p>
        )}

        <div className="modal-action gap-2 mt-6">
          <button className="btn btn-ghost" onClick={onClose} disabled={loading}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={onConfirm}
            disabled={loading || !estimate}
          >
            {loading ? (
              <>
                <span className="loading loading-spinner loading-sm"></span>
                Confirming...
              </>
            ) : (
              `Confirm ($${estimate?.estimated_cost.toFixed(4) || '0.00'})`
            )}
          </button>
        </div>
      </div>
      <div className="modal-backdrop" onClick={onClose} />
    </div>
  );
}
