import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { ImportWizard } from './TrueLayer/ImportWizard';

const API_URL = 'http://localhost:5000/api';

interface TrueLayerAccount {
  id: number;
  account_id: string;
  display_name: string;
  account_type: string;
  currency: string;
  last_synced_at?: string | null;
}

interface TrueLayerConnection {
  id: number;
  provider_id: string;
  provider_name: string;
  connection_status: string;
  last_synced_at: string | null;
  is_token_expired?: boolean;  // Token expiry status from backend
  accounts: TrueLayerAccount[];
}

interface SyncProgress {
  jobId: string;
  connectionId: number;
  status: string;
  totalAccounts?: number;
  accountsProcessed?: number;
  transactionsSynced?: number;
  duplicates?: number;
  errors?: number;
}

export default function TrueLayerIntegration() {
  const [connections, setConnections] = useState<TrueLayerConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [syncProgress, setSyncProgress] = useState<SyncProgress | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showImportWizard, setShowImportWizard] = useState(false);
  const [selectedConnection, setSelectedConnection] = useState<TrueLayerConnection | null>(null);

  // Date range for sync (90 days back by default)
  const [syncDateFrom, setSyncDateFrom] = useState(() => {
    const date = new Date();
    date.setDate(date.getDate() - 90);
    return date.toISOString().split('T')[0];
  });
  const [syncDateTo, setSyncDateTo] = useState(() => new Date().toISOString().split('T')[0]);

  useEffect(() => {
    fetchConnections();
  }, []);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      // Clear sync progress if component unmounts
      setSyncProgress(null);
      setSyncing(null);
    };
  }, []);

  const fetchConnections = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/truelayer/accounts`);
      setConnections(response.data.connections || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch TrueLayer connections:', err);
      setError('Failed to fetch TrueLayer connections');
    } finally {
      setLoading(false);
    }
  };

  const handleAuthorize = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/truelayer/authorize`);
      const { auth_url } = response.data;

      sessionStorage.setItem('truelayer_state', response.data.state);
      sessionStorage.setItem('truelayer_code_verifier', response.data.code_verifier);

      window.location.href = auth_url;
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to initiate authorization');
      setLoading(false);
    }
  };

  const pollJobStatus = async (jobId: string, connectionId: number) => {
    const pollInterval = setInterval(async () => {
      try {
        const response = await axios.get(`${API_URL}/truelayer/jobs/${jobId}`);
        const status = response.data;

        setSyncProgress({
          jobId,
          connectionId,
          status: status.status,
          totalAccounts: status.total_accounts,
          accountsProcessed: status.accounts_processed,
          transactionsSynced: status.transactions_synced,
          duplicates: status.duplicates,
          errors: status.errors,
        });

        // Stop polling if completed or failed
        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(pollInterval);
          setSyncing(null);

          if (status.status === 'completed') {
            // Wait a bit to show final progress, then clear
            setTimeout(() => {
              setSyncProgress(null);
              fetchConnections();
              window.dispatchEvent(new Event('transactions-updated'));
            }, 2000);
          } else {
            alert(`Sync failed: ${status.error || 'Unknown error'}`);
            setSyncProgress(null);
          }
        }
      } catch (err) {
        console.error('Failed to poll job status:', err);
        clearInterval(pollInterval);
        setSyncing(null);
        setSyncProgress(null);
      }
    }, 2000); // Poll every 2 seconds
  };

  const handleSync = async (connectionId: number) => {
    try {
      setSyncing(connectionId);
      setSyncProgress({
        jobId: '',
        connectionId,
        status: 'queued',
      });

      // Use async mode
      const response = await axios.post(`${API_URL}/truelayer/sync?async=true`, {
        connection_id: connectionId,
        date_from: syncDateFrom,
        date_to: syncDateTo
      });

      const { job_id } = response.data;

      // Start polling for progress
      pollJobStatus(job_id, connectionId);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to sync transactions');
      setSyncing(null);
      setSyncProgress(null);
    }
  };

  const handleDisconnect = async (connectionId: number) => {
    if (!confirm('Are you sure you want to disconnect this bank account?')) {
      return;
    }

    try {
      await axios.post(`${API_URL}/truelayer/disconnect`, {
        connection_id: connectionId
      });

      alert('Bank account disconnected successfully');
      fetchConnections();
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to disconnect account');
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

  const formatAccountType = (type: string) => {
    return type.charAt(0) + type.slice(1).toLowerCase();
  };

  const toggleExpanded = (connectionId: number) => {
    setExpanded(expanded === connectionId ? null : connectionId);
  };

  if (loading && connections.length === 0) {
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
        <h3 className="text-lg font-semibold">Linked Accounts</h3>
        <button
          className="btn btn-sm btn-primary"
          onClick={handleAuthorize}
          disabled={loading}
        >
          {loading ? (
            <span className="loading loading-spinner loading-sm"></span>
          ) : (
            'Add Account'
          )}
        </button>
      </div>

      {/* Sync Date Range */}
      <div className="card bg-base-200">
        <div className="card-body py-3 px-4">
          <div className="flex flex-col gap-3">
            {/* Date Inputs */}
            <div className="flex items-center gap-4">
              <span className="text-sm font-medium">Sync Date Range:</span>
              <div className="flex items-center gap-2">
                <input
                  type="date"
                  value={syncDateFrom}
                  onChange={(e) => setSyncDateFrom(e.target.value)}
                  className="input input-sm input-bordered"
                />
                <span className="text-sm">to</span>
                <input
                  type="date"
                  value={syncDateTo}
                  onChange={(e) => setSyncDateTo(e.target.value)}
                  max={new Date().toISOString().split('T')[0]}
                  className="input input-sm input-bordered"
                />
              </div>
            </div>

            {/* Preset Buttons */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-base-content/70">Quick select:</span>
              <div className="flex gap-2">
                <button
                  className="btn btn-xs btn-outline"
                  onClick={() => {
                    const date = new Date();
                    date.setDate(date.getDate() - 30);
                    setSyncDateFrom(date.toISOString().split('T')[0]);
                    setSyncDateTo(new Date().toISOString().split('T')[0]);
                  }}
                >
                  Last 30 Days
                </button>
                <button
                  className="btn btn-xs btn-outline"
                  onClick={() => {
                    const date = new Date();
                    date.setDate(date.getDate() - 90);
                    setSyncDateFrom(date.toISOString().split('T')[0]);
                    setSyncDateTo(new Date().toISOString().split('T')[0]);
                  }}
                >
                  Last 90 Days
                </button>
                <button
                  className="btn btn-xs btn-outline"
                  onClick={() => {
                    const date = new Date();
                    date.setFullYear(date.getFullYear() - 1);
                    setSyncDateFrom(date.toISOString().split('T')[0]);
                    setSyncDateTo(new Date().toISOString().split('T')[0]);
                  }}
                >
                  Last Year
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sync Progress Bar */}
      {syncProgress && (
        <div className="card bg-primary/10 border border-primary/30">
          <div className="card-body py-4 px-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">
                {syncProgress.status === 'queued' && 'Starting sync...'}
                {syncProgress.status === 'syncing' && `Syncing accounts...`}
                {syncProgress.status === 'completed' && '✓ Sync completed!'}
                {syncProgress.status === 'failed' && '✗ Sync failed'}
              </span>
              {syncProgress.totalAccounts !== undefined && syncProgress.accountsProcessed !== undefined && (
                <span className="text-sm text-base-content/70">
                  {syncProgress.accountsProcessed} / {syncProgress.totalAccounts} accounts
                </span>
              )}
            </div>

            {/* Progress bar */}
            <div className="w-full bg-base-300 rounded-full h-2.5 mb-2">
              <div
                className={`h-2.5 rounded-full transition-all duration-300 ${
                  syncProgress.status === 'completed' ? 'bg-success' :
                  syncProgress.status === 'failed' ? 'bg-error' :
                  'bg-primary'
                }`}
                style={{
                  width: syncProgress.totalAccounts
                    ? `${(syncProgress.accountsProcessed || 0) / syncProgress.totalAccounts * 100}%`
                    : '0%'
                }}
              ></div>
            </div>

            {/* Stats */}
            {syncProgress.transactionsSynced !== undefined && (
              <div className="flex gap-4 text-xs text-base-content/70">
                <span>Synced: {syncProgress.transactionsSynced}</span>
                {syncProgress.duplicates !== undefined && syncProgress.duplicates > 0 && (
                  <span>Duplicates: {syncProgress.duplicates}</span>
                )}
                {syncProgress.errors !== undefined && syncProgress.errors > 0 && (
                  <span className="text-error">Errors: {syncProgress.errors}</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
        </div>
      )}

      {connections.length === 0 ? (
        <div className="alert alert-info">
          <span>No accounts connected. Click "Add Account" to link your bank.</span>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th className="w-8"></th>
                <th>Bank</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {connections.map((connection) => (
                <React.Fragment key={connection.id}>
                  {/* Bank Row (Level 1) */}
                  <tr
                    className="hover cursor-pointer"
                    onClick={() => toggleExpanded(connection.id)}
                  >
                    <td className="w-4 pr-0 bg-transparent">
                      <span className="text-base-content/50" style={{ fontFamily: 'system-ui, sans-serif', fontSize: '1.4em' }}>
                        {expanded === connection.id ? '▾' : '▸'}
                      </span>
                    </td>
                    <td className="pl-2">
                      <span className="font-medium">{connection.provider_name}</span>
                      {connection.is_token_expired && (
                        <span className="badge badge-error badge-sm ml-2">
                          Token Expired
                        </span>
                      )}
                      {connection.connection_status !== 'active' && !connection.is_token_expired && (
                        <span className="badge badge-warning badge-sm ml-2">
                          {connection.connection_status}
                        </span>
                      )}
                    </td>
                    <td className="text-right">
                      <div className="flex gap-2 justify-end" onClick={(e) => e.stopPropagation()}>
                        {connection.is_token_expired ? (
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={handleAuthorize}
                            disabled={loading}
                          >
                            Reconnect
                          </button>
                        ) : (
                          <button
                            className="btn btn-xs btn-primary"
                            onClick={() => handleSync(connection.id)}
                            disabled={syncing === connection.id}
                          >
                            {syncing === connection.id ? (
                              <span className="loading loading-spinner loading-xs"></span>
                            ) : (
                              'Sync'
                            )}
                          </button>
                        )}
                        <button
                          className="btn btn-xs btn-outline"
                          onClick={() => {
                            setSelectedConnection(connection);
                            setShowImportWizard(true);
                          }}
                        >
                          Import
                        </button>
                        <button
                          className="btn btn-xs btn-ghost text-error"
                          onClick={() => handleDisconnect(connection.id)}
                        >
                          Disconnect
                        </button>
                      </div>
                    </td>
                  </tr>

                  {/* Accounts Row (Level 2 - Expanded) */}
                  {expanded === connection.id && connection.accounts.length > 0 && (
                    <tr key={`${connection.id}-accounts`}>
                      <td colSpan={3} className="bg-base-200 p-0">
                        <table className="table table-sm">
                          <thead>
                            <tr className="text-xs">
                              <th className="pl-10">Account Name</th>
                              <th>Type</th>
                              <th>Last Sync</th>
                            </tr>
                          </thead>
                          <tbody>
                            {connection.accounts.map((account) => (
                              <tr key={account.id}>
                                <td className="pl-10">{account.display_name}</td>
                                <td>
                                  <span className="badge badge-ghost badge-sm">
                                    {formatAccountType(account.account_type)}
                                  </span>
                                </td>
                                <td className="text-base-content/70">
                                  {formatDate(account.last_synced_at)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </td>
                    </tr>
                  )}

                  {/* No accounts message */}
                  {expanded === connection.id && connection.accounts.length === 0 && (
                    <tr key={`${connection.id}-empty`}>
                      <td colSpan={3} className="bg-base-200 pl-10 text-base-content/50">
                        No accounts found
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Import Wizard Modal */}
      {showImportWizard && selectedConnection && (
        <ImportWizard
          connection={selectedConnection}
          onImportComplete={(jobId) => {
            console.log('Import job completed:', jobId);
            window.dispatchEvent(new Event('transactions-updated'));
            setShowImportWizard(false);
          }}
          onClose={() => setShowImportWizard(false)}
        />
      )}
    </div>
  );
}
