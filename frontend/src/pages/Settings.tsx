import { useState, useEffect } from 'react';
import BankTab from '../components/Settings/BankTab';
import EnrichmentTab from '../components/Settings/EnrichmentTab';
import DataSourcesTab from '../components/Settings/DataSourcesTab';
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
 * Settings page - renders tab content based on URL hash.
 * Tab navigation UI is handled by SettingsTabsDrawer in App.tsx.
 */
export default function Settings() {
  const [activeTab, setActiveTab] = useState<TabType>(() => {
    const hash = window.location.hash.replace('#', '') as TabType;
    if (hash && VALID_TABS.includes(hash)) {
      return hash;
    }
    const saved = localStorage.getItem(SETTINGS_TAB_KEY) as TabType;
    if (saved && VALID_TABS.includes(saved)) {
      return saved;
    }
    return 'bank';
  });

  useEffect(() => {
    // Sync hash on mount if needed
    if (!window.location.hash) {
      window.location.hash = activeTab;
    }

    // Listen for hash changes from SettingsTabsDrawer
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '') as TabType;
      if (hash && VALID_TABS.includes(hash) && hash !== activeTab) {
        setActiveTab(hash);
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [activeTab]);

  return (
    <div className="container mx-auto p-4 max-w-6xl">
      {activeTab === 'bank' && <BankTab />}
      {activeTab === 'enrichment' && <EnrichmentTab />}
      {activeTab === 'data-sources' && <DataSourcesTab />}
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
