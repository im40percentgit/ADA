/**
 * OnboardingPersonality — personality trait selection screen.
 *
 * Presents three dimensions of companion personality (Warmth, Verbosity,
 * Formality) as two-option toggle rows. A preview bubble shows how the
 * selected traits affect the companion's communication style.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'

export interface PersonalitySettings {
  warmth: string
  verbosity: string
  formality: string
}

export interface OnboardingPersonalityProps {
  name: string
  personality: PersonalitySettings
  onPersonalityChange: (p: PersonalitySettings) => void
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

const rowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  width: '100%',
  marginBottom: 'var(--space-md)',
}

const rowLabelStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-body)',
  color: 'var(--color-text-primary)',
  minWidth: '80px',
}

const toggleGroupStyle: CSSProperties = {
  display: 'flex',
  gap: '0',
}

const toggleBtnBase: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-sm)',
  padding: 'var(--space-sm) var(--space-md)',
  border: '1px solid var(--color-border)',
  cursor: 'pointer',
  minHeight: 'var(--touch-target-min)',
  display: 'inline-flex',
  alignItems: 'center',
}

const toggleBtnLeft: CSSProperties = {
  ...toggleBtnBase,
  borderRadius: 'var(--radius-button) 0 0 var(--radius-button)',
  borderRight: 'none',
}

const toggleBtnRight: CSSProperties = {
  ...toggleBtnBase,
  borderRadius: '0 var(--radius-button) var(--radius-button) 0',
}

const activeToggle: CSSProperties = {
  background: 'var(--color-primary)',
  color: '#ffffff',
  borderColor: 'var(--color-primary)',
}

const inactiveToggle: CSSProperties = {
  background: 'var(--color-bg-elevated)',
  color: 'var(--color-text-secondary)',
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

const TRAITS: { key: keyof PersonalitySettings; label: string; options: [string, string] }[] = [
  { key: 'warmth', label: 'Warmth', options: ['warm', 'professional'] },
  { key: 'verbosity', label: 'Verbosity', options: ['chatty', 'concise'] },
  { key: 'formality', label: 'Formality', options: ['casual', 'formal'] },
]

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function getPreviewText(name: string, p: PersonalitySettings): string {
  if (p.warmth === 'warm' && p.verbosity === 'chatty') {
    return `"Hey there! ${name} here. I'd love to hear how your day's been going!"`
  }
  if (p.warmth === 'professional' && p.verbosity === 'concise') {
    return `"Good day. ${name} ready. How can I assist you today?"`
  }
  return `"Hi! I'm ${name}. How are you feeling today?"`
}

export function OnboardingPersonality({
  name,
  personality,
  onPersonalityChange,
  onNext,
  onBack,
}: OnboardingPersonalityProps) {
  function setTrait(key: keyof PersonalitySettings, value: string) {
    onPersonalityChange({ ...personality, [key]: value })
  }

  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>How should {name} communicate?</h1>
      {TRAITS.map((trait) => (
        <div key={trait.key} style={rowStyle}>
          <span style={rowLabelStyle}>{trait.label}</span>
          <div style={toggleGroupStyle}>
            <button
              style={{
                ...toggleBtnLeft,
                ...(personality[trait.key] === trait.options[0] ? activeToggle : inactiveToggle),
              }}
              onClick={() => setTrait(trait.key, trait.options[0])}
              aria-pressed={personality[trait.key] === trait.options[0]}
            >
              {capitalize(trait.options[0])}
            </button>
            <button
              style={{
                ...toggleBtnRight,
                ...(personality[trait.key] === trait.options[1] ? activeToggle : inactiveToggle),
              }}
              onClick={() => setTrait(trait.key, trait.options[1])}
              aria-pressed={personality[trait.key] === trait.options[1]}
            >
              {capitalize(trait.options[1])}
            </button>
          </div>
        </div>
      ))}
      <div style={previewStyle} data-testid="personality-preview">
        {getPreviewText(name, personality)}
      </div>
      <div style={navStyle}>
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button onClick={onNext}>Next</Button>
      </div>
    </div>
  )
}
