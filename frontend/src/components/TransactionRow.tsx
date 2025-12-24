import { memo, Fragment, useState } from 'react';
import type { Transaction, EnrichmentSource } from '../types';
import { getCategoryColor } from '../utils/categoryColors';

// Source type labels for display
const SOURCE_TYPE_LABELS: Record<EnrichmentSource['source_type'], { label: string; color: string }> = {
  amazon: { label: 'Amazon', color: 'badge-warning' },
  amazon_business: { label: 'Amazon Biz', color: 'badge-warning' },
  apple: { label: 'Apple', color: 'badge-info' },
  gmail: { label: 'Email', color: 'badge-secondary' },
  manual: { label: 'Manual', color: 'badge-success' },
};

// Format time: "23:12"
const formatTime = (dateStr: string): string => {
  const date = new Date(dateStr);
  return date.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
};

export interface ColumnVisibility {
  date: boolean;
  description: boolean;
  lookup_details: boolean;
  pre_enrichment_status: boolean;
  amount: boolean;
  category: boolean;
  merchant_clean_name: boolean;
  subcategory: boolean;
  merchant_type: boolean;
  essential_discretionary: boolean;
  payment_method: boolean;
  payment_method_subtype: boolean;
  purchase_date: boolean;
  confidence_score: boolean;
  enrichment_source: boolean;
}

export type ColumnKey = keyof ColumnVisibility;
export type ColumnOrder = ColumnKey[];

// Props passed to cell render functions for interactive columns
export interface CellRenderProps {
  isToggling: boolean;
  effectiveRequired: boolean;
  onToggleEnrichment: (txnId: number, currentRequired: boolean) => void;
  onViewEnrichmentSource?: (sourceId: number, transactionId: number) => void;
}

interface ColumnConfig {
  key: ColumnKey;
  header: string;
  group: 'info' | 'enrichment';
  renderCell: (txn: Transaction, props: CellRenderProps) => React.ReactNode;
}

// Centralized column configuration - single source of truth for all column definitions
export const COLUMN_CONFIG: Record<ColumnKey, ColumnConfig> = {
  date: {
    key: 'date',
    header: 'Time',
    group: 'info',
    renderCell: (txn) => (
      <td className="text-sm">{formatTime(txn.date)}</td>
    ),
  },
  description: {
    key: 'description',
    header: 'Description',
    group: 'info',
    renderCell: (txn) => (
      <td className="text-sm" title={txn.description}>{txn.description}</td>
    ),
  },
  lookup_details: {
    key: 'lookup_details',
    header: 'Lookup Details',
    group: 'info',
    renderCell: (txn, { onViewEnrichmentSource }) => {
      const sources = txn.enrichment_sources || [];
      const primarySource = sources.find(s => s.is_primary) || sources[0];
      const additionalSources = sources.filter(s => s !== primarySource);
      const hasMultipleSources = additionalSources.length > 0;

      // No enrichment sources available
      if (sources.length === 0) {
        return (
          <td className="text-sm">
            <span className="text-base-content/30">-</span>
          </td>
        );
      }

      const handleBadgeClick = (source: typeof primarySource, e: React.MouseEvent) => {
        e.stopPropagation();
        // The 'id' field in EnrichmentSource refers to the transaction_enrichment_sources.id
        if (source?.id && onViewEnrichmentSource) {
          onViewEnrichmentSource(source.id, txn.id);
        }
      };

      return (
        <td className="text-sm">
          <div className="flex items-center gap-1">
            {/* Primary source description */}
            <span
              className="text-base-content font-medium italic truncate max-w-[300px]"
              title={primarySource?.description || ''}
            >
              {primarySource?.description || '-'}
            </span>

            {/* Badge showing source type - clickable */}
            {primarySource && (
              <button
                onClick={(e) => handleBadgeClick(primarySource, e)}
                className={`badge badge-xs ${SOURCE_TYPE_LABELS[primarySource.source_type]?.color || 'badge-ghost'} cursor-pointer hover:opacity-80 transition-opacity`}
                title="Click to view details"
              >
                {SOURCE_TYPE_LABELS[primarySource.source_type]?.label || primarySource.source_type}
              </button>
            )}

            {/* Additional sources dropdown */}
            {hasMultipleSources && (
              <div className="dropdown dropdown-hover dropdown-end">
                <div
                  tabIndex={0}
                  role="button"
                  className="badge badge-xs badge-primary cursor-pointer"
                  title={`${additionalSources.length} more source(s)`}
                >
                  +{additionalSources.length}
                </div>
                <ul
                  tabIndex={0}
                  className="dropdown-content z-[1] menu p-2 shadow-lg bg-base-200 rounded-box w-80 max-h-60 overflow-y-auto"
                >
                  {additionalSources.map((source, idx) => (
                    <li key={idx}>
                      <button
                        className="flex flex-col gap-1 py-2 w-full text-left hover:bg-base-300"
                        onClick={(e) => handleBadgeClick(source, e)}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`badge badge-xs ${SOURCE_TYPE_LABELS[source.source_type]?.color || 'badge-ghost'}`}>
                            {SOURCE_TYPE_LABELS[source.source_type]?.label || source.source_type}
                          </span>
                          {source.confidence && (
                            <span className="text-xs text-base-content/50">{source.confidence}%</span>
                          )}
                        </div>
                        <span className="text-sm">{source.description}</span>
                        {source.order_id && (
                          <span className="text-xs text-base-content/50">Order: {source.order_id}</span>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </td>
      );
    },
  },
  pre_enrichment_status: {
    key: 'pre_enrichment_status',
    header: 'Pre-Enrichment',
    group: 'info',
    renderCell: (txn) => (
      <td className="text-sm text-center">
        {txn.pre_enrichment_status && txn.pre_enrichment_status !== 'None' ? (
          <span className={`badge badge-sm ${
            txn.pre_enrichment_status === 'Matched' ? 'badge-success' :
            txn.pre_enrichment_status === 'Apple' ? 'badge-warning' :
            txn.pre_enrichment_status === 'AMZN' ? 'badge-warning' :
            txn.pre_enrichment_status === 'AMZN RTN' ? 'badge-info' :
            txn.pre_enrichment_status === 'AMZN BIZ' ? 'badge-warning' :
            txn.pre_enrichment_status === 'Gmail' ? 'badge-secondary' :
            'badge-ghost'
          }`}>
            {txn.pre_enrichment_status}
          </span>
        ) : (
          <span className="text-base-content/30">-</span>
        )}
      </td>
    ),
  },
  amount: {
    key: 'amount',
    header: 'Amount',
    group: 'info',
    renderCell: (txn) => (
      <td className={txn.transaction_type === 'DEBIT' ? 'text-error font-semibold' : 'text-success font-semibold'}>
        £{parseFloat(String(txn.amount)).toFixed(2)}
      </td>
    ),
  },
  category: {
    key: 'category',
    header: 'Category',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm">
        <span className={`badge ${getCategoryColor(txn.category)}`}>
          {txn.category || '-'}
        </span>
      </td>
    ),
  },
  subcategory: {
    key: 'subcategory',
    header: 'Subcategory',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm text-base-content/70">{txn.subcategory || '-'}</td>
    ),
  },
  merchant_clean_name: {
    key: 'merchant_clean_name',
    header: 'Clean Merchant',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm text-base-content/70 font-medium">{txn.merchant_clean_name || '-'}</td>
    ),
  },
  merchant_type: {
    key: 'merchant_type',
    header: 'Merchant Type',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm text-base-content/70">{txn.merchant_type || '-'}</td>
    ),
  },
  essential_discretionary: {
    key: 'essential_discretionary',
    header: 'Required',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm">
        {txn.essential_discretionary ? (
          <span className={`badge ${txn.essential_discretionary === 'Essential' ? 'badge-success' : 'badge-secondary'}`}>
            {txn.essential_discretionary}
          </span>
        ) : <span className="text-base-content/40">-</span>}
      </td>
    ),
  },
  payment_method: {
    key: 'payment_method',
    header: 'Payment Method',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm text-base-content/70">{txn.payment_method || '-'}</td>
    ),
  },
  payment_method_subtype: {
    key: 'payment_method_subtype',
    header: 'Payment Subtype',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm text-base-content/70">{txn.payment_method_subtype || '-'}</td>
    ),
  },
  purchase_date: {
    key: 'purchase_date',
    header: 'Purchase Date',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm text-base-content/70">{txn.purchase_date || '-'}</td>
    ),
  },
  confidence_score: {
    key: 'confidence_score',
    header: 'Confidence',
    group: 'enrichment',
    renderCell: (txn) => (
      <td className="text-sm text-center">
        {txn.confidence_score ? (
          <span className={`badge ${txn.confidence_score >= 0.9 ? 'badge-success' : txn.confidence_score >= 0.7 ? 'badge-warning' : 'badge-error'}`}>
            {(txn.confidence_score * 100).toFixed(0)}%
          </span>
        ) : <span className="text-base-content/40">-</span>}
      </td>
    ),
  },
  enrichment_source: {
    key: 'enrichment_source',
    header: 'Think',
    group: 'enrichment',
    renderCell: (txn, { isToggling, effectiveRequired, onToggleEnrichment }) => (
      <td className="text-sm">
        {(() => {
          // Priority 1: If marked as required, show "required" badge
          if (effectiveRequired) {
            return (
              <button
                onClick={() => onToggleEnrichment(txn.id, true)}
                disabled={isToggling}
                className={`badge badge-sm badge-warning cursor-pointer hover:opacity-70 transition-opacity ${isToggling ? 'opacity-50' : ''}`}
                title={txn.enrichment_source ? "Queued for re-enrichment - click to cancel" : "Click to skip enrichment"}
              >
                {isToggling ? '...' : 'required'}
              </button>
            );
          }

          // Priority 2: Has enrichment source - show it (clickable to re-queue)
          if (txn.enrichment_source) {
            return (
              <button
                onClick={() => onToggleEnrichment(txn.id, false)}
                disabled={isToggling}
                className={`badge badge-sm cursor-pointer hover:opacity-70 transition-opacity ${
                  txn.enrichment_source === 'llm' ? 'badge-info' :
                  txn.enrichment_source === 'rule' ? 'badge-success' :
                  txn.enrichment_source === 'cache' ? 'badge-secondary' :
                  txn.enrichment_source === 'lookup' ? 'badge-primary' :
                  txn.enrichment_source === 'regex' ? 'badge-warning' :
                  txn.enrichment_source === 'manual' ? 'badge-success' :
                  'badge-ghost'
                } ${isToggling ? 'opacity-50' : ''}`}
                title="Click to mark for re-enrichment"
              >
                {isToggling ? '...' : txn.enrichment_source}
              </button>
            );
          }

          // Priority 3: Not enriched and not required - show dash
          return (
            <button
              onClick={() => onToggleEnrichment(txn.id, false)}
              disabled={isToggling}
              className={`text-base-content/40 cursor-pointer hover:text-base-content transition-colors ${isToggling ? 'opacity-50' : ''}`}
              title="Click to mark for enrichment"
            >
              {isToggling ? '...' : '—'}
            </button>
          );
        })()}
      </td>
    ),
  },
};

interface TransactionRowProps {
  txn: Transaction;
  columnVisibility: ColumnVisibility;
  columnOrder: ColumnOrder;
  dataGroup: string;  // Date key for imperative DOM targeting
  isToggling: boolean;
  effectiveRequired: boolean;
  onToggleEnrichment: (txnId: number, currentRequired: boolean) => void;
  onViewEnrichmentSource?: (sourceId: number, transactionId: number) => void;
}

/**
 * Memoized transaction row component.
 *
 * Returns a Fragment of <td> cells for use with TableVirtuoso.
 * Virtuoso wraps these in a <tr> automatically.
 * Renders cells in the order specified by columnOrder.
 */
const TransactionRow = memo(function TransactionRow({
  txn,
  columnVisibility,
  columnOrder,
  dataGroup,
  isToggling,
  effectiveRequired,
  onToggleEnrichment,
  onViewEnrichmentSource,
}: TransactionRowProps) {
  const cellProps: CellRenderProps = { isToggling, effectiveRequired, onToggleEnrichment, onViewEnrichmentSource };

  return (
    <Fragment>
      {columnOrder.map(key => {
        if (!columnVisibility[key]) return null;
        return (
          <Fragment key={key}>
            {COLUMN_CONFIG[key].renderCell(txn, cellProps)}
          </Fragment>
        );
      })}
      {/* Spacer cell to match spacer column */}
      <td key="spacer" className="w-0 p-0" />
    </Fragment>
  );
}, (prevProps, nextProps) => {
  // Custom equality check - only re-render when these specific props change
  // dataGroup is stable (date key) so not included in comparison
  return (
    prevProps.txn === nextProps.txn &&
    prevProps.isToggling === nextProps.isToggling &&
    prevProps.effectiveRequired === nextProps.effectiveRequired &&
    prevProps.columnVisibility === nextProps.columnVisibility &&
    prevProps.columnOrder === nextProps.columnOrder
  );
});

export default TransactionRow;
