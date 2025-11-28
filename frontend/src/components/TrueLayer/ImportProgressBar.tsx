import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface Account {
  account_id: string;
  display_name: string;
  progress_status: 'pending' | 'syncing' | 'completed' | 'failed';
  synced_count: number;
  duplicates_count: number;
  errors_count: number;
}

interface JobStatus {
  job_id: number;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'enriching';
  progress: {
    completed_accounts: number;
    total_accounts: number;
    percent: number;
  };
  accounts: Account[];
  estimated_completion: string;
  total_so_far: {
    synced: number;
    duplicates: number;
    errors: number;
  };
}

interface ImportProgressBarProps {
  jobId: number;
  onComplete?: () => void;
}

const API_BASE = 'http://localhost:5000/api';

const getStatusBadgeColor = (status: string): string => {
  switch (status) {
    case 'completed':
      return 'badge-success';
    case 'syncing':
      return 'badge-info';
    case 'failed':
      return 'badge-error';
    default:
      return 'badge-ghost';
  }
};

const getStatusIcon = (status: string): string => {
  switch (status) {
    case 'completed':
      return '✓';
    case 'syncing':
      return '⟳';
    case 'failed':
      return '✗';
    default:
      return '○';
  }
};

export const ImportProgressBar: React.FC<ImportProgressBarProps> = ({ jobId, onComplete }) => {
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [isPolling, setIsPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Polling effect
  useEffect(() => {
    if (!isPolling) return;

    const pollStatus = async () => {
      try {
        const response = await axios.get<JobStatus>(`${API_BASE}/truelayer/import/status/${jobId}`);
        setJobStatus(response.data);
        setError(null);

        // Stop polling when job is completed or failed
        if (response.data.status === 'completed' || response.data.status === 'failed') {
          setIsPolling(false);
          if (onComplete) {
            setTimeout(onComplete, 2000); // Give user 2 seconds to see final state
          }
        }
      } catch (err: any) {
        setError(err.response?.data?.error || 'Failed to fetch status');
        setIsPolling(false);
      }
    };

    // Poll immediately and then every 2 seconds
    pollStatus();
    const interval = setInterval(pollStatus, 2000);

    return () => clearInterval(interval);
  }, [jobId, isPolling, onComplete]);

  if (!jobStatus) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg" />
      </div>
    );
  }

  const formatTime = (isoString?: string): string => {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleTimeString();
  };

  const formatDate = (isoString?: string): string => {
    if (!isoString) return 'N/A';
    const date = new Date(isoString);
    return date.toLocaleDateString();
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Import Progress</h2>

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
        </div>
      )}

      {/* Overall Progress */}
      <div className="card bg-base-100 border border-base-300">
        <div className="card-body">
          <div className="flex justify-between items-center mb-3">
            <div>
              <h3 className="font-semibold">Overall Progress</h3>
              <p className="text-sm text-gray-500">
                {jobStatus.progress.completed_accounts} of {jobStatus.progress.total_accounts} accounts
              </p>
            </div>
            <div className="text-3xl font-bold text-primary">{jobStatus.progress.percent}%</div>
          </div>
          <progress
            className="progress progress-primary w-full"
            value={jobStatus.progress.percent}
            max={100}
          />
        </div>
      </div>

      {/* Status Summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="card bg-success/10 border border-success/30">
          <div className="card-body p-4">
            <div className="text-2xl font-bold text-success">{jobStatus.total_so_far.synced}</div>
            <div className="text-xs text-gray-600">Transactions Synced</div>
          </div>
        </div>

        <div className="card bg-warning/10 border border-warning/30">
          <div className="card-body p-4">
            <div className="text-2xl font-bold text-warning">{jobStatus.total_so_far.duplicates}</div>
            <div className="text-xs text-gray-600">Duplicates Skipped</div>
          </div>
        </div>

        <div className="card bg-error/10 border border-error/30">
          <div className="card-body p-4">
            <div className="text-2xl font-bold text-error">{jobStatus.total_so_far.errors}</div>
            <div className="text-xs text-gray-600">Errors</div>
          </div>
        </div>
      </div>

      {/* Per-Account Progress */}
      <div className="space-y-3">
        <h3 className="font-semibold">Account Details</h3>

        {jobStatus.accounts.map((account, idx) => (
          <div
            key={`${account.account_id}-${idx}`}
            className="border rounded-lg p-4 hover:bg-base-50 transition"
          >
            <div className="flex justify-between items-start mb-2">
              <div className="flex-1">
                <div className="font-medium">{account.display_name}</div>
                <div className="text-xs text-gray-500">{account.account_id}</div>
              </div>
              <div className={`badge ${getStatusBadgeColor(account.progress_status)}`}>
                {getStatusIcon(account.progress_status)} {account.progress_status}
              </div>
            </div>

            {/* Account stats */}
            <div className="grid grid-cols-3 gap-2 text-sm mb-2">
              <div className="flex items-center gap-1">
                <span className="text-success">✓</span>
                <span>{account.synced_count} synced</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-warning">↻</span>
                <span>{account.duplicates_count} dupes</span>
              </div>
              <div className="flex items-center gap-1">
                <span className="text-error">✗</span>
                <span>{account.errors_count} errors</span>
              </div>
            </div>

            {/* Account progress bar (if syncing) */}
            {account.progress_status === 'syncing' && (
              <progress className="progress progress-info w-full h-2" value={50} max={100} />
            )}
          </div>
        ))}
      </div>

      {/* ETA */}
      <div className="card bg-base-200">
        <div className="card-body">
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <div className="text-gray-600">Est. Completion</div>
              <div className="font-mono">
                {jobStatus.estimated_completion
                  ? formatTime(jobStatus.estimated_completion)
                  : 'Computing...'}
              </div>
            </div>
            <div>
              <div className="text-gray-600">Current Status</div>
              <div className="font-mono capitalize">{jobStatus.status}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Status messages */}
      {jobStatus.status === 'completed' && (
        <div className="alert alert-success">
          <span>✓ Import completed successfully!</span>
        </div>
      )}

      {jobStatus.status === 'failed' && (
        <div className="alert alert-error">
          <span>✗ Import failed. Please try again.</span>
        </div>
      )}

      {jobStatus.status === 'enriching' && (
        <div className="alert alert-info">
          <span>⟳ Auto-enriching transactions with AI...</span>
        </div>
      )}

      {/* Close button */}
      {(jobStatus.status === 'completed' || jobStatus.status === 'failed') && (
        <button onClick={onComplete} className="btn btn-primary w-full">
          {jobStatus.status === 'completed' ? 'View Imported Transactions' : 'Close'}
        </button>
      )}
    </div>
  );
};
