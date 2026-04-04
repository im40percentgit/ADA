/**
 * SessionSummary — SOAP note detail viewer for a single session.
 *
 * Fetches the session summary on mount and renders:
 *   - Header with session date
 *   - Four SOAP cards: Subjective, Objective, Assessment, Plan
 *   - Key topics as colored tag chips
 *   - Risk flags as severity badges (LOW=gray, MODERATE=amber, HIGH=red, CRITICAL=red bold)
 *   - ClinicianNotes annotation section at bottom
 *
 * @decision DEC-FRONTEND-061
 * @title SessionSummary fetches data directly, no hook extraction
 * @status accepted
 * @rationale The component has a simple single-fetch lifecycle with no
 *   re-fetch triggers (unlike ProgressReport which has time range state).
 *   Extracting a hook would add a file with no reuse benefit at this stage.
 */

import { useState, useEffect } from 'react'
import { getSessionSummary } from '../api/client'
import type { SessionSummaryData } from '../types'
import { ClinicianNotes } from './ClinicianNotes'

interface SessionSummaryProps {
  sessionId: string
  onBack: () => void
  /** Current user role — passed through to ClinicianNotes */
  role?: string
}

const SEVERITY_STYLES: Record<string, { background: string; color: string; fontWeight?: number }> = {
  LOW: { background: '#e5e7eb', color: '#374151' },
  MODERATE: { background: '#fef3c7', color: '#92400e' },
  HIGH: { background: '#fee2e2', color: '#991b1b' },
  CRITICAL: { background: '#fee2e2', color: '#991b1b', fontWeight: 700 },
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

/** Extract severity keyword from a risk flag string (e.g. "HIGH: suicidal ideation") */
function parseSeverity(flag: string): { severity: string; text: string } {
  const match = flag.match(/^(LOW|MODERATE|HIGH|CRITICAL):\s*(.+)$/i)
  if (match) {
    return { severity: match[1].toUpperCase(), text: match[2] }
  }
  return { severity: 'MODERATE', text: flag }
}

export function SessionSummary({ sessionId, onBack, role }: SessionSummaryProps) {
  const [data, setData] = useState<SessionSummaryData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getSessionSummary(sessionId)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load session summary')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId])

  if (loading) {
    return (
      <div className="patient-dash" aria-busy="true">
        Loading session summary...
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
        <p className="patient-dash__empty">No summary available</p>
        <button type="button" className="med-card__btn med-card__btn--secondary" onClick={onBack}>
          Back
        </button>
      </div>
    )
  }

  const soapSections = [
    { title: 'Subjective', content: data.subjective },
    { title: 'Objective', content: data.objective },
    { title: 'Assessment', content: data.assessment },
    { title: 'Plan', content: data.plan },
  ]

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
      <h2 style={{ margin: '0 0 16px' }}>
        Session — {formatDate(data.created_at)}
      </h2>

      {/* SOAP cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: '16px',
        }}
      >
        {soapSections.map((s) => (
          <div key={s.title} className="patient-dash__card">
            <h3>{s.title}</h3>
            <p style={{ margin: 0, lineHeight: 1.6 }}>{s.content}</p>
          </div>
        ))}
      </div>

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

      {/* Risk flags */}
      {data.risk_flags.length > 0 && (
        <div className="patient-dash__card patient-dash__card--full" style={{ marginTop: '16px' }}>
          <h3>Risk Flags</h3>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {data.risk_flags.map((flag, i) => {
              const { severity, text } = parseSeverity(flag)
              const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.MODERATE
              return (
                <span
                  key={i}
                  data-testid="risk-flag"
                  style={{
                    padding: '4px 12px',
                    borderRadius: '16px',
                    fontSize: '13px',
                    fontWeight: style.fontWeight ?? 500,
                    background: style.background,
                    color: style.color,
                  }}
                >
                  {severity}: {text}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* Clinician Notes */}
      <div style={{ marginTop: '16px' }}>
        <ClinicianNotes entityType="session_summary" entityId={sessionId} role={role} />
      </div>
    </div>
  )
}
