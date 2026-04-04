/**
 * OnboardingFlow.test.tsx — tests for the onboarding wizard component.
 *
 * Verifies step navigation, progress dots, skip functionality, and
 * role-specific screen sequences (patient vs caregiver paths).
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { OnboardingFlow } from '../../src/components/onboarding/OnboardingFlow'

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
    expect(screen.getByText(/What would you like to call your companion/)).toBeTruthy()
  })

  it('back button goes to previous step', async () => {
    const { user } = setup()
    // Advance to step 1 (name)
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    expect(screen.getByText(/What would you like to call your companion/)).toBeTruthy()

    // Go back to step 0 (welcome)
    await user.click(screen.getByRole('button', { name: 'Back' }))
    expect(screen.getByText('Welcome to Ada')).toBeTruthy()
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

    // Advance to step 1
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
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

    // Step 0 → 1 (name)
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    // Step 1 → 2 (voice)
    await user.click(screen.getByRole('button', { name: 'Next' }))
    // Step 2 → 3 (personality)
    await user.click(screen.getByRole('button', { name: 'Next' }))
    // Step 3 → 4 (chat — patient-specific)
    await user.click(screen.getByRole('button', { name: 'Next' }))

    // OnboardingChat shows "Talk to Ada anytime" heading
    expect(screen.getByText(/Talk to Ada anytime/)).toBeTruthy()
  })

  it('caregiver role shows caregiver screens at step 4 (circle)', async () => {
    const { user } = setup('caregiver')

    // Step 0 → 1 (name)
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    // Step 1 → 2 (voice)
    await user.click(screen.getByRole('button', { name: 'Next' }))
    // Step 2 → 3 (personality)
    await user.click(screen.getByRole('button', { name: 'Next' }))
    // Step 3 → 4 (circle — caregiver-specific)
    await user.click(screen.getByRole('button', { name: 'Next' }))

    // OnboardingCircle shows care circle heading
    expect(screen.getByText(/Set up your care circle/)).toBeTruthy()
  })

  it('caregiver step 5 shows dashboard screen (differs from patient)', async () => {
    const { user } = setup('caregiver')

    // Navigate to step 5
    await user.click(screen.getByRole('button', { name: 'Get Started' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))

    // OnboardingDashboard shows "Your command center" heading
    expect(screen.getByText(/Your command center/)).toBeTruthy()
  })
})
