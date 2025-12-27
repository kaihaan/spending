import { useState, useEffect } from 'react';
import axios from 'axios';
import CategoryColumn from '../CategoryPromotion/CategoryColumn';
import SubcategoryColumn from '../CategoryPromotion/SubcategoryColumn';
import NewCategoryBuilder from '../CategoryPromotion/NewCategoryBuilder';
import { CategoryEditor } from './CategoryEditor';
import type {
  Category,
  HiddenCategory,
  Subcategory,
  SelectedSubcategory,
  CategorySummaryResponse,
  SubcategoryResponse
} from '../CategoryPromotion/types';

const API_URL = 'http://localhost:5000/api';

type TabType = 'edit' | 'promote';

export default function CategoriesTab() {
  // Tab state
  const [activeTab, setActiveTab] = useState<TabType>('edit');

  // Data state
  const [categories, setCategories] = useState<Category[]>([]);
  const [hiddenCategories, setHiddenCategories] = useState<HiddenCategory[]>([]);
  const [subcategories, setSubcategories] = useState<Subcategory[]>([]);

  // Selection state
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedSubcategories, setSelectedSubcategories] = useState<SelectedSubcategory[]>([]);
  const [newCategoryName, setNewCategoryName] = useState('');

  // Loading/error state
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [loadingSubcategories, setLoadingSubcategories] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Confirmation modal state
  const [showHideConfirm, setShowHideConfirm] = useState(false);
  const [categoryToHide, setCategoryToHide] = useState<string | null>(null);

  // Success modal state
  const [showSuccess, setShowSuccess] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  // Fetch categories on mount
  useEffect(() => {
    fetchCategories();
  }, []);

  // Fetch subcategories when category selected
  useEffect(() => {
    if (selectedCategory) {
      fetchSubcategories(selectedCategory);
    } else {
      setSubcategories([]);
    }
  }, [selectedCategory]);

  const fetchCategories = async () => {
    try {
      setLoadingCategories(true);
      const response = await axios.get<CategorySummaryResponse>(`${API_URL}/categories/summary`);
      setCategories(response.data.categories);
      setHiddenCategories(response.data.hidden_categories);
    } catch (err: any) {
      console.error('Error fetching categories:', err);
      setError(err.response?.data?.error || 'Failed to load categories');
    } finally {
      setLoadingCategories(false);
    }
  };

  const fetchSubcategories = async (categoryName: string) => {
    try {
      setLoadingSubcategories(true);
      const response = await axios.get<SubcategoryResponse>(
        `${API_URL}/categories/${encodeURIComponent(categoryName)}/subcategories`
      );
      setSubcategories(response.data.subcategories);
    } catch (err: any) {
      console.error('Error fetching subcategories:', err);
      setSubcategories([]);
    } finally {
      setLoadingSubcategories(false);
    }
  };

  const handleSelectCategory = (name: string) => {
    setSelectedCategory(name === selectedCategory ? null : name);
  };

  const handleAddSubcategory = (subcategory: Subcategory) => {
    if (!selectedCategory) return;

    const newSelected: SelectedSubcategory = {
      name: subcategory.name,
      total_spend: subcategory.total_spend,
      original_category: selectedCategory
    };

    setSelectedSubcategories((prev) => [...prev, newSelected]);
  };

  const handleRemoveSubcategory = (name: string) => {
    setSelectedSubcategories((prev) => prev.filter((s) => s.name !== name));
  };

  const handleHideCategory = (name: string) => {
    setCategoryToHide(name);
    setShowHideConfirm(true);
  };

  const confirmHideCategory = async () => {
    if (!categoryToHide) return;

    try {
      setSubmitting(true);
      const response = await axios.post(`${API_URL}/categories/hide`, {
        category_name: categoryToHide
      });

      setShowHideConfirm(false);
      setCategoryToHide(null);

      // Show success message
      setSuccessMessage(response.data.message);
      setShowSuccess(true);

      // Refresh data
      await fetchCategories();

      // Clear selection if the hidden category was selected
      if (selectedCategory === categoryToHide) {
        setSelectedCategory(null);
        setSubcategories([]);
      }
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to hide category');
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnhideCategory = async (name: string) => {
    try {
      setSubmitting(true);
      const response = await axios.post(`${API_URL}/categories/unhide`, {
        category_name: name
      });

      setSuccessMessage(response.data.message);
      setShowSuccess(true);

      await fetchCategories();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to restore category');
    } finally {
      setSubmitting(false);
    }
  };

  const handleCreateCategory = async () => {
    if (!newCategoryName.trim() || selectedSubcategories.length === 0) return;

    try {
      setSubmitting(true);
      setError(null);

      const response = await axios.post(`${API_URL}/categories/promote`, {
        new_category_name: newCategoryName.trim(),
        subcategories: selectedSubcategories.map((s) => ({
          name: s.name,
          original_category: s.original_category
        }))
      });

      // Show success
      setSuccessMessage(response.data.message);
      setShowSuccess(true);

      // Reset form
      setNewCategoryName('');
      setSelectedSubcategories([]);
      setSelectedCategory(null);

      // Refresh data
      await fetchCategories();
    } catch (err: any) {
      setError(err.response?.data?.error || 'Failed to create category');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Tabs */}
      <div className="tabs tabs-boxed bg-base-200 p-1 w-fit">
        <button
          className={`tab ${activeTab === 'edit' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('edit')}
        >
          Edit Categories
        </button>
        <button
          className={`tab ${activeTab === 'promote' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('promote')}
        >
          Promote Subcategories
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'edit' ? (
        <CategoryEditor />
      ) : (
        <>
          {/* Header for Promote tab */}
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-lg font-semibold">Promote Subcategories</h2>
              <p className="text-sm text-base-content/60">
                Create new categories by promoting existing subcategories
              </p>
            </div>
            <button
              className="btn btn-sm btn-outline"
              onClick={fetchCategories}
              disabled={loadingCategories}
            >
              Refresh
            </button>
          </div>

          {/* Error display */}
          {error && (
            <div className="alert alert-error">
              <span>{error}</span>
              <button className="btn btn-ghost btn-xs" onClick={() => setError(null)}>
                Dismiss
              </button>
            </div>
          )}

          {/* Three column layout */}
          <div className="grid grid-cols-3 gap-4 min-h-[500px]">
            <CategoryColumn
              categories={categories}
              hiddenCategories={hiddenCategories}
              selectedCategory={selectedCategory}
              onSelect={handleSelectCategory}
              onHide={handleHideCategory}
              onUnhide={handleUnhideCategory}
              loading={loadingCategories}
            />

            <SubcategoryColumn
              subcategories={subcategories}
              selectedCategory={selectedCategory}
              selectedSubcategoryNames={selectedSubcategories.map((s) => s.name)}
              onAdd={handleAddSubcategory}
              loading={loadingSubcategories}
            />

            <NewCategoryBuilder
              name={newCategoryName}
              onNameChange={setNewCategoryName}
              subcategories={selectedSubcategories}
              onRemove={handleRemoveSubcategory}
              onSubmit={handleCreateCategory}
              submitting={submitting}
              error={error}
            />
          </div>
        </>
      )}

      {/* Hide Confirmation Modal */}
      {showHideConfirm && categoryToHide && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg">Hide Category?</h3>
            <p className="py-4">
              Hiding <strong>"{categoryToHide}"</strong> will:
            </p>
            <ul className="list-disc list-inside text-sm space-y-1 mb-4">
              <li>Remove all transactions from this category</li>
              <li>Reset them for re-enrichment by the LLM</li>
              <li>Exclude this category from future LLM prompts</li>
            </ul>
            <p className="text-sm text-warning">
              Transactions will be re-categorized the next time you run enrichment.
            </p>
            <div className="modal-action">
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setShowHideConfirm(false);
                  setCategoryToHide(null);
                }}
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                className="btn btn-error btn-sm"
                onClick={confirmHideCategory}
                disabled={submitting}
              >
                {submitting ? (
                  <>
                    <span className="loading loading-spinner loading-xs"></span>
                    Hiding...
                  </>
                ) : (
                  'Hide Category'
                )}
              </button>
            </div>
          </div>
          <div
            className="modal-backdrop"
            onClick={() => !submitting && setShowHideConfirm(false)}
          />
        </div>
      )}

      {/* Success Modal */}
      {showSuccess && (
        <div className="modal modal-open">
          <div className="modal-box">
            <h3 className="font-bold text-lg text-success">Success</h3>
            <p className="py-4">{successMessage}</p>
            <div className="modal-action">
              <button
                className="btn btn-primary btn-sm"
                onClick={() => setShowSuccess(false)}
              >
                OK
              </button>
            </div>
          </div>
          <div className="modal-backdrop" onClick={() => setShowSuccess(false)} />
        </div>
      )}
    </div>
  );
}
