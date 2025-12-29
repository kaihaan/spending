/**
 * MSW Request Handlers
 *
 * Define mock API responses for testing. These handlers intercept
 * network requests during tests and return controlled responses.
 *
 * Pattern: Add handlers grouped by API domain (auth, transactions, etc.)
 */

import { http, HttpResponse } from 'msw'

const API_URL = 'http://localhost:5000/api'

// Auth-related handlers
const authHandlers = [
  // Auth check endpoint (called on mount by AuthContext)
  http.get(`${API_URL}/auth/check`, () => {
    return HttpResponse.json({ authenticated: false })
  }),

  // Login endpoint
  http.post(`${API_URL}/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string }

    if (body.email === 'test@example.com' && body.password === 'password123') {
      return HttpResponse.json({
        user: {
          id: 1,
          email: 'test@example.com',
          username: 'testuser',
        },
      })
    }

    return HttpResponse.json({ error: 'Invalid credentials' }, { status: 401 })
  }),

  // Logout endpoint
  http.post(`${API_URL}/auth/logout`, () => {
    return HttpResponse.json({ message: 'Logged out successfully' })
  }),

  // Session check endpoint
  http.get(`${API_URL}/auth/session`, () => {
    return HttpResponse.json({ authenticated: false })
  }),

  // Register endpoint
  http.post(`${API_URL}/auth/register`, async ({ request }) => {
    const body = (await request.json()) as {
      email?: string
      password?: string
      username?: string
    }

    if (!body.email || !body.password || !body.username) {
      return HttpResponse.json({ error: 'Missing required fields' }, { status: 400 })
    }

    return HttpResponse.json(
      {
        user: {
          id: 1,
          email: body.email,
          username: body.username,
        },
      },
      { status: 201 }
    )
  }),
]

// Transaction-related handlers
const transactionHandlers = [
  // Get transactions - returns Transaction[] directly (not wrapped)
  http.get(`${API_URL}/transactions`, () => {
    // Return empty array - FilterContext expects Transaction[] directly
    return HttpResponse.json([])
  }),

  // Get transaction summary
  http.get(`${API_URL}/summary`, () => {
    return HttpResponse.json({
      total_income: 0,
      total_expenses: 0,
      net: 0,
      by_category: {},
    })
  }),
]

// TrueLayer-related handlers
const trueLayerHandlers = [
  // Get connections
  http.get(`${API_URL}/truelayer/connections`, () => {
    return HttpResponse.json([])
  }),

  // Get accounts
  http.get(`${API_URL}/truelayer/accounts`, () => {
    return HttpResponse.json([])
  }),
]

// Data source stats handlers
const dataSourceHandlers = [
  // Amazon stats
  http.get(`${API_URL}/amazon/stats`, () => {
    return HttpResponse.json({
      total_orders: 0,
      matched_orders: 0,
      unmatched_orders: 0,
      min_order_date: null,
      max_order_date: null,
    })
  }),

  // Apple stats
  http.get(`${API_URL}/apple/stats`, () => {
    return HttpResponse.json({
      total_transactions: 0,
      matched_transactions: 0,
      unmatched_transactions: 0,
      min_transaction_date: null,
      max_transaction_date: null,
    })
  }),

  // Gmail stats
  http.get(`${API_URL}/gmail/stats`, () => {
    return HttpResponse.json({
      total_receipts: 0,
      matched_receipts: 0,
      parsed_receipts: 0,
      pending_receipts: 0,
      failed_receipts: 0,
      min_receipt_date: null,
      max_receipt_date: null,
    })
  }),
]

// Export all handlers
export const handlers = [
  ...authHandlers,
  ...transactionHandlers,
  ...trueLayerHandlers,
  ...dataSourceHandlers,
]
