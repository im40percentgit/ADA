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
import type { CSSProperties } from 'react'
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

  const cardStyle: CSSProperties = {
    background: 'var(--color-bg-card)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-card)',
    padding: 'var(--space-xl)',
    width: '100%',
    maxWidth: '400px',
    boxShadow: 'var(--shadow-elevated)',
  }

  const inputStyle: CSSProperties = {
    width: '100%',
    background: 'var(--color-bg-elevated)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-input)',
    height: 'var(--touch-target-min)',
    padding: '0 var(--space-sm)',
    color: 'var(--color-text-primary)',
    fontFamily: 'var(--font-body)',
    fontSize: 'var(--size-body)',
    boxSizing: 'border-box' as const,
  }

  const submitStyle: CSSProperties = {
    width: '100%',
    background: 'var(--color-primary)',
    color: '#ffffff',
    border: 'none',
    borderRadius: 'var(--radius-button)',
    minHeight: 'var(--touch-target-min)',
    fontFamily: 'var(--font-body)',
    fontWeight: 600,
    fontSize: 'var(--size-body)',
    cursor: 'pointer',
  }

  return (
    <div className="login" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--color-bg-base)', fontFamily: 'var(--font-body)' }}>
      <div className="login__card" style={cardStyle}>
        <div className="login__brand" style={{ textAlign: 'center', marginBottom: 'var(--space-lg)' }}>
          <h1 className="login__brand-name" style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)', color: 'var(--color-text-primary)', margin: 0 }}>Ada</h1>
          <p className="login__brand-tagline" style={{ color: 'var(--color-text-muted)', fontSize: 'var(--size-sm)', margin: 'var(--space-xs) 0 0' }}>Mental Health Support</p>
        </div>

        <h2 className="login__section-title" style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)', margin: '0 0 var(--space-md)' }}>Reset your password</h2>

        {submitted ? (
          <div className="login__success" role="status" style={{ color: 'var(--color-text-secondary)', fontSize: 'var(--size-body)', lineHeight: 1.6 }}>
            <p>
              If an account with that email exists, we've sent a reset link.
              Check your console output.
            </p>
            <button
              className="login__link-btn"
              type="button"
              onClick={onBack}
              style={{ background: 'none', border: 'none', color: 'var(--color-primary-light)', fontSize: 'var(--size-sm)', cursor: 'pointer', padding: 'var(--space-sm)', fontFamily: 'var(--font-body)' }}
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form className="login__form" onSubmit={handleSubmit} noValidate style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
            <label className="login__label" htmlFor="forgot-email" style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginBottom: '4px', display: 'block' }}>
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
              style={inputStyle}
            />

            <button
              className="login__submit"
              type="submit"
              disabled={submitting || !email}
              style={{ ...submitStyle, opacity: (submitting || !email) ? 0.5 : 1 }}
            >
              {submitting ? 'Sending…' : 'Send reset link'}
            </button>

            <button
              className="login__link-btn"
              type="button"
              onClick={onBack}
              disabled={submitting}
              style={{ background: 'none', border: 'none', color: 'var(--color-primary-light)', fontSize: 'var(--size-sm)', cursor: 'pointer', padding: 'var(--space-sm)', fontFamily: 'var(--font-body)' }}
            >
              Back to sign in
            </button>
          </form>
        )}
      </div>
    </div>
  )
}
