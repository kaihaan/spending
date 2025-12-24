import FilterBar from './FilterBar/FilterBar';
import CategoryDrawer from './CategoryDrawer';
import { useFilters } from '../contexts/FilterContext';

/**
 * FilterDrawer - Combines FilterBar and CategoryDrawer into a single
 * drawer component that attaches below the Navigation bar.
 * Similar styling to the Settings page tabs drawer.
 */
export default function FilterDrawer() {
  const { categoryDrawerOpen } = useFilters();

  return (
    <div className="bg-base-200 shadow-sm">
      <div className="container mx-auto px-4">
        <FilterBar />
      </div>

      {/* Category drawer - expands when open */}
      <div
        className={`
          overflow-hidden transition-all duration-300 ease-in-out
          ${categoryDrawerOpen ? 'max-h-96 opacity-100' : 'max-h-0 opacity-0'}
        `}
      >
        <div className="container mx-auto px-4 pb-3">
          <CategoryDrawer />
        </div>
      </div>
    </div>
  );
}
