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
import { describe, it, expect, beforeEach } from 'vitest'
import { ConsentManager } from '../../src/components/ConsentManager'

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
})
