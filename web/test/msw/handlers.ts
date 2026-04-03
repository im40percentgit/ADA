/**
 * test/msw/handlers.ts — MSW request handlers mirroring Ada's real API.
 *
 * Handlers cover every endpoint exercised by the 6 component tests:
 *   - Auth: /api/auth/login, /api/auth/register, /api/auth/me, /api/auth/refresh
 *   - Patients: /api/patients
 *   - Sessions: /api/sessions, /api/patients/:id/sessions, /api/sessions/:id/messages
 *   - Caregiver: /api/caregiver/overview
 *   - Circles: /api/circles/my, /api/circles/:id/members, /api/circles/:id/boards
 *   - Boards: /api/boards/:id, /api/boards/:id/items, approve
 *   - Medications: /api/patients/:id/medications, medication logs
 *   - Appointments: /api/patients/:id/appointments
 *   - Alerts: /api/alerts/:id
 *   - Notifications: /api/notifications/vapid-key, subscribe
 *   - Mood: /api/patients/:id/mood-history
 *   - Assessments: /api/patients/:id/assessments, /api/assessments
 *
 * @decision DEC-TEST-011
 * @title MSW handlers mirror real API shapes using factories
 * @status accepted
 * @rationale Factories produce domain objects with sensible defaults,
 *   preventing test brittleness when shapes evolve. Every handler returns
 *   the same shape as the real backend so tests exercise real api/client.ts
 *   deserialization code. One canonical factory per domain type, overridable
 *   per test via MSW server.use() for error paths.
 */

import { http, HttpResponse, type StrictResponse } from 'msw'
import { setupServer } from 'msw/node'
import {
  makeUser,
  makePatient,
  makeSession,
  makeOverview,
  makeCircle,
  makeBoard,
  makeBoardItem,
  makeMedication,
  makeAppointment,
  makeMoodPoint,
  makeAlert,
} from '../factories'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function json<T>(data: T, status = 200): StrictResponse<T> {
  return HttpResponse.json(data, { status }) as StrictResponse<T>
}

// ---------------------------------------------------------------------------
// Handler definitions
// ---------------------------------------------------------------------------

export const handlers = [

  // -- Auth ----------------------------------------------------------------

  http.post('/api/auth/login', async ({ request }) => {
    const body = await request.json() as { email: string; password: string }
    if (body.password === 'wrong') {
      return json({ detail: 'Invalid credentials' }, 401)
    }
    return json({ access_token: 'test-access-token', refresh_token: 'test-refresh-token' })
  }),

  http.post('/api/auth/register', async ({ request }) => {
    const body = await request.json() as { email: string; password: string; role?: string }
    if (body.email === 'existing@example.com') {
      return json({ detail: 'Email already registered' }, 400)
    }
    return json(makeUser({ email: body.email, role: body.role ?? 'user' }), 201)
  }),

  http.get('/api/auth/me', ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth || !auth.startsWith('Bearer ')) {
      return json({ detail: 'Not authenticated' }, 401)
    }
    return json(makeUser())
  }),

  http.post('/api/auth/refresh', () => {
    return json({ access_token: 'test-access-token-2', refresh_token: 'test-refresh-token-2' })
  }),

  http.post('/api/auth/forgot-password', () => {
    return json({ message: 'If an account exists, a reset link has been sent' })
  }),

  http.post('/api/auth/reset-password', async ({ request }) => {
    const body = await request.json() as { token: string; new_password: string }
    if (body.token === 'invalid-token') {
      return json({ detail: 'Invalid or expired reset link' }, 400)
    }
    return json({ message: 'Password updated successfully' })
  }),

  // -- Patients ------------------------------------------------------------

  http.get('/api/patients', () => {
    return json([makePatient()])
  }),

  http.post('/api/patients', async ({ request }) => {
    const body = await request.json() as { name: string }
    return json(makePatient({ name: body.name }), 201)
  }),

  // -- Sessions ------------------------------------------------------------

  http.get('/api/patients/:patientId/sessions', () => {
    return json([makeSession()])
  }),

  http.post('/api/sessions', async ({ request }) => {
    const body = await request.json() as { patient_id: string }
    return json(makeSession({ patient_id: body.patient_id }), 201)
  }),

  http.get('/api/sessions/:sessionId/messages', () => {
    return json([])
  }),

  http.post('/api/sessions/:sessionId/end', () => {
    return json(makeSession({ ended_at: new Date().toISOString() }))
  }),

  // -- Caregiver overview --------------------------------------------------

  http.get('/api/caregiver/overview', () => {
    return json(makeOverview())
  }),

  // -- Care Circles --------------------------------------------------------

  http.get('/api/circles/my', () => {
    return json([makeCircle()])
  }),

  http.get('/api/circles/:circleId/members', () => {
    return json([
      {
        id: 'mem-1',
        user_id: 'user-caregiver-1',
        email: 'caregiver@example.com',
        role: 'primary_caregiver',
        created_at: '2026-01-01T00:00:00Z',
      },
    ])
  }),

  http.get('/api/circles/:circleId/boards', () => {
    return json([makeBoard()])
  }),

  // -- Boards --------------------------------------------------------------

  http.get('/api/boards/:boardId', ({ params }) => {
    const board = makeBoard({ id: params.boardId as string })
    return json({ board, items: [makeBoardItem({ board_id: params.boardId as string })] })
  }),

  http.post('/api/boards/:boardId/items', async ({ request, params }) => {
    const body = await request.json() as { text: string }
    return json(makeBoardItem({ board_id: params.boardId as string, text: body.text }), 201)
  }),

  http.patch('/api/boards/:boardId/items/:itemId', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeBoardItem({ id: params.itemId as string, ...body }))
  }),

  http.delete('/api/boards/:boardId/items/:itemId', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  http.post('/api/boards/:boardId/items/:itemId/approve', ({ params }) => {
    return json(makeBoardItem({ id: params.itemId as string, approved: true }))
  }),

  // -- Medications ---------------------------------------------------------

  http.get('/api/patients/:patientId/medications', () => {
    return json([makeMedication()])
  }),

  http.post('/api/patients/:patientId/medications/:medId/log', ({ params }) => {
    return json(
      {
        id: 'log-1',
        medication_id: params.medId as string,
        patient_id: params.patientId as string,
        taken_at: new Date().toISOString(),
        status: 'taken',
        created_at: new Date().toISOString(),
      },
      201,
    )
  }),

  http.get('/api/patients/:patientId/medications/:medId/logs', () => {
    return json([])
  }),

  // -- Appointments --------------------------------------------------------

  http.get('/api/patients/:patientId/appointments', () => {
    // Return a future appointment so the dashboard's upcoming filter shows it
    const futureDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
    return json([makeAppointment({ scheduled_at: futureDate })])
  }),

  http.patch('/api/patients/:patientId/appointments/:apptId', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeAppointment(body))
  }),

  // -- Crisis alerts -------------------------------------------------------

  http.patch('/api/alerts/:alertId', async ({ request, params }) => {
    const body = await request.json() as { status: string }
    return json(
      makeAlert({
        id: params.alertId as string,
        status: body.status as 'active' | 'acknowledged' | 'resolved',
      }),
    )
  }),

  // -- Mood history --------------------------------------------------------

  http.get('/api/patients/:patientId/mood-history', () => {
    return json([makeMoodPoint(), makeMoodPoint({ score: 7 })])
  }),

  // -- Assessments ---------------------------------------------------------

  http.get('/api/patients/:patientId/assessments', () => {
    return json([])
  }),

  http.post('/api/assessments', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return json(
      {
        id: 'assess-1',
        patient_id: body.patient_id,
        session_id: body.session_id,
        instrument: body.instrument,
        scores: body.scores,
        total_score: 0,
        severity: 'minimal',
        created_at: new Date().toISOString(),
      },
      201,
    )
  }),

  // -- Notifications -------------------------------------------------------

  http.get('/api/notifications/vapid-key', () => {
    return json({ public_key: '' })
  }),

  http.post('/api/notifications/subscribe', () => {
    return json({ status: 'subscribed' }, 201)
  }),

  http.delete('/api/notifications/subscribe', () => {
    return new HttpResponse(null, { status: 204 })
  }),
]

// ---------------------------------------------------------------------------
// MSW node server (used in vitest / Node environment)
// ---------------------------------------------------------------------------

export const server = setupServer(...handlers)
