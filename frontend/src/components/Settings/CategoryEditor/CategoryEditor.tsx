import { useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import {
  NormalizedCategory,
  NormalizedSubcategory,
  CategoryWithSubcategories,
  UpdateCategoryRequest,
  UpdateSubcategoryRequest,
} from './types';

const API_URL = 'http://localhost:5000/api/v2';

interface PendingChange {
  type: 'category' | 'subcategory';
  id: number;
  field: 'name' | 'description';
  oldValue: string | null;
  newValue: string | null;
}

export default function CategoryEditor() {
  // Data state
  const [categories, setCategories] = useState<NormalizedCategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<CategoryWithSubcategories | null>(null);
  const [selectedSubcategory, setSelectedSubcategory] = useState<NormalizedSubcategory | null>(null);

  // Edit state - tracks uncommitted changes
  const [editingCategoryName, setEditingCategoryName] = useState<string>('');
  const [editingCategoryDescription, setEditingCategoryDescription] = useState<string>('');
  const [editingSubcategoryName, setEditingSubcategoryName] = useState<string>('');
  const [editingSubcategoryDescription, setEditingSubcategoryDescription] = useState<string>('');

  // Track if there are unsaved changes
  const [pendingChanges, setPendingChanges] = useState<PendingChange[]>([]);

  // UI state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Rename confirmation modal
  const [showRenameConfirm, setShowRenameConfirm] = useState(false);
  const [renameImpact, setRenameImpact] = useState<{
    transactionCount: number;
    ruleCount: number;
  } | null>(null);

  // Fetch categories on mount
  useEffect(() => {
    fetchCategories();
  }, []);

  // Update editing state when selection changes
  useEffect(() => {
    if (selectedCategory) {
      setEditingCategoryName(selectedCategory.name);
      setEditingCategoryDescription(selectedCategory.description || '');
    }
  }, [selectedCategory]);

  useEffect(() => {
    if (selectedSubcategory) {
      setEditingSubcategoryName(selectedSubcategory.name);
      setEditingSubcategoryDescription(selectedSubcategory.description || '');
    }
  }, [selectedSubcategory]);

  const fetchCategories = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await axios.get(`${API_URL}/categories?include_counts=true`);
      setCategories(response.data.categories);
    } catch (err: any) {
      console.error('Error fetching categories:', err);
      setError(err.response?.data?.error || 'Failed to load categories');
    } finally {
      setLoading(false);
    }
  };

  const fetchCategoryDetails = async (categoryId: number) => {
    try {
      const response = await axios.get(`${API_URL}/categories/${categoryId}`);
      setSelectedCategory(response.data.category);
      setSelectedSubcategory(null);
      setPendingChanges([]);
    } catch (err: any) {
      console.error('Error fetching category details:', err);
      setError(err.response?.data?.error || 'Failed to load category details');
    }
  };

  const handleSelectCategory = (category: NormalizedCategory) => {
    if (pendingChanges.length > 0) {
      if (!confirm('You have unsaved changes. Discard them?')) {
        return;
      }
    }
    fetchCategoryDetails(category.id);
  };

  const handleSelectSubcategory = (subcategory: NormalizedSubcategory) => {
    setSelectedSubcategory(subcategory);
    setEditingSubcategoryName(subcategory.name);
    setEditingSubcategoryDescription(subcategory.description || '');
  };

  const trackChange = useCallback((
    type: 'category' | 'subcategory',
    id: number,
    field: 'name' | 'description',
    oldValue: string | null,
    newValue: string | null
  ) => {
    setPendingChanges(prev => {
      // Remove existing change for same entity/field
      const filtered = prev.filter(
        c => !(c.type === type && c.id === id && c.field === field)
      );
      // Only add if value actually changed
      if (oldValue !== newValue) {
        return [...filtered, { type, id, field, oldValue, newValue }];
      }
      return filtered;
    });
  }, []);

  const handleCategoryNameChange = (value: string) => {
    setEditingCategoryName(value);
    if (selectedCategory) {
      trackChange('category', selectedCategory.id, 'name', selectedCategory.name, value);
    }
  };

  const handleCategoryDescriptionChange = (value: string) => {
    setEditingCategoryDescription(value);
    if (selectedCategory) {
      trackChange('category', selectedCategory.id, 'description', selectedCategory.description, value || null);
    }
  };

  const handleSubcategoryNameChange = (value: string) => {
    setEditingSubcategoryName(value);
    if (selectedSubcategory) {
      trackChange('subcategory', selectedSubcategory.id, 'name', selectedSubcategory.name, value);
    }
  };

  const handleSubcategoryDescriptionChange = (value: string) => {
    setEditingSubcategoryDescription(value);
    if (selectedSubcategory) {
      trackChange('subcategory', selectedSubcategory.id, 'description', selectedSubcategory.description, value || null);
    }
  };

  const hasNameChange = pendingChanges.some(c => c.field === 'name');

  const handleApply = async () => {
    if (pendingChanges.length === 0) return;

    // If there's a name change, show confirmation
    if (hasNameChange && selectedCategory) {
      setRenameImpact({
        transactionCount: selectedCategory.transaction_count || 0,
        ruleCount: 0 // Would need an API call to get rule count
      });
      setShowRenameConfirm(true);
      return;
    }

    await applyChanges();
  };

  const applyChanges = async () => {
    try {
      setSaving(true);
      setError(null);
      setShowRenameConfirm(false);

      let updatedCount = 0;

      // Group changes by entity
      const categoryChanges = pendingChanges.filter(c => c.type === 'category');
      const subcategoryChanges = pendingChanges.filter(c => c.type === 'subcategory');

      // Apply category changes
      if (categoryChanges.length > 0 && selectedCategory) {
        const updates: UpdateCategoryRequest = {};
        categoryChanges.forEach(change => {
          if (change.field === 'name' && change.newValue) {
            updates.name = change.newValue;
          }
          if (change.field === 'description') {
            updates.description = change.newValue;
          }
        });

        const response = await axios.put(`${API_URL}/categories/${selectedCategory.id}`, updates);
        updatedCount += response.data.transactions_updated || 0;
      }

      // Apply subcategory changes
      for (const change of subcategoryChanges) {
        const updates: UpdateSubcategoryRequest = {};
        if (change.field === 'name' && change.newValue) {
          updates.name = change.newValue;
        }
        if (change.field === 'description') {
          updates.description = change.newValue;
        }

        const response = await axios.put(`${API_URL}/subcategories/${change.id}`, updates);
        updatedCount += response.data.transactions_updated || 0;
      }

      // Refresh data
      await fetchCategories();
      if (selectedCategory) {
        await fetchCategoryDetails(selectedCategory.id);
      }

      setPendingChanges([]);
      setSuccessMessage(`Changes applied. ${updatedCount} transactions updated.`);
      setTimeout(() => setSuccessMessage(null), 3000);

    } catch (err: any) {
      console.error('Error applying changes:', err);
      setError(err.response?.data?.error || 'Failed to apply changes');
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setPendingChanges([]);
    if (selectedCategory) {
      setEditingCategoryName(selectedCategory.name);
      setEditingCategoryDescription(selectedCategory.description || '');
    }
    if (selectedSubcategory) {
      setEditingSubcategoryName(selectedSubcategory.name);
      setEditingSubcategoryDescription(selectedSubcategory.description || '');
    }
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: 'GBP'
    }).format(Math.abs(amount));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <span className="loading loading-dots loading-lg"></span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Apply/Cancel */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">
            {selectedCategory ? (
              <span className="flex items-center gap-2">
                <span className={`badge ${selectedCategory.color || 'badge-neutral'} badge-sm`}>
                  {selectedCategory.name}
                </span>
                {selectedSubcategory && (
                  <>
                    <span className="text-base-content/40">/</span>
                    <span className="text-base-content/70">{selectedSubcategory.name}</span>
                  </>
                )}
              </span>
            ) : (
              'Category Editor'
            )}
          </h2>
          {selectedCategory?.is_system && (
            <span className="badge badge-outline badge-xs">System</span>
          )}
          {selectedCategory?.is_essential && (
            <span className="badge badge-success badge-xs">Essential</span>
          )}
        </div>

        <div className="flex gap-2">
          {pendingChanges.length > 0 && (
            <>
              <button
                className="btn btn-ghost btn-sm"
                onClick={handleCancel}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleApply}
                disabled={saving}
              >
                {saving ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Applying...
                  </>
                ) : (
                  <>Apply {pendingChanges.length} change{pendingChanges.length !== 1 ? 's' : ''}</>
                )}
              </button>
            </>
          )}
          <button
            className="btn btn-sm btn-outline"
            onClick={fetchCategories}
            disabled={loading}
          >
            Refresh
          </button>
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

      {/* Two column layout */}
      <div className="grid grid-cols-3 gap-4 min-h-[500px]">
        {/* Left column: Category list */}
        <div className="card bg-base-200 col-span-1">
          <div className="card-body p-4">
            <h3 className="font-medium text-sm text-base-content/70 mb-2">Categories</h3>
            <div className="space-y-1 max-h-[450px] overflow-y-auto">
              {categories.filter(c => c.is_active).map(category => (
                <button
                  key={category.id}
                  className={`w-full text-left px-3 py-2 rounded-lg transition-colors flex justify-between items-center ${
                    selectedCategory?.id === category.id
                      ? 'bg-primary text-primary-content'
                      : 'hover:bg-base-300'
                  }`}
                  onClick={() => handleSelectCategory(category)}
                >
                  <span className="flex items-center gap-2">
                    <span className={`badge ${category.color || 'badge-neutral'} badge-xs`}></span>
                    <span className="truncate">{category.name}</span>
                  </span>
                  <span className="text-xs opacity-60">
                    {category.transaction_count || 0}
                  </span>
                </button>
              ))}
            </div>

            {/* Hidden categories section */}
            {categories.filter(c => !c.is_active).length > 0 && (
              <div className="mt-4 pt-4 border-t border-base-300">
                <h4 className="font-medium text-xs text-base-content/50 mb-2">Hidden</h4>
                <div className="space-y-1">
                  {categories.filter(c => !c.is_active).map(category => (
                    <button
                      key={category.id}
                      className="w-full text-left px-3 py-1 rounded text-sm opacity-50 hover:opacity-75"
                      onClick={() => handleSelectCategory(category)}
                    >
                      {category.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right columns: Category details & Subcategories */}
        <div className="col-span-2 space-y-4">
          {selectedCategory ? (
            <>
              {/* Category details */}
              <div className="card bg-base-200">
                <div className="card-body p-4">
                  <div className="space-y-4">
                    {/* Name field */}
                    <div>
                      <label className="label">
                        <span className="label-text font-medium">Category Name</span>
                        {pendingChanges.some(c => c.type === 'category' && c.field === 'name') && (
                          <span className="label-text-alt text-warning">Modified</span>
                        )}
                      </label>
                      <input
                        type="text"
                        className="input input-bordered w-full"
                        value={editingCategoryName}
                        onChange={(e) => handleCategoryNameChange(e.target.value)}
                        placeholder="Category name"
                      />
                    </div>

                    {/* Description field */}
                    <div>
                      <label className="label">
                        <span className="label-text font-medium">Description for LLM</span>
                        {pendingChanges.some(c => c.type === 'category' && c.field === 'description') && (
                          <span className="label-text-alt text-warning">Modified</span>
                        )}
                      </label>
                      <textarea
                        className="textarea textarea-bordered w-full h-20"
                        value={editingCategoryDescription}
                        onChange={(e) => handleCategoryDescriptionChange(e.target.value)}
                        placeholder="Description to help LLM classify transactions accurately..."
                      />
                      <label className="label">
                        <span className="label-text-alt text-base-content/50">
                          This description is included in LLM prompts to improve classification accuracy
                        </span>
                      </label>
                    </div>

                    {/* Stats */}
                    <div className="flex gap-4 text-sm text-base-content/60">
                      <span>{selectedCategory.transaction_count || 0} transactions</span>
                      <span>{selectedCategory.subcategory_count || 0} subcategories</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Subcategories */}
              <div className="card bg-base-200">
                <div className="card-body p-4">
                  <h3 className="font-medium text-sm text-base-content/70 mb-2">
                    Subcategories
                  </h3>

                  {selectedCategory.subcategories?.length > 0 ? (
                    <div className="grid grid-cols-2 gap-2 max-h-[200px] overflow-y-auto">
                      {selectedCategory.subcategories.map(sub => (
                        <button
                          key={sub.id}
                          className={`text-left px-3 py-2 rounded-lg transition-colors ${
                            selectedSubcategory?.id === sub.id
                              ? 'bg-secondary text-secondary-content'
                              : 'bg-base-100 hover:bg-base-300'
                          }`}
                          onClick={() => handleSelectSubcategory(sub)}
                        >
                          <div className="flex justify-between items-center">
                            <span className="truncate">{sub.name}</span>
                            <span className="text-xs opacity-60">{sub.transaction_count || 0}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-base-content/50">No subcategories</p>
                  )}

                  {/* Selected subcategory editor */}
                  {selectedSubcategory && (
                    <div className="mt-4 pt-4 border-t border-base-300 space-y-3">
                      <h4 className="font-medium text-sm">
                        Editing: {selectedSubcategory.name}
                      </h4>

                      <div>
                        <label className="label py-0">
                          <span className="label-text text-sm">Subcategory Name</span>
                          {pendingChanges.some(c => c.type === 'subcategory' && c.field === 'name' && c.id === selectedSubcategory.id) && (
                            <span className="label-text-alt text-warning text-xs">Modified</span>
                          )}
                        </label>
                        <input
                          type="text"
                          className="input input-bordered input-sm w-full"
                          value={editingSubcategoryName}
                          onChange={(e) => handleSubcategoryNameChange(e.target.value)}
                        />
                      </div>

                      <div>
                        <label className="label py-0">
                          <span className="label-text text-sm">Description</span>
                          {pendingChanges.some(c => c.type === 'subcategory' && c.field === 'description' && c.id === selectedSubcategory.id) && (
                            <span className="label-text-alt text-warning text-xs">Modified</span>
                          )}
                        </label>
                        <textarea
                          className="textarea textarea-bordered textarea-sm w-full h-16"
                          value={editingSubcategoryDescription}
                          onChange={(e) => handleSubcategoryDescriptionChange(e.target.value)}
                          placeholder="Optional description for LLM..."
                        />
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          ) : (
            <div className="card bg-base-200 h-full flex items-center justify-center">
              <p className="text-base-content/50">Select a category to edit</p>
            </div>
          )}
        </div>
      </div>

      {/* Rename Confirmation Modal */}
      {showRenameConfirm && renameImpact && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Confirm Rename</h3>
            <p className="py-4">
              Renaming will update the following:
            </p>
            <ul className="list-disc list-inside text-sm space-y-1 mb-4">
              <li>{renameImpact.transactionCount} transactions</li>
              <li>Category rules that reference this category</li>
              <li>LLM enrichment prompts</li>
            </ul>
            <p className="text-sm text-warning">
              This action cannot be undone.
            </p>
            <div className="modal-action">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowRenameConfirm(false)}
                disabled={saving}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={applyChanges}
                disabled={saving}
              >
                {saving ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Applying...
                  </>
                ) : (
                  'Apply Rename'
                )}
              </button>
            </div>
          </div>
          <div
            className="modal-backdrop"
            onClick={() => !saving && setShowRenameConfirm(false)}
          />
        </div>
      )}
    </div>
  );
}
