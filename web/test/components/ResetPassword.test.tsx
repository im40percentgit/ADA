/**
 * ResetPassword.test.tsx — component tests for the ResetPassword form.
 *
 * ResetPassword receives token, onSuccess, and onBack as props. It posts to
 * /api/auth/reset-password (via MSW). Tests cover rendering, client-side
 * validation (passwords must match, minimum length), success redirect,
 * API error states, and missing-token guard.
 *
 * @decision DEC-TEST-015
 * @title ResetPassword tests use MSW for API boundary — real component rendered
 * @status accepted
 * @rationale Same rationale as DEC-TEST-014. MSW intercepts at the HTTP
 *   boundary; the component and API client are real implementations.
 *   The MSW handler distinguishes 'invalid-token' (400) from valid tokens (200).
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { ResetPassword } from '../../src/components/ResetPassword'

function setup(overrides: {
  token?: string
  onSuccess?: ReturnType<typeof vi.fn>
  onBack?: ReturnType<typeof vi.fn>
} = {}) {
  const token = overrides.token ?? 'valid-reset-token'
  const onSuccess = overrides.onSuccess ?? vi.fn()
  const onBack = overrides.onBack ?? vi.fn()
  const user = userEvent.setup()
  render(<ResetPassword token={token} onSuccess={onSuccess} onBack={onBack} />)
  return { user, onSuccess, onBack }
}

describe('ResetPassword', () => {
  it('renders password fields and submit button', () => {
    setup()
    expect(screen.getByLabelText('New password')).toBeInTheDocument()
    expect(screen.getByLabelText('Confirm password')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Set new password' })).toBeInTheDocument()
  })

  it('submit button is disabled when fields are empty', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Set new password' })).toBeDisabled()
  })

  it('shows error when passwords do not match', async () => {
    const { user } = setup()
    await user.type(screen.getByLabelText('New password'), 'Password123!')
    await user.type(screen.getByLabelText('Confirm password'), 'DifferentPass!')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/do not match/i)
    })
  })

  it('shows error when password is too short', async () => {
    const { user } = setup()
    await user.type(screen.getByLabelText('New password'), 'short')
    await user.type(screen.getByLabelText('Confirm password'), 'short')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/at least 8/i)
    })
  })

  it('calls onSuccess after a successful reset', async () => {
    const { user, onSuccess } = setup({ token: 'valid-token' })
    await user.type(screen.getByLabelText('New password'), 'NewPassword123!')
    await user.type(screen.getByLabelText('Confirm password'), 'NewPassword123!')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))

    await waitFor(() => {
      expect(onSuccess).toHaveBeenCalledOnce()
    })
  })

  it('shows error when server returns 400 (invalid token)', async () => {
    const { user } = setup({ token: 'invalid-token' })
    await user.type(screen.getByLabelText('New password'), 'NewPassword123!')
    await user.type(screen.getByLabelText('Confirm password'), 'NewPassword123!')
    await user.click(screen.getByRole('button', { name: 'Set new password' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/invalid or expired/i)
    })
  })

  it('renders error guard when token is empty string', () => {
    setup({ token: '' })
    expect(screen.getByRole('alert')).toHaveTextContent(/invalid or expired/i)
    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument()
  })

  it('calls onBack when back link is clicked', async () => {
    const { user, onBack } = setup()
    await user.click(screen.getByRole('button', { name: 'Back to sign in' }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('shows submitting state while request is in flight', async () => {
    const { user } = setup({ token: 'valid-token' })
    await user.type(screen.getByLabelText('New password'), 'NewPassword123!')
    await user.type(screen.getByLabelText('Confirm password'), 'NewPassword123!')

    user.click(screen.getByRole('button', { name: 'Set new password' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Saving/i })).toBeDisabled()
    })
  })
})
