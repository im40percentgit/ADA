/**
 * OnboardingVoice — voice selection screen.
 *
 * Presents three Card options (Female, Male, Neutral) for the companion's
 * voice. The selected card receives a primary-coloured border to indicate
 * the active choice.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export interface OnboardingVoiceProps {
  name: string
  voice: string
  onVoiceChange: (v: string) => void
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

const optionsStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--space-md)',
  width: '100%',
  marginBottom: 'var(--space-xl)',
}

const selectedBorder: CSSProperties = {
  borderColor: 'var(--color-primary)',
  borderWidth: '2px',
}

const optionLabelStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-primary)',
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--space-sm)',
}

const navStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
}

const VOICE_OPTIONS: { value: string; label: string; icon: string }[] = [
  { value: 'female', label: 'Female', icon: '\u{1F469}' },
  { value: 'male', label: 'Male', icon: '\u{1F468}' },
  { value: 'neutral', label: 'Neutral', icon: '\u{1F9D1}' },
]

export function OnboardingVoice({ name, voice, onVoiceChange, onNext, onBack }: OnboardingVoiceProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>Choose {name}&apos;s voice</h1>
      <div style={optionsStyle}>
        {VOICE_OPTIONS.map((opt) => (
          <Card
            key={opt.value}
            onClick={() => onVoiceChange(opt.value)}
            style={voice === opt.value ? selectedBorder : undefined}
          >
            <span style={optionLabelStyle}>
              <span aria-hidden="true">{opt.icon}</span>
              {opt.label}
            </span>
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
