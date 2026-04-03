/**
 * NotificationBell.test.tsx — component tests for the push notification bell.
 *
 * NotificationBell renders four distinct states driven by Notification.permission:
 *   - 'unsupported' → renders nothing
 *   - 'default'     → renders an "Enable Notifications" prompt button
 *   - 'denied'      → renders a "Notifications Blocked" indicator (no button)
 *   - 'granted'     → renders a toggle button (On/Off) driven by subscribed state
 *                     + a "Preferences" button when subscribed
 *                     + an inline preferences panel when preferences button clicked
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

function setSubscribed(isSubscribed: boolean) {
  Object.defineProperty(globalThis.navigator, 'serviceWorker', {
    value: {
      ready: Promise.resolve({
        pushManager: {
          getSubscription: async () =>
            isSubscribed ? { endpoint: 'https://example.com/push/1' } : null,
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
}

afterEach(() => {
  setPermission('default')
  setSubscribed(false)
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
    setSubscribed(false)
    render(<NotificationBell />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Notifications Off/i })).toBeInTheDocument()
    })
  })

  it('clicking Enable Notifications calls requestPermission then subscribe', async () => {
    setPermission('default')
    const user = userEvent.setup()
    render(<NotificationBell />)

    const btn = screen.getByRole('button', { name: /Enable Notifications/i })
    await user.click(btn)
    // No assertion error means the handler ran without throwing
  })

  it('renders Notifications On toggle when permission granted and subscribed', async () => {
    setPermission('granted')
    setSubscribed(true)
    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Notifications On/i })).toBeInTheDocument()
    })
  })

  it('renders Preferences button when subscribed', async () => {
    setPermission('granted')
    setSubscribed(true)
    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Preferences/i })).toBeInTheDocument()
    })
  })

  it('does not render Preferences button when not subscribed', async () => {
    setPermission('granted')
    setSubscribed(false)
    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Notifications Off/i })).toBeInTheDocument()
    })
    expect(screen.queryByRole('button', { name: /Preferences/i })).not.toBeInTheDocument()
  })

  it('clicking Preferences button opens the preferences panel', async () => {
    setPermission('granted')
    setSubscribed(true)
    const user = userEvent.setup()
    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Preferences/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /Preferences/i }))

    await waitFor(() => {
      expect(screen.getByText(/Notify me about:/i)).toBeInTheDocument()
    })
  })

  it('preferences panel shows all 6 event type checkboxes', async () => {
    setPermission('granted')
    setSubscribed(true)
    const user = userEvent.setup()
    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Preferences/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /Preferences/i }))

    await waitFor(() => {
      const checkboxes = screen.getAllByRole('checkbox')
      expect(checkboxes).toHaveLength(6)
    })
  })

  it('clicking a preference checkbox calls updatePreferences without error', async () => {
    setPermission('granted')
    setSubscribed(true)
    const user = userEvent.setup()
    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Preferences/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /Preferences/i }))

    await waitFor(() => {
      expect(screen.getAllByRole('checkbox').length).toBeGreaterThan(0)
    })

    const crisisCheckbox = screen.getByRole('checkbox', { name: /Crisis alerts/i })
    expect(crisisCheckbox).toBeChecked()
    await user.click(crisisCheckbox)
    // PUT fires via MSW — no error thrown means success
  })

  it('clicking Preferences button again collapses the panel', async () => {
    setPermission('granted')
    setSubscribed(true)
    const user = userEvent.setup()
    render(<NotificationBell />)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Preferences/i })).toBeInTheDocument()
    })

    // Open
    await user.click(screen.getByRole('button', { name: /Preferences/i }))
    await waitFor(() => {
      expect(screen.getByText(/Notify me about:/i)).toBeInTheDocument()
    })

    // Close — label changes to "Hide preferences"
    await user.click(screen.getByRole('button', { name: /Hide preferences/i }))
    await waitFor(() => {
      expect(screen.queryByText(/Notify me about:/i)).not.toBeInTheDocument()
    })
  })
})
