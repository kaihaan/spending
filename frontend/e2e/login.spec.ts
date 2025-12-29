/**
 * Login Page E2E Tests
 *
 * End-to-end tests for the login flow.
 * These tests run against the actual frontend and backend.
 *
 * Prerequisites:
 * - Frontend running on localhost:5173
 * - Backend running on localhost:5000
 */

import { test, expect } from '@playwright/test'

test.describe('Login Page', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to login page
    await page.goto('/login')
  })

  test('displays login form', async ({ page }) => {
    // Verify page elements are visible
    await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible()
    await expect(page.getByPlaceholder(/username or email/i)).toBeVisible()
    await expect(page.getByPlaceholder(/password/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('shows validation error for empty form', async ({ page }) => {
    // Click submit without filling form
    await page.getByRole('button', { name: /sign in/i }).click()

    // Should show validation error
    await expect(page.getByText(/please enter both/i)).toBeVisible()
  })

  test('allows typing in form fields', async ({ page }) => {
    // Type in username
    const usernameInput = page.getByPlaceholder(/username or email/i)
    await usernameInput.fill('testuser')
    await expect(usernameInput).toHaveValue('testuser')

    // Type in password
    const passwordInput = page.getByPlaceholder(/password/i)
    await passwordInput.fill('password123')
    await expect(passwordInput).toHaveValue('password123')
  })

  test('has remember me checkbox checked by default', async ({ page }) => {
    const checkbox = page.getByRole('checkbox', { name: /remember me/i })
    await expect(checkbox).toBeChecked()
  })

  test('navigates to register page', async ({ page }) => {
    await page.getByRole('link', { name: /create one here/i }).click()
    await expect(page).toHaveURL(/\/register/)
  })

  test('navigates to forgot password page', async ({ page }) => {
    await page.getByRole('link', { name: /forgot password/i }).click()
    await expect(page).toHaveURL(/\/forgot-password/)
  })
})

test.describe('Login Flow', () => {
  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/login')

    // Fill in invalid credentials
    await page.getByPlaceholder(/username or email/i).fill('wronguser')
    await page.getByPlaceholder(/password/i).fill('wrongpassword')

    // Submit form
    await page.getByRole('button', { name: /sign in/i }).click()

    // Wait for error (from backend)
    // Note: This test requires the backend to be running
    await expect(page.getByRole('alert').or(page.getByText(/invalid|error|failed/i))).toBeVisible({
      timeout: 10000,
    })
  })
})
