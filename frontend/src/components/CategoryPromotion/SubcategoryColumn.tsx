import type { Subcategory } from './types';

interface SubcategoryColumnProps {
  subcategories: Subcategory[];
  selectedCategory: string | null;
  selectedSubcategoryNames: string[];
  onAdd: (subcategory: Subcategory) => void;
  loading: boolean;
}

export default function SubcategoryColumn({
  subcategories,
  selectedCategory,
  selectedSubcategoryNames,
  onAdd,
  loading
}: SubcategoryColumnProps) {
  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: 'GBP',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const isDisabled = (sub: Subcategory) => {
    return sub.already_mapped || selectedSubcategoryNames.includes(sub.name);
  };

  if (!selectedCategory) {
    return (
      <div className="border border-base-300 rounded-lg p-4 h-full flex flex-col">
        <h3 className="font-semibold text-sm mb-3">Subcategories</h3>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-base-content/60 text-center">
            Select a category to view its subcategories
          </p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="border border-base-300 rounded-lg p-4 h-full flex flex-col">
        <h3 className="font-semibold text-sm mb-3">
          Subcategories: {selectedCategory}
        </h3>
        <div className="flex-1 flex justify-center items-center">
          <span className="loading loading-spinner loading-md"></span>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-base-300 rounded-lg p-4 h-full flex flex-col">
      <h3 className="font-semibold text-sm mb-3">
        Subcategories: <span className="text-primary">{selectedCategory}</span>
      </h3>

      <div className="flex-1 overflow-y-auto space-y-1">
        {subcategories.map((sub) => {
          const disabled = isDisabled(sub);
          return (
            <div
              key={sub.name}
              className={`flex items-center justify-between p-2 rounded ${
                disabled
                  ? 'bg-base-200/50 opacity-50'
                  : 'hover:bg-base-200 cursor-pointer'
              }`}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <button
                  className={`btn btn-ghost btn-xs ${
                    disabled
                      ? 'text-base-content/30 cursor-not-allowed'
                      : 'text-success hover:bg-success/10'
                  }`}
                  onClick={() => !disabled && onAdd(sub)}
                  disabled={disabled}
                  title={
                    sub.already_mapped
                      ? 'Already mapped to another category'
                      : selectedSubcategoryNames.includes(sub.name)
                      ? 'Already selected'
                      : 'Add to new category'
                  }
                >
                  +
                </button>
                <div className="min-w-0 flex-1">
                  <span className="text-sm truncate block">{sub.name}</span>
                  <span className="text-xs text-base-content/60">
                    {sub.transaction_count} txns
                  </span>
                </div>
              </div>
              <span className="text-sm font-medium text-warning whitespace-nowrap ml-2">
                {formatCurrency(sub.total_spend)}
              </span>
            </div>
          );
        })}

        {subcategories.length === 0 && (
          <div className="text-center py-4 text-sm text-base-content/60">
            No subcategories found
          </div>
        )}
      </div>
    </div>
  );
}
