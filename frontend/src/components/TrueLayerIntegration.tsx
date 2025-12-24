import { useState, useEffect } from 'react';
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
  accounts: TrueLayerAccount[];
}

export default function TrueLayerIntegration() {
  const [connections, setConnections] = useState<TrueLayerConnection[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [syncing, setSyncing] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [showImportWizard, setShowImportWizard] = useState(false);
  const [selectedConnection, setSelectedConnection] = useState<TrueLayerConnection | null>(null);

  useEffect(() => {
    fetchConnections();
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

  const handleSync = async (connectionId: number) => {
    try {
      setSyncing(connectionId);
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
                <>
                  {/* Bank Row (Level 1) */}
                  <tr
                    key={connection.id}
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
                      {connection.connection_status !== 'active' && (
                        <span className="badge badge-warning badge-sm ml-2">
                          {connection.connection_status}
                        </span>
                      )}
                    </td>
                    <td className="text-right">
                      <div className="flex gap-2 justify-end" onClick={(e) => e.stopPropagation()}>
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
                </>
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
