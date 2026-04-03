/**
 * ForgotPassword — request a password-reset link.
 *
 * Renders a single email-input form. On submit, calls POST /api/auth/forgot-password.
 * Always shows the same success message regardless of whether the email exists,
 * to prevent email enumeration. Includes a back link to return to login.
 *
 * @decision DEC-FRONTEND-012
 * @title ForgotPassword always shows success message — no enumeration
 * @status accepted
 * @rationale The backend always returns 200. The frontend mirrors that: a single
 *   success message is shown regardless of the backend's actual action. This
 *   prevents leaking account existence via the UI even if the user inspects
 *   network responses.
 */

import { useState, type FormEvent } from 'react'
import { forgotPassword } from '../api/auth'

interface ForgotPasswordProps {
  onBack: () => void
}

export function ForgotPassword({ onBack }: ForgotPasswordProps) {
  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      await forgotPassword(email)
    } catch {
      // Intentionally swallowed — we always show the success message
      // to prevent leaking whether the email exists.
    } finally {
      setSubmitting(false)
      setSubmitted(true)
    }
  }

  return (
    <div className="login">
      <div className="login__card">
        <div className="login__brand">
          <h1 className="login__brand-name">Ada</h1>
          <p className="login__brand-tagline">Mental Health Support</p>
        </div>

        <h2 className="login__section-title">Reset your password</h2>

        {submitted ? (
          <div className="login__success" role="status">
            <p>
              If an account with that email exists, we've sent a reset link.
              Check your console output.
            </p>
            <button
              className="login__link-btn"
              type="button"
              onClick={onBack}
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form className="login__form" onSubmit={handleSubmit} noValidate>
            <label className="login__label" htmlFor="forgot-email">
              Email address
            </label>
            <input
              id="forgot-email"
              className="login__input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              disabled={submitting}
            />

            <button
              className="login__submit"
              type="submit"
              disabled={submitting || !email}
            >
              {submitting ? 'Sending…' : 'Send reset link'}
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
        )}
      </div>
    </div>
  )
}
