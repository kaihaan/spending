import { useState, useRef, useEffect } from 'react';
import { useFilters } from '../../contexts/FilterContext';
import { getCategoryColor } from '../../utils/categoryColors';

export default function FilterBar() {
  const {
    filters,
    updateFilter,
    clearAllFilters,
    filteredTransactions,
    categoryDrawerOpen,
    setCategoryDrawerOpen
  } = useFilters();

  const [dateDropdownOpen, setDateDropdownOpen] = useState(false);

  const dateRef = useRef<HTMLDivElement>(null);

  // Close date dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dateRef.current && !dateRef.current.contains(event.target as Node)) {
        setDateDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Calculate totals
  const totalDebit = filteredTransactions
    .filter(txn => txn.transaction_type === 'DEBIT')
    .reduce((sum, txn) => sum + parseFloat(String(txn.amount)), 0);

  const totalCredit = filteredTransactions
    .filter(txn => txn.transaction_type === 'CREDIT')
    .reduce((sum, txn) => sum + parseFloat(String(txn.amount)), 0);

  const hasActiveFilters = filters.selectedCategory !== 'All' ||
    filters.dateFrom || filters.dateTo || filters.searchKeyword ||
    filters.showInbound !== filters.showOutbound ||
    filters.showEssential || filters.showDiscretionary;

  const hasDateFilter = filters.dateFrom || filters.dateTo;
  const hasCategoryFilter = filters.selectedCategory !== 'All';

  // Format date range for button display
  const formatDateRange = () => {
    if (!filters.dateFrom && !filters.dateTo) return 'Dates';
    const from = filters.dateFrom ? new Date(filters.dateFrom).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '';
    const to = filters.dateTo ? new Date(filters.dateTo).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '';
    if (from && to) return `${from} - ${to}`;
    if (from) return `From ${from}`;
    return `Until ${to}`;
  };

  // Date preset handlers
  const setDatePreset = (days: number) => {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - days);
    updateFilter('dateFrom', from.toISOString().split('T')[0]);
    updateFilter('dateTo', to.toISOString().split('T')[0]);
    setDateDropdownOpen(false);
  };

  // Get button label for category/subcategory
  const getCategoryButtonLabel = () => {
    if (!hasCategoryFilter) return 'Categories';
    if (filters.selectedSubcategory) {
      return `${filters.selectedCategory} > ${filters.selectedSubcategory}`;
    }
    return filters.selectedCategory;
  };

  return (
    <div className="flex flex-wrap gap-2 items-center py-2">

        {/* Search Input */}
        <div className="relative flex-1 min-w-[200px]">
          <input
            type="text"
            placeholder="Search..."
            className="input input-sm input-bordered w-full pr-8"
            value={filters.searchKeyword}
            onChange={(e) => updateFilter('searchKeyword', e.target.value)}
          />
          {filters.searchKeyword && (
            <button
              className="absolute right-2 top-1/2 -translate-y-1/2 text-base-content/50 hover:text-base-content"
              onClick={() => updateFilter('searchKeyword', '')}
            >
              ×
            </button>
          )}
        </div>

        {/* Date Range Dropdown */}
        <div className="relative" ref={dateRef}>
          <label
            tabIndex={0}
            className={`btn btn-sm ${hasDateFilter ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => {
              setDateDropdownOpen(!dateDropdownOpen);
              setCategoryDropdownOpen(false);
            }}
          >
            {formatDateRange()}
          </label>
          {dateDropdownOpen && (
            <div className="absolute top-full left-0 z-50 menu p-3 shadow bg-base-100 rounded-box w-64 mt-1">
              <div className="space-y-2">
                <button className="btn btn-ghost btn-sm w-full justify-start" onClick={() => setDatePreset(7)}>Last 7 days</button>
                <button className="btn btn-ghost btn-sm w-full justify-start" onClick={() => setDatePreset(30)}>Last 30 days</button>
                <button className="btn btn-ghost btn-sm w-full justify-start" onClick={() => setDatePreset(90)}>Last 3 months</button>
                <button className="btn btn-ghost btn-sm w-full justify-start" onClick={() => setDatePreset(365)}>Last year</button>
                <div className="divider my-1"></div>
                <div className="space-y-2">
                  <label className="text-xs font-semibold">Custom Range</label>
                  <input
                    type="date"
                    className="input input-sm input-bordered w-full"
                    value={filters.dateFrom}
                    onChange={(e) => updateFilter('dateFrom', e.target.value)}
                  />
                  <input
                    type="date"
                    className="input input-sm input-bordered w-full"
                    value={filters.dateTo}
                    onChange={(e) => updateFilter('dateTo', e.target.value)}
                  />
                </div>
                {hasDateFilter && (
                  <button
                    className="btn btn-ghost btn-sm w-full"
                    onClick={() => {
                      updateFilter('dateFrom', '');
                      updateFilter('dateTo', '');
                      setDateDropdownOpen(false);
                    }}
                  >
                    Clear Dates
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Category Drawer Toggle */}
        <button
          className={`btn btn-sm gap-1 ${hasCategoryFilter ? 'btn-primary' : categoryDrawerOpen ? 'btn-active' : 'btn-ghost'}`}
          onClick={() => {
            setCategoryDrawerOpen(!categoryDrawerOpen);
            setDateDropdownOpen(false);
          }}
        >
          {hasCategoryFilter && (
            <span className={`badge badge-xs ${getCategoryColor(filters.selectedCategory)}`} />
          )}
          <span>{getCategoryButtonLabel()}</span>
          <span className="text-xs opacity-70">{categoryDrawerOpen ? '▲' : '▼'}</span>
        </button>

        {/* Direction Toggles (In/Out) */}
        <div className="flex items-center gap-1">
          <button
            className={`btn btn-sm ${filters.showInbound ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => updateFilter('showInbound', !filters.showInbound)}
            title="Show inbound transactions (credits/refunds)"
          >
            In
          </button>
          <button
            className={`btn btn-sm ${filters.showOutbound ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => updateFilter('showOutbound', !filters.showOutbound)}
            title="Show outbound transactions (debits/spending)"
          >
            Out
          </button>
        </div>

        {/* Huququllah Toggles */}
        <div className="flex items-center gap-1">
          <button
            className={`btn btn-sm ${filters.showEssential ? 'btn-success' : 'btn-ghost'}`}
            onClick={() => {
              updateFilter('showEssential', !filters.showEssential);
              if (!filters.showEssential) updateFilter('showDiscretionary', false);
            }}
            title="Show only essential spending (Huququllah)"
          >
            Essential
          </button>
          <button
            className={`btn btn-sm ${filters.showDiscretionary ? 'btn-secondary' : 'btn-ghost'}`}
            onClick={() => {
              updateFilter('showDiscretionary', !filters.showDiscretionary);
              if (!filters.showDiscretionary) updateFilter('showEssential', false);
            }}
            title="Show only discretionary spending (Huququllah)"
          >
            Discretionary
          </button>
        </div>

        {/* Totals */}
        <div className="flex items-center gap-3 text-sm ml-auto">
          <span className="text-error font-semibold">DEBIT: £{totalDebit.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          <span className="text-success font-semibold">CREDIT: £{totalCredit.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
          <span className="text-base-content/60">{filteredTransactions.length} txns</span>
        </div>

        {/* Clear All Button */}
        {hasActiveFilters && (
          <button
            className="btn btn-ghost btn-sm text-error"
            onClick={clearAllFilters}
          >
            Clear
          </button>
        )}
    </div>
  );
}
