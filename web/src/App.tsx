/**
 * App — root component
 *
 * Manages authentication state via useAuth, then patient/session selection
 * and view routing for authenticated users. Renders the Login component when
 * the user is not authenticated, and a loading spinner while the stored token
 * is being validated on mount.
 *
 * Patient context: for a 'user' role account, currentUser.patient_id is the
 * linked patient record. Clinician/admin accounts have no linked patient so we
 * fall back to DEMO_PATIENT_ID — this lets non-patient accounts still exercise
 * the UI during development.
 *
 * @decision DEC-FRONTEND-010
 * @title Auth wraps App root — Login gate replaces hardcoded DEMO_PATIENT_ID
 * @status superseded
 * @rationale Phase 1 used a hardcoded DEMO_PATIENT_ID (no auth). Phase 2
 *   introduces real JWT auth via useAuth. The patient_id now comes from
 *   currentUser.patient_id (for user-role accounts). The DEMO_PATIENT_ID
 *   fallback is retained only for clinician/admin accounts so the UI
 *   remains functional in development without needing a patient-linked user.
 *
 * @decision DEC-FRONTEND-011
 * @title Loading spinner blocks render until token validation resolves
 * @status accepted
 * @rationale On cold load, useAuth calls /api/auth/me with the stored token
 *   before setting currentUser. Blocking render prevents a flash of the login
 *   screen for already-authenticated users. The spinner disappears in <200 ms
 *   on a local server; for production a skeleton layout is preferable.
 *
 * @decision DEC-FRONTEND-014
 * @title Hash-based routing for forgot-password and reset-password views
 * @status accepted
 * @rationale The app uses no routing library. Two new auth-adjacent views
 *   (ForgotPassword, ResetPassword) are injected before the auth gate so
 *   unauthenticated users can access them. Hash detection runs once on mount
 *   via window.location.hash — no router setup required. The reset token is
 *   parsed from the hash query string (/#/reset-password?token=...).
 */

import { useState } from 'react'
import { SessionList } from './components/SessionList'
import { Chat } from './components/Chat'
import { MoodChart } from './components/MoodChart'
import { Login } from './components/Login'
import { ForgotPassword } from './components/ForgotPassword'
import { ResetPassword } from './components/ResetPassword'
import { CaregiverDashboard } from './components/CaregiverDashboard'
import { PatientDashboard } from './components/PatientDashboard'
import { ConnectionStatus } from './components/ConnectionStatus'
import { useAuth } from './hooks/useAuth'
import type { ReconnectingWsStatus } from './hooks/useReconnectingWebSocket'
import './App.css'

// Fallback patient ID for clinician/admin accounts in development
const DEMO_PATIENT_ID = 'demo-patient-001'

type View = 'home' | 'chat' | 'mood'
type AuthView = 'login' | 'forgot-password' | 'reset-password'

/** Parse the initial auth view from the URL hash (e.g. /#/reset-password?token=...) */
function parseInitialAuthView(): { view: AuthView; resetToken: string } {
  const hash = window.location.hash // e.g. "#/reset-password?token=abc"
  if (hash.includes('/reset-password')) {
    const search = hash.includes('?') ? hash.slice(hash.indexOf('?')) : ''
    const token = new URLSearchParams(search).get('token') ?? ''
    return { view: 'reset-password', resetToken: token }
  }
  if (hash.includes('/forgot-password')) {
    return { view: 'forgot-password', resetToken: '' }
  }
  return { view: 'login', resetToken: '' }
}

const _initial = parseInitialAuthView()

export default function App() {
  const { currentUser, isAuthenticated, loading, error, login, logout, register } = useAuth()
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [view, setView] = useState<View>('home')
  const [chatWsStatus, setChatWsStatus] = useState<ReconnectingWsStatus>('connecting')
  const [authView, setAuthView] = useState<AuthView>(_initial.view)
  const [resetToken] = useState<string>(_initial.resetToken)
  const [resetSuccessMsg, setResetSuccessMsg] = useState<string | null>(null)

  // While token validation is in flight, show a minimal loading screen
  if (loading) {
    return (
      <div className="app__loading" role="status" aria-label="Loading">
        <div className="app__loading-spinner" />
      </div>
    )
  }

  // Unauthenticated — show login/register/forgot-password/reset-password
  if (!isAuthenticated) {
    if (authView === 'forgot-password') {
      return (
        <ForgotPassword onBack={() => setAuthView('login')} />
      )
    }
    if (authView === 'reset-password') {
      return (
        <ResetPassword
          token={resetToken}
          onSuccess={() => {
            setResetSuccessMsg('Password updated. Please sign in with your new password.')
            window.location.hash = ''
            setAuthView('login')
          }}
          onBack={() => setAuthView('login')}
        />
      )
    }
    return (
      <Login
        onLogin={login}
        onRegister={register}
        error={resetSuccessMsg ?? error}
        onForgotPassword={() => setAuthView('forgot-password')}
      />
    )
  }

  // Caregiver role — show dedicated dashboard instead of chat/mood
  if (currentUser?.role === 'caregiver') {
    return (
      <div className="app">
        <CaregiverDashboard onLogout={logout} />
      </div>
    )
  }

  // Resolve patient ID: prefer the linked patient on the user account
  const patientId = currentUser?.patient_id ?? DEMO_PATIENT_ID

  return (
    <div className="app">
      <ConnectionStatus status={chatWsStatus} />

      {/* Sidebar */}
      <div className="app__sidebar">
        <div className="app__brand">
          <h1 className="app__brand-name">Ada</h1>
          <p className="app__brand-tagline">Mental Health Support</p>
        </div>

        <nav className="app__nav" aria-label="Main navigation">
          <button
            className={`app__nav-btn${view === 'home' ? ' app__nav-btn--active' : ''}`}
            onClick={() => setView('home')}
            aria-current={view === 'home' ? 'page' : undefined}
            type="button"
          >
            Home
          </button>
          <button
            className={`app__nav-btn${view === 'chat' ? ' app__nav-btn--active' : ''}`}
            onClick={() => setView('chat')}
            aria-current={view === 'chat' ? 'page' : undefined}
            type="button"
          >
            Chat
          </button>
          <button
            className={`app__nav-btn${view === 'mood' ? ' app__nav-btn--active' : ''}`}
            onClick={() => setView('mood')}
            aria-current={view === 'mood' ? 'page' : undefined}
            type="button"
          >
            Mood
          </button>
        </nav>

        <SessionList
          patientId={patientId}
          activeSessionId={activeSessionId}
          onSelectSession={setActiveSessionId}
        />

        {/* User info + logout */}
        <div className="app__user-bar">
          <span className="app__user-email" title={currentUser?.email}>
            {currentUser?.email}
          </span>
          <button
            className="app__logout-btn"
            onClick={logout}
            type="button"
            aria-label="Sign out"
          >
            Sign out
          </button>
        </div>
      </div>

      {/* Main content */}
      <div className="app__main">
        {view === 'home' ? (
          <PatientDashboard patientId={patientId} onNavigateToChat={() => setView('chat')} />
        ) : view === 'chat' ? (
          activeSessionId ? (
            <Chat sessionId={activeSessionId} patientId={patientId} onWsStatusChange={setChatWsStatus} />
          ) : (
            <div className="app__no-session">
              <p>Select a session or start a new one to begin.</p>
            </div>
          )
        ) : (
          <div className="app__mood-view">
            <h2 className="app__mood-title">Your Mood History</h2>
            <MoodChart patientId={patientId} />
          </div>
        )}
      </div>
    </div>
  )
}
