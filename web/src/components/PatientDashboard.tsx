/**
 * PatientDashboard — main patient-facing view.
 *
 * Replaces the chat-first patient layout with a 6-card grid that surfaces the
 * most actionable information: a direct shortcut to Ada, medications with
 * one-tap logging, upcoming appointments with change requests, shared boards,
 * care team roster, and a mood summary.
 *
 * All data fetching is local to each card section so failures are isolated —
 * a broken mood fetch doesn't break the medications card.
 *
 * @decision DEC-FRONTEND-040
 * @title PatientDashboard co-locates card sections — no separate card files
 * @status accepted
 * @rationale Six cards, each small enough (~30-50 lines of JSX) to keep
 *   inline without hurting readability. Avoids prop-drilling a shared patientId
 *   through six extra file boundaries. If any card grows beyond ~80 lines it
 *   should be extracted.
 */

import { useState, useEffect, useCallback } from 'react'
import {
  listMedications,
  listAppointments,
  logMedicationTaken,
  updateAppointment,
  getCircleBoards,
  getCircleMembers,
  getMoodHistory,
} from '../api/client'
import { useCircles } from '../hooks/useCircles'
import type { Medication, Appointment, Board, CareCircleMember, MoodDataPoint } from '../types'

interface PatientDashboardProps {
  patientId: string
  /** Flexible navigation callback: accepts view name strings (e.g. 'chat', 'knowledge-graph', 'progress'). */
  onNavigate: (view: string) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function moodTrend(points: MoodDataPoint[]): 'up' | 'down' | 'stable' {
  if (points.length < 2) return 'stable'
  const recent = points[points.length - 1].score
  const prev = points[points.length - 2].score
  if (recent > prev) return 'up'
  if (recent < prev) return 'down'
  return 'stable'
}

const TREND_LABEL: Record<'up' | 'down' | 'stable', string> = {
  up: '↑ improving',
  down: '↓ declining',
  stable: '→ stable',
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PatientDashboard({ patientId, onNavigate }: PatientDashboardProps) {
  // -- Medications ---------------------------------------------------------
  const [meds, setMeds] = useState<Medication[]>([])
  const [medsLoading, setMedsLoading] = useState(true)
  const [takenIds, setTakenIds] = useState<Set<string>>(new Set())
  const [medError, setMedError] = useState<string | null>(null)

  // -- Appointments --------------------------------------------------------
  const [appointments, setAppts] = useState<Appointment[]>([])
  const [apptLoading, setApptLoading] = useState(true)
  const [apptError, setApptError] = useState<string | null>(null)
  // Per-appointment change-request state: apptId → { open, note, saving }
  const [changeReqs, setChangeReqs] = useState<
    Record<string, { open: boolean; note: string; saving: boolean; done: boolean }>
  >({})

  // -- Boards --------------------------------------------------------------
  const [boards, setBoards] = useState<Board[]>([])
  const [boardsLoading, setBoardsLoading] = useState(false)
  const [boardsError, setBoardsError] = useState<string | null>(null)

  // -- Care team -----------------------------------------------------------
  const [members, setMembers] = useState<CareCircleMember[]>([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [membersError, setMembersError] = useState<string | null>(null)

  // -- Mood ----------------------------------------------------------------
  const [moodPoints, setMoodPoints] = useState<MoodDataPoint[]>([])
  const [moodLoading, setMoodLoading] = useState(true)

  // -- Circle (shared between boards + care team) --------------------------
  const { selectedCircle } = useCircles()

  // -------------------------------------------------------------------------
  // Fetch: medications
  // -------------------------------------------------------------------------
  const fetchMeds = useCallback(async () => {
    try {
      const data = await listMedications(patientId, true)
      setMeds(data)
    } catch (err) {
      setMedError(err instanceof Error ? err.message : 'Failed to load medications')
    } finally {
      setMedsLoading(false)
    }
  }, [patientId])

  // -------------------------------------------------------------------------
  // Fetch: appointments
  // -------------------------------------------------------------------------
  const fetchAppts = useCallback(async () => {
    try {
      const data = await listAppointments(patientId)
      setAppts(data)
    } catch (err) {
      setApptError(err instanceof Error ? err.message : 'Failed to load appointments')
    } finally {
      setApptLoading(false)
    }
  }, [patientId])

  // -------------------------------------------------------------------------
  // Fetch: boards + members (depend on circle)
  // -------------------------------------------------------------------------
  const fetchBoards = useCallback(async (circleId: string) => {
    setBoardsLoading(true)
    try {
      const data = await getCircleBoards(circleId)
      setBoards(data)
    } catch (err) {
      setBoardsError(err instanceof Error ? err.message : 'Failed to load boards')
    } finally {
      setBoardsLoading(false)
    }
  }, [])

  const fetchMembers = useCallback(async (circleId: string) => {
    setMembersLoading(true)
    try {
      const data = await getCircleMembers(circleId)
      setMembers(data)
    } catch (err) {
      setMembersError(err instanceof Error ? err.message : 'Failed to load care team')
    } finally {
      setMembersLoading(false)
    }
  }, [])

  // -------------------------------------------------------------------------
  // Fetch: mood history
  // -------------------------------------------------------------------------
  const fetchMood = useCallback(async () => {
    try {
      const data = await getMoodHistory(patientId)
      setMoodPoints(data)
    } catch {
      // Non-critical — mood card degrades gracefully
    } finally {
      setMoodLoading(false)
    }
  }, [patientId])

  // -------------------------------------------------------------------------
  // Effects
  // -------------------------------------------------------------------------
  useEffect(() => { fetchMeds() }, [fetchMeds])
  useEffect(() => { fetchAppts() }, [fetchAppts])
  useEffect(() => { fetchMood() }, [fetchMood])

  useEffect(() => {
    if (selectedCircle) {
      fetchBoards(selectedCircle.id)
      fetchMembers(selectedCircle.id)
    }
  }, [selectedCircle, fetchBoards, fetchMembers])

  // -------------------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------------------
  const handleMarkTaken = async (medId: string) => {
    try {
      await logMedicationTaken(patientId, medId)
      setTakenIds(prev => new Set([...prev, medId]))
    } catch {
      // Silent — button stays enabled so patient can retry
    }
  }

  const openChangeReq = (apptId: string) => {
    setChangeReqs(prev => ({
      ...prev,
      [apptId]: { open: true, note: '', saving: false, done: false },
    }))
  }

  const closeChangeReq = (apptId: string) => {
    setChangeReqs(prev => {
      const next = { ...prev }
      delete next[apptId]
      return next
    })
  }

  const submitChangeReq = async (apptId: string) => {
    const req = changeReqs[apptId]
    if (!req) return
    setChangeReqs(prev => ({ ...prev, [apptId]: { ...prev[apptId], saving: true } }))
    try {
      await updateAppointment(patientId, apptId, {
        change_requested: true,
        change_note: req.note.trim() || undefined,
      })
      setChangeReqs(prev => ({ ...prev, [apptId]: { ...prev[apptId], saving: false, done: true, open: false } }))
    } catch {
      setChangeReqs(prev => ({ ...prev, [apptId]: { ...prev[apptId], saving: false } }))
    }
  }

  // Upcoming = future + not cancelled
  const now = new Date()
  const upcomingAppts = appointments
    .filter(a => a.status !== 'cancelled' && new Date(a.scheduled_at) > now)
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
    <div className="patient-dash">

      {/* Card 1: Talk to Ada — full width */}
      <div
        className="patient-dash__card patient-dash__card--full patient-dash__card--ada"
        onClick={() => onNavigate('chat')}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && onNavigate('chat')}
        aria-label="Open chat with Ada"
      >
        <h2>Talk to Ada</h2>
        <p>Start a conversation with Ada</p>
      </div>

      {/* Card 2: My Journey Map */}
      <div
        className="patient-dash__card patient-dash__card--clickable"
        onClick={() => onNavigate('knowledge-graph')}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && onNavigate('knowledge-graph')}
        aria-label="View your journey map"
      >
        <h3>My Journey Map</h3>
        <p className="patient-dash__card-desc">Explore your wellness journey and how topics connect</p>
      </div>

      {/* Card 3: Progress Report */}
      <div
        className="patient-dash__card patient-dash__card--clickable"
        onClick={() => onNavigate('progress')}
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && onNavigate('progress')}
        aria-label="View your progress report"
      >
        <h3>Progress Report</h3>
        <p className="patient-dash__card-desc">See how you are doing over time</p>
      </div>

      {/* Card 4: Medications */}
      <div className="patient-dash__card">
        <h3>Medications</h3>
        {medsLoading ? (
          <p className="patient-dash__empty">Loading…</p>
        ) : medError ? (
          <p className="patient-dash__error">{medError}</p>
        ) : meds.length === 0 ? (
          <p className="patient-dash__empty">No medications</p>
        ) : (
          <ul className="patient-dash__list">
            {meds.map(med => (
              <li key={med.id} className="patient-dash__item">
                <div className="patient-dash__item-info">
                  <span className="patient-dash__item-name">{med.name}</span>
                  {med.dosage && <span className="patient-dash__item-sub">{med.dosage}</span>}
                  {med.frequency && <span className="patient-dash__item-tag">{med.frequency}</span>}
                </div>
                {takenIds.has(med.id) ? (
                  <span className="patient-dash__taken-badge">Taken</span>
                ) : (
                  <button
                    type="button"
                    className="med-card__btn"
                    onClick={() => handleMarkTaken(med.id)}
                    aria-label={`Mark ${med.name} as taken`}
                  >
                    Mark taken
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Card 3: Upcoming Appointments */}
      <div className="patient-dash__card">
        <h3>Upcoming Appointments</h3>
        {apptLoading ? (
          <p className="patient-dash__empty">Loading…</p>
        ) : apptError ? (
          <p className="patient-dash__error">{apptError}</p>
        ) : upcomingAppts.length === 0 ? (
          <p className="patient-dash__empty">No upcoming appointments</p>
        ) : (
          <ul className="patient-dash__list">
            {upcomingAppts.map(appt => {
              const req = changeReqs[appt.id]
              return (
                <li key={appt.id} className="patient-dash__item patient-dash__item--col">
                  <div className="patient-dash__item-info">
                    <span className="patient-dash__item-name">{appt.title}</span>
                    <span className="patient-dash__item-sub">{formatDate(appt.scheduled_at)}</span>
                  </div>
                  {req?.done ? (
                    <span className="patient-dash__taken-badge">Request sent</span>
                  ) : req?.open ? (
                    <div className="patient-dash__change-form">
                      <input
                        className="patient-dash__change-input"
                        type="text"
                        placeholder="Reason for change (optional)"
                        value={req.note}
                        onChange={e =>
                          setChangeReqs(prev => ({
                            ...prev,
                            [appt.id]: { ...prev[appt.id], note: e.target.value },
                          }))
                        }
                        disabled={req.saving}
                        autoFocus
                        aria-label="Change request note"
                      />
                      <div className="patient-dash__change-actions">
                        <button
                          type="button"
                          className="med-card__btn med-card__btn--secondary"
                          onClick={() => closeChangeReq(appt.id)}
                          disabled={req.saving}
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          className="med-card__btn"
                          onClick={() => submitChangeReq(appt.id)}
                          disabled={req.saving}
                        >
                          {req.saving ? 'Sending…' : 'Send'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="med-card__btn med-card__btn--secondary"
                      onClick={() => openChangeReq(appt.id)}
                      aria-label={`Request change for ${appt.title}`}
                    >
                      Request change
                    </button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {/* Card 4: My Boards */}
      <div className="patient-dash__card">
        <h3>My Boards</h3>
        {!selectedCircle ? (
          <p className="patient-dash__empty">Not part of a care circle</p>
        ) : boardsLoading ? (
          <p className="patient-dash__empty">Loading…</p>
        ) : boardsError ? (
          <p className="patient-dash__error">{boardsError}</p>
        ) : boards.length === 0 ? (
          <p className="patient-dash__empty">No boards yet</p>
        ) : (
          <ul className="patient-dash__list">
            {boards.map(board => (
              <li key={board.id} className="patient-dash__board-item">
                <span className="patient-dash__item-name">{board.name}</span>
                <span className="patient-dash__item-tag">{board.board_type}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Card 5: My Care Team */}
      <div className="patient-dash__card">
        <h3>My Care Team</h3>
        {!selectedCircle ? (
          <p className="patient-dash__empty">Not part of a care circle</p>
        ) : membersLoading ? (
          <p className="patient-dash__empty">Loading…</p>
        ) : membersError ? (
          <p className="patient-dash__error">{membersError}</p>
        ) : members.length === 0 ? (
          <p className="patient-dash__empty">Not part of a care circle</p>
        ) : (
          <ul className="patient-dash__list">
            {members.map(m => (
              <li key={m.user_id} className="patient-dash__item">
                <span className="patient-dash__item-name">{m.email}</span>
                <span className="patient-dash__item-tag">{m.role}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Card 6: Mood Summary */}
      <div className="patient-dash__card">
        <h3>Mood Summary</h3>
        {moodLoading ? (
          <p className="patient-dash__empty">Loading…</p>
        ) : moodPoints.length === 0 ? (
          <p className="patient-dash__empty">Chat with Ada to track your mood</p>
        ) : (
          <div className="patient-dash__mood">
            <span className="patient-dash__mood-score">
              {moodPoints[moodPoints.length - 1].score}/10
            </span>
            <span className="patient-dash__mood-trend">
              {TREND_LABEL[moodTrend(moodPoints)]}
            </span>
            <p className="patient-dash__mood-label">
              Most recent mood score
            </p>
          </div>
        )}
      </div>

    </div>
  )
}
