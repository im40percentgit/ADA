/**
 * SessionSummary.test.tsx — component tests for the SOAP note detail viewer.
 *
 * Tests:
 *   - Renders loading state initially
 *   - Renders all 4 SOAP sections after data loads
 *   - Shows key topics as chips
 *   - Shows risk flags with severity styling
 *   - Back button fires onBack callback
 *   - Error state renders error message
 *   - Renders ClinicianNotes section for non-patient role
 *
 * Data is served by the MSW handler for GET /api/sessions/:id/summary
 * which returns makeSessionSummary() from factories.ts.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { SessionSummary } from '../../src/components/SessionSummary'

const SESSION_ID = 'session-1'

function renderSummary(onBack = vi.fn(), role = 'clinician') {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return { onBack, ...render(<SessionSummary sessionId={SESSION_ID} onBack={onBack} role={role} />) }
}

describe('SessionSummary', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders loading state initially', () => {
    renderSummary()
    expect(screen.getByText(/Loading session summary/i)).toBeInTheDocument()
  })

  it('renders all 4 SOAP sections after data loads', async () => {
    renderSummary()
    await waitFor(() => {
      expect(screen.getByText('Subjective')).toBeInTheDocument()
    })
    expect(screen.getByText('Objective')).toBeInTheDocument()
    expect(screen.getByText('Assessment')).toBeInTheDocument()
    expect(screen.getByText('Plan')).toBeInTheDocument()
  })

  it('renders SOAP section content', async () => {
    renderSummary()
    await waitFor(() => {
      expect(
        screen.getByText(/Patient reports feeling less anxious this week/i),
      ).toBeInTheDocument()
    })
    expect(screen.getByText(/Speech was clear, affect appropriate/i)).toBeInTheDocument()
    expect(screen.getByText(/Mild anxiety, improving trend/i)).toBeInTheDocument()
    expect(
      screen.getByText(/Continue current therapeutic approach/i),
    ).toBeInTheDocument()
  })

  it('shows key topics as chips', async () => {
    renderSummary()
    await waitFor(() => {
      expect(screen.getByText('anxiety')).toBeInTheDocument()
    })
    expect(screen.getByText('sleep')).toBeInTheDocument()
    expect(screen.getByText('work')).toBeInTheDocument()
  })

  it('shows risk flags with severity badges', async () => {
    server.use(
      http.get('/api/sessions/:sessionId/summary', () =>
        HttpResponse.json({
          session_id: SESSION_ID,
          patient_id: 'patient-1',
          subjective: 'Reports distress.',
          objective: 'Elevated anxiety noted.',
          assessment: 'High risk.',
          plan: 'Immediate follow-up.',
          key_topics: ['crisis'],
          risk_flags: ['HIGH: suicidal ideation', 'MODERATE: social withdrawal'],
          created_at: '2026-01-15T11:00:00Z',
        }),
      ),
    )

    renderSummary()
    await waitFor(() => {
      expect(screen.getByText('Risk Flags')).toBeInTheDocument()
    })

    const flags = screen.getAllByTestId('risk-flag')
    expect(flags).toHaveLength(2)
    expect(flags[0]).toHaveTextContent('HIGH: suicidal ideation')
    expect(flags[1]).toHaveTextContent('MODERATE: social withdrawal')
  })

  it('back button fires onBack callback', async () => {
    const user = userEvent.setup()
    const { onBack } = renderSummary()

    await waitFor(() => {
      expect(screen.getByText('Subjective')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Back'))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders error state when API fails', async () => {
    server.use(
      http.get('/api/sessions/:sessionId/summary', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    )
    renderSummary()
    await waitFor(() => {
      expect(screen.getByText(/API 404/i)).toBeInTheDocument()
    })
  })

  it('renders ClinicianNotes section for clinician role', async () => {
    renderSummary(vi.fn(), 'clinician')
    await waitFor(() => {
      expect(screen.getByText('Clinician Notes')).toBeInTheDocument()
    })
  })

  it('does not render ClinicianNotes for patient role', async () => {
    renderSummary(vi.fn(), 'user')
    await waitFor(() => {
      expect(screen.getByText('Subjective')).toBeInTheDocument()
    })
    expect(screen.queryByText('Clinician Notes')).not.toBeInTheDocument()
  })
})
