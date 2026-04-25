/**
 * LabelDayPage.test.tsx — component tests for Phase 15+ M3 admin labeling UI.
 *
 * Coverage:
 *   - Renders unlabeled rows from a mocked API (verdict date, chip, explanation)
 *   - Clicking a label button fires POST to /api/verdict/{id}/label with correct body
 *   - After labeling, the row is removed from the list
 *   - Calibration header chip renders with correct numbers
 *   - Empty state message when no unlabeled verdicts
 *   - Auto-triggers POST /api/verdict/generate with today's date on mount (DEC-VERDICT-008)
 *
 * Uses MSW to intercept HTTP calls. Real LabelDayPage logic (fetch, state) is
 * exercised end-to-end through MSW without any module-level mocks.
 *
 * @decision DEC-VERDICT-007
 * @title /admin/label-day is internal tooling — minimal UI, tested for correctness
 * @status accepted
 * @rationale Founder uses this during 21-day calibration. Tests verify the
 *     three label buttons call the correct API and the calibration header
 *     shows accurate numbers. No visual-design assertions.
 *
 * @decision DEC-VERDICT-008
 * @title auto-generate on mount is tested via captured MSW request body
 * @status accepted
 * @rationale Verifies idempotent generate fires with today's UTC date on every
 *     page load, so the founder never has to curl manually.
 */

import '@testing-library/jest-dom/vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { describe, it, expect, beforeEach, afterEach, afterAll } from 'vitest'
import { LabelDayPage } from '../LabelDayPage'

// Set up an isolated MSW server for this test file so we don't pull in
// pre-existing type-strict issues in test/msw/handlers.ts. New handlers
// are added via server.use() in each test below.
const server = setupServer()
server.listen({ onUnhandledRequest: 'error' })
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

// ---------------------------------------------------------------------------
// Test data factories
// ---------------------------------------------------------------------------

function makeVerdict(overrides: Partial<{
  id: number
  verdict_date: string
  verdict: string
  explanation: string
  dimension: string | null
  labeled_truth: string | null
}> = {}) {
  return {
    id: overrides.id ?? 1,
    patient_id: 'pat-test-001',
    verdict_date: overrides.verdict_date ?? '2026-04-24',
    verdict: overrides.verdict ?? 'OK',
    explanation: overrides.explanation ?? 'Session within normal range.',
    dimension: overrides.dimension ?? null,
    model_used: 'claude-stub',
    prompt_version: 'v1',
    telemetry_summary: { total_sessions: 1, total_duration_ms: 300000 },
    baseline_summary: 'insufficient',
    generated_at: '2026-04-24T20:00:00',
    labeled_truth: overrides.labeled_truth ?? null,
    labeled_at: null,
    labeled_by: null,
  }
}

function makeCalibration(overrides: Partial<{
  labeled_streak_days: number
  last7_false_ok_count: number
  last7_false_off_count: number
  all_unsure_no_signal_ratio: number
  gate_passed: boolean
}> = {}) {
  return {
    labeled_streak_days: overrides.labeled_streak_days ?? 5,
    labeled_streak_target: 21,
    last7_false_ok_count: overrides.last7_false_ok_count ?? 0,
    last7_false_off_count: overrides.last7_false_off_count ?? 0,
    all_unsure_no_signal_ratio: overrides.all_unsure_no_signal_ratio ?? 0.18,
    gate_passed: overrides.gate_passed ?? false,
  }
}

// ---------------------------------------------------------------------------
// MSW handler setup helpers
// ---------------------------------------------------------------------------

function setupHandlers(
  verdicts: ReturnType<typeof makeVerdict>[],
  calibration: ReturnType<typeof makeCalibration>,
) {
  server.use(
    // DEC-VERDICT-008: auto-generate endpoint — idempotent, always included
    // so existing tests don't fail on unhandled-request error.
    http.post('/api/verdict/generate', () => {
      return HttpResponse.json({ verdict: 'OK' })
    }),
    http.get('/api/verdict/unlabeled', () => {
      return HttpResponse.json(verdicts)
    }),
    http.get('/api/verdict/calibration', () => {
      return HttpResponse.json(calibration)
    }),
    http.post('/api/verdict/:id/label', async ({ params, request }) => {
      const body = await request.json() as { label: string }
      const id = Number(params.id)
      return HttpResponse.json({
        ...makeVerdict({ id }),
        labeled_truth: body.label,
        labeled_at: '2026-04-24T21:00:00',
        labeled_by: 'founder@example.com',
      })
    }),
  )
}

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderPage(patientId = 'pat-test-001') {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-token')
  return render(<LabelDayPage patientId={patientId} />)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LabelDayPage', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-token')
  })

  // ── Renders unlabeled rows ───────────────────────────────────────────────

  it('renders unlabeled verdict rows from API', async () => {
    setupHandlers(
      [
        makeVerdict({ id: 1, verdict_date: '2026-04-23', verdict: 'UNSURE' }),
        makeVerdict({ id: 2, verdict_date: '2026-04-24', verdict: 'OK' }),
      ],
      makeCalibration(),
    )

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('2026-04-23')).toBeInTheDocument()
      expect(screen.getByText('2026-04-24')).toBeInTheDocument()
    })

    // Verdict chips visible
    expect(screen.getByText('UNSURE')).toBeInTheDocument()
    expect(screen.getByText('OK')).toBeInTheDocument()
  })

  it('renders explanation text for each row', async () => {
    setupHandlers(
      [makeVerdict({ id: 1, explanation: 'Decision time 2.5 sigma above baseline.' })],
      makeCalibration(),
    )
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('Decision time 2.5 sigma above baseline.')).toBeInTheDocument()
    })
  })

  // ── Calibration header ───────────────────────────────────────────────────

  it('renders calibration header with correct numbers', async () => {
    setupHandlers(
      [],
      makeCalibration({
        labeled_streak_days: 12,
        last7_false_ok_count: 1,
        last7_false_off_count: 0,
        all_unsure_no_signal_ratio: 0.25,
        gate_passed: false,
      }),
    )
    renderPage()

    const header = await screen.findByTestId('calibration-header')
    expect(header).toHaveTextContent('12')
    expect(header).toHaveTextContent('/ 21')
    expect(header).toHaveTextContent('FP: 0')  // last7_false_off_count
    expect(header).toHaveTextContent('FN: 1')  // last7_false_ok_count
    expect(header).toHaveTextContent('25%')
  })

  it('shows gate passed indicator when gate_passed = true', async () => {
    setupHandlers([], makeCalibration({ gate_passed: true, labeled_streak_days: 21 }))
    renderPage()

    await waitFor(() => {
      expect(screen.getByTestId('calibration-header')).toHaveTextContent('Gate passed')
    })
  })

  // ── Empty state ───────────────────────────────────────────────────────────

  it('shows empty state message when no unlabeled verdicts', async () => {
    setupHandlers([], makeCalibration())
    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/no unlabeled verdicts/i)).toBeInTheDocument()
    })
  })

  // ── Label button fires correct API call ──────────────────────────────────

  it('clicking TRUTH_OK fires POST /api/verdict/{id}/label with correct body', async () => {
    const capturedBodies: unknown[] = []
    server.use(
      http.post('/api/verdict/generate', () => HttpResponse.json({ verdict: 'OK' })),
      http.get('/api/verdict/unlabeled', () =>
        HttpResponse.json([makeVerdict({ id: 42, verdict_date: '2026-04-24' })])
      ),
      http.get('/api/verdict/calibration', () => HttpResponse.json(makeCalibration())),
      http.post('/api/verdict/42/label', async ({ request }) => {
        const body = await request.json()
        capturedBodies.push(body)
        return HttpResponse.json({ ...makeVerdict({ id: 42 }), labeled_truth: 'TRUTH_OK' })
      }),
    )

    renderPage()
    await screen.findByText('2026-04-24')

    const btn = screen.getByTestId('label-btn-42-TRUTH_OK')
    await userEvent.click(btn)

    await waitFor(() => {
      expect(capturedBodies).toHaveLength(1)
      expect(capturedBodies[0]).toMatchObject({ label: 'TRUTH_OK' })
    })
  })

  it('clicking TRUTH_OFF fires POST with TRUTH_OFF body', async () => {
    const capturedBodies: unknown[] = []
    server.use(
      http.post('/api/verdict/generate', () => HttpResponse.json({ verdict: 'OK' })),
      http.get('/api/verdict/unlabeled', () =>
        HttpResponse.json([makeVerdict({ id: 7 })])
      ),
      http.get('/api/verdict/calibration', () => HttpResponse.json(makeCalibration())),
      http.post('/api/verdict/7/label', async ({ request }) => {
        const body = await request.json()
        capturedBodies.push(body)
        return HttpResponse.json({ ...makeVerdict({ id: 7 }), labeled_truth: 'TRUTH_OFF' })
      }),
    )

    renderPage()
    await screen.findByText('2026-04-24')

    await userEvent.click(screen.getByTestId('label-btn-7-TRUTH_OFF'))

    await waitFor(() => {
      expect(capturedBodies[0]).toMatchObject({ label: 'TRUTH_OFF' })
    })
  })

  // ── Row removal after labeling ────────────────────────────────────────────

  it('row disappears from list after labeling', async () => {
    server.use(
      http.post('/api/verdict/generate', () => HttpResponse.json({ verdict: 'OK' })),
      http.get('/api/verdict/unlabeled', () =>
        HttpResponse.json([makeVerdict({ id: 99, verdict_date: '2026-04-20' })])
      ),
      http.get('/api/verdict/calibration', () => HttpResponse.json(makeCalibration())),
      http.post('/api/verdict/99/label', async () =>
        HttpResponse.json({ ...makeVerdict({ id: 99 }), labeled_truth: 'TRUTH_UNSURE' })
      ),
    )

    renderPage()
    await screen.findByText('2026-04-20')

    await userEvent.click(screen.getByTestId('label-btn-99-TRUTH_UNSURE'))

    await waitFor(() => {
      expect(screen.queryByText('2026-04-20')).not.toBeInTheDocument()
    })
  })

  // ── DEC-VERDICT-009: caregiver context — "Labeling for:" header ─────────

  it('shows "Labeling for:" header when patientName is provided', async () => {
    setupHandlers([], makeCalibration())
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-token')
    render(<LabelDayPage patientId="pat-test-001" patientName="Alice Smith" />)

    await screen.findByTestId('calibration-header')
    const ctx = screen.getByTestId('label-day-patient-context')
    expect(ctx).toHaveTextContent('Labeling for:')
    expect(ctx).toHaveTextContent('Alice Smith')
  })

  it('does not render patient context header when patientName is omitted', async () => {
    setupHandlers([], makeCalibration())
    renderPage()  // no patientName

    await screen.findByTestId('calibration-header')
    expect(screen.queryByTestId('label-day-patient-context')).not.toBeInTheDocument()
  })

  // ── DEC-VERDICT-008: auto-generate on mount ──────────────────────────────

  it('auto-triggers POST /api/verdict/generate with today\'s date on mount', async () => {
    // DEC-VERDICT-008: page load must fire the idempotent generate endpoint
    // so the founder never needs a manual curl.
    const capturedBodies: unknown[] = []
    server.use(
      http.post('/api/verdict/generate', async ({ request }) => {
        capturedBodies.push(await request.json())
        return HttpResponse.json({ verdict: 'OK' })
      }),
      http.get('/api/verdict/unlabeled', () => HttpResponse.json([])),
      http.get('/api/verdict/calibration', () => HttpResponse.json(makeCalibration())),
    )

    renderPage()

    // Wait for the page to settle (generate fires before reload)
    await screen.findByTestId('calibration-header')

    expect(capturedBodies).toHaveLength(1)
    const body = capturedBodies[0] as { patient_id: string; date: string }
    expect(body.patient_id).toBe('pat-test-001')
    // date must be a YYYY-MM-DD string (UTC)
    expect(body.date).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})
