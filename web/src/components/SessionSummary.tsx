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
import { usePdfExport } from '../hooks/usePdfExport'
import type { SessionSummaryData } from '../types'
import { ClinicianNotes } from './ClinicianNotes'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'

interface SessionSummaryProps {
  sessionId: string
  onBack: () => void
  /** Current user role — passed through to ClinicianNotes */
  role?: string
}

const SEVERITY_STYLES: Record<string, { background: string; color: string; fontWeight?: number }> = {
  LOW: { background: 'var(--color-bg-elevated)', color: 'var(--color-text-muted)' },
  MODERATE: { background: '#451a03', color: 'var(--color-warning)' },
  HIGH: { background: '#450a0a', color: 'var(--color-danger)' },
  CRITICAL: { background: '#450a0a', color: 'var(--color-danger)', fontWeight: 700 },
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
  const { exportToPdf, exporting } = usePdfExport()

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
      <div className="patient-dash" aria-busy="true" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        Loading session summary...
      </div>
    )
  }

  if (error) {
    return (
      <div className="patient-dash" role="alert" style={{ fontFamily: 'var(--font-body)' }}>
        <p className="patient-dash__error" style={{ color: 'var(--color-danger)' }}>{error}</p>
        <Button variant="secondary" onClick={onBack}>Back</Button>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="patient-dash" style={{ fontFamily: 'var(--font-body)' }}>
        <p className="patient-dash__empty" style={{ color: 'var(--color-text-muted)' }}>No summary available</p>
        <Button variant="secondary" onClick={onBack}>Back</Button>
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
    <div className="patient-dash" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
      {/* Back button + PDF export */}
      <div style={{ display: 'flex', gap: 'var(--space-sm)', alignItems: 'center' }}>
        <Button
          variant="secondary"
          size="sm"
          onClick={onBack}
          className="med-card__btn"
        >
          Back
        </Button>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => exportToPdf('export-session-summary', `session-summary-${sessionId}.pdf`)}
          disabled={exporting}
        >
          {exporting ? 'Exporting...' : 'Download PDF'}
        </Button>
      </div>

      <div id="export-session-summary">
      {/* Header */}
      <h1 style={{ margin: 'var(--space-md) 0', fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)' }}>
        Session — {formatDate(data.created_at)}
      </h1>

      {/* SOAP cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 'var(--space-md)',
        }}
      >
        {soapSections.map((s) => (
          <section key={s.title} aria-label={s.title}>
            <Card>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-sm)' }}>{s.title}</h2>
              <p style={{ margin: 0, lineHeight: 1.6, color: 'var(--color-text-secondary)' }}>{s.content}</p>
            </Card>
          </section>
        ))}
      </div>

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

      {/* Risk flags */}
      {data.risk_flags.length > 0 && (
        <Card style={{ marginTop: 'var(--space-md)' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-sm)' }}>Risk Flags</h2>
          <div style={{ display: 'flex', gap: 'var(--space-sm)', flexWrap: 'wrap' }}>
            {data.risk_flags.map((flag, i) => {
              const { severity, text } = parseSeverity(flag)
              const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.MODERATE
              const isUrgent = severity === 'HIGH' || severity === 'CRITICAL'
              return (
                <span
                  key={i}
                  data-testid="risk-flag"
                  {...(isUrgent ? { role: 'alert' } : {})}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '2px 8px',
                    borderRadius: '10px',
                    fontSize: 'var(--size-xs)',
                    fontWeight: style.fontWeight ?? 600,
                    background: style.background,
                    color: style.color,
                    lineHeight: 1.4,
                  }}
                >
                  {severity}: {text}
                </span>
              )
            })}
          </div>
        </Card>
      )}

      {/* Clinician Notes */}
      <div style={{ marginTop: 'var(--space-md)' }}>
        <ClinicianNotes entityType="session_summary" entityId={sessionId} role={role} />
      </div>
      </div>
    </div>
  )
}
