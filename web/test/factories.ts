/**
 * test/factories.ts — Test data factories for Ada domain types.
 *
 * Each factory function returns a complete, valid domain object with sensible
 * defaults. Pass a partial override to customize specific fields. All IDs use
 * sequential counters so test output is deterministic and debuggable.
 *
 * Usage:
 *   const patient = makePatient()                        // default
 *   const patient = makePatient({ name: 'Alice' })       // override
 *   const item    = makeBoardItem({ suggested_by_ada: true, approved: false })
 *
 * @decision DEC-TEST-012
 * @title Factories use sequential counters for unique IDs
 * @status accepted
 * @rationale Sequential IDs (patient-1, patient-2...) are deterministic and
 *   readable in test output. UUIDs would be opaque and vary between runs,
 *   making assertion messages harder to debug. Counters reset between test
 *   files because each file runs in its own module scope.
 */

import type {
  Patient,
  Session,
  Medication,
  Appointment,
  Board,
  BoardItem,
  CareCircle,
  MoodDataPoint,
  CaregiverOverview,
  CrisisAlertFull,
} from '../src/types'
import type { UserProfile } from '../src/api/auth'

// ---------------------------------------------------------------------------
// Counters — increment per factory call for unique IDs
// ---------------------------------------------------------------------------

let userCount = 0
let patientCount = 0
let sessionCount = 0
let boardCount = 0
let itemCount = 0
let medCount = 0
let apptCount = 0
let alertCount = 0

// ---------------------------------------------------------------------------
// User / Auth
// ---------------------------------------------------------------------------

export function makeUser(overrides: Partial<UserProfile> = {}): UserProfile {
  const n = ++userCount
  return {
    id: `user-${n}`,
    email: `user${n}@example.com`,
    role: 'user',
    patient_id: `patient-${n}`,
    created_at: '2026-01-01T00:00:00Z',
    is_active: true,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Patient
// ---------------------------------------------------------------------------

export function makePatient(overrides: Partial<Patient> = {}): Patient {
  const n = ++patientCount
  return {
    id: `patient-${n}`,
    name: `Test Patient ${n}`,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export function makeSession(overrides: Partial<Session> = {}): Session {
  const n = ++sessionCount
  return {
    id: `session-${n}`,
    patient_id: 'patient-1',
    started_at: '2026-01-01T10:00:00Z',
    ended_at: null,
    summary: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Care Circle
// ---------------------------------------------------------------------------

export function makeCircle(overrides: Partial<CareCircle> = {}): CareCircle {
  return {
    id: 'circle-1',
    patient_id: 'patient-1',
    patient_name: 'Test Patient 1',
    my_role: 'primary_caregiver',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------------

export function makeBoard(overrides: Partial<Board> = {}): Board {
  const n = ++boardCount
  return {
    id: `board-${n}`,
    care_circle_id: 'circle-1',
    name: `Test Board ${n}`,
    board_type: 'custom',
    created_by: 'user-1',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Board Item
// ---------------------------------------------------------------------------

export function makeBoardItem(overrides: Partial<BoardItem> = {}): BoardItem {
  const n = ++itemCount
  return {
    id: `item-${n}`,
    board_id: 'board-1',
    text: `Test item ${n}`,
    checked: false,
    assigned_to: null,
    due_date: null,
    position: n,
    created_by: 'user-1',
    suggested_by_ada: false,
    approved: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Medication
// ---------------------------------------------------------------------------

export function makeMedication(overrides: Partial<Medication> = {}): Medication {
  const n = ++medCount
  return {
    id: `med-${n}`,
    patient_id: 'patient-1',
    name: `Medication ${n}`,
    dosage: '10mg',
    frequency: 'daily',
    start_date: '2026-01-01',
    end_date: null,
    notes: null,
    prescribed_by: null,
    active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Appointment
// ---------------------------------------------------------------------------

export function makeAppointment(overrides: Partial<Appointment> = {}): Appointment {
  const n = ++apptCount
  // Default to a future date so upcoming-filter tests work
  const futureDate = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString()
  return {
    id: `appt-${n}`,
    patient_id: 'patient-1',
    title: `Appointment ${n}`,
    description: null,
    scheduled_at: futureDate,
    duration_minutes: 60,
    appointment_type: 'checkup',
    status: 'scheduled',
    provider_name: null,
    notes: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Mood data point
// ---------------------------------------------------------------------------

export function makeMoodPoint(overrides: Partial<MoodDataPoint> = {}): MoodDataPoint {
  return {
    date: '2026-01-01',
    score: 6,
    session_id: 'session-1',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Crisis alert (full detail)
// ---------------------------------------------------------------------------

export function makeAlert(overrides: Partial<CrisisAlertFull> = {}): CrisisAlertFull {
  const n = ++alertCount
  return {
    id: `alert-${n}`,
    patient_id: 'patient-1',
    session_id: 'session-1',
    severity: 'HIGH',
    detection_method: 'keyword',
    escalation_action: null,
    timestamp: '2026-01-01T10:00:00Z',
    status: 'active',
    resolved_at: null,
    resolved_by: null,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Caregiver overview (aggregated)
// ---------------------------------------------------------------------------

export function makeOverview(overrides: Partial<CaregiverOverview> = {}): CaregiverOverview {
  return {
    patient: {
      name: 'Test Patient 1',
      dob: null,
      emergency_contact: null,
    },
    recent_sessions: [
      {
        id: 'session-1',
        started_at: '2026-01-01T10:00:00Z',
        ended_at: '2026-01-01T11:00:00Z',
        summary: {
          subjective: 'Patient reports feeling better.',
          assessment: 'Stable mood.',
          plan: 'Continue current approach.',
          key_topics: ['sleep', 'mood'],
          risk_flags: [],
        },
      },
    ],
    crisis_alerts: [],
    assessments: {
      phq9: [],
      gad7: [],
      who5: [
        { total_score: 16, severity: 'moderate', timestamp: '2026-01-01T10:00:00Z' },
      ],
    },
    medications: [
      { name: 'Medication 1', dosage: '10mg', frequency: 'daily', active: true },
    ],
    appointments: [
      {
        title: 'Checkup',
        scheduled_at: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
        status: 'scheduled',
      },
    ],
    daily_summary: null,
    ...overrides,
  }
}
