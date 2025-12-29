import { useState, useEffect } from 'react';
import BankTab from '../components/Settings/BankTab';
import EnrichmentTab from '../components/Settings/EnrichmentTab';
import DataSources from '../components/Settings/DataSources';
import DeveloperTab from '../components/Settings/DeveloperTab';
import CategoriesTab from '../components/Settings/CategoriesTab';
import DirectDebitsTab from '../components/Settings/DirectDebitsTab';
import RulesTab from '../components/Settings/RulesTab';
import ThemeTab from '../components/Settings/ThemeTab';
import GmailMerchantsTab from '../components/Settings/GmailMerchantsTab';
import GmailLLMQueueTab from '../components/Settings/GmailLLMQueueTab';

type TabType = 'bank' | 'enrichment' | 'data-sources' | 'developer' | 'categories' | 'direct-debits' | 'rules' | 'theme' | 'gmail-merchants' | 'gmail-llm-queue';

const VALID_TABS: TabType[] = ['bank', 'enrichment', 'data-sources', 'developer', 'categories', 'direct-debits', 'rules', 'theme', 'gmail-merchants', 'gmail-llm-queue'];
const SETTINGS_TAB_KEY = 'settings-active-tab';

/**
 * Parse hash to extract main tab and optional sub-tab.
 * Examples:
 * - "#data-sources" -> { mainTab: "data-sources", subTab: undefined }
 * - "#data-sources/amazon" -> { mainTab: "data-sources", subTab: "amazon" }
 */
function parseHash(hash: string): { mainTab: string; subTab?: string } {
  const cleanHash = hash.replace('#', '');
  const parts = cleanHash.split('/');
  return {
    mainTab: parts[0] || '',
    subTab: parts[1],
  };
}

/**
 * Settings page - renders tab content based on URL hash.
 * Tab navigation UI is handled by SettingsTabsDrawer in App.tsx.
 *
 * Supports sub-tabs for data-sources:
 * - #data-sources -> Summary view
 * - #data-sources/amazon -> Amazon Purchases detail
 * - #data-sources/returns -> Amazon Returns detail
 * - etc.
 */
export default function Settings() {
  const [activeTab, setActiveTab] = useState<TabType>(() => {
    const { mainTab } = parseHash(window.location.hash);
    if (mainTab && VALID_TABS.includes(mainTab as TabType)) {
      return mainTab as TabType;
    }
    const saved = localStorage.getItem(SETTINGS_TAB_KEY) as TabType;
    if (saved && VALID_TABS.includes(saved)) {
      return saved;
    }
    return 'bank';
  });

  const [dataSourcesSubTab, setDataSourcesSubTab] = useState<string | undefined>(() => {
    const { mainTab, subTab } = parseHash(window.location.hash);
    return mainTab === 'data-sources' ? subTab : undefined;
  });

  useEffect(() => {
    // Sync hash on mount if needed
    if (!window.location.hash) {
      window.location.hash = activeTab;
    }

    // Listen for hash changes from SettingsTabsDrawer or DataSources sub-tabs
    const handleHashChange = () => {
      const { mainTab, subTab } = parseHash(window.location.hash);

      // Handle main tab change
      if (mainTab && VALID_TABS.includes(mainTab as TabType) && mainTab !== activeTab) {
        setActiveTab(mainTab as TabType);
      }

      // Handle sub-tab for data-sources
      if (mainTab === 'data-sources') {
        setDataSourcesSubTab(subTab);
      } else {
        setDataSourcesSubTab(undefined);
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [activeTab]);

  return (
    <div className="container mx-auto p-4 max-w-6xl">
      {activeTab === 'bank' && <BankTab />}
      {activeTab === 'enrichment' && <EnrichmentTab />}
      {activeTab === 'data-sources' && <DataSources subTab={dataSourcesSubTab} />}
      {activeTab === 'developer' && <DeveloperTab />}
      {activeTab === 'categories' && <CategoriesTab />}
      {activeTab === 'direct-debits' && <DirectDebitsTab />}
      {activeTab === 'rules' && <RulesTab />}
      {activeTab === 'gmail-merchants' && <GmailMerchantsTab />}
      {activeTab === 'gmail-llm-queue' && <GmailLLMQueueTab />}
      {activeTab === 'theme' && <ThemeTab />}
    </div>
  );
}
