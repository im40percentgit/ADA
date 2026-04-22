/**
 * PatientDashboard — main patient-facing view.
 *
 * Replaces the chat-first patient layout with a card-based grid that surfaces the
 * most actionable information: a hero shortcut to the companion, wellbeing score,
 * medications with one-tap logging, upcoming appointments with change requests,
 * shared boards, care team roster, cognitive screening, and a mood summary.
 *
 * All data fetching is local to each card section so failures are isolated —
 * a broken mood fetch doesn't break the medications card.
 *
 * Uses the design-system Card, Badge, and Button components with token-based
 * styling from tokens.css.
 *
 * @decision DEC-FRONTEND-040
 * @title PatientDashboard co-locates card sections — no separate card files
 * @status accepted
 * @rationale Six cards, each small enough (~30-50 lines of JSX) to keep
 *   inline without hurting readability. Avoids prop-drilling a shared patientId
 *   through six extra file boundaries. If any card grows beyond ~80 lines it
 *   should be extracted.
 *
 * @decision DEC-DASH-STATES-001
 * @title AsyncBoundary primitives applied to PatientDashboard loading/empty/error states
 * @status accepted
 * @rationale Each of the five independent data sections (medications, appointments,
 *   boards, care team, mood) previously used ad-hoc inline `<p>` elements for
 *   loading ("Loading…"), error (red text), and empty ("No X") states. These have
 *   been replaced with SkeletonCard (loading), ErrorState with onRetry (errors),
 *   and EmptyState with warm tone + helpful copy (empty). The existing AppShell,
 *   BottomNav, Card containers, and all aria-label/role attributes are preserved
 *   unchanged. Retry callbacks are wired to the existing useCallback fetch
 *   functions — no hook refactoring required. The mood card degrades silently
 *   (non-critical) so it uses EmptyState but no ErrorState.
 */

import { useState, useEffect, useCallback } from 'react'
import type { CSSProperties } from 'react'
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
import { useCompanionPreferences, DEFAULT_COMPANION_PREFERENCES } from '../hooks/useCompanionPreferences'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { SkeletonCard } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'
import { ErrorState } from './ui/ErrorState'
import { BoardView } from './BoardView'
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

const TREND_VARIANT: Record<'up' | 'down' | 'stable', 'success' | 'danger' | 'neutral'> = {
  up: 'success',
  down: 'danger',
  stable: 'neutral',
}

// ---------------------------------------------------------------------------
// Styles (token-based)
// ---------------------------------------------------------------------------

const dashboardStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(2, 1fr)',
  gap: 'var(--space-md)',
  padding: 'var(--space-md)',
  maxWidth: '900px',
  margin: '0 auto',
}

const heroCardStyle: CSSProperties = {
  gridColumn: '1 / -1',
  background: 'linear-gradient(135deg, var(--color-primary), #6d28d9)',
  border: 'none',
  padding: 'var(--space-xl)',
  cursor: 'pointer',
}

const heroTitleStyle: CSSProperties = {
  fontFamily: 'var(--font-heading)',
  fontSize: 'var(--size-h1)',
  fontWeight: 700,
  color: '#ffffff',
  margin: '0 0 var(--space-sm) 0',
}

const heroSubStyle: CSSProperties = {
  fontSize: 'var(--size-body)',
  color: 'rgba(255,255,255,0.85)',
  margin: '0 0 var(--space-md) 0',
}

const fullWidthCardStyle: CSSProperties = {
  gridColumn: '1 / -1',
}

const moodScoreStyle: CSSProperties = {
  fontFamily: 'var(--font-heading)',
  fontSize: '36px',
  fontWeight: 700,
  color: 'var(--color-text-primary)',
}

const moodLabelStyle: CSSProperties = {
  fontSize: 'var(--size-sm)',
  color: 'var(--color-text-muted)',
  marginTop: 'var(--space-xs)',
}

const sectionHeadingStyle: CSSProperties = {
  fontFamily: 'var(--font-heading)',
  fontSize: 'var(--size-h2)',
  fontWeight: 600,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-sm) 0',
}

const cardDescStyle: CSSProperties = {
  fontSize: 'var(--size-sm)',
  color: 'var(--color-text-muted)',
  margin: '0 0 var(--space-sm) 0',
}

const listStyle: CSSProperties = {
  listStyle: 'none',
  padding: 0,
  margin: 0,
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-sm)',
}

const listItemStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: 'var(--space-sm)',
  borderRadius: 'var(--radius-input)',
  background: 'var(--color-bg-elevated)',
}

const listItemColStyle: CSSProperties = {
  ...listItemStyle,
  flexDirection: 'column',
  alignItems: 'stretch',
  gap: 'var(--space-sm)',
}

const itemNameStyle: CSSProperties = {
  fontSize: 'var(--size-body)',
  fontWeight: 600,
  color: 'var(--color-text-primary)',
}

const itemSubStyle: CSSProperties = {
  fontSize: 'var(--size-sm)',
  color: 'var(--color-text-muted)',
}

const itemTagStyle: CSSProperties = {
  fontSize: 'var(--size-xs)',
  color: 'var(--color-text-muted)',
}

const changeFormStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-sm)',
}

const changeInputStyle: CSSProperties = {
  background: 'var(--color-bg-base)',
  border: '1px solid var(--color-border)',
  borderRadius: 'var(--radius-input)',
  padding: 'var(--space-sm)',
  color: 'var(--color-text-primary)',
  fontSize: 'var(--size-sm)',
}

const changeActionsStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-sm)',
  justifyContent: 'flex-end',
}

const cardActionsStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-sm)',
  flexWrap: 'wrap',
}

const headingRowStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 'var(--space-sm)',
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PatientDashboard({ patientId, onNavigate }: PatientDashboardProps) {
  // -- Companion preferences ------------------------------------------------
  const { preferences: companionPrefs } = useCompanionPreferences()
  const companionName = companionPrefs?.name ?? DEFAULT_COMPANION_PREFERENCES.name

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
  const [activeBoardId, setActiveBoardId] = useState<string | null>(null)

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
    setMedsLoading(true)
    setMedError(null)
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
    setApptLoading(true)
    setApptError(null)
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

  const pendingMedCount = meds.filter(m => !takenIds.has(m.id)).length

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  // Drill-down: when a board is selected, replace the full dashboard with BoardView
  if (activeBoardId) {
    return (
      <div style={dashboardStyle} role="main" aria-label="Board detail">
        <BoardView boardId={activeBoardId} onBack={() => setActiveBoardId(null)} />
      </div>
    )
  }

  return (
    <div style={dashboardStyle} role="main" aria-label="Patient Dashboard">
      <h1 className="sr-only">Patient Dashboard</h1>

      {/* Hero Card: Talk to companion */}
      <Card
        style={heroCardStyle}
        onClick={() => onNavigate('chat')}
      >
        <div
          role="button"
          tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && onNavigate('chat')}
          aria-label={`Open chat with ${companionName}`}
        >
          <h2 style={heroTitleStyle}>Talk to {companionName}</h2>
          <p style={heroSubStyle}>Start a conversation with {companionName}</p>
          <Button variant="secondary" size="md">
            Start Session →
          </Button>
        </div>
      </Card>

      {/* Wellbeing / Mood Score Card */}
      <section aria-label="Wellbeing">
      <Card>
        <h2 style={sectionHeadingStyle}>Mood Summary</h2>
        {moodLoading ? (
          <SkeletonCard lines={2} />
        ) : moodPoints.length === 0 ? (
          <EmptyState
            tone="warm"
            icon="💙"
            title="No mood check-ins yet"
            description={`Share how you're feeling — ${companionName} will track your trend.`}
          />
        ) : (
          <div>
            <span style={moodScoreStyle}>
              {moodPoints[moodPoints.length - 1].score}/10
            </span>
            <div style={{ marginTop: 'var(--space-xs)' }}>
              <Badge variant={TREND_VARIANT[moodTrend(moodPoints)]}>
                {TREND_LABEL[moodTrend(moodPoints)]}
              </Badge>
            </div>
            <p style={moodLabelStyle}>
              Most recent mood score
            </p>
          </div>
        )}
      </Card>
      </section>

      {/* Quick Action: My Journey Map */}
      <Card
        onClick={() => onNavigate('knowledge-graph')}
      >
        <div
          role="button"
          tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && onNavigate('knowledge-graph')}
          aria-label="View your journey map"
        >
          <h2 style={sectionHeadingStyle}>My Journey Map</h2>
          <p style={cardDescStyle}>Explore your wellness journey and how topics connect</p>
        </div>
      </Card>

      {/* Quick Action: Progress Report */}
      <Card
        onClick={() => onNavigate('progress')}
      >
        <div
          role="button"
          tabIndex={0}
          onKeyDown={e => e.key === 'Enter' && onNavigate('progress')}
          aria-label="View your progress report"
        >
          <h2 style={sectionHeadingStyle}>Progress Report</h2>
          <p style={cardDescStyle}>See how you are doing over time</p>
        </div>
      </Card>

      {/* Medications Card */}
      <section aria-label="Medications">
      <Card style={fullWidthCardStyle}>
        <div style={headingRowStyle}>
          <h2 style={{ ...sectionHeadingStyle, margin: 0 }}>Medications</h2>
          {!medsLoading && !medError && meds.length > 0 && (
            <Badge variant={pendingMedCount > 0 ? 'warning' : 'success'}>
              {pendingMedCount > 0 ? `${pendingMedCount} pending` : 'All taken'}
            </Badge>
          )}
        </div>
        {medsLoading ? (
          <SkeletonCard lines={3} />
        ) : medError ? (
          <ErrorState
            title="Couldn't load medications"
            message={medError}
            onRetry={fetchMeds}
          />
        ) : meds.length === 0 ? (
          <EmptyState
            tone="warm"
            icon="💊"
            title="No medications tracked"
            description="Add a medication to start logging daily adherence."
          />
        ) : (
          <ul style={listStyle}>
            {meds.map(med => (
              <li key={med.id} style={listItemStyle}>
                <div>
                  <span style={itemNameStyle}>{med.name}</span>
                  {med.dosage && <span style={{ ...itemSubStyle, marginLeft: 'var(--space-sm)' }}>{med.dosage}</span>}
                  {med.frequency && <span style={{ ...itemTagStyle, marginLeft: 'var(--space-sm)' }}>{med.frequency}</span>}
                </div>
                {takenIds.has(med.id) ? (
                  <Badge variant="success">Taken</Badge>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => handleMarkTaken(med.id)}
                  >
                    <span aria-label={`Mark ${med.name} as taken`}>Mark taken</span>
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
      </section>

      {/* Upcoming Appointments Card */}
      <section aria-label="Upcoming Appointments">
      <Card style={fullWidthCardStyle}>
        <div style={headingRowStyle}>
          <h2 style={{ ...sectionHeadingStyle, margin: 0 }}>Upcoming Appointments</h2>
          {!apptLoading && !apptError && upcomingAppts.length > 0 && (
            <Badge variant="info">
              Next: {formatDate(upcomingAppts[0].scheduled_at)}
            </Badge>
          )}
        </div>
        {apptLoading ? (
          <SkeletonCard lines={2} />
        ) : apptError ? (
          <ErrorState
            title="Couldn't load appointments"
            message={apptError}
            onRetry={fetchAppts}
          />
        ) : upcomingAppts.length === 0 ? (
          <EmptyState
            tone="warm"
            icon="📅"
            title="No upcoming appointments"
            description="Your schedule is clear."
          />
        ) : (
          <ul style={listStyle}>
            {upcomingAppts.map(appt => {
              const req = changeReqs[appt.id]
              return (
                <li key={appt.id} style={listItemColStyle}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <span style={itemNameStyle}>{appt.title}</span>
                      <span style={{ ...itemSubStyle, marginLeft: 'var(--space-sm)' }}>{formatDate(appt.scheduled_at)}</span>
                    </div>
                  </div>
                  {req?.done ? (
                    <Badge variant="success">Request sent</Badge>
                  ) : req?.open ? (
                    <div style={changeFormStyle}>
                      <input
                        style={changeInputStyle}
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
                      <div style={changeActionsStyle}>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => closeChangeReq(appt.id)}
                          disabled={req.saving}
                        >
                          Cancel
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => submitChangeReq(appt.id)}
                          disabled={req.saving}
                        >
                          {req.saving ? 'Sending…' : 'Send'}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => openChangeReq(appt.id)}
                    >
                      <span aria-label={`Request change for ${appt.title}`}>Request change</span>
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </Card>
      </section>

      {/* My Boards Card */}
      <Card>
        <h2 style={sectionHeadingStyle}>My Boards</h2>
        {!selectedCircle ? (
          <EmptyState
            tone="warm"
            icon="📋"
            title="No shared boards yet"
            description="Ask a family member to invite you or start a new board."
          />
        ) : boardsLoading ? (
          <SkeletonCard lines={2} />
        ) : boardsError ? (
          <ErrorState
            title="Couldn't load boards"
            message={boardsError}
            onRetry={() => fetchBoards(selectedCircle.id)}
          />
        ) : boards.length === 0 ? (
          <EmptyState
            tone="warm"
            icon="📋"
            title="No shared boards yet"
            description="Ask a family member to invite you or start a new board."
          />
        ) : (
          <ul style={listStyle}>
            {boards.map(board => (
              <li key={board.id}>
                <button
                  style={{
                    ...listItemStyle,
                    width: '100%',
                    minHeight: '44px',
                    cursor: 'pointer',
                    background: 'var(--color-bg-elevated)',
                    border: '1px solid var(--color-border)',
                    borderRadius: 'var(--radius-input)',
                    textAlign: 'left',
                  }}
                  onClick={() => setActiveBoardId(board.id)}
                  aria-label={`Open board: ${board.name}`}
                >
                  <span style={itemNameStyle}>{board.name}</span>
                  <Badge variant="neutral">{board.board_type}</Badge>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* My Care Team Card */}
      <Card>
        <h2 style={sectionHeadingStyle}>My Care Team</h2>
        {!selectedCircle ? (
          <EmptyState
            tone="warm"
            icon="👥"
            title="No care team members yet"
            description="Invite someone to share wellbeing updates."
          />
        ) : membersLoading ? (
          <SkeletonCard lines={2} />
        ) : membersError ? (
          <ErrorState
            title="Couldn't load care team"
            message={membersError}
            onRetry={() => fetchMembers(selectedCircle.id)}
          />
        ) : members.length === 0 ? (
          <EmptyState
            tone="warm"
            icon="👥"
            title="No care team members yet"
            description="Invite someone to share wellbeing updates."
          />
        ) : (
          <ul style={listStyle}>
            {members.map(m => (
              <li key={m.user_id} style={listItemStyle}>
                <span style={itemNameStyle}>{m.email}</span>
                <Badge variant="info">{m.role}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Cognitive Screening Card */}
      <Card style={fullWidthCardStyle}>
        <h2 style={sectionHeadingStyle}>Cognitive Screening</h2>
        <p style={cardDescStyle}>Assess memory, attention, and cognitive function</p>
        <div style={cardActionsStyle}>
          <Button
            variant="primary"
            size="sm"
            onClick={() => onNavigate('cognitive-screening')}
          >
            <span aria-label="Start a new cognitive screening">Start Screening</span>
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onNavigate('screening-history')}
          >
            <span aria-label="View cognitive screening history">View History</span>
          </Button>
        </div>
      </Card>

    </div>
  )
}
