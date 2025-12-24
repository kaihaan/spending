import { useState, useEffect } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

interface AccountMapping {
  id: number;
  sort_code: string;
  account_number: string;
  friendly_name: string;
  created_at: string;
}

interface DiscoveredAccount {
  sort_code: string;
  account_number: string;
  sample_description: string;
  count: number;
}

export default function AccountMappings() {
  const [mappings, setMappings] = useState<AccountMapping[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add/Edit state
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [editingMapping, setEditingMapping] = useState<AccountMapping | null>(null);
  const [sortCode, setSortCode] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [friendlyName, setFriendlyName] = useState('');

  // Discovery state
  const [discoveredAccounts, setDiscoveredAccounts] = useState<DiscoveredAccount[]>([]);
  const [discovering, setDiscovering] = useState(false);

  // Inline add mapping for discovered accounts
  const [addingFor, setAddingFor] = useState<string | null>(null);
  const [inlineFriendlyName, setInlineFriendlyName] = useState('');

  useEffect(() => {
    fetchMappings();
  }, []);

  const fetchMappings = async () => {
    try {
      setLoading(true);
      const response = await axios.get<AccountMapping[]>(`${API_URL}/settings/account-mappings`);
      setMappings(response.data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch account mappings');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const validateSortCode = (value: string): boolean => {
    return /^\d{6}$/.test(value);
  };

  const validateAccountNumber = (value: string): boolean => {
    return /^\d{8}$/.test(value);
  };

  const formatSortCode = (value: string): string => {
    const digits = value.replace(/\D/g, '');
    return digits.substring(0, 6);
  };

  const formatAccountNumber = (value: string): string => {
    const digits = value.replace(/\D/g, '');
    return digits.substring(0, 8);
  };

  const displaySortCode = (sortCode: string): string => {
    if (sortCode.length === 6) {
      return `${sortCode.substring(0, 2)}-${sortCode.substring(2, 4)}-${sortCode.substring(4, 6)}`;
    }
    return sortCode;
  };

  const reapplyMappingsAfterAdd = async () => {
    try {
      const response = await axios.post(`${API_URL}/migrations/reapply-account-mappings`);
      const { transactions_updated, transactions_total } = response.data;
      window.dispatchEvent(new Event('transactions-updated'));
      return { transactions_updated, transactions_total };
    } catch (err: any) {
      console.error('Failed to auto-reapply mappings:', err);
      return { transactions_updated: 0, transactions_total: 0 };
    }
  };

  const handleAddMapping = async () => {
    if (!validateSortCode(sortCode)) {
      alert('Sort code must be exactly 6 digits');
      return;
    }

    if (!validateAccountNumber(accountNumber)) {
      alert('Account number must be exactly 8 digits');
      return;
    }

    if (!friendlyName.trim()) {
      alert('Friendly name is required');
      return;
    }

    try {
      await axios.post(`${API_URL}/settings/account-mappings`, {
        sort_code: sortCode,
        account_number: accountNumber,
        friendly_name: friendlyName.trim()
      });

      setSortCode('');
      setAccountNumber('');
      setFriendlyName('');
      setShowAddDialog(false);
      fetchMappings();

      const { transactions_updated, transactions_total } = await reapplyMappingsAfterAdd();
      alert(`Account mapping added successfully!\nApplied to ${transactions_updated} of ${transactions_total} transactions.`);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to add account mapping');
    }
  };

  const handleUpdateMapping = async () => {
    if (!editingMapping) return;

    if (!friendlyName.trim()) {
      alert('Friendly name is required');
      return;
    }

    try {
      await axios.put(`${API_URL}/settings/account-mappings/${editingMapping.id}`, {
        friendly_name: friendlyName.trim()
      });

      setEditingMapping(null);
      setFriendlyName('');
      fetchMappings();

      const { transactions_updated, transactions_total } = await reapplyMappingsAfterAdd();
      alert(`Account mapping updated successfully!\nApplied to ${transactions_updated} of ${transactions_total} transactions.`);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to update account mapping');
    }
  };

  const handleDeleteMapping = async (id: number, name: string) => {
    if (!confirm(`Delete mapping for "${name}"? This cannot be undone.`)) return;

    try {
      await axios.delete(`${API_URL}/settings/account-mappings/${id}`);
      fetchMappings();
      alert('Account mapping deleted successfully!');
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to delete account mapping');
    }
  };

  const openAddDialog = () => {
    setSortCode('');
    setAccountNumber('');
    setFriendlyName('');
    setShowAddDialog(true);
  };

  const openEditDialog = (mapping: AccountMapping) => {
    setEditingMapping(mapping);
    setFriendlyName(mapping.friendly_name);
  };

  const handleDiscoverAccounts = async () => {
    try {
      setDiscovering(true);
      const response = await axios.get<DiscoveredAccount[]>(`${API_URL}/settings/account-mappings/discover`);
      setDiscoveredAccounts(response.data);

      if (response.data.length === 0) {
        alert('No unmapped accounts found in transactions!');
      }
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to discover accounts');
    } finally {
      setDiscovering(false);
    }
  };

  const startInlineAdd = (sortCode: string, accountNumber: string) => {
    setAddingFor(`${sortCode}_${accountNumber}`);
    setInlineFriendlyName('');
  };

  const cancelInlineAdd = () => {
    setAddingFor(null);
    setInlineFriendlyName('');
  };

  const handleInlineAddMapping = async (sortCode: string, accountNumber: string) => {
    if (!inlineFriendlyName.trim()) {
      alert('Friendly name is required');
      return;
    }

    try {
      await axios.post(`${API_URL}/settings/account-mappings`, {
        sort_code: sortCode,
        account_number: accountNumber,
        friendly_name: inlineFriendlyName.trim()
      });

      setDiscoveredAccounts(discoveredAccounts.filter(
        acc => !(acc.sort_code === sortCode && acc.account_number === accountNumber)
      ));

      setAddingFor(null);
      setInlineFriendlyName('');
      fetchMappings();

      const { transactions_updated, transactions_total } = await reapplyMappingsAfterAdd();
      alert(`Account mapping added successfully!\nApplied to ${transactions_updated} of ${transactions_total} transactions.`);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to add account mapping');
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center p-8">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert alert-error">
        <span>{error}</span>
      </div>
    );
  }

  return (
    <div className="mb-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold">Account Mappings</h3>
        <div className="flex gap-2">
          <button
            className="btn btn-sm btn-outline"
            onClick={handleDiscoverAccounts}
            disabled={discovering}
          >
            {discovering ? (
              <>
                <span className="loading loading-spinner loading-sm"></span>
                Discovering...
              </>
            ) : (
              'Discover Accounts'
            )}
          </button>
          <button
            className="btn btn-sm btn-primary"
            onClick={openAddDialog}
          >
            + Add Mapping
          </button>
        </div>
      </div>

      {mappings.length === 0 && discoveredAccounts.length === 0 ? (
        <div className="alert alert-info">
          <span>
            No mappings configured. Click "Discover Accounts" to find accounts or add manually.
          </span>
        </div>
      ) : (
        <div className="overflow-x-auto border border-base-300 rounded-lg">
              <table className="table">
                <thead>
                  <tr>
                    <th>Friendly Name</th>
                    <th>Sort Code</th>
                    <th>Account Number</th>
                    <th>Info</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {mappings.map((mapping) => (
                    <tr key={`mapped-${mapping.id}`}>
                      <td className="font-semibold">{mapping.friendly_name}</td>
                      <td>
                        <code className="text-sm">{displaySortCode(mapping.sort_code)}</code>
                      </td>
                      <td>
                        <code className="text-sm">{mapping.account_number}</code>
                      </td>
                      <td className="text-sm text-base-content/70">
                        {new Date(mapping.created_at).toLocaleDateString()}
                      </td>
                      <td>
                        <div className="flex gap-2">
                          <button
                            className="btn btn-ghost btn-xs"
                            onClick={() => openEditDialog(mapping)}
                          >
                            Edit
                          </button>
                          <button
                            className="btn btn-ghost btn-xs text-error"
                            onClick={() => handleDeleteMapping(mapping.id, mapping.friendly_name)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}

                  {discoveredAccounts.map((account) => {
                    const key = `${account.sort_code}_${account.account_number}`;
                    const isAdding = addingFor === key;

                    return (
                      <tr key={`discovered-${key}`} className="bg-warning/10">
                        <td>
                          {isAdding ? (
                            <input
                              type="text"
                              placeholder="Enter friendly name..."
                              className="input input-sm input-bordered w-full"
                              value={inlineFriendlyName}
                              onChange={(e) => setInlineFriendlyName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') {
                                  handleInlineAddMapping(account.sort_code, account.account_number);
                                } else if (e.key === 'Escape') {
                                  cancelInlineAdd();
                                }
                              }}
                              autoFocus
                            />
                          ) : (
                            <div className="flex items-center gap-2">
                              <span className="badge badge-warning badge-sm">Unmapped</span>
                              <span className="text-sm text-base-content/50">No friendly name yet</span>
                            </div>
                          )}
                        </td>
                        <td>
                          <code className="text-sm">{displaySortCode(account.sort_code)}</code>
                        </td>
                        <td>
                          <code className="text-sm">{account.account_number}</code>
                        </td>
                        <td>
                          <details className="text-xs">
                            <summary className="cursor-pointer text-info">
                              Found in {account.count} transaction{account.count > 1 ? 's' : ''}
                            </summary>
                            <div className="mt-2 p-2 bg-base-300 rounded text-base-content/70 max-w-md truncate">
                              {account.sample_description}
                            </div>
                          </details>
                        </td>
                        <td>
                          {isAdding ? (
                            <div className="flex gap-2">
                              <button
                                className="btn btn-success btn-xs"
                                onClick={() => handleInlineAddMapping(account.sort_code, account.account_number)}
                                disabled={!inlineFriendlyName.trim()}
                              >
                                Save
                              </button>
                              <button
                                className="btn btn-ghost btn-xs"
                                onClick={cancelInlineAdd}
                              >
                                Cancel
                              </button>
                            </div>
                          ) : (
                            <button
                              className="btn btn-primary btn-xs"
                              onClick={() => startInlineAdd(account.sort_code, account.account_number)}
                            >
                              Add Mapping
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
        </div>
      )}

      {/* Add Mapping Dialog */}
      {showAddDialog && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Add Account Mapping</h3>
            <div className="py-4 space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Sort Code (6 digits)</span>
                </label>
                <input
                  type="text"
                  placeholder="123456"
                  className="input input-sm input-bordered"
                  value={sortCode}
                  onChange={(e) => setSortCode(formatSortCode(e.target.value))}
                  maxLength={6}
                />
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Account Number (8 digits)</span>
                </label>
                <input
                  type="text"
                  placeholder="12345678"
                  className="input input-sm input-bordered"
                  value={accountNumber}
                  onChange={(e) => setAccountNumber(formatAccountNumber(e.target.value))}
                  maxLength={8}
                />
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Friendly Name</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g., Yasmin, Savings Account"
                  className="input input-sm input-bordered"
                  value={friendlyName}
                  onChange={(e) => setFriendlyName(e.target.value)}
                />
              </div>
            </div>
            <div className="modal-action">
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => {
                  setShowAddDialog(false);
                  setSortCode('');
                  setAccountNumber('');
                  setFriendlyName('');
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-sm btn-primary"
                onClick={handleAddMapping}
                disabled={!validateSortCode(sortCode) || !validateAccountNumber(accountNumber) || !friendlyName.trim()}
              >
                Add Mapping
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Mapping Dialog */}
      {editingMapping && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Edit Account Mapping</h3>
            <div className="py-4 space-y-4">
              <div className="form-control">
                <label className="label">
                  <span className="label-text">Sort Code</span>
                </label>
                <input
                  type="text"
                  className="input input-sm input-bordered"
                  value={displaySortCode(editingMapping.sort_code)}
                  disabled
                />
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Account Number</span>
                </label>
                <input
                  type="text"
                  className="input input-sm input-bordered"
                  value={editingMapping.account_number}
                  disabled
                />
              </div>

              <div className="form-control">
                <label className="label">
                  <span className="label-text">Friendly Name</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g., Yasmin, Savings Account"
                  className="input input-sm input-bordered"
                  value={friendlyName}
                  onChange={(e) => setFriendlyName(e.target.value)}
                  autoFocus
                />
              </div>
            </div>
            <div className="modal-action">
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => {
                  setEditingMapping(null);
                  setFriendlyName('');
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-sm btn-primary"
                onClick={handleUpdateMapping}
                disabled={!friendlyName.trim()}
              >
                Update
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
