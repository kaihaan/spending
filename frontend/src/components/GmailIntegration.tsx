import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface GmailConnection {
  id: number;
  email_address: string;
  connection_status: string;
  last_synced_at: string | null;
  sync_from_date: string | null;
}

interface GmailStats {
  total_receipts: number;
  parsed_receipts: number;
  matched_receipts: number;
  pending_receipts: number;
  failed_receipts: number;
}

interface SyncProgress {
  status: string;
  total_messages?: number;
  processed?: number;
  parsed?: number;
  failed?: number;
  duplicates?: number;
}

export default function GmailIntegration() {
  const [connection, setConnection] = useState<GmailConnection | null>(null);
  const [stats, setStats] = useState<GmailStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncProgress, setSyncProgress] = useState<SyncProgress | null>(null);

  useEffect(() => {
    fetchConnection();
  }, []);

  const fetchConnection = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/gmail/connection`);

      if (response.data.connected) {
        setConnection(response.data.connection);
        setStats(response.data.statistics);
      } else {
        setConnection(null);
        setStats(null);
      }
      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch Gmail connection:', err);
      // 404 means not connected, which is expected
      if (err.response?.status !== 404) {
        setError('Failed to fetch Gmail connection status');
      }
      setConnection(null);
      setStats(null);
    } finally {
      setLoading(false);
    }
  };

  const handleConnect = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(`${API_URL}/gmail/authorize`);
      const { auth_url, state, code_verifier } = response.data;

      // Store PKCE values for callback
      sessionStorage.setItem('gmail_state', state);
      sessionStorage.setItem('gmail_code_verifier', code_verifier);

      // Redirect to Google OAuth
      window.location.href = auth_url;
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to initiate Gmail authorization');
      setLoading(false);
    }
  };

  const handleSync = async () => {
    if (!connection) return;

    try {
      setSyncing(true);
      setSyncProgress({ status: 'starting' });

      const response = await axios.post(`${API_URL}/gmail/sync`, {
        connection_id: connection.id,
        sync_type: 'auto'
      });

      const result = response.data;
      setSyncProgress({
        status: 'completed',
        total_messages: result.total_messages,
        processed: result.processed,
        parsed: result.parsed,
        failed: result.failed,
        duplicates: result.duplicates
      });

      // Refresh connection data
      await fetchConnection();
      window.dispatchEvent(new Event('transactions-updated'));

    } catch (err: any) {
      setError(err.response?.data?.error || 'Sync failed');
      setSyncProgress(null);
    } finally {
      setSyncing(false);
    }
  };

  const handleDisconnect = async () => {
    if (!connection) return;

    if (!confirm('Are you sure you want to disconnect Gmail? All synced receipts will be deleted.')) {
      return;
    }

    try {
      await axios.post(`${API_URL}/gmail/disconnect`, {
        connection_id: connection.id
      });

      setConnection(null);
      setStats(null);
      setSyncProgress(null);
      window.dispatchEvent(new Event('transactions-updated'));
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to disconnect Gmail');
    }
  };

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return 'Never';
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffHours / 24);

    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;

    return date.toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short'
    });
  };

  if (loading && !connection) {
    return (
      <div className="flex justify-center items-center p-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold">Gmail Receipts</h3>
        {!connection && (
          <button
            className="btn btn-sm btn-primary"
            onClick={handleConnect}
            disabled={loading}
          >
            {loading ? (
              <span className="loading loading-spinner loading-sm"></span>
            ) : (
              'Connect Gmail'
            )}
          </button>
        )}
      </div>

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
          <button className="btn btn-ghost btn-xs" onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {!connection ? (
        <div className="alert alert-info">
          <span>Connect your Gmail account to automatically sync receipt emails for transaction matching.</span>
        </div>
      ) : (
        <div className="card bg-base-200">
          <div className="card-body p-4">
            {/* Connection info */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="avatar placeholder">
                  <div className="bg-primary text-primary-content rounded-full w-10">
                    <span className="text-lg">📧</span>
                  </div>
                </div>
                <div>
                  <div className="font-medium">{connection.email_address}</div>
                  <div className="text-sm text-base-content/70">
                    {connection.connection_status === 'active' ? (
                      <span className="text-success">Connected</span>
                    ) : (
                      <span className="text-warning">{connection.connection_status}</span>
                    )}
                    {' • '}
                    Last synced: {formatDate(connection.last_synced_at)}
                  </div>
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  className="btn btn-sm btn-primary"
                  onClick={handleSync}
                  disabled={syncing}
                >
                  {syncing ? (
                    <>
                      <span className="loading loading-spinner loading-xs"></span>
                      Syncing...
                    </>
                  ) : (
                    'Sync'
                  )}
                </button>
                <button
                  className="btn btn-sm btn-ghost text-error"
                  onClick={handleDisconnect}
                >
                  Disconnect
                </button>
              </div>
            </div>

            {/* LLM Fallback Warning */}
            <div className="alert alert-warning py-2 mt-4">
              <svg xmlns="http://www.w3.org/2000/svg" className="stroke-current shrink-0 h-5 w-5" fill="none" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div className="text-sm">
                <span className="font-medium">AI Parsing:</span>{' '}
                Receipts that can't be parsed automatically may use LLM
                (~$0.001/receipt). Cost shown after sync completes.
              </div>
            </div>

            {/* Stats */}
            {stats && (
              <div className="stats stats-horizontal bg-base-100 mt-4">
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Total</div>
                  <div className="stat-value text-lg">{stats.total_receipts}</div>
                </div>
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Parsed</div>
                  <div className="stat-value text-lg text-info">{stats.parsed_receipts}</div>
                </div>
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Matched</div>
                  <div className="stat-value text-lg text-success">{stats.matched_receipts}</div>
                </div>
                <div className="stat py-2 px-4">
                  <div className="stat-title text-xs">Pending</div>
                  <div className="stat-value text-lg text-warning">{stats.pending_receipts}</div>
                </div>
              </div>
            )}

            {/* Sync progress */}
            {syncProgress && syncProgress.status !== 'completed' && (
              <div className="mt-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="loading loading-spinner loading-xs"></span>
                  <span className="text-sm">
                    {syncProgress.status === 'starting' && 'Starting sync...'}
                    {syncProgress.status === 'scanning' && `Found ${syncProgress.total_messages} messages...`}
                    {syncProgress.status === 'processing' && (
                      `Processing: ${syncProgress.processed}/${syncProgress.total_messages}`
                    )}
                  </span>
                </div>
                {syncProgress.total_messages && syncProgress.processed && (
                  <progress
                    className="progress progress-primary w-full"
                    value={syncProgress.processed}
                    max={syncProgress.total_messages}
                  ></progress>
                )}
              </div>
            )}

            {/* Completed sync summary */}
            {syncProgress && syncProgress.status === 'completed' && (
              <div className="alert alert-success mt-4">
                <span>
                  Sync complete: {syncProgress.parsed} receipts stored,
                  {syncProgress.duplicates} duplicates,
                  {syncProgress.failed} failed
                </span>
                <button
                  className="btn btn-ghost btn-xs"
                  onClick={() => setSyncProgress(null)}
                >
                  ✕
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
