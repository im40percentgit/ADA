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
  Assessment,
  MoodDataPoint,
  CreatePatientRequest,
  CreateSessionRequest,
  SubmitAssessmentRequest,
  CaregiverOverview,
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
// Caregiver dashboard
// ---------------------------------------------------------------------------

export function getCaregiverOverview(): Promise<CaregiverOverview> {
  return request<CaregiverOverview>('/caregiver/overview')
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
