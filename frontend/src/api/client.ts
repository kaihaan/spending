/**
 * Shared API Client
 *
 * Pre-configured axios instance with credentials enabled for session-based auth.
 * All API calls should use this client instead of raw axios.
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

// Export for convenience
export default apiClient;
