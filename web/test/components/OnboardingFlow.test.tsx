/**
 * OnboardingFlow.test.tsx — tests for the onboarding wizard component.
 *
 * Verifies step navigation, progress dots, skip functionality,
 * role-specific screen sequences (patient vs caregiver paths), and
 * step transition motion behavior (DEC-MOTION-005).
 */

import { render, screen, within, act, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { OnboardingFlow } from '../../src/components/onboarding/OnboardingFlow'

// Helper: wait for the step-container to return to idle phase, meaning the full
// two-phase transition (120ms exit + 240ms enter) has completed and buttons are
// no longer blocked by the transition guard.
async function waitForIdle() {
  await waitFor(() => {
    const container = document.querySelector('[data-testid="step-container"]')
    if (container?.getAttribute('data-transition-phase') !== 'idle') {
      throw new Error('transition not idle yet')
    }
  }, { timeout: 1000 })
}

function setup(role: 'user' | 'caregiver' = 'user') {
  const onComplete = vi.fn()
  const user = userEvent.setup()
  render(<OnboardingFlow role={role} onComplete={onComplete} />)
  return { onComplete, user }
}

describe('OnboardingFlow', () => {
  it('renders welcome screen initially', () => {
    setup()
    expect(screen.getByText('Welcome to Ada')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Get Started' })).toBeTruthy()
  })

  it('"Get Started" advances to step 2 (name screen)', async () => {
    const { user } = setup()
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    // Wait for the transition (120ms exit + displayedStep swap) to complete
    await waitFor(() => screen.getByText(/What would you like to call your companion/))
  })

  it('back button goes to previous step', async () => {
    const { user } = setup()
    // Advance to step 1 (name) and wait for full transition to idle
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    await waitFor(() => screen.getByText(/What would you like to call your companion/))
    await waitForIdle()

    // Go back to step 0 (welcome)
    await user.click(screen.getByRole('button', { name: 'Back' }))
    await waitFor(() => screen.getByText('Welcome to Ada'))
  })

  it('progress dots show correct count (7)', () => {
    setup()
    const dotsContainer = screen.getByTestId('progress-dots')
    const dots = within(dotsContainer).getAllByTestId(/^dot-/)
    expect(dots).toHaveLength(7)
  })

  it('progress dots reflect current step', async () => {
    const { user } = setup()
    // Step 0: first dot is current
    const dot0 = screen.getByTestId('dot-0')
    expect(dot0.getAttribute('aria-label')).toBe('Step 1 current')

    const dot1 = screen.getByTestId('dot-1')
    expect(dot1.getAttribute('aria-label')).toBe('Step 2 future')

    // Advance to step 1 — dots update when `step` state changes (immediately on click)
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    // `step` increments synchronously; `displayedStep` lags but dots use `step`
    expect(screen.getByTestId('dot-0').getAttribute('aria-label')).toBe('Step 1 completed')
    expect(screen.getByTestId('dot-1').getAttribute('aria-label')).toBe('Step 2 current')
  })

  it('step counter shows correct text', () => {
    setup()
    expect(screen.getByText('Step 1 of 7')).toBeTruthy()
  })

  it('skip link calls onComplete', async () => {
    const { user, onComplete } = setup()
    await user.click(screen.getByTestId('skip-link'))
    expect(onComplete).toHaveBeenCalledTimes(1)
  })

  it('patient role shows patient screens at step 4 (chat)', async () => {
    const { user } = setup('user')

    // Each step: click, wait for content, wait for idle before next click
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    await waitFor(() => screen.getByText(/What would you like to call your companion/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/Choose Ada's voice/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/How should Ada communicate/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/Talk to Ada anytime/))
  })

  it('caregiver role shows caregiver screens at step 4 (circle)', async () => {
    const { user } = setup('caregiver')

    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    await waitFor(() => screen.getByText(/What would you like to call your companion/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/Choose Ada's voice/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/How should Ada communicate/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/Set up your care circle/))
  })

  it('caregiver step 5 shows dashboard screen (differs from patient)', async () => {
    const { user } = setup('caregiver')

    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    await waitFor(() => screen.getByText(/What would you like to call your companion/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/Choose Ada's voice/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/How should Ada communicate/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/Set up your care circle/))
    await waitForIdle()

    await user.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => screen.getByText(/Your command center/))
  })
})

// ---------------------------------------------------------------------------
// Step transition motion tests (DEC-MOTION-005)
// ---------------------------------------------------------------------------
// jsdom does not execute CSS transitions, so we assert class names and
// data attributes that reflect the transition state machine. This verifies
// the JS state machine wiring without requiring a real browser.
// ---------------------------------------------------------------------------

// Motion tests use fireEvent (synchronous) + vi.useFakeTimers so we can control
// the setTimeout sequencing without userEvent's internal timer dependencies.
describe('OnboardingFlow — step transition motion (DEC-MOTION-005)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('forward navigation: exiting class applied immediately after Next click', () => {
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    // fireEvent is synchronous — no internal timer dependencies
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Get Started' }))
    })

    const container = screen.getByTestId('step-container')
    expect(container.getAttribute('data-transition-phase')).toBe('exiting')
    expect(container.className).toContain('onboarding-step--exiting')
  })

  it('forward navigation: enter-forward class applied after exit duration (120ms)', () => {
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Get Started' }))
    })

    // Advance past the 120ms exit phase — displayedStep swaps, entering begins
    act(() => { vi.advanceTimersByTime(130) })

    const container = screen.getByTestId('step-container')
    expect(container.getAttribute('data-transition-phase')).toBe('entering')
    expect(container.className).toContain('onboarding-step--enter-forward')
    expect(screen.getByText(/What would you like to call your companion/)).toBeTruthy()
  })

  it('forward navigation: direction attribute is "forward"', () => {
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Get Started' }))
    })

    const container = screen.getByTestId('step-container')
    expect(container.getAttribute('data-direction')).toBe('forward')
  })

  it('back navigation: enter-back class applied after exit duration', () => {
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    // Navigate forward to step 1 and let transition fully settle (idle)
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Get Started' }))
    })
    act(() => { vi.advanceTimersByTime(400) }) // clears exit (120ms) + enter (240ms)

    // Now go back — transition guard is idle, click registers
    act(() => {
      fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    })

    const container = screen.getByTestId('step-container')
    expect(container.getAttribute('data-transition-phase')).toBe('exiting')

    // Advance past exit phase — displayedStep swaps to step 0, entering begins
    act(() => { vi.advanceTimersByTime(130) })
    expect(container.getAttribute('data-transition-phase')).toBe('entering')
    expect(container.className).toContain('onboarding-step--enter-back')
    expect(container.getAttribute('data-direction')).toBe('back')
  })

  it('back navigation: direction attribute is "back"', () => {
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    // Navigate to step 1 and settle to idle
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Get Started' })) })
    act(() => { vi.advanceTimersByTime(400) })

    // Navigate back and advance past exit phase
    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Back' })) })
    act(() => { vi.advanceTimersByTime(130) })

    const container = screen.getByTestId('step-container')
    expect(container.getAttribute('data-direction')).toBe('back')
  })

  it('transition settles to idle phase after full animation completes', () => {
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Get Started' })) })

    // Advance past both exit (120ms) + enter (240ms) phases with margin
    act(() => { vi.advanceTimersByTime(400) })

    const container = screen.getByTestId('step-container')
    expect(container.getAttribute('data-transition-phase')).toBe('idle')
    expect(container.className).not.toContain('onboarding-step--exiting')
    expect(container.className).not.toContain('onboarding-step--entering')
  })

  it('focus lands on step-container when entering phase begins (13c contract)', () => {
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Get Started' })) })
    act(() => { vi.advanceTimersByTime(130) })

    const container = screen.getByTestId('step-container')
    // The useEffect fires on displayedStep change which happens at entering start
    expect(document.activeElement).toBe(container)
  })

  it('reduced-motion: JS state machine cycles through all phases (CSS handles instant swap)', () => {
    // jsdom does not apply CSS, so only the JS state machine is verifiable here.
    // The CSS blanket override (DEC-MOTION-002) zeroes transition-duration in real
    // browsers so the user sees an instant swap — tested by visual QA, not jsdom.
    render(<OnboardingFlow role="user" onComplete={vi.fn()} />)

    act(() => { fireEvent.click(screen.getByRole('button', { name: 'Get Started' })) })

    const container = screen.getByTestId('step-container')
    expect(container.getAttribute('data-transition-phase')).toBe('exiting')

    act(() => { vi.advanceTimersByTime(130) })
    expect(container.getAttribute('data-transition-phase')).toBe('entering')

    act(() => { vi.advanceTimersByTime(250) })
    expect(container.getAttribute('data-transition-phase')).toBe('idle')
    expect(screen.getByText(/What would you like to call your companion/)).toBeTruthy()
  })
})
