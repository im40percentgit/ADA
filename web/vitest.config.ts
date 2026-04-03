/**
 * vitest.config.ts — Vitest configuration for Ada web frontend tests.
 *
 * Uses jsdom as the test environment so React components render in a
 * browser-like DOM. Path aliases mirror vite.config.ts so test imports
 * use the same short paths as source files.
 *
 * setup.ts is loaded before every test file — it configures RTL cleanup,
 * MSW server lifecycle, and global browser API mocks (WebSocket, localStorage,
 * Notification, serviceWorker).
 *
 * @decision DEC-TEST-001
 * @title Vitest + RTL + MSW as the frontend testing stack
 * @status accepted
 * @rationale Vitest is the natural companion for a Vite project — it reuses
 *   the same transform pipeline and config conventions, avoiding a separate
 *   Jest configuration. RTL enforces accessibility-first queries (by role,
 *   label, text) rather than implementation details. MSW intercepts fetch()
 *   at the network layer so components exercise real API client code without
 *   a running backend. Together these three libraries test components exactly
 *   as users experience them.
 */

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./test/setup.ts'],
    globals: true,
    css: false,
  },
})
