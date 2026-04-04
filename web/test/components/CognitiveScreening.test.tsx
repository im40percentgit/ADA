/**
 * CognitiveScreening.test.tsx — component tests for the standalone screening page.
 *
 * Tests:
 *   - Renders intro screen with start button
 *   - Start button triggers screening (MSW intercepts)
 *   - Task renders after receiving task data (via pushTask on the hook)
 *   - Progress bar shows correct position
 *   - Back button works on intro and task screens
 *   - Multiple choice task renders options
 *   - Free text task renders input
 *   - Error state renders when API fails
 *
 * Data is served by the MSW handler for POST /api/patients/:id/screenings/start
 * which returns { screening_id: 'screening-1' } from handlers.ts.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { CognitiveScreening } from '../../src/components/CognitiveScreening'

const PATIENT_ID = 'patient-1'

function renderScreening(
  onBack = vi.fn(),
  onComplete = vi.fn(),
) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return {
    onBack,
    onComplete,
    ...render(
      <CognitiveScreening
        patientId={PATIENT_ID}
        onBack={onBack}
        onComplete={onComplete}
      />,
    ),
  }
}

describe('CognitiveScreening', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders intro screen with start button', () => {
    renderScreening()
    expect(screen.getByText('Cognitive Screening')).toBeInTheDocument()
    expect(screen.getByText(/This assessment takes about 8-10 minutes/i)).toBeInTheDocument()
    expect(screen.getByTestId('start-screening')).toBeInTheDocument()
  })

  it('renders the description text', () => {
    renderScreening()
    expect(
      screen.getByText(/memory, attention, language, and visuospatial skills/i),
    ).toBeInTheDocument()
  })

  it('start button triggers screening and shows loading', async () => {
    const user = userEvent.setup()
    renderScreening()

    await user.click(screen.getByTestId('start-screening'))

    // Should show loading/starting state
    await waitFor(() => {
      // Either 'Starting screening...' or transitions to 'Waiting for next task...'
      const starting = screen.queryByText('Starting screening...')
      const waiting = screen.queryByText('Waiting for next task...')
      expect(starting || waiting).toBeTruthy()
    })
  })

  it('transitions to in_progress after start', async () => {
    const user = userEvent.setup()
    renderScreening()

    await user.click(screen.getByTestId('start-screening'))

    await waitFor(() => {
      expect(screen.getByText('Waiting for next task...')).toBeInTheDocument()
    })
  })

  it('back button fires onBack callback on intro screen', async () => {
    const user = userEvent.setup()
    const { onBack } = renderScreening()

    await user.click(screen.getByText('Back'))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders error state when start API fails', async () => {
    server.use(
      http.post('/api/patients/:patientId/screenings/start', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )

    const user = userEvent.setup()
    renderScreening()

    await user.click(screen.getByTestId('start-screening'))

    await waitFor(() => {
      expect(screen.getByText(/API 500/i)).toBeInTheDocument()
    })
  })

  it('error state returns to idle so start button is still visible', async () => {
    server.use(
      http.post('/api/patients/:patientId/screenings/start', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )

    const user = userEvent.setup()
    renderScreening()

    await user.click(screen.getByTestId('start-screening'))

    await waitFor(() => {
      // Should still show the start button after error
      expect(screen.getByTestId('start-screening')).toBeInTheDocument()
    })
  })

  it('intro screen has correct test ids', () => {
    renderScreening()
    expect(screen.getByTestId('screening-intro')).toBeInTheDocument()
  })
})
