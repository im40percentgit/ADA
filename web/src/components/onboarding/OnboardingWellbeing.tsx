/**
 * OnboardingWellbeing — patient-path screen introducing wellbeing tracking.
 *
 * Describes the mood and assessment tracking features with a mini chart
 * visual (styled bars) to illustrate the concept.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'

export interface OnboardingWellbeingProps {
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

const chartVisualStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-end',
  gap: 'var(--space-sm)',
  height: '120px',
  width: '100%',
  background: 'var(--color-bg-card)',
  borderRadius: 'var(--radius-card)',
  padding: 'var(--space-md)',
  marginBottom: 'var(--space-xl)',
  border: '1px solid var(--color-border)',
  boxSizing: 'border-box',
}

const barStyle = (height: string): CSSProperties => ({
  flex: 1,
  height,
  background: 'linear-gradient(to top, var(--color-primary), var(--color-primary-light))',
  borderRadius: '4px 4px 0 0',
})

const navStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
}

const BARS = ['40%', '55%', '45%', '70%', '65%', '80%', '75%']

export function OnboardingWellbeing({ onNext, onBack }: OnboardingWellbeingProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>Track your wellbeing</h1>
      <p style={descStyle}>
        See how you&apos;re doing over time with mood tracking and validated
        wellness assessments. Small patterns lead to big insights.
      </p>
      <div style={chartVisualStyle} aria-hidden="true">
        {BARS.map((h, i) => (
          <div key={i} style={barStyle(h)} />
        ))}
      </div>
      <div style={navStyle}>
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button onClick={onNext}>Next</Button>
      </div>
    </div>
  )
}
