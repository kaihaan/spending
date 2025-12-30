/**
 * Shared API Client
 *
 * Pre-configured axios instance with credentials enabled for session-based auth.
 * All API calls should use this client instead of raw axios.
 *
 * Features:
 * - Automatic 401 handling: Dispatches 'auth-expired' event for session timeout
 * - Credentials: Includes session cookies for Flask-Login
 */

import axios from 'axios';

const API_URL = 'http://localhost:5000/api';

/**
 * Axios instance configured for authenticated API requests.
 *
 * Key settings:
 * - withCredentials: true - Required for Flask-Login session cookies
 * - Content-Type: application/json - Default for JSON APIs
 */
export const apiClient = axios.create({
  baseURL: API_URL,
  withCredentials: true, // CRITICAL: Required for session cookies
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Response interceptor for handling authentication errors.
 *
 * When a 401 response is received (session expired/invalid):
 * 1. Dispatches 'auth-expired' custom event for AuthContext to handle
 * 2. Rejects the promise so the calling code can handle the error
 *
 * This allows automatic logout and redirect to login page.
 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Dispatch custom event for AuthContext to handle
      window.dispatchEvent(new CustomEvent('auth-expired'));
    }
    return Promise.reject(error);
  }
);

// Export for convenience
export default apiClient;
