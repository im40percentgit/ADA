/**
 * Login — login and registration form component
 *
 * Renders a single card that toggles between "Sign in" and "Create account"
 * modes. Uses the login/register methods from useAuth. Errors are displayed
 * inline below the submit button.
 *
 * Styling uses the existing CSS custom properties from App.css (--color-primary,
 * --color-error, --radius-md, etc.) via BEM-style class names (login__*).
 *
 * @decision DEC-FRONTEND-006
 * @title Login and Register share a single toggled form — no separate routes
 * @status accepted
 * @rationale Phase 2 has no routing library. A toggle within a single card
 *   gives the same UX benefit as two routes with a fraction of the complexity.
 *   If React Router is added in a later phase, this component splits naturally
 *   into two route-level components.
 */

import { useState, type FormEvent } from 'react'
import type { CSSProperties } from 'react'
import type { UseAuthReturn } from '../hooks/useAuth'

interface LoginProps {
  onLogin: UseAuthReturn['login']
  onRegister: (email: string, password: string, role?: string) => Promise<void>
  error: string | null
  onForgotPassword?: () => void
}

export function Login({ onLogin, onRegister, error, onForgotPassword }: LoginProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<string>('user')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      if (mode === 'login') {
        await onLogin(email, password)
      } else {
        await onRegister(email, password, role)
      }
    } catch {
      // Error is surfaced via the `error` prop from useAuth
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

  const labelStyle: CSSProperties = {
    fontSize: 'var(--size-caption)',
    color: 'var(--color-text-muted)',
    marginBottom: '4px',
    display: 'block',
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
        {/* Brand */}
        <div className="login__brand" style={{ textAlign: 'center', marginBottom: 'var(--space-lg)' }}>
          <h1 className="login__brand-name" style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h1)', color: 'var(--color-text-primary)', margin: 0 }}>Ada</h1>
          <p className="login__brand-tagline" style={{ color: 'var(--color-text-muted)', fontSize: 'var(--size-sm)', margin: 'var(--space-xs) 0 0' }}>Mental Health Support</p>
        </div>

        {/* Mode toggle */}
        <div className="login__tabs" role="tablist" style={{ display: 'flex', gap: 'var(--space-xs)', marginBottom: 'var(--space-lg)' }}>
          <button
            role="tab"
            aria-selected={mode === 'login'}
            className={`login__tab${mode === 'login' ? ' login__tab--active' : ''}`}
            onClick={() => setMode('login')}
            type="button"
            style={{
              flex: 1,
              padding: 'var(--space-sm)',
              borderRadius: 'var(--radius-button)',
              border: 'none',
              fontFamily: 'var(--font-body)',
              fontWeight: 600,
              fontSize: 'var(--size-sm)',
              cursor: 'pointer',
              minHeight: 'var(--touch-target-min)',
              background: mode === 'login' ? 'var(--color-primary)' : 'var(--color-bg-elevated)',
              color: mode === 'login' ? '#ffffff' : 'var(--color-text-muted)',
            }}
          >
            Sign in
          </button>
          <button
            role="tab"
            aria-selected={mode === 'register'}
            className={`login__tab${mode === 'register' ? ' login__tab--active' : ''}`}
            onClick={() => setMode('register')}
            type="button"
            style={{
              flex: 1,
              padding: 'var(--space-sm)',
              borderRadius: 'var(--radius-button)',
              border: 'none',
              fontFamily: 'var(--font-body)',
              fontWeight: 600,
              fontSize: 'var(--size-sm)',
              cursor: 'pointer',
              minHeight: 'var(--touch-target-min)',
              background: mode === 'register' ? 'var(--color-primary)' : 'var(--color-bg-elevated)',
              color: mode === 'register' ? '#ffffff' : 'var(--color-text-muted)',
            }}
          >
            Create account
          </button>
        </div>

        {/* Form */}
        <form className="login__form" onSubmit={handleSubmit} noValidate style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-sm)' }}>
          <label className="login__label" htmlFor="login-email" style={labelStyle}>
            Email
          </label>
          <input
            id="login-email"
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

          <label className="login__label" htmlFor="login-password" style={labelStyle}>
            Password
          </label>
          <input
            id="login-password"
            className="login__input"
            type="password"
            autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={mode === 'register' ? 'At least 8 characters' : '••••••••'}
            disabled={submitting}
            style={inputStyle}
            aria-describedby={error ? 'login-error' : undefined}
          />

          {mode === 'register' && (
            <>
              <label className="login__label" htmlFor="login-role" style={labelStyle}>
                Role
              </label>
              <select
                id="login-role"
                className="login__input"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                disabled={submitting}
                style={inputStyle}
              >
                <option value="user">Patient</option>
                <option value="caregiver">Caregiver</option>
              </select>
            </>
          )}

          {error && (
            <p className="login__error" id="login-error" role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--size-sm)', margin: 'var(--space-xs) 0' }}>
              {error}
            </p>
          )}

          <button
            className="login__submit"
            type="submit"
            disabled={submitting || !email || !password}
            style={{ ...submitStyle, opacity: (submitting || !email || !password) ? 0.5 : 1 }}
          >
            {submitting
              ? mode === 'login'
                ? 'Signing in…'
                : 'Creating account…'
              : mode === 'login'
                ? 'Sign in'
                : 'Create account'}
          </button>

          {mode === 'login' && onForgotPassword && (
            <button
              className="login__link-btn"
              type="button"
              onClick={onForgotPassword}
              disabled={submitting}
              style={{ background: 'none', border: 'none', color: 'var(--color-primary-light)', fontSize: 'var(--size-sm)', cursor: 'pointer', padding: 'var(--space-sm)', fontFamily: 'var(--font-body)' }}
            >
              Forgot password?
            </button>
          )}
        </form>
      </div>
    </div>
  )
}
