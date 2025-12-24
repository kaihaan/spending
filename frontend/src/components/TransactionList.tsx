import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { TableVirtuoso } from 'react-virtuoso';
import axios from 'axios';
import type { Transaction, Category } from '../types';
import CategoryUpdateModal from './CategoryUpdateModal';
import EnrichmentSourceDetailModal from './EnrichmentSourceDetailModal';
import { useFilters } from '../contexts/FilterContext';
import TransactionRow, { ColumnVisibility, ColumnOrder, ColumnKey, COLUMN_CONFIG } from './TransactionRow';

// Virtual row types for flattened data structure
type VirtualRow =
  | { type: 'header'; dateKey: string; count: number; formattedDate: string }
  | { type: 'transaction'; dateKey: string; txn: Transaction };

const API_URL = 'http://localhost:5000/api';

// Format date for group header: "Mon 12th November, 2025"
const formatDateHeader = (dateStr: string): string => {
  const date = new Date(dateStr);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December'];

  const dayName = days[date.getDay()];
  const day = date.getDate();
  const month = months[date.getMonth()];
  const year = date.getFullYear();

  // Add ordinal suffix (1st, 2nd, 3rd, etc.)
  const ordinal = (n: number) => {
    const s = ['th', 'st', 'nd', 'rd'];
    const v = n % 100;
    return n + (s[(v - 20) % 10] || s[v] || s[0]);
  };

  return `${dayName} ${ordinal(day)} ${month}, ${year}`;
};

// Get date key for grouping (YYYY-MM-DD)
const getDateKey = (dateStr: string): string => {
  return new Date(dateStr).toISOString().split('T')[0];
};

const DEFAULT_COLUMN_VISIBILITY: ColumnVisibility = {
  date: false,  // Hidden by default - TrueLayer only provides dates, not times
  description: true,
  lookup_details: true,
  pre_enrichment_status: false,
  amount: true,
  category: true,
  merchant_clean_name: true,
  subcategory: true,
  merchant_type: false,
  essential_discretionary: true,
  payment_method: false,
  payment_method_subtype: false,
  purchase_date: false,
  confidence_score: true,
  enrichment_source: true
};

// Default column widths (numeric, in pixels) - user can resize
const DEFAULT_COLUMN_WIDTHS: Record<keyof ColumnVisibility, number> = {
  date: 70,
  description: 200,
  lookup_details: 160,
  pre_enrichment_status: 100,
  amount: 90,
  category: 120,
  merchant_clean_name: 140,
  subcategory: 100,
  merchant_type: 100,
  essential_discretionary: 140,
  payment_method: 110,
  payment_method_subtype: 110,
  purchase_date: 100,
  confidence_score: 90,
  enrichment_source: 110,
};

const MIN_COLUMN_WIDTH = 40; // Minimum width to prevent columns from disappearing

const loadColumnWidths = (): Record<keyof ColumnVisibility, number> => {
  const saved = localStorage.getItem('transactionColumnWidths');
  return saved ? JSON.parse(saved) : DEFAULT_COLUMN_WIDTHS;
};

const saveColumnWidths = (widths: Record<keyof ColumnVisibility, number>) => {
  localStorage.setItem('transactionColumnWidths', JSON.stringify(widths));
};

const loadColumnVisibility = (): ColumnVisibility => {
  const saved = localStorage.getItem('transactionColumnVisibility');
  return saved ? JSON.parse(saved) : DEFAULT_COLUMN_VISIBILITY;
};

const saveColumnVisibility = (visibility: ColumnVisibility) => {
  localStorage.setItem('transactionColumnVisibility', JSON.stringify(visibility));
};

// Default column order - determines display sequence
const DEFAULT_COLUMN_ORDER: ColumnOrder = [
  'date', 'description', 'lookup_details', 'pre_enrichment_status', 'amount',
  'category', 'subcategory', 'merchant_clean_name', 'merchant_type',
  'essential_discretionary', 'payment_method', 'payment_method_subtype',
  'purchase_date', 'confidence_score', 'enrichment_source',
];

const loadColumnOrder = (): ColumnOrder => {
  const saved = localStorage.getItem('transactionColumnOrder');
  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      // Validate: ensure all keys present and correct count
      if (parsed.length === DEFAULT_COLUMN_ORDER.length) {
        const defaultSet = new Set(DEFAULT_COLUMN_ORDER);
        if (parsed.every((key: string) => defaultSet.has(key as ColumnKey))) {
          return parsed;
        }
      }
    } catch {}
  }
  return DEFAULT_COLUMN_ORDER;
};

const saveColumnOrder = (order: ColumnOrder) => {
  localStorage.setItem('transactionColumnOrder', JSON.stringify(order));
};

// Resize handle component for column headers
interface ResizeHandleProps {
  onResizeStart: (actualWidth: number) => void;
  onResize: (delta: number) => void;
  onResizeEnd: () => void;
}

const ResizeHandle = ({ onResizeStart, onResize, onResizeEnd }: ResizeHandleProps) => {
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation(); // Prevent header click events
    const startX = e.pageX;

    // Measure actual rendered width of the parent <th> to prevent width jumps
    const th = (e.target as HTMLElement).closest('th');
    const actualWidth = th?.getBoundingClientRect().width ?? 0;
    onResizeStart(actualWidth);

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.pageX - startX;
      onResize(delta);
    };

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      onResizeEnd();
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  return (
    <div
      onMouseDown={handleMouseDown}
      className="resize-handle"
      title="Drag to resize column"
    />
  );
};

export default function TransactionList() {
  const { filteredTransactions, transactions, loading, error, refreshTransactions, filters } = useFilters();
  const [categories, setCategories] = useState<Category[]>([]);
  const [editingTransaction, setEditingTransaction] = useState<Transaction | null>(null);
  // Enrichment source detail modal state
  const [viewingEnrichmentSource, setViewingEnrichmentSource] = useState<{
    sourceId: number;
    transactionId: number;
  } | null>(null);
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibility>(loadColumnVisibility());
  // Resizable column widths - stored in localStorage
  const [columnWidths, setColumnWidths] = useState<Record<keyof ColumnVisibility, number>>(loadColumnWidths);
  const [resizingColumn, setResizingColumn] = useState<keyof ColumnVisibility | null>(null);
  // Use ref instead of state to avoid stale closure issues during resize
  const resizeStartWidthRef = useRef<number>(0);
  // Column order - stored in localStorage
  const [columnOrder, setColumnOrder] = useState<ColumnOrder>(loadColumnOrder);
  // Drag-and-drop state for column reordering
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  // State-driven collapse for virtualization (collapsed groups are filtered out of data)
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [togglingIds, setTogglingIds] = useState<Set<number>>(new Set());
  const [localRequiredState, setLocalRequiredState] = useState<Map<number, boolean>>(new Map());
  // Column drawer state
  const [isColumnDrawerOpen, setIsColumnDrawerOpen] = useState(false);

  // Toggle enrichment_required for a transaction - memoized with useCallback
  const toggleEnrichmentRequired = useCallback(async (txnId: number, currentRequired: boolean) => {
    setTogglingIds(prev => new Set(prev).add(txnId));
    // Optimistic update - toggle the state immediately
    setLocalRequiredState(prev => new Map(prev).set(txnId, !currentRequired));

    try {
      await axios.post(`${API_URL}/transactions/${txnId}/toggle-required`);
      // Don't call refreshTransactions() - optimistic update is sufficient
      // This prevents page jump and scroll position loss
    } catch (err) {
      console.error('Failed to toggle enrichment required:', err);
      // Revert optimistic update on error
      setLocalRequiredState(prev => {
        const next = new Map(prev);
        next.delete(txnId);
        return next;
      });
    } finally {
      setTogglingIds(prev => {
        const next = new Set(prev);
        next.delete(txnId);
        return next;
      });
    }
  }, []);

  // Open enrichment source detail modal
  const handleViewEnrichmentSource = useCallback((sourceId: number, transactionId: number) => {
    setViewingEnrichmentSource({ sourceId, transactionId });
  }, []);

  // Get effective enrichment_required value (local state takes precedence for optimistic updates)
  const getEffectiveRequired = (txn: Transaction): boolean => {
    if (localRequiredState.has(txn.id)) {
      return localRequiredState.get(txn.id)!;
    }
    return txn.enrichment_required ?? true;
  };

  // Group transactions by date
  const groupedTransactions = useMemo(() => {
    const groups: { [key: string]: Transaction[] } = {};

    filteredTransactions.forEach(txn => {
      const dateKey = getDateKey(txn.date);
      if (!groups[dateKey]) {
        groups[dateKey] = [];
      }
      groups[dateKey].push(txn);
    });

    // Return as array of [dateKey, transactions] sorted by date desc
    return Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0]));
  }, [filteredTransactions]);

  // Flatten grouped data for virtualization (headers + transactions in one array)
  // Collapsed groups only show header, expanded groups show header + all transactions
  const flattenedRows = useMemo(() => {
    const rows: VirtualRow[] = [];
    for (const [dateKey, txns] of groupedTransactions) {
      // Always add header row
      rows.push({
        type: 'header',
        dateKey,
        count: txns.length,
        formattedDate: formatDateHeader(dateKey),
      });
      // Only add transaction rows if group is not collapsed
      if (!collapsedGroups.has(dateKey)) {
        for (const txn of txns) {
          rows.push({ type: 'transaction', dateKey, txn });
        }
      }
    }
    return rows;
  }, [groupedTransactions, collapsedGroups]);

  // Count visible columns for colSpan
  const visibleColumnCount = useMemo(() => {
    return Object.values(columnVisibility).filter(Boolean).length;
  }, [columnVisibility]);

  // State-driven toggle for virtualization - collapsed groups are filtered from flattenedRows
  const toggleGroup = useCallback((dateKey: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev);
      if (next.has(dateKey)) {
        next.delete(dateKey);
      } else {
        next.add(dateKey);
      }
      return next;
    });
  }, []);

  // Sync all column widths to match actual rendered widths (safety net for table-layout redistribution)
  const syncAllColumnWidths = useCallback(() => {
    const headerRow = document.querySelector('thead tr');
    if (!headerRow) return;

    // Get all th elements except the spacer (last one)
    const ths = Array.from(headerRow.querySelectorAll('th')).slice(0, -1);
    const actualWidths: Record<keyof ColumnVisibility, number> = { ...columnWidths };
    let thIndex = 0;

    columnOrder.forEach(key => {
      if (columnVisibility[key] && ths[thIndex]) {
        actualWidths[key] = ths[thIndex].getBoundingClientRect().width;
        thIndex++;
      }
    });

    setColumnWidths(actualWidths);
  }, [columnOrder, columnVisibility, columnWidths]);

  // Column resize handlers
  const startResize = useCallback((column: keyof ColumnVisibility, actualWidth: number) => {
    // Sync all columns first to prevent cascade effects from table-layout redistribution
    syncAllColumnWidths();
    setResizingColumn(column);
    // Use ref for immediate availability - avoids stale closure in handleResize
    resizeStartWidthRef.current = actualWidth;
  }, [syncAllColumnWidths]);

  const handleResize = useCallback((column: keyof ColumnVisibility, delta: number) => {
    if (resizingColumn !== column && resizingColumn !== null) return;

    setColumnWidths(prev => ({
      ...prev,
      // Read from ref for always-current value (avoids stale closure)
      [column]: Math.max(MIN_COLUMN_WIDTH, resizeStartWidthRef.current + delta),
    }));
  }, [resizingColumn]);

  const endResize = useCallback(() => {
    setResizingColumn(null);
    resizeStartWidthRef.current = 0;
  }, []);

  // Column reordering drag handlers
  const handleDragStart = useCallback((index: number) => {
    setDraggedIndex(index);
  }, []);

  const handleDragOver = useCallback((index: number) => {
    if (draggedIndex !== null && draggedIndex !== index) {
      setDragOverIndex(index);
    }
  }, [draggedIndex]);

  const handleDragEnd = useCallback(() => {
    if (draggedIndex !== null && dragOverIndex !== null && draggedIndex !== dragOverIndex) {
      setColumnOrder(prev => {
        const newOrder = [...prev];
        const [removed] = newOrder.splice(draggedIndex, 1);
        newOrder.splice(dragOverIndex, 0, removed);
        return newOrder;
      });
    }
    setDraggedIndex(null);
    setDragOverIndex(null);
  }, [draggedIndex, dragOverIndex]);

  useEffect(() => {
    fetchCategories();
  }, []);

  // Save column widths to localStorage when they change
  useEffect(() => {
    saveColumnWidths(columnWidths);
  }, [columnWidths]);

  // Save column visibility to localStorage whenever it changes
  useEffect(() => {
    saveColumnVisibility(columnVisibility);
  }, [columnVisibility]);

  // Save column order to localStorage whenever it changes
  useEffect(() => {
    saveColumnOrder(columnOrder);
  }, [columnOrder]);

  // Escape key closes the column drawer
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isColumnDrawerOpen) {
        setIsColumnDrawerOpen(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isColumnDrawerOpen]);

  const toggleColumnVisibility = (column: keyof ColumnVisibility) => {
    setColumnVisibility(prev => ({
      ...prev,
      [column]: !prev[column]
    }));
  };

  const resetColumnSettings = () => {
    setColumnVisibility(DEFAULT_COLUMN_VISIBILITY);
    setColumnOrder(DEFAULT_COLUMN_ORDER);
    setColumnWidths(DEFAULT_COLUMN_WIDTHS);
  };

  const fetchCategories = async () => {
    try {
      const response = await axios.get<Category[]>(`${API_URL}/categories`);
      setCategories(response.data);
    } catch (err) {
      console.error('Failed to fetch categories:', err);
    }
  };

  const handleModalSuccess = () => {
    // Refresh transactions after successful update
    refreshTransactions();
  };

  const handleClassificationChange = async (transactionId: number, classification: 'essential' | 'discretionary' | null) => {
    try {
      await axios.put(`${API_URL}/transactions/${transactionId}/huququllah`, {
        classification
      });
      // Refresh transactions to show updated classification
      refreshTransactions();
    } catch (err) {
      console.error('Failed to update classification:', err);
      alert('Failed to update classification');
    }
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
    <div className="relative">
      {/* Gear tab - positioned outside container at right edge */}
      <button
        onClick={() => setIsColumnDrawerOpen(!isColumnDrawerOpen)}
        className={`
          absolute left-full top-0 z-30
          w-8 h-8 flex items-center justify-center
          bg-base-300 hover:bg-base-200
          rounded-r-lg
          border border-l-0 border-base-content/20
          transition-all duration-300
          ${isColumnDrawerOpen ? 'opacity-0 pointer-events-none' : 'opacity-100'}
        `}
        title="Column settings"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>

      {/* Inner container with overflow-hidden for table and drawer */}
      <div className="relative overflow-hidden">
        {/* Virtualized Transactions Table */}
        <div className="overflow-x-auto">
        <TableVirtuoso
          style={{ height: 'calc(100vh - 300px)', minHeight: '400px' }}
          data={flattenedRows}
          components={{
            Table: ({ style, ...props }) => (
              <table
                {...props}
                className="table table-zebra table-fixed"
                style={{ ...style, width: '100%', tableLayout: 'fixed' }}
              >
                <colgroup>
                  {columnOrder.map(key =>
                    columnVisibility[key] && <col key={key} style={{ width: columnWidths[key] }} />
                  )}
                  {/* Spacer column absorbs extra table width */}
                  <col key="spacer" style={{ width: 'auto' }} />
                </colgroup>
                {props.children}
              </table>
            ),
            TableHead: React.forwardRef((props, ref) => (
              <thead {...props} ref={ref} className="sticky top-0 z-10 bg-base-100">
                <tr>
                  {columnOrder.map(key => {
                    if (!columnVisibility[key]) return null;
                    return (
                      <th key={key} className="relative">
                        {COLUMN_CONFIG[key].header}
                        <ResizeHandle
                          onResizeStart={(actualWidth) => startResize(key, actualWidth)}
                          onResize={(delta) => handleResize(key, delta)}
                          onResizeEnd={endResize}
                        />
                      </th>
                    );
                  })}
                  {/* Spacer header cell */}
                  <th key="spacer" className="w-0 p-0" />
                </tr>
              </thead>
            )),
            TableBody: React.forwardRef((props, ref) => <tbody {...props} ref={ref} />),
            TableRow: ({ item, ...props }) => {
              // Add data-transaction-row for CSS animation on transaction rows only
              const isTransaction = item.type === 'transaction';
              return <tr {...props} {...(isTransaction && { 'data-transaction-row': true })} />;
            },
          }}
          fixedHeaderContent={() => null}
          itemContent={(index, row) => {
            if (row.type === 'header') {
              // Date header row
              const isCollapsed = collapsedGroups.has(row.dateKey);
              return (
                <td
                  colSpan={visibleColumnCount + 1}  /* +1 for spacer column */
                  className="bg-base-300 py-1 px-2 cursor-pointer hover:bg-base-200/70 transition-colors"
                  onClick={() => toggleGroup(row.dateKey)}
                >
                  <div className="flex items-center gap-2">
                    <svg
                      className={`w-4 h-4 chevron-icon ${isCollapsed ? '' : 'rotate-90'}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                    <span className="text-xs text-base-content/60 font-medium">
                      {row.formattedDate}
                    </span>
                    <span className="text-xs text-base-content/40">
                      ({row.count} transaction{row.count !== 1 ? 's' : ''})
                    </span>
                  </div>
                </td>
              );
            }
            // Transaction row - render cells inline (Virtuoso wraps in <tr>)
            const txn = row.txn;
            return (
              <TransactionRow
                txn={txn}
                columnVisibility={columnVisibility}
                columnOrder={columnOrder}
                dataGroup={row.dateKey}
                isToggling={togglingIds.has(txn.id)}
                effectiveRequired={getEffectiveRequired(txn)}
                onToggleEnrichment={toggleEnrichmentRequired}
                onViewEnrichmentSource={handleViewEnrichmentSource}
              />
            );
          }}
        />
      </div>

      {/* Dark Backdrop (no blur) */}
      {isColumnDrawerOpen && (
        <div
          className="absolute inset-0 bg-black/30 z-10 transition-all duration-300 rounded-lg"
          onClick={() => setIsColumnDrawerOpen(false)}
        />
      )}

      {/* Column Drawer Panel (glassmorphism) */}
      <div
        className={`
          absolute top-0 right-0 bottom-0
          bg-black/40 backdrop-blur-md shadow-xl border-l border-white/10
          transform transition-transform duration-300 ease-in-out
          ${isColumnDrawerOpen ? 'translate-x-0' : 'translate-x-full'}
          z-20 overflow-y-auto
        `}
      >
        <div className="p-4 w-64">
          {/* Header */}
          <div className="flex items-center justify-between mb-2">
            <h3 className="font-semibold text-base">Columns</h3>
            <button
              onClick={() => setIsColumnDrawerOpen(false)}
              className="btn btn-ghost btn-sm btn-circle"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Instructions */}
          <p className="text-xs text-base-content/60 mb-2">
            Drag to reorder • Check to show
          </p>

          {/* Column List */}
          <ul className="space-y-1">
            {columnOrder.map((key, index) => (
              <li
                key={key}
                draggable
                onDragStart={() => handleDragStart(index)}
                onDragOver={(e) => {
                  e.preventDefault();
                  handleDragOver(index);
                }}
                onDragEnd={handleDragEnd}
                className={`rounded transition-all ${
                  draggedIndex === index ? 'opacity-50 bg-base-300' : ''
                } ${dragOverIndex === index ? 'border-t-2 border-primary' : ''}`}
              >
                <label className="flex items-center gap-2 cursor-pointer hover:bg-base-300 p-2 rounded">
                  {/* Drag handle */}
                  <span className="drag-handle text-base-content/40 hover:text-base-content">
                    <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                      <circle cx="9" cy="6" r="1.5" />
                      <circle cx="15" cy="6" r="1.5" />
                      <circle cx="9" cy="12" r="1.5" />
                      <circle cx="15" cy="12" r="1.5" />
                      <circle cx="9" cy="18" r="1.5" />
                      <circle cx="15" cy="18" r="1.5" />
                    </svg>
                  </span>
                  <input
                    type="checkbox"
                    checked={columnVisibility[key]}
                    onChange={() => toggleColumnVisibility(key)}
                    className="checkbox checkbox-sm"
                  />
                  <span className="text-sm flex-1">{COLUMN_CONFIG[key].header}</span>
                  <span className={`badge badge-xs ${COLUMN_CONFIG[key].group === 'info' ? 'badge-ghost' : 'badge-primary badge-outline'}`}>
                    {COLUMN_CONFIG[key].group === 'info' ? 'Info' : 'AI'}
                  </span>
                </label>
              </li>
            ))}
          </ul>

          {/* Reset Button */}
          <div className="pt-3 border-t border-base-300 mt-3">
            <button className="btn btn-ghost btn-sm w-full" onClick={resetColumnSettings}>
              Reset to Default
            </button>
          </div>
        </div>
      </div>
      </div>{/* End inner overflow-hidden container */}

      {filteredTransactions.length === 0 && filters.selectedCategory !== 'All' && (
        <div className="alert alert-info">
          <span>No transactions in category: {filters.selectedCategory}</span>
        </div>
      )}

      {/* Summary */}
      <div className="text-sm text-base-content/60">
        Showing {filteredTransactions.length} of {transactions.length} transactions
      </div>

      {/* Category Update Modal */}
      {editingTransaction && (
        <CategoryUpdateModal
          transactionId={editingTransaction.id}
          currentCategory={editingTransaction.category}
          merchant={editingTransaction.merchant}
          onClose={() => setEditingTransaction(null)}
          onSuccess={handleModalSuccess}
        />
      )}

      {/* Enrichment Source Detail Modal */}
      <EnrichmentSourceDetailModal
        isOpen={viewingEnrichmentSource !== null}
        sourceId={viewingEnrichmentSource?.sourceId ?? null}
        transactionId={viewingEnrichmentSource?.transactionId ?? 0}
        onClose={() => setViewingEnrichmentSource(null)}
        onSetPrimary={() => {
          // Refresh transactions to show updated primary source
          refreshTransactions();
        }}
      />
    </div>
  );
}
