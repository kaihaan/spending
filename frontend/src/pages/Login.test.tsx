/**
 * Login Page Tests
 *
 * Basic rendering and form element tests for the Login page.
 * Note: Full integration tests with auth flow are better suited for E2E tests.
 */

import { describe, it, expect } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { render } from '../test/test-utils'
import Login from './Login'

describe('Login', () => {
  describe('rendering', () => {
    it('renders login form header', async () => {
      render(<Login />, { initialRoute: '/login' })

      // Wait for any async operations to complete
      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /welcome back/i })).toBeInTheDocument()
      })
    })

    it('renders username input field', async () => {
      render(<Login />, { initialRoute: '/login' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/username or email/i)).toBeInTheDocument()
      })
    })

    it('renders password input field', async () => {
      render(<Login />, { initialRoute: '/login' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/password/i)).toBeInTheDocument()
      })
    })

    it('renders sign in button', async () => {
      render(<Login />, { initialRoute: '/login' })

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
      })
    })

    it('renders forgot password link', async () => {
      render(<Login />, { initialRoute: '/login' })

      await waitFor(() => {
        expect(screen.getByRole('link', { name: /forgot password/i })).toBeInTheDocument()
      })
    })

    it('renders register link', async () => {
      render(<Login />, { initialRoute: '/login' })

      await waitFor(() => {
        expect(screen.getByRole('link', { name: /create one here/i })).toBeInTheDocument()
      })
    })
  })

  describe('form interaction', () => {
    it('allows typing in username field', async () => {
      const { user } = render(<Login />, { initialRoute: '/login' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/username or email/i)).toBeInTheDocument()
      })

      const usernameInput = screen.getByPlaceholderText(/username or email/i)
      await user.type(usernameInput, 'testuser')

      expect(usernameInput).toHaveValue('testuser')
    })

    it('allows typing in password field', async () => {
      const { user } = render(<Login />, { initialRoute: '/login' })

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/enter your password/i)).toBeInTheDocument()
      })

      const passwordInput = screen.getByPlaceholderText(/enter your password/i)
      await user.type(passwordInput, 'secretpassword')

      expect(passwordInput).toHaveValue('secretpassword')
    })
  })
})
