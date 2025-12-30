/**
 * MatchesTab Component
 *
 * Displays bank transactions with match status badges for each data source.
 * Shows a detail panel for the selected match with full source information.
 * Persists selection to localStorage.
 */

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../../api/client';

// ============================================================================
// Types
// ============================================================================

interface EnrichmentSource {
  id: number;
  source_type: string;
  source_id: number;
  match_confidence: number;
  is_primary: boolean;
}

interface TransactionWithMatches {
  id: number;
  timestamp: string | null;
  description: string;
  amount: number;
  currency: string;
  enrichment_sources: EnrichmentSource[];
}

interface PaginatedResponse {
  items: TransactionWithMatches[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface SelectedMatch {
  transactionId: number;
  enrichmentSourceId: number;
  sourceType: string;
  sourceId: number;
}

interface MatchDetails {
  id: number;
  truelayer_transaction_id: number;
  source_type: string;
  source_id: number;
  description: string | null;
  order_id: string | null;
  line_items: unknown[] | null;
  match_confidence: number;
  match_method: string | null;
  is_primary: boolean;
  user_verified: boolean;
  created_at: string;
  source_details: {
    // Common
    id?: number;
    order_id?: string;
    order_date?: string;
    created_at?: string;
    source_file?: string;
    currency?: string;

    // Amazon
    website?: string;
    total_owed?: number;
    product_names?: string;
    order_status?: string;
    shipment_status?: string;
    parsed_line_items?: { name: string; quantity: number }[];

    // Amazon Business
    region?: string;
    purchase_order_number?: string;
    buyer_name?: string;
    buyer_email?: string;
    subtotal?: number;
    tax?: number;
    shipping?: number;
    net_total?: number;
    item_count?: number;
    product_summary?: string;
    line_items?: {
      line_item_id?: string;
      asin?: string;
      title?: string;
      brand?: string;
      category?: string;
      quantity?: number;
      unit_price?: number;
      total_price?: number;
      seller_name?: string;
    }[];

    // Apple
    total_amount?: number;
    app_names?: string;
    publishers?: string;

    // Gmail
    connection_id?: number;
    message_id?: string;
    thread_id?: string;
    sender_email?: string;
    sender_name?: string;
    subject?: string;
    received_at?: string;
    merchant_name?: string;
    merchant_domain?: string;
    currency_code?: string;
    receipt_date?: string;
    parse_method?: string;
    parse_confidence?: number;
    parsing_status?: string;
    pdf_attachments?: {
      id: number;
      filename: string;
      size_bytes: number;
      mime_type: string;
      object_key: string;
    }[];
  } | null;
}

// ============================================================================
// Constants
// ============================================================================

const STORAGE_KEY = 'data-sources-selected-match';
const PAGE_SIZE = 50;

// Source type labels for display
const SOURCE_LABELS: Record<string, string> = {
  amazon: 'Amazon',
  amazon_business: 'Business',
  apple: 'Apple',
  gmail: 'Gmail',
  returns: 'Returns',
  manual: 'Manual',
};

// All source types we display columns for
const SOURCE_COLUMNS = ['amazon', 'amazon_business', 'apple', 'gmail'] as const;

// ============================================================================
// Helper Functions
// ============================================================================

function formatDate(dateString: string | null): string {
  if (!dateString) return '—';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

function formatAmount(amount: number, currency: string): string {
  const symbol = currency === 'GBP' ? '£' : currency === 'USD' ? '$' : currency;
  return `${symbol}${Math.abs(amount).toFixed(2)}`;
}

function getSourceForType(
  sources: EnrichmentSource[],
  sourceType: string
): EnrichmentSource | undefined {
  return sources.find((s) => s.source_type === sourceType);
}

// ============================================================================
// Component
// ============================================================================

export default function MatchesTab() {
  // Data state
  const [data, setData] = useState<PaginatedResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);

  // Selection state
  const [selectedMatch, setSelectedMatch] = useState<SelectedMatch | null>(null);
  const [matchDetails, setMatchDetails] = useState<MatchDetails | null>(null);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);

  // Load saved selection from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as SelectedMatch;
        setSelectedMatch(parsed);
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      }
    }
  }, []);

  // Save selection to localStorage when it changes
  useEffect(() => {
    if (selectedMatch) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedMatch));
    }
  }, [selectedMatch]);

  // Fetch transactions with matches
  const fetchData = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiClient.get<PaginatedResponse>(
        '/transactions/with-matches',
        { params: { page, page_size: PAGE_SIZE } }
      );
      setData(response.data);
    } catch (error) {
      console.error('Failed to fetch transactions with matches:', error);
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Fetch match details when selection changes
  useEffect(() => {
    if (!selectedMatch) {
      setMatchDetails(null);
      return;
    }

    const fetchDetails = async () => {
      setIsLoadingDetails(true);
      try {
        const response = await apiClient.get<MatchDetails>(
          `/enrichment-sources/${selectedMatch.enrichmentSourceId}/details`
        );
        setMatchDetails(response.data);
      } catch (error) {
        console.error('Failed to fetch match details:', error);
        setMatchDetails(null);
      } finally {
        setIsLoadingDetails(false);
      }
    };

    fetchDetails();
  }, [selectedMatch]);

  // Handle badge click
  const handleBadgeClick = (
    transaction: TransactionWithMatches,
    source: EnrichmentSource
  ) => {
    setSelectedMatch({
      transactionId: transaction.id,
      enrichmentSourceId: source.id,
      sourceType: source.source_type,
      sourceId: source.source_id,
    });
  };

  // Helper to render a detail field
  const DetailField = ({
    label,
    value,
    mono = false,
    wide = false,
  }: {
    label: string;
    value: React.ReactNode;
    mono?: boolean;
    wide?: boolean;
  }) => (
    <div className={wide ? 'col-span-2' : ''}>
      <div className="text-xs text-base-content/60 uppercase tracking-wide">{label}</div>
      <div className={`${mono ? 'font-mono text-xs' : ''} break-words`}>{value}</div>
    </div>
  );

  // Render Amazon-specific details
  const renderAmazonDetails = (details: NonNullable<MatchDetails['source_details']>) => (
    <>
      {details.order_id && <DetailField label="Order ID" value={details.order_id} mono />}
      {details.order_date && <DetailField label="Order Date" value={formatDate(details.order_date)} />}
      {details.total_owed !== undefined && (
        <DetailField label="Total" value={`£${Number(details.total_owed).toFixed(2)}`} />
      )}
      {details.currency && <DetailField label="Currency" value={details.currency} />}
      {details.website && <DetailField label="Website" value={details.website} />}
      {details.order_status && <DetailField label="Order Status" value={details.order_status} />}
      {details.shipment_status && <DetailField label="Shipment" value={details.shipment_status} />}
      {details.product_names && (
        <DetailField label="Products" value={details.product_names} wide />
      )}
      {details.source_file && <DetailField label="Source File" value={details.source_file} wide />}
    </>
  );

  // Render Amazon Business-specific details
  const renderAmazonBusinessDetails = (details: NonNullable<MatchDetails['source_details']>) => (
    <>
      {details.order_id && <DetailField label="Order ID" value={details.order_id} mono />}
      {details.order_date && <DetailField label="Order Date" value={formatDate(details.order_date)} />}
      {details.net_total !== undefined && (
        <DetailField label="Net Total" value={`£${Number(details.net_total).toFixed(2)}`} />
      )}
      {details.subtotal !== undefined && (
        <DetailField label="Subtotal" value={`£${Number(details.subtotal).toFixed(2)}`} />
      )}
      {details.tax !== undefined && (
        <DetailField label="Tax" value={`£${Number(details.tax).toFixed(2)}`} />
      )}
      {details.shipping !== undefined && (
        <DetailField label="Shipping" value={`£${Number(details.shipping).toFixed(2)}`} />
      )}
      {details.currency && <DetailField label="Currency" value={details.currency} />}
      {details.region && <DetailField label="Region" value={details.region} />}
      {details.order_status && <DetailField label="Status" value={details.order_status} />}
      {details.purchase_order_number && (
        <DetailField label="PO Number" value={details.purchase_order_number} mono />
      )}
      {details.buyer_name && <DetailField label="Buyer" value={details.buyer_name} />}
      {details.buyer_email && <DetailField label="Buyer Email" value={details.buyer_email} />}
      {details.item_count !== undefined && (
        <DetailField label="Items" value={details.item_count} />
      )}
      {details.product_summary && (
        <DetailField label="Product Summary" value={details.product_summary} wide />
      )}
      {/* Line items for business orders */}
      {details.line_items && details.line_items.length > 0 && (
        <div className="col-span-full mt-2">
          <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">
            Line Items ({details.line_items.length})
          </div>
          <div className="bg-base-300 rounded-lg overflow-x-auto">
            <table className="table table-xs">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Brand</th>
                  <th>Category</th>
                  <th className="text-right">Qty</th>
                  <th className="text-right">Unit</th>
                  <th className="text-right">Total</th>
                </tr>
              </thead>
              <tbody>
                {details.line_items.map((item, i) => (
                  <tr key={i}>
                    <td className="max-w-[200px] truncate" title={item.title}>
                      {item.title || '—'}
                    </td>
                    <td>{item.brand || '—'}</td>
                    <td>{item.category || '—'}</td>
                    <td className="text-right">{item.quantity ?? '—'}</td>
                    <td className="text-right font-mono">
                      {item.unit_price !== undefined ? `£${Number(item.unit_price).toFixed(2)}` : '—'}
                    </td>
                    <td className="text-right font-mono">
                      {item.total_price !== undefined ? `£${Number(item.total_price).toFixed(2)}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );

  // Render Apple-specific details
  const renderAppleDetails = (details: NonNullable<MatchDetails['source_details']>) => (
    <>
      {details.order_id && <DetailField label="Order ID" value={details.order_id} mono />}
      {details.order_date && <DetailField label="Order Date" value={formatDate(details.order_date)} />}
      {details.total_amount !== undefined && (
        <DetailField label="Total" value={`£${Number(details.total_amount).toFixed(2)}`} />
      )}
      {details.currency && <DetailField label="Currency" value={details.currency} />}
      {details.item_count !== undefined && <DetailField label="Items" value={details.item_count} />}
      {details.app_names && <DetailField label="Apps" value={details.app_names} wide />}
      {details.publishers && <DetailField label="Publishers" value={details.publishers} wide />}
      {details.source_file && <DetailField label="Source File" value={details.source_file} wide />}
    </>
  );

  // Render Gmail-specific details
  const renderGmailDetails = (details: NonNullable<MatchDetails['source_details']>) => (
    <>
      {details.merchant_name && <DetailField label="Merchant" value={details.merchant_name} />}
      {details.merchant_domain && <DetailField label="Domain" value={details.merchant_domain} />}
      {details.order_id && <DetailField label="Order ID" value={details.order_id} mono />}
      {details.total_amount !== undefined && (
        <DetailField
          label="Total"
          value={`${details.currency_code === 'GBP' ? '£' : details.currency_code || ''}${Number(details.total_amount).toFixed(2)}`}
        />
      )}
      {details.receipt_date && <DetailField label="Receipt Date" value={formatDate(details.receipt_date)} />}
      {details.received_at && <DetailField label="Email Received" value={formatDate(details.received_at)} />}
      {details.sender_name && <DetailField label="Sender" value={details.sender_name} />}
      {details.sender_email && <DetailField label="Sender Email" value={details.sender_email} />}
      {details.subject && <DetailField label="Subject" value={details.subject} wide />}
      {details.message_id && <DetailField label="Message ID" value={details.message_id} mono wide />}
      {details.thread_id && <DetailField label="Thread ID" value={details.thread_id} mono />}
      {details.parse_method && <DetailField label="Parse Method" value={details.parse_method} />}
      {details.parse_confidence !== undefined && (
        <DetailField label="Parse Confidence" value={`${details.parse_confidence}%`} />
      )}
      {details.parsing_status && <DetailField label="Parse Status" value={details.parsing_status} />}
      {/* Gmail line items */}
      {details.line_items && Array.isArray(details.line_items) && details.line_items.length > 0 && (
        <div className="col-span-full mt-2">
          <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">
            Line Items ({details.line_items.length})
          </div>
          <div className="bg-base-300 rounded-lg p-2 text-xs">
            <pre className="whitespace-pre-wrap">{JSON.stringify(details.line_items, null, 2)}</pre>
          </div>
        </div>
      )}
      {/* PDF Attachments */}
      {details.pdf_attachments && details.pdf_attachments.length > 0 && (
        <div className="col-span-full mt-2">
          <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">
            PDF Attachments ({details.pdf_attachments.length})
          </div>
          <div className="flex flex-wrap gap-2">
            {details.pdf_attachments.map((pdf) => (
              <div key={pdf.id} className="badge badge-outline gap-1">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clipRule="evenodd" />
                </svg>
                {pdf.filename}
                <span className="opacity-60">
                  ({(pdf.size_bytes / 1024).toFixed(0)}KB)
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );

  // Render detail panel content
  const renderDetailContent = () => {
    if (!selectedMatch) {
      return (
        <div className="text-center py-6 text-base-content/60">
          <svg
            className="w-12 h-12 mx-auto mb-2 opacity-50"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p>Select a match badge to see details</p>
        </div>
      );
    }

    if (isLoadingDetails) {
      return (
        <div className="flex items-center justify-center py-6">
          <span className="loading loading-dots loading-md"></span>
        </div>
      );
    }

    if (!matchDetails) {
      return (
        <div className="text-center py-6 text-error">
          Failed to load match details
        </div>
      );
    }

    const sourceLabel = SOURCE_LABELS[matchDetails.source_type] || matchDetails.source_type;
    const details = matchDetails.source_details;

    return (
      <div className="space-y-4">
        {/* Header row with badges */}
        <div className="flex flex-wrap items-center gap-2">
          <span className="badge badge-primary badge-lg">{sourceLabel}</span>
          <span className="badge badge-outline">
            {matchDetails.match_confidence}% confidence
          </span>
          {matchDetails.match_method && (
            <span className="badge badge-ghost badge-sm">
              {matchDetails.match_method}
            </span>
          )}
          {matchDetails.is_primary && (
            <span className="badge badge-success badge-sm">Primary</span>
          )}
          {matchDetails.user_verified && (
            <span className="badge badge-info badge-sm">Verified</span>
          )}
        </div>

        {/* Enrichment source metadata */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm pb-3 border-b border-base-300">
          <DetailField label="Source ID" value={matchDetails.source_id} mono />
          <DetailField label="Enrichment ID" value={matchDetails.id} mono />
          {matchDetails.order_id && (
            <DetailField label="Order ID (Enrichment)" value={matchDetails.order_id} mono />
          )}
          {matchDetails.description && (
            <DetailField label="Description" value={matchDetails.description} wide />
          )}
          <DetailField label="Created" value={formatDate(matchDetails.created_at)} />
        </div>

        {/* Source-specific details */}
        {details && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            {matchDetails.source_type === 'amazon' && renderAmazonDetails(details)}
            {matchDetails.source_type === 'amazon_business' && renderAmazonBusinessDetails(details)}
            {matchDetails.source_type === 'apple' && renderAppleDetails(details)}
            {matchDetails.source_type === 'gmail' && renderGmailDetails(details)}
          </div>
        )}

        {!details && (
          <div className="text-center py-4 text-base-content/60">
            No source details available (may be a manual entry)
          </div>
        )}
      </div>
    );
  };

  // Render badge for a source type
  const renderBadge = (
    transaction: TransactionWithMatches,
    sourceType: string
  ) => {
    const source = getSourceForType(transaction.enrichment_sources, sourceType);
    const isSelected =
      selectedMatch?.transactionId === transaction.id &&
      selectedMatch?.sourceType === sourceType;

    if (source) {
      return (
        <button
          className={`badge badge-sm cursor-pointer transition-all ${
            isSelected
              ? 'badge-primary ring-2 ring-primary ring-offset-1'
              : 'badge-success hover:badge-primary'
          }`}
          onClick={() => handleBadgeClick(transaction, source)}
          title={`${SOURCE_LABELS[sourceType]} match (${source.match_confidence}% confidence)`}
        >
          ✓
        </button>
      );
    }

    return (
      <span className="badge badge-ghost badge-sm opacity-40" title="No match">
        —
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">Bank Transaction Matches</h2>
        {data && (
          <span className="text-sm text-base-content/60">
            {data.total.toLocaleString()} transactions
          </span>
        )}
      </div>

      {/* Detail Panel */}
      <div className="bg-base-200 rounded-lg p-4">
        <div className="text-xs text-base-content/60 uppercase tracking-wide mb-2">
          Match Details
        </div>
        {renderDetailContent()}
      </div>

      {/* Transactions Table */}
      <div className="overflow-x-auto">
        <table className="table table-zebra">
          <thead>
            <tr>
              <th>Date</th>
              <th>Description</th>
              <th className="text-right">Amount</th>
              <th className="text-center">Amazon</th>
              <th className="text-center">Business</th>
              <th className="text-center">Apple</th>
              <th className="text-center">Gmail</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td><div className="h-4 bg-base-300 rounded w-20" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-48" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-16 ml-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-6 mx-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-6 mx-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-6 mx-auto" /></td>
                  <td><div className="h-4 bg-base-300 rounded w-6 mx-auto" /></td>
                </tr>
              ))
            ) : !data || data.items.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 opacity-50">
                  No bank transactions found. Connect a bank account to get started.
                </td>
              </tr>
            ) : (
              data.items.map((txn) => {
                const isSelectedRow = selectedMatch?.transactionId === txn.id;
                return (
                  <tr
                    key={txn.id}
                    className={isSelectedRow ? 'bg-primary/10' : ''}
                  >
                    <td className="whitespace-nowrap">{formatDate(txn.timestamp)}</td>
                    <td className="max-w-xs truncate" title={txn.description}>
                      {txn.description}
                    </td>
                    <td className="text-right font-mono">
                      {formatAmount(txn.amount, txn.currency)}
                    </td>
                    {SOURCE_COLUMNS.map((sourceType) => (
                      <td key={sourceType} className="text-center">
                        {renderBadge(txn, sourceType)}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex justify-center gap-2">
          <button
            className="btn btn-sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
          >
            Previous
          </button>
          <span className="flex items-center px-4">
            Page {page} of {data.total_pages}
          </span>
          <button
            className="btn btn-sm"
            onClick={() => setPage((p) => Math.min(data.total_pages, p + 1))}
            disabled={page === data.total_pages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
