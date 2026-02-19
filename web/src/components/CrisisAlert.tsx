/**
 * CrisisAlert — persistent crisis notification banner
 *
 * Intentionally non-dismissible (safety requirement). Displays hotline
 * number and links to emergency resources. Renders above the chat interface
 * with high visual contrast.
 *
 * @decision DEC-FRONTEND-005
 * @title CrisisAlert is non-dismissible by design
 * @status accepted
 * @rationale In a mental health context, a crisis alert must remain visible
 *   for the duration of the session once triggered. Allowing dismissal could
 *   cause a user in distress to accidentally hide critical safety information.
 *   The component renders with role="alert" aria-live="assertive" so screen
 *   readers announce it immediately.
 */

import type { WsCrisisAlert } from '../types'

interface CrisisAlertProps {
  alert: WsCrisisAlert
}

const SEVERITY_LABELS: Record<WsCrisisAlert['severity'], string> = {
  LOW: 'Support Notice',
  MEDIUM: 'Support Notice',
  HIGH: 'Crisis Alert',
  CRITICAL: 'Emergency Alert',
}

export function CrisisAlert({ alert }: CrisisAlertProps) {
  const isEmergency = alert.severity === 'HIGH' || alert.severity === 'CRITICAL'

  return (
    <div
      className={`crisis-alert crisis-alert--${alert.severity.toLowerCase()}`}
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <div className="crisis-alert__header">
        <span className="crisis-alert__icon" aria-hidden="true">
          {isEmergency ? '🚨' : 'ℹ️'}
        </span>
        <strong className="crisis-alert__title">
          {SEVERITY_LABELS[alert.severity]}
        </strong>
      </div>

      <p className="crisis-alert__message">{alert.message}</p>

      <div className="crisis-alert__resources">
        <p className="crisis-alert__hotline">
          <strong>988 Suicide &amp; Crisis Lifeline:</strong>{' '}
          <a href="tel:988" className="crisis-alert__link">
            Call or text <strong>{alert.hotline}</strong>
          </a>
        </p>
        <p className="crisis-alert__resources-note">
          Available 24/7 &mdash; free, confidential support.{' '}
          <a
            href="https://988lifeline.org"
            target="_blank"
            rel="noopener noreferrer"
            className="crisis-alert__link"
          >
            988lifeline.org
          </a>
        </p>
        {isEmergency && (
          <p className="crisis-alert__emergency">
            If you are in immediate danger, please call{' '}
            <a href="tel:911" className="crisis-alert__link">
              <strong>911</strong>
            </a>{' '}
            or go to your nearest emergency room.
          </p>
        )}
      </div>
    </div>
  )
}
