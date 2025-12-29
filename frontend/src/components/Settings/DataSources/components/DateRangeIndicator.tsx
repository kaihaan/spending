/**
 * DateRangeIndicator Component
 *
 * Displays the date range and staleness indicator for a data source.
 * Shows: "Date Range: 01 Jan - 28 Dec 2025 | Gap: 1 day [Current]"
 */

interface DateRangeIndicatorProps {
  minDate: string | null;
  maxDate: string | null;
  isLoading?: boolean;
}

/**
 * Calculate the number of days between a date and today.
 */
function calculateDaysGap(dateString: string | null): number | null {
  if (!dateString) return null;

  const date = new Date(dateString);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  date.setHours(0, 0, 0, 0);

  const diffTime = today.getTime() - date.getTime();
  const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

  return diffDays;
}

/**
 * Format a date string to a readable format like "01 Jan 2025".
 */
function formatDate(dateString: string | null): string {
  if (!dateString) return 'N/A';

  const date = new Date(dateString);
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/**
 * Get staleness status and styling based on days gap.
 */
function getStalenessStatus(daysGap: number | null): {
  label: string;
  badgeClass: string;
  description: string;
} {
  if (daysGap === null) {
    return {
      label: 'No Data',
      badgeClass: 'badge-ghost',
      description: 'No data available',
    };
  }

  if (daysGap <= 1) {
    return {
      label: 'Current',
      badgeClass: 'badge-success',
      description: 'Up to date',
    };
  }

  if (daysGap <= 7) {
    return {
      label: `${daysGap} days`,
      badgeClass: 'badge-info',
      description: 'Recently synced',
    };
  }

  if (daysGap <= 30) {
    return {
      label: `${daysGap} days`,
      badgeClass: 'badge-warning',
      description: 'May need sync',
    };
  }

  return {
    label: `${daysGap} days`,
    badgeClass: 'badge-error',
    description: 'Stale - needs sync',
  };
}

export default function DateRangeIndicator({
  minDate,
  maxDate,
  isLoading = false,
}: DateRangeIndicatorProps) {
  if (isLoading) {
    return (
      <div className="flex items-center gap-4 p-4 bg-base-200 rounded-lg animate-pulse">
        <div className="h-4 bg-base-300 rounded w-48" />
        <div className="h-4 bg-base-300 rounded w-24" />
      </div>
    );
  }

  const daysGap = calculateDaysGap(maxDate);
  const staleness = getStalenessStatus(daysGap);

  const hasDateRange = minDate && maxDate;

  return (
    <div className="flex flex-wrap items-center gap-4 p-4 bg-base-200 rounded-lg">
      {/* Date Range */}
      <div className="flex items-center gap-2">
        <span className="text-sm opacity-70">Date Range:</span>
        <span className="font-medium">
          {hasDateRange ? (
            <>
              {formatDate(minDate)} - {formatDate(maxDate)}
            </>
          ) : (
            <span className="opacity-50">No data</span>
          )}
        </span>
      </div>

      {/* Staleness Indicator */}
      {hasDateRange && (
        <>
          <span className="opacity-30">|</span>
          <div className="flex items-center gap-2">
            <span className="text-sm opacity-70">Gap:</span>
            <span className={`badge ${staleness.badgeClass}`}>
              {staleness.label}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

export { calculateDaysGap, formatDate, getStalenessStatus };
