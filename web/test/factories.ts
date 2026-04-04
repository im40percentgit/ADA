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
  CompanionPreferences,
  KnowledgeNode,
  KnowledgeEdge,
  ProgressReportData,
  SessionSummaryData,
  ClinicianNote,
  CognitiveTaskPresented,
  CognitiveScreening,
  Organization,
  OrganizationMember,
  TreatmentPlan,
  TreatmentGoal,
  TreatmentIntervention,
  PrescribingNote,
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
let nodeCount = 0
let edgeCount = 0
let noteCount = 0
let screeningCount = 0
let orgCount = 0
let orgMemberCount = 0
let planCount = 0
let goalCount = 0
let interventionCount = 0
let prescribingNoteCount = 0

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

// ---------------------------------------------------------------------------
// Companion Preferences (Phase 13a)
// ---------------------------------------------------------------------------

export function makeCompanionPreferences(
  overrides: Partial<CompanionPreferences> = {},
): CompanionPreferences {
  return {
    name: 'Ada',
    voice: 'female',
    personality: {
      warmth: 'warm',
      verbosity: 'balanced',
      formality: 'casual',
    },
    ...overrides,
    // Deep-merge personality if overrides include partial personality
    ...(overrides.personality
      ? {
          personality: {
            warmth: 'warm',
            verbosity: 'balanced',
            formality: 'casual',
            ...overrides.personality,
          },
        }
      : {}),
  }
}

// ---------------------------------------------------------------------------
// Knowledge Node (Phase 12a)
// ---------------------------------------------------------------------------

export function makeKnowledgeNode(overrides: Partial<KnowledgeNode> = {}): KnowledgeNode {
  const n = ++nodeCount
  return {
    id: `node-${n}`,
    patient_id: 'patient-1',
    node_type: 'symptom',
    label: `Node ${n}`,
    properties: {},
    mention_count: 3,
    confidence: 0.85,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Knowledge Edge (Phase 12a)
// ---------------------------------------------------------------------------

export function makeKnowledgeEdge(overrides: Partial<KnowledgeEdge> = {}): KnowledgeEdge {
  const n = ++edgeCount
  return {
    id: `edge-${n}`,
    patient_id: 'patient-1',
    from_node: 'node-1',
    to_node: 'node-2',
    relation: 'related_to',
    weight: 0.7,
    mention_count: 2,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Progress Report (Phase 12a)
// ---------------------------------------------------------------------------

export function makeProgressReport(overrides: Partial<ProgressReportData> = {}): ProgressReportData {
  return {
    narrative: 'Patient has shown steady improvement over the reporting period.',
    who5_trend: [
      { date: '2026-01-01', score: 12 },
      { date: '2026-01-08', score: 14 },
      { date: '2026-01-15', score: 16 },
    ],
    session_count_by_week: [
      { week: '2026-W01', count: 2 },
      { week: '2026-W02', count: 3 },
    ],
    emotion_distribution: { neutral: 0.5, happy: 0.3, sad: 0.2 },
    medication_adherence: { taken: 12, total: 14, missed_dates: ['2026-01-05'] },
    assessment_scores: {
      phq9: { current: 8, previous: 12, severity: 'mild' },
      gad7: { current: 6, previous: 9, severity: 'mild' },
    },
    flags: [],
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Session Summary (Phase 12a)
// ---------------------------------------------------------------------------

export function makeSessionSummary(overrides: Partial<SessionSummaryData> = {}): SessionSummaryData {
  return {
    session_id: 'session-1',
    patient_id: 'patient-1',
    subjective: 'Patient reports feeling less anxious this week.',
    objective: 'Speech was clear, affect appropriate.',
    assessment: 'Mild anxiety, improving trend.',
    plan: 'Continue current therapeutic approach. Review in two weeks.',
    key_topics: ['anxiety', 'sleep', 'work'],
    risk_flags: [],
    created_at: '2026-01-15T11:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Clinician Note (Phase 12a)
// ---------------------------------------------------------------------------

export function makeClinicianNote(overrides: Partial<ClinicianNote> = {}): ClinicianNote {
  const n = ++noteCount
  return {
    id: `note-${n}`,
    user_id: 'user-1',
    entity_type: 'session',
    entity_id: 'session-1',
    content: `Clinician note ${n}`,
    created_at: '2026-01-15T11:00:00Z',
    updated_at: '2026-01-15T11:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Cognitive Screening (Phase 12b)
// ---------------------------------------------------------------------------

export function makeCognitiveTaskPresented(overrides: Partial<CognitiveTaskPresented> = {}): CognitiveTaskPresented {
  return {
    screening_id: 'screening-1',
    task_index: 0,
    total_tasks: 5,
    domain: 'memory',
    task_type: 'text',
    prompt: 'Please repeat the following words: apple, table, penny',
    task_data: {},
    ...overrides,
  }
}

export function makeCognitiveScreening(overrides: Partial<CognitiveScreening> = {}): CognitiveScreening {
  const n = ++screeningCount
  return {
    id: `screening-${n}`,
    patient_id: 'patient-1',
    session_id: null,
    status: 'completed',
    domains: {
      memory: { task_count: 2, avg_score: 0.75, total_score: 1.5 },
      attention: { task_count: 1, avg_score: 0.8, total_score: 0.8 },
    },
    tasks: [
      {
        domain: 'memory',
        prompt: 'Please repeat the following words: apple, table, penny',
        response: 'apple, table, penny',
        score: 1.0,
        rationale: 'All three words recalled correctly.',
      },
    ],
    overall_score: 0.77,
    concerns: [],
    started_at: '2026-01-15T10:00:00Z',
    completed_at: '2026-01-15T10:15:00Z',
    created_at: '2026-01-15T10:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Organization (Phase 14a)
// ---------------------------------------------------------------------------

export function makeOrganization(overrides: Partial<Organization> = {}): Organization {
  const n = ++orgCount
  return {
    id: `org-${n}`,
    name: `Test Organization ${n}`,
    slug: `test-org-${n}`,
    plan: 'free',
    settings: {},
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Organization Member (Phase 14a)
// ---------------------------------------------------------------------------

export function makeOrgMember(overrides: Partial<OrganizationMember> = {}): OrganizationMember {
  const n = ++orgMemberCount
  return {
    id: `orgmem-${n}`,
    organization_id: 'org-1',
    user_id: `user-${n}`,
    role: 'member',
    email: `member${n}@example.com`,
    name: `Member ${n}`,
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Treatment Intervention (Phase 14b)
// ---------------------------------------------------------------------------

export function makeIntervention(overrides: Partial<TreatmentIntervention> = {}): TreatmentIntervention {
  const n = ++interventionCount
  return {
    id: `intervention-${n}`,
    goal_id: 'goal-1',
    description: `Intervention ${n}`,
    frequency: 'weekly',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Treatment Goal (Phase 14b)
// ---------------------------------------------------------------------------

export function makeGoal(overrides: Partial<TreatmentGoal> = {}): TreatmentGoal {
  const n = ++goalCount
  return {
    id: `goal-${n}`,
    plan_id: 'plan-1',
    description: `Goal ${n}`,
    target_metric: 'phq9',
    target_operator: '<',
    target_value: 10,
    current_value: 14,
    status: 'active',
    due_date: null,
    interventions: [makeIntervention({ goal_id: `goal-${n}` })],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Treatment Plan (Phase 14b)
// ---------------------------------------------------------------------------

export function makeTreatmentPlan(overrides: Partial<TreatmentPlan> = {}): TreatmentPlan {
  const n = ++planCount
  return {
    id: `plan-${n}`,
    patient_id: 'patient-1',
    clinician_id: 'user-1',
    organization_id: null,
    title: `Treatment Plan ${n}`,
    status: 'active',
    goals: [makeGoal({ plan_id: `plan-${n}` })],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Prescribing Note (Phase 14b)
// ---------------------------------------------------------------------------

export function makePrescribingNote(overrides: Partial<PrescribingNote> = {}): PrescribingNote {
  const n = ++prescribingNoteCount
  return {
    id: `prescribing-note-${n}`,
    patient_id: 'patient-1',
    clinician_id: 'user-1',
    medication_id: 'med-1',
    note_type: 'prescribe',
    content: `Prescribing note ${n}`,
    created_at: '2026-01-15T10:00:00Z',
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
