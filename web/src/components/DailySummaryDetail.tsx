/**
 * DailySummaryDetail — daily narrative detail viewer.
 *
 * Fetches the daily summary for a patient+date on mount and renders:
 *   - Header with date and overall mood
 *   - Full narrative paragraph
 *   - Trend alerts as cards (direction + text)
 *   - Key topics as colored chips
 *   - Session links (clickable, calls onViewSession)
 *   - ClinicianNotes annotation section at bottom
 *
 * @decision DEC-FRONTEND-062
 * @title DailySummaryDetail derives session links from appointment_prep field
 * @status accepted
 * @rationale The DailySummary type does not include explicit session IDs.
 *   The appointment_prep field may contain session references. Rather than
 *   overloading this, we render session links only if the parent provides
 *   them via an optional prop. The onViewSession callback enables navigation
 *   to SessionSummary from any session reference.
 */

import { useState, useEffect } from 'react'
import { getDailySummary } from '../api/client'
import type { DailySummary } from '../types'
import { ClinicianNotes } from './ClinicianNotes'

interface DailySummaryDetailProps {
  patientId: string
  date: string
  onBack: () => void
  onViewSession: (sessionId: string) => void
  /** Optional list of session IDs that occurred on this day */
  sessionIds?: string[]
  /** Current user role — passed through to ClinicianNotes */
  role?: string
}

const MOOD_COLORS: Record<string, string> = {
  positive: '#10b981',
  neutral: '#6b7280',
  negative: '#ef4444',
  anxious: '#f59e0b',
  depressed: '#8b5cf6',
}

const TREND_ICONS: Record<string, string> = {
  improving: 'Improving',
  declining: 'Declining',
  stable: 'Stable',
}

function formatDate(dateStr: string): string {
  return new Date(dateStr + 'T00:00:00').toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

export function DailySummaryDetail({
  patientId,
  date,
  onBack,
  onViewSession,
  sessionIds,
  role,
}: DailySummaryDetailProps) {
  const [data, setData] = useState<DailySummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getDailySummary(patientId, date)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load daily summary')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [patientId, date])

  if (loading) {
    return (
      <div className="patient-dash" aria-busy="true">
        Loading daily summary...
      </div>
    )
  }

  if (error) {
    return (
      <div className="patient-dash" role="alert">
        <p className="patient-dash__error">{error}</p>
        <button type="button" className="med-card__btn med-card__btn--secondary" onClick={onBack}>
          Back
        </button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="patient-dash">
        <p className="patient-dash__empty">No summary available for this date</p>
        <button type="button" className="med-card__btn med-card__btn--secondary" onClick={onBack}>
          Back
        </button>
      </div>
    )
  }

  const moodColor = MOOD_COLORS[data.overall_mood.toLowerCase()] ?? '#6b7280'

  return (
    <div className="patient-dash">
      {/* Back button */}
      <button
        type="button"
        className="med-card__btn med-card__btn--secondary"
        onClick={onBack}
        style={{ alignSelf: 'flex-start', marginBottom: '12px' }}
      >
        Back
      </button>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        <h2 style={{ margin: 0 }}>{formatDate(date)}</h2>
        <span
          data-testid="overall-mood"
          style={{
            padding: '4px 12px',
            borderRadius: '16px',
            fontSize: '13px',
            fontWeight: 600,
            background: moodColor + '20',
            color: moodColor,
          }}
        >
          {data.overall_mood}
        </span>
      </div>

      {/* Narrative */}
      <div
        className="patient-dash__card patient-dash__card--full"
        style={{ borderLeft: '4px solid #3b82f6', paddingLeft: '16px' }}
      >
        <h3>Daily Narrative</h3>
        <p style={{ margin: 0, lineHeight: 1.6 }}>{data.narrative}</p>
      </div>

      {/* Trend alerts */}
      {data.trend_alerts.length > 0 && (
        <div className="patient-dash__card patient-dash__card--full" style={{ marginTop: '16px' }}>
          <h3>Trend Alerts</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {data.trend_alerts.map((alert, i) => {
              // Try to parse direction from the alert string (e.g., "improving: sleep quality")
              const dirMatch = alert.match(/^(improving|declining|stable):\s*(.+)$/i)
              const direction = dirMatch ? dirMatch[1].toLowerCase() : 'stable'
              const alertText = dirMatch ? dirMatch[2] : alert

              return (
                <div
                  key={i}
                  data-testid="trend-alert"
                  style={{
                    padding: '10px 14px',
                    borderRadius: '8px',
                    background: '#f9fafb',
                    border: '1px solid #e5e7eb',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <span
                    style={{
                      fontSize: '12px',
                      fontWeight: 600,
                      textTransform: 'uppercase',
                      color:
                        direction === 'improving'
                          ? '#059669'
                          : direction === 'declining'
                            ? '#dc2626'
                            : '#6b7280',
                    }}
                  >
                    {TREND_ICONS[direction] ?? 'Stable'}
                  </span>
                  <span style={{ fontSize: '14px' }}>{alertText}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Key topics */}
      {data.key_topics.length > 0 && (
        <div className="patient-dash__card patient-dash__card--full" style={{ marginTop: '16px' }}>
          <h3>Key Topics</h3>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {data.key_topics.map((topic, i) => (
              <span
                key={i}
                style={{
                  padding: '4px 12px',
                  borderRadius: '16px',
                  fontSize: '13px',
                  fontWeight: 500,
                  background: '#ede9fe',
                  color: '#5b21b6',
                }}
              >
                {topic}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Session links */}
      {sessionIds && sessionIds.length > 0 && (
        <div className="patient-dash__card patient-dash__card--full" style={{ marginTop: '16px' }}>
          <h3>Sessions</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {sessionIds.map((sid) => (
              <button
                key={sid}
                type="button"
                className="med-card__btn med-card__btn--secondary"
                onClick={() => onViewSession(sid)}
                style={{ textAlign: 'left' }}
                data-testid="session-link"
              >
                View Session {sid}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Clinician Notes */}
      {data.id && (
        <div style={{ marginTop: '16px' }}>
          <ClinicianNotes entityType="daily_summary" entityId={data.id} role={role} />
        </div>
      )}
    </div>
  )
}
