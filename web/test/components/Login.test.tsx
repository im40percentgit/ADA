/**
 * Login.test.tsx — component tests for the Login/Register form.
 *
 * Login is a pure presentational component: it receives onLogin, onRegister,
 * and error as props. Tests verify the form renders correctly, mode toggling
 * works, and the prop callbacks are invoked with the right arguments.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { Login } from '../../src/components/Login'

function setup(overrides: {
  onLogin?: ReturnType<typeof vi.fn>
  onRegister?: ReturnType<typeof vi.fn>
  error?: string | null
} = {}) {
  const onLogin = overrides.onLogin ?? vi.fn().mockResolvedValue(undefined)
  const onRegister = overrides.onRegister ?? vi.fn().mockResolvedValue(undefined)
  const error = overrides.error ?? null
  const user = userEvent.setup()

  render(<Login onLogin={onLogin} onRegister={onRegister} error={error} />)
  return { onLogin, onRegister, user }
}

describe('Login', () => {
  it('renders sign-in tab selected by default', () => {
    setup()
    expect(screen.getByRole('tab', { name: 'Sign in' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Create account' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('renders email and password inputs', () => {
    setup()
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('submit button is disabled when fields are empty', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeDisabled()
  })

  it('calls onLogin with email and password on submit', async () => {
    const { onLogin, user } = setup()

    await user.type(screen.getByLabelText('Email'), 'test@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(onLogin).toHaveBeenCalledWith('test@example.com', 'password123')
    })
  })

  it('switches to register mode and shows role selector', async () => {
    const { user } = setup()

    await user.click(screen.getByRole('tab', { name: 'Create account' }))

    expect(screen.getByRole('tab', { name: 'Create account' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByLabelText('Role')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument()
  })

  it('calls onRegister with email, password, and role on register submit', async () => {
    const { onRegister, user } = setup()

    await user.click(screen.getByRole('tab', { name: 'Create account' }))
    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.selectOptions(screen.getByLabelText('Role'), 'caregiver')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    await waitFor(() => {
      expect(onRegister).toHaveBeenCalledWith('new@example.com', 'password123', 'caregiver')
    })
  })

  it('displays error message when error prop is set', () => {
    setup({ error: 'Invalid credentials' })
    expect(screen.getByRole('alert')).toHaveTextContent('Invalid credentials')
  })

  it('shows submitting state while login is in flight', async () => {
    // onLogin that never resolves so we can observe the submitting state
    let resolve!: () => void
    const onLogin = vi.fn().mockReturnValue(new Promise<void>(r => { resolve = r }))
    const { user } = setup({ onLogin })

    await user.type(screen.getByLabelText('Email'), 'test@example.com')
    await user.type(screen.getByLabelText('Password'), 'password123')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Signing in/i })).toBeDisabled()
    })

    // Clean up: resolve the promise so the component finishes
    resolve()
  })
})
