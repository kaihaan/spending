import { useState, useEffect } from 'react';
import axios from 'axios';
import type { CategoryRules, TransactionChange, ApplyRulesFilters, KeywordSuggestion, SuggestionsResponse, CategoryClassificationPattern } from '../types';
import { getCategoryColor } from '../utils/categoryColors';

const API_URL = 'http://localhost:5000/api';

const DEFAULT_CATEGORIES = [
  'Groceries', 'Transport', 'Dining', 'Entertainment',
  'Utilities', 'Shopping', 'Health', 'Income', 'Other'
];

export default function Rules() {
  const [rules, setRules] = useState<Record<string, string[]>>({});
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Edit state
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [newKeyword, setNewKeyword] = useState('');

  // New category state
  const [showNewCategoryDialog, setShowNewCategoryDialog] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');

  // Preview state
  const [previewChanges, setPreviewChanges] = useState<TransactionChange[]>([]);
  const [showPreview, setShowPreview] = useState(false);
  const [applyFilters, setApplyFilters] = useState<ApplyRulesFilters>({ only_other: true });
  const [selectedChanges, setSelectedChanges] = useState<Set<number>>(new Set());
  const [applying, setApplying] = useState(false);

  // Suggestions state
  const [suggestions, setSuggestions] = useState<KeywordSuggestion[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState<Record<string, string>>({});

  // Huququllah classification patterns state
  const [classificationPatterns, setClassificationPatterns] = useState<Record<string, CategoryClassificationPattern>>({});
  const [patternsLoading, setPatternsLoading] = useState(false);
  const [showPatterns, setShowPatterns] = useState(false);

  useEffect(() => {
    fetchRules();
  }, []);

  const fetchRules = async () => {
    try {
      setLoading(true);
      const response = await axios.get<CategoryRules>(`${API_URL}/rules`);
      setRules(response.data.rules);
      setCategories(response.data.categories);
      setError(null);
    } catch (err) {
      setError('Failed to fetch rules');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddKeyword = async (category: string) => {
    if (!newKeyword.trim()) return;

    try {
      await axios.post(`${API_URL}/rules/keywords`, {
        category,
        keyword: newKeyword.trim()
      });

      setNewKeyword('');
      setEditingCategory(null);
      fetchRules();
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to add keyword');
    }
  };

  const handleRemoveKeyword = async (category: string, keyword: string) => {
    try {
      await axios.delete(`${API_URL}/rules/keywords`, {
        data: { category, keyword }
      });

      fetchRules();
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to remove keyword');
    }
  };

  const handleCreateCategory = async () => {
    if (!newCategoryName.trim()) return;

    try {
      await axios.post(`${API_URL}/rules/categories`, {
        name: newCategoryName.trim()
      });

      setNewCategoryName('');
      setShowNewCategoryDialog(false);
      fetchRules();
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to create category');
    }
  };

  const handleDeleteCategory = async (category: string) => {
    if (!confirm(`Delete category "${category}"? This cannot be undone.`)) return;

    try {
      await axios.delete(`${API_URL}/rules/categories/${category}`);
      fetchRules();
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to delete category');
    }
  };

  const handlePreviewRules = async () => {
    try {
      const response = await axios.post(`${API_URL}/rules/preview`, {
        filters: applyFilters
      });

      setPreviewChanges(response.data.changes);
      setShowPreview(true);

      // Select all by default
      const allIds = new Set(response.data.changes.map((c: TransactionChange) => c.id));
      setSelectedChanges(allIds);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to preview changes');
    }
  };

  const handleApplyRules = async () => {
    if (selectedChanges.size === 0) {
      alert('No transactions selected');
      return;
    }

    try {
      setApplying(true);
      await axios.post(`${API_URL}/rules/apply`, {
        transaction_ids: Array.from(selectedChanges)
      });

      alert(`Successfully updated ${selectedChanges.size} transaction(s)`);
      setShowPreview(false);
      setPreviewChanges([]);
      setSelectedChanges(new Set());

      // Refresh transactions list
      window.dispatchEvent(new Event('transactions-updated'));
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to apply rules');
    } finally {
      setApplying(false);
    }
  };

  const toggleChange = (id: number) => {
    const newSelected = new Set(selectedChanges);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedChanges(newSelected);
  };

  const toggleAllChanges = () => {
    if (selectedChanges.size === previewChanges.length) {
      setSelectedChanges(new Set());
    } else {
      setSelectedChanges(new Set(previewChanges.map(c => c.id)));
    }
  };

  const handleAnalyzeSuggestions = async () => {
    try {
      setSuggestionsLoading(true);
      const response = await axios.get<SuggestionsResponse>(`${API_URL}/rules/suggestions`);

      setSuggestions(response.data.suggestions);
      setShowSuggestions(true);

      // Initialize selected categories with suggestions
      const initialSelections: Record<string, string> = {};
      response.data.suggestions.forEach(suggestion => {
        initialSelections[suggestion.keyword] = suggestion.suggested_category;
      });
      setSelectedCategory(initialSelections);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to analyze suggestions');
    } finally {
      setSuggestionsLoading(false);
    }
  };

  const handleAddSuggestion = async (keyword: string, category: string) => {
    try {
      await axios.post(`${API_URL}/rules/keywords`, {
        category,
        keyword
      });

      // Remove from suggestions
      setSuggestions(suggestions.filter(s => s.keyword !== keyword));

      // Refresh rules
      fetchRules();

      alert(`Added "${keyword}" to ${category}`);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to add keyword');
    }
  };

  const handleFetchClassificationPatterns = async () => {
    try {
      setPatternsLoading(true);
      const response = await axios.get<Record<string, CategoryClassificationPattern>>(`${API_URL}/huququllah/category-patterns`);
      setClassificationPatterns(response.data);
      setShowPatterns(true);
    } catch (err: any) {
      alert(err.response?.data?.error || 'Failed to fetch classification patterns');
    } finally {
      setPatternsLoading(false);
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
    <div className="container mx-auto p-4">
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Categorization Rules</h1>
        <p className="text-base-content/70">
          Manage keywords and categories for automatic transaction categorization
        </p>
      </div>

      {/* Keyword Suggestions Section - Moved to Top */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2 className="text-xl font-semibold">Smart Keyword Suggestions</h2>
            <p className="text-sm text-base-content/70">
              AI-powered analysis of 'Other' category transactions
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleAnalyzeSuggestions}
            disabled={suggestionsLoading}
          >
            {suggestionsLoading ? (
              <>
                <span className="loading loading-spinner loading-sm"></span>
                Analyzing...
              </>
            ) : (
              '🔍 Analyze Transactions'
            )}
          </button>
        </div>

        {showSuggestions && suggestions.length > 0 && (
          <div className="card bg-base-200 shadow">
            <div className="card-body">
              <h3 className="font-semibold mb-4">
                Found {suggestions.length} keyword suggestion(s)
              </h3>

              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Keyword</th>
                      <th>Frequency</th>
                      <th>Suggested Category</th>
                      <th>Confidence</th>
                      <th>Sample</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {suggestions.map((suggestion) => (
                      <tr key={suggestion.keyword}>
                        <td className="font-semibold">{suggestion.keyword}</td>
                        <td>
                          <span className="badge badge-neutral">
                            {suggestion.frequency}x
                          </span>
                        </td>
                        <td>
                          <select
                            className="select select-sm select-bordered"
                            value={selectedCategory[suggestion.keyword] || suggestion.suggested_category}
                            onChange={(e) => setSelectedCategory({
                              ...selectedCategory,
                              [suggestion.keyword]: e.target.value
                            })}
                          >
                            {categories.map(cat => (
                              <option key={cat} value={cat}>{cat}</option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            <progress
                              className="progress progress-primary w-20"
                              value={suggestion.confidence}
                              max="100"
                            ></progress>
                            <span className="text-xs">{suggestion.confidence}%</span>
                          </div>
                        </td>
                        <td className="max-w-xs">
                          <details className="text-xs">
                            <summary className="cursor-pointer text-primary">
                              View samples
                            </summary>
                            <ul className="mt-2 space-y-1">
                              {suggestion.sample_transactions.map((sample, idx) => (
                                <li key={idx} className="truncate text-base-content/70">
                                  {sample}
                                </li>
                              ))}
                            </ul>
                          </details>
                        </td>
                        <td>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => handleAddSuggestion(
                              suggestion.keyword,
                              selectedCategory[suggestion.keyword] || suggestion.suggested_category
                            )}
                          >
                            Add to Rules
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {showSuggestions && suggestions.length === 0 && (
          <div className="alert alert-success">
            <span>
              🎉 Great! All your 'Other' transactions are well categorized. No new patterns found.
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Panel: Category Rules Editor */}
        <div className="space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-xl font-semibold">Categories & Keywords</h2>
            <button
              className="btn btn-primary btn-sm"
              onClick={() => setShowNewCategoryDialog(true)}
            >
              + New Category
            </button>
          </div>

          {categories.map((category) => (
            <div key={category} className="card bg-base-200 shadow">
              <div className="card-body p-4">
                <div className="flex justify-between items-center mb-2">
                  <h3 className={`font-semibold badge ${getCategoryColor(category)} badge-lg`}>
                    {category}
                  </h3>
                  {!DEFAULT_CATEGORIES.includes(category) && (
                    <button
                      className="btn btn-ghost btn-xs text-error"
                      onClick={() => handleDeleteCategory(category)}
                    >
                      Delete
                    </button>
                  )}
                </div>

                <div className="flex flex-wrap gap-2 mb-2">
                  {rules[category]?.map((keyword) => (
                    <div key={keyword} className="badge badge-outline gap-2">
                      {keyword}
                      <button
                        className="text-error"
                        onClick={() => handleRemoveKeyword(category, keyword)}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                  {(!rules[category] || rules[category].length === 0) && (
                    <span className="text-sm text-base-content/50">No keywords yet</span>
                  )}
                </div>

                {editingCategory === category ? (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="Enter keyword..."
                      className="input input-sm input-bordered flex-1"
                      value={newKeyword}
                      onChange={(e) => setNewKeyword(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleAddKeyword(category)}
                      autoFocus
                    />
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleAddKeyword(category)}
                    >
                      Add
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => {
                        setEditingCategory(null);
                        setNewKeyword('');
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    className="btn btn-sm btn-ghost w-full"
                    onClick={() => setEditingCategory(category)}
                  >
                    + Add Keyword
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Right Panel: Apply Rules */}
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Apply Rules to Transactions</h2>

          <div className="card bg-base-200 shadow">
            <div className="card-body">
              <h3 className="font-semibold mb-2">Filter Options</h3>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-2">
                  <input
                    type="radio"
                    className="radio radio-primary"
                    checked={applyFilters.only_other === true}
                    onChange={() => setApplyFilters({ only_other: true })}
                  />
                  <span className="label-text">Only re-categorize 'Other' transactions</span>
                </label>
              </div>

              <div className="form-control">
                <label className="label cursor-pointer justify-start gap-2">
                  <input
                    type="radio"
                    className="radio radio-primary"
                    checked={applyFilters.all === true}
                    onChange={() => setApplyFilters({ all: true })}
                  />
                  <span className="label-text">Re-categorize all transactions</span>
                </label>
              </div>

              <button
                className="btn btn-primary mt-4"
                onClick={handlePreviewRules}
              >
                Preview Changes
              </button>
            </div>
          </div>

          {showPreview && previewChanges.length > 0 && (
            <div className="card bg-base-200 shadow">
              <div className="card-body">
                <div className="flex justify-between items-center mb-4">
                  <h3 className="font-semibold">
                    Preview: {previewChanges.length} transactions would change
                  </h3>
                  <label className="label cursor-pointer gap-2">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-primary"
                      checked={selectedChanges.size === previewChanges.length}
                      onChange={toggleAllChanges}
                    />
                    <span className="label-text">Select All</span>
                  </label>
                </div>

                <div className="overflow-x-auto max-h-96 overflow-y-auto">
                  <table className="table table-sm">
                    <thead>
                      <tr>
                        <th></th>
                        <th>Description</th>
                        <th>Current</th>
                        <th>→</th>
                        <th>New</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previewChanges.map((change) => (
                        <tr key={change.id}>
                          <td>
                            <input
                              type="checkbox"
                              className="checkbox checkbox-sm"
                              checked={selectedChanges.has(change.id)}
                              onChange={() => toggleChange(change.id)}
                            />
                          </td>
                          <td className="max-w-xs truncate">
                            {change.description}
                          </td>
                          <td>
                            <span className={`badge badge-sm ${getCategoryColor(change.current_category)}`}>
                              {change.current_category}
                            </span>
                          </td>
                          <td>→</td>
                          <td>
                            <span className={`badge badge-sm ${getCategoryColor(change.new_category)}`}>
                              {change.new_category}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex gap-2 mt-4">
                  <button
                    className="btn btn-primary flex-1"
                    onClick={handleApplyRules}
                    disabled={applying || selectedChanges.size === 0}
                  >
                    {applying ? 'Applying...' : `Apply to ${selectedChanges.size} transaction(s)`}
                  </button>
                  <button
                    className="btn btn-ghost"
                    onClick={() => {
                      setShowPreview(false);
                      setPreviewChanges([]);
                      setSelectedChanges(new Set());
                    }}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          )}

          {showPreview && previewChanges.length === 0 && (
            <div className="alert alert-info">
              <span>No transactions would be changed with current rules and filters.</span>
            </div>
          )}
        </div>
      </div>

      {/* Huququllah Classification Patterns Section */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <div>
            <h2 className="text-xl font-semibold">Huququllah Classification Patterns</h2>
            <p className="text-sm text-base-content/70">
              View how transactions in each category are typically classified (Essential vs Discretionary)
            </p>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleFetchClassificationPatterns}
            disabled={patternsLoading}
          >
            {patternsLoading ? (
              <>
                <span className="loading loading-spinner loading-sm"></span>
                Loading...
              </>
            ) : (
              '💝 View Patterns'
            )}
          </button>
        </div>

        {showPatterns && Object.keys(classificationPatterns).length > 0 && (
          <div className="card bg-base-200 shadow">
            <div className="card-body">
              <h3 className="font-semibold mb-4">
                Classification patterns for {Object.keys(classificationPatterns).length} categor{Object.keys(classificationPatterns).length === 1 ? 'y' : 'ies'}
              </h3>

              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Category</th>
                      <th>Essential</th>
                      <th>Discretionary</th>
                      <th>Most Common</th>
                      <th>Total Classified</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(classificationPatterns)
                      .sort(([,a], [,b]) => (a.essential_count + a.discretionary_count) - (b.essential_count + b.discretionary_count))
                      .reverse()
                      .map(([category, pattern]) => (
                      <tr key={category}>
                        <td>
                          <span className={`badge ${getCategoryColor(category)}`}>
                            {category}
                          </span>
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            <span className="badge badge-success">{pattern.essential_count}</span>
                            <span className="text-sm text-base-content/70">
                              ({pattern.essential_percentage}%)
                            </span>
                          </div>
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            <span className="badge badge-secondary">{pattern.discretionary_count}</span>
                            <span className="text-sm text-base-content/70">
                              ({pattern.discretionary_percentage}%)
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className={`badge ${
                            pattern.most_common === 'essential' ? 'badge-success' : 'badge-secondary'
                          }`}>
                            {pattern.most_common}
                          </span>
                        </td>
                        <td>
                          {pattern.essential_count + pattern.discretionary_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="alert alert-info mt-4">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" className="stroke-current shrink-0 w-6 h-6">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>These patterns are learned from your past Huququllah classifications and used by the smart suggestion system.</span>
              </div>
            </div>
          </div>
        )}

        {showPatterns && Object.keys(classificationPatterns).length === 0 && (
          <div className="alert alert-warning">
            <span>No classification patterns found. Start classifying transactions in the Huququllah page to see patterns.</span>
          </div>
        )}
      </div>

      {/* New Category Dialog */}
      {showNewCategoryDialog && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Create New Category</h3>
            <div className="py-4">
              <input
                type="text"
                placeholder="Category name..."
                className="input input-bordered w-full"
                value={newCategoryName}
                onChange={(e) => setNewCategoryName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateCategory()}
                autoFocus
              />
            </div>
            <div className="modal-action">
              <button
                className="btn btn-ghost"
                onClick={() => {
                  setShowNewCategoryDialog(false);
                  setNewCategoryName('');
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleCreateCategory}
                disabled={!newCategoryName.trim()}
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
