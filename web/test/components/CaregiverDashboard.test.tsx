/**
 * CaregiverDashboard.test.tsx — component tests for the caregiver home view.
 *
 * # @mock-exempt: useCircles is NOT mocked — it calls GET /api/circles/my
 * # which MSW intercepts. All data flows through real hooks + MSW network layer.
 * # No internal module mocks are used in this file.
 *
 * CaregiverDashboard requires a selectedCircle to show data. MSW returns a
 * circle from GET /api/circles/my, which useCircles auto-selects. The
 * overview is then fetched from GET /api/caregiver/overview?patient_id=...
 */

import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { CaregiverDashboard } from '../../src/components/CaregiverDashboard'
import { makeOverview } from '../factories'

function renderDashboard() {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return render(<CaregiverDashboard onLogout={() => {}} />)
}

describe('CaregiverDashboard', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders dashboard header after data loads', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText('Ada Caregiver Dashboard')).toBeInTheDocument()
    })
  })

  it('displays patient name from overview', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText('Test Patient 1')).toBeInTheDocument()
    })
  })

  it('renders sign out button', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument()
    })
  })

  it('shows CircleSetupWizard when no circles exist', async () => {
    server.use(
      http.get('/api/circles/my', () => HttpResponse.json([])),
    )
    renderDashboard()
    await waitFor(() => {
      // Wizard heading — exact h2 text
      expect(screen.getByRole('heading', { name: /Set up a care circle/i })).toBeInTheDocument()
    })
  })

  it('shows error state when overview fetch fails', async () => {
    server.use(
      http.get('/api/caregiver/overview', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('shows retry button on error', async () => {
    server.use(
      http.get('/api/caregiver/overview', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
    })
  })

  it('renders No recent alerts when crisis_alerts is empty', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/No recent alerts/i)).toBeInTheDocument()
    })
  })

  it('displays crisis alert when overview contains one', async () => {
    server.use(
      http.get('/api/caregiver/overview', () =>
        HttpResponse.json(
          makeOverview({
            crisis_alerts: [
              {
                id: 'alert-test-1',
                severity: 'HIGH',
                timestamp: '2026-01-01T10:00:00Z',
                escalation_action: null,
                status: 'active',
              },
            ],
          }),
        ),
      ),
      // Also handle the query-param form used by getCaregiverOverviewForPatient
      http.get('/api/caregiver/overview', () =>
        HttpResponse.json(
          makeOverview({
            crisis_alerts: [
              {
                id: 'alert-test-1',
                severity: 'HIGH',
                timestamp: '2026-01-01T10:00:00Z',
                escalation_action: null,
                status: 'active',
              },
            ],
          }),
        ),
      ),
    )
    renderDashboard()
    // AlertsCard renders severity text in a span
    await waitFor(() => {
      // Acknowledge button only appears for active alerts
      expect(screen.getByRole('button', { name: /acknowledge/i })).toBeInTheDocument()
    })
  })

  it('renders Today\'s Summary section', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText("Today's Summary")).toBeInTheDocument()
    })
  })

  it('shows "No daily summary yet" when daily_summary is null', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/No daily summary yet/i)).toBeInTheDocument()
    })
  })
})
