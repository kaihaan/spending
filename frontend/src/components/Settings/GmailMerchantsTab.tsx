import React, { useState, useEffect, useCallback } from 'react';
import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

// Types
interface GmailMerchant {
  merchant_normalized: string;  // Primary key for grouping (e.g., 'amazon', 'amazon_business')
  merchant_domain: string;
  merchant_name: string;
  receipt_count: number;
  parsed_count: number;
  matched_count: number;
  pending_count: number;
  failed_count: number;
  has_template: boolean;
  template_type: 'schema_org' | 'vendor' | 'pattern' | 'llm' | 'none';
  has_vendor_parser: boolean;
  potential_transaction_matches: number;
  amazon_coverage: number;
  amazon_business_coverage: number;
  amazon_fresh_coverage: number;
  apple_coverage: number;
  earliest_receipt: string | null;
  latest_receipt: string | null;
  llm_cost_cents: number;
  schema_parsed_count: number;
  pattern_parsed_count: number;
  llm_parsed_count: number;
  total_amount: number;
}

interface MerchantsSummary {
  total_merchants: number;
  with_template: number;
  without_template: number;
  with_vendor_parser: number;
  total_receipts: number;
  total_parsed: number;
  total_matched: number;
  total_pending: number;
  total_failed: number;
  total_llm_cost_cents: number;
  total_potential_matches: number;
  total_amount: number;
}

interface LineItem {
  name: string;
  price?: number;
  quantity?: number;
}

interface GmailReceipt {
  id: number;
  message_id: string;
  sender_email: string;
  sender_name: string | null;
  subject: string;
  received_at: string;
  merchant_name: string | null;
  merchant_domain: string | null;
  order_id: string | null;
  total_amount: number | null;
  currency_code: string;
  receipt_date: string | null;
  line_items: LineItem[] | null;
  parse_method: string | null;
  parse_confidence: number;
  parsing_status: string;
  parsing_error: string | null;
  llm_cost_cents: number | null;
  match_id: number | null;
  match_confidence: number | null;
  transaction_id: number | null;
  transaction_description: string | null;
  transaction_amount: number | null;
}

interface EnrichmentResult {
  success: boolean;
  processed: number;
  parsed: number;
  failed: number;
  llm_cost_cents: number;
  domain: string;
  message?: string;
}

export default function GmailMerchantsTab() {
  const [merchants, setMerchants] = useState<GmailMerchant[]>([]);
  const [summary, setSummary] = useState<MerchantsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Expanded row state - uses merchant_normalized as key
  const [expandedMerchant, setExpandedMerchant] = useState<string | null>(null);
  const [expandedReceipts, setExpandedReceipts] = useState<GmailReceipt[]>([]);
  const [loadingReceipts, setLoadingReceipts] = useState(false);

  // LLM enrichment state - uses merchant_normalized as key
  const [enrichingMerchant, setEnrichingMerchant] = useState<string | null>(null);
  const [enrichmentResult, setEnrichmentResult] = useState<EnrichmentResult | null>(null);

  // Fetch merchants data
  const fetchMerchants = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await axios.get(`${API_URL}/gmail/merchants`);

      setMerchants(response.data.merchants || []);
      setSummary(response.data.summary || null);
    } catch (err) {
      console.error('Failed to fetch Gmail merchants:', err);
      setError('Failed to load Gmail merchants. Make sure Gmail is connected.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMerchants();
  }, [fetchMerchants]);

  // Fetch receipts for expanded merchant (uses normalized name as identifier)
  const fetchReceipts = async (normalizedName: string) => {
    try {
      setLoadingReceipts(true);
      // API auto-detects: if contains '.', treats as domain; otherwise as normalized name
      const response = await axios.get(`${API_URL}/gmail/merchants/${encodeURIComponent(normalizedName)}/receipts`, {
        params: { limit: 20 }
      });
      setExpandedReceipts(response.data.receipts || []);
    } catch (err) {
      console.error('Failed to fetch receipts:', err);
      setExpandedReceipts([]);
    } finally {
      setLoadingReceipts(false);
    }
  };

  // Toggle row expansion (uses normalized name as key)
  const toggleExpand = (normalizedName: string) => {
    if (expandedMerchant === normalizedName) {
      setExpandedMerchant(null);
      setExpandedReceipts([]);
    } else {
      setExpandedMerchant(normalizedName);
      fetchReceipts(normalizedName);
    }
  };

  // Run LLM enrichment for a merchant (uses domain for enrich endpoint)
  const runLLMEnrichment = async (normalizedName: string, domain: string) => {
    try {
      setEnrichingMerchant(normalizedName);
      setEnrichmentResult(null);

      // Enrich endpoint still uses domain for now
      const response = await axios.post(`${API_URL}/gmail/merchants/${encodeURIComponent(domain)}/enrich`, {
        force: false
      });

      setEnrichmentResult(response.data);

      // Refresh data after enrichment
      await fetchMerchants();

      // Refresh expanded receipts if this merchant is expanded
      if (expandedMerchant === normalizedName) {
        await fetchReceipts(normalizedName);
      }
    } catch (err) {
      console.error('LLM enrichment failed:', err);
      setEnrichmentResult({
        success: false,
        processed: 0,
        parsed: 0,
        failed: 0,
        llm_cost_cents: 0,
        domain,
        message: 'Enrichment failed'
      });
    } finally {
      setEnrichingMerchant(null);
    }
  };

  // Format date for display
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-GB', {
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    });
  };

  // Format currency
  const formatCurrency = (amount: number | null, currency = 'GBP') => {
    if (amount === null) return '-';
    return new Intl.NumberFormat('en-GB', {
      style: 'currency',
      currency: currency
    }).format(Math.abs(amount));
  };

  // Format line items for display
  const formatLineItems = (items: LineItem[] | null): string => {
    if (!items || items.length === 0) return '-';
    // Show first 2 items, with count if more
    const displayItems = items.slice(0, 2).map(item => {
      const name = item.name?.substring(0, 40) || 'Unknown item';
      return name.length < (item.name?.length || 0) ? name + '...' : name;
    });
    const suffix = items.length > 2 ? ` (+${items.length - 2} more)` : '';
    return displayItems.join(', ') + suffix;
  };

  // Extract brand information from line items
  const extractBrand = (items: LineItem[] | null): string => {
    if (!items || items.length === 0) return '-';

    // Check first item for brand metadata
    const firstItem = items[0] as any;

    // Deliveroo/Uber Eats have restaurant field
    if (firstItem.restaurant) {
      return firstItem.restaurant;
    }

    // PayPal has merchant field
    if (firstItem.merchant) {
      return firstItem.merchant;
    }

    // Black Sheep Coffee has location field
    if (firstItem.location) {
      return firstItem.location;
    }

    // Airbnb has property_name field
    if (firstItem.property_name) {
      return firstItem.property_name;
    }

    // eBay/Etsy/Vinted have seller field
    if (firstItem.seller) {
      return firstItem.seller;
    }

    // Apple has developer field (if we add it)
    if (firstItem.developer) {
      return firstItem.developer;
    }

    // Amazon has brand/manufacturer (if we add it)
    if (firstItem.brand) {
      return firstItem.brand;
    }
    if (firstItem.manufacturer) {
      return firstItem.manufacturer;
    }

    return '-';
  };

  // Get template badge
  const getTemplateBadge = (merchant: GmailMerchant) => {
    if (merchant.has_vendor_parser) {
      return <span className="badge badge-success badge-sm">Vendor</span>;
    }
    if (merchant.has_template) {
      const typeMap: Record<string, string> = {
        'schema_org': 'Schema.org',
        'pattern': 'Pattern',
        'llm': 'LLM'
      };
      return <span className="badge badge-info badge-sm">{typeMap[merchant.template_type] || merchant.template_type}</span>;
    }
    return <span className="badge badge-ghost badge-sm">None</span>;
  };

  // Get parsing status badge
  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { color: string; label: string }> = {
      'parsed': { color: 'badge-success', label: 'Parsed' },
      'pending': { color: 'badge-warning', label: 'Pending' },
      'failed': { color: 'badge-error', label: 'Failed' },
      'unparseable': { color: 'badge-ghost', label: 'Unparseable' }
    };
    const info = statusMap[status] || { color: 'badge-ghost', label: status };
    return <span className={`badge badge-sm ${info.color}`}>{info.label}</span>;
  };

  // Check if LLM enrichment should be available
  const canRunLLM = (merchant: GmailMerchant) => {
    // Show LLM option if: no template AND has pending receipts AND has potential matches
    return !merchant.has_template &&
           !merchant.has_vendor_parser &&
           merchant.pending_count > 0 &&
           merchant.potential_transaction_matches > 0;
  };

  // Loading state
  if (loading) {
    return (
      <div className="flex justify-center items-center py-12">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="alert alert-info">
        <span>{error}</span>
        <button className="btn btn-sm btn-ghost" onClick={fetchMerchants}>
          Retry
        </button>
      </div>
    );
  }

  // No merchants
  if (merchants.length === 0) {
    return (
      <div className="alert alert-info">
        <span>No Gmail receipts found. Connect Gmail and sync receipts to see merchant data.</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Stats */}
      {summary && (
        <div className="stats stats-horizontal bg-base-200 w-full">
          <div className="stat">
            <div className="stat-title">Total Amount</div>
            <div className="stat-value text-2xl">{formatCurrency(summary.total_amount)}</div>
            <div className="stat-desc">
              from {summary.total_receipts} receipts
            </div>
          </div>
          <div className="stat">
            <div className="stat-title">Merchants</div>
            <div className="stat-value text-2xl">{summary.total_merchants}</div>
            <div className="stat-desc">
              {summary.with_template} with templates
            </div>
          </div>
          <div className="stat">
            <div className="stat-title">Matched</div>
            <div className="stat-value text-2xl text-success">{summary.total_matched}</div>
            <div className="stat-desc">
              {summary.total_pending} pending
            </div>
          </div>
          <div className="stat">
            <div className="stat-title">Potential</div>
            <div className="stat-value text-2xl text-info">{summary.total_potential_matches}</div>
            <div className="stat-desc">
              Unmatched bank txns
            </div>
          </div>
        </div>
      )}

      {/* Enrichment Result Alert */}
      {enrichmentResult && (
        <div className={`alert ${enrichmentResult.success ? 'alert-success' : 'alert-error'}`}>
          <span>
            {enrichmentResult.success
              ? `Enriched ${enrichmentResult.domain}: ${enrichmentResult.parsed} parsed, ${enrichmentResult.failed} failed`
              : enrichmentResult.message || 'Enrichment failed'
            }
          </span>
          <button className="btn btn-ghost btn-xs" onClick={() => setEnrichmentResult(null)}>
            Dismiss
          </button>
        </div>
      )}

      {/* Merchants Table */}
      <div className="overflow-x-auto">
        <table className="table table-sm">
          <thead>
            <tr>
              <th className="w-8"></th>
              <th>Domain</th>
              <th className="text-right">Total</th>
              <th className="text-center">Parsed</th>
              <th className="text-center">Matched</th>
              <th className="text-center">Template</th>
            </tr>
          </thead>
          <tbody>
            {merchants.map((merchant) => (
              <React.Fragment key={merchant.merchant_normalized}>
                {/* Main Row */}
                <tr
                  className={`hover cursor-pointer ${expandedMerchant === merchant.merchant_normalized ? 'bg-base-200' : ''}`}
                  onClick={() => toggleExpand(merchant.merchant_normalized)}
                >
                  <td>
                    <span className="text-sm">
                      {expandedMerchant === merchant.merchant_normalized ? '▼' : '▶'}
                    </span>
                  </td>
                  <td>
                    <div className="font-medium">{merchant.merchant_name}</div>
                    <div className="text-xs opacity-60">
                      {merchant.merchant_domain}
                      {merchant.merchant_normalized !== merchant.merchant_domain.split('.')[0] && (
                        <span className="badge badge-xs badge-ghost ml-1">{merchant.merchant_normalized}</span>
                      )}
                    </div>
                  </td>
                  <td className="text-right font-medium">
                    {merchant.total_amount > 0 ? formatCurrency(merchant.total_amount) : '-'}
                  </td>
                  <td className="text-center">
                    <span className={merchant.parsed_count === merchant.receipt_count ? 'text-success' : ''}>
                      {merchant.parsed_count}/{merchant.receipt_count}
                    </span>
                    {merchant.pending_count > 0 && (
                      <span className="text-warning ml-1">({merchant.pending_count} pending)</span>
                    )}
                  </td>
                  <td className="text-center">
                    <span className={merchant.matched_count > 0 ? 'text-success font-semibold' : 'text-base-content/50'}>
                      {merchant.matched_count}
                    </span>
                  </td>
                  <td className="text-center">
                    {getTemplateBadge(merchant)}
                  </td>
                </tr>

                {/* Expanded Row - Receipts */}
                {expandedMerchant === merchant.merchant_normalized && (
                  <tr key={`${merchant.merchant_normalized}-expanded`}>
                    <td colSpan={6} className="bg-base-200 p-4">
                      {loadingReceipts ? (
                        <div className="flex justify-center py-4">
                          <span className="loading loading-spinner loading-sm"></span>
                        </div>
                      ) : expandedReceipts.length === 0 ? (
                        <div className="text-center text-sm opacity-60 py-4">
                          No receipts found
                        </div>
                      ) : (
                        <div className="overflow-x-auto">
                          <table className="table table-xs">
                            <thead>
                              <tr>
                                <th>Date</th>
                                <th>Subject</th>
                                <th>Products</th>
                                <th>Brand</th>
                                <th className="text-right">Amount</th>
                                <th className="text-center">Parsed</th>
                                <th className="text-center">Matched</th>
                              </tr>
                            </thead>
                            <tbody>
                              {expandedReceipts.map((receipt) => (
                                <tr key={receipt.id} className="hover">
                                  <td className="whitespace-nowrap">
                                    {formatDate(receipt.received_at)}
                                  </td>
                                  <td className="max-w-xs truncate" title={receipt.subject}>
                                    {receipt.subject}
                                  </td>
                                  <td className="max-w-xs truncate" title={receipt.line_items?.map(i => i.name).join(', ') || ''}>
                                    <span className={receipt.line_items && receipt.line_items.length > 0 ? 'text-success' : 'opacity-50'}>
                                      {formatLineItems(receipt.line_items)}
                                    </span>
                                  </td>
                                  <td className="max-w-32 truncate">
                                    <span className={extractBrand(receipt.line_items) !== '-' ? 'text-info font-medium' : 'opacity-50'}>
                                      {extractBrand(receipt.line_items)}
                                    </span>
                                  </td>
                                  <td className="text-right whitespace-nowrap">
                                    {formatCurrency(receipt.total_amount, receipt.currency_code)}
                                  </td>
                                  <td className="text-center">
                                    {receipt.parsing_status === 'parsed' ? (
                                      <span className="badge badge-success badge-xs">Parsed</span>
                                    ) : receipt.parsing_status === 'pending' ? (
                                      <span className="badge badge-warning badge-xs">Pending</span>
                                    ) : receipt.parsing_status === 'failed' ? (
                                      <span className="badge badge-error badge-xs">Failed</span>
                                    ) : (
                                      <span className="badge badge-ghost badge-xs">Unparseable</span>
                                    )}
                                  </td>
                                  <td className="text-center">
                                    {receipt.transaction_id ? (
                                      <span className="badge badge-success badge-xs">Yes</span>
                                    ) : (
                                      <span className="badge badge-ghost badge-xs">No</span>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          {expandedReceipts.length === 20 && (
                            <div className="text-xs text-center mt-2 opacity-60">
                              Showing first 20 receipts
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="text-xs opacity-60 flex flex-wrap gap-4">
        <span>Template types: </span>
        <span className="badge badge-success badge-xs">Vendor</span> = Dedicated parser
        <span className="badge badge-info badge-xs">Schema.org</span> = Structured data
        <span className="badge badge-info badge-xs">Pattern</span> = Regex patterns
        <span className="badge badge-ghost badge-xs">None</span> = Needs LLM
      </div>
    </div>
  );
}
