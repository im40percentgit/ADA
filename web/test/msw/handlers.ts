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
  makeCompanionPreferences,
  makeKnowledgeNode,
  makeKnowledgeEdge,
  makeProgressReport,
  makeSessionSummary,
  makeClinicianNote,
  makeCognitiveScreening,
  makeCognitiveTaskPresented,
  makeOrganization,
  makeOrgMember,
  makeTreatmentPlan,
  makeGoal,
  makeIntervention,
  makePrescribingNote,
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

  // -- Companion Preferences (Phase 13a) -----------------------------------

  http.get('/api/companion/preferences', () => {
    return json(makeCompanionPreferences())
  }),

  http.put('/api/companion/preferences', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeCompanionPreferences(body as Partial<import('../../src/types').CompanionPreferences>))
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

  http.get('/api/notifications/preferences', () => {
    return json({
      crisis_detected: true,
      board_item_suggested: true,
      board_item_added: true,
      board_item_checked: true,
      daily_summary_generated: true,
      circle_member_added: true,
    })
  }),

  http.put('/api/notifications/preferences', async ({ request }) => {
    const body = await request.json() as Record<string, boolean>
    return json({
      crisis_detected: true,
      board_item_suggested: true,
      board_item_added: true,
      board_item_checked: true,
      daily_summary_generated: true,
      circle_member_added: true,
      ...body,
    })
  }),

  // -- Knowledge Graph (Phase 12a) -----------------------------------------

  http.get('/api/patients/:patientId/knowledge/graph', () => {
    return json({ nodes: [makeKnowledgeNode()], edges: [makeKnowledgeEdge()] })
  }),

  http.get('/api/patients/:patientId/knowledge/trends', () => {
    return json([
      { node_id: 'node-1', label: 'anxiety', current_count: 5, prior_count: 8, direction: 'improving' },
      { node_id: 'node-2', label: 'sleep', current_count: 3, prior_count: 3, direction: 'stable' },
    ])
  }),

  // -- Progress Report (Phase 12a) -----------------------------------------

  http.get('/api/patients/:patientId/progress-report', () => {
    return json(makeProgressReport())
  }),

  // -- Session Summary (Phase 12a) -----------------------------------------

  http.get('/api/sessions/:sessionId/summary', () => {
    return json(makeSessionSummary())
  }),

  // -- Daily Summaries (Phase 12a) -----------------------------------------

  http.get('/api/patients/:patientId/daily-summaries/:date', ({ params }) => {
    return json({
      id: 'summary-1',
      summary_date: params.date as string,
      narrative: 'A stable day with mild anxiety reported.',
      trend_alerts: [],
      appointment_prep: [],
      key_topics: ['anxiety', 'sleep'],
      overall_mood: 'neutral',
      created_at: '2026-01-15T12:00:00Z',
    })
  }),

  // -- Clinician Notes (Phase 12a) -----------------------------------------

  http.get('/api/notes', () => {
    return json([makeClinicianNote()])
  }),

  http.put('/api/notes', async ({ request }) => {
    const body = await request.json() as { entity_type: string; entity_id: string; content: string }
    return json(
      makeClinicianNote({
        entity_type: body.entity_type,
        entity_id: body.entity_id,
        content: body.content,
      }),
    )
  }),

  // -- Cognitive Screenings (Phase 12b) ------------------------------------

  http.post('/api/patients/:patientId/screenings/start', ({ params }) => {
    return json({ screening_id: `screening-1` }, 201)
  }),

  http.post('/api/screenings/:screeningId/respond', async ({ params }) => {
    const task = makeCognitiveTaskPresented({ screening_id: params.screeningId as string })
    return json(task)
  }),

  http.get('/api/patients/:patientId/cognitive-screenings', () => {
    return json([makeCognitiveScreening()])
  }),

  http.get('/api/patients/:patientId/cognitive-screenings/:screeningId', ({ params }) => {
    return json(makeCognitiveScreening({ id: params.screeningId as string }))
  }),

  // -- Onboarding (Phase 13b) -----------------------------------------------

  http.get('/api/onboarding/status', () => {
    return json({ status: 'not_started' })
  }),

  http.put('/api/onboarding/status', async ({ request }) => {
    const body = await request.json() as { status: string }
    return json({ status: body.status })
  }),

  // -- Organizations (Phase 14a) -------------------------------------------

  http.get('/api/organizations/me', () => {
    // Default: user has no organization (solo mode)
    return json(null)
  }),

  http.post('/api/organizations', async ({ request }) => {
    const body = await request.json() as { name: string; slug: string }
    return json(makeOrganization({ name: body.name, slug: body.slug }), 201)
  }),

  http.get('/api/organizations/:orgId', ({ params }) => {
    return json(makeOrganization({ id: params.orgId as string }))
  }),

  http.get('/api/organizations/:orgId/members', () => {
    return json([
      makeOrgMember({ role: 'owner', email: 'owner@example.com', name: 'Owner' }),
      makeOrgMember({ role: 'member', email: 'member@example.com', name: 'Member' }),
    ])
  }),

  http.post('/api/organizations/:orgId/invite', async ({ request }) => {
    const _body = await request.json() as { email: string; role: string }
    return json({ status: 'invited' }, 201)
  }),

  http.delete('/api/organizations/:orgId/members/:userId', () => {
    return new HttpResponse(null, { status: 204 })
  }),

  // -- Treatment Plans (Phase 14b) ------------------------------------------

  http.get('/api/patients/:patientId/treatment-plans', () => {
    return json([makeTreatmentPlan()])
  }),

  http.get('/api/treatment-plans/:planId', ({ params }) => {
    return json(makeTreatmentPlan({ id: params.planId as string }))
  }),

  http.post('/api/patients/:patientId/treatment-plans', async ({ request, params }) => {
    const body = await request.json() as { title: string }
    return json(
      makeTreatmentPlan({
        patient_id: params.patientId as string,
        title: body.title,
      }),
      201,
    )
  }),

  http.patch('/api/treatment-plans/:planId', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeTreatmentPlan({ id: params.planId as string, ...body as Partial<import('../../src/types').TreatmentPlan> }))
  }),

  http.post('/api/treatment-plans/:planId/goals', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeGoal(body as Partial<import('../../src/types').TreatmentGoal>), 201)
  }),

  http.patch('/api/treatment-goals/:goalId', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeGoal({ id: params.goalId as string, ...body as Partial<import('../../src/types').TreatmentGoal> }))
  }),

  http.post('/api/treatment-goals/:goalId/interventions', async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeIntervention(body as Partial<import('../../src/types').TreatmentIntervention>), 201)
  }),

  http.patch('/api/treatment-interventions/:interventionId', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return json(makeIntervention({ id: params.interventionId as string, ...body as Partial<import('../../src/types').TreatmentIntervention> }))
  }),

  // -- Prescribing Notes (Phase 14b) ----------------------------------------

  http.get('/api/patients/:patientId/prescribing-notes', () => {
    return json([makePrescribingNote()])
  }),

  http.post('/api/patients/:patientId/prescribing-notes', async ({ request, params }) => {
    const body = await request.json() as Record<string, unknown>
    return json(
      makePrescribingNote({
        patient_id: params.patientId as string,
        ...body as Partial<import('../../src/types').PrescribingNote>,
      }),
      201,
    )
  }),

  // -- Consent Records (Phase 14c) -------------------------------------------

  http.get('/api/consent', () => {
    return json([
      { id: 'consent-1', user_id: 'user-1', consent_type: 'data_collection', granted: true, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: null },
      { id: 'consent-2', user_id: 'user-1', consent_type: 'ai_analysis', granted: true, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: null },
      { id: 'consent-3', user_id: 'user-1', consent_type: 'data_sharing', granted: false, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: '2026-02-01T00:00:00Z' },
      { id: 'consent-4', user_id: 'user-1', consent_type: 'research', granted: false, version: '1.0', granted_at: '2026-01-01T00:00:00Z', revoked_at: '2026-02-01T00:00:00Z' },
    ])
  }),

  http.put('/api/consent', async ({ request }) => {
    const body = await request.json() as { consent_type: string; granted: boolean }
    return json({
      id: `consent-${body.consent_type}`,
      user_id: 'user-1',
      consent_type: body.consent_type,
      granted: body.granted,
      version: '1.0',
      granted_at: new Date().toISOString(),
      revoked_at: body.granted ? null : new Date().toISOString(),
    })
  }),

  // DEC-FRONTEND-081: LLM mode endpoint — Chat fetches this on mount for trust badge.
  // Default handler returns 'dual' so most tests see no badge. Chat.test.tsx uses
  // server.use() to override to 'claude' when testing the badge.
  http.get('/api/admin/settings/llm-mode', () => {
    return json({
      mode: 'dual',
      profiles: ['claude_opus', 'claude_sonnet', 'claude_haiku', 'offline_tier'],
      agent_mapping: {
        wellness_companion: 'claude_sonnet',
        crisis_monitor: 'claude_opus',
      },
    })
  }),
]

// ---------------------------------------------------------------------------
// MSW node server (used in vitest / Node environment)
// ---------------------------------------------------------------------------

export const server = setupServer(...handlers)
