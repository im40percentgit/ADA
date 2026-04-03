/**
 * PatientDashboard.test.tsx — component tests for the patient home view.
 *
 * PatientDashboard fetches all data via REST (MSW handles it). The useCircles
 * hook calls GET /api/circles/my — also intercepted by MSW. No hook mocking
 * needed here: all data flows through real hooks hitting the MSW network layer.
 *
 * The localStorage token is set before each test so the api/client.ts
 * Authorization header is populated (some MSW handlers check it).
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { PatientDashboard } from '../../src/components/PatientDashboard'

const PATIENT_ID = 'patient-1'

function renderDashboard(onNavigateToChat = vi.fn()) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return render(
    <PatientDashboard patientId={PATIENT_ID} onNavigateToChat={onNavigateToChat} />,
  )
}

describe('PatientDashboard', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders the Talk to Ada card', async () => {
    renderDashboard()
    expect(screen.getByRole('button', { name: /Open chat with Ada/i })).toBeInTheDocument()
    expect(screen.getByText('Talk to Ada')).toBeInTheDocument()
  })

  it('calls onNavigateToChat when Talk to Ada card is clicked', async () => {
    const onNavigateToChat = vi.fn()
    const user = userEvent.setup()
    renderDashboard(onNavigateToChat)

    await user.click(screen.getByRole('button', { name: /Open chat with Ada/i }))
    expect(onNavigateToChat).toHaveBeenCalledOnce()
  })

  it('renders Medications card heading', async () => {
    renderDashboard()
    expect(screen.getByText('Medications')).toBeInTheDocument()
  })

  it('displays medication name after loading', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/^Medication \d+$/)).toBeInTheDocument()
    })
  })

  it('shows Mark taken button for each medication', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Mark Medication \d+ as taken/i })).toBeInTheDocument()
    })
  })

  it('clicking Mark taken switches to Taken badge', async () => {
    const user = userEvent.setup()
    renderDashboard()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Mark Medication \d+ as taken/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /Mark Medication \d+ as taken/i }))

    await waitFor(() => {
      expect(screen.getByText('Taken')).toBeInTheDocument()
    })
  })

  it('renders Upcoming Appointments card heading', async () => {
    renderDashboard()
    expect(screen.getByText('Upcoming Appointments')).toBeInTheDocument()
  })

  it('displays upcoming appointment title', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/^Appointment \d+$/)).toBeInTheDocument()
    })
  })

  it('renders My Boards card — shows not part of circle when no circle', async () => {
    // Override handler: no circles
    server.use(
      http.get('/api/circles/my', () => HttpResponse.json([])),
    )
    renderDashboard()
    await waitFor(() => {
      // Both My Boards and My Care Team show this message when no circle
      const msgs = screen.getAllByText('Not part of a care circle')
      expect(msgs.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders Mood Summary card heading', async () => {
    renderDashboard()
    expect(screen.getByText('Mood Summary')).toBeInTheDocument()
  })

  it('displays mood score after loading', async () => {
    renderDashboard()
    await waitFor(() => {
      // Mood data: two points with scores 6 and 7 (from factories)
      expect(screen.getByText('7/10')).toBeInTheDocument()
    })
  })

  it('shows empty mood state when no mood history', async () => {
    server.use(
      http.get('/api/patients/:patientId/mood-history', () => HttpResponse.json([])),
    )
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/Chat with Ada to track your mood/i)).toBeInTheDocument()
    })
  })

  it('shows medications error when API fails', async () => {
    server.use(
      http.get('/api/patients/:patientId/medications', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/API 500/i)).toBeInTheDocument()
    })
  })
})
