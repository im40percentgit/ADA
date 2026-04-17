/**
 * AlertsCard.test.tsx — component tests for the crisis alert display card.
 *
 * AlertsCard is a pure rendering component — it takes an alerts array as props.
 * No MSW needed for empty/data tests. The updateAlertStatus API call is tested
 * via MSW for the action (acknowledge/resolve) flows.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { AlertsCard } from '../../src/components/AlertsCard'
import type { CaregiverAlert } from '../../src/types'

function makeAlert(overrides: Partial<CaregiverAlert> = {}): CaregiverAlert {
  return {
    id: 'alert-1',
    severity: 'HIGH',
    timestamp: '2026-01-01T10:00:00Z',
    escalation_action: null,
    status: 'active',
    ...overrides,
  }
}

describe('AlertsCard', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders EmptyState with "No recent alerts" when alerts list is empty', () => {
    render(<AlertsCard alerts={[]} />)
    expect(screen.getByText('No recent alerts')).toBeInTheDocument()
    // Also check the EmptyState description
    expect(screen.getByText(/Everything's quiet right now/i)).toBeInTheDocument()
  })

  it('renders severity label for a HIGH alert', () => {
    render(<AlertsCard alerts={[makeAlert({ severity: 'HIGH' })]} />)
    expect(screen.getByText('Needs Attention')).toBeInTheDocument()
  })

  it('renders acknowledge and resolve buttons for active alert', () => {
    render(<AlertsCard alerts={[makeAlert({ status: 'active' })]} />)
    expect(screen.getByRole('button', { name: /acknowledge/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resolve/i })).toBeInTheDocument()
  })

  it('shows "Acknowledged" label and only Resolve button for acknowledged alert', () => {
    render(<AlertsCard alerts={[makeAlert({ status: 'acknowledged' })]} />)
    expect(screen.getByText('Acknowledged')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /resolve/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /acknowledge/i })).not.toBeInTheDocument()
  })

  it('shows "Resolved" label with no action buttons for resolved alert', () => {
    render(<AlertsCard alerts={[makeAlert({ status: 'resolved' })]} />)
    expect(screen.getByText('Resolved')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /acknowledge/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /resolve/i })).not.toBeInTheDocument()
  })

  it('updates to acknowledged state after clicking Acknowledge', async () => {
    server.use(
      http.patch('/api/crisis-alerts/:alertId/status', () =>
        HttpResponse.json({ status: 'acknowledged' }),
      ),
    )
    const user = userEvent.setup()
    render(<AlertsCard alerts={[makeAlert({ status: 'active' })]} />)

    await user.click(screen.getByRole('button', { name: /acknowledge/i }))

    await waitFor(() => {
      expect(screen.getByText('Acknowledged')).toBeInTheDocument()
    })
  })
})
