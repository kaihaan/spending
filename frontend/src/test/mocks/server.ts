/**
 * MSW Server Setup
 *
 * Creates the MSW server instance for intercepting network requests
 * during Node.js (Vitest) testing environment.
 *
 * The server is started/stopped in setup.ts via beforeAll/afterAll hooks.
 */

import { setupServer } from 'msw/node'
import { handlers } from './handlers'

// Create server with default handlers
export const server = setupServer(...handlers)
