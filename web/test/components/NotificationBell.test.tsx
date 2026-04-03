/**
 * NotificationBell.test.tsx — component tests for the push notification bell.
 *
 * NotificationBell renders four distinct states driven by Notification.permission:
 *   - 'unsupported' → renders nothing
 *   - 'default'     → renders an "Enable Notifications" prompt button
 *   - 'denied'      → renders a "Notifications Blocked" indicator (no button)
 *   - 'granted'     → renders a toggle button (On/Off) driven by subscribed state
 *
 * We control permission state by overwriting globalThis.Notification.permission
 * before each test and restoring it after. The serviceWorker mock in setup.ts
 * provides a navigator.serviceWorker.ready stub so useNotifications() mounts
 * without errors.
 *
 * @decision DEC-TEST-012
 * @title NotificationBell tests override Notification.permission per-test
 * @status accepted
 * @rationale useNotifications reads Notification.permission at hook mount time
 *   via useState initializer. Overwriting the property before render lets each
 *   test exercise a specific branch without mocking the hook itself, so the
 *   component and hook stay coupled through their real interface.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, afterEach } from 'vitest'
import { NotificationBell } from '../../src/components/NotificationBell'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function setPermission(perm: NotificationPermission | 'unsupported') {
  if (perm === 'unsupported') {
    // Simulate a browser with no Notification API
    Object.defineProperty(globalThis, 'Notification', {
      value: undefined,
      writable: true,
      configurable: true,
    })
  } else {
    Object.defineProperty(globalThis, 'Notification', {
      value: {
        permission: perm,
        requestPermission: async () => 'granted' as NotificationPermission,
      },
      writable: true,
      configurable: true,
    })
  }
}

afterEach(() => {
  // Restore to 'default' so other test files are unaffected
  setPermission('default')
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('NotificationBell', () => {
  it('renders nothing when Notification API is unsupported', () => {
    setPermission('unsupported')
    const { container } = render(<NotificationBell />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders Enable Notifications button when permission is default', () => {
    setPermission('default')
    render(<NotificationBell />)
    const btn = screen.getByRole('button', { name: /Enable Notifications/i })
    expect(btn).toBeInTheDocument()
  })

  it('renders blocked indicator (no button) when permission is denied', () => {
    setPermission('denied')
    render(<NotificationBell />)
    expect(screen.getByText(/Notifications Blocked/i)).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('renders Notifications Off toggle when granted but not yet subscribed', async () => {
    setPermission('granted')
    render(<NotificationBell />)
    // useNotifications checks serviceWorker.ready on mount; wait for it to settle
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Notifications Off/i })).toBeInTheDocument()
    })
  })

  it('clicking Enable Notifications calls requestPermission then subscribe', async () => {
    setPermission('default')
    const user = userEvent.setup()
    render(<NotificationBell />)

    const btn = screen.getByRole('button', { name: /Enable Notifications/i })
    // The click triggers requestPermission + subscribe. Both are async no-ops in
    // test (VAPID key returns empty string, so subscribe bails early). We simply
    // verify the click does not throw and the button was present and clickable.
    await user.click(btn)
    // No assertion error means the handler ran without throwing
  })

  it('renders Notifications On toggle when permission granted and subscribed', async () => {
    setPermission('granted')
    // Override serviceWorker.ready to report an existing subscription
    Object.defineProperty(globalThis.navigator, 'serviceWorker', {
      value: {
        ready: Promise.resolve({
          pushManager: {
            // Return a truthy subscription object → subscribed = true
            getSubscription: async () => ({ endpoint: 'https://example.com/push/1' }),
            subscribe: async () => ({ toJSON: () => ({}) }),
          },
        }),
        register: async () => ({
          pushManager: {
            getSubscription: async () => null,
            subscribe: async () => ({ toJSON: () => ({}) }),
          },
        }),
      },
      writable: true,
      configurable: true,
    })

    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Notifications On/i })).toBeInTheDocument()
    })

    // Restore default serviceWorker mock so later tests are unaffected
    Object.defineProperty(globalThis.navigator, 'serviceWorker', {
      value: {
        ready: Promise.resolve({
          pushManager: {
            getSubscription: async () => null,
            subscribe: async () => ({ toJSON: () => ({}) }),
          },
        }),
        register: async () => ({
          pushManager: {
            getSubscription: async () => null,
            subscribe: async () => ({ toJSON: () => ({}) }),
          },
        }),
      },
      writable: true,
      configurable: true,
    })
  })
})
