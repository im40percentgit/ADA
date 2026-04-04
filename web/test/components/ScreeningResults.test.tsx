/**
 * ScreeningResults.test.tsx — component tests for the cognitive screening detail viewer.
 *
 * Tests:
 *   - Renders loading state initially
 *   - Renders overall score after data loads
 *   - Renders domain bars for each domain
 *   - Renders clinical concerns card when concerns exist
 *   - Renders task breakdown rows
 *   - Back button fires onBack callback
 *
 * Data is served by the MSW handler for
 * GET /api/patients/:id/cognitive-screenings/:screeningId
 * which returns makeCognitiveScreening() from factories.ts.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { ScreeningResults } from '../../src/components/ScreeningResults'
import { makeCognitiveScreening } from '../factories'

const PATIENT_ID = 'patient-1'
const SCREENING_ID = 'screening-1'

function renderResults(onBack = vi.fn()) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return {
    onBack,
    ...render(
      <ScreeningResults
        patientId={PATIENT_ID}
        screeningId={SCREENING_ID}
        onBack={onBack}
      />,
    ),
  }
}

describe('ScreeningResults', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders loading state initially', () => {
    renderResults()
    expect(screen.getByText(/Loading screening results/i)).toBeInTheDocument()
  })

  it('renders overall score after data loads', async () => {
    // Default factory: overall_score = 0.77 → 77
    renderResults()
    await waitFor(() => {
      expect(screen.getByTestId('overall-score')).toBeInTheDocument()
    })
    expect(screen.getByTestId('overall-score')).toHaveTextContent('77')
  })

  it('renders domain bars for each domain', async () => {
    renderResults()
    await waitFor(() => {
      expect(screen.getAllByTestId('domain-bar').length).toBeGreaterThan(0)
    })
    // Default factory has 'memory' and 'attention' domains
    const bars = screen.getAllByTestId('domain-bar')
    expect(bars.length).toBe(2)
    expect(bars[0]).toHaveTextContent(/memory/i)
    expect(bars[1]).toHaveTextContent(/attention/i)
  })

  it('renders concerns card when concerns exist', async () => {
    server.use(
      http.get('/api/patients/:patientId/cognitive-screenings/:screeningId', () =>
        HttpResponse.json(
          makeCognitiveScreening({
            id: SCREENING_ID,
            concerns: ['Significant memory impairment', 'Attention deficit noted'],
          }),
        ),
      ),
    )

    renderResults()
    await waitFor(() => {
      expect(screen.getByTestId('concerns-card')).toBeInTheDocument()
    })
    expect(screen.getByText('Significant memory impairment')).toBeInTheDocument()
    expect(screen.getByText('Attention deficit noted')).toBeInTheDocument()
  })

  it('does not render concerns card when concerns array is empty', async () => {
    renderResults()
    await waitFor(() => {
      expect(screen.getByTestId('overall-score')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('concerns-card')).not.toBeInTheDocument()
  })

  it('renders task breakdown rows with domain badge and score', async () => {
    renderResults()
    await waitFor(() => {
      expect(screen.getAllByTestId('domain-badge').length).toBeGreaterThan(0)
    })
    // Default factory has 1 task with domain 'memory'
    expect(screen.getByTestId('domain-badge')).toHaveTextContent('memory')
    expect(screen.getByTestId('task-score')).toBeInTheDocument()
  })

  it('task row expands to show response and rationale on click', async () => {
    const user = userEvent.setup()
    renderResults()

    await waitFor(() => {
      expect(screen.getByTestId('task-row-0')).toBeInTheDocument()
    })

    // Before expand
    expect(screen.queryByText(/Response:/i)).not.toBeInTheDocument()

    await user.click(screen.getByTestId('task-row-0'))

    expect(screen.getByText(/Response:/i)).toBeInTheDocument()
    expect(screen.getByText(/Rationale:/i)).toBeInTheDocument()
  })

  it('back button fires onBack callback', async () => {
    const user = userEvent.setup()
    const { onBack } = renderResults()

    await waitFor(() => {
      expect(screen.getByTestId('overall-score')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Back'))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders error state when API fails', async () => {
    server.use(
      http.get('/api/patients/:patientId/cognitive-screenings/:screeningId', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    )
    renderResults()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
    expect(screen.getByText(/API 404/i)).toBeInTheDocument()
  })

  it('renders Clinician Notes section', async () => {
    renderResults()
    await waitFor(() => {
      expect(screen.getByText('Clinician Notes')).toBeInTheDocument()
    })
  })

  it('renders date from started_at', async () => {
    renderResults()
    await waitFor(() => {
      // Default factory started_at = '2026-01-15T10:00:00Z' → 'January 15, 2026' or similar
      expect(screen.getByText(/January 15, 2026/i)).toBeInTheDocument()
    })
  })

  it('renders task count in header', async () => {
    renderResults()
    await waitFor(() => {
      // Header paragraph: "1 tasks · 15m 0s"
      expect(screen.getAllByText(/1 tasks/i).length).toBeGreaterThan(0)
    })
  })
})
