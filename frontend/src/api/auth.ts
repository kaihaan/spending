/**
 * Authentication API Client
 *
 * Provides typed API methods for all authentication operations.
 * Uses axios with credentials: 'include' for Flask-Login session cookies.
 */

import axios from 'axios';

const API_URL = 'http://localhost:5000/api/auth';

// Configure axios to include credentials (session cookies) with every request
const authClient = axios.create({
  baseURL: API_URL,
  withCredentials: true, // CRITICAL: Required for Flask-Login cookies
  headers: {
    'Content-Type': 'application/json',
  },
});

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface User {
  id: number;
  username: string;
  email: string;
  is_admin: boolean;
  last_login_at?: string;
  created_at: string;
}

export interface LoginRequest {
  username: string;
  password: string;
  remember?: boolean;
}

export interface RegisterRequest {
  email: string;
  password: string;
  username?: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  password: string;
}

export interface UpdateProfileRequest {
  username?: string;
  current_password?: string;
  new_password?: string;
}

export interface AuthResponse {
  success: boolean;
  user?: User;
  message?: string;
  error?: string;
}

export interface CheckAuthResponse {
  authenticated: boolean;
  user?: User;
}

// ============================================================================
// API METHODS
// ============================================================================

/**
 * Login with username/email and password
 */
export const login = async (data: LoginRequest): Promise<AuthResponse> => {
  const response = await authClient.post<AuthResponse>('/login', data);
  return response.data;
};

/**
 * Register a new user account
 */
export const register = async (data: RegisterRequest): Promise<AuthResponse> => {
  const response = await authClient.post<AuthResponse>('/register', data);
  return response.data;
};

/**
 * Logout current user
 */
export const logout = async (): Promise<AuthResponse> => {
  const response = await authClient.post<AuthResponse>('/logout');
  return response.data;
};

/**
 * Get current authenticated user
 */
export const getCurrentUser = async (): Promise<User> => {
  const response = await authClient.get<User>('/me');
  return response.data;
};

/**
 * Check if user is authenticated (for initial app load)
 */
export const checkAuth = async (): Promise<CheckAuthResponse> => {
  const response = await authClient.get<CheckAuthResponse>('/check');
  return response.data;
};

/**
 * Request password reset email
 */
export const forgotPassword = async (
  data: ForgotPasswordRequest
): Promise<AuthResponse> => {
  const response = await authClient.post<AuthResponse>('/forgot-password', data);
  return response.data;
};

/**
 * Reset password using token from email
 */
export const resetPassword = async (
  data: ResetPasswordRequest
): Promise<AuthResponse> => {
  const response = await authClient.post<AuthResponse>('/reset-password', data);
  return response.data;
};

/**
 * Get user profile
 */
export const getProfile = async (): Promise<User> => {
  const response = await authClient.get<User>('/profile');
  return response.data;
};

/**
 * Update user profile (username and/or password)
 */
export const updateProfile = async (
  data: UpdateProfileRequest
): Promise<AuthResponse> => {
  const response = await authClient.put<AuthResponse>('/profile', data);
  return response.data;
};

// ============================================================================
// ERROR HANDLING HELPERS
// ============================================================================

/**
 * Extract error message from API response
 */
export const getErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    return error.response?.data?.message || error.response?.data?.error || error.message;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'An unknown error occurred';
};
