/**
 * OnboardingFlow — wizard component managing the step sequence.
 *
 * Orchestrates navigation between onboarding screens based on the user's
 * role (patient or caregiver). Owns all wizard state (step, companion name,
 * voice, personality) and passes it down to pure presentational screens.
 *
 * On the final step's onNext, saves companion preferences and marks
 * onboarding as completed before calling the parent's onComplete callback.
 *
 * @decision DEC-ONBOARD-002
 * @title OnboardingFlow owns all wizard state, screens are pure
 * @status accepted
 * @rationale Centralising step navigation, preferences, and the completion
 *   side-effects (API calls) in a single component keeps the individual
 *   screens independently testable and the flow logic easy to follow.
 */

import { useState, useEffect, useRef, type CSSProperties } from 'react'
import { OnboardingWelcome } from './OnboardingWelcome'
import { OnboardingName } from './OnboardingName'
import { OnboardingVoice } from './OnboardingVoice'
import { OnboardingPersonality } from './OnboardingPersonality'
import { OnboardingChat } from './OnboardingChat'
import { OnboardingWellbeing } from './OnboardingWellbeing'
import { OnboardingCognitive } from './OnboardingCognitive'
import { OnboardingCircle } from './OnboardingCircle'
import { OnboardingDashboard } from './OnboardingDashboard'
import { OnboardingNotifications } from './OnboardingNotifications'
import { updateCompanionPreferences, setOnboardingStatus } from '../../api/client'
import type { PersonalitySettings } from './OnboardingPersonality'

export interface OnboardingFlowProps {
  role: 'user' | 'caregiver'
  onComplete: () => void
}

const TOTAL_STEPS = 7

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const wrapperStyle: CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  minHeight: '100vh',
  background: 'var(--color-bg-base, #fafafa)',
}

const headerStyle: CSSProperties = {
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  padding: 'var(--space-md) var(--space-lg)',
}

const dotsContainerStyle: CSSProperties = {
  display: 'flex',
  gap: '8px',
  justifyContent: 'center',
}

const stepCounterStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-sm, 12px)',
  color: 'var(--color-text-muted, #999)',
  textAlign: 'center',
  marginTop: 'var(--space-xs, 4px)',
}

const skipStyle: CSSProperties = {
  fontFamily: 'var(--font-body)',
  fontSize: 'var(--size-sm, 14px)',
  color: 'var(--color-text-muted, #999)',
  background: 'none',
  border: 'none',
  cursor: 'pointer',
  padding: 'var(--space-sm)',
  minHeight: 'var(--touch-target-min, 44px)',
  display: 'inline-flex',
  alignItems: 'center',
}

const contentStyle: CSSProperties = {
  flex: 1,
  display: 'flex',
  flexDirection: 'column',
  justifyContent: 'center',
}

function dotStyle(state: 'completed' | 'current' | 'future'): CSSProperties {
  const base: CSSProperties = {
    width: '10px',
    height: '10px',
    borderRadius: '50%',
    display: 'inline-block',
  }
  if (state === 'completed') {
    return { ...base, background: 'var(--color-primary, #6c63ff)' }
  }
  if (state === 'current') {
    return {
      ...base,
      background: 'var(--color-primary, #6c63ff)',
      boxShadow: '0 0 0 3px var(--color-primary-subtle, rgba(108,99,255,0.2))',
    }
  }
  // future
  return {
    ...base,
    background: 'transparent',
    border: '2px solid var(--color-border, #ddd)',
    boxSizing: 'border-box',
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function OnboardingFlow({ role, onComplete }: OnboardingFlowProps) {
  const [step, setStep] = useState(0)
  const [companionName, setCompanionName] = useState('Ada')
  const [voice, setVoice] = useState('female')
  const [personality, setPersonality] = useState<PersonalitySettings>({
    warmth: 'warm',
    verbosity: 'balanced',
    formality: 'casual',
  })
  const stepContainerRef = useRef<HTMLDivElement>(null)

  // Focus the step container when step changes
  useEffect(() => {
    stepContainerRef.current?.focus()
  }, [step])

  const goNext = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS - 1))
  const goBack = () => setStep((s) => Math.max(s - 1, 0))

  async function handleFinalNext() {
    try {
      await updateCompanionPreferences({
        name: companionName,
        voice: voice as 'male' | 'female' | 'neutral',
        personality,
      })
    } catch {
      // Best-effort — don't block onboarding completion if prefs fail
    }
    try {
      await setOnboardingStatus('completed')
    } catch {
      // Best-effort
    }
    onComplete()
  }

  async function handleSkip() {
    try {
      await setOnboardingStatus('completed')
    } catch {
      // Best-effort
    }
    onComplete()
  }

  // Determine which screen to render based on role and step
  function renderStep() {
    // Steps 0-3 are shared between patient and caregiver
    switch (step) {
      case 0:
        return <OnboardingWelcome onNext={goNext} />
      case 1:
        return (
          <OnboardingName
            name={companionName}
            onNameChange={setCompanionName}
            onNext={goNext}
            onBack={goBack}
          />
        )
      case 2:
        return (
          <OnboardingVoice
            name={companionName}
            voice={voice}
            onVoiceChange={setVoice}
            onNext={goNext}
            onBack={goBack}
          />
        )
      case 3:
        return (
          <OnboardingPersonality
            name={companionName}
            personality={personality}
            onPersonalityChange={setPersonality}
            onNext={goNext}
            onBack={goBack}
          />
        )
      default:
        break
    }

    // Steps 4-6 diverge by role
    if (role === 'user') {
      switch (step) {
        case 4:
          return <OnboardingChat name={companionName} onNext={goNext} onBack={goBack} />
        case 5:
          return <OnboardingWellbeing onNext={goNext} onBack={goBack} />
        case 6:
          return <OnboardingCognitive name={companionName} onNext={handleFinalNext} onBack={goBack} />
      }
    } else {
      // caregiver
      switch (step) {
        case 4:
          return <OnboardingCircle onNext={goNext} onBack={goBack} />
        case 5:
          return <OnboardingDashboard onNext={goNext} onBack={goBack} />
        case 6:
          return <OnboardingNotifications onNext={handleFinalNext} onBack={goBack} />
      }
    }

    return null
  }

  return (
    <div style={wrapperStyle} data-testid="onboarding-flow">
      {/* Header with progress and skip */}
      <div style={headerStyle}>
        <div style={{ flex: 1 }} />
        <div style={{ flex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
          <div style={dotsContainerStyle} data-testid="progress-dots">
            {Array.from({ length: TOTAL_STEPS }, (_, i) => {
              let state: 'completed' | 'current' | 'future'
              if (i < step) state = 'completed'
              else if (i === step) state = 'current'
              else state = 'future'
              return <span key={i} style={dotStyle(state)} data-testid={`dot-${i}`} aria-label={`Step ${i + 1} ${state}`} />
            })}
          </div>
          <span style={stepCounterStyle}>Step {step + 1} of {TOTAL_STEPS}</span>
        </div>
        <div style={{ flex: 1, display: 'flex', justifyContent: 'flex-end' }}>
          <button style={skipStyle} onClick={handleSkip} data-testid="skip-link">
            Skip
          </button>
        </div>
      </div>

      {/* Step content */}
      <div
        ref={stepContainerRef}
        style={contentStyle}
        tabIndex={-1}
        aria-label={`Onboarding step ${step + 1} of ${TOTAL_STEPS}`}
        data-testid="step-container"
      >
        {renderStep()}
      </div>
    </div>
  )
}
