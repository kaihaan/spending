import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useFilters } from '../contexts/FilterContext';
import { getSubcategoriesForCategory } from '../utils/filterUtils';
import D3BarChart from '../components/charts/D3BarChart';
import D3LineChart from '../components/charts/D3LineChart';
import MonthSelector, { type MonthKey } from '../components/MonthSelector';

type ChartView = 'category' | 'timeline';

export default function Dashboard() {
  const { filters, updateFilter, filteredTransactions, transactions, loading, error, uniqueCategories } = useFilters();
  const [chartView, setChartView] = useState<ChartView>('category');
  const [selectedMonth, setSelectedMonth] = useState<MonthKey | null>('average');

  const isAverageMode = selectedMonth === 'average';

  // Detect if AI categorization is needed (only null category or no categories)
  const needsAICategorization =
    uniqueCategories.length === 0 ||
    (uniqueCategories.length === 1 && uniqueCategories[0] === 'null');

  // Process data for category bar chart
  const categoryData = uniqueCategories
    .map(category => {
      const categoryTransactions = filteredTransactions.filter(
        txn => txn.category === category
      );
      const total = categoryTransactions.reduce((sum, txn) => sum + parseFloat(String(txn.amount)), 0);

      return {
        label: category,
        value: parseFloat(total.toFixed(2))
      };
    })
    .filter(item => item.value > 0)
    .sort((a, b) => b.value - a.value);

  // Process data for subcategory bar chart (when a category is selected)
  const subcategoryData = (() => {
    if (filters.selectedCategory === 'All') {
      return [];
    }

    const subcategories = getSubcategoriesForCategory(transactions, filters.selectedCategory);

    return subcategories
      .map(subcategory => {
        const subcategoryTransactions = filteredTransactions.filter(
          txn => txn.category === filters.selectedCategory &&
                 txn.subcategory === subcategory
        );

        const total = subcategoryTransactions.reduce(
          (sum, txn) => sum + parseFloat(String(txn.amount)),
          0
        );

        return {
          label: subcategory,
          value: parseFloat(total.toFixed(2))
        };
      })
      .filter(item => item.value > 0)
      .sort((a, b) => b.value - a.value);
  })();

  // Calculate average monthly spending by category
  const calculateAverageCategoryData = () => {
    // Group all transactions by month and category
    const monthlyTotals: Record<string, Record<string, number>> = {};

    filteredTransactions.forEach(txn => {
      // Skip transactions with null/undefined date
      if (!txn.date) return;

      const monthKey = txn.date.substring(0, 7); // "2024-12"
      if (!monthlyTotals[monthKey]) monthlyTotals[monthKey] = {};
      if (!monthlyTotals[monthKey][txn.category]) monthlyTotals[monthKey][txn.category] = 0;
      monthlyTotals[monthKey][txn.category] += parseFloat(String(txn.amount));
    });

    // Calculate average per category
    const monthCount = Object.keys(monthlyTotals).length || 1;
    const categoryTotals: Record<string, number> = {};

    Object.values(monthlyTotals).forEach(monthData => {
      Object.entries(monthData).forEach(([category, total]) => {
        categoryTotals[category] = (categoryTotals[category] || 0) + total;
      });
    });

    return Object.entries(categoryTotals)
      .map(([label, total]) => ({ label, value: parseFloat((total / monthCount).toFixed(2)) }))
      .filter(item => item.value > 0)
      .sort((a, b) => b.value - a.value);
  };

  // Calculate average monthly spending by subcategory (when a category is selected)
  const calculateAverageSubcategoryData = () => {
    if (filters.selectedCategory === 'All') return [];

    const monthlyTotals: Record<string, Record<string, number>> = {};

    filteredTransactions.forEach(txn => {
      if (txn.category !== filters.selectedCategory) return;
      if (!txn.date) return;
      const monthKey = txn.date.substring(0, 7);
      const subcategory = txn.subcategory || 'Uncategorized';
      if (!monthlyTotals[monthKey]) monthlyTotals[monthKey] = {};
      if (!monthlyTotals[monthKey][subcategory]) monthlyTotals[monthKey][subcategory] = 0;
      monthlyTotals[monthKey][subcategory] += parseFloat(String(txn.amount));
    });

    const monthCount = Object.keys(monthlyTotals).length || 1;
    const subcategoryTotals: Record<string, number> = {};

    Object.values(monthlyTotals).forEach(monthData => {
      Object.entries(monthData).forEach(([subcategory, total]) => {
        subcategoryTotals[subcategory] = (subcategoryTotals[subcategory] || 0) + total;
      });
    });

    return Object.entries(subcategoryTotals)
      .map(([label, total]) => ({ label, value: parseFloat((total / monthCount).toFixed(2)) }))
      .filter(item => item.value > 0)
      .sort((a, b) => b.value - a.value);
  };

  // Determine which chart data to use
  const barChartData = isAverageMode
    ? (filters.selectedCategory !== 'All' ? calculateAverageSubcategoryData() : calculateAverageCategoryData())
    : (filters.selectedCategory !== 'All' ? subcategoryData : categoryData);

  const chartTitle = isAverageMode
    ? (filters.selectedCategory !== 'All'
        ? `Average Monthly Spending: ${filters.selectedCategory} Subcategories`
        : 'Average Monthly Spending by Category')
    : (filters.selectedCategory !== 'All' ? `Spending by Subcategory: ${filters.selectedCategory}` : undefined);

  // Process data for timeline chart
  const timelineData = (() => {
    const dailySpending: Record<string, number> = {};

    filteredTransactions.forEach(txn => {
      if (!dailySpending[txn.date]) {
        dailySpending[txn.date] = 0;
      }
      dailySpending[txn.date] += parseFloat(String(txn.amount));
    });

    return Object.entries(dailySpending)
      .map(([date, total]) => ({
        date,
        value: parseFloat(total.toFixed(2))
      }))
      .sort((a, b) => a.date.localeCompare(b.date));
  })();

  // Handle month selection
  const handleMonthSelect = (month: MonthKey) => {
    // Toggle off if clicking active month
    if (month === selectedMonth) {
      setSelectedMonth(null);
      return;
    }

    setSelectedMonth(month);

    if (month === 'average') {
      // Keep current filter range for average calculation
      return;
    }

    // Calculate first and last day of selected month
    const now = new Date();
    const monthsBack = month === 'current' ? 0 : parseInt(month.split('-')[1]);
    const firstDay = new Date(now.getFullYear(), now.getMonth() - monthsBack, 1);
    const lastDay = new Date(firstDay.getFullYear(), firstDay.getMonth() + 1, 0);

    updateFilter('dateFrom', firstDay.toISOString().split('T')[0]);
    updateFilter('dateTo', lastDay.toISOString().split('T')[0]);
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

  if (transactions.length === 0) {
    return (
      <div className="alert alert-info">
        <span>No transactions yet. Import bank statements to get started!</span>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4 space-y-4">
      <div className="card bg-base-200 shadow-xl">
        <div className="card-body">
          {/* Chart View Toggle and Month Selector */}
          <div className="flex justify-between items-center mb-4">
            <div className="flex gap-2">
              <button
                className={`btn btn-sm ${chartView === 'category' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setChartView('category')}
              >
                By Category
              </button>
              <button
                className={`btn btn-sm ${chartView === 'timeline' ? 'btn-primary' : 'btn-ghost'}`}
                onClick={() => setChartView('timeline')}
              >
                Timeline
              </button>
            </div>

            {/* Month Selector - only show for category view */}
            {chartView === 'category' && (
              <MonthSelector
                selectedMonth={selectedMonth}
                onMonthSelect={handleMonthSelect}
              />
            )}
          </div>

          {/* Chart Display */}
          {filteredTransactions.length === 0 ? (
            <div className="alert alert-info">
              <span>No transactions match the current filters</span>
            </div>
          ) : (
            <div className="relative bg-base-100 p-4 rounded-lg">
              {/* AI Needed Banner - shows when no categorization has been run */}
              {chartView === 'category' && needsAICategorization && (
                <div className="absolute inset-0 flex items-center justify-center z-10 bg-base-100/80 backdrop-blur-sm rounded-lg">
                  <div className="text-center space-y-3 p-6">
                    <div className="text-lg font-semibold text-warning flex items-center justify-center gap-2">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                      </svg>
                      AI Categorization Needed
                    </div>
                    <p className="text-base-content/70 text-sm">
                      Transactions haven't been categorized yet
                    </p>
                    <Link
                      to="/settings#enrichment"
                      className="btn btn-primary btn-sm"
                    >
                      Configure AI Settings →
                    </Link>
                  </div>
                </div>
              )}

              {chartView === 'category' && barChartData.length > 0 && (
                <div className="space-y-2">
                  {/* Subcategory view: show back button + title */}
                  {filters.selectedCategory !== 'All' && (
                    <div className="flex items-center justify-between">
                      <button
                        className="btn btn-sm btn-ghost gap-1"
                        onClick={() => {
                          updateFilter('selectedCategory', 'All');
                          updateFilter('selectedSubcategory', '');
                        }}
                      >
                        ← Back to Categories
                      </button>
                      <h3 className="text-lg font-semibold">
                        {chartTitle}
                      </h3>
                      <div className="w-[140px]"></div> {/* Spacer for centering */}
                    </div>
                  )}
                  {/* Category view: centered title only */}
                  {filters.selectedCategory === 'All' && chartTitle && (
                    <h3 className="text-lg font-semibold text-center">
                      {chartTitle}
                    </h3>
                  )}
                  <D3BarChart
                    data={barChartData}
                    height={400}
                    onBarClick={(label) => {
                      if (filters.selectedCategory === 'All') {
                        // Clicking a category bar → filter to that category
                        updateFilter('selectedCategory', label);
                        updateFilter('selectedSubcategory', '');
                      } else {
                        // Clicking a subcategory bar → filter to that subcategory
                        updateFilter('selectedSubcategory', label);
                      }
                    }}
                  />
                </div>
              )}

              {chartView === 'timeline' && timelineData.length > 0 && (
                <D3LineChart data={timelineData} height={400} />
              )}

              {chartView === 'category' && barChartData.length === 0 && (
                <div className="alert alert-info">
                  <span>
                    {filters.selectedCategory !== 'All'
                      ? `No subcategory spending data for ${filters.selectedCategory}`
                      : 'No spending data for selected filters'
                    }
                  </span>
                </div>
              )}

              {chartView === 'timeline' && timelineData.length === 0 && (
                <div className="alert alert-info">
                  <span>No timeline data for selected filters</span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
