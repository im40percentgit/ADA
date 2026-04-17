/**
 * ErrorState.test.tsx — component tests for the ErrorState UI primitive.
 *
 * Verifies:
 * - Title and message render
 * - Retry button renders only when onRetry is provided
 * - Retry button fires the callback
 * - action prop renders additional CTA when provided
 * - role="status" and aria-label a11y attributes present
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ErrorState } from '../../../src/components/ui/ErrorState'

describe('ErrorState', () => {
  it('renders title and message', () => {
    render(<ErrorState title="Something went wrong" message="Network error" />)
    expect(screen.getByText('Something went wrong')).toBeTruthy()
    expect(screen.getByText('Network error')).toBeTruthy()
  })

  it('has role=status and aria-label', () => {
    const { container } = render(
      <ErrorState title="Error" message="Failed" />
    )
    const el = container.querySelector('[role="status"]')
    expect(el).toBeTruthy()
    expect(el?.getAttribute('aria-label')).toBe('Error state')
  })

  it('does not render retry button when onRetry is absent', () => {
    render(<ErrorState title="Error" message="Failed" />)
    expect(screen.queryByRole('button', { name: /try again/i })).toBeNull()
  })

  it('renders retry button when onRetry is provided', () => {
    const onRetry = vi.fn()
    render(<ErrorState title="Error" message="Failed" onRetry={onRetry} />)
    expect(screen.getByRole('button', { name: /try again/i })).toBeTruthy()
  })

  it('fires onRetry when retry button is clicked', async () => {
    const onRetry = vi.fn()
    render(<ErrorState title="Error" message="Failed" onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: /try again/i }))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('renders action slot when provided', () => {
    render(
      <ErrorState
        title="Error"
        message="Failed"
        action={<button>Go home</button>}
      />
    )
    expect(screen.getByRole('button', { name: 'Go home' })).toBeTruthy()
  })

  it('renders both retry and action when both provided', async () => {
    const onRetry = vi.fn()
    render(
      <ErrorState
        title="Error"
        message="Failed"
        onRetry={onRetry}
        action={<button>Go home</button>}
      />
    )
    expect(screen.getByRole('button', { name: /try again/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Go home' })).toBeTruthy()
  })
})
