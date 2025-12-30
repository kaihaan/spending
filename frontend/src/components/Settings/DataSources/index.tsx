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
import type {
  SourceTabId,
  AmazonStats,
  ReturnsStats,
  AppleStats,
  AmazonBusinessStats,
  GmailStats,
} from './types';

interface DataSourcesProps {
  subTab?: string;
}

export default function DataSources({ subTab }: DataSourcesProps) {
  // Parse the current sub-tab from props (passed from Settings.tsx)
  const activeTab: SourceTabId = (subTab as SourceTabId) || 'summary';

  // Statistics for badge counts in sub-tabs
  const [amazonStats, setAmazonStats] = useState<AmazonStats | null>(null);
  const [returnsStats, setReturnsStats] = useState<ReturnsStats | null>(null);
  const [appleStats, setAppleStats] = useState<AppleStats | null>(null);
  const [businessStats, setBusinessStats] = useState<AmazonBusinessStats | null>(null);
  const [gmailStats, setGmailStats] = useState<GmailStats | null>(null);
  const [isLoadingStats, setIsLoadingStats] = useState(true);

  // Fetch statistics for all sources (for badge counts)
  const fetchAllStats = useCallback(async () => {
    setIsLoadingStats(true);
    try {
      const [amazon, returns, apple, business, gmail] = await Promise.all([
        apiClient.get<AmazonStats>('/amazon/statistics').catch(() => ({ data: null })),
        apiClient.get<ReturnsStats>('/amazon/returns/statistics').catch(() => ({ data: null })),
        apiClient.get<AppleStats>('/apple/statistics').catch(() => ({ data: null })),
        apiClient.get<AmazonBusinessStats>('/amazon-business/statistics').catch(() => ({ data: null })),
        apiClient.get<GmailStats>('/gmail/statistics?user_id=1').catch(() => ({ data: null })),
      ]);

      setAmazonStats(amazon.data);
      setReturnsStats(returns.data);
      setAppleStats(apple.data);
      setBusinessStats(business.data);
      setGmailStats(gmail.data);
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
