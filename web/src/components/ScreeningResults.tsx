/**
 * ScreeningResults — detailed viewer for a completed cognitive screening.
 *
 * Fetches a single CognitiveScreening by (patientId, screeningId) on mount.
 * Renders:
 *   1. Header: date, task count, duration, overall score (0-100, prominent)
 *   2. Domain scores: horizontal bar chart per domain with colour coding
 *   3. Clinical concerns: amber-bordered card listing concern strings
 *   4. Task breakdown: expandable rows with domain badge, prompt, score, response
 *   5. Clinician Notes: ClinicianNotes widget at bottom
 *
 * Domain bar colour: green ≥70%, amber 40-69%, red <40%.
 * Bar width maps avg_score/2 to a 0-100% scale (max task score = 2).
 *
 * @decision DEC-FRONTEND-065
 * @title ScreeningResults fetches directly — no custom hook
 * @status accepted
 * @rationale Single-fetch lifecycle with no re-fetch triggers; extracting a
 *   hook would add indirection without reuse benefit, matching the SessionSummary
 *   precedent (DEC-FRONTEND-061).
 */

import { useState, useEffect } from 'react'
import { getCognitiveScreening } from '../api/client'
import { usePdfExport } from '../hooks/usePdfExport'
import type { CognitiveScreening } from '../types'
import { ClinicianNotes } from './ClinicianNotes'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { ProgressBar } from './ui/ProgressBar'

interface ScreeningResultsProps {
  patientId: string
  screeningId: string
  onBack: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString([], {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatDuration(startedAt: string, completedAt: string | null): string {
  if (!completedAt) return '—'
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime()
  const totalSeconds = Math.round(ms / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  if (minutes === 0) return `${seconds}s`
  return `${minutes}m ${seconds}s`
}

/** Convert avg_score (0-2 scale) to a percentage width (0-100%) */
function domainBarWidth(avgScore: number): string {
  return `${Math.min(100, Math.max(0, (avgScore / 2) * 100)).toFixed(1)}%`
}

/** Colour band based on percentage equivalent of avg_score */
function domainBarColor(avgScore: number): string {
  const pct = (avgScore / 2) * 100
  if (pct >= 70) return '#16a34a' // green
  if (pct >= 40) return '#d97706' // amber
  return '#dc2626' // red
}

const SCORE_COLOR: Record<number, string> = {
  0: '#dc2626',
  1: '#d97706',
  2: '#16a34a',
}

const DOMAIN_BADGE_COLORS: Record<string, { background: string; color: string }> = {
  memory: { background: 'var(--color-primary-subtle)', color: 'var(--color-primary-light)' },
  attention: { background: '#1e3a5f', color: '#93c5fd' },
  language: { background: '#052e16', color: 'var(--color-success)' },
  visuospatial: { background: '#451a03', color: 'var(--color-warning)' },
  executive: { background: '#450a0a', color: 'var(--color-danger)' },
  orientation: { background: '#0c4a6e', color: '#7dd3fc' },
}

function domainBadgeStyle(domain: string): { background: string; color: string } {
  return DOMAIN_BADGE_COLORS[domain.toLowerCase()] ?? { background: '#f3f4f6', color: '#374151' }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface TaskRowProps {
  task: CognitiveScreening['tasks'][number]
  index: number
}

function TaskRow({ task, index }: TaskRowProps) {
  const [expanded, setExpanded] = useState(false)
  const badge = domainBadgeStyle(task.domain)
  const scoreColor = SCORE_COLOR[Math.round(task.score)] ?? 'var(--color-text-muted)'

  return (
    <div
      style={{
        borderBottom: '1px solid var(--color-border)',
        paddingBottom: 'var(--space-md)',
        marginBottom: 'var(--space-md)',
      }}
    >
      {/* Row header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-sm)',
          cursor: 'pointer',
          minHeight: 'var(--touch-target-min)',
        }}
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && setExpanded((v) => !v)}
        data-testid={`task-row-${index}`}
      >
        {/* Domain badge */}
        <span
          style={{
            padding: '2px 10px',
            borderRadius: '10px',
            fontSize: 'var(--size-xs)',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            background: badge.background,
            color: badge.color,
          }}
          data-testid="domain-badge"
        >
          {task.domain}
        </span>

        {/* Prompt */}
        <span style={{ flex: 1, fontSize: 'var(--size-sm)', color: 'var(--color-text-secondary)' }}>{task.prompt}</span>

        {/* Score */}
        <span
          style={{
            fontWeight: 700,
            fontSize: 'var(--size-body)',
            color: scoreColor,
            minWidth: '28px',
            textAlign: 'right',
          }}
          data-testid="task-score"
        >
          {task.score}
        </span>

        {/* Expand toggle */}
        <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--size-xs)' }}>{expanded ? '\u25B2' : '\u25BC'}</span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div
          style={{
            marginTop: 'var(--space-sm)',
            paddingLeft: 'var(--space-md)',
            borderLeft: '3px solid var(--color-border)',
          }}
        >
          <p style={{ margin: '0 0 6px', fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)' }}>
            <strong>Response:</strong> {task.response}
          </p>
          <p style={{ margin: 0, fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)' }}>
            <strong>Rationale:</strong> {task.rationale}
          </p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ScreeningResults({ patientId, screeningId, onBack }: ScreeningResultsProps) {
  const [data, setData] = useState<CognitiveScreening | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const { exportToPdf, exporting } = usePdfExport()

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getCognitiveScreening(patientId, screeningId)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load screening results')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [patientId, screeningId])

  if (loading) {
    return (
      <div className="patient-dash" aria-busy="true" style={{ fontFamily: 'var(--font-body)', color: 'var(--color-text-primary)' }}>
        Loading screening results...
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
        <p className="patient-dash__empty" style={{ color: 'var(--color-text-muted)' }}>No screening data available</p>
        <Button variant="secondary" onClick={onBack}>Back</Button>
      </div>
    )
  }

  const overallPct = data.overall_score != null ? Math.round(data.overall_score * 100) : null
  const domainEntries = Object.entries(data.domains)

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
          onClick={() => exportToPdf('export-screening-results', `screening-${screeningId}.pdf`)}
          disabled={exporting}
        >
          {exporting ? 'Exporting...' : 'Download PDF'}
        </Button>
      </div>

      <div id="export-screening-results">
      {/* Header card */}
      <Card style={{ marginTop: 'var(--space-md)' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 'var(--space-md)',
          }}
        >
          {/* Date + meta */}
          <div>
            <h1 style={{ margin: '0 0 4px', fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)' }}>Cognitive Screening</h1>
            <p style={{ margin: 0, color: 'var(--color-text-muted)', fontSize: 'var(--size-sm)' }}>
              {formatDate(data.started_at)}
            </p>
            <p style={{ margin: '4px 0 0', color: 'var(--color-text-muted)', fontSize: 'var(--size-caption)' }}>
              {data.tasks.length} tasks &middot; {formatDuration(data.started_at, data.completed_at)}
            </p>
          </div>

          {/* Overall score */}
          {overallPct != null && (
            <div
              style={{ textAlign: 'center' }}
              data-testid="overall-score"
            >
              <div
                style={{
                  fontSize: '48px',
                  fontWeight: 800,
                  lineHeight: 1,
                  color:
                    overallPct >= 70 ? 'var(--color-success)' : overallPct >= 40 ? 'var(--color-warning)' : 'var(--color-danger)',
                }}
              >
                {overallPct}
              </div>
              <div style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                Overall Score
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Domain scores */}
      {domainEntries.length > 0 && (
        <Card style={{ marginTop: 'var(--space-md)' }}>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-md)' }}>Domain Scores</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-md)' }}>
            {domainEntries.map(([domain, info]) => {
              const barPct = (info.avg_score / 2) * 100
              return (
                <div key={domain} data-testid="domain-bar" aria-label={`${domain}: ${barPct.toFixed(0)}%`}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: '4px',
                      fontSize: 'var(--size-caption)',
                    }}
                  >
                    <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{domain}</span>
                    <span style={{ color: 'var(--color-text-muted)' }}>
                      {barPct.toFixed(0)}% ({info.task_count} tasks)
                    </span>
                  </div>
                  <ProgressBar
                    value={barPct}
                    color={domainBarColor(info.avg_score)}
                  />
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-md)',
              marginTop: 'var(--space-md)',
              fontSize: 'var(--size-xs)',
              color: 'var(--color-text-muted)',
            }}
          >
            <span>
              <span style={{ color: 'var(--color-success)', fontWeight: 700 }}>&#9632;</span> Strong ({'\u2265'}70%)
            </span>
            <span>
              <span style={{ color: 'var(--color-warning)', fontWeight: 700 }}>&#9632;</span> Moderate (40{'\u2013'}69%)
            </span>
            <span>
              <span style={{ color: 'var(--color-danger)', fontWeight: 700 }}>&#9632;</span> Concern (&lt;40%)
            </span>
          </div>
        </Card>
      )}

      {/* Clinical concerns */}
      {data.concerns.length > 0 && (
        <div
          style={{
            marginTop: 'var(--space-md)',
            border: '1px solid var(--color-warning)',
            background: '#451a03',
            borderRadius: 'var(--radius-card)',
            padding: 'var(--space-md)',
          }}
          data-testid="concerns-card"
        >
          <h2 style={{ color: 'var(--color-warning)', margin: '0 0 var(--space-sm)', fontFamily: 'var(--font-heading)' }}>Clinical Concerns</h2>
          <ul style={{ margin: 0, paddingLeft: '20px', color: 'var(--color-warning)' }}>
            {data.concerns.map((concern, i) => (
              <li key={i} style={{ marginBottom: '4px', fontSize: 'var(--size-sm)' }}>
                {concern}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Task breakdown */}
      <Card style={{ marginTop: 'var(--space-md)' }}>
        <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', margin: '0 0 var(--space-md)' }}>Task Breakdown</h2>
        <ol style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {data.tasks.map((task, i) => (
            <li key={i}>
              <TaskRow task={task} index={i} />
            </li>
          ))}
        </ol>
      </Card>

      {/* Clinician Notes */}
      <div style={{ marginTop: 'var(--space-md)' }}>
        <ClinicianNotes entityType="cognitive_screening" entityId={screeningId} />
      </div>
      </div>
    </div>
  )
}
