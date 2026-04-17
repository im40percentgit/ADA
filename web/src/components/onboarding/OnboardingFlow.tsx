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
 *
 * @decision DEC-MOTION-005
 * @title Step transition: fade-out 120ms, then fade-in + slide 240ms, direction-aware
 * @status accepted
 * @rationale Onboarding steps are heavyweight full-screen views; abrupt swaps
 *   are visually jarring and provide no spatial cue. The two-phase approach
 *   (short exit at 120ms, then directional entrance at 240ms) maps to the
 *   spec exactly: outgoing disappears quickly so the user isn't kept waiting,
 *   incoming slides from ±8px so forward/back feel physically distinct.
 *
 *   State machine: `direction` captures forward/back intent at the moment the
 *   navigation button is pressed. `transitionPhase` cycles idle → exiting →
 *   entering → idle. `displayedStep` lags behind `step` during the exit phase
 *   and is updated only when entering begins, so the exiting content is the
 *   correct outgoing frame.
 *
 *   CSS class variants `.onboarding-step--enter-forward` and
 *   `.onboarding-step--enter-back` apply translateX(8px) vs translateX(-8px)
 *   as the enter start-frame; both resolve to translateX(0) on
 *   `.onboarding-step--entering` so the slide reads as inward motion.
 *
 *   Focus management: the existing Phase 13c focus-on-step-change useEffect
 *   fires on `displayedStep` updates, which happen right as the entering
 *   phase begins — matching the visual frame of the new content appearing.
 *   This preserves the 13c contract without additional timing coupling.
 *
 *   Reduced-motion: the blanket prefers-reduced-motion override in base.css
 *   (DEC-MOTION-002) zeroes all transition durations, so the 120ms exit and
 *   240ms entrance collapse to ~0ms. No per-component override is needed.
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

// Duration constants mirror the motion tokens so setTimeout values stay in sync.
// These are JS-side only; CSS reads from var(--motion-duration-*) directly.
const EXIT_DURATION_MS = 120  // fade-out before swap
const ENTER_DURATION_MS = 240 // --motion-duration-base: slide + fade-in

type Direction = 'forward' | 'back'
type TransitionPhase = 'idle' | 'exiting' | 'entering'

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
  const [displayedStep, setDisplayedStep] = useState(0)
  const [direction, setDirection] = useState<Direction>('forward')
  const [transitionPhase, setTransitionPhase] = useState<TransitionPhase>('idle')
  const [companionName, setCompanionName] = useState('Ada')
  const [voice, setVoice] = useState('female')
  const [personality, setPersonality] = useState<PersonalitySettings>({
    warmth: 'warm',
    verbosity: 'balanced',
    formality: 'casual',
  })
  const stepContainerRef = useRef<HTMLDivElement>(null)

  // Focus the step container when the displayed step changes (Phase 13c contract).
  // Fires when displayedStep updates — which is exactly when entering begins and
  // the new content is placed in the DOM.
  useEffect(() => {
    stepContainerRef.current?.focus()
  }, [displayedStep])

  // Orchestrate the two-phase transition whenever `step` changes.
  useEffect(() => {
    // Skip on initial mount (step === displayedStep, nothing to transition).
    if (step === displayedStep) return

    // Phase 1 — exit: current content fades out over EXIT_DURATION_MS.
    setTransitionPhase('exiting')

    const exitTimer = setTimeout(() => {
      // Phase 2 — entering: swap to new content, apply enter class.
      setDisplayedStep(step)
      setTransitionPhase('entering')

      const enterTimer = setTimeout(() => {
        // Phase 3 — idle: entrance animation complete, remove classes.
        setTransitionPhase('idle')
      }, ENTER_DURATION_MS)

      return () => clearTimeout(enterTimer)
    }, EXIT_DURATION_MS)

    return () => clearTimeout(exitTimer)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  function navigate(targetStep: number, dir: Direction) {
    if (transitionPhase !== 'idle') return // guard: ignore during active transition
    setDirection(dir)
    setStep(targetStep)
  }

  const goNext = () => navigate(Math.min(step + 1, TOTAL_STEPS - 1), 'forward')
  const goBack = () => navigate(Math.max(step - 1, 0), 'back')

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

  // Build CSS class string for the step container based on transition phase + direction.
  function stepClassName(): string {
    const classes = ['onboarding-step']
    if (transitionPhase === 'exiting') {
      classes.push('onboarding-step--exiting')
    } else if (transitionPhase === 'entering') {
      classes.push('onboarding-step--entering')
      classes.push(
        direction === 'forward'
          ? 'onboarding-step--enter-forward'
          : 'onboarding-step--enter-back',
      )
    }
    return classes.join(' ')
  }

  // Determine which screen to render based on role and displayedStep.
  // Uses displayedStep (not step) so exiting content stays visible during fade-out.
  function renderStep() {
    switch (displayedStep) {
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

    if (role === 'user') {
      switch (displayedStep) {
        case 4:
          return <OnboardingChat name={companionName} onNext={goNext} onBack={goBack} />
        case 5:
          return <OnboardingWellbeing onNext={goNext} onBack={goBack} />
        case 6:
          return <OnboardingCognitive name={companionName} onNext={handleFinalNext} onBack={goBack} />
      }
    } else {
      // caregiver
      switch (displayedStep) {
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

      {/* Step content — transition wrapper */}
      <div
        ref={stepContainerRef}
        style={contentStyle}
        tabIndex={-1}
        aria-label={`Onboarding step ${step + 1} of ${TOTAL_STEPS}`}
        data-testid="step-container"
        className={stepClassName()}
        data-transition-phase={transitionPhase}
        data-direction={direction}
      >
        {renderStep()}
      </div>
    </div>
  )
}
