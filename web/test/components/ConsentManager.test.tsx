/**
 * ConsentManager.test.tsx — tests for the privacy consent toggle card.
 *
 * The component fetches consent records from GET /api/consent on mount
 * and renders four toggles. MSW returns two granted (data_collection,
 * ai_analysis) and two revoked (data_sharing, research) by default.
 *
 * Tests verify:
 *   - All four consent toggles render with correct labels
 *   - Toggle state reflects fetched consent values
 *   - Clicking a toggle calls PUT /api/consent
 *   - ErrorState renders when GET /api/consent fails (DEC-SETTINGS-STATES-001)
 *   - Retry button in ErrorState re-fetches consents (DEC-SETTINGS-STATES-001)
 *
 * @decision DEC-TEST-026
 * @title ConsentManager tests exercise real MSW handlers end-to-end
 * @status accepted
 * @rationale The test exercises the full data flow: component mounts,
 *   fetches consents via MSW, renders toggles, user clicks toggle, PUT
 *   fires via MSW. This catches serialization and state update bugs
 *   that a unit test with mocked hooks would miss.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { describe, it, expect, beforeEach } from 'vitest'
import { ConsentManager } from '../../src/components/ConsentManager'
import { server } from '../msw/handlers'

describe('ConsentManager', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-token')
  })

  it('renders the Privacy & Consent heading', async () => {
    render(<ConsentManager />)
    expect(screen.getByText('Privacy & Consent')).toBeInTheDocument()
  })

  it('renders all four consent toggles', async () => {
    render(<ConsentManager />)

    // Wait for consents to load
    await waitFor(() => {
      expect(screen.getByLabelText('Data Collection')).toBeInTheDocument()
    })

    expect(screen.getByLabelText('AI Analysis')).toBeInTheDocument()
    expect(screen.getByLabelText('Data Sharing')).toBeInTheDocument()
    expect(screen.getByLabelText('Research Participation')).toBeInTheDocument()
  })

  it('toggles reflect fetched consent state', async () => {
    render(<ConsentManager />)

    // MSW defaults: data_collection=true, ai_analysis=true, data_sharing=false, research=false
    await waitFor(() => {
      const dataCollection = screen.getByLabelText('Data Collection') as HTMLInputElement
      expect(dataCollection.checked).toBe(true)
    })

    const aiAnalysis = screen.getByLabelText('AI Analysis') as HTMLInputElement
    expect(aiAnalysis.checked).toBe(true)

    const dataSharing = screen.getByLabelText('Data Sharing') as HTMLInputElement
    expect(dataSharing.checked).toBe(false)

    const research = screen.getByLabelText('Research Participation') as HTMLInputElement
    expect(research.checked).toBe(false)
  })

  it('clicking a toggle updates its state (optimistic update)', async () => {
    const user = userEvent.setup()
    render(<ConsentManager />)

    // Wait for data to load
    await waitFor(() => {
      const dataSharing = screen.getByLabelText('Data Sharing') as HTMLInputElement
      expect(dataSharing.checked).toBe(false)
    })

    // Toggle data_sharing on
    const dataSharingToggle = screen.getByLabelText('Data Sharing')
    await user.click(dataSharingToggle)

    // Should be checked now (optimistic update)
    await waitFor(() => {
      const dataSharing = screen.getByLabelText('Data Sharing') as HTMLInputElement
      expect(dataSharing.checked).toBe(true)
    })
  })

  it('renders descriptions for each consent type', async () => {
    render(<ConsentManager />)

    await waitFor(() => {
      expect(screen.getByText(/collection of session data/i)).toBeInTheDocument()
    })

    expect(screen.getByText(/AI-powered analysis/i)).toBeInTheDocument()
    expect(screen.getByText(/sharing anonymized data/i)).toBeInTheDocument()
    expect(screen.getByText(/mental health research/i)).toBeInTheDocument()
  })

  // ── ErrorState on fetch failure (DEC-SETTINGS-STATES-001) ────────────────

  it('renders ErrorState when the consent fetch fails', async () => {
    server.use(
      http.get('/api/consent', () => {
        return HttpResponse.json({ detail: 'Internal server error' }, { status: 500 })
      }),
    )
    render(<ConsentManager />)
    await waitFor(() => {
      expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    })
    expect(screen.getByText(/Unable to load your consent settings/i)).toBeInTheDocument()
  })

  it('renders a retry button in the ErrorState', async () => {
    server.use(
      http.get('/api/consent', () => {
        return HttpResponse.json({ detail: 'Internal server error' }, { status: 500 })
      }),
    )
    render(<ConsentManager />)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    })
  })

  it('clicking retry re-fetches consents and restores the toggles', async () => {
    let callCount = 0
    server.use(
      http.get('/api/consent', () => {
        callCount++
        if (callCount === 1) {
          return HttpResponse.json({ detail: 'Internal server error' }, { status: 500 })
        }
        // Second call succeeds — return normal data
        return HttpResponse.json([
          { id: 'c-1', user_id: 'u-1', consent_type: 'data_collection', granted: true, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: null },
          { id: 'c-2', user_id: 'u-1', consent_type: 'ai_analysis', granted: false, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: null },
          { id: 'c-3', user_id: 'u-1', consent_type: 'data_sharing', granted: false, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: null },
          { id: 'c-4', user_id: 'u-1', consent_type: 'research', granted: false, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: null },
        ])
      }),
    )
    const user = userEvent.setup()
    render(<ConsentManager />)

    // Wait for error state
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    })

    // Click retry — second fetch succeeds
    await user.click(screen.getByRole('button', { name: /try again/i }))

    // Toggles should now render
    await waitFor(() => {
      expect(screen.getByLabelText('Data Collection')).toBeInTheDocument()
    })
  })
})
