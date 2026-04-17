/**
 * ScreeningHistory.test.tsx — component tests for the screening history timeline.
 *
 * Tests:
 *   - Loading state (aria-busy + SkeletonList)
 *   - Renders timeline entries after data loads
 *   - Score badges render with correct values
 *   - Clicking an entry calls onViewScreening
 *   - Empty state when no screenings exist
 *   - Error state on API failure
 *   - Trend indicator when multiple screenings present
 *
 * Data is served by the MSW handler for
 * GET /api/patients/:id/cognitive-screenings
 * which returns [makeCognitiveScreening()] by default.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { ScreeningHistory } from '../../src/components/ScreeningHistory'
import { makeCognitiveScreening } from '../factories'

const PATIENT_ID = 'patient-1'

function renderHistory(onViewScreening = vi.fn()) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return {
    onViewScreening,
    ...render(
      <ScreeningHistory
        patientId={PATIENT_ID}
        onViewScreening={onViewScreening}
      />,
    ),
  }
}

describe('ScreeningHistory', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('shows loading state initially (aria-busy)', () => {
    renderHistory()
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument()
  })

  it('renders a SkeletonList while loading', () => {
    renderHistory()
    // SkeletonList renders multiple skeleton lines with class ada-skeleton--line
    expect(document.querySelector('.ada-skeleton--line')).toBeInTheDocument()
  })

  it('renders screening entry after data loads', async () => {
    renderHistory()
    await waitFor(() => {
      expect(screen.getByTestId('screening-entry-0')).toBeInTheDocument()
    })
  })

  it('renders score badge with correct percentage', async () => {
    server.use(
      http.get('/api/patients/:patientId/cognitive-screenings', () =>
        HttpResponse.json([makeCognitiveScreening({ overall_score: 0.85 })]),
      ),
    )
    renderHistory()
    await waitFor(() => {
      expect(screen.getByTestId('score-badge')).toHaveTextContent('85')
    })
  })

  it('clicking an entry calls onViewScreening with screening id', async () => {
    const user = userEvent.setup()
    server.use(
      http.get('/api/patients/:patientId/cognitive-screenings', () =>
        HttpResponse.json([makeCognitiveScreening({ id: 'screening-abc' })]),
      ),
    )
    const { onViewScreening } = renderHistory()

    await waitFor(() => {
      expect(screen.getByTestId('screening-entry-0')).toBeInTheDocument()
    })

    await user.click(screen.getByTestId('screening-entry-0'))
    expect(onViewScreening).toHaveBeenCalledWith('screening-abc')
  })

  it('shows empty state when no screenings exist', async () => {
    server.use(
      http.get('/api/patients/:patientId/cognitive-screenings', () =>
        HttpResponse.json([]),
      ),
    )
    renderHistory()
    await waitFor(() => {
      expect(screen.getByText('No past screenings')).toBeInTheDocument()
    })
  })

  it('shows error state when API fails', async () => {
    server.use(
      http.get('/api/patients/:patientId/cognitive-screenings', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    renderHistory()
    await waitFor(() => {
      // ErrorState uses role="status"
      expect(screen.getByRole('status', { name: /Error state/i })).toBeInTheDocument()
    })
  })

  it('renders trend indicator when two or more screenings exist', async () => {
    server.use(
      http.get('/api/patients/:patientId/cognitive-screenings', () =>
        HttpResponse.json([
          makeCognitiveScreening({ overall_score: 0.85, started_at: '2026-02-01T10:00:00Z' }),
          makeCognitiveScreening({ overall_score: 0.72, started_at: '2026-01-15T10:00:00Z' }),
        ]),
      ),
    )
    renderHistory()
    await waitFor(() => {
      expect(screen.getByTestId('trend-indicator')).toBeInTheDocument()
    })
  })
})
