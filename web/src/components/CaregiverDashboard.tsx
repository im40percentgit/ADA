/**
 * CaregiverDashboard — main container for the caregiver view.
 *
 * Fetches aggregated patient data from GET /api/caregiver/overview on mount,
 * then polls every 60 seconds. Renders StatusCard, AlertsCard, SessionsCard,
 * WellbeingChart, DailySummaryCard, plus medications and appointments sections.
 *
 * Uses the design-system Card, Badge, and Button components with token-based
 * styling from tokens.css.
 *
 * @decision DEC-FRONTEND-020
 * @title CaregiverDashboard polls at 60s interval — no WebSocket
 * @status accepted
 * @rationale The caregiver dashboard is a read-only summary view. Real-time
 *   streaming (WebSocket) is reserved for the patient chat experience. A 60s
 *   polling interval provides adequate freshness for status monitoring while
 *   keeping the implementation simple and server load minimal.
 *
 * @decision DEC-FRONTEND-021
 * @title DailySummaryCard inlined in CaregiverDashboard (not a separate file)
 * @status accepted
 * @rationale The DailySummaryCard is used only in this dashboard and is small
 *   enough (~60 lines) that extracting it would add import indirection without
 *   benefit. Co-location makes the data flow obvious: overview.daily_summary
 *   flows directly into the card without prop drilling through an extra module.
 *
 * @decision DEC-DASH-STATES-001
 * @title AsyncBoundary primitives applied to CaregiverDashboard loading/error states
 * @status accepted
 * @rationale The previous full-screen spinner (role="status" + app__loading-spinner)
 *   and red error banner (role="alert" + errorTextStyle paragraph) have been
 *   replaced with SkeletonList (initial load) and ErrorState with onRetry (fetch
 *   error). The existing AppShell, Card containers, aria-label attributes, polling
 *   interval, and CircleSetupWizard path are all preserved unchanged. The fetchData
 *   callback doubles as the retry handler — no hook refactoring required. The
 *   ErrorState role="status" satisfies the existing test that asserts
 *   getByRole('alert') via the outer role="alert" wrapper retained around it.
 */

import { useEffect, useState, useCallback } from 'react'
import type { CSSProperties } from 'react'
import { getCaregiverOverviewForPatient } from '../api/client'
import type { CaregiverOverview, DailySummary } from '../types'
import { useCircles } from '../hooks/useCircles'
import { CircleSetupWizard } from './CircleSetupWizard'
import { StatusCard } from './StatusCard'
import { AlertsCard } from './AlertsCard'
import { SessionsCard } from './SessionsCard'
import { WellbeingChart } from './WellbeingChart'
import { CircleSelector } from './CircleSelector'
import { CircleMembers } from './CircleMembers'
import { BoardList } from './BoardList'
import { BoardView } from './BoardView'
import { MedicationCard } from './MedicationCard'
import { AppointmentCard } from './AppointmentCard'
import { NotificationBell } from './NotificationBell'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { SkeletonList } from './ui/Skeleton'
import { ErrorState } from './ui/ErrorState'

// ---------------------------------------------------------------------------
// Styles (token-based)
// ---------------------------------------------------------------------------

const dashboardStyle: CSSProperties = {
  padding: 'var(--space-md)',
  maxWidth: '1100px',
  margin: '0 auto',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 'var(--space-md)',
  marginBottom: 'var(--space-lg)',
  flexWrap: 'wrap',
}

const headerLeftStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-xs)',
}

const headerRightStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-sm)',
}

const titleStyle: CSSProperties = {
  fontFamily: 'var(--font-heading)',
  fontSize: 'var(--size-h1)',
  fontWeight: 700,
  color: 'var(--color-text-primary)',
  margin: 0,
}

const patientNameStyle: CSSProperties = {
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-muted)',
  margin: 0,
}

const gridStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
  gap: 'var(--space-md)',
}

const fullWidthStyle: CSSProperties = {
  gridColumn: '1 / -1',
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

const emptyTextStyle: CSSProperties = {
  fontSize: 'var(--size-sm)',
  color: 'var(--color-text-muted)',
}

// ---------------------------------------------------------------------------
// DailySummaryCard (inline, token-based)
// ---------------------------------------------------------------------------

const MOOD_VARIANT: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
  anxious: 'warning',
  depressed: 'danger',
  stable: 'neutral',
  improving: 'success',
  declining: 'danger',
  mixed: 'info',
}

const dailyHeaderStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  marginBottom: 'var(--space-sm)',
}

const dailyMetaStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-sm)',
}

const dailyDateStyle: CSSProperties = {
  fontSize: 'var(--size-sm)',
  color: 'var(--color-text-muted)',
}

const narrativeStyle: CSSProperties = {
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-secondary)',
  margin: '0 0 var(--space-md) 0',
  lineHeight: 1.5,
}

const dailySectionTitleStyle: CSSProperties = {
  fontFamily: 'var(--font-heading)',
  fontSize: 'var(--size-sm)',
  fontWeight: 600,
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-xs) 0',
}

const alertListStyle: CSSProperties = {
  listStyle: 'none',
  padding: 0,
  margin: '0 0 var(--space-sm) 0',
}

const alertItemStyle: CSSProperties = {
  fontSize: 'var(--size-sm)',
  color: 'var(--color-warning)',
  padding: 'var(--space-xs) 0',
  display: 'flex',
  alignItems: 'flex-start',
  gap: 'var(--space-xs)',
}

const prepListStyle: CSSProperties = {
  listStyle: 'none',
  padding: 0,
  margin: '0 0 var(--space-sm) 0',
}

const prepItemStyle: CSSProperties = {
  fontSize: 'var(--size-sm)',
  color: 'var(--color-text-secondary)',
  padding: 'var(--space-xs) 0',
  display: 'flex',
  alignItems: 'flex-start',
  gap: 'var(--space-xs)',
}

const topicChipsStyle: CSSProperties = {
  display: 'flex',
  flexWrap: 'wrap',
  gap: 'var(--space-xs)',
}

function DailySummaryCard({ summary, onViewDetail }: { summary: DailySummary | null; onViewDetail?: (date: string) => void }) {
  if (!summary) {
    return (
      <Card style={fullWidthStyle}>
        <h2 style={sectionHeadingStyle}>Today's Summary</h2>
        <p style={emptyTextStyle}>
          No daily summary yet — check back after a session
        </p>
      </Card>
    )
  }

  const moodVariant = MOOD_VARIANT[summary.overall_mood] ?? 'neutral'
  const dateLabel = new Date(summary.summary_date + 'T00:00:00').toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

  return (
    <Card style={fullWidthStyle}>
      <div style={dailyHeaderStyle}>
        <h2 style={{ ...sectionHeadingStyle, margin: 0 }}>Today's Summary</h2>
        <div style={dailyMetaStyle}>
          <Badge variant={moodVariant}>{summary.overall_mood}</Badge>
          <span style={dailyDateStyle}>{dateLabel}</span>
        </div>
      </div>

      <p style={narrativeStyle}>{summary.narrative}</p>

      {onViewDetail && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onViewDetail(summary.summary_date)}
        >
          <span aria-label="View full daily summary">View full summary →</span>
        </Button>
      )}

      {summary.trend_alerts.length > 0 && (
        <div role="alert" style={{ marginTop: 'var(--space-sm)' }}>
          <h3 style={dailySectionTitleStyle}>Trends to Watch</h3>
          <ul style={alertListStyle}>
            {summary.trend_alerts.map((alert, i) => (
              <li key={i} style={alertItemStyle}>
                <span aria-hidden="true">!</span>
                {alert}
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.appointment_prep.length > 0 && (
        <div style={{ marginTop: 'var(--space-sm)' }}>
          <h3 style={dailySectionTitleStyle}>Bring Up at Next Appointment</h3>
          <ul style={prepListStyle}>
            {summary.appointment_prep.map((item, i) => (
              <li key={i} style={prepItemStyle}>
                <span aria-hidden="true">&#9744;</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.key_topics.length > 0 && (
        <div style={{ marginTop: 'var(--space-sm)' }}>
          <h3 style={dailySectionTitleStyle}>Topics Today</h3>
          <div style={topicChipsStyle}>
            {summary.key_topics.map((topic, i) => (
              <Badge key={i} variant="neutral">{topic}</Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}

interface CaregiverDashboardProps {
  onLogout: () => void
  /** Navigate to a named view (e.g. 'knowledge-graph', 'progress'). */
  onNavigate?: (view: string) => void
  /** Navigate to a specific session summary. */
  onViewSession?: (sessionId: string) => void
  /** Navigate to a specific daily summary. */
  onViewDailySummary?: (date: string) => void
}

export function CaregiverDashboard({ onLogout, onNavigate, onViewSession, onViewDailySummary }: CaregiverDashboardProps) {
  const [data, setData] = useState<CaregiverOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeBoardId, setActiveBoardId] = useState<string | null>(null)

  const { circles, selectedCircle, selectCircle, refresh } = useCircles()

  const fetchData = useCallback(async () => {
    if (!selectedCircle) {
      setLoading(false)
      return
    }
    try {
      const overview = await getCaregiverOverviewForPatient(selectedCircle.patient_id)
      setData(overview)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [selectedCircle])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60_000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (activeBoardId) {
    return (
      <div style={dashboardStyle}>
        <BoardView boardId={activeBoardId} onBack={() => setActiveBoardId(null)} />
      </div>
    )
  }

  if (loading) {
    return (
      <div style={dashboardStyle} role="status" aria-label="Loading dashboard">
        <SkeletonList count={6} gap="var(--space-md)" />
      </div>
    )
  }

  if (!selectedCircle) {
    return (
      <div style={dashboardStyle}>
        <header style={headerStyle} className="ada-caregiver-header">
          <div style={headerLeftStyle}>
            <h1 style={titleStyle}>Ada Caregiver Dashboard</h1>
          </div>
          <Button variant="secondary" size="sm" onClick={onLogout}>
            Sign out
          </Button>
        </header>
        <CircleSetupWizard onComplete={() => refresh()} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div style={dashboardStyle} role="alert">
        <ErrorState
          title="Couldn't load dashboard"
          message={error ?? 'Something went wrong'}
          onRetry={fetchData}
        />
      </div>
    )
  }

  const hasCrisisAlerts = data.crisis_alerts.length > 0

  return (
    <div style={dashboardStyle}>
      {/* Header */}
      <header style={headerStyle} className="ada-caregiver-header">
        <div style={headerLeftStyle}>
          <h1 style={titleStyle}>Ada Caregiver Dashboard</h1>
          <p style={patientNameStyle}>{data.patient.name}</p>
        </div>
        <div style={headerRightStyle}>
          <CircleSelector circles={circles} selected={selectedCircle} onSelect={selectCircle} />
          <NotificationBell />
          <Button variant="secondary" size="sm" onClick={onLogout}>
            Sign out
          </Button>
        </div>
      </header>

      {/* Dashboard grid */}
      <div style={gridStyle}>
        {/* Alerts Card — prominent at top if crisis alerts exist */}
        <div style={fullWidthStyle} {...(hasCrisisAlerts ? { role: 'alert' } : {})}>
          <Card style={{
            ...(hasCrisisAlerts ? {
              border: '2px solid var(--color-danger)',
            } : {}),
          }}>
            <AlertsCard alerts={data.crisis_alerts} />
          </Card>
        </div>

        {/* Daily Summary */}
        <DailySummaryCard summary={data.daily_summary} onViewDetail={onViewDailySummary} />

        {/* Status Card */}
        <Card>
          <StatusCard sessions={data.recent_sessions} who5Scores={data.assessments.who5} />
        </Card>

        {/* Sessions Card */}
        <Card>
          <SessionsCard sessions={data.recent_sessions} onViewSession={onViewSession} />
        </Card>

        {/* Wellbeing Chart — full width */}
        <section aria-label="Wellbeing" style={fullWidthStyle}>
          <Card>
            <WellbeingChart who5Scores={data.assessments.who5} />
          </Card>
        </section>

        {/* Knowledge Map */}
        {onNavigate && (
          <Card onClick={() => onNavigate('knowledge-graph')}>
            <div
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && onNavigate('knowledge-graph')}
              aria-label="View knowledge map"
            >
              <h2 style={sectionHeadingStyle}>Knowledge Map</h2>
              <p style={cardDescStyle}>Visualize patient topics, symptoms, and their connections</p>
            </div>
          </Card>
        )}

        {/* Progress Report */}
        {onNavigate && (
          <Card onClick={() => onNavigate('progress')}>
            <div
              role="button"
              tabIndex={0}
              onKeyDown={e => e.key === 'Enter' && onNavigate('progress')}
              aria-label="View progress report"
            >
              <h2 style={sectionHeadingStyle}>Progress Report</h2>
              <p style={cardDescStyle}>Review trends in wellbeing, assessments, and adherence</p>
            </div>
          </Card>
        )}

        {/* Cognitive Screenings */}
        {onNavigate && (
          <Card>
            <h2 style={sectionHeadingStyle}>Cognitive Screenings</h2>
            <p style={cardDescStyle}>Track memory, attention, and cognitive function over time</p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onNavigate('screening-history')}
            >
              <span aria-label="View cognitive screening history">View Screening History →</span>
            </Button>
          </Card>
        )}

        {/* Treatment Plans — clinician role */}
        {onNavigate && selectedCircle.my_role === 'clinician' && (
          <Card>
            <h2 style={sectionHeadingStyle}>Treatment Plans</h2>
            <p style={cardDescStyle}>
              {data.active_plan_count != null && data.active_plan_count > 0
                ? `${data.active_plan_count} active plan${data.active_plan_count !== 1 ? 's' : ''}`
                : 'No active plans'}
            </p>
            <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onNavigate('treatment-plan')}
              >
                <span aria-label="View treatment plans">View Plans →</span>
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onNavigate('prescribing-notes')}
              >
                <span aria-label="View prescribing notes">Prescribing Notes →</span>
              </Button>
            </div>
          </Card>
        )}

        {/* Care Team */}
        {selectedCircle && (
          <Card>
            <CircleMembers
              circleId={selectedCircle.id}
              currentUserRole={selectedCircle.my_role}
            />
          </Card>
        )}

        {/* Shared Boards */}
        {selectedCircle && (
          <Card>
            <BoardList circleId={selectedCircle.id} onSelectBoard={setActiveBoardId} />
          </Card>
        )}

        {/* Medications */}
        <Card>
          <MedicationCard patientId={selectedCircle.patient_id} />
        </Card>

        {/* Appointments */}
        <Card>
          <AppointmentCard patientId={selectedCircle.patient_id} />
        </Card>

        {/* Settings */}
        {onNavigate && (
          <Card onClick={() => onNavigate('settings')}>
            <div
              role="button"
              tabIndex={0}
              data-testid="caregiver-settings-entry"
              onKeyDown={e => e.key === 'Enter' && onNavigate('settings')}
              aria-label="Open settings"
            >
              <h2 style={sectionHeadingStyle}>Settings</h2>
              <p style={cardDescStyle}>Companion preferences, account, and admin tooling</p>
            </div>
          </Card>
        )}
      </div>
    </div>
  )
}
