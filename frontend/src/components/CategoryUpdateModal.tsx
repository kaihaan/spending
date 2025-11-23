import { useState, useEffect } from 'react';
import axios from 'axios';
import { getCategoryColor } from '../utils/categoryColors';

const API_URL = 'http://localhost:5000/api';

interface CategoryUpdateModalProps {
  transactionId: number;
  currentCategory: string;
  merchant: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

export default function CategoryUpdateModal({
  transactionId,
  currentCategory,
  merchant,
  onClose,
  onSuccess
}: CategoryUpdateModalProps) {
  const [newCategory, setNewCategory] = useState(currentCategory);
  const [merchantTransactionCount, setMerchantTransactionCount] = useState(0);
  const [applyToMerchant, setApplyToMerchant] = useState(true);
  const [addToRules, setAddToRules] = useState(true);
  const [loading, setLoading] = useState(false);
  const [fetchingInfo, setFetchingInfo] = useState(true);
  const [categories, setCategories] = useState<string[]>([]);

  useEffect(() => {
    // Fetch merchant info and categories when modal opens
    const fetchData = async () => {
      try {
        setFetchingInfo(true);

        // Fetch merchant info
        const merchantResponse = await axios.get(
          `${API_URL}/transactions/${transactionId}/merchant-info`
        );
        setMerchantTransactionCount(merchantResponse.data.merchant_transaction_count);

        // Fetch all categories (including custom ones)
        const categoriesResponse = await axios.get(`${API_URL}/categories`);
        const categoryNames = categoriesResponse.data.map((cat: any) => cat.name);
        setCategories(categoryNames);
      } catch (err) {
        console.error('Failed to fetch data:', err);
      } finally {
        setFetchingInfo(false);
      }
    };

    fetchData();
  }, [transactionId]);

  const handleSubmit = async () => {
    try {
      setLoading(true);

      await axios.post(
        `${API_URL}/transactions/${transactionId}/category/smart`,
        {
          category: newCategory,
          apply_to_merchant: applyToMerchant && merchant && merchantTransactionCount > 1,
          add_to_rules: addToRules && merchant
        }
      );

      onSuccess();
      onClose();
    } catch (err) {
      console.error('Failed to update category:', err);
      alert('Failed to update category');
    } finally {
      setLoading(false);
    }
  };

  const hasMultipleTransactions = merchantTransactionCount > 1;

  return (
    <div className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg mb-4">Update Transaction Category</h3>

        {fetchingInfo ? (
          <div className="flex justify-center p-4">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        ) : (
          <>
            {/* Category Selection */}
            <div className="form-control mb-4">
              <label className="label">
                <span className="label-text font-semibold">New Category</span>
              </label>
              <select
                className="select select-bordered w-full"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
              >
                {categories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>

            {/* Merchant Info */}
            {merchant && (
              <div className="alert alert-info mb-4">
                <div>
                  <div className="font-semibold">Merchant: {merchant}</div>
                  <div className="text-sm">
                    {merchantTransactionCount} transaction{merchantTransactionCount !== 1 ? 's' : ''} found
                  </div>
                </div>
              </div>
            )}

            {/* Options */}
            <div className="space-y-3">
              {/* Update all from merchant */}
              {merchant && hasMultipleTransactions && (
                <div className="form-control">
                  <label className="label cursor-pointer justify-start gap-3">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-primary"
                      checked={applyToMerchant}
                      onChange={(e) => setApplyToMerchant(e.target.checked)}
                    />
                    <span className="label-text">
                      Update all {merchantTransactionCount} transactions from <strong>{merchant}</strong>
                    </span>
                  </label>
                </div>
              )}

              {/* Add to rules */}
              {merchant && (
                <div className="form-control">
                  <label className="label cursor-pointer justify-start gap-3">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-primary"
                      checked={addToRules}
                      onChange={(e) => setAddToRules(e.target.checked)}
                    />
                    <span className="label-text">
                      Add <strong>{merchant}</strong> to{' '}
                      <span className={`badge ${getCategoryColor(newCategory)} badge-sm`}>
                        {newCategory}
                      </span>{' '}
                      rules (auto-categorize future transactions)
                    </span>
                  </label>
                </div>
              )}

              {!merchant && (
                <div className="alert alert-warning">
                  <span className="text-sm">
                    No merchant information available. Only this transaction will be updated.
                  </span>
                </div>
              )}
            </div>

            {/* Action Buttons */}
            <div className="modal-action">
              <button
                className="btn btn-ghost"
                onClick={onClose}
                disabled={loading}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={loading || newCategory === currentCategory}
              >
                {loading ? (
                  <>
                    <span className="loading loading-spinner loading-sm"></span>
                    Updating...
                  </>
                ) : (
                  'Apply Changes'
                )}
              </button>
            </div>
          </>
        )}
      </div>
      <div className="modal-backdrop" onClick={onClose}></div>
    </div>
  );
}
