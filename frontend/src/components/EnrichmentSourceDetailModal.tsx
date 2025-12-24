import { useEffect, useState } from 'react';
import axios from 'axios';
import PDFAttachmentViewer from './PDFAttachmentViewer';

// Source type configuration for display
const SOURCE_TYPE_CONFIG: Record<string, { label: string; color: string; icon: string }> = {
  amazon: { label: 'Amazon', color: 'badge-warning', icon: '📦' },
  amazon_business: { label: 'Amazon Business', color: 'badge-warning', icon: '🏢' },
  apple: { label: 'Apple', color: 'badge-info', icon: '🍎' },
  gmail: { label: 'Email Receipt', color: 'badge-secondary', icon: '📧' },
  manual: { label: 'Manual Entry', color: 'badge-success', icon: '✏️' },
};

// Line item interface for display
interface LineItem {
  name: string;
  quantity?: number;
  price?: number;
  unit_price?: number;
  total_price?: number;
  brand?: string;
  category?: string;
  asin?: string;
}

// Full enrichment source details from API
interface EnrichmentSourceDetails {
  id: number;
  truelayer_transaction_id: number;
  source_type: string;
  source_id: number | null;
  description: string;
  order_id: string | null;
  line_items: LineItem[] | null;
  match_confidence: number;
  match_method: string | null;
  is_primary: boolean;
  user_verified: boolean;
  created_at: string;
  source_details: {
    // Common fields
    id?: number;
    order_id?: string;
    created_at?: string;
    // Amazon fields
    order_date?: string;
    website?: string;
    currency?: string;
    total_owed?: number;
    product_names?: string;
    order_status?: string;
    shipment_status?: string;
    parsed_line_items?: LineItem[];
    // Amazon Business fields
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
    line_items?: LineItem[];
    // Apple fields
    total_amount?: number;
    app_names?: string;
    publishers?: string;
    // Gmail fields
    sender_email?: string;
    sender_name?: string;
    subject?: string;
    received_at?: string;
    merchant_name?: string;
    merchant_domain?: string;
    total_amount_gmail?: number;
    total_amount?: number;
    currency_code?: string;
    receipt_date?: string;
    parse_method?: string;
    parse_confidence?: number;
    parsing_status?: string;
    // PDF attachments
    pdf_attachments?: Array<{
      id: number;
      filename: string;
      size_bytes: number;
      mime_type: string;
      object_key: string;
      created_at: string;
    }>;
  } | null;
}

interface Props {
  isOpen: boolean;
  sourceId: number | null;
  transactionId: number;
  onClose: () => void;
  onSetPrimary?: (sourceId: number) => void;
}

export default function EnrichmentSourceDetailModal({
  isOpen,
  sourceId,
  transactionId,
  onClose,
  onSetPrimary,
}: Props) {
  const [details, setDetails] = useState<EnrichmentSourceDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingPrimary, setSettingPrimary] = useState(false);

  useEffect(() => {
    if (!isOpen || !sourceId) {
      setDetails(null);
      setError(null);
      return;
    }

    const fetchDetails = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axios.get(`/api/enrichment-sources/${sourceId}/details`);
        setDetails(response.data);
      } catch (err) {
        setError('Failed to load source details');
        console.error('Failed to fetch enrichment source details:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchDetails();
  }, [isOpen, sourceId]);

  const handleSetPrimary = async () => {
    if (!sourceId || !details) return;

    setSettingPrimary(true);
    try {
      await axios.post(`/api/transactions/${transactionId}/enrichment-sources/primary`, {
        source_type: details.source_type,
        source_id: details.source_id,
      });
      // Update local state
      setDetails({ ...details, is_primary: true });
      onSetPrimary?.(sourceId);
    } catch (err) {
      console.error('Failed to set primary source:', err);
      setError('Failed to set as primary source');
    } finally {
      setSettingPrimary(false);
    }
  };

  if (!isOpen) return null;

  const config = SOURCE_TYPE_CONFIG[details?.source_type || ''] || {
    label: details?.source_type || 'Unknown',
    color: 'badge-ghost',
    icon: '📋',
  };

  // Get line items from source details or enrichment source
  const getLineItems = (): LineItem[] => {
    if (!details) return [];

    // Check enrichment source line_items first
    if (details.line_items && details.line_items.length > 0) {
      return details.line_items;
    }

    // Fall back to source_details parsed items
    if (details.source_details) {
      if (details.source_details.line_items) {
        return details.source_details.line_items;
      }
      if (details.source_details.parsed_line_items) {
        return details.source_details.parsed_line_items;
      }
    }

    return [];
  };

  // Format currency
  const formatAmount = (amount: number | undefined, currency: string = 'GBP'): string => {
    if (amount === undefined || amount === null) return '-';
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: currency,
    }).format(amount);
  };

  // Format date
  const formatDate = (dateStr: string | undefined): string => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
    });
  };

  const lineItems = getLineItems();
  const sd = details?.source_details;

  return (
    <div className="modal modal-open">
      <div className="modal-box w-11/12 max-w-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{config.icon}</span>
            <div>
              <h3 className="font-bold text-lg">{config.label} Source Details</h3>
              {details?.order_id && (
                <p className="text-sm text-base-content/60">Order: {details.order_id}</p>
              )}
            </div>
          </div>
          <span className={`badge ${config.color}`}>
            {details?.match_confidence || 0}% match
          </span>
        </div>

        {/* Loading State */}
        {loading && (
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner loading-lg text-primary"></span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="alert alert-error mb-4">
            <span>{error}</span>
          </div>
        )}

        {/* Content */}
        {details && !loading && (
          <div className="space-y-4">
            {/* Primary Source Badge */}
            {details.is_primary && (
              <div className="badge badge-success gap-1">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Primary Source
              </div>
            )}

            {/* Description */}
            <div className="bg-base-200 rounded-lg p-4">
              <h4 className="font-semibold text-sm text-base-content/60 mb-1">Description</h4>
              <p className="text-base-content">{details.description}</p>
            </div>

            {/* Source Metadata */}
            <div className="grid grid-cols-2 gap-4 text-sm">
              {/* Amazon specific */}
              {(details.source_type === 'amazon' || details.source_type === 'amazon_business') && sd && (
                <>
                  <div>
                    <span className="text-base-content/60">Order Date:</span>
                    <span className="ml-2 font-medium">{formatDate(sd.order_date)}</span>
                  </div>
                  <div>
                    <span className="text-base-content/60">Total:</span>
                    <span className="ml-2 font-medium">
                      {formatAmount(sd.total_owed || sd.net_total, sd.currency || 'GBP')}
                    </span>
                  </div>
                  {sd.order_status && (
                    <div>
                      <span className="text-base-content/60">Status:</span>
                      <span className="ml-2 font-medium">{sd.order_status}</span>
                    </div>
                  )}
                  {sd.website && (
                    <div>
                      <span className="text-base-content/60">Website:</span>
                      <span className="ml-2 font-medium">{sd.website}</span>
                    </div>
                  )}
                </>
              )}

              {/* Apple specific */}
              {details.source_type === 'apple' && sd && (
                <>
                  <div>
                    <span className="text-base-content/60">Purchase Date:</span>
                    <span className="ml-2 font-medium">{formatDate(sd.order_date)}</span>
                  </div>
                  <div>
                    <span className="text-base-content/60">Total:</span>
                    <span className="ml-2 font-medium">
                      {formatAmount(sd.total_amount, sd.currency || 'GBP')}
                    </span>
                  </div>
                  {sd.publishers && (
                    <div className="col-span-2">
                      <span className="text-base-content/60">Publishers:</span>
                      <span className="ml-2 font-medium">{sd.publishers}</span>
                    </div>
                  )}
                </>
              )}

              {/* Gmail specific */}
              {details.source_type === 'gmail' && sd && (
                <>
                  <div>
                    <span className="text-base-content/60">Receipt Date:</span>
                    <span className="ml-2 font-medium">{formatDate(sd.receipt_date || sd.received_at)}</span>
                  </div>
                  <div>
                    <span className="text-base-content/60">Amount:</span>
                    <span className="ml-2 font-medium">
                      {formatAmount(sd.total_amount, sd.currency_code || 'GBP')}
                    </span>
                  </div>
                  {sd.merchant_name && (
                    <div>
                      <span className="text-base-content/60">Merchant:</span>
                      <span className="ml-2 font-medium">{sd.merchant_name}</span>
                    </div>
                  )}
                  {sd.sender_email && (
                    <div>
                      <span className="text-base-content/60">From:</span>
                      <span className="ml-2 font-medium">{sd.sender_name || sd.sender_email}</span>
                    </div>
                  )}
                  {sd.subject && (
                    <div className="col-span-2">
                      <span className="text-base-content/60">Subject:</span>
                      <span className="ml-2 font-medium text-sm">{sd.subject}</span>
                    </div>
                  )}
                  {/* PDF Attachments */}
                  {sd.pdf_attachments && sd.pdf_attachments.length > 0 && (
                    <div className="col-span-2">
                      <PDFAttachmentViewer attachments={sd.pdf_attachments} />
                    </div>
                  )}
                </>
              )}

              {/* Match method */}
              {details.match_method && (
                <div>
                  <span className="text-base-content/60">Match Method:</span>
                  <span className="ml-2 font-medium">{details.match_method.replace(/_/g, ' ')}</span>
                </div>
              )}
            </div>

            {/* Line Items Table */}
            {lineItems.length > 0 && (
              <div>
                <h4 className="font-semibold text-sm text-base-content/60 mb-2">Items</h4>
                <div className="overflow-x-auto">
                  <table className="table table-sm table-zebra w-full">
                    <thead>
                      <tr>
                        <th>Item</th>
                        <th className="text-center">Qty</th>
                        <th className="text-right">Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {lineItems.map((item, idx) => (
                        <tr key={idx}>
                          <td className="max-w-[300px]">
                            <div className="truncate" title={item.name}>
                              {item.name}
                            </div>
                            {item.brand && (
                              <div className="text-xs text-base-content/50">{item.brand}</div>
                            )}
                          </td>
                          <td className="text-center">{item.quantity || 1}</td>
                          <td className="text-right">
                            {item.price !== undefined
                              ? formatAmount(item.price)
                              : item.unit_price !== undefined
                              ? formatAmount(item.unit_price)
                              : item.total_price !== undefined
                              ? formatAmount(item.total_price)
                              : '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Verification Status */}
            {details.user_verified && (
              <div className="flex items-center gap-2 text-sm text-success">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                User verified
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="modal-action gap-2 mt-6">
          {details && !details.is_primary && !loading && (
            <button
              className="btn btn-outline"
              onClick={handleSetPrimary}
              disabled={settingPrimary}
            >
              {settingPrimary ? (
                <span className="loading loading-spinner loading-sm"></span>
              ) : (
                'Set as Primary'
              )}
            </button>
          )}
          <button className="btn btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
      <div className="modal-backdrop" onClick={onClose} />
    </div>
  );
}
