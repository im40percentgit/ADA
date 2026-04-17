/**
 * AlertsCard — crisis alert display with resolution actions for the caregiver dashboard.
 *
 * Shows recent crisis alerts with severity-based styling. HIGH/CRITICAL
 * get red backgrounds. Shows "No recent alerts" when the list is empty.
 *
 * Each alert shows status-dependent actions:
 *   active       → Acknowledge + Resolve buttons
 *   acknowledged → Acknowledged label + Resolve button
 *   resolved     → Resolved badge (no buttons)
 *
 * Local state tracks status overrides so the UI updates immediately after an
 * action without waiting for the next 60-second poll cycle.
 *
 * @decision DEC-FRONTEND-022
 * @title AlertsCard uses alert.id as key after Task 7 added id + status fields
 * @status accepted
 * @rationale Task 3 (Phase 10b) added id, status, resolved_at, resolved_by to
 *   the crisis_alerts table. The overview endpoint passes all non-trigger_text
 *   fields through, so id and status are now available. The previous index-key
 *   workaround documented here is superseded — alert.id is the stable key.
 */

import { useState } from 'react'
import type { CaregiverAlert } from '../types'
import { updateAlertStatus } from '../api/client'
import { EmptyState } from './ui/EmptyState'

interface AlertsCardProps {
  alerts: CaregiverAlert[]
}

type AlertStatus = 'active' | 'acknowledged' | 'resolved'

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

const SEVERITY_LABELS: Record<string, string> = {
  LOW: 'Low Concern',
  MODERATE: 'Moderate',
  HIGH: 'Needs Attention',
  CRITICAL: 'Urgent',
}

export function AlertsCard({ alerts }: AlertsCardProps) {
  // Map of alertId → overridden status (updated optimistically on button click)
  const [statusOverrides, setStatusOverrides] = useState<Record<string, AlertStatus>>({})
  // Map of alertId → in-flight action (prevents double-clicks)
  const [pending, setPending] = useState<Record<string, boolean>>({})

  async function handleAction(alertId: string, newStatus: AlertStatus) {
    setPending(p => ({ ...p, [alertId]: true }))
    try {
      await updateAlertStatus(alertId, newStatus)
      setStatusOverrides(s => ({ ...s, [alertId]: newStatus }))
    } catch (err) {
      console.error('Failed to update alert status', err)
    } finally {
      setPending(p => ({ ...p, [alertId]: false }))
    }
  }

  return (
    <section className="cg-card cg-alerts" aria-label="Crisis alerts">
      <h2 className="cg-card__title">Alerts</h2>

      {alerts.length === 0 ? (
        <EmptyState
          tone="info"
          icon="✅"
          title="No recent alerts"
          description="Everything's quiet right now."
        />
      ) : (
        <ul className="cg-alerts__list">
          {alerts.map((alert) => {
            const status: AlertStatus = statusOverrides[alert.id] ?? alert.status ?? 'active'
            const isUrgent = alert.severity === 'HIGH' || alert.severity === 'CRITICAL'
            const isBusy = pending[alert.id] ?? false

            return (
              <li
                key={alert.id}
                className={`cg-alerts__item${isUrgent ? ' cg-alerts__item--urgent' : ''}`}
              >
                <span className="cg-alerts__severity">
                  {SEVERITY_LABELS[alert.severity] ?? alert.severity}
                </span>
                <span className="cg-alerts__time">{timeAgo(alert.timestamp)}</span>

                {alert.escalation_action && (
                  <p className="cg-alerts__action">{alert.escalation_action}</p>
                )}

                <div className="cg-alerts__actions">
                  {status === 'active' && (
                    <>
                      <button
                        className="med-card__btn cg-alerts__btn"
                        disabled={isBusy}
                        onClick={() => handleAction(alert.id, 'acknowledged')}
                      >
                        Acknowledge
                      </button>
                      <button
                        className="med-card__btn med-card__btn--secondary cg-alerts__btn"
                        disabled={isBusy}
                        onClick={() => handleAction(alert.id, 'resolved')}
                      >
                        Resolve
                      </button>
                    </>
                  )}

                  {status === 'acknowledged' && (
                    <>
                      <span className="cg-alerts__status-label">Acknowledged</span>
                      <button
                        className="med-card__btn med-card__btn--secondary cg-alerts__btn"
                        disabled={isBusy}
                        onClick={() => handleAction(alert.id, 'resolved')}
                      >
                        Resolve
                      </button>
                    </>
                  )}

                  {status === 'resolved' && (
                    <span className="cg-alerts__status-label cg-alerts__status-label--resolved">
                      Resolved
                    </span>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
