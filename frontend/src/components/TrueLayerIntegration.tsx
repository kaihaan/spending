import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface TrueLayerAccount {
  id: number;
  account_id: string;
  display_name: string;
  account_type: string;
  currency: string;
}

interface TrueLayerConnection {
  id: number;
  provider_id: string;
  connection_status: string;
  last_synced_at: string | null;
  accounts: TrueLayerAccount[];
}

interface SyncStatus {
  account_id: string;
  display_name: string;
  last_synced_at: string | null;
  connection_status: string;
}

export default function TrueLayerIntegration() {
  const [connections, setConnections] = useState<TrueLayerConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<string | null>(null);
  const [syncStatus, setSyncStatus] = useState<SyncStatus[]>([]);

  useEffect(() => {
    fetchConnections();
  }, []);

  const fetchConnections = async () => {
    try {
      setLoading(true);
      const response = await axios.get(`${API_URL}/truelayer/accounts`);
      setConnections(response.data.connections || []);
      setSyncStatus(response.data.sync_status || []);
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

      // Store state and code_verifier in sessionStorage for OAuth callback
      sessionStorage.setItem('truelayer_state', response.data.state);
      sessionStorage.setItem('truelayer_code_verifier', response.data.code_verifier);

      // Redirect to TrueLayer authorization
      window.location.href = auth_url;
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to initiate authorization');
      setLoading(false);
    }
  };

  const handleSync = async (connectionId: number) => {
    try {
      setSyncing(`${connectionId}`);
      const response = await axios.post(`${API_URL}/truelayer/sync`, {
        connection_id: connectionId
      });

      const result = response.data.result;
      alert(
        `Sync complete!\n` +
        `Synced: ${result.total_synced} transactions\n` +
        `Duplicates: ${result.total_duplicates}\n` +
        `Errors: ${result.total_errors}`
      );

      // Refresh connections and sync status
      fetchConnections();
      window.dispatchEvent(new Event('transactions-updated'));
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to sync transactions');
    } finally {
      setSyncing(null);
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

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString('en-GB', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return 'badge badge-success';
      case 'expired':
        return 'badge badge-warning';
      case 'disconnected':
        return 'badge badge-error';
      default:
        return 'badge badge-secondary';
    }
  };

  if (loading && connections.length === 0) {
    return (
      <div className="card bg-base-200 shadow mb-8">
        <div className="card-body">
          <div className="flex justify-center items-center p-8">
            <span className="loading loading-spinner loading-lg"></span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card bg-base-200 shadow mb-8">
      <div className="card-body">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2 className="card-title">🏦 TrueLayer Bank Integration</h2>
            <p className="text-sm text-base-content/70 mt-1">
              Connect your bank account for real-time transaction synchronization
            </p>
          </div>
          {connections.length === 0 ? (
            <button
              className="btn btn-primary"
              onClick={handleAuthorize}
              disabled={loading}
            >
              {loading ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  Connecting...
                </>
              ) : (
                '🔗 Connect Bank Account'
              )}
            </button>
          ) : (
            <button
              className="btn btn-primary btn-outline"
              onClick={handleAuthorize}
              disabled={loading}
            >
              + Add Another Account
            </button>
          )}
        </div>

        {error && (
          <div className="alert alert-error mb-4">
            <span>{error}</span>
          </div>
        )}

        {connections.length === 0 ? (
          <div className="alert alert-info">
            <span>
              No bank accounts connected. Click "Connect Bank Account" to authorize TrueLayer access and start syncing transactions automatically.
            </span>
          </div>
        ) : (
          <div className="space-y-4">
            {connections.map((connection) => (
              <div key={connection.id} className="border border-base-300 rounded-lg p-4 bg-base-100">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-2">
                      <h3 className="font-semibold text-lg">
                        {connection.provider_id || 'Bank Account'}
                      </h3>
                      <span className={getStatusBadge(connection.connection_status)}>
                        {connection.connection_status}
                      </span>
                    </div>
                    <p className="text-sm text-base-content/70">
                      Last synced: {formatDate(connection.last_synced_at)}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => handleSync(connection.id)}
                      disabled={syncing === `${connection.id}`}
                    >
                      {syncing === `${connection.id}` ? (
                        <>
                          <span className="loading loading-spinner loading-sm"></span>
                          Syncing...
                        </>
                      ) : (
                        '🔄 Sync Now'
                      )}
                    </button>
                    <button
                      className="btn btn-sm btn-ghost text-error"
                      onClick={() => handleDisconnect(connection.id)}
                    >
                      Disconnect
                    </button>
                  </div>
                </div>

                {connection.accounts && connection.accounts.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-base-300">
                    <p className="text-sm font-semibold mb-2">Linked Accounts:</p>
                    <div className="space-y-2">
                      {connection.accounts.map((account) => (
                        <div
                          key={account.id}
                          className="flex justify-between items-center text-sm p-2 bg-base-200 rounded"
                        >
                          <div>
                            <span className="font-medium">{account.display_name}</span>
                            <span className="text-base-content/60 ml-2">
                              ({account.account_type})
                            </span>
                          </div>
                          <span className="text-base-content/70 font-mono">
                            {account.currency}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}

            {syncStatus.length > 0 && (
              <div className="border border-info rounded-lg p-4 bg-info/10">
                <p className="text-sm font-semibold mb-3">📊 Sync Status Overview</p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                  {syncStatus.map((account) => (
                    <div key={account.account_id} className="text-sm">
                      <span className="font-medium">{account.display_name}:</span>
                      <span className="text-base-content/70 ml-2">
                        {account.connection_status === 'active'
                          ? `Last: ${formatDate(account.last_synced_at)}`
                          : 'Disconnected'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
