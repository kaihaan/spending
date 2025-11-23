import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navigation from './components/Navigation';
import Dashboard from './pages/Dashboard';
import Transactions from './pages/Transactions';
import Huququllah from './pages/Huququllah';
import Import from './pages/Import';
import Rules from './pages/Rules';
import Settings from './pages/Settings';
import TrueLayerCallbackHandler from './components/TrueLayerCallbackHandler';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-base-100">
        <Navigation />
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/huququllah" element={<Huququllah />} />
          <Route path="/import" element={<Import />} />
          <Route path="/rules" element={<Rules />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/auth/callback" element={<TrueLayerCallbackHandler />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;
