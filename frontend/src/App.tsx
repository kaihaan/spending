import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import Navigation from './components/Navigation';
import MainLayout from './components/layouts/MainLayout';
import FilterDrawer from './components/FilterDrawer';
import SettingsTabsDrawer from './components/SettingsTabsDrawer';
import { FilterProvider } from './contexts/FilterContext';
import { AuthProvider } from './contexts/AuthContext';
import { BackgroundTaskProvider } from './contexts/BackgroundTaskContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { useScrollVisibility } from './hooks/useScrollVisibility';
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Huququllah from './pages/Huququllah';
import Settings from './pages/Settings';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import Profile from './pages/Profile';
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
        {/* Public Routes - No authentication required */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />

        {/* OAuth Callback Routes - Public (users might not be logged in yet) */}
        <Route path="/auth/callback" element={<TrueLayerCallbackHandler />} />
        <Route path="/auth/gmail/callback" element={<GmailCallbackHandler />} />

        {/* Protected Routes - Require authentication */}
        <Route element={<MainLayout />}>
          <Route path="/" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
          <Route path="/transactions" element={<ProtectedRoute><Transactions /></ProtectedRoute>} />
          <Route path="/huququllah" element={<ProtectedRoute><Huququllah /></ProtectedRoute>} />
        </Route>
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
      </Routes>
    </div>
  );
}

function App() {
  return (
    <AuthProvider>
      <BackgroundTaskProvider>
        <FilterProvider>
          <Router>
            <AppContent />
          </Router>
        </FilterProvider>
      </BackgroundTaskProvider>
    </AuthProvider>
  );
}

export default App;
