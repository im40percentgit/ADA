/**
 * StatusCard — "How They're Doing" summary for the caregiver dashboard.
 *
 * Derives a friendly status from the latest SOAP assessment. Shows mood trend
 * arrow based on recent WHO-5 scores and time since last session.
 *
 * @decision DEC-FRONTEND-021
 * @title StatusCard derives trend from WHO-5 deltas, not PHQ-9/GAD-7
 * @status accepted
 * @rationale WHO-5 measures positive wellbeing (not disorder severity), making
 *   it the most appropriate instrument for a caregiver "how are they doing"
 *   summary. PHQ-9/GAD-7 scores are disorder-specific and clinically sensitive —
 *   exposing raw scores in a caregiver summary risks misinterpretation. The
 *   trend arrow shows direction of change between the two most recent scores.
 */

import type { CaregiverSession, CaregiverAssessmentEntry } from '../types'
import { EmptyState } from './ui/EmptyState'

interface StatusCardProps {
  sessions: CaregiverSession[]
  who5Scores: CaregiverAssessmentEntry[]
}

function timeAgo(dateStr: string): string {
  const normalized = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  const diff = Date.now() - new Date(normalized).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

function moodTrend(scores: CaregiverAssessmentEntry[]): { label: string; arrow: string } {
  if (scores.length < 2) return { label: 'Not enough data', arrow: '' }
  const sorted = [...scores].sort((a, b) => a.timestamp.localeCompare(b.timestamp))
  const recent = sorted[sorted.length - 1].total_score
  const prev = sorted[sorted.length - 2].total_score
  if (recent > prev) return { label: 'Improving', arrow: '\u2191' }
  if (recent < prev) return { label: 'Declining', arrow: '\u2193' }
  return { label: 'Stable', arrow: '\u2192' }
}

export function StatusCard({ sessions, who5Scores }: StatusCardProps) {
  const latest = sessions[0]
  const trend = moodTrend(who5Scores)
  const latestPlan = latest?.summary?.plan

  return (
    <section className="cg-card cg-status" aria-label="Patient status">
      <h2 className="cg-card__title">How They're Doing</h2>

      {latest ? (
        <div className="cg-status__body">
          {latestPlan && (
            <p className="cg-status__plan">{latestPlan}</p>
          )}
          <div className="cg-status__meta">
            {trend.arrow && (
              <span className={`cg-status__trend cg-status__trend--${trend.label.toLowerCase()}`}>
                {trend.arrow} {trend.label}
              </span>
            )}
            <span className="cg-status__last-session">
              Last session: {timeAgo(latest.started_at)}
            </span>
          </div>
        </div>
      ) : (
        <EmptyState
          tone="info"
          icon="💬"
          title="No sessions yet"
          description="Status will update after the first conversation."
        />
      )}
    </section>
  )
}
