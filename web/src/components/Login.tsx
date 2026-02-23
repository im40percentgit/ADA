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
import type { UseAuthReturn } from '../hooks/useAuth'

interface LoginProps {
  onLogin: UseAuthReturn['login']
  onRegister: UseAuthReturn['register']
  error: string | null
}

export function Login({ onLogin, onRegister, error }: LoginProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    try {
      if (mode === 'login') {
        await onLogin(email, password)
      } else {
        await onRegister(email, password)
      }
    } catch {
      // Error is surfaced via the `error` prop from useAuth
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="login">
      <div className="login__card">
        {/* Brand */}
        <div className="login__brand">
          <h1 className="login__brand-name">Ada</h1>
          <p className="login__brand-tagline">Mental Health Support</p>
        </div>

        {/* Mode toggle */}
        <div className="login__tabs" role="tablist">
          <button
            role="tab"
            aria-selected={mode === 'login'}
            className={`login__tab${mode === 'login' ? ' login__tab--active' : ''}`}
            onClick={() => setMode('login')}
            type="button"
          >
            Sign in
          </button>
          <button
            role="tab"
            aria-selected={mode === 'register'}
            className={`login__tab${mode === 'register' ? ' login__tab--active' : ''}`}
            onClick={() => setMode('register')}
            type="button"
          >
            Create account
          </button>
        </div>

        {/* Form */}
        <form className="login__form" onSubmit={handleSubmit} noValidate>
          <label className="login__label" htmlFor="login-email">
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
          />

          <label className="login__label" htmlFor="login-password">
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
          />

          {error && (
            <p className="login__error" role="alert">
              {error}
            </p>
          )}

          <button
            className="login__submit"
            type="submit"
            disabled={submitting || !email || !password}
          >
            {submitting
              ? mode === 'login'
                ? 'Signing in…'
                : 'Creating account…'
              : mode === 'login'
                ? 'Sign in'
                : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  )
}
