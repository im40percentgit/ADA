/**
 * OnboardingCognitive — patient-path final screen introducing cognitive check-ins.
 *
 * Explains the cognitive screening feature with a mini grid visual and a
 * "Start Using {name}" button to complete onboarding.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'

export interface OnboardingCognitiveProps {
  name: string
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

const gridVisualStyle: CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(3, 1fr)',
  gap: 'var(--space-sm)',
  width: '160px',
  marginBottom: 'var(--space-xl)',
}

const cellStyle = (filled: boolean): CSSProperties => ({
  width: '100%',
  aspectRatio: '1',
  borderRadius: '8px',
  background: filled ? 'var(--color-primary)' : 'var(--color-bg-elevated)',
  border: '1px solid var(--color-border)',
})

const navStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
}

const GRID_PATTERN = [true, false, true, false, true, false, true, false, true]

export function OnboardingCognitive({ name, onNext, onBack }: OnboardingCognitiveProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>Cognitive check-ins</h1>
      <p style={descStyle}>
        Quick, engaging exercises to track memory, attention, and other cognitive
        skills over time. Just a few minutes and completely private.
      </p>
      <div style={gridVisualStyle} aria-hidden="true">
        {GRID_PATTERN.map((filled, i) => (
          <div key={i} style={cellStyle(filled)} />
        ))}
      </div>
      <div style={navStyle}>
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button onClick={onNext}>Start Using {name}</Button>
      </div>
    </div>
  )
}
