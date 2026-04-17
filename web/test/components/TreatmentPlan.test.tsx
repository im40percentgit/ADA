/**
 * TreatmentPlan.test.tsx — component tests for the treatment plan UI.
 *
 * Tests:
 *   - Renders plan title in detail mode
 *   - Renders goals with progress bars
 *   - Add goal form submits correctly
 *   - List mode renders plan cards
 *   - Add intervention form works
 *
 * Data is served by MSW handlers using makeTreatmentPlan/makeGoal factories.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { TreatmentPlan } from '../../src/components/TreatmentPlan'
import { makeTreatmentPlan, makeGoal, makeIntervention } from '../factories'

function renderPlan(props: Partial<Parameters<typeof TreatmentPlan>[0]> = {}) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  const defaultProps = {
    patientId: 'patient-1',
    onBack: () => {},
    ...props,
  }
  return render(<TreatmentPlan {...defaultProps} />)
}

describe('TreatmentPlan', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders plan title in detail mode', async () => {
    const plan = makeTreatmentPlan({ id: 'plan-test', title: 'CBT Protocol' })
    server.use(
      http.get('/api/treatment-plans/:planId', () => {
        return HttpResponse.json(plan)
      }),
    )

    renderPlan({ planId: 'plan-test' })

    await waitFor(() => {
      expect(screen.getByTestId('plan-title')).toHaveTextContent('CBT Protocol')
    })
  })

  it('renders goals with progress', async () => {
    const plan = makeTreatmentPlan({
      id: 'plan-test',
      title: 'Test Plan',
      goals: [
        makeGoal({
          id: 'goal-a',
          description: 'Reduce depression',
          target_metric: 'phq9',
          target_operator: '<',
          target_value: 10,
          current_value: 14,
          status: 'active',
        }),
      ],
    })

    server.use(
      http.get('/api/treatment-plans/:planId', () => {
        return HttpResponse.json(plan)
      }),
    )

    renderPlan({ planId: 'plan-test' })

    await waitFor(() => {
      expect(screen.getByTestId('goal-description')).toHaveTextContent('Reduce depression')
    })
    expect(screen.getByTestId('goal-target')).toHaveTextContent('PHQ-9 < 10')
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('add goal form works', async () => {
    const user = userEvent.setup()
    const plan = makeTreatmentPlan({ id: 'plan-form', title: 'Form Test', goals: [] })

    server.use(
      http.get('/api/treatment-plans/:planId', () => {
        return HttpResponse.json(plan)
      }),
      http.post('/api/treatment-plans/:planId/goals', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        return HttpResponse.json(
          makeGoal({
            description: body.description as string,
            target_metric: body.target_metric as 'phq9' | null,
            interventions: [],
          }),
          { status: 201 },
        )
      }),
    )

    renderPlan({ planId: 'plan-form' })

    await waitFor(() => {
      expect(screen.getByTestId('plan-title')).toHaveTextContent('Form Test')
    })

    // Open the form
    await user.click(screen.getByText('+ Add Goal'))

    // Fill in the description
    const descInput = screen.getByLabelText('Goal description')
    await user.type(descInput, 'Lower anxiety')

    // Submit — use getByRole to target the button specifically (not the h3 heading)
    await user.click(screen.getByRole('button', { name: 'Add Goal' }))

    // Goal should appear in the list
    await waitFor(() => {
      expect(screen.getByTestId('goal-description')).toHaveTextContent('Lower anxiety')
    })
  })

  it('renders plan list in list mode', async () => {
    server.use(
      http.get('/api/patients/:patientId/treatment-plans', () => {
        return HttpResponse.json([
          makeTreatmentPlan({ id: 'plan-a', title: 'Plan Alpha' }),
          makeTreatmentPlan({ id: 'plan-b', title: 'Plan Beta' }),
        ])
      }),
    )

    renderPlan()

    await waitFor(() => {
      expect(screen.getByText('Plan Alpha')).toBeInTheDocument()
    })
    expect(screen.getByText('Plan Beta')).toBeInTheDocument()
    expect(screen.getByText('Treatment Plans')).toBeInTheDocument()
  })

  it('shows empty state when no plans exist', async () => {
    server.use(
      http.get('/api/patients/:patientId/treatment-plans', () => {
        return HttpResponse.json([])
      }),
    )

    renderPlan()

    await waitFor(() => {
      // EmptyState title has no trailing period
      expect(screen.getByText('No treatment plans yet')).toBeInTheDocument()
    })
  })

  it('shows error state on API failure', async () => {
    server.use(
      http.get('/api/patients/:patientId/treatment-plans', () => {
        return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      }),
    )

    renderPlan()

    await waitFor(() => {
      // ErrorState uses role="status" (polite live region), not role="alert"
      expect(screen.getByRole('status', { name: /Error state/i })).toBeInTheDocument()
    })
  })

  it('loading container has aria-busy="true"', () => {
    renderPlan()
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument()
  })
})
