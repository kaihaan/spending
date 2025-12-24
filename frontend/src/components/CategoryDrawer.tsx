import { useFilters } from '../contexts/FilterContext';
import { getCategoryColor } from '../utils/categoryColors';

export default function CategoryDrawer() {
  const {
    filters,
    updateFilter,
    uniqueCategories,
    getSubcategoriesForCategory,
    getFilteredCountForCategory,
    categoryDrawerOpen
  } = useFilters();

  const hasCategoryFilter = filters.selectedCategory !== 'All';
  const subcategories = hasCategoryFilter
    ? getSubcategoriesForCategory(filters.selectedCategory)
    : [];

  return (
    <div
      className={`
        overflow-hidden transition-all duration-300 ease-in-out
        ${categoryDrawerOpen ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}
      `}
    >
      <div className="container mx-auto px-4 pt-0 pb-2">
        <div className="bg-base-200 rounded-lg px-3 py-3">
          {/* Categories Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {/* All Categories option */}
            <button
              className={`
                btn btn-sm justify-start gap-2
                ${!hasCategoryFilter ? 'btn-primary' : 'btn-ghost'}
              `}
              onClick={() => {
                updateFilter('selectedCategory', 'All');
                updateFilter('selectedSubcategory', '');
              }}
            >
              <span>All</span>
              <span className="text-xs opacity-70">
                ({getFilteredCountForCategory('All')})
              </span>
            </button>

            {/* Category options */}
            {uniqueCategories.map(category => {
              const count = getFilteredCountForCategory(category);
              if (count === 0) return null;
              const isSelected = filters.selectedCategory === category;

              return (
                <button
                  key={category}
                  className={`
                    btn btn-sm justify-start gap-2
                    ${isSelected ? 'btn-primary' : 'btn-ghost'}
                  `}
                  onClick={() => {
                    updateFilter('selectedCategory', category);
                    updateFilter('selectedSubcategory', '');
                  }}
                >
                  <span className={`badge badge-xs ${getCategoryColor(category)}`} />
                  <span className="truncate">{category}</span>
                  <span className="text-xs opacity-70 ml-auto">({count})</span>
                </button>
              );
            })}
          </div>

          {/* Subcategories Section */}
          {hasCategoryFilter && subcategories.length > 0 && (
            <div className="mt-3 pt-3 border-t border-base-300">
              <div className="text-xs font-semibold text-base-content/60 mb-2">
                Subcategories for {filters.selectedCategory}
              </div>
              <div className="flex flex-wrap gap-2">
                {/* All Subcategories option */}
                <button
                  className={`
                    btn btn-xs
                    ${!filters.selectedSubcategory ? 'btn-secondary' : 'btn-ghost'}
                  `}
                  onClick={() => updateFilter('selectedSubcategory', '')}
                >
                  All
                </button>

                {/* Subcategory options */}
                {subcategories.map(subcat => (
                  <button
                    key={subcat}
                    className={`
                      btn btn-xs
                      ${filters.selectedSubcategory === subcat ? 'btn-secondary' : 'btn-ghost'}
                    `}
                    onClick={() => updateFilter('selectedSubcategory', subcat)}
                  >
                    {subcat}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
