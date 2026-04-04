/**
 * OnboardingCircle — caregiver-path screen for care circle setup.
 *
 * Introduces the care circle concept with a "Set Up Circle" primary action
 * and a "Skip for now" secondary link for caregivers who want to do it later.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'

export interface OnboardingCircleProps {
  onSetupCircle?: () => void
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

const circleVisualStyle: CSSProperties = {
  width: '160px',
  height: '160px',
  borderRadius: '50%',
  background: 'var(--color-bg-card)',
  border: '2px dashed var(--color-primary-light)',
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

const navStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
  marginBottom: 'var(--space-md)',
}

export function OnboardingCircle({ onSetupCircle, onNext, onBack }: OnboardingCircleProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>Set up your care circle</h1>
      <p style={descStyle}>
        Invite family members and clinicians to collaborate on care. Everyone
        stays connected and informed.
      </p>
      <div style={circleVisualStyle} aria-hidden="true">
        <span role="img" aria-label="people">&#128101;</span>
      </div>
      <div style={actionsStyle}>
        <div style={navStyle}>
          <Button variant="secondary" onClick={onBack}>Back</Button>
          {onSetupCircle ? (
            <Button onClick={onSetupCircle}>Set Up Circle</Button>
          ) : (
            <Button onClick={onNext}>Next</Button>
          )}
        </div>
        <button style={skipStyle} onClick={onNext}>
          Skip for now
        </button>
      </div>
    </div>
  )
}
