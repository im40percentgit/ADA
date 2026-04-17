/**
 * DailySummaryDetail.test.tsx — component tests for the daily narrative detail viewer.
 *
 * Tests:
 *   - Loading state (aria-busy + SkeletonCard)
 *   - Renders narrative after data loads
 *   - Renders key topics as badges
 *   - Back button fires onBack callback
 *   - Error state on API failure
 *   - Empty/no-data state
 *   - Trend alerts rendered when present
 *   - Session links rendered when sessionIds prop provided
 *
 * Data is served by the MSW handler for
 * GET /api/patients/:id/daily-summaries/:date
 * which returns a fixed inline object in handlers.ts.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { DailySummaryDetail } from '../../src/components/DailySummaryDetail'

const PATIENT_ID = 'patient-1'
const DATE = '2026-01-15'

function renderDetail(props: {
  onBack?: () => void
  onViewSession?: (id: string) => void
  sessionIds?: string[]
} = {}) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  const onBack = props.onBack ?? vi.fn()
  const onViewSession = props.onViewSession ?? vi.fn()
  return {
    onBack,
    onViewSession,
    ...render(
      <DailySummaryDetail
        patientId={PATIENT_ID}
        date={DATE}
        onBack={onBack}
        onViewSession={onViewSession}
        sessionIds={props.sessionIds}
      />,
    ),
  }
}

describe('DailySummaryDetail', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('shows loading state initially (aria-busy)', () => {
    renderDetail()
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument()
  })

  it('renders a SkeletonCard while loading', () => {
    renderDetail()
    expect(document.querySelector('.ada-skeleton-card')).toBeInTheDocument()
  })

  it('renders Daily Narrative heading after data loads', async () => {
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('Daily Narrative')).toBeInTheDocument()
    })
  })

  it('renders narrative text from API', async () => {
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText(/A stable day with mild anxiety reported/i)).toBeInTheDocument()
    })
  })

  it('renders key topics as badges', async () => {
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('anxiety')).toBeInTheDocument()
      expect(screen.getByText('sleep')).toBeInTheDocument()
    })
  })

  it('back button fires onBack callback', async () => {
    const user = userEvent.setup()
    const { onBack } = renderDetail()

    await waitFor(() => {
      expect(screen.getByText('Daily Narrative')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Back'))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('shows error state when API fails', async () => {
    server.use(
      http.get('/api/patients/:patientId/daily-summaries/:date', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    )
    renderDetail()
    await waitFor(() => {
      // ErrorState uses role="status"
      expect(screen.getByRole('status', { name: /Error state/i })).toBeInTheDocument()
    })
    expect(screen.getByText(/API 404/i)).toBeInTheDocument()
  })

  it('shows empty state when API returns null', async () => {
    server.use(
      http.get('/api/patients/:patientId/daily-summaries/:date', () =>
        HttpResponse.json(null, { status: 200 }),
      ),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getByText('No summary available')).toBeInTheDocument()
    })
  })

  it('renders trend alerts when present', async () => {
    server.use(
      http.get('/api/patients/:patientId/daily-summaries/:date', () =>
        HttpResponse.json({
          id: 'summary-1',
          summary_date: DATE,
          narrative: 'Good day.',
          trend_alerts: ['improving: Sleep quality has improved'],
          appointment_prep: [],
          key_topics: [],
          overall_mood: 'positive',
          created_at: '2026-01-15T12:00:00Z',
        }),
      ),
    )
    renderDetail()
    await waitFor(() => {
      expect(screen.getAllByTestId('trend-alert').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('Trend Alerts')).toBeInTheDocument()
  })

  it('renders session links when sessionIds prop is provided', async () => {
    renderDetail({ sessionIds: ['session-abc', 'session-xyz'] })
    await waitFor(() => {
      expect(screen.getByText('View Session session-abc')).toBeInTheDocument()
      expect(screen.getByText('View Session session-xyz')).toBeInTheDocument()
    })
  })

  it('clicking a session link calls onViewSession', async () => {
    const user = userEvent.setup()
    const { onViewSession } = renderDetail({ sessionIds: ['session-abc'] })

    await waitFor(() => {
      expect(screen.getByTestId('session-link')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('session-link'))
    expect(onViewSession).toHaveBeenCalledWith('session-abc')
  })
})
