/**
 * AlertsCard — crisis alert display for the caregiver dashboard.
 *
 * Shows recent crisis alerts with severity-based styling. HIGH/CRITICAL
 * get red backgrounds. Shows "No recent alerts" when the list is empty.
 *
 * @decision DEC-FRONTEND-022
 * @title AlertsCard uses index as key — alerts have no stable ID from backend
 * @status accepted
 * @rationale The CaregiverAlert type returned by GET /api/caregiver/overview
 *   does not include a unique ID field (the backend aggregates from the crisis
 *   events log which stores severity + timestamp, not UUIDs). Using array index
 *   as key is acceptable here because the list is read-only (no reordering or
 *   in-place mutation) and re-renders are driven by a 60s polling interval, not
 *   user interaction. If alert IDs are added to the backend model, switch to
 *   alert.id as the key.
 */

import type { CaregiverAlert } from '../types'

interface AlertsCardProps {
  alerts: CaregiverAlert[]
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

const SEVERITY_LABELS: Record<string, string> = {
  LOW: 'Low Concern',
  MODERATE: 'Moderate',
  HIGH: 'Needs Attention',
  CRITICAL: 'Urgent',
}

export function AlertsCard({ alerts }: AlertsCardProps) {
  return (
    <section className="cg-card cg-alerts" aria-label="Crisis alerts">
      <h2 className="cg-card__title">Alerts</h2>

      {alerts.length === 0 ? (
        <p className="cg-card__empty cg-alerts__none">No recent alerts</p>
      ) : (
        <ul className="cg-alerts__list">
          {alerts.map((alert, i) => {
            const isUrgent = alert.severity === 'HIGH' || alert.severity === 'CRITICAL'
            return (
              <li
                key={i}
                className={`cg-alerts__item${isUrgent ? ' cg-alerts__item--urgent' : ''}`}
              >
                <span className="cg-alerts__severity">
                  {SEVERITY_LABELS[alert.severity] ?? alert.severity}
                </span>
                <span className="cg-alerts__time">{timeAgo(alert.timestamp)}</span>
                {alert.escalation_action && (
                  <p className="cg-alerts__action">{alert.escalation_action}</p>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
