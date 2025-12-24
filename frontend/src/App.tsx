import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Navigation from './components/Navigation';
import MainLayout from './components/layouts/MainLayout';
import FilterDrawer from './components/FilterDrawer';
import SettingsTabsDrawer from './components/SettingsTabsDrawer';
import { FilterProvider } from './contexts/FilterContext';
import { useScrollVisibility } from './hooks/useScrollVisibility';
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Huququllah from './pages/Huququllah';
import Settings from './pages/Settings';
import TrueLayerCallbackHandler from './components/TrueLayerCallbackHandler';
import GmailCallbackHandler from './components/GmailCallbackHandler';

// Routes that should show the FilterDrawer
const FILTER_DRAWER_ROUTES = ['/', '/transactions', '/huququllah'];

function AppContent() {
  const location = useLocation();
  const isNavVisible = useScrollVisibility(2000);

  const showFilterDrawer = FILTER_DRAWER_ROUTES.includes(location.pathname);
  const showSettingsDrawer = location.pathname === '/settings';

  return (
    <div className="min-h-screen bg-base-100">
      {/* Sticky Nav + Filter/Settings Drawer Container */}
      <div
        className={`
          sticky top-0 z-50
          transition-transform duration-300 ease-in-out
          ${isNavVisible ? 'translate-y-0' : '-translate-y-full'}
        `}
      >
        <Navigation />
        {showFilterDrawer && <FilterDrawer />}
        {showSettingsDrawer && <SettingsTabsDrawer />}
      </div>

      <Routes>
        {/* Routes with FilterBar */}
        <Route element={<MainLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/huququllah" element={<Huququllah />} />
        </Route>
        {/* Routes without FilterBar */}
        <Route path="/settings" element={<Settings />} />
        <Route path="/auth/callback" element={<TrueLayerCallbackHandler />} />
        <Route path="/auth/gmail/callback" element={<GmailCallbackHandler />} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <FilterProvider>
      <Router>
        <AppContent />
      </Router>
    </FilterProvider>
  );
}

export default App;
