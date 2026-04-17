/**
 * ProgressReport.test.tsx — component tests for the progress dashboard.
 *
 * Tests:
 *   - Renders loading state
 *   - Renders AI narrative text after data loads
 *   - Renders chart section headings
 *   - Time range buttons render and are interactive
 *   - Back button fires the onBack callback
 *   - Error state renders error message
 *
 * Data is served by the MSW handler for GET /api/patients/:id/progress-report
 * which returns makeProgressReport() from factories.ts.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { ProgressReport } from '../../src/components/ProgressReport'

const PATIENT_ID = 'patient-1'

function renderReport(onBack = vi.fn()) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return { onBack, ...render(<ProgressReport patientId={PATIENT_ID} onBack={onBack} />) }
}

describe('ProgressReport', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders loading state initially', () => {
    renderReport()
    // SkeletonCard renders multiple child skeletons with generic "Loading…" labels.
    // The loading container is identified by aria-busy="true" on its wrapper div.
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument()
  })

  it('renders AI narrative text after data loads', async () => {
    renderReport()
    await waitFor(() => {
      expect(
        screen.getByText(/Patient has shown steady improvement/i),
      ).toBeInTheDocument()
    })
  })

  it('renders the AI Narrative heading', async () => {
    renderReport()
    await waitFor(() => {
      expect(screen.getByText('AI Narrative')).toBeInTheDocument()
    })
  })

  it('renders chart section headings', async () => {
    renderReport()
    await waitFor(() => {
      expect(screen.getByText('WHO-5 Wellbeing Trend')).toBeInTheDocument()
    })
    expect(screen.getByText('Sessions per Week')).toBeInTheDocument()
    expect(screen.getByText('Emotion Distribution')).toBeInTheDocument()
    expect(screen.getByText('Medication Adherence')).toBeInTheDocument()
    expect(screen.getByText('Assessment Scores')).toBeInTheDocument()
  })

  it('renders time range buttons', async () => {
    renderReport()
    await waitFor(() => {
      expect(screen.getByText('1W')).toBeInTheDocument()
    })
    expect(screen.getByText('2W')).toBeInTheDocument()
    expect(screen.getByText('1M')).toBeInTheDocument()
    expect(screen.getByText('3M')).toBeInTheDocument()
    expect(screen.getByText('ALL')).toBeInTheDocument()
  })

  it('2W range pill is active by default', async () => {
    renderReport()
    await waitFor(() => {
      const pill = screen.getByText('2W')
      expect(pill).toHaveAttribute('aria-pressed', 'true')
    })
  })

  it('clicking a range pill marks it as active', async () => {
    const user = userEvent.setup()
    renderReport()

    await waitFor(() => {
      expect(screen.getByText('1M')).toBeInTheDocument()
    })

    await user.click(screen.getByText('1M'))

    await waitFor(() => {
      expect(screen.getByText('1M')).toHaveAttribute('aria-pressed', 'true')
    })
  })

  it('back button fires onBack callback', async () => {
    const user = userEvent.setup()
    const { onBack } = renderReport()

    await waitFor(() => {
      expect(screen.getByText('AI Narrative')).toBeInTheDocument()
    })

    await user.click(screen.getByText('Back'))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders error state when API fails', async () => {
    server.use(
      http.get('/api/patients/:patientId/progress-report', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )
    renderReport()
    await waitFor(() => {
      // ErrorState uses role="status" (polite live region), not role="alert"
      expect(screen.getByRole('status', { name: /Error state/i })).toBeInTheDocument()
    })
    expect(screen.getByText(/API 500/i)).toBeInTheDocument()
  })

  it('renders assessment score cards with correct instruments', async () => {
    renderReport()
    await waitFor(() => {
      expect(screen.getByText('PHQ-9')).toBeInTheDocument()
    })
    expect(screen.getByText('GAD-7')).toBeInTheDocument()
  })

  it('renders emotion chips', async () => {
    renderReport()
    await waitFor(() => {
      expect(screen.getByText(/neutral/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/happy/i)).toBeInTheDocument()
    expect(screen.getByText(/sad/i)).toBeInTheDocument()
  })

  it('renders missed medication dates', async () => {
    renderReport()
    await waitFor(() => {
      expect(screen.getByText('2026-01-05')).toBeInTheDocument()
    })
  })

  it('loading container has aria-busy="true"', () => {
    renderReport()
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument()
  })

  it('shows chart-area skeleton while range-change fetch is in flight', async () => {
    const user = userEvent.setup()
    renderReport()

    // Wait for initial data
    await waitFor(() => {
      expect(screen.getByText('AI Narrative')).toBeInTheDocument()
    })

    // Block the next fetch so isFetching stays true for a tick
    let resolveNext: () => void
    server.use(
      http.get('/api/patients/:patientId/progress-report', () =>
        new Promise<Response>((resolve) => {
          resolveNext = () => resolve(HttpResponse.json({ detail: 'ok' }, { status: 200 }))
        }),
      ),
    )

    await user.click(screen.getByText('1M'))

    // isFetching skeleton replaces the chart grid during the pending fetch
    await waitFor(() => {
      expect(screen.getByRole('status', { name: /Loading chart data/i })).toBeInTheDocument()
    })

    // Unblock the fetch
    resolveNext!()
  })

  it('shows empty state when API returns no data', async () => {
    server.use(
      http.get('/api/patients/:patientId/progress-report', () =>
        HttpResponse.json(null, { status: 200 }),
      ),
    )
    renderReport()
    await waitFor(() => {
      expect(screen.getByText('Nothing to report yet')).toBeInTheDocument()
    })
  })
})
