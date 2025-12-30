import { useEffect, useState } from 'react';

type TabType = 'bank' | 'enrichment' | 'data-sources' | 'developer' | 'categories' | 'direct-debits' | 'theme' | 'gmail-merchants' | 'gmail-llm-queue';

const VALID_TABS: TabType[] = ['bank', 'enrichment', 'data-sources', 'developer', 'categories', 'direct-debits', 'theme', 'gmail-merchants', 'gmail-llm-queue'];
const SETTINGS_TAB_KEY = 'settings-active-tab';

/**
 * SettingsTabsDrawer - Settings sub-navigation that attaches below the main nav.
 * Syncs with URL hash and localStorage for tab persistence.
 */
export default function SettingsTabsDrawer() {
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
    // Sync hash with current tab on mount
    if (window.location.hash.replace('#', '') !== activeTab) {
      window.location.hash = activeTab;
    }

    // Listen for hash changes (back/forward navigation)
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '') as TabType;
      if (hash && VALID_TABS.includes(hash) && hash !== activeTab) {
        setActiveTab(hash);
        localStorage.setItem(SETTINGS_TAB_KEY, hash);
      }
    };

    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, [activeTab]);

  const handleTabChange = (tab: TabType) => {
    setActiveTab(tab);
    window.location.hash = tab;
    localStorage.setItem(SETTINGS_TAB_KEY, tab);
  };

  return (
    <div className="bg-base-200 shadow-sm">
      <div className="container mx-auto px-4 max-w-6xl">
        <div className="tabs tabs-boxed bg-transparent py-1" role="tablist">
          <button
            role="tab"
            className={`tab ${activeTab === 'bank' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('bank')}
          >
            Bank
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'data-sources' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('data-sources')}
          >
            Pre-AI
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'enrichment' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('enrichment')}
          >
            AI
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'developer' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('developer')}
          >
            Developer
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'categories' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('categories')}
          >
            Categories
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'direct-debits' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('direct-debits')}
          >
            Direct Debits
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'gmail-merchants' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('gmail-merchants')}
          >
            Gmail
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'gmail-llm-queue' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('gmail-llm-queue')}
          >
            LLM Queue
          </button>
          <button
            role="tab"
            className={`tab ${activeTab === 'theme' ? 'tab-active' : ''}`}
            onClick={() => handleTabChange('theme')}
          >
            Theme
          </button>
        </div>
      </div>
    </div>
  );
}
