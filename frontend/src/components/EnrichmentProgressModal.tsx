import { useEffect, useState } from 'react';
import axios from 'axios';

interface EnrichmentStatus {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  current?: number;
  total?: number;
  progress_percentage?: number;
  successful_enrichments?: number;
  failed_enrichments?: number;
  total_cost?: number;
  error?: string;
}

interface Props {
  isOpen: boolean;
  jobId: string | null;
  onComplete: () => void;
}

export default function EnrichmentProgressModal({
  isOpen,
  jobId,
  onComplete
}: Props) {
  const [status, setStatus] = useState<EnrichmentStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [intervalId, setIntervalId] = useState<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!jobId || !isOpen) return;

    const pollStatus = async () => {
      try {
        const response = await axios.get(`/api/enrichment/status/${jobId}`);
        const data = response.data as EnrichmentStatus;

        setStatus(data);
        setError(null);

        if (data.status === 'completed' || data.status === 'failed') {
          if (intervalId) clearInterval(intervalId);
          if (data.status === 'completed') {
            setTimeout(onComplete, 2000);
          }
        }
      } catch (err) {
        setError('Failed to check enrichment status');
        if (intervalId) clearInterval(intervalId);
      }
    };

    // Initial poll
    pollStatus();

    // Set up polling interval
    const id = setInterval(pollStatus, 2000);
    setIntervalId(id);

    return () => {
      if (id) clearInterval(id);
    };
  }, [jobId, isOpen, onComplete]);

  if (!isOpen) return null;

  const isComplete = status?.status === 'completed';
  const isFailed = status?.status === 'failed';
  const isRunning = status?.status === 'running';

  return (
    <div className="modal modal-open">
      <div className="modal-box w-11/12 max-w-md">
        {isComplete ? (
          <>
            <h3 className="font-bold text-lg text-success mb-4">Enrichment Complete</h3>
            <div className="space-y-3">
              <p>
                Successfully enriched{' '}
                <span className="font-semibold">{status?.successful_enrichments || 0}</span> of{' '}
                <span className="font-semibold">{status?.total}</span> transactions
              </p>
              <p className="text-sm text-base-content/70">
                Cost: <span className="font-medium">${(status?.total_cost || 0).toFixed(6)} USD</span>
              </p>
              {(status?.failed_enrichments || 0) > 0 && (
                <div className="alert alert-warning">
                  <span>
                    {status?.failed_enrichments} transaction{(status?.failed_enrichments || 0) !== 1 ? 's' : ''} failed (you can retry later)
                  </span>
                </div>
              )}
            </div>
          </>
        ) : isFailed ? (
          <>
            <h3 className="font-bold text-lg text-error mb-4">Enrichment Failed</h3>
            <p className="text-sm mb-4">{status?.error || 'Unknown error occurred'}</p>
            <div className="alert alert-error">
              <span>Please try again or check the logs for more details.</span>
            </div>
          </>
        ) : (
          <>
            <h3 className="font-bold text-lg mb-4">Enriching Transactions...</h3>
            <div className="space-y-4">
              <div>
                <progress
                  className="progress progress-primary w-full"
                  value={status?.progress_percentage || 0}
                  max="100"
                ></progress>
                <p className="text-sm text-center mt-2 font-medium">
                  {status?.progress_percentage || 0}%
                </p>
              </div>
              <p className="text-sm text-center text-base-content/70">
                {status?.current || 0} of {status?.total || 0} transactions processed
              </p>
              <div className="flex justify-center">
                <span className="loading loading-spinner loading-lg text-primary"></span>
              </div>
            </div>
          </>
        )}

        {(isComplete || isFailed || error) && (
          <div className="modal-action gap-2 mt-6">
            <button className="btn btn-primary" onClick={onComplete}>
              {isComplete ? 'Continue' : 'Close'}
            </button>
          </div>
        )}
      </div>
      <div className="modal-backdrop" />
    </div>
  );
}
