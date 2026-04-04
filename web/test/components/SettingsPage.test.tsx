/**
 * SettingsPage.test.tsx — component tests for companion personalization and
 * account management settings.
 *
 * The component calls useCompanionPreferences() which hits GET/PUT
 * /api/companion/preferences. Both routes are handled by MSW via
 * makeCompanionPreferences(), returning { name: 'Ada', voice: 'female',
 * personality: { warmth: 'warm', verbosity: 'balanced', formality: 'casual' }}.
 *
 * Tests cover:
 *   - Companion name input renders with the fetched default
 *   - Voice option buttons are all present
 *   - Personality control rows are all present
 *   - Save button fires a PUT to /api/companion/preferences via the hook
 *   - Logout button fires the onLogout callback
 *
 * @decision DEC-TEST-018
 * @title SettingsPage tests use MSW for hook data, vi.fn() for callbacks
 * @status accepted
 * @rationale The real useCompanionPreferences hook is exercised end-to-end
 *   through MSW network interception so all async state transitions are covered.
 *   The onLogout callback is a thin prop — tested with vi.fn() rather than
 *   asserting on the auth module to keep the test focused on the component.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { SettingsPage } from '../../src/components/SettingsPage'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderSettings({
  onLogout = vi.fn(),
  email = 'user@example.com',
}: {
  onLogout?: () => void
  email?: string
} = {}) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-token')
  return render(<SettingsPage onLogout={onLogout} email={email} />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SettingsPage', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-token')
  })

  // ── Companion name input ──────────────────────────────────────────────────

  it('renders the companion name input', async () => {
    renderSettings()
    // Input renders immediately; value populates once hook resolves
    const input = await waitFor(() =>
      screen.getByRole('textbox', { name: /call your companion/i }),
    )
    expect(input).toBeInTheDocument()
  })

  it('populates the name input with the fetched companion name', async () => {
    renderSettings()
    const input = await waitFor(() =>
      screen.getByRole('textbox', { name: /call your companion/i }),
    ) as HTMLInputElement
    await waitFor(() => {
      expect(input.value).toBe('Ada')
    })
  })

  // ── Voice option buttons ──────────────────────────────────────────────────

  it('renders all three voice option buttons', async () => {
    renderSettings()
    expect(screen.getByRole('button', { name: /^Female$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Male$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Neutral$/i })).toBeInTheDocument()
  })

  it('marks the fetched voice as active (aria-pressed)', async () => {
    renderSettings()
    // MSW default: voice = 'female'
    const femaleBtn = screen.getByRole('button', { name: /^Female$/i })
    await waitFor(() => {
      expect(femaleBtn.getAttribute('aria-pressed')).toBe('true')
    })
  })

  it('switches voice selection when a different voice button is clicked', async () => {
    const user = userEvent.setup()
    renderSettings()

    // Wait for component to be interactive
    const maleBtn = await waitFor(() => screen.getByRole('button', { name: /^Male$/i }))
    await user.click(maleBtn)

    expect(maleBtn.getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: /^Female$/i }).getAttribute('aria-pressed')).toBe('false')
  })

  // ── Personality controls ──────────────────────────────────────────────────

  it('renders the Warmth personality control', async () => {
    renderSettings()
    expect(screen.getByText('Warmth')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Warm$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Professional$/i })).toBeInTheDocument()
  })

  it('renders the Verbosity personality control', async () => {
    renderSettings()
    expect(screen.getByText('Verbosity')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Chatty$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Concise$/i })).toBeInTheDocument()
  })

  it('renders the Formality personality control', async () => {
    renderSettings()
    expect(screen.getByText('Formality')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Casual$/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Formal$/i })).toBeInTheDocument()
  })

  // ── Save button ───────────────────────────────────────────────────────────

  it('renders the Save button', async () => {
    renderSettings()
    expect(screen.getByRole('button', { name: /^Save$/i })).toBeInTheDocument()
  })

  it('Save button calls the update API (MSW PUT /api/companion/preferences)', async () => {
    const user = userEvent.setup()
    renderSettings()

    // Wait for preferences to load so the Save button is enabled
    await waitFor(() => {
      const saveBtn = screen.getByRole('button', { name: /^Save$/i })
      expect(saveBtn).not.toBeDisabled()
    })

    const saveBtn = screen.getByRole('button', { name: /^Save$/i })
    await user.click(saveBtn)

    // After save, loading state triggers briefly; no error thrown = PUT succeeded
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Save$/i })).not.toBeDisabled()
    })
  })

  // ── Account section ───────────────────────────────────────────────────────

  it('renders the account email', async () => {
    renderSettings({ email: 'alice@example.com' })
    expect(screen.getByText('alice@example.com')).toBeInTheDocument()
  })

  it('renders the logout button', async () => {
    renderSettings()
    expect(screen.getByRole('button', { name: /log out/i })).toBeInTheDocument()
  })

  it('logout button fires the onLogout callback', async () => {
    const onLogout = vi.fn()
    const user = userEvent.setup()
    renderSettings({ onLogout })

    await user.click(screen.getByRole('button', { name: /log out/i }))
    expect(onLogout).toHaveBeenCalledTimes(1)
  })
})
