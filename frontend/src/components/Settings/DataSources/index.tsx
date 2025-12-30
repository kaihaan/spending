/**
 * DataSources Container Component
 *
 * This component handles sub-tab routing for the Pre-AI data sources section.
 * URL scheme: /settings#data-sources[/subtab]
 *
 * Examples:
 * - /settings#data-sources         → Summary view
 * - /settings#data-sources/amazon  → Amazon Purchases detail
 * - /settings#data-sources/gmail   → Gmail Receipts detail
 */

import { useState, useEffect, useCallback } from 'react';
import apiClient from '../../../api/client';
import DataSourcesSubTabs from './DataSourcesSubTabs';
import SourceSummaryTable from './SourceSummaryTable';
import AmazonPurchasesTab from './AmazonPurchasesTab';
import AmazonReturnsTab from './AmazonReturnsTab';
import AmazonBusinessTab from './AmazonBusinessTab';
import AppleAppStoreTab from './AppleAppStoreTab';
import GmailReceiptsTab from './GmailReceiptsTab';
import AmazonDigitalTab from './AmazonDigitalTab';
import MatchesTab from './MatchesTab';
import type {
  SourceTabId,
  AmazonStats,
  ReturnsStats,
  AppleStats,
  AmazonBusinessStats,
  GmailStats,
  AmazonDigitalStats,
} from './types';

const DATA_SOURCES_TAB_KEY = 'data-sources-active-tab';
const VALID_SUBTABS: SourceTabId[] = ['summary', 'amazon', 'returns', 'business', 'apple', 'gmail', 'digital', 'matches'];

interface DataSourcesProps {
  subTab?: string;
}

export default function DataSources({ subTab }: DataSourcesProps) {
  // Parse the current sub-tab from props, falling back to localStorage then 'summary'
  const getActiveTab = (): SourceTabId => {
    if (subTab && VALID_SUBTABS.includes(subTab as SourceTabId)) {
      return subTab as SourceTabId;
    }
    // No subtab in URL - check localStorage for last selected
    const saved = localStorage.getItem(DATA_SOURCES_TAB_KEY);
    if (saved && VALID_SUBTABS.includes(saved as SourceTabId)) {
      return saved as SourceTabId;
    }
    return 'summary';
  };

  const activeTab: SourceTabId = getActiveTab();

  // Persist tab selection and sync URL when activeTab changes
  useEffect(() => {
    localStorage.setItem(DATA_SOURCES_TAB_KEY, activeTab);
    // If URL doesn't have the subtab but we restored from localStorage, update URL
    if (!subTab && activeTab !== 'summary') {
      window.location.hash = `data-sources/${activeTab}`;
    }
  }, [activeTab, subTab]);

  // Statistics for badge counts in sub-tabs
  const [amazonStats, setAmazonStats] = useState<AmazonStats | null>(null);
  const [returnsStats, setReturnsStats] = useState<ReturnsStats | null>(null);
  const [appleStats, setAppleStats] = useState<AppleStats | null>(null);
  const [businessStats, setBusinessStats] = useState<AmazonBusinessStats | null>(null);
  const [gmailStats, setGmailStats] = useState<GmailStats | null>(null);
  const [digitalStats, setDigitalStats] = useState<AmazonDigitalStats | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState(true);

  // Fetch statistics for all sources (for badge counts)
  const fetchAllStats = useCallback(async () => {
    setIsLoadingStats(true);
    try {
      const [amazon, returns, apple, business, gmail, digital] = await Promise.all([
        apiClient.get<AmazonStats>('/amazon/statistics').catch(() => ({ data: null })),
        apiClient.get<ReturnsStats>('/amazon/returns/statistics').catch(() => ({ data: null })),
        apiClient.get<AppleStats>('/apple/statistics').catch(() => ({ data: null })),
        apiClient.get<AmazonBusinessStats>('/amazon-business/statistics').catch(() => ({ data: null })),
        apiClient.get<GmailStats>('/gmail/statistics?user_id=1').catch(() => ({ data: null })),
        apiClient.get<AmazonDigitalStats>('/amazon/digital/statistics').catch(() => ({ data: null })),
      ]);

      setAmazonStats(amazon.data);
      setReturnsStats(returns.data);
      setAppleStats(apple.data);
      setBusinessStats(business.data);
      setGmailStats(gmail.data);
      setDigitalStats(digital.data);
    } catch (error) {
      console.error('Failed to fetch source statistics:', error);
    } finally {
      setIsLoadingStats(false);
    }
  }, []);

  useEffect(() => {
    fetchAllStats();
  }, [fetchAllStats]);

  // Build tab counts for badges
  const tabCounts = {
    amazon: amazonStats?.total_orders ?? undefined,
    returns: returnsStats?.total_returns ?? undefined,
    apple: appleStats?.total_transactions ?? undefined,
    business: businessStats?.total_orders ?? undefined,
    gmail: gmailStats?.total_receipts ?? undefined,
    digital: digitalStats?.total_orders ?? undefined,
  };

  // Handle tab change by updating URL hash
  const handleTabChange = (tabId: SourceTabId) => {
    if (tabId === 'summary') {
      window.location.hash = 'data-sources';
    } else {
      window.location.hash = `data-sources/${tabId}`;
    }
  };

  // Render the active tab content
  const renderTabContent = () => {
    switch (activeTab) {
      case 'summary':
        return (
          <SourceSummaryTable
            amazonStats={amazonStats}
            returnsStats={returnsStats}
            appleStats={appleStats}
            businessStats={businessStats}
            gmailStats={gmailStats}
            isLoading={isLoadingStats}
            onNavigateToTab={handleTabChange}
          />
        );
      case 'amazon':
        return <AmazonPurchasesTab stats={amazonStats} onStatsUpdate={fetchAllStats} />;
      case 'returns':
        return <AmazonReturnsTab stats={returnsStats} onStatsUpdate={fetchAllStats} />;
      case 'business':
        return <AmazonBusinessTab stats={businessStats} onStatsUpdate={fetchAllStats} />;
      case 'apple':
        return <AppleAppStoreTab stats={appleStats} onStatsUpdate={fetchAllStats} />;
      case 'gmail':
        return <GmailReceiptsTab stats={gmailStats} onStatsUpdate={fetchAllStats} />;
      case 'digital':
        return <AmazonDigitalTab stats={digitalStats} onStatsUpdate={fetchAllStats} />;
      case 'matches':
        return <MatchesTab />;
      default:
        return <SourceSummaryTable
          amazonStats={amazonStats}
          returnsStats={returnsStats}
          appleStats={appleStats}
          businessStats={businessStats}
          gmailStats={gmailStats}
          isLoading={isLoadingStats}
          onNavigateToTab={handleTabChange}
        />;
    }
  };

  return (
    <div className="space-y-4">
      {/* Sub-tab navigation */}
      <DataSourcesSubTabs
        activeTab={activeTab}
        onTabChange={handleTabChange}
        tabCounts={tabCounts}
        isLoading={isLoadingStats}
      />

      {/* Tab content */}
      <div className="mt-4">
        {renderTabContent()}
      </div>
    </div>
  );
}
