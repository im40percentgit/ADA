/**
 * ResetPassword — consume a reset token and set a new password.
 *
 * Reads the raw token from the URL query param: /#/reset-password?token=abc123
 * Renders a new-password + confirm-password form with client-side validation:
 *   - passwords must match
 *   - minimum 8 characters
 * On success: calls onSuccess() so App can redirect to login with a message.
 * On API error (400): displays "Invalid or expired reset link".
 *
 * @decision DEC-FRONTEND-013
 * @title Token read from URL hash query param — no server-side routing needed
 * @status accepted
 * @rationale App uses hash-based navigation (no React Router). The reset URL
 *   is /#/reset-password?token=... — we parse window.location.hash to extract
 *   the token. This keeps the frontend self-contained with no routing library.
 */

import { useState, type FormEvent } from 'react'
import { resetPassword } from '../api/auth'

interface ResetPasswordProps {
  token: string
  onSuccess: () => void
  onBack: () => void
}

export function ResetPassword({ token, onSuccess, onBack }: ResetPasswordProps) {
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function validate(): string | null {
    if (newPassword.length < 8) {
      return 'Password must be at least 8 characters'
    }
    if (newPassword !== confirmPassword) {
      return 'Passwords do not match'
    }
    return null
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    const validationError = validate()
    if (validationError) {
      setError(validationError)
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await resetPassword(token, newPassword)
      onSuccess()
    } catch {
      setError('Invalid or expired reset link')
    } finally {
      setSubmitting(false)
    }
  }

  if (!token) {
    return (
      <div className="login">
        <div className="login__card">
          <div className="login__brand">
            <h1 className="login__brand-name">Ada</h1>
          </div>
          <p className="login__error" role="alert">
            Invalid or expired reset link
          </p>
          <button className="login__link-btn" type="button" onClick={onBack}>
            Back to sign in
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="login">
      <div className="login__card">
        <div className="login__brand">
          <h1 className="login__brand-name">Ada</h1>
          <p className="login__brand-tagline">Mental Health Support</p>
        </div>

        <h2 className="login__section-title">Set a new password</h2>

        <form className="login__form" onSubmit={handleSubmit} noValidate>
          <label className="login__label" htmlFor="reset-new-password">
            New password
          </label>
          <input
            id="reset-new-password"
            className="login__input"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            placeholder="At least 8 characters"
            disabled={submitting}
          />

          <label className="login__label" htmlFor="reset-confirm-password">
            Confirm password
          </label>
          <input
            id="reset-confirm-password"
            className="login__input"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Repeat your new password"
            disabled={submitting}
          />

          {error && (
            <p className="login__error" role="alert">
              {error}
            </p>
          )}

          <button
            className="login__submit"
            type="submit"
            disabled={submitting || !newPassword || !confirmPassword}
          >
            {submitting ? 'Saving…' : 'Set new password'}
          </button>

          <button
            className="login__link-btn"
            type="button"
            onClick={onBack}
            disabled={submitting}
          >
            Back to sign in
          </button>
        </form>
      </div>
    </div>
  )
}
