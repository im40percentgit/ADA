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
import type { CSSProperties } from 'react'
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

  const linkBtnStyle: CSSProperties = {
    background: 'none',
    border: 'none',
    color: 'var(--color-primary-light)',
    fontSize: 'var(--size-sm)',
    cursor: 'pointer',
    padding: 'var(--space-sm)',
    fontFamily: 'var(--font-body)',
  }

  if (!token) {
    return (
      <div className="login" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--color-bg-base)', fontFamily: 'var(--font-body)' }}>
        <div className="login__card" style={cardStyle}>
          <div className="login__brand" style={{ textAlign: 'center', marginBottom: 'var(--space-lg)' }}>
            <h1 className="login__brand-name" style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)', color: 'var(--color-text-primary)', margin: 0 }}>Ada</h1>
          </div>
          <p className="login__error" role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--size-sm)', margin: 'var(--space-xs) 0' }}>
            Invalid or expired reset link
          </p>
          <button className="login__link-btn" type="button" onClick={onBack} style={linkBtnStyle}>
            Back to sign in
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="login" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--color-bg-base)', fontFamily: 'var(--font-body)' }}>
      <div className="login__card" style={cardStyle}>
        <div className="login__brand" style={{ textAlign: 'center', marginBottom: 'var(--space-lg)' }}>
          <h1 className="login__brand-name" style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)', color: 'var(--color-text-primary)', margin: 0 }}>Ada</h1>
          <p className="login__brand-tagline" style={{ color: 'var(--color-text-muted)', fontSize: 'var(--size-sm)', margin: 'var(--space-xs) 0 0' }}>Mental Health Support</p>
        </div>

        <h2 className="login__section-title" style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', color: 'var(--color-text-primary)', margin: '0 0 var(--space-md)' }}>Set a new password</h2>

        <form className="login__form" onSubmit={handleSubmit} noValidate style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
          <label className="login__label" htmlFor="reset-new-password" style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginBottom: '4px', display: 'block' }}>
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
            style={inputStyle}
            aria-describedby={error ? 'reset-error' : undefined}
          />

          <label className="login__label" htmlFor="reset-confirm-password" style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginBottom: '4px', display: 'block' }}>
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
            style={inputStyle}
            aria-describedby={error ? 'reset-error' : undefined}
          />

          {error && (
            <p className="login__error" id="reset-error" role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--size-sm)', margin: 'var(--space-xs) 0' }}>
              {error}
            </p>
          )}

          <button
            className="login__submit"
            type="submit"
            disabled={submitting || !newPassword || !confirmPassword}
            style={{ ...submitStyle, opacity: (submitting || !newPassword || !confirmPassword) ? 0.5 : 1 }}
          >
            {submitting ? 'Saving…' : 'Set new password'}
          </button>

          <button
            className="login__link-btn"
            type="button"
            onClick={onBack}
            disabled={submitting}
            style={linkBtnStyle}
          >
            Back to sign in
          </button>
        </form>
      </div>
    </div>
  )
}
