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
 */

import { useState } from 'react'
import { SessionList } from './components/SessionList'
import { Chat } from './components/Chat'
import { MoodChart } from './components/MoodChart'
import { Login } from './components/Login'
import { CaregiverDashboard } from './components/CaregiverDashboard'
import { useAuth } from './hooks/useAuth'
import './App.css'

// Fallback patient ID for clinician/admin accounts in development
const DEMO_PATIENT_ID = 'demo-patient-001'

type View = 'chat' | 'mood'

export default function App() {
  const { currentUser, isAuthenticated, loading, error, login, logout, register } = useAuth()
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [view, setView] = useState<View>('chat')

  // While token validation is in flight, show a minimal loading screen
  if (loading) {
    return (
      <div className="app__loading" role="status" aria-label="Loading">
        <div className="app__loading-spinner" />
      </div>
    )
  }

  // Unauthenticated — show login/register gate
  if (!isAuthenticated) {
    return <Login onLogin={login} onRegister={register} error={error} />
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
      {/* Sidebar */}
      <div className="app__sidebar">
        <div className="app__brand">
          <h1 className="app__brand-name">Ada</h1>
          <p className="app__brand-tagline">Mental Health Support</p>
        </div>

        <nav className="app__nav" aria-label="Main navigation">
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
        {view === 'chat' ? (
          activeSessionId ? (
            <Chat sessionId={activeSessionId} patientId={patientId} />
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
