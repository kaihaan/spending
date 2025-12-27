import { useState, useEffect } from 'react';
import axios from 'axios';
import type { DirectDebitPayee, Category } from '../../types';

const API_URL = 'http://localhost:5000/api';

interface EditingState {
  payee: string;
  normalized_name: string;
  category: string;
  subcategory: string;
  merchant_type: string;
}

export default function DirectDebitsTab() {
  // Data state
  const [payees, setPayees] = useState<DirectDebitPayee[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);

  // Editing state - tracks which row is being edited
  const [editingPayee, setEditingPayee] = useState<string | null>(null);
  const [editingState, setEditingState] = useState<EditingState>({
    payee: '',
    normalized_name: '',
    category: '',
    subcategory: '',
    merchant_type: ''
  });

  // Loading/status state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null); // Tracks which payee is being saved
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Fetch data on mount
  useEffect(() => {
    fetchPayees();
    fetchCategories();
  }, []);

  const fetchPayees = async () => {
    try {
      setLoading(true);
      const response = await axios.get<DirectDebitPayee[]>(`${API_URL}/direct-debit/payees`);
      setPayees(response.data);
    } catch (err: any) {
      console.error('Error fetching direct debit payees:', err);
      setError(err.response?.data?.error || 'Failed to load direct debit payees');
    } finally {
      setLoading(false);
    }
  };

  const fetchCategories = async () => {
    try {
      // Use categories/summary to get all categories including enrichment-created ones
      const response = await axios.get<{ categories: { name: string; total_spend: number }[] }>(
        `${API_URL}/categories/summary`
      );
      // Convert to Category format for the dropdown
      const cats = response.data.categories.map((c, idx) => ({
        id: idx,
        name: c.name,
        rule_pattern: null,
        ai_suggested: false
      }));
      setCategories(cats);
    } catch (err: any) {
      console.error('Error fetching categories:', err);
    }
  };

  const startEditing = (payee: DirectDebitPayee) => {
    setEditingPayee(payee.payee);
    setEditingState({
      payee: payee.payee,
      normalized_name: payee.mapped_name || payee.payee,
      category: payee.mapped_category || payee.current_category || '',
      subcategory: payee.mapped_subcategory || payee.current_subcategory || '',
      merchant_type: ''
    });
  };

  const cancelEditing = () => {
    setEditingPayee(null);
    setEditingState({
      payee: '',
      normalized_name: '',
      category: '',
      subcategory: '',
      merchant_type: ''
    });
  };

  const saveMapping = async () => {
    if (!editingPayee || !editingState.category) return;

    try {
      setSaving(editingPayee);
      setError(null);

      await axios.post(`${API_URL}/direct-debit/mappings`, {
        payee_pattern: editingState.payee,
        normalized_name: editingState.normalized_name || editingState.payee,
        category: editingState.category,
        subcategory: editingState.subcategory || editingState.normalized_name,
        merchant_type: editingState.merchant_type || null
      });

      setSuccessMessage(`Mapping saved for ${editingState.payee}`);
      setTimeout(() => setSuccessMessage(null), 3000);

      // Refresh data and clear editing state
      await fetchPayees();
      cancelEditing();
    } catch (err: any) {
      console.error('Error saving mapping:', err);
      setError(err.response?.data?.error || 'Failed to save mapping');
    } finally {
      setSaving(null);
    }
  };

  const deleteMapping = async (payee: DirectDebitPayee) => {
    if (!payee.mapping_id) return;

    try {
      setSaving(payee.payee);
      setError(null);

      await axios.delete(`${API_URL}/direct-debit/mappings/${payee.mapping_id}`);

      setSuccessMessage(`Mapping removed for ${payee.payee}`);
      setTimeout(() => setSuccessMessage(null), 3000);

      await fetchPayees();
    } catch (err: any) {
      console.error('Error deleting mapping:', err);
      setError(err.response?.data?.error || 'Failed to delete mapping');
    } finally {
      setSaving(null);
    }
  };

  const applyAllMappings = async () => {
    try {
      setApplying(true);
      setError(null);

      const response = await axios.post(`${API_URL}/direct-debit/apply-mappings`);

      setSuccessMessage(`Applied mappings to ${response.data.updated_count} transactions`);
      setTimeout(() => setSuccessMessage(null), 5000);

      // Dispatch event to refresh transactions in other components
      window.dispatchEvent(new CustomEvent('transactionsUpdated'));

      await fetchPayees();
    } catch (err: any) {
      console.error('Error applying mappings:', err);
      setError(err.response?.data?.error || 'Failed to apply mappings');
    } finally {
      setApplying(false);
    }
  };

  const mappedCount = payees.filter(p => p.mapping_id).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="card bg-base-100 border border-base-300 shadow-sm">
        <div className="card-body">
          <h2 className="card-title text-lg">Direct Debit Mappings</h2>
          <p className="text-base-content/70 text-sm">
            Configure how direct debit payees are categorized. The system extracts payee names from
            transaction descriptions like "DIRECT DEBIT PAYMENT TO EMMANUEL COLL..." and applies
            your configured mappings during enrichment.
          </p>

          <div className="flex items-center gap-4 mt-4">
            <div className="stats shadow-sm">
              <div className="stat py-2 px-4">
                <div className="stat-title text-xs">Total Payees</div>
                <div className="stat-value text-lg">{payees.length}</div>
              </div>
              <div className="stat py-2 px-4">
                <div className="stat-title text-xs">Mapped</div>
                <div className="stat-value text-lg text-success">{mappedCount}</div>
              </div>
              <div className="stat py-2 px-4">
                <div className="stat-title text-xs">Unmapped</div>
                <div className="stat-value text-lg text-warning">{payees.length - mappedCount}</div>
              </div>
            </div>

            <button
              className="btn btn-primary ml-auto"
              onClick={applyAllMappings}
              disabled={applying || mappedCount === 0}
            >
              {applying ? (
                <>
                  <span className="loading loading-spinner loading-sm"></span>
                  Applying...
                </>
              ) : (
                'Apply All Mappings'
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Error/Success alerts */}
      {error && (
        <div className="alert alert-error">
          <span>{error}</span>
          <button className="btn btn-ghost btn-xs" onClick={() => setError(null)}>
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="alert alert-success">
          <span>{successMessage}</span>
        </div>
      )}

      {/* Payees table */}
      <div className="card bg-base-100 border border-base-300 shadow-sm">
        <div className="card-body p-0">
          {loading ? (
            <div className="p-8 text-center">
              <span className="loading loading-spinner loading-lg"></span>
              <p className="mt-2 text-base-content/70">Loading direct debit payees...</p>
            </div>
          ) : payees.length === 0 ? (
            <div className="p-8 text-center text-base-content/70">
              <p>No direct debit transactions found.</p>
              <p className="text-sm mt-2">
                Direct debits are detected from transaction descriptions starting with
                "DIRECT DEBIT PAYMENT TO..."
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="table table-sm">
                <thead>
                  <tr className="bg-base-200">
                    <th className="w-48">Payee</th>
                    <th className="w-20 text-center">Count</th>
                    <th className="w-48">Mapped Name</th>
                    <th className="w-40">Category</th>
                    <th className="w-40">Subcategory</th>
                    <th className="w-24 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {payees.map((payee) => {
                    const isEditing = editingPayee === payee.payee;
                    const isSaving = saving === payee.payee;

                    return (
                      <tr key={payee.payee} className={payee.mapping_id ? 'bg-success/5' : 'bg-warning/5'}>
                        {/* Payee name */}
                        <td className="font-mono text-sm" title={payee.sample_description}>
                          {payee.payee}
                        </td>

                        {/* Transaction count */}
                        <td className="text-center">
                          <span className="badge badge-ghost">{payee.transaction_count}</span>
                        </td>

                        {/* Mapped name - editable */}
                        <td>
                          {isEditing ? (
                            <input
                              type="text"
                              className="input input-bordered input-sm w-full"
                              value={editingState.normalized_name}
                              onChange={(e) =>
                                setEditingState((s) => ({ ...s, normalized_name: e.target.value }))
                              }
                              placeholder="Clean merchant name"
                            />
                          ) : payee.mapped_name ? (
                            <span className="font-medium text-success">{payee.mapped_name}</span>
                          ) : (
                            <span className="text-base-content/40">-</span>
                          )}
                        </td>

                        {/* Category - editable, shows mapped or current */}
                        <td>
                          {isEditing ? (
                            <select
                              className="select select-bordered select-sm w-full"
                              value={editingState.category}
                              onChange={(e) =>
                                setEditingState((s) => ({ ...s, category: e.target.value }))
                              }
                            >
                              <option value="">Select category...</option>
                              {categories.map((cat) => (
                                <option key={cat.id} value={cat.name}>
                                  {cat.name}
                                </option>
                              ))}
                            </select>
                          ) : payee.mapped_category ? (
                            <span className="badge badge-success badge-sm">{payee.mapped_category}</span>
                          ) : payee.current_category ? (
                            <span className="badge badge-outline badge-sm">{payee.current_category}</span>
                          ) : (
                            <span className="text-base-content/40">-</span>
                          )}
                        </td>

                        {/* Subcategory - editable, shows mapped or current */}
                        <td>
                          {isEditing ? (
                            <input
                              type="text"
                              className="input input-bordered input-sm w-full"
                              value={editingState.subcategory}
                              onChange={(e) =>
                                setEditingState((s) => ({ ...s, subcategory: e.target.value }))
                              }
                              placeholder="Subcategory"
                            />
                          ) : payee.mapped_subcategory ? (
                            <span className="text-sm font-medium text-success">
                              {payee.mapped_subcategory}
                            </span>
                          ) : payee.current_subcategory ? (
                            <span className="text-sm text-base-content/70">
                              {payee.current_subcategory}
                            </span>
                          ) : (
                            <span className="text-base-content/40">-</span>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="text-center">
                          {isEditing ? (
                            <div className="flex gap-1 justify-center">
                              <button
                                className="btn btn-success btn-xs"
                                onClick={saveMapping}
                                disabled={isSaving || !editingState.category}
                                title="Save mapping"
                              >
                                {isSaving ? (
                                  <span className="loading loading-spinner loading-xs"></span>
                                ) : (
                                  '✓'
                                )}
                              </button>
                              <button
                                className="btn btn-ghost btn-xs"
                                onClick={cancelEditing}
                                disabled={isSaving}
                                title="Cancel"
                              >
                                ✕
                              </button>
                            </div>
                          ) : (
                            <div className="flex gap-1 justify-center">
                              <button
                                className="btn btn-ghost btn-xs"
                                onClick={() => startEditing(payee)}
                                disabled={!!saving}
                                title="Edit mapping"
                              >
                                Edit
                              </button>
                              {payee.mapping_id && (
                                <button
                                  className="btn btn-ghost btn-xs text-error"
                                  onClick={() => deleteMapping(payee)}
                                  disabled={!!saving}
                                  title="Remove mapping"
                                >
                                  {saving === payee.payee ? (
                                    <span className="loading loading-spinner loading-xs"></span>
                                  ) : (
                                    '✕'
                                  )}
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
