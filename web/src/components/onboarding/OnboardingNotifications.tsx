/**
 * OnboardingNotifications — caregiver-path final screen for notification setup.
 *
 * Offers an "Enable Notifications" button, a "Skip" link, and a "Start Using
 * Ada" button to complete onboarding. Caregivers can opt in to push
 * notifications for crisis alerts, board updates, and daily summaries.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'

export interface OnboardingNotificationsProps {
  onEnableNotifications?: () => void
  onNext: () => void
  onBack: () => void
}

const containerStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  maxWidth: '480px',
  margin: '0 auto',
  padding: 'var(--space-lg)',
}

const headingStyle: CSSProperties = {
  fontFamily: 'var(--font-heading)',
  fontSize: 'var(--size-h1)',
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-sm) 0',
  textAlign: 'center',
}

const descStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-secondary)',
  margin: '0 0 var(--space-lg) 0',
  textAlign: 'center',
}

const bellVisualStyle: CSSProperties = {
  width: '120px',
  height: '120px',
  borderRadius: '50%',
  background: 'var(--color-bg-card)',
  border: '1px solid var(--color-border)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '48px',
  marginBottom: 'var(--space-xl)',
}

const actionsStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-md)',
  width: '100%',
  alignItems: 'center',
}

const skipStyle: CSSProperties = {
  background: 'none',
  border: 'none',
  color: 'var(--color-text-muted)',
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-sm)',
  cursor: 'pointer',
  textDecoration: 'underline',
  padding: 'var(--space-sm)',
}

const buttonRowStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
}

export function OnboardingNotifications({
  onEnableNotifications,
  onNext,
  onBack,
}: OnboardingNotificationsProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>Stay informed</h1>
      <p style={descStyle}>
        Get notified about crisis alerts, board updates, and daily summaries.
        Never miss an important moment in your loved one&apos;s care.
      </p>
      <div style={bellVisualStyle} aria-hidden="true">
        <span role="img" aria-label="bell">&#128276;</span>
      </div>
      <div style={actionsStyle}>
        {onEnableNotifications && (
          <div style={{ width: '100%' }}>
            <Button onClick={onEnableNotifications}>Enable Notifications</Button>
          </div>
        )}
        <button style={skipStyle} onClick={onNext}>
          Skip
        </button>
        <div style={buttonRowStyle}>
          <Button variant="secondary" onClick={onBack}>Back</Button>
          <Button onClick={onNext}>Start Using Ada</Button>
        </div>
      </div>
    </div>
  )
}
