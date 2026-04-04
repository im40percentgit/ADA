/**
 * CaregiverDashboard — main container for the caregiver view.
 *
 * Fetches aggregated patient data from GET /api/caregiver/overview on mount,
 * then polls every 60 seconds. Renders StatusCard, AlertsCard, SessionsCard,
 * WellbeingChart, DailySummaryCard, plus medications and appointments sections.
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
 */

import { useEffect, useState, useCallback } from 'react'
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

// ---------------------------------------------------------------------------
// DailySummaryCard
// ---------------------------------------------------------------------------

const MOOD_CLASS: Record<string, string> = {
  anxious: 'cg-daily__mood--anxious',
  depressed: 'cg-daily__mood--depressed',
  stable: 'cg-daily__mood--stable',
  improving: 'cg-daily__mood--improving',
  declining: 'cg-daily__mood--declining',
  mixed: 'cg-daily__mood--mixed',
}

function DailySummaryCard({ summary, onViewDetail }: { summary: DailySummary | null; onViewDetail?: (date: string) => void }) {
  if (!summary) {
    return (
      <section className="cg-card cg-daily" aria-label="Daily Summary">
        <h2 className="cg-card__title">Today's Summary</h2>
        <p className="cg-card__empty">
          No daily summary yet — check back after a session
        </p>
      </section>
    )
  }

  const moodClass = MOOD_CLASS[summary.overall_mood] ?? 'cg-daily__mood--stable'
  const dateLabel = new Date(summary.summary_date + 'T00:00:00').toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  })

  return (
    <section className="cg-card cg-daily" aria-label="Daily Summary">
      <div className="cg-daily__header">
        <h2 className="cg-card__title">Today's Summary</h2>
        <div className="cg-daily__meta">
          <span className={`cg-daily__mood ${moodClass}`}>{summary.overall_mood}</span>
          <span className="cg-daily__date">{dateLabel}</span>
        </div>
      </div>

      <p className="cg-daily__narrative">{summary.narrative}</p>

      {onViewDetail && (
        <button
          type="button"
          className="cg-daily__view-detail"
          onClick={() => onViewDetail(summary.summary_date)}
          aria-label="View full daily summary"
        >
          View full summary &rarr;
        </button>
      )}

      {summary.trend_alerts.length > 0 && (
        <div className="cg-daily__alerts" role="alert">
          <h3 className="cg-daily__section-title">Trends to Watch</h3>
          <ul className="cg-daily__alert-list">
            {summary.trend_alerts.map((alert, i) => (
              <li key={i} className="cg-daily__alert-item">
                <span className="cg-daily__alert-icon" aria-hidden="true">!</span>
                {alert}
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.appointment_prep.length > 0 && (
        <div className="cg-daily__prep">
          <h3 className="cg-daily__section-title">Bring Up at Next Appointment</h3>
          <ul className="cg-daily__prep-list">
            {summary.appointment_prep.map((item, i) => (
              <li key={i} className="cg-daily__prep-item">
                <span className="cg-daily__prep-check" aria-hidden="true">&#9744;</span>
                {item}
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary.key_topics.length > 0 && (
        <div className="cg-daily__topics">
          <h3 className="cg-daily__section-title">Topics Today</h3>
          <div className="cg-daily__topic-chips">
            {summary.key_topics.map((topic, i) => (
              <span key={i} className="cg-daily__topic-chip">{topic}</span>
            ))}
          </div>
        </div>
      )}
    </section>
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
      <div className="caregiver-dashboard">
        <BoardView boardId={activeBoardId} onBack={() => setActiveBoardId(null)} />
      </div>
    )
  }

  if (loading) {
    return (
      <div className="cg-dashboard cg-dashboard--loading" role="status" aria-label="Loading dashboard">
        <div className="app__loading-spinner" />
      </div>
    )
  }

  if (!selectedCircle) {
    return (
      <div className="cg-dashboard">
        <header className="cg-dashboard__header">
          <div>
            <h1 className="cg-dashboard__title">Ada Caregiver Dashboard</h1>
          </div>
          <button className="cg-dashboard__sign-out" onClick={onLogout} type="button">
            Sign out
          </button>
        </header>
        <CircleSetupWizard onComplete={() => refresh()} />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="cg-dashboard cg-dashboard--error" role="alert">
        <p>{error ?? 'Something went wrong'}</p>
        <button className="cg-dashboard__retry" onClick={fetchData} type="button">
          Try Again
        </button>
      </div>
    )
  }

  return (
    <div className="cg-dashboard">
      {/* Header */}
      <header className="cg-dashboard__header">
        <div>
          <h1 className="cg-dashboard__title">Ada Caregiver Dashboard</h1>
          <p className="cg-dashboard__patient-name">{data.patient.name}</p>
        </div>
        <CircleSelector circles={circles} selected={selectedCircle} onSelect={selectCircle} />
        <NotificationBell />
        <button className="cg-dashboard__logout" onClick={onLogout} type="button">
          Sign out
        </button>
      </header>

      {/* Dashboard grid */}
      <div className="cg-dashboard__grid">
        <DailySummaryCard summary={data.daily_summary} onViewDetail={onViewDailySummary} />
        <StatusCard sessions={data.recent_sessions} who5Scores={data.assessments.who5} />
        <AlertsCard alerts={data.crisis_alerts} />
        <SessionsCard sessions={data.recent_sessions} onViewSession={onViewSession} />
        <WellbeingChart who5Scores={data.assessments.who5} />

        {/* Knowledge Map */}
        {onNavigate && (
          <section
            className="cg-card cg-card--clickable"
            onClick={() => onNavigate('knowledge-graph')}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && onNavigate('knowledge-graph')}
            aria-label="View knowledge map"
          >
            <h2 className="cg-card__title">Knowledge Map</h2>
            <p className="cg-card__desc">Visualize patient topics, symptoms, and their connections</p>
          </section>
        )}

        {/* Progress Report */}
        {onNavigate && (
          <section
            className="cg-card cg-card--clickable"
            onClick={() => onNavigate('progress')}
            role="button"
            tabIndex={0}
            onKeyDown={e => e.key === 'Enter' && onNavigate('progress')}
            aria-label="View progress report"
          >
            <h2 className="cg-card__title">Progress Report</h2>
            <p className="cg-card__desc">Review trends in wellbeing, assessments, and adherence</p>
          </section>
        )}

        {/* Care Team */}
        {selectedCircle && (
          <section className="cg-card" aria-label="Care Team">
            <CircleMembers
              circleId={selectedCircle.id}
              currentUserRole={selectedCircle.my_role}
            />
          </section>
        )}

        {/* Shared Boards */}
        {selectedCircle && (
          <section className="cg-card" aria-label="Shared Boards">
            <BoardList circleId={selectedCircle.id} onSelectBoard={setActiveBoardId} />
          </section>
        )}

        {/* Medications */}
        <section className="cg-dashboard__card">
          <MedicationCard patientId={selectedCircle.patient_id} />
        </section>

        {/* Appointments */}
        <section className="cg-dashboard__card">
          <AppointmentCard patientId={selectedCircle.patient_id} />
        </section>
      </div>
    </div>
  )
}
