/**
 * OnboardingDashboard — caregiver-path screen introducing the command center.
 *
 * Previews the caregiver dashboard with a mini visual showing session
 * summaries, alerts, and assessment trends at a glance.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export interface OnboardingDashboardProps {
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

const dashboardVisualStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: '1fr 1fr',
  gap: 'var(--space-sm)',
  width: '100%',
  marginBottom: 'var(--space-xl)',
}

const miniCardLabelStyle: CSSProperties = {
  fontSize: 'var(--size-caption)',
  color: 'var(--color-text-muted)',
  margin: '0 0 var(--space-xs) 0',
}

const miniCardValueStyle: CSSProperties = {
  fontSize: 'var(--size-h2)',
  color: 'var(--color-text-primary)',
  fontFamily: 'var(--font-heading)',
  margin: 0,
}

const navStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
}

const DASHBOARD_ITEMS = [
  { label: 'Sessions', value: '12', icon: '\u{1F4AC}' },
  { label: 'Alerts', value: '0', icon: '\u{1F514}' },
  { label: 'Mood Trend', value: '\u{2191}', icon: '\u{1F4C8}' },
  { label: 'Medications', value: '3', icon: '\u{1F48A}' },
]

export function OnboardingDashboard({ onNext, onBack }: OnboardingDashboardProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>Your command center</h1>
      <p style={descStyle}>
        Get a complete picture of your loved one&apos;s wellbeing. Session
        summaries, alerts, assessments, and medications all in one place.
      </p>
      <div style={dashboardVisualStyle} aria-hidden="true">
        {DASHBOARD_ITEMS.map((item) => (
          <Card key={item.label}>
            <p style={miniCardLabelStyle}>{item.icon} {item.label}</p>
            <p style={miniCardValueStyle}>{item.value}</p>
          </Card>
        ))}
      </div>
      <div style={navStyle}>
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button onClick={onNext}>Next</Button>
      </div>
    </div>
  )
}
