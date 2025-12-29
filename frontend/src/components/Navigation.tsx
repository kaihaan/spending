import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import BackgroundTaskIndicator from './BackgroundTaskIndicator';
import { useAuth } from '../contexts/AuthContext';

interface NavLink {
  path: string;
  label: string;
  hidden?: boolean;
}

export default function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  // Generate initials from username or email
  const getInitials = (): string => {
    if (!user) return '?';
    if (user.username) {
      // Split by space for "John Doe" → "JD", or just first char for "john"
      const parts = user.username.split(' ');
      if (parts.length > 1) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      }
      return user.username[0].toUpperCase();
    }
    // Fallback to email first char
    return user.email[0].toUpperCase();
  };

  const handleLogout = async () => {
    try {
      await logout();
      navigate('/login', { replace: true });
    } catch (err) {
      console.error('Logout failed:', err);
    }
  };

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  const navLinks = [
    { path: '/', label: 'Dashboard' },
    { path: '/transactions', label: 'Transactions' },
    { path: '/huququllah', label: 'Huququllah' },
    { path: '/settings', label: 'Settings' },
    { path: '/auth/callback', label: 'OAuth Callback', hidden: true },
  ];

  return (
    <div className="navbar bg-base-300 shadow-lg">
      <div className="navbar-start">
        <div className="dropdown">
          <label
            tabIndex={0}
            className="btn btn-ghost lg:hidden"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            Menu
          </label>
          {mobileMenuOpen && (
            <ul
              tabIndex={0}
              className="menu menu-sm dropdown-content mt-3 z-[1] p-2 shadow bg-base-200 rounded-box w-52"
              onClick={() => setMobileMenuOpen(false)}
            >
              {navLinks.filter(link => !link.hidden).map((link) => (
                <li key={link.path}>
                  <Link
                    to={link.path}
                    className={isActive(link.path) ? 'active' : ''}
                  >
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
        <Link to="/" className="btn btn-ghost text-xl">
          Personal Finance Tracker
        </Link>
      </div>

      <div className="navbar-center hidden lg:flex">
        <ul className="menu menu-horizontal px-1">
          {navLinks.filter(link => !link.hidden).map((link) => (
            <li key={link.path}>
              <Link
                to={link.path}
                className={isActive(link.path)
                  ? 'border-b-2 border-primary'
                  : 'border-b-2 border-transparent'}
              >
                {link.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <div className="navbar-end gap-2">
        <BackgroundTaskIndicator />

        {/* User Avatar Dropdown */}
        {user ? (
          <div className="dropdown dropdown-end">
            <div
              tabIndex={0}
              role="button"
              className="avatar placeholder cursor-pointer"
            >
              <div className="bg-neutral text-neutral-content w-9 rounded-full flex items-center justify-center">
                <span className="text-sm font-medium">{getInitials()}</span>
              </div>
            </div>
            <ul
              tabIndex={0}
              className="dropdown-content menu bg-base-200 rounded-box z-[1] w-52 p-2 shadow-lg mt-2"
            >
              <li className="menu-title px-2 py-1">
                <span className="text-xs text-base-content/70 truncate">
                  {user.email}
                </span>
              </li>
              <li>
                <Link to="/profile" className="justify-between">
                  Profile
                </Link>
              </li>
              <div className="divider my-1"></div>
              <li>
                <button onClick={handleLogout} className="text-error">
                  Logout
                </button>
              </li>
            </ul>
          </div>
        ) : (
          <Link to="/login" className="btn btn-sm btn-ghost">
            Login
          </Link>
        )}
      </div>
    </div>
  );
}
