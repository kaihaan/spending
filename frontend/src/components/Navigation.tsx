import { Link, useLocation } from 'react-router-dom';
import { useState } from 'react';

interface NavLink {
  path: string;
  label: string;
  hidden?: boolean;
}

export default function Navigation() {
  const location = useLocation();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

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

      <div className="navbar-end">
        <span className="badge badge-success mr-2">Phase 2</span>
      </div>
    </div>
  );
}
