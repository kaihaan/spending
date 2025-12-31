/**
 * RuleResultsTab Component
 *
 * Displays rule-enriched transactions with conflict detection and resolution.
 * Shows all transactions that have been categorized by rules (category_rule,
 * merchant_rule, or direct_debit) with ability to analyze and resolve conflicts.
 */

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../../api/client';
import { useTableStyles } from '../../../hooks/useTableStyles';

// Types
interface RuleEnrichment {
  primary_category: string;
  subcategory: string | null;
  essential_discretionary: string | null;
  rule_type: 'category_rule' | 'merchant_rule' | 'direct_debit';
  matched_rule_id: number | null;
  matched_rule_name: string | null;
  matched_merchant_id: number | null;
  matched_merchant_name: string | null;
  merchant_clean_name: string | null;
  confidence_score: number;
}

interface RuleEnrichedTransaction {
  id: number;
  description: string;
  amount: number;
  timestamp: string;
  rule_enrichment: RuleEnrichment;
  has_conflict: boolean;
  conflicting_rules_count: number;
  conflict_resolved: boolean;
}

interface PaginatedResponse {
  transactions: RuleEnrichedTransaction[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

interface MatchingRule {
  id: number;
  type: 'category_rule' | 'merchant_rule';
  name: string;
  category: string;
  subcategory: string | null;
  priority: number;
  pattern: string;
  pattern_type: string;
  is_winner?: boolean;
}

interface TransactionDetail {
  transaction: {
    id: number;
    description: string;
    amount: number;
    timestamp: string;
    transaction_type: string;
  };
  applied_rule: RuleEnrichment | null;
  all_matching_rules: MatchingRule[];
  has_conflict: boolean;
}

interface ConflictAnalysis {
  total_transactions: number;
  rule_enriched_count: number;
  conflicts_count: number;
  conflicts: Array<{
    transaction_id: number;
    description: string;
    amount: number;
    matching_rules: MatchingRule[];
    winning_rule: MatchingRule;
  }>;
  analyzed_at: string;
}

// Rule type badge colors
const RULE_TYPE_STYLES: Record<string, { bg: string; text: string }> = {
  category_rule: { bg: 'badge-primary', text: 'Category' },
  merchant_rule: { bg: 'badge-secondary', text: 'Merchant' },
  direct_debit: { bg: 'badge-accent', text: 'Direct Debit' },
};

export default function RuleResultsTab() {
  // Glass effect styling for theme-aware table backgrounds
  const { style: glassStyle, className: glassClassName } = useTableStyles();

  // Data state
  const [data, setData] = useState<PaginatedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 50;

  // Filters - restored from localStorage
  const [ruleTypeFilter, setRuleTypeFilter] = useState<string>(() => {
    return localStorage.getItem('ruleResults.ruleTypeFilter') || '';
  });
  const [categoryFilter, setCategoryFilter] = useState<string>(() => {
    return localStorage.getItem('ruleResults.categoryFilter') || '';
  });
  const [conflictsOnlyFilter, setConflictsOnlyFilter] = useState<boolean>(() => {
    return localStorage.getItem('ruleResults.conflictsOnly') === 'true';
  });

  // Conflict analysis
  const [conflictAnalysis, setConflictAnalysis] = useState<ConflictAnalysis | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Detail drawer
  const [selectedTransaction, setSelectedTransaction] = useState<number | null>(null);
  const [transactionDetail, setTransactionDetail] = useState<TransactionDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Conflict resolution
  const [selectedRule, setSelectedRule] = useState<number | null>(null);
  const [selectedRuleType, setSelectedRuleType] = useState<string>('');
  const [isResolving, setIsResolving] = useState(false);

  // Fetch paginated rule results
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, string | number | boolean> = {
        page,
        page_size: pageSize,
      };
      if (ruleTypeFilter) params.rule_type = ruleTypeFilter;
      if (categoryFilter) params.category = categoryFilter;
      if (conflictsOnlyFilter) params.has_conflict = true;

      const response = await apiClient.get<PaginatedResponse>('/rules/results', { params });
      setData(response.data);
    } catch (err) {
      console.error('Failed to fetch rule results:', err);
      setError('Failed to load rule-enriched transactions');
    } finally {
      setLoading(false);
    }
  }, [page, ruleTypeFilter, categoryFilter, conflictsOnlyFilter]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Fetch transaction detail with all matching rules
  const fetchTransactionDetail = useCallback(async (transactionId: number) => {
    try {
      setLoadingDetail(true);
      const response = await apiClient.get<TransactionDetail>(`/rules/results/${transactionId}`);
      setTransactionDetail(response.data);

      // Pre-select the winning rule
      if (response.data.applied_rule) {
        setSelectedRule(response.data.applied_rule.matched_rule_id);
        setSelectedRuleType(response.data.applied_rule.rule_type);
      }
    } catch (err) {
      console.error('Failed to fetch transaction detail:', err);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  // Open detail drawer
  const handleRowClick = (transactionId: number) => {
    setSelectedTransaction(transactionId);
    void fetchTransactionDetail(transactionId);
  };

  // Close detail drawer
  const handleCloseDrawer = () => {
    setSelectedTransaction(null);
    setTransactionDetail(null);
    setSelectedRule(null);
    setSelectedRuleType('');
  };

  // Analyze conflicts
  const handleAnalyzeConflicts = async () => {
    try {
      setIsAnalyzing(true);
      const response = await apiClient.post<ConflictAnalysis>('/rules/results/analyze-conflicts');
      setConflictAnalysis(response.data);
    } catch (err) {
      console.error('Failed to analyze conflicts:', err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Resolve conflict
  const handleResolveConflict = async (applyToSimilar: boolean) => {
    if (!selectedTransaction || !selectedRule || !selectedRuleType) return;

    try {
      setIsResolving(true);
      await apiClient.post('/rules/results/resolve-conflict', {
        transaction_id: selectedTransaction,
        winning_rule_id: selectedRule,
        winning_rule_type: selectedRuleType,
        resolution_type: 'override_transaction',
        apply_to_similar: applyToSimilar,
      });

      // Refresh data and close drawer
      void fetchData();
      handleCloseDrawer();
    } catch (err) {
      console.error('Failed to resolve conflict:', err);
    } finally {
      setIsResolving(false);
    }
  };

  // Format helpers
  const formatDateTime = (timestamp: string): string => {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  };

  const formatAmount = (amount: number): string => {
    const absAmount = Math.abs(amount);
    const formatted = absAmount.toLocaleString('en-GB', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return amount < 0 ? `-£${formatted}` : `£${formatted}`;
  };

  // Get unique categories for filter
  const categories = data?.transactions
    ? [...new Set(data.transactions.map((t) => t.rule_enrichment.primary_category))]
    : [];

  if (error) {
    return (
      <div className="alert alert-error">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="stroke-current shrink-0 h-6 w-6"
          fill="none"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span>{error}</span>
        <button className="btn btn-sm" onClick={() => void fetchData()}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h3 className="text-lg font-semibold">Rule-Enriched Transactions</h3>
          <p className="text-sm text-base-content/60">
            Transactions categorized by pattern rules
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <div className="badge badge-neutral badge-lg">
              {data.total.toLocaleString()} transactions
            </div>
          )}
          <button
            className={`btn btn-sm btn-outline ${isAnalyzing ? 'loading' : ''}`}
            onClick={() => void handleAnalyzeConflicts()}
            disabled={isAnalyzing}
          >
            {isAnalyzing ? 'Analyzing...' : 'Analyze Conflicts'}
          </button>
        </div>
      </div>

      {/* Conflict Analysis Banner */}
      {conflictAnalysis && (
        <div
          className={`alert ${conflictAnalysis.conflicts_count > 0 ? 'alert-warning' : 'alert-success'}`}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div>
            <div className="font-medium">
              {conflictAnalysis.conflicts_count > 0
                ? `${conflictAnalysis.conflicts_count} potential conflicts found`
                : 'No conflicts detected'}
            </div>
            <div className="text-sm opacity-70">
              {conflictAnalysis.rule_enriched_count.toLocaleString()} of{' '}
              {conflictAnalysis.total_transactions.toLocaleString()} transactions have rule enrichment
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4 flex-wrap">
        <select
          className="select select-bordered select-sm"
          value={ruleTypeFilter}
          onChange={(e) => {
            const value = e.target.value;
            setRuleTypeFilter(value);
            localStorage.setItem('ruleResults.ruleTypeFilter', value);
            setPage(1);
          }}
        >
          <option value="">All Rule Types</option>
          <option value="category_rule">Category Rules</option>
          <option value="merchant_rule">Merchant Rules</option>
          <option value="direct_debit">Direct Debit</option>
        </select>

        <select
          className="select select-bordered select-sm"
          value={categoryFilter}
          onChange={(e) => {
            const value = e.target.value;
            setCategoryFilter(value);
            localStorage.setItem('ruleResults.categoryFilter', value);
            setPage(1);
          }}
        >
          <option value="">All Categories</option>
          {categories.map((cat) => (
            <option key={cat} value={cat}>
              {cat}
            </option>
          ))}
        </select>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            className="checkbox checkbox-sm checkbox-warning"
            checked={conflictsOnlyFilter}
            onChange={(e) => {
              const checked = e.target.checked;
              setConflictsOnlyFilter(checked);
              localStorage.setItem('ruleResults.conflictsOnly', String(checked));
              setPage(1);
            }}
          />
          <span className="text-sm flex items-center gap-1">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-4 w-4 text-warning"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
            Conflicts Only
          </span>
        </label>
      </div>

      {/* Table */}
      <div className={`overflow-x-auto border border-base-300 rounded-lg ${glassClassName}`} style={glassStyle}>
        <table className="table table-sm">
          <thead className={glassClassName} style={glassStyle}>
            <tr>
              <th className="w-24">Date</th>
              <th>Description</th>
              <th className="w-24 text-right">Amount</th>
              <th className="w-28">Rule Type</th>
              <th className="w-32">Rule Name</th>
              <th className="w-28">Category</th>
              <th className="w-8"></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              // Loading skeleton
              Array.from({ length: 10 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  <td>
                    <div className="h-4 bg-base-300 rounded w-20" />
                  </td>
                  <td>
                    <div className="h-4 bg-base-300 rounded w-48" />
                  </td>
                  <td>
                    <div className="h-4 bg-base-300 rounded w-16 ml-auto" />
                  </td>
                  <td>
                    <div className="h-4 bg-base-300 rounded w-20" />
                  </td>
                  <td>
                    <div className="h-4 bg-base-300 rounded w-24" />
                  </td>
                  <td>
                    <div className="h-4 bg-base-300 rounded w-20" />
                  </td>
                  <td></td>
                </tr>
              ))
            ) : data?.transactions.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-base-content/60">
                  No rule-enriched transactions found
                </td>
              </tr>
            ) : (
              data?.transactions.map((txn) => {
                const ruleStyle = RULE_TYPE_STYLES[txn.rule_enrichment.rule_type] || {
                  bg: 'badge-ghost',
                  text: txn.rule_enrichment.rule_type,
                };
                return (
                  <tr
                    key={txn.id}
                    className="hover cursor-pointer"
                    onClick={() => handleRowClick(txn.id)}
                  >
                    <td className="text-xs whitespace-nowrap">{formatDateTime(txn.timestamp)}</td>
                    <td className="max-w-xs truncate" title={txn.description}>
                      {txn.description}
                    </td>
                    <td
                      className={`text-right font-mono text-sm ${txn.amount < 0 ? 'text-error' : 'text-success'}`}
                    >
                      {formatAmount(txn.amount)}
                    </td>
                    <td>
                      <span className={`badge badge-sm whitespace-nowrap ${ruleStyle.bg}`}>{ruleStyle.text}</span>
                    </td>
                    <td className="text-sm truncate max-w-[8rem]" title={txn.rule_enrichment.matched_rule_name || ''}>
                      {txn.rule_enrichment.matched_rule_name || txn.rule_enrichment.matched_merchant_name || '—'}
                    </td>
                    <td className="text-sm">{txn.rule_enrichment.primary_category}</td>
                    <td>
                      {txn.has_conflict && txn.conflict_resolved ? (
                        // Resolved conflict - green checkmark
                        <span className="text-success" title="Conflict resolved">
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="h-5 w-5"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                            />
                          </svg>
                        </span>
                      ) : txn.has_conflict ? (
                        // Unresolved conflict - yellow warning
                        <span className="text-warning" title="Multiple rules match">
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            className="h-5 w-5"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                            />
                          </svg>
                        </span>
                      ) : null}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-base-content/60">
            Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, data.total)} of{' '}
            {data.total.toLocaleString()}
          </div>
          <div className="join">
            <button
              className="join-item btn btn-sm"
              disabled={page === 1 || loading}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </button>
            <button className="join-item btn btn-sm btn-disabled">
              Page {page} of {data.total_pages}
            </button>
            <button
              className="join-item btn btn-sm"
              disabled={page >= data.total_pages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Detail/Resolution Drawer */}
      {selectedTransaction && (
        <div className="fixed inset-0 z-50 overflow-hidden">
          <div className="absolute inset-0 bg-black/50" onClick={handleCloseDrawer} />
          <div className="absolute right-0 top-0 h-full w-full max-w-lg bg-base-100 shadow-xl overflow-y-auto">
            <div className="p-6">
              {/* Drawer Header */}
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-lg font-semibold">
                  {transactionDetail?.has_conflict ? 'Resolve Conflict' : 'Rule Details'}
                </h3>
                <button className="btn btn-sm btn-ghost btn-circle" onClick={handleCloseDrawer}>
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className="h-6 w-6"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {loadingDetail ? (
                <div className="space-y-4 animate-pulse">
                  <div className="h-6 bg-base-300 rounded w-3/4" />
                  <div className="h-4 bg-base-300 rounded w-1/2" />
                  <div className="h-32 bg-base-300 rounded" />
                </div>
              ) : transactionDetail ? (
                <div className="space-y-6">
                  {/* Transaction Info */}
                  <div className="bg-base-200 rounded-lg p-4">
                    <div className="text-sm text-base-content/60 mb-1">Transaction</div>
                    <div className="font-medium">{transactionDetail.transaction.description}</div>
                    <div className="flex gap-4 mt-2 text-sm">
                      <span
                        className={
                          transactionDetail.transaction.amount < 0 ? 'text-error' : 'text-success'
                        }
                      >
                        {formatAmount(transactionDetail.transaction.amount)}
                      </span>
                      <span className="text-base-content/60">
                        {formatDateTime(transactionDetail.transaction.timestamp)}
                      </span>
                    </div>
                  </div>

                  {/* Matching Rules */}
                  <div>
                    <div className="text-sm font-medium mb-3">
                      Matching Rules ({transactionDetail.all_matching_rules.length})
                    </div>
                    <div className="space-y-2">
                      {transactionDetail.all_matching_rules.map((rule) => (
                        <label
                          key={`${rule.type}-${rule.id}`}
                          className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                            selectedRule === rule.id && selectedRuleType === rule.type
                              ? 'border-primary bg-primary/5'
                              : 'border-base-300 hover:border-base-content/30'
                          }`}
                        >
                          <input
                            type="radio"
                            name="winning-rule"
                            className="radio radio-primary mt-1"
                            checked={selectedRule === rule.id && selectedRuleType === rule.type}
                            onChange={() => {
                              setSelectedRule(rule.id);
                              setSelectedRuleType(rule.type);
                            }}
                          />
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <span className="font-medium">{rule.name}</span>
                              <span
                                className={`badge badge-xs whitespace-nowrap ${RULE_TYPE_STYLES[rule.type]?.bg || 'badge-ghost'}`}
                              >
                                {RULE_TYPE_STYLES[rule.type]?.text || rule.type}
                              </span>
                              {rule.is_winner && (
                                <span className="badge badge-xs badge-success">Current</span>
                              )}
                            </div>
                            <div className="text-sm text-base-content/60 mt-1">
                              {rule.category}
                              {rule.subcategory && ` / ${rule.subcategory}`}
                            </div>
                            <div className="text-xs text-base-content/40 mt-1">
                              Priority: {rule.priority} | Pattern: {rule.pattern_type}
                            </div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex flex-col gap-3 pt-4 border-t border-base-300">
                    {transactionDetail.has_conflict ? (
                      <>
                        <div className="text-sm font-medium text-base-content/70">
                          Apply selected rule to:
                        </div>
                        <div className="flex gap-2">
                          <button
                            className={`btn btn-outline flex-1 ${isResolving ? 'loading' : ''}`}
                            disabled={!selectedRule || isResolving}
                            onClick={() => void handleResolveConflict(false)}
                          >
                            This Transaction Only
                          </button>
                          <button
                            className={`btn btn-primary flex-1 ${isResolving ? 'loading' : ''}`}
                            disabled={!selectedRule || isResolving}
                            onClick={() => void handleResolveConflict(true)}
                          >
                            All Similar
                          </button>
                        </div>
                        <button className="btn btn-ghost btn-sm" onClick={handleCloseDrawer}>
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button className="btn btn-ghost" onClick={handleCloseDrawer}>
                        Close
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-base-content/60">Failed to load details</div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
