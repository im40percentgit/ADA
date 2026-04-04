/**
 * InstallBanner.test.tsx — component tests for the PWA install prompt banner.
 *
 * InstallBanner listens for `beforeinstallprompt`, shows a banner with
 * Install and Dismiss buttons, and suppresses itself when:
 *   - The app is in standalone mode (already installed)
 *   - localStorage has 'ada_install_dismissed' = 'true'
 *   - No `beforeinstallprompt` event has fired
 *
 * We fire synthetic `beforeinstallprompt` events via window.dispatchEvent
 * and control the standalone detection by overriding window.matchMedia.
 *
 * @mock-exempt: reason The `prompt` and `userChoice` properties on the
 * `beforeinstallprompt` event are browser-native Web APIs that jsdom does
 * not implement. Synthetic versions are required so the component can call
 * deferredPrompt.prompt() and await deferredPrompt.userChoice without
 * throwing. This is an external browser boundary — the component itself
 * (InstallBanner.tsx) is exercised through its real implementation with no
 * internal mocking.
 *
 * @decision DEC-TEST-015
 * @title InstallBanner tests fire synthetic beforeinstallprompt events
 * @status accepted
 * @rationale The banner only becomes visible after the browser fires
 *   `beforeinstallprompt`. In jsdom this event never fires naturally, so
 *   tests dispatch it manually on window. The global matchMedia mock in
 *   setup.ts returns matches:false by default (not standalone), which is
 *   the correct baseline. Tests that check standalone suppression override
 *   matchMedia locally to simulate the installed state.
 */

import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { InstallBanner } from '../../src/components/InstallBanner'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Dispatch a synthetic beforeinstallprompt event with stub prompt/userChoice.
 * These stubs replace the browser-native BeforeInstallPromptEvent members
 * that jsdom cannot provide — they are external browser API boundaries.
 */
function fireInstallPrompt(promptResult: 'accepted' | 'dismissed' = 'accepted') {
  const mockPrompt = vi.fn().mockResolvedValue(undefined)
  const mockUserChoice = Promise.resolve({ outcome: promptResult })

  const event = Object.assign(new Event('beforeinstallprompt'), {
    prompt: mockPrompt,
    userChoice: mockUserChoice,
  })

  act(() => {
    window.dispatchEvent(event)
  })

  return { mockPrompt }
}

/** Override matchMedia to simulate standalone (already-installed) mode. */
function setStandalone(isStandalone: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: query.includes('standalone') ? isStandalone : false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  localStorage.clear()
  setStandalone(false)
})

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('InstallBanner', () => {
  it('renders nothing before beforeinstallprompt fires', () => {
    const { container } = render(<InstallBanner />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders banner after beforeinstallprompt fires', async () => {
    render(<InstallBanner />)
    fireInstallPrompt()

    expect(await screen.findByRole('banner', { name: /Install Ada/i })).toBeInTheDocument()
    expect(screen.getByText(/Install Ada on your device/i)).toBeInTheDocument()
  })

  it('renders Install and Dismiss buttons', async () => {
    render(<InstallBanner />)
    fireInstallPrompt()

    expect(await screen.findByRole('button', { name: /^Install$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Dismiss/i })).toBeInTheDocument()
  })

  it('clicking Install calls deferredPrompt.prompt()', async () => {
    render(<InstallBanner />)
    const { mockPrompt } = fireInstallPrompt('accepted')

    const installBtn = await screen.findByRole('button', { name: /^Install$/i })
    await userEvent.click(installBtn)

    expect(mockPrompt).toHaveBeenCalledTimes(1)
  })

  it('clicking Install hides the banner', async () => {
    render(<InstallBanner />)
    fireInstallPrompt('accepted')

    const installBtn = await screen.findByRole('button', { name: /^Install$/i })
    await userEvent.click(installBtn)

    expect(screen.queryByRole('banner', { name: /Install Ada/i })).not.toBeInTheDocument()
  })

  it('clicking Dismiss hides the banner', async () => {
    render(<InstallBanner />)
    fireInstallPrompt()

    const dismissBtn = await screen.findByRole('button', { name: /Dismiss/i })
    await userEvent.click(dismissBtn)

    expect(screen.queryByRole('banner', { name: /Install Ada/i })).not.toBeInTheDocument()
  })

  it('clicking Dismiss sets ada_install_dismissed in localStorage', async () => {
    render(<InstallBanner />)
    fireInstallPrompt()

    const dismissBtn = await screen.findByRole('button', { name: /Dismiss/i })
    await userEvent.click(dismissBtn)

    expect(localStorage.getItem('ada_install_dismissed')).toBe('true')
  })

  it('does not show banner when already dismissed in localStorage', () => {
    localStorage.setItem('ada_install_dismissed', 'true')
    render(<InstallBanner />)
    fireInstallPrompt()

    expect(screen.queryByRole('banner', { name: /Install Ada/i })).not.toBeInTheDocument()
  })

  it('does not show banner when running in standalone mode', () => {
    setStandalone(true)
    render(<InstallBanner />)
    fireInstallPrompt()

    expect(screen.queryByRole('banner', { name: /Install Ada/i })).not.toBeInTheDocument()
  })

  it('stores dismissed key when user declines the native install dialog', async () => {
    render(<InstallBanner />)
    fireInstallPrompt('dismissed')

    const installBtn = await screen.findByRole('button', { name: /^Install$/i })
    await userEvent.click(installBtn)

    expect(localStorage.getItem('ada_install_dismissed')).toBe('true')
  })
})
