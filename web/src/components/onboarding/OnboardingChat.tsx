/**
 * OnboardingChat — patient-path screen introducing the chat feature.
 *
 * Shows a description of the chat capability with a mock chat bubble visual
 * to give patients a preview of the conversation experience.
 *
 * @decision DEC-ONBOARD-001
 * @title Onboarding screens are pure presentational components
 * @status accepted
 */

import type { CSSProperties } from 'react'
import { Button } from '../ui/Button'

export interface OnboardingChatProps {
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

const chatVisualStyle: CSSProperties = {
  width: '100%',
  background: 'var(--color-bg-card)',
  borderRadius: 'var(--radius-card)',
  padding: 'var(--space-md)',
  marginBottom: 'var(--space-xl)',
  border: '1px solid var(--color-border)',
}

const bubbleAssistantStyle: CSSProperties = {
  background: 'var(--color-primary-subtle)',
  borderRadius: '12px 12px 12px 4px',
  padding: 'var(--space-sm) var(--space-md)',
  color: 'var(--color-text-secondary)',
  fontSize: 'var(--size-sm)',
  fontFamily: 'var(--font-body)',
  maxWidth: '80%',
  marginBottom: 'var(--space-sm)',
}

const bubbleUserStyle: CSSProperties = {
  background: 'var(--color-primary)',
  borderRadius: '12px 12px 4px 12px',
  padding: 'var(--space-sm) var(--space-md)',
  color: '#ffffff',
  fontSize: 'var(--size-sm)',
  fontFamily: 'var(--font-body)',
  maxWidth: '80%',
  marginLeft: 'auto',
  marginBottom: 'var(--space-sm)',
}

const navStyle: CSSProperties = {
  display: 'flex',
  gap: 'var(--space-md)',
  width: '100%',
}

export function OnboardingChat({ name, onNext, onBack }: OnboardingChatProps) {
  return (
    <div style={containerStyle}>
      <h1 style={headingStyle}>Talk to {name} anytime</h1>
      <p style={descStyle}>
        Share how you&apos;re feeling, ask questions, or just chat. {name} is
        always here to listen and support you.
      </p>
      <div style={chatVisualStyle} aria-hidden="true">
        <div style={bubbleAssistantStyle}>
          Hi! How are you feeling today?
        </div>
        <div style={bubbleUserStyle}>
          Pretty good, thanks for asking!
        </div>
        <div style={bubbleAssistantStyle}>
          That&apos;s wonderful to hear! Tell me more about your day.
        </div>
      </div>
      <div style={navStyle}>
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button onClick={onNext}>Next</Button>
      </div>
    </div>
  )
}
