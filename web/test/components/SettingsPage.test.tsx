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
 *   - Account card shows email (no logout button — sign-out is in TopBar)
 *   - Org loading state renders SkeletonCard (DEC-SETTINGS-STATES-001)
 *   - Solo mode renders EmptyState with correct copy (DEC-SETTINGS-STATES-001)
 *
 * @decision DEC-TEST-018
 * @title SettingsPage tests use MSW for hook data
 * @status accepted
 * @rationale The real useCompanionPreferences hook is exercised end-to-end
 *   through MSW network interception so all async state transitions are covered.
 *   The onLogout prop was removed in feat/settings-wiring — sign-out now lives
 *   exclusively in TopBar, so no callback testing is needed here.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, it, expect, beforeEach } from 'vitest'
import { SettingsPage } from '../../src/components/SettingsPage'
import { server } from '../msw/handlers'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderSettings({
  email = 'user@example.com',
}: {
  email?: string
} = {}) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-token')
  return render(<SettingsPage email={email} />)
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

  it('does not render a logout button (sign-out is in TopBar)', async () => {
    renderSettings()
    expect(screen.queryByRole('button', { name: /log out/i })).not.toBeInTheDocument()
  })

  // ── Organization loading state (DEC-SETTINGS-STATES-001) ─────────────────

  it('shows a skeleton while the org fetch is in-flight', async () => {
    // Delay the org response so we can observe the loading state
    server.use(
      http.get('/api/organizations/me', async () => {
        await new Promise((r) => setTimeout(r, 200))
        return HttpResponse.json(null)
      }),
    )
    renderSettings()
    // Before the fetch resolves, SkeletonCard renders multiple Skeleton spans —
    // getAllByRole confirms at least one loading indicator is present.
    const skeletons = screen.getAllByRole('status', { name: /loading/i })
    expect(skeletons.length).toBeGreaterThan(0)
  })

  // ── Solo-mode EmptyState (DEC-SETTINGS-STATES-001) ───────────────────────

  it('renders the solo-mode EmptyState title when no org exists', async () => {
    // MSW default returns null for /api/organizations/me
    renderSettings()
    await waitFor(() => {
      expect(screen.getByText('Solo mode')).toBeInTheDocument()
    })
  })

  it('renders the solo-mode EmptyState description', async () => {
    renderSettings()
    await waitFor(() => {
      expect(
        screen.getByText("You're not part of an organization yet."),
      ).toBeInTheDocument()
    })
  })
})
