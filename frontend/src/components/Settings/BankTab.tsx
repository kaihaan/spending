/**
 * BankTab Component
 *
 * Main container for bank settings with overview panel and sub-tab navigation:
 * - Accounts: TrueLayer linking, sync, and account mappings
 * - Raw Data: Paginated table of raw TrueLayer transaction data (with overview stats)
 * - Rules: Enrichment rules for automatic transaction categorization
 */

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../api/client';
import { BankAccountsTab, BankRawDataTab } from './Bank';
import RulesTab from './RulesTab';

type TabId = 'accounts' | 'raw-data' | 'rules';

const BANK_TAB_KEY = 'bank-active-tab';
const VALID_TABS: TabId[] = ['accounts', 'raw-data', 'rules'];

interface BankStats {
  transaction_count: number;
  total_in: number;
  total_out: number;
  min_date: string | null;
  max_date: string | null;
}

/** Format date string to readable format like "01 Jan 2025" */
function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

/** Format currency with £ symbol */
function formatCurrency(amount: number): string {
  return `£${amount.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function BankTab() {
  // Restore tab from localStorage or default to 'accounts'
  const getInitialTab = (): TabId => {
    const saved = localStorage.getItem(BANK_TAB_KEY);
    if (saved && VALID_TABS.includes(saved as TabId)) {
      return saved as TabId;
    }
    return 'accounts';
  };

  const [activeTab, setActiveTab] = useState<TabId>(getInitialTab);
  const [stats, setStats] = useState<BankStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Persist tab selection to localStorage
  useEffect(() => {
    localStorage.setItem(BANK_TAB_KEY, activeTab);
  }, [activeTab]);

  const fetchStats = useCallback(async () => {
    try {
      const response = await apiClient.get<BankStats>('/truelayer/statistics');
      setStats(response.data);
    } catch (error) {
      console.error('Failed to fetch bank statistics:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return (
    <div className="space-y-6">
      {/* Tab Navigation */}
      <div role="tablist" className="tabs tabs-bordered">
        <button
          role="tab"
          className={`tab tab-lg ${activeTab === 'accounts' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('accounts')}
        >
          Accounts
        </button>
        <button
          role="tab"
          className={`tab tab-lg ${activeTab === 'raw-data' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('raw-data')}
        >
          Raw Data
        </button>
        <button
          role="tab"
          className={`tab tab-lg ${activeTab === 'rules' ? 'tab-active' : ''}`}
          onClick={() => setActiveTab('rules')}
        >
          Rules
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'accounts' && <BankAccountsTab />}
      {activeTab === 'raw-data' && (
        <>
          {/* Overview Panel */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Total In & Total Out - stacked vertically */}
            <div className="bg-base-200 rounded-lg p-4 space-y-4">
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Total In</div>
                {isLoading ? (
                  <div className="animate-pulse h-7 bg-base-300 rounded w-32" />
                ) : (
                  <div className="font-medium text-2xl text-success">
                    {formatCurrency(stats?.total_in ?? 0)}
                  </div>
                )}
              </div>
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Total Out</div>
                {isLoading ? (
                  <div className="animate-pulse h-7 bg-base-300 rounded w-32" />
                ) : (
                  <div className="font-medium text-2xl text-error">
                    {formatCurrency(stats?.total_out ?? 0)}
                  </div>
                )}
              </div>
            </div>

            {/* Date Range & Transaction Count - stacked vertically */}
            <div className="bg-base-200 rounded-lg p-4 space-y-4">
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Date Range</div>
                {isLoading ? (
                  <div className="animate-pulse h-5 bg-base-300 rounded w-48" />
                ) : stats?.min_date && stats?.max_date ? (
                  <div className="font-medium">
                    {formatDate(stats.min_date)} — {formatDate(stats.max_date)}
                  </div>
                ) : (
                  <div className="text-base-content/50">No data</div>
                )}
              </div>
              <div>
                <div className="text-xs text-base-content/60 uppercase tracking-wide mb-1">Transactions</div>
                {isLoading ? (
                  <div className="animate-pulse h-5 bg-base-300 rounded w-24" />
                ) : (
                  <div className="font-medium text-2xl">
                    {(stats?.transaction_count ?? 0).toLocaleString()}
                  </div>
                )}
              </div>
            </div>
          </div>

          <BankRawDataTab />
        </>
      )}
      {activeTab === 'rules' && <RulesTab />}
    </div>
  );
}
