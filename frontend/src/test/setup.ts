/**
 * Global test setup file for Vitest + React Testing Library
 *
 * This file runs before each test file and sets up:
 * - RTL jest-dom matchers
 * - MSW server for API mocking
 * - Global mocks (localStorage, ResizeObserver, matchMedia)
 */

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll, afterAll, vi } from 'vitest'
import { server } from './mocks/server'

// Cleanup after each test (unmount components)
afterEach(() => {
  cleanup()
})

// MSW server setup for API mocking
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
  length: 0,
  key: vi.fn(),
}
vi.stubGlobal('localStorage', localStorageMock)

// Mock ResizeObserver (used by D3 charts and some UI components)
vi.stubGlobal(
  'ResizeObserver',
  vi.fn().mockImplementation(() => ({
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  }))
)

// Mock window.matchMedia (for theme detection)
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock scrollTo (used by some components)
Object.defineProperty(window, 'scrollTo', {
  writable: true,
  value: vi.fn(),
})
