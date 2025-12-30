/**
 * DataSourcesSubTabs Component
 *
 * Renders a horizontal tab bar for navigating between data source detail views.
 * Uses daisyUI tabs with badge counts for each source.
 */

import type { SourceTabId } from './types';

interface TabCounts {
  amazon?: number;
  returns?: number;
  apple?: number;
  business?: number;
  gmail?: number;
  digital?: number;
}

interface DataSourcesSubTabsProps {
  activeTab: SourceTabId;
  onTabChange: (tabId: SourceTabId) => void;
  tabCounts: TabCounts;
  isLoading?: boolean;
}

interface TabConfig {
  id: SourceTabId;
  label: string;
  countKey?: keyof TabCounts;
}

const TABS: TabConfig[] = [
  { id: 'summary', label: 'Summary' },
  { id: 'amazon', label: 'Amazon', countKey: 'amazon' },
  { id: 'returns', label: 'Returns', countKey: 'returns' },
  { id: 'business', label: 'Business', countKey: 'business' },
  { id: 'apple', label: 'Apple', countKey: 'apple' },
  { id: 'gmail', label: 'Gmail', countKey: 'gmail' },
  { id: 'digital', label: 'Digital', countKey: 'digital' },
  { id: 'matches', label: 'Matches' },
];

export default function DataSourcesSubTabs({
  activeTab,
  onTabChange,
  tabCounts,
  isLoading = false,
}: DataSourcesSubTabsProps) {
  return (
    <div className="border-b border-base-300">
      <div role="tablist" className="tabs tabs-bordered">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          const count = tab.countKey ? tabCounts[tab.countKey] : undefined;

          return (
            <button
              key={tab.id}
              role="tab"
              className={`tab gap-2 ${isActive ? 'tab-active' : ''}`}
              onClick={() => onTabChange(tab.id)}
              aria-selected={isActive}
            >
              <span>{tab.label}</span>
              {tab.countKey && (
                <span className={`badge badge-sm ${isActive ? 'badge-primary' : 'badge-ghost'}`}>
                  {isLoading ? (
                    <span className="loading loading-dots loading-xs" />
                  ) : (
                    count ?? 0
                  )}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
