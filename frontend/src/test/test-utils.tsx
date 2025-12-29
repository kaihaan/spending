/**
 * Custom Test Utilities
 *
 * Provides a custom render function that wraps components with all
 * necessary providers (Auth, Filter, Router, etc.) for testing.
 *
 * Usage:
 *   import { render, screen } from '../test/test-utils'
 *   // or from '@testing-library/react' for basic cases
 *
 * The custom render returns the same queries as RTL plus:
 *   - user: A userEvent instance for simulating user interactions
 */

import { ReactElement, ReactNode } from 'react'
import { render as rtlRender, RenderOptions, RenderResult } from '@testing-library/react'
import { BrowserRouter, MemoryRouter } from 'react-router'
import type { MemoryRouterProps } from 'react-router'
import userEvent, { UserEvent } from '@testing-library/user-event'
import { FilterProvider } from '../contexts/FilterContext'
import { AuthProvider } from '../contexts/AuthContext'
import { BackgroundTaskProvider } from '../contexts/BackgroundTaskContext'

/**
 * Extended render result that includes userEvent
 */
interface CustomRenderResult extends RenderResult {
  user: UserEvent
}

/**
 * Custom render options
 */
interface CustomRenderOptions extends Omit<RenderOptions, 'wrapper'> {
  /**
   * Initial route for MemoryRouter (e.g., '/settings', '/transactions')
   * If not provided, BrowserRouter is used instead
   */
  initialRoute?: string

  /**
   * Additional MemoryRouter props (e.g., initialEntries)
   */
  routerProps?: Omit<MemoryRouterProps, 'children'>

  /**
   * Whether to skip auth provider wrapping (for testing auth itself)
   */
  skipAuth?: boolean
}

/**
 * All providers wrapper component
 */
function AllProviders({
  children,
  skipAuth = false,
}: {
  children: ReactNode
  skipAuth?: boolean
}) {
  // Core providers stack (inside-out order)
  const content = (
    <BackgroundTaskProvider>
      <FilterProvider>{children}</FilterProvider>
    </BackgroundTaskProvider>
  )

  // Auth provider is optional (for testing auth logic itself)
  if (skipAuth) {
    return content
  }

  return <AuthProvider>{content}</AuthProvider>
}

/**
 * Custom render function that wraps components with all providers
 *
 * @example
 * // Basic render
 * const { user } = render(<MyComponent />)
 * await user.click(screen.getByRole('button'))
 *
 * @example
 * // With initial route
 * render(<MyComponent />, { initialRoute: '/settings' })
 *
 * @example
 * // Without auth provider (for testing auth)
 * render(<LoginForm />, { skipAuth: true })
 */
function render(
  ui: ReactElement,
  options: CustomRenderOptions = {}
): CustomRenderResult {
  const {
    initialRoute,
    routerProps,
    skipAuth = false,
    ...renderOptions
  } = options

  // Choose router based on whether we need a specific route
  const Router = initialRoute ? MemoryRouter : BrowserRouter
  const routerConfig = initialRoute
    ? { initialEntries: [initialRoute], ...routerProps }
    : {}

  // Create wrapper with all providers + router
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <AllProviders skipAuth={skipAuth}>
        <Router {...routerConfig}>{children}</Router>
      </AllProviders>
    )
  }

  // Create userEvent instance with default options
  const user = userEvent.setup()

  // Render with custom wrapper
  const renderResult = rtlRender(ui, { wrapper: Wrapper, ...renderOptions })

  return {
    ...renderResult,
    user,
  }
}

/**
 * Create a render function for a specific route
 * Useful for page-level tests
 *
 * @example
 * const renderSettings = createRouteRender('/settings')
 * const { user } = renderSettings(<Settings />)
 */
function createRouteRender(route: string) {
  return (ui: ReactElement, options: Omit<CustomRenderOptions, 'initialRoute'> = {}) =>
    render(ui, { ...options, initialRoute: route })
}

// Re-export everything from RTL
export * from '@testing-library/react'

// Override render with our custom version
export { render, createRouteRender }
export type { CustomRenderOptions, CustomRenderResult }
