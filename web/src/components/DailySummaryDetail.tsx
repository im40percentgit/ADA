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
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { SkeletonCard } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'
import { ErrorState } from './ui/ErrorState'

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
  positive: 'var(--color-success)',
  neutral: 'var(--color-text-muted)',
  negative: 'var(--color-danger)',
  anxious: 'var(--color-warning)',
  depressed: 'var(--color-primary-light)',
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
      <div className="patient-dash" aria-busy="true" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        <SkeletonCard lines={3} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="patient-dash" style={{ fontFamily: 'var(--font-body)' }}>
        <ErrorState
          title="Could not load daily summary"
          message={error}
          action={<Button variant="secondary" onClick={onBack}>Go back</Button>}
        />
      </div>
    )
  }

  if (!data) {
    return (
      <div className="patient-dash" style={{ fontFamily: 'var(--font-body)' }}>
        <EmptyState
          icon="📓"
          title="No summary available"
          description="This day has no recorded sessions."
          tone="neutral"
          action={<Button variant="secondary" onClick={onBack}>Go back</Button>}
        />
      </div>
    )
  }

  const moodColor = MOOD_COLORS[data.overall_mood.toLowerCase()] ?? 'var(--color-text-muted)'

  return (
    <div className="patient-dash" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
      {/* Back button */}
      <Button
        variant="secondary"
        size="sm"
        onClick={onBack}
        className="med-card__btn"
      >
        Back
      </Button>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-md)', marginBottom: 'var(--space-md)', marginTop: 'var(--space-md)' }}>
        <h1 style={{ margin: 0, fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)' }}>{formatDate(date)}</h1>
        <span
          data-testid="overall-mood"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: '2px 8px',
            borderRadius: '10px',
            fontSize: 'var(--size-xs)',
            fontWeight: 600,
            color: moodColor,
            lineHeight: 1.4,
          }}
        >
          {data.overall_mood}
        </span>
      </div>

      {/* Narrative */}
      <Card style={{ borderLeft: '4px solid var(--color-warmth)', paddingLeft: 'var(--space-md)' }}>
        <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-sm)' }}>Daily Narrative</h2>
        <p style={{ margin: 0, lineHeight: 1.6, color: 'var(--color-text-secondary)' }}>{data.narrative}</p>
      </Card>

      {/* Trend alerts */}
      {data.trend_alerts.length > 0 && (
        <Card style={{ marginTop: 'var(--space-md)' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-sm)' }}>Trend Alerts</h2>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
            {data.trend_alerts.map((alert, i) => {
              const dirMatch = alert.match(/^(improving|declining|stable):\s*(.+)$/i)
              const direction = dirMatch ? dirMatch[1].toLowerCase() : 'stable'
              const alertText = dirMatch ? dirMatch[2] : alert

              return (
                <li key={i}>
                  <Card
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 'var(--space-sm)',
                      padding: 'var(--space-sm) var(--space-md)',
                    }}
                  >
                    <span
                      data-testid="trend-alert"
                      style={{
                        fontSize: 'var(--size-xs)',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        color:
                          direction === 'improving'
                            ? 'var(--color-success)'
                            : direction === 'declining'
                              ? 'var(--color-danger)'
                              : 'var(--color-text-muted)',
                      }}
                    >
                      {TREND_ICONS[direction] ?? 'Stable'}
                    </span>
                    <span style={{ fontSize: 'var(--size-sm)', color: 'var(--color-text-secondary)' }}>{alertText}</span>
                  </Card>
                </li>
              )
            })}
          </ul>
        </Card>
      )}

      {/* Key topics */}
      {data.key_topics.length > 0 && (
        <Card style={{ marginTop: 'var(--space-md)' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-sm)' }}>Key Topics</h2>
          <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
            {data.key_topics.map((topic, i) => (
              <Badge key={i} variant="info">{topic}</Badge>
            ))}
          </div>
        </Card>
      )}

      {/* Session links */}
      {sessionIds && sessionIds.length > 0 && (
        <Card style={{ marginTop: 'var(--space-md)' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-sm)' }}>Sessions</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-xs)' }}>
            {sessionIds.map((sid) => (
              <button
                key={sid}
                type="button"
                className="med-card__btn med-card__btn--secondary"
                onClick={() => onViewSession(sid)}
                style={{
                  textAlign: 'left',
                  background: 'var(--color-bg-elevated)',
                  color: 'var(--color-text-primary)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-button)',
                  padding: 'var(--space-sm) var(--space-md)',
                  minHeight: 'var(--touch-target-min)',
                  fontFamily: 'var(--font-body)',
                  cursor: 'pointer',
                }}
                data-testid="session-link"
              >
                View Session {sid}
              </button>
            ))}
          </div>
        </Card>
      )}

      {/* Clinician Notes */}
      {data.id && (
        <div style={{ marginTop: 'var(--space-md)' }}>
          <ClinicianNotes entityType="daily_summary" entityId={data.id} role={role} />
        </div>
      )}
    </div>
  )
}
