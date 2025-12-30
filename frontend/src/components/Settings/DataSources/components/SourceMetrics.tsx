/**
 * SourceMetrics Component
 *
 * Displays metrics cards for a data source: Total, Matched, Unmatched.
 * Used in individual source detail tabs.
 */

interface SourceMetricsProps {
  total: number;
  matched: number;
  unmatched: number;
  isLoading?: boolean;
  labels?: {
    total?: string;
    matched?: string;
    unmatched?: string;
  };
}

export default function SourceMetrics({
  total,
  matched,
  unmatched,
  isLoading = false,
  labels = {},
}: SourceMetricsProps) {
  const {
    total: totalLabel = 'Total',
    matched: matchedLabel = 'Matched',
    unmatched: unmatchedLabel = 'Unmatched',
  } = labels;

  if (isLoading) {
    return (
      <div className="grid grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="stat bg-base-200 rounded-lg animate-pulse">
            <div className="stat-title h-4 bg-base-300 rounded w-16 mb-2" />
            <div className="stat-value h-8 bg-base-300 rounded w-20" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="stat bg-base-200 rounded-lg">
        <div className="stat-title">{totalLabel}</div>
        <div className="stat-value text-2xl">{total.toLocaleString()}</div>
      </div>

      <div className="stat bg-base-200 rounded-lg">
        <div className="stat-title">{matchedLabel}</div>
        <div className="stat-value text-2xl text-success">{matched.toLocaleString()}</div>
      </div>

      <div className="stat bg-base-200 rounded-lg">
        <div className="stat-title">{unmatchedLabel}</div>
        <div className="stat-value text-2xl text-warning">{unmatched.toLocaleString()}</div>
      </div>
    </div>
  );
}
