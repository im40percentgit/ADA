/**
 * ScreeningHistory — timeline of past cognitive screenings for a patient.
 *
 * Fetches all CognitiveScreenings for the patient on mount, displays them
 * in reverse-chronological order. Each entry shows:
 *   - Date (formatted)
 *   - Overall score as a coloured badge
 *   - Domain summary (name + avg_score for each domain)
 *   - Trend indicator comparing the most recent score to the previous
 *
 * Clicking an entry calls onViewScreening(id) to navigate to the detail view.
 *
 * @decision DEC-FRONTEND-066
 * @title ScreeningHistory fetches directly — no custom hook
 * @status accepted
 * @rationale Single-fetch with no re-fetch triggers. Consistent with the
 *   SessionSummary and ScreeningResults pattern.
 */

import { useState, useEffect } from 'react'
import { listCognitiveScreenings } from '../api/client'
import type { CognitiveScreening } from '../types'

interface ScreeningHistoryProps {
  patientId: string
  onViewScreening: (id: string) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function scoreColor(pct: number): string {
  if (pct >= 70) return '#16a34a'
  if (pct >= 40) return '#d97706'
  return '#dc2626'
}

/** Compare latest score vs previous and return a trend symbol + label */
function trendIndicator(
  latest: number | null,
  previous: number | null,
): { symbol: string; label: string; color: string } | null {
  if (latest == null || previous == null) return null
  const diff = latest - previous
  if (diff > 0.02) return { symbol: '▲', label: `+${Math.round(diff * 100)}pts`, color: '#16a34a' }
  if (diff < -0.02) return { symbol: '▼', label: `${Math.round(diff * 100)}pts`, color: '#dc2626' }
  return { symbol: '—', label: 'Stable', color: '#6b7280' }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ScreeningHistory({ patientId, onViewScreening }: ScreeningHistoryProps) {
  const [screenings, setScreenings] = useState<CognitiveScreening[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listCognitiveScreenings(patientId)
      .then((results) => {
        if (!cancelled) {
          // Sort newest-first
          const sorted = [...results].sort(
            (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
          )
          setScreenings(sorted)
          setError(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load screening history')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [patientId])

  if (loading) {
    return (
      <div className="patient-dash" aria-busy="true">
        Loading screening history...
      </div>
    )
  }

  if (error) {
    return (
      <div className="patient-dash" role="alert">
        <p className="patient-dash__error">{error}</p>
      </div>
    )
  }

  if (screenings.length === 0) {
    return (
      <div className="patient-dash">
        <p className="patient-dash__empty">No cognitive screenings yet</p>
      </div>
    )
  }

  // Compute trend: compare index 0 (latest) vs index 1 (previous)
  const trend = trendIndicator(
    screenings[0]?.overall_score ?? null,
    screenings[1]?.overall_score ?? null,
  )

  return (
    <div className="patient-dash">
      <h1 className="sr-only">Screening History</h1>
      {/* Trend banner (only shown when ≥2 screenings exist) */}
      {trend && screenings.length >= 2 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            padding: '10px 16px',
            borderRadius: '8px',
            background: '#f9fafb',
            border: '1px solid #e5e7eb',
            marginBottom: '16px',
            fontSize: '14px',
          }}
          data-testid="trend-indicator"
        >
          <span style={{ fontWeight: 700, color: trend.color, fontSize: '18px' }}>
            {trend.symbol}
          </span>
          <span style={{ color: '#374151' }}>
            Trend since last screening:
          </span>
          <span style={{ fontWeight: 600, color: trend.color }}>{trend.label}</span>
        </div>
      )}

      {/* Timeline */}
      <ol style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '12px' }} aria-label="Screening history timeline">
        {screenings.map((s, index) => {
          const pct = s.overall_score != null ? Math.round(s.overall_score * 100) : null
          const domainEntries = Object.entries(s.domains)

          return (
            <li
              key={s.id}
              className="patient-dash__card"
              style={{ cursor: 'pointer', transition: 'box-shadow 0.15s' }}
              role="button"
              tabIndex={0}
              onClick={() => onViewScreening(s.id)}
              onKeyDown={(e) =>
                (e.key === 'Enter' || e.key === ' ') && onViewScreening(s.id)
              }
              data-testid={`screening-entry-${index}`}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '12px',
                  flexWrap: 'wrap',
                }}
              >
                {/* Date */}
                <div>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: '15px', color: '#111827' }}>
                    {formatDate(s.started_at)}
                  </p>
                  <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#9ca3af' }}>
                    {s.tasks.length} tasks
                  </p>
                </div>

                {/* Overall score badge */}
                {pct != null && (
                  <div
                    style={{
                      minWidth: '52px',
                      textAlign: 'center',
                      padding: '6px 12px',
                      borderRadius: '8px',
                      background: '#f9fafb',
                      border: `2px solid ${scoreColor(pct)}`,
                    }}
                    data-testid="score-badge"
                  >
                    <div
                      style={{
                        fontSize: '22px',
                        fontWeight: 800,
                        lineHeight: 1,
                        color: scoreColor(pct),
                      }}
                    >
                      {pct}
                    </div>
                    <div style={{ fontSize: '11px', color: '#6b7280' }}>score</div>
                  </div>
                )}
              </div>

              {/* Domain summary */}
              {domainEntries.length > 0 && (
                <div
                  style={{
                    display: 'flex',
                    gap: '8px',
                    flexWrap: 'wrap',
                    marginTop: '10px',
                  }}
                >
                  {domainEntries.map(([domain, info]) => {
                    const domPct = Math.round((info.avg_score / 2) * 100)
                    return (
                      <span
                        key={domain}
                        style={{
                          padding: '2px 10px',
                          borderRadius: '12px',
                          fontSize: '12px',
                          fontWeight: 500,
                          background: '#f3f4f6',
                          color: scoreColor(domPct),
                          border: `1px solid ${scoreColor(domPct)}22`,
                        }}
                      >
                        {domain}: {domPct}%
                      </span>
                    )
                  })}
                </div>
              )}
            </li>
          )
        })}
      </ol>
    </div>
  )
}
