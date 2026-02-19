/**
 * Ada frontend — REST + WebSocket API client
 *
 * All backend communication goes through this module. REST calls use fetch()
 * with JSON serialization. WebSocket lifecycle is managed by the useWebSocket
 * hook; this module only exports the URL builder used by that hook.
 *
 * @decision DEC-FRONTEND-002
 * @title Thin API client with direct fetch — no axios/query library
 * @status accepted
 * @rationale Phase 1 has a small, stable endpoint surface (6 REST routes +
 *   1 WebSocket path). A thin fetch wrapper keeps the bundle small and avoids
 *   pulling in React Query or SWR before the API surface stabilises. If the
 *   endpoint count grows significantly in Phase 2, migrate to React Query.
 */

import type {
  Patient,
  Session,
  Assessment,
  MoodDataPoint,
  CreatePatientRequest,
  CreateSessionRequest,
  SubmitAssessmentRequest,
} from '../types'

const BASE = '/api'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
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
  return request<Session[]>(`/sessions?patient_id=${encodeURIComponent(patientId)}`)
}

export function createSession(body: CreateSessionRequest): Promise<Session> {
  return request<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

// ---------------------------------------------------------------------------
// Assessments
// ---------------------------------------------------------------------------

export function listAssessments(patientId: string): Promise<Assessment[]> {
  return request<Assessment[]>(`/assessments?patient_id=${encodeURIComponent(patientId)}`)
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
  return request<MoodDataPoint[]>(`/mood-history?patient_id=${encodeURIComponent(patientId)}`)
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
