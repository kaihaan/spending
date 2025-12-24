import { SelectedSubcategory } from './types';

interface NewCategoryBuilderProps {
  name: string;
  onNameChange: (name: string) => void;
  subcategories: SelectedSubcategory[];
  onRemove: (name: string) => void;
  onSubmit: () => void;
  submitting: boolean;
  error: string | null;
}

export default function NewCategoryBuilder({
  name,
  onNameChange,
  subcategories,
  onRemove,
  onSubmit,
  submitting,
  error
}: NewCategoryBuilderProps) {
  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: 'GBP',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const totalSpend = subcategories.reduce((sum, sub) => sum + sub.total_spend, 0);
  const isValid = name.trim().length > 0 && subcategories.length > 0;

  return (
    <div className="border border-base-300 rounded-lg p-4 h-full flex flex-col">
      <h3 className="font-semibold text-sm mb-3">New Category</h3>

      <div className="mb-4">
        <input
          type="text"
          className="input input-sm input-bordered w-full"
          placeholder="Category name..."
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          disabled={submitting}
        />
        {error && (
          <p className="text-xs text-error mt-1">{error}</p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        {subcategories.length > 0 ? (
          <div className="space-y-1">
            <p className="text-xs text-base-content/60 mb-2">Selected subcategories:</p>
            {subcategories.map((sub) => (
              <div
                key={sub.name}
                className="flex items-center justify-between p-2 rounded bg-primary/5 border border-primary/20"
              >
                <div className="min-w-0 flex-1">
                  <span className="text-sm truncate block">{sub.name}</span>
                  <span className="text-xs text-base-content/60">
                    from {sub.original_category}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-warning whitespace-nowrap">
                    {formatCurrency(sub.total_spend)}
                  </span>
                  <button
                    className="btn btn-ghost btn-xs text-error hover:bg-error/10"
                    onClick={() => onRemove(sub.name)}
                    disabled={submitting}
                    title="Remove"
                  >
                    x
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-8 text-sm text-base-content/60">
            <p>Add subcategories using the + button</p>
          </div>
        )}
      </div>

      {subcategories.length > 0 && (
        <div className="mt-4 pt-3 border-t border-base-300">
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-medium">Total:</span>
            <span className="text-lg font-bold text-warning">
              {formatCurrency(totalSpend)}
            </span>
          </div>

          <button
            className="btn btn-sm btn-primary w-full"
            onClick={onSubmit}
            disabled={!isValid || submitting}
          >
            {submitting ? (
              <>
                <span className="loading loading-spinner loading-xs"></span>
                Creating...
              </>
            ) : (
              'Add Category'
            )}
          </button>
        </div>
      )}
    </div>
  );
}
