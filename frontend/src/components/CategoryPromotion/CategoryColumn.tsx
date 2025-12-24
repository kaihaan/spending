import { Category, HiddenCategory } from './types';

interface CategoryColumnProps {
  categories: Category[];
  hiddenCategories: HiddenCategory[];
  selectedCategory: string | null;
  onSelect: (name: string) => void;
  onHide: (name: string) => void;
  onUnhide: (name: string) => void;
  loading: boolean;
}

export default function CategoryColumn({
  categories,
  hiddenCategories,
  selectedCategory,
  onSelect,
  onHide,
  onUnhide,
  loading
}: CategoryColumnProps) {
  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: 'GBP',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="border border-base-300 rounded-lg p-4">
        <h3 className="font-semibold text-sm mb-3">Categories</h3>
        <div className="flex justify-center py-8">
          <span className="loading loading-spinner loading-md"></span>
        </div>
      </div>
    );
  }

  return (
    <div className="border border-base-300 rounded-lg p-4 h-full flex flex-col">
      <h3 className="font-semibold text-sm mb-3">Categories</h3>

      <div className="flex-1 overflow-y-auto space-y-1">
        {categories.map((cat) => (
          <div
            key={cat.name}
            className={`flex items-center justify-between p-2 rounded cursor-pointer hover:bg-base-200 ${
              selectedCategory === cat.name ? 'bg-primary/10 border border-primary/30' : ''
            }`}
            onClick={() => onSelect(cat.name)}
          >
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <button
                className="btn btn-ghost btn-xs text-error hover:bg-error/10"
                onClick={(e) => {
                  e.stopPropagation();
                  onHide(cat.name);
                }}
                title="Hide category"
              >
                -
              </button>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1">
                  <span className="text-sm truncate">{cat.name}</span>
                  {cat.is_custom && (
                    <span className="badge badge-primary badge-xs">custom</span>
                  )}
                </div>
                <span className="text-xs text-base-content/60">
                  {cat.transaction_count} txns
                </span>
              </div>
            </div>
            <span className="text-sm font-medium text-warning whitespace-nowrap ml-2">
              {formatCurrency(cat.total_spend)}
            </span>
          </div>
        ))}

        {categories.length === 0 && (
          <div className="text-center py-4 text-sm text-base-content/60">
            No categories found
          </div>
        )}
      </div>

      {hiddenCategories.length > 0 && (
        <div className="mt-4 pt-3 border-t border-base-300">
          <h4 className="text-xs font-medium text-base-content/60 mb-2">Hidden</h4>
          <div className="space-y-1">
            {hiddenCategories.map((cat) => (
              <div
                key={cat.id}
                className="flex items-center justify-between p-2 rounded bg-base-200/50"
              >
                <span className="text-sm text-base-content/60">{cat.name}</span>
                <button
                  className="btn btn-ghost btn-xs text-success hover:bg-success/10"
                  onClick={() => onUnhide(cat.name)}
                  title="Restore category"
                >
                  Restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
