/**
 * CaregiverDashboard — main container for the caregiver view.
 *
 * Fetches aggregated patient data from GET /api/caregiver/overview on mount,
 * then polls every 60 seconds. Renders StatusCard, AlertsCard, SessionsCard,
 * WellbeingChart, plus medications and appointments sections.
 *
 * @decision DEC-FRONTEND-020
 * @title CaregiverDashboard polls at 60s interval — no WebSocket
 * @status accepted
 * @rationale The caregiver dashboard is a read-only summary view. Real-time
 *   streaming (WebSocket) is reserved for the patient chat experience. A 60s
 *   polling interval provides adequate freshness for status monitoring while
 *   keeping the implementation simple and server load minimal.
 */

import { useEffect, useState, useCallback } from 'react'
import { getCaregiverOverview } from '../api/client'
import type { CaregiverOverview } from '../types'
import { StatusCard } from './StatusCard'
import { AlertsCard } from './AlertsCard'
import { SessionsCard } from './SessionsCard'
import { WellbeingChart } from './WellbeingChart'

interface CaregiverDashboardProps {
  onLogout: () => void
}

export function CaregiverDashboard({ onLogout }: CaregiverDashboardProps) {
  const [data, setData] = useState<CaregiverOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const overview = await getCaregiverOverview()
      setData(overview)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 60_000)
    return () => clearInterval(interval)
  }, [fetchData])

  if (loading) {
    return (
      <div className="cg-dashboard cg-dashboard--loading" role="status" aria-label="Loading dashboard">
        <div className="app__loading-spinner" />
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
        <button className="cg-dashboard__logout" onClick={onLogout} type="button">
          Sign out
        </button>
      </header>

      {/* Dashboard grid */}
      <div className="cg-dashboard__grid">
        <StatusCard sessions={data.recent_sessions} who5Scores={data.assessments.who5} />
        <AlertsCard alerts={data.crisis_alerts} />
        <SessionsCard sessions={data.recent_sessions} />
        <WellbeingChart who5Scores={data.assessments.who5} />

        {/* Medications */}
        <section className="cg-card cg-meds" aria-label="Medications">
          <h2 className="cg-card__title">Medications</h2>
          {data.medications.length === 0 ? (
            <p className="cg-card__empty">No medications recorded</p>
          ) : (
            <ul className="cg-meds__list">
              {data.medications.map((m, i) => (
                <li key={i} className={`cg-meds__item${!m.active ? ' cg-meds__item--inactive' : ''}`}>
                  <span className="cg-meds__name">{m.name}</span>
                  {m.dosage && <span className="cg-meds__dosage">{m.dosage}</span>}
                  {m.frequency && <span className="cg-meds__freq">{m.frequency}</span>}
                  {!m.active && <span className="cg-meds__badge">Discontinued</span>}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Appointments */}
        <section className="cg-card cg-appts" aria-label="Appointments">
          <h2 className="cg-card__title">Upcoming Appointments</h2>
          {data.appointments.length === 0 ? (
            <p className="cg-card__empty">No upcoming appointments</p>
          ) : (
            <ul className="cg-appts__list">
              {data.appointments.map((a, i) => (
                <li key={i} className="cg-appts__item">
                  <span className="cg-appts__title">{a.title}</span>
                  <span className="cg-appts__time">
                    {new Date(a.scheduled_at).toLocaleDateString([], {
                      month: 'short',
                      day: 'numeric',
                      hour: 'numeric',
                      minute: '2-digit',
                    })}
                  </span>
                  <span className={`cg-appts__status cg-appts__status--${a.status}`}>
                    {a.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
