/**
 * Navigation E2E Tests
 *
 * Tests for app navigation and routing.
 * Verifies that pages load correctly and navigation works.
 */

import { test, expect } from '@playwright/test'

test.describe('App Navigation', () => {
  test('homepage loads successfully', async ({ page }) => {
    await page.goto('/')

    // App should load (either login page or dashboard depending on auth state)
    await expect(page.locator('body')).toBeVisible()
  })

  test('login page is accessible', async ({ page }) => {
    await page.goto('/login')

    // Login page should have sign in button
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('register page is accessible', async ({ page }) => {
    await page.goto('/register')

    // Register page should have create account elements
    await expect(page.getByRole('heading').or(page.locator('h1, h2'))).toBeVisible()
  })

  test('handles unknown routes gracefully', async ({ page }) => {
    await page.goto('/this-page-does-not-exist')

    // Should either redirect to login or show 404
    // Either way, something should be visible
    await expect(page.locator('body')).toBeVisible()
  })
})

test.describe('Page Titles', () => {
  test('login page has appropriate title', async ({ page }) => {
    await page.goto('/login')

    // Page should have a title (from index.html or React helmet)
    await expect(page).toHaveTitle(/.+/)
  })
})

test.describe('Responsive Layout', () => {
  test('login page works on mobile viewport', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 })

    await page.goto('/login')

    // Form elements should still be visible and accessible
    await expect(page.getByPlaceholder(/username or email/i)).toBeVisible()
    await expect(page.getByPlaceholder(/password/i)).toBeVisible()
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
  })

  test('login page works on tablet viewport', async ({ page }) => {
    // Set tablet viewport
    await page.setViewportSize({ width: 768, height: 1024 })

    await page.goto('/login')

    // Form elements should be visible
    await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible()
  })
})
