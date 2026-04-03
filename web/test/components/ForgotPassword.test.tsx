/**
 * ForgotPassword.test.tsx — component tests for the ForgotPassword form.
 *
 * ForgotPassword receives an onBack callback as its only prop and calls the
 * forgotPassword API function (via MSW). Tests verify rendering, form submission,
 * success state, and back-link behaviour.
 *
 * @decision DEC-TEST-014
 * @title ForgotPassword tests use MSW for API boundary — real component rendered
 * @status accepted
 * @rationale The component calls forgotPassword() from api/auth.ts. MSW intercepts
 *   the real fetch call at the network boundary — the component and API client
 *   module are exercised as real implementations. Only the HTTP server is
 *   substituted, which is the correct external boundary for a frontend test.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ForgotPassword } from '../../src/components/ForgotPassword'

function setup(onBack = vi.fn()) {
  const user = userEvent.setup()
  render(<ForgotPassword onBack={onBack} />)
  return { user, onBack }
}

describe('ForgotPassword', () => {
  it('renders the email input and submit button', () => {
    setup()
    expect(screen.getByLabelText('Email address')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send reset link' })).toBeInTheDocument()
  })

  it('submit button is disabled when email is empty', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Send reset link' })).toBeDisabled()
  })

  it('submit button is enabled when email is entered', async () => {
    const { user } = setup()
    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    expect(screen.getByRole('button', { name: 'Send reset link' })).not.toBeDisabled()
  })

  it('shows submitting state while request is in flight', async () => {
    const { user } = setup()
    await user.type(screen.getByLabelText('Email address'), 'test@example.com')

    // Don't await the click — observe the loading state
    user.click(screen.getByRole('button', { name: 'Send reset link' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sending/i })).toBeDisabled()
    })
  })

  it('shows success message after submission', async () => {
    const { user } = setup()
    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
    expect(screen.getByRole('status')).toHaveTextContent(/reset link/i)
  })

  it('shows success message even for unknown email (no enumeration)', async () => {
    const { user } = setup()
    // MSW always returns 200 regardless
    await user.type(screen.getByLabelText('Email address'), 'nobody@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    await waitFor(() => {
      expect(screen.getByRole('status')).toBeInTheDocument()
    })
  })

  it('shows back link after success', async () => {
    const { user, onBack } = setup()
    await user.type(screen.getByLabelText('Email address'), 'test@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Back to sign in' })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'Back to sign in' }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('calls onBack when the pre-submit back link is clicked', async () => {
    const { user, onBack } = setup()
    await user.click(screen.getByRole('button', { name: 'Back to sign in' }))
    expect(onBack).toHaveBeenCalledOnce()
  })
})
