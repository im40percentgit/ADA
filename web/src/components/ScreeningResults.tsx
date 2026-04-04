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
import type { CognitiveScreening } from '../types'
import { ClinicianNotes } from './ClinicianNotes'

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
  memory: { background: '#ede9fe', color: '#5b21b6' },
  attention: { background: '#dbeafe', color: '#1d4ed8' },
  language: { background: '#d1fae5', color: '#065f46' },
  visuospatial: { background: '#fef3c7', color: '#92400e' },
  executive: { background: '#fee2e2', color: '#991b1b' },
  orientation: { background: '#e0f2fe', color: '#0369a1' },
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
  const scoreColor = SCORE_COLOR[Math.round(task.score)] ?? '#374151'

  return (
    <div
      style={{
        borderBottom: '1px solid #e5e7eb',
        paddingBottom: '12px',
        marginBottom: '12px',
      }}
    >
      {/* Row header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          cursor: 'pointer',
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
            borderRadius: '12px',
            fontSize: '12px',
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
        <span style={{ flex: 1, fontSize: '14px', color: '#374151' }}>{task.prompt}</span>

        {/* Score */}
        <span
          style={{
            fontWeight: 700,
            fontSize: '15px',
            color: scoreColor,
            minWidth: '28px',
            textAlign: 'right',
          }}
          data-testid="task-score"
        >
          {task.score}
        </span>

        {/* Expand toggle */}
        <span style={{ color: '#9ca3af', fontSize: '12px' }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div
          style={{
            marginTop: '10px',
            paddingLeft: '16px',
            borderLeft: '3px solid #e5e7eb',
          }}
        >
          <p style={{ margin: '0 0 6px', fontSize: '13px', color: '#6b7280' }}>
            <strong>Response:</strong> {task.response}
          </p>
          <p style={{ margin: 0, fontSize: '13px', color: '#6b7280' }}>
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
      <div className="patient-dash" aria-busy="true">
        Loading screening results...
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
        <p className="patient-dash__empty">No screening data available</p>
        <button type="button" className="med-card__btn med-card__btn--secondary" onClick={onBack}>
          Back
        </button>
      </div>
    )
  }

  const overallPct = data.overall_score != null ? Math.round(data.overall_score * 100) : null
  const domainEntries = Object.entries(data.domains)

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

      {/* Header card */}
      <div className="patient-dash__card patient-dash__card--full">
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          {/* Date + meta */}
          <div>
            <h2 style={{ margin: '0 0 4px' }}>Cognitive Screening</h2>
            <p style={{ margin: 0, color: '#6b7280', fontSize: '14px' }}>
              {formatDate(data.started_at)}
            </p>
            <p style={{ margin: '4px 0 0', color: '#6b7280', fontSize: '13px' }}>
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
                    overallPct >= 70 ? '#16a34a' : overallPct >= 40 ? '#d97706' : '#dc2626',
                }}
              >
                {overallPct}
              </div>
              <div style={{ fontSize: '13px', color: '#6b7280', marginTop: '4px' }}>
                Overall Score
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Domain scores */}
      {domainEntries.length > 0 && (
        <div className="patient-dash__card patient-dash__card--full" style={{ marginTop: '16px' }}>
          <h3>Domain Scores</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {domainEntries.map(([domain, info]) => {
              const barPct = (info.avg_score / 2) * 100
              return (
                <div key={domain} data-testid="domain-bar">
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: '4px',
                      fontSize: '13px',
                    }}
                  >
                    <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{domain}</span>
                    <span style={{ color: '#6b7280' }}>
                      {barPct.toFixed(0)}% ({info.task_count} tasks)
                    </span>
                  </div>
                  <div
                    style={{
                      background: '#f3f4f6',
                      borderRadius: '6px',
                      height: '10px',
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: domainBarWidth(info.avg_score),
                        height: '100%',
                        background: domainBarColor(info.avg_score),
                        borderRadius: '6px',
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                </div>
              )
            })}
          </div>

          {/* Legend */}
          <div
            style={{
              display: 'flex',
              gap: '16px',
              marginTop: '12px',
              fontSize: '12px',
              color: '#6b7280',
            }}
          >
            <span>
              <span style={{ color: '#16a34a', fontWeight: 700 }}>&#9632;</span> Strong (≥70%)
            </span>
            <span>
              <span style={{ color: '#d97706', fontWeight: 700 }}>&#9632;</span> Moderate (40–69%)
            </span>
            <span>
              <span style={{ color: '#dc2626', fontWeight: 700 }}>&#9632;</span> Concern (&lt;40%)
            </span>
          </div>
        </div>
      )}

      {/* Clinical concerns */}
      {data.concerns.length > 0 && (
        <div
          className="patient-dash__card patient-dash__card--full"
          style={{
            marginTop: '16px',
            border: '1px solid #fbbf24',
            background: '#fffbeb',
          }}
          data-testid="concerns-card"
        >
          <h3 style={{ color: '#92400e', margin: '0 0 10px' }}>Clinical Concerns</h3>
          <ul style={{ margin: 0, paddingLeft: '20px', color: '#92400e' }}>
            {data.concerns.map((concern, i) => (
              <li key={i} style={{ marginBottom: '4px', fontSize: '14px' }}>
                {concern}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Task breakdown */}
      <div className="patient-dash__card patient-dash__card--full" style={{ marginTop: '16px' }}>
        <h3>Task Breakdown</h3>
        {data.tasks.map((task, i) => (
          <TaskRow key={i} task={task} index={i} />
        ))}
      </div>

      {/* Clinician Notes */}
      <div style={{ marginTop: '16px' }}>
        <ClinicianNotes entityType="cognitive_screening" entityId={screeningId} />
      </div>
    </div>
  )
}
