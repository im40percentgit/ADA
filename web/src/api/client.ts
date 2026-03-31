/**
 * Ada frontend — REST + WebSocket API client
 *
 * All backend communication goes through this module. REST calls use fetch()
 * with JSON serialization. WebSocket lifecycle is managed by the useWebSocket
 * hook; this module only exports the URL builder used by that hook.
 *
 * Auth: the request() helper reads the stored access token from localStorage
 * and injects it as an Authorization: Bearer header. On a 401 response it
 * attempts a single token refresh via auth.refresh(), then retries once.
 * Auth-path requests (/api/auth/*) are never retried to avoid infinite loops.
 *
 * @decision DEC-FRONTEND-002
 * @title Thin API client with direct fetch — no axios/query library
 * @status accepted
 * @rationale Phase 1 has a small, stable endpoint surface (6 REST routes +
 *   1 WebSocket path). A thin fetch wrapper keeps the bundle small and avoids
 *   pulling in React Query or SWR before the API surface stabilises. If the
 *   endpoint count grows significantly in Phase 2, migrate to React Query.
 *
 * @decision DEC-FRONTEND-004
 * @title 401 refresh-retry in request() — single retry, auth routes excluded
 * @status accepted
 * @rationale Auto-refresh on 401 gives seamless UX for expired access tokens
 *   without requiring every call-site to handle token expiry. A single retry
 *   prevents infinite loops. Auth routes are excluded by path prefix check —
 *   if the refresh itself 401s, the error propagates to the caller (useAuth
 *   will then call logout()).
 */

import type {
  Patient,
  Session,
  Message,
  Assessment,
  MoodDataPoint,
  CreatePatientRequest,
  CreateSessionRequest,
  SubmitAssessmentRequest,
  CaregiverOverview,
  CareCircle,
  CareCircleMember,
  Board,
  BoardItem,
  Medication,
  MedicationCreate,
  MedicationUpdate,
  MedicationCreateResponse,
  Appointment,
  AppointmentCreate,
  AppointmentUpdate,
  UserLookup,
  CreateWithPatientResponse,
} from '../types'
import { getAccessToken, refresh as refreshToken } from './auth'

const BASE = '/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit, _isRetry = false): Promise<T> {
  const token = getAccessToken()
  const authHeader: Record<string, string> = token
    ? { Authorization: `Bearer ${token}` }
    : {}

  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...authHeader,
      ...init?.headers,
    },
    ...init,
  })

  // On 401, attempt a single token refresh then retry — but never for auth routes
  if (res.status === 401 && !_isRetry && !path.startsWith('/auth/')) {
    try {
      await refreshToken()
    } catch {
      // Refresh failed — propagate the original 401
      const text = await res.text().catch(() => res.statusText)
      throw new Error(`API ${res.status}: ${text}`)
    }
    return request<T>(path, init, true)
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`API ${res.status}: ${text}`)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Patients
// ---------------------------------------------------------------------------

export function listPatients(): Promise<Patient[]> {
  return request<Patient[]>('/patients')
}

export function createPatient(body: CreatePatientRequest): Promise<Patient> {
  return request<Patient>('/patients', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// Sessions
// ---------------------------------------------------------------------------

export function listSessions(patientId: string): Promise<Session[]> {
  return request<Session[]>(`/patients/${encodeURIComponent(patientId)}/sessions`)
}

export function createSession(body: CreateSessionRequest): Promise<Session> {
  return request<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function getSessionMessages(sessionId: string): Promise<Message[]> {
  return request<Message[]>(`/sessions/${encodeURIComponent(sessionId)}/messages`)
}

export function endSession(sessionId: string, moodEnd?: number): Promise<Session> {
  return request<Session>(`/sessions/${encodeURIComponent(sessionId)}/end`, {
    method: 'POST',
    body: JSON.stringify({ mood_end: moodEnd ?? null }),
  })
}

// ---------------------------------------------------------------------------
// Assessments
// ---------------------------------------------------------------------------

export function listAssessments(patientId: string): Promise<Assessment[]> {
  return request<Assessment[]>(`/patients/${encodeURIComponent(patientId)}/assessments`)
}

export function submitAssessment(body: SubmitAssessmentRequest): Promise<Assessment> {
  return request<Assessment>('/assessments', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// Mood history
// ---------------------------------------------------------------------------

export function getMoodHistory(patientId: string): Promise<MoodDataPoint[]> {
  return request<MoodDataPoint[]>(`/patients/${encodeURIComponent(patientId)}/mood-history`)
}

// ---------------------------------------------------------------------------
// Caregiver dashboard
// ---------------------------------------------------------------------------

export function getCaregiverOverview(): Promise<CaregiverOverview> {
  return request<CaregiverOverview>('/caregiver/overview')
}

// -- Care Circles -------------------------------------------------------

export function getMyCircles(): Promise<CareCircle[]> {
  return request<CareCircle[]>('/circles/my')
}

export function getCircleMembers(circleId: string): Promise<CareCircleMember[]> {
  return request<CareCircleMember[]>(`/circles/${circleId}/members`)
}

export function addCircleMember(
  circleId: string,
  body: { email: string; role: string },
): Promise<CareCircleMember> {
  return request<CareCircleMember>(`/circles/${circleId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function removeCircleMember(circleId: string, userId: string): Promise<void> {
  return request<void>(`/circles/${circleId}/members/${userId}`, {
    method: 'DELETE',
  })
}

export function getCaregiverOverviewForPatient(patientId: string): Promise<CaregiverOverview> {
  return request<CaregiverOverview>(`/caregiver/overview?patient_id=${patientId}`)
}

// -- Shared Boards ------------------------------------------------------

export function getCircleBoards(circleId: string): Promise<Board[]> {
  return request<Board[]>(`/circles/${circleId}/boards`)
}

export function createBoard(circleId: string, body: { name: string; board_type: string }): Promise<Board> {
  return request<Board>(`/circles/${circleId}/boards`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function getBoard(boardId: string): Promise<{ board: Board; items: BoardItem[] }> {
  return request<{ board: Board; items: BoardItem[] }>(`/boards/${boardId}`)
}

export function addBoardItem(boardId: string, body: { text: string; assigned_to?: string; due_date?: string }): Promise<BoardItem> {
  return request<BoardItem>(`/boards/${boardId}/items`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function updateBoardItem(boardId: string, itemId: string, body: Record<string, unknown>): Promise<BoardItem> {
  return request<BoardItem>(`/boards/${boardId}/items/${itemId}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function deleteBoardItem(boardId: string, itemId: string): Promise<void> {
  return request<void>(`/boards/${boardId}/items/${itemId}`, { method: 'DELETE' })
}

export function approveBoardItem(boardId: string, itemId: string): Promise<BoardItem> {
  return request<BoardItem>(`/boards/${boardId}/items/${itemId}/approve`, { method: 'POST' })
}

export function boardWsUrl(boardId: string): string {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${location.host}/ws/board/${boardId}`
}

// -- Medications --------------------------------------------------------

export function listMedications(patientId: string, activeOnly = false): Promise<Medication[]> {
  const params = activeOnly ? '?active_only=true' : ''
  return request<Medication[]>(`/patients/${patientId}/medications${params}`)
}

export function createMedication(patientId: string, body: MedicationCreate): Promise<MedicationCreateResponse> {
  return request<MedicationCreateResponse>(`/patients/${patientId}/medications`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateMedication(patientId: string, medId: string, body: MedicationUpdate): Promise<Medication> {
  return request<Medication>(`/patients/${patientId}/medications/${medId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deactivateMedication(patientId: string, medId: string): Promise<void> {
  return request<void>(`/patients/${patientId}/medications/${medId}`, { method: 'DELETE' })
}

// -- Appointments -------------------------------------------------------

export function listAppointments(patientId: string, status?: string): Promise<Appointment[]> {
  const params = status ? `?status=${status}` : ''
  return request<Appointment[]>(`/patients/${patientId}/appointments${params}`)
}

export function createAppointment(patientId: string, body: AppointmentCreate): Promise<Appointment> {
  return request<Appointment>(`/patients/${patientId}/appointments`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function updateAppointment(patientId: string, apptId: string, body: AppointmentUpdate): Promise<Appointment> {
  return request<Appointment>(`/patients/${patientId}/appointments/${apptId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteAppointment(patientId: string, apptId: string): Promise<void> {
  return request<void>(`/patients/${patientId}/appointments/${apptId}`, { method: 'DELETE' })
}

// -- Circle Setup -------------------------------------------------------

export function lookupUserByEmail(email: string): Promise<UserLookup> {
  return request<UserLookup>(`/circles/lookup?email=${encodeURIComponent(email)}`)
}

export function createCircleWithPatient(body: { patient_name: string; patient_email?: string }): Promise<CreateWithPatientResponse> {
  return request<CreateWithPatientResponse>('/circles/create-with-patient', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// WebSocket URL builder
// ---------------------------------------------------------------------------

/**
 * Returns the WebSocket URL for a given session.
 * Vite proxies /ws → ws://localhost:8000 in dev; in production the path
 * resolves to the same host serving the frontend.
 */
export function wsUrl(sessionId: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}/ws/chat/${sessionId}`
}
