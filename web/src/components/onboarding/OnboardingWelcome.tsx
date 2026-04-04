/**
 * OnboardingWelcome — first screen of the onboarding flow.
 *
 * Displays a welcoming heading, subtitle, and a purple gradient illustration
 * (styled div), with a "Get Started" button to advance to the next step.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 * @rationale Keeping each screen as a stateless presentational component
 *   (props in, callbacks out) makes them independently testable and lets the
 *   parent OnboardingFlow own all navigation and state logic.
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'

export interface OnboardingWelcomeProps {
  onNext: () => void
}

const containerStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  maxWidth: '480px',
  margin: '0 auto',
  padding: 'var(--space-lg)',
  textAlign: 'center',
}

const illustrationStyle: CSSProperties = {
  width: '160px',
  height: '160px',
  borderRadius: '50%',
  background: 'linear-gradient(135deg, var(--color-primary), var(--color-primary-light))',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '64px',
  marginBottom: 'var(--space-xl)',
}

const headingStyle: CSSProperties = {
  fontFamily: 'var(--font-heading)',
  fontSize: 'var(--size-h1)',
  color: 'var(--color-text-primary)',
  margin: '0 0 var(--space-sm) 0',
}

const subtitleStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-secondary)',
  margin: '0 0 var(--space-xl) 0',
}

const buttonWrapperStyle: CSSProperties = {
  width: '100%',
}

export function OnboardingWelcome({ onNext }: OnboardingWelcomeProps) {
  return (
    <div style={containerStyle}>
      <div style={illustrationStyle} aria-hidden="true">
        <span role="img" aria-label="sparkle">&#10024;</span>
      </div>
      <h1 style={headingStyle}>Welcome to Ada</h1>
      <p style={subtitleStyle}>
        Your personal wellness companion. Let&apos;s set things up so Ada feels
        just right for you.
      </p>
      <div style={buttonWrapperStyle}>
        <Button onClick={onNext} size="lg">Get Started</Button>
      </div>
    </div>
  )
}
