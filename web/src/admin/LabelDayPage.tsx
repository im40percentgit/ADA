/**
 * LabelDayPage — internal admin tooling for Phase 15+ M3 ground-truth labeling.
 *
 * Shows the unlabeled verdict queue for the current patient and lets the
 * founder apply a TRUTH_OK / TRUTH_OFF / TRUTH_UNSURE label to each day.
 * After labeling, the row disappears from the queue.
 *
 * Also displays the calibration header chip showing progress toward the
 * 21-day gate required before M4 push notifications ship.
 *
 * Internal tooling — no design polish (DEC-VERDICT-007). Minimal CSS.
 * No nav entry on PatientDashboard; accessed via the Settings page admin link
 * or direct URL hash navigation.
 *
 * @decision DEC-VERDICT-007
 * @title /admin/label-day is internal tooling — no design polish
 * @status accepted
 * @rationale Founder uses this during 21-day shadow calibration; no external
 *     users in Phase 15+. The only UX requirement is "can I label a day quickly
 *     and see my calibration progress." A plain table with three buttons per
 *     row satisfies that without production-UI investment.
 */

import { useCallback, useEffect, useState } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DailyVerdict {
  id: number
  patient_id: string
  verdict_date: string
  verdict: 'OK' | 'OFF' | 'UNSURE' | 'NO_SIGNAL'
  explanation: string
  dimension: string | null
  model_used: string
  prompt_version: string
  telemetry_summary: Record<string, unknown>
  baseline_summary: Record<string, unknown> | string
  generated_at: string | null
  labeled_truth: string | null
  labeled_at: string | null
  labeled_by: string | null
}

interface CalibrationMetrics {
  labeled_streak_days: number
  labeled_streak_target: number
  last7_false_ok_count: number
  last7_false_off_count: number
  all_unsure_no_signal_ratio: number
  gate_passed: boolean
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('ADA_ACCESS_TOKEN') ?? ''
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` }
}

async function fetchUnlabeled(patientId: string): Promise<DailyVerdict[]> {
  const resp = await fetch(`/api/verdict/unlabeled?patient_id=${encodeURIComponent(patientId)}`, {
    headers: authHeaders(),
  })
  if (!resp.ok) throw new Error(`GET unlabeled failed: ${resp.status}`)
  return resp.json()
}

async function fetchCalibration(patientId: string): Promise<CalibrationMetrics> {
  const resp = await fetch(`/api/verdict/calibration?patient_id=${encodeURIComponent(patientId)}`, {
    headers: authHeaders(),
  })
  if (!resp.ok) throw new Error(`GET calibration failed: ${resp.status}`)
  return resp.json()
}

async function postLabel(verdictId: number, label: string): Promise<DailyVerdict> {
  const resp = await fetch(`/api/verdict/${verdictId}/label`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ label }),
  })
  if (!resp.ok) throw new Error(`POST label failed: ${resp.status}`)
  return resp.json()
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

const VERDICT_COLORS: Record<string, string> = {
  OK: '#22c55e',
  OFF: '#ef4444',
  UNSURE: '#6b7280',
  NO_SIGNAL: '#9ca3af',
}

function VerdictChip({ verdict }: { verdict: string }) {
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 12,
        fontWeight: 600,
        color: '#fff',
        backgroundColor: VERDICT_COLORS[verdict] ?? '#6b7280',
        fontFamily: 'monospace',
      }}
    >
      {verdict}
    </span>
  )
}

function CalibrationHeader({ metrics }: { metrics: CalibrationMetrics | null }) {
  if (!metrics) return <p style={{ color: '#6b7280', fontSize: 13 }}>Loading calibration…</p>

  const gateColor = metrics.gate_passed ? '#22c55e' : '#f59e0b'
  return (
    <div
      data-testid="calibration-header"
      style={{
        display: 'flex',
        gap: 12,
        flexWrap: 'wrap',
        alignItems: 'center',
        padding: '8px 12px',
        borderRadius: 6,
        backgroundColor: '#1f2937',
        color: '#f9fafb',
        fontSize: 13,
        marginBottom: 16,
      }}
    >
      <span style={{ color: gateColor, fontWeight: 700 }}>
        {metrics.gate_passed ? '✓ Gate passed' : '◉ Shadow mode'}
      </span>
      <span>
        Calibration:{' '}
        <strong>
          {metrics.labeled_streak_days} / {metrics.labeled_streak_target}
        </strong>{' '}
        labeled days
      </span>
      <span>
        last7 FP: <strong>{metrics.last7_false_off_count}</strong>
      </span>
      <span>
        last7 FN: <strong>{metrics.last7_false_ok_count}</strong>
      </span>
      <span>
        UNSURE+NO_SIGNAL:{' '}
        <strong>{(metrics.all_unsure_no_signal_ratio * 100).toFixed(0)}%</strong>
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// LabelDayPage
// ---------------------------------------------------------------------------

export interface LabelDayPageProps {
  patientId: string
  onBack?: () => void
}

export function LabelDayPage({ patientId, onBack }: LabelDayPageProps) {
  const [rows, setRows] = useState<DailyVerdict[]>([])
  const [calibration, setCalibration] = useState<CalibrationMetrics | null>(null)
  const [loadingIds, setLoadingIds] = useState<Set<number>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const reload = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const [unlabeled, cal] = await Promise.all([
        fetchUnlabeled(patientId),
        fetchCalibration(patientId),
      ])
      setRows(unlabeled)
      setCalibration(cal)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  useEffect(() => {
    reload()
  }, [reload])

  async function handleLabel(verdictId: number, label: string) {
    setLoadingIds(prev => new Set(prev).add(verdictId))
    try {
      await postLabel(verdictId, label)
      // Remove the row from the queue and refresh calibration
      setRows(prev => prev.filter(r => r.id !== verdictId))
      const cal = await fetchCalibration(patientId)
      setCalibration(cal)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Label failed')
    } finally {
      setLoadingIds(prev => { const s = new Set(prev); s.delete(verdictId); return s })
    }
  }

  return (
    <div style={{ padding: 20, fontFamily: 'system-ui, sans-serif', maxWidth: 900 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        {onBack && (
          <button onClick={onBack} style={{ fontSize: 13, cursor: 'pointer' }}>
            ← Back
          </button>
        )}
        <h2 style={{ margin: 0, fontSize: 18 }}>Label Day — Shadow Mode</h2>
      </div>

      <CalibrationHeader metrics={calibration} />

      {error && (
        <p style={{ color: '#ef4444', fontSize: 13 }}>{error}</p>
      )}

      {loading ? (
        <p style={{ color: '#6b7280', fontSize: 13 }}>Loading…</p>  // lint-empty-states:allow — DEC-VERDICT-007 internal admin tooling, no AsyncBoundary polish
      ) : rows.length === 0 ? (
        <p style={{ color: '#6b7280', fontSize: 13 }}>No unlabeled verdicts. Check back after the next session.</p>
      ) : (
        <table
          style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: 13,
          }}
        >
          <thead>
            <tr style={{ borderBottom: '1px solid #374151', color: '#9ca3af', textAlign: 'left' }}>
              <th style={{ padding: '6px 8px' }}>Date</th>
              <th style={{ padding: '6px 8px' }}>Verdict</th>
              <th style={{ padding: '6px 8px' }}>Explanation</th>
              <th style={{ padding: '6px 8px' }}>Dimension</th>
              <th style={{ padding: '6px 8px' }}>Telemetry</th>
              <th style={{ padding: '6px 8px' }}>Label</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(row => (
              <tr
                key={row.id}
                style={{ borderBottom: '1px solid #1f2937', verticalAlign: 'top' }}
              >
                <td style={{ padding: '8px', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                  {row.verdict_date}
                </td>
                <td style={{ padding: '8px' }}>
                  <VerdictChip verdict={row.verdict} />
                </td>
                <td style={{ padding: '8px', maxWidth: 260, color: '#d1d5db' }}>
                  {row.explanation}
                </td>
                <td style={{ padding: '8px', color: '#9ca3af', fontFamily: 'monospace' }}>
                  {row.dimension ?? '—'}
                </td>
                <td style={{ padding: '8px' }}>
                  <details>
                    <summary style={{ cursor: 'pointer', color: '#6b7280', fontSize: 11 }}>
                      view
                    </summary>
                    <pre
                      style={{
                        fontSize: 10,
                        color: '#9ca3af',
                        margin: '4px 0 0',
                        maxHeight: 120,
                        overflow: 'auto',
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {JSON.stringify(row.telemetry_summary, null, 2)}
                    </pre>
                  </details>
                </td>
                <td style={{ padding: '8px', whiteSpace: 'nowrap' }}>
                  {(['TRUTH_OK', 'TRUTH_OFF', 'TRUTH_UNSURE'] as const).map(label => (
                    <button
                      key={label}
                      data-testid={`label-btn-${row.id}-${label}`}
                      disabled={loadingIds.has(row.id)}
                      onClick={() => handleLabel(row.id, label)}
                      style={{
                        marginRight: 4,
                        padding: '3px 8px',
                        fontSize: 11,
                        cursor: loadingIds.has(row.id) ? 'not-allowed' : 'pointer',
                        opacity: loadingIds.has(row.id) ? 0.5 : 1,
                        borderRadius: 3,
                        border: '1px solid #374151',
                        backgroundColor:
                          label === 'TRUTH_OK'
                            ? '#166534'
                            : label === 'TRUTH_OFF'
                            ? '#7f1d1d'
                            : '#374151',
                        color: '#f9fafb',
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
