import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface GmailSyncJob {
  id: number;
  connection_id: number;
  status: 'pending' | 'queued' | 'running' | 'completed' | 'failed';
  job_type: 'full' | 'incremental';
  total_messages: number;
  processed_messages: number;
  parsed_receipts: number;
  failed_messages: number;
  sync_from_date: string | null;
  sync_to_date: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  progress_percentage: number;
  llm_cost_cents: number | null;
}

/**
 * Animated ellipses for loading states - gentle rippling dots
 * Uses larger bullet characters for better visibility
 */
const AnimatedEllipses: React.FC = () => (
  <span className="inline-flex ml-1 text-lg leading-none align-middle">
    <span className="animate-dot-pulse" style={{ animationDelay: '0s' }}>•</span>
    <span className="animate-dot-pulse mx-0.5" style={{ animationDelay: '0.2s' }}>•</span>
    <span className="animate-dot-pulse" style={{ animationDelay: '0.4s' }}>•</span>
  </span>
);

interface GmailSyncProgressBarProps {
  jobId: number;
  onComplete?: (result: GmailSyncJob) => void;
  onError?: (error: string) => void;
}

const API_URL = 'http://localhost:5000/api';
const POLL_INTERVAL = 2000; // 2 seconds

/**
 * Format seconds as MM:SS or HH:MM:SS
 */
const formatElapsed = (seconds: number): string => {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return h > 0
    ? `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
    : `${m}:${s.toString().padStart(2, '0')}`;
};

/**
 * Real-time progress bar for Gmail receipt sync.
 * Polls the job status endpoint every 2 seconds.
 */
export const GmailSyncProgressBar: React.FC<GmailSyncProgressBarProps> = ({
  jobId,
  onComplete,
  onError,
}) => {
  const [job, setJob] = useState<GmailSyncJob | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isPolling) return;

    const pollStatus = async () => {
      try {
        const response = await axios.get<GmailSyncJob>(`${API_URL}/gmail/sync/${jobId}`);
        const jobData = response.data;
        setJob(jobData);
        setError(null);

        // Stop polling when job is completed or failed (keep polling for pending/queued/running)
        if (jobData.status === 'completed' || jobData.status === 'failed') {
          setIsPolling(false);

          if (jobData.status === 'completed' && onComplete) {
            setTimeout(() => onComplete(jobData), 1500);
          }
          if (jobData.status === 'failed' && onError) {
            onError(jobData.error_message || 'Sync failed');
          }
        }
      } catch (err: any) {
        const errorMsg = err.response?.data?.error || 'Failed to fetch job status';
        setError(errorMsg);
        setIsPolling(false);
        if (onError) onError(errorMsg);
      }
    };

    // Poll immediately
    pollStatus();

    // Then poll at interval
    const interval = setInterval(pollStatus, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [jobId, isPolling, onComplete, onError]);

  // Loading state
  if (!job && !error) {
    return (
      <div className="flex items-center gap-3 p-3">
        <span className="text-sm text-base-content/70">
          Starting sync<AnimatedEllipses />
        </span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="alert alert-error py-2">
        <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-5 w-5" fill="none" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <span className="text-sm">{error}</span>
      </div>
    );
  }

  if (!job) return null;

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString();
  };

  const remaining = job.total_messages - job.processed_messages;

  // Timing calculations
  // For completed jobs, use completed_at; for running jobs, use current time
  const endTime = job.completed_at ? new Date(job.completed_at).getTime() : Date.now();
  const elapsedSeconds = job.started_at
    ? Math.floor((endTime - new Date(job.started_at).getTime()) / 1000)
    : 0;

  // Processing rate (messages per second)
  const rate = elapsedSeconds > 0
    ? job.processed_messages / elapsedSeconds
    : 0;

  // Estimated time remaining
  const etaSeconds = rate > 0 ? Math.ceil(remaining / rate) : null;

  return (
    <div className="space-y-3 p-3 bg-base-200 rounded-lg">
      {/* Date range */}
      {(job.sync_from_date || job.sync_to_date) && (
        <div className="text-xs text-base-content/60">
          Syncing emails from {formatDate(job.sync_from_date)} to {formatDate(job.sync_to_date)}
        </div>
      )}

      {/* Progress bar */}
      <div className="space-y-1">
        <div className="flex justify-between items-center text-sm">
          <span className="font-medium">
            {job.status === 'completed' ? 'Sync Complete' : 'Processing receipts...'}
          </span>
          <span className="text-base-content/70">{job.progress_percentage}%</span>
        </div>
        <progress
          className={`progress w-full ${
            job.status === 'completed' ? 'progress-success' :
            job.status === 'failed' ? 'progress-error' :
            'progress-primary'
          }`}
          value={job.progress_percentage}
          max={100}
        />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-4 gap-2 text-center">
        <div className="bg-base-100 rounded p-2">
          <div className="text-lg font-bold text-primary">{job.processed_messages}</div>
          <div className="text-xs text-base-content/60">Processed</div>
        </div>
        <div className="bg-base-100 rounded p-2">
          <div className="text-lg font-bold text-success">{job.parsed_receipts}</div>
          <div className="text-xs text-base-content/60">Stored</div>
        </div>
        <div className="bg-base-100 rounded p-2">
          <div className="text-lg font-bold text-warning">{remaining > 0 ? remaining : 0}</div>
          <div className="text-xs text-base-content/60">Remaining</div>
        </div>
        <div className="bg-base-100 rounded p-2">
          <div className="text-lg font-bold text-error">{job.failed_messages}</div>
          <div className="text-xs text-base-content/60">Failed</div>
        </div>
      </div>

      {/* Timing stats - show for queued, running, and completed jobs */}
      {(job.status === 'queued' || job.status === 'running' || job.status === 'completed') && (
        <div className="flex justify-between items-center text-sm px-1 py-2 border-t border-base-300">
          {job.status === 'queued' && !job.started_at ? (
            <span className="text-base-content/60 flex items-center">
              Waiting to start<AnimatedEllipses />
            </span>
          ) : (
            <>
              <span className="flex items-center gap-2">
                <span className="text-base-content/60">{job.status === 'completed' ? 'Total time:' : 'Elapsed:'}</span>
                <span className="font-mono font-medium">{elapsedSeconds > 0 ? formatElapsed(elapsedSeconds) : '0:00'}</span>
              </span>
              {rate > 0 && (
                <span className="flex items-center gap-2">
                  <span className="text-base-content/60">{job.status === 'completed' ? 'Avg rate:' : 'Rate:'}</span>
                  <span className="font-mono font-medium">{rate.toFixed(1)}/sec</span>
                </span>
              )}
              {job.status === 'running' && etaSeconds !== null && etaSeconds > 0 && (
                <span className="flex items-center gap-2">
                  <span className="text-base-content/60">ETA:</span>
                  <span className="font-mono font-medium">{formatElapsed(etaSeconds)}</span>
                </span>
              )}
            </>
          )}
        </div>
      )}

      {/* Status messages */}
      {job.status === 'completed' && (
        <div className="alert alert-success py-2">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-5 w-5" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="flex flex-col">
            <span className="text-sm">Sync completed! {job.parsed_receipts} receipts stored.</span>
            {job.llm_cost_cents != null && job.llm_cost_cents > 0 && (
              <span className="text-xs opacity-70">
                AI parsing cost: ${(job.llm_cost_cents / 100).toFixed(3)}
              </span>
            )}
          </div>
        </div>
      )}

      {job.status === 'failed' && job.error_message && (
        <div className="alert alert-error py-2">
          <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-5 w-5" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-sm">{job.error_message}</span>
        </div>
      )}
    </div>
  );
};
