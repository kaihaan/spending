/**
 * SourceSummaryTable Component
 *
 * Displays a compact summary table of all data sources with key metrics.
 * Clicking on a row navigates to that source's detail tab.
 */

import { calculateDaysGap, getStalenessStatus } from './components/DateRangeIndicator';
import { useTableStyles } from '../../../hooks/useTableStyles';
import type {
  SourceTabId,
  AmazonStats,
  ReturnsStats,
  AppleStats,
  AmazonBusinessStats,
  GmailStats,
} from './types';

interface SourceSummaryTableProps {
  amazonStats: AmazonStats | null;
  returnsStats: ReturnsStats | null;
  appleStats: AppleStats | null;
  businessStats: AmazonBusinessStats | null;
  gmailStats: GmailStats | null;
  isLoading: boolean;
  onNavigateToTab: (tabId: SourceTabId) => void;
}

interface SourceRow {
  id: SourceTabId;
  name: string;
  total: number;
  matched: number;
  unmatched: number;
  maxDate: string | null;
  minDate: string | null;
}

export default function SourceSummaryTable({
  amazonStats,
  returnsStats,
  appleStats,
  businessStats,
  gmailStats,
  isLoading,
  onNavigateToTab,
}: SourceSummaryTableProps) {
  const { style: glassStyle, className: glassClassName } = useTableStyles();

  // Build rows from stats
  const rows: SourceRow[] = [
    {
      id: 'amazon',
      name: 'Amazon Purchases',
      total: amazonStats?.total_orders ?? 0,
      matched: amazonStats?.total_matched ?? 0,
      unmatched: amazonStats?.total_unmatched ?? 0,
      maxDate: amazonStats?.max_order_date ?? null,
      minDate: amazonStats?.min_order_date ?? null,
    },
    {
      id: 'returns',
      name: 'Amazon Returns',
      total: returnsStats?.total_returns ?? 0,
      matched: returnsStats?.matched_returns ?? 0,
      unmatched: returnsStats?.unmatched_returns ?? 0,
      maxDate: returnsStats?.max_return_date ?? null,
      minDate: returnsStats?.min_return_date ?? null,
    },
    {
      id: 'business',
      name: 'Amazon Business',
      total: businessStats?.total_orders ?? 0,
      matched: businessStats?.total_matched ?? 0,
      unmatched: businessStats?.total_unmatched ?? 0,
      maxDate: businessStats?.max_order_date ?? null,
      minDate: businessStats?.min_order_date ?? null,
    },
    {
      id: 'apple',
      name: 'Apple App Store',
      total: appleStats?.total_transactions ?? 0,
      matched: appleStats?.matched_transactions ?? 0,
      unmatched: appleStats?.unmatched_transactions ?? 0,
      maxDate: appleStats?.max_transaction_date ?? null,
      minDate: appleStats?.min_transaction_date ?? null,
    },
    {
      id: 'gmail',
      name: 'Gmail Receipts',
      total: gmailStats?.total_receipts ?? 0,
      matched: gmailStats?.matched_receipts ?? 0,
      unmatched: (gmailStats?.total_receipts ?? 0) - (gmailStats?.matched_receipts ?? 0),
      maxDate: gmailStats?.max_receipt_date ?? null,
      minDate: gmailStats?.min_receipt_date ?? null,
    },
  ];

  if (isLoading) {
    return (
      <div className={`overflow-x-auto rounded-lg ${glassClassName}`} style={glassStyle}>
        <table className="table">
          <thead>
            <tr>
              <th>Source</th>
              <th className="text-right">Total</th>
              <th className="text-right">Matched</th>
              <th className="text-right">Unmatched</th>
              <th className="text-right">Match %</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {[1, 2, 3, 4, 5].map((i) => (
              <tr key={i} className="animate-pulse">
                <td><div className="h-4 bg-base-300 rounded w-32" /></td>
                <td className="text-right"><div className="h-4 bg-base-300 rounded w-12 ml-auto" /></td>
                <td className="text-right"><div className="h-4 bg-base-300 rounded w-12 ml-auto" /></td>
                <td className="text-right"><div className="h-4 bg-base-300 rounded w-12 ml-auto" /></td>
                <td className="text-right"><div className="h-4 bg-base-300 rounded w-12 ml-auto" /></td>
                <td><div className="h-4 bg-base-300 rounded w-20" /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className={`overflow-x-auto rounded-lg ${glassClassName}`} style={glassStyle}>
      <table className="table">
        <thead>
          <tr>
            <th>Source</th>
            <th className="text-right">Total</th>
            <th className="text-right">Matched</th>
            <th className="text-right">Unmatched</th>
            <th className="text-right">Match %</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const matchPercentage = row.total > 0
              ? Math.round((row.matched / row.total) * 100)
              : 0;
            const daysGap = calculateDaysGap(row.maxDate);
            const staleness = getStalenessStatus(daysGap);

            return (
              <tr
                key={row.id}
                className="cursor-pointer hover:bg-base-200 transition-colors"
                onClick={() => onNavigateToTab(row.id)}
              >
                <td>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{row.name}</span>
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="h-4 w-4 opacity-30"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  </div>
                </td>
                <td className="text-right font-mono">{row.total.toLocaleString()}</td>
                <td className="text-right font-mono text-success">{row.matched.toLocaleString()}</td>
                <td className="text-right font-mono text-warning">{row.unmatched.toLocaleString()}</td>
                <td className="text-right">
                  <span className={`font-mono ${
                    matchPercentage >= 90 ? 'text-success' :
                    matchPercentage >= 70 ? 'text-warning' : 'text-error'
                  }`}>
                    {matchPercentage}%
                  </span>
                </td>
                <td>
                  <span className={`badge badge-sm ${staleness.badgeClass}`}>
                    {staleness.label}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
