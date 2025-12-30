/**
 * Authentication Context
 *
 * Provides global authentication state and methods for the entire application.
 * Automatically checks auth status on mount and maintains session state.
 */

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import * as authApi from '../api/auth';
import type { User, LoginRequest, RegisterRequest } from '../api/auth';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface AuthContextType {
  user: User | null;
  loading: boolean;
  error: string | null;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearError: () => void;
}

interface AuthProviderProps {
  children: ReactNode;
}

// ============================================================================
// CONTEXT CREATION
// ============================================================================

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// ============================================================================
// PROVIDER COMPONENT
// ============================================================================

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /**
   * Check authentication status on mount
   * This runs once when the app loads to restore session from cookies
   */
  useEffect(() => {
    checkAuthStatus();
  }, []);

  /**
   * Listen for auth-expired events from apiClient interceptor
   * When session expires, clear user state to trigger redirect to login
   */
  useEffect(() => {
    const handleAuthExpired = () => {
      console.log('Session expired - redirecting to login');
      setUser(null);
      setError('Session expired. Please log in again.');
    };

    window.addEventListener('auth-expired', handleAuthExpired);
    return () => {
      window.removeEventListener('auth-expired', handleAuthExpired);
    };
  }, []);

  /**
   * Check if user is authenticated and load user data
   */
  const checkAuthStatus = async () => {
    try {
      setLoading(true);
      const response = await authApi.checkAuth();

      if (response.authenticated && response.user) {
        setUser(response.user);
      } else {
        setUser(null);
      }
    } catch (err) {
      console.error('Auth check failed:', err);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Login with username/password
   */
  const login = async (credentials: LoginRequest) => {
    try {
      setLoading(true);
      setError(null);

      const response = await authApi.login(credentials);

      if (response.success && response.user) {
        setUser(response.user);
      } else {
        throw new Error(response.message || response.error || 'Login failed');
      }
    } catch (err) {
      const errorMessage = authApi.getErrorMessage(err);
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Register new user account
   */
  const register = async (data: RegisterRequest) => {
    try {
      setLoading(true);
      setError(null);

      const response = await authApi.register(data);

      if (response.success && response.user) {
        setUser(response.user);
      } else {
        throw new Error(response.message || response.error || 'Registration failed');
      }
    } catch (err) {
      const errorMessage = authApi.getErrorMessage(err);
      setError(errorMessage);
      throw new Error(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Logout current user
   */
  const logout = async () => {
    try {
      setLoading(true);
      setError(null);

      await authApi.logout();
      setUser(null);
    } catch (err) {
      console.error('Logout failed:', err);
      // Clear user state even if logout API fails
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  /**
   * Refresh current user data (e.g., after profile update)
   */
  const refreshUser = async () => {
    try {
      const userData = await authApi.getCurrentUser();
      setUser(userData);
    } catch (err) {
      console.error('Failed to refresh user:', err);
      // If refresh fails, user might be logged out
      setUser(null);
    }
  };

  /**
   * Clear error message
   */
  const clearError = () => {
    setError(null);
  };

  const value: AuthContextType = {
    user,
    loading,
    error,
    login,
    register,
    logout,
    refreshUser,
    clearError,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

// ============================================================================
// CUSTOM HOOK
// ============================================================================

/**
 * Hook to access auth context
 * Throws error if used outside AuthProvider
 */
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);

  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
}
