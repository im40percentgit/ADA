/**
 * OnboardingName — companion naming screen.
 *
 * Lets the user choose a custom name for their wellness companion. Shows a
 * live preview of how the companion will greet them. Input is pre-filled with
 * the current name so the default ("Ada") is visible immediately.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'

export interface OnboardingNameProps {
  name: string
  onNameChange: (n: string) => void
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
  margin: '0 0 var(--space-lg) 0',
  textAlign: 'center',
}

const previewStyle: CSSProperties = {
  background: 'var(--color-primary-subtle)',
  borderRadius: 'var(--radius-card)',
  padding: 'var(--space-md)',
  color: 'var(--color-text-secondary)',
  fontSize: 'var(--size-body)',
  fontFamily: 'var(--font-body)',
  width: '100%',
  marginTop: 'var(--space-md)',
  marginBottom: 'var(--space-xl)',
  boxSizing: 'border-box',
}

const navStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
}

export function OnboardingName({ name, onNameChange, onNext, onBack }: OnboardingNameProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>What would you like to call your companion?</h1>
      <div style={{ width: '100%' }}>
        <Input
          label="Companion name"
          value={name}
          onChange={(e) => onNameChange(e.currentTarget.value)}
          placeholder="Ada"
        />
      </div>
      <div style={previewStyle} data-testid="name-preview">
        Hi! I&apos;m {name || 'Ada'}. I&apos;m here to support your wellness journey.
      </div>
      <div style={navStyle}>
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button onClick={onNext} disabled={!name.trim()}>Next</Button>
      </div>
    </div>
  )
}
