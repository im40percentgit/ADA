/**
 * Ada frontend — shared TypeScript interfaces
 *
 * These mirror the Pydantic models from the backend (ada/models/).
 * Keep in sync when backend domain models change.
 *
 * @decision DEC-FRONTEND-001
 * @title Shared TypeScript types mirror backend Pydantic models
 * @status accepted
 * @rationale Co-locating all domain interfaces in a single types/index.ts
 *   gives components a single import point and makes backend drift visible
 *   in one place. PHQ-9 and GAD-7 question arrays are defined here (not in
 *   components) so AssessmentForm and any future consumers share the canonical
 *   question text without duplication.
 */

// ---------------------------------------------------------------------------
// Domain models
// ---------------------------------------------------------------------------

export interface Patient {
  id: string
  name: string
  created_at: string
}

export interface Session {
  id: string
  patient_id: string
  started_at: string
  ended_at: string | null
  summary: string | null
}

export interface Message {
  id: string
  session_id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  agent: string | null
}

export interface Assessment {
  id: string
  patient_id: string
  session_id: string | null
  instrument: 'phq9' | 'gad7' | 'who5'
  scores: number[]
  total_score: number
  severity: string
  created_at: string
}

export interface MoodDataPoint {
  date: string
  score: number
  session_id: string
}

// ---------------------------------------------------------------------------
// WebSocket message types (backend → frontend)
// ---------------------------------------------------------------------------

export interface WsTokenMessage {
  type: 'token'
  content: string
}

export interface WsCompleteMessage {
  type: 'message'
  content: string
  agent: string
}

export interface WsCrisisAlert {
  type: 'crisis_alert'
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  message: string
  hotline: string
}

export interface WsAssessmentPrompt {
  type: 'assessment_prompt'
  instrument: 'phq9' | 'gad7' | 'who5'
  questions: string[]
}

export interface WsErrorMessage {
  type: 'error'
  message: string
}

export interface WsEmotionUpdate {
  type: 'emotion_update'
  emotion: string
  valence: number
  arousal: number
  confidence: number
  modalities: string[]
}

export interface WsVitalsUpdate {
  type: 'vitals_update'
  sensor_type: 'hr' | 'gsr' | 'spo2'
  value: number
  unit: string
}

/** Phase 7: live speech transcript from TranscriptionAgent */
export interface WsTranscription {
  type: 'transcription'
  text: string
  language: string
  confidence: number
  interim?: boolean
}

export interface WsAudioResponse {
  type: 'audio_response'
  message_id: string
  sentence_index: number
  total_sentences: number
  is_final: boolean
  sample_rate: number
  format: string
}

export type WsInboundMessage =
  | WsTokenMessage
  | WsCompleteMessage
  | WsCrisisAlert
  | WsAssessmentPrompt
  | WsErrorMessage
  | WsEmotionUpdate
  | WsVitalsUpdate
  | WsTranscription
  | WsAudioResponse

// ---------------------------------------------------------------------------
// UI-only chat message (combines streaming + complete states)
// ---------------------------------------------------------------------------

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  agent?: string
  /** True while tokens are still streaming in */
  streaming?: boolean
  timestamp: Date
  /** Phase 7: 'voice' for messages that originated from speech transcription */
  source?: 'text' | 'voice'
}

// ---------------------------------------------------------------------------
// Assessment form
// ---------------------------------------------------------------------------

export type AssessmentInstrument = 'phq9' | 'gad7'

export interface AssessmentQuestion {
  index: number
  text: string
}

export const PHQ9_QUESTIONS: AssessmentQuestion[] = [
  { index: 0, text: 'Little interest or pleasure in doing things' },
  { index: 1, text: 'Feeling down, depressed, or hopeless' },
  { index: 2, text: 'Trouble falling or staying asleep, or sleeping too much' },
  { index: 3, text: 'Feeling tired or having little energy' },
  { index: 4, text: 'Poor appetite or overeating' },
  { index: 5, text: 'Feeling bad about yourself — or that you are a failure or have let yourself or your family down' },
  { index: 6, text: 'Trouble concentrating on things, such as reading the newspaper or watching television' },
  { index: 7, text: 'Moving or speaking so slowly that other people could have noticed. Or the opposite — being so fidgety or restless' },
  { index: 8, text: 'Thoughts that you would be better off dead or of hurting yourself in some way' },
]

export const GAD7_QUESTIONS: AssessmentQuestion[] = [
  { index: 0, text: 'Feeling nervous, anxious or on edge' },
  { index: 1, text: 'Not being able to stop or control worrying' },
  { index: 2, text: 'Worrying too much about different things' },
  { index: 3, text: 'Trouble relaxing' },
  { index: 4, text: 'Being so restless that it is hard to sit still' },
  { index: 5, text: 'Becoming easily annoyed or irritable' },
  { index: 6, text: 'Feeling afraid as if something awful might happen' },
]

export const SCORE_LABELS = [
  'Not at all',
  'Several days',
  'More than half the days',
  'Nearly every day',
]

// ---------------------------------------------------------------------------
// API request/response types
// ---------------------------------------------------------------------------

export interface CreatePatientRequest {
  name: string
}

export interface CreateSessionRequest {
  patient_id: string
}

export interface SubmitAssessmentRequest {
  patient_id: string
  session_id: string | null
  instrument: AssessmentInstrument
  scores: number[]
}

// ---------------------------------------------------------------------------
// Caregiver dashboard
// ---------------------------------------------------------------------------

export interface CaregiverSessionSummary {
  subjective: string
  assessment: string
  plan: string
  key_topics: string[]
  risk_flags: string[]
}

export interface CaregiverSession {
  id: string
  started_at: string
  ended_at: string | null
  summary: CaregiverSessionSummary | null
}

export interface CaregiverAlert {
  id: string
  severity: 'LOW' | 'MODERATE' | 'HIGH' | 'CRITICAL'
  timestamp: string
  escalation_action: string | null
  status: 'active' | 'acknowledged' | 'resolved'
}

export interface CaregiverAssessmentEntry {
  total_score: number
  severity: string
  timestamp: string
}

export interface CaregiverMedication {
  name: string
  dosage: string | null
  frequency: string | null
  active: boolean
}

export interface CaregiverAppointment {
  title: string
  scheduled_at: string
  status: string
}

export interface DailySummary {
  id: string
  summary_date: string
  narrative: string
  trend_alerts: string[]
  appointment_prep: string[]
  key_topics: string[]
  overall_mood: string
  created_at: string
}

export interface CaregiverOverview {
  patient: { name: string; dob: string | null; emergency_contact: string | null }
  recent_sessions: CaregiverSession[]
  crisis_alerts: CaregiverAlert[]
  assessments: {
    phq9: CaregiverAssessmentEntry[]
    gad7: CaregiverAssessmentEntry[]
    who5: CaregiverAssessmentEntry[]
  }
  medications: CaregiverMedication[]
  appointments: CaregiverAppointment[]
  daily_summary: DailySummary | null
}

// -- Care Circles -------------------------------------------------------

export interface CareCircle {
  id: string
  patient_id: string
  patient_name: string
  my_role: 'primary_caregiver' | 'family' | 'clinician'
  created_at: string
}

export interface CareCircleMember {
  id: string
  user_id: string
  email: string
  role: 'primary_caregiver' | 'family' | 'clinician'
  created_at: string
}

// -- Shared Boards ------------------------------------------------------

export interface Board {
  id: string
  care_circle_id: string
  name: string
  board_type: 'shopping' | 'chores' | 'custom'
  created_by: string
  created_at: string
}

export interface BoardItem {
  id: string
  board_id: string
  text: string
  checked: boolean
  assigned_to: string | null
  due_date: string | null
  position: number
  created_by: string
  suggested_by_ada: boolean
  approved: boolean
  created_at: string
  updated_at: string
}

export type WsBoardMessage =
  | { type: 'item_added'; item: BoardItem; by: string }
  | { type: 'item_checked'; item_id: string; checked: boolean; by: string }
  | { type: 'item_edited'; item_id: string; text: string; by: string }
  | { type: 'item_deleted'; item_id: string; by: string }
  | { type: 'item_reordered'; item_id: string; position: number; by: string }
  | { type: 'item_suggested'; item: BoardItem; by: 'ada' }
  | { type: 'item_approved'; item_id: string; by: string }
  | { type: 'error'; message: string }

// -- Medications --------------------------------------------------------

export interface Medication {
  id: string
  patient_id: string
  name: string
  dosage: string | null
  frequency: string | null
  start_date: string | null
  end_date: string | null
  notes: string | null
  prescribed_by: string | null
  active: boolean
  created_at: string
  updated_at: string
}

export interface MedicationCreate {
  name: string
  dosage?: string
  frequency?: string
  start_date?: string
  prescribed_by?: string
  notes?: string
}

export interface MedicationUpdate {
  name?: string
  dosage?: string
  frequency?: string
  start_date?: string
  end_date?: string
  active?: boolean
  prescribed_by?: string
  notes?: string
}

export interface MedicationCreateResponse extends Medication {
  interaction_warning?: string
}

// -- Appointments -------------------------------------------------------

export interface Appointment {
  id: string
  patient_id: string
  title: string
  description: string | null
  scheduled_at: string
  duration_minutes: number
  appointment_type: string
  status: string
  provider_name: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface AppointmentCreate {
  title: string
  scheduled_at: string
  description?: string
  duration_minutes?: number
  appointment_type?: string
  provider_name?: string
  notes?: string
}

export interface AppointmentUpdate {
  title?: string
  scheduled_at?: string
  description?: string
  duration_minutes?: number
  status?: string
  provider_name?: string
  notes?: string
  change_requested?: boolean
  change_note?: string
}

// -- Circle Setup -------------------------------------------------------

export interface UserLookup {
  user_id: string
  email: string
  patient_id: string | null
  role: string
}

export interface CreateWithPatientResponse {
  circle_id: string
  patient_id: string
  patient_name: string
}

// -- Medication Logs ----------------------------------------------------

export interface MedicationLog {
  id: string
  medication_id: string
  patient_id: string
  taken_at: string
  status: 'taken' | 'skipped' | 'missed'
  created_at: string
}

// -- Crisis Alerts (full detail) ----------------------------------------

export interface CrisisAlertFull {
  id: string
  patient_id: string
  session_id: string | null
  severity: string
  detection_method: string
  escalation_action: string | null
  timestamp: string
  status: 'active' | 'acknowledged' | 'resolved'
  resolved_at: string | null
  resolved_by: string | null
}

// -- Notification Preferences (Phase 11b) -------------------------------

export interface NotificationPreferences {
  crisis_detected: boolean
  board_item_suggested: boolean
  board_item_added: boolean
  board_item_checked: boolean
  daily_summary_generated: boolean
  circle_member_added: boolean
}

// -- Clinical Visualization (Phase 12a) ---------------------------------

export interface KnowledgeNode {
  id: string
  patient_id: string
  node_type: string
  label: string
  properties: Record<string, unknown>
  mention_count: number
  confidence: number
  created_at: string
  updated_at: string
}

export interface KnowledgeEdge {
  id: string
  patient_id: string
  from_node: string
  to_node: string
  relation: string
  weight: number
  mention_count: number
  created_at: string
  updated_at: string
}

export interface KnowledgeGraphData {
  nodes: KnowledgeNode[]
  edges: KnowledgeEdge[]
}

export interface KnowledgeTrend {
  node_id: string
  label: string
  current_count: number
  prior_count: number
  direction: 'improving' | 'declining' | 'stable'
}

export interface ProgressReportData {
  narrative: string
  who5_trend: { date: string; score: number }[]
  session_count_by_week: { week: string; count: number }[]
  emotion_distribution: Record<string, number>
  medication_adherence: { taken: number; total: number; missed_dates: string[] }
  assessment_scores: Record<string, { current: number; previous: number; severity: string }>
  flags: string[]
}

export interface SessionSummaryData {
  session_id: string
  patient_id: string
  subjective: string
  objective: string
  assessment: string
  plan: string
  key_topics: string[]
  risk_flags: string[]
  created_at: string
}

export interface ClinicianNote {
  id: string
  user_id: string
  entity_type: string
  entity_id: string
  content: string
  created_at: string
  updated_at: string
}
