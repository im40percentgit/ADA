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

import { useState, useEffect } from 'react'
import { Chat } from './components/Chat'
import { MoodChart } from './components/MoodChart'
import { Login } from './components/Login'
import { ForgotPassword } from './components/ForgotPassword'
import { ResetPassword } from './components/ResetPassword'
import { CaregiverApp } from './components/CaregiverApp'
import { PatientDashboard } from './components/PatientDashboard'
import { KnowledgeGraph } from './components/KnowledgeGraph'
import { ProgressReport } from './components/ProgressReport'
import { SessionSummary } from './components/SessionSummary'
import { DailySummaryDetail } from './components/DailySummaryDetail'
import { CognitiveScreening } from './components/CognitiveScreening'
import { ScreeningResults } from './components/ScreeningResults'
import { ScreeningHistory } from './components/ScreeningHistory'
import { ConnectionStatus } from './components/ConnectionStatus'
import { InstallBanner } from './components/InstallBanner'
import { AppShell } from './components/AppShell'
import { SettingsPage } from './components/SettingsPage'
import { SessionList } from './components/SessionList'
import { OnboardingFlow } from './components/onboarding/OnboardingFlow'
import { useAuth } from './hooks/useAuth'
import type { ReconnectingWsStatus } from './hooks/useReconnectingWebSocket'
import { getOnboardingStatus } from './api/client'
import './App.css'

// Fallback patient ID for clinician/admin accounts in development
const DEMO_PATIENT_ID = 'demo-patient-001'

type View = 'home' | 'chat' | 'mood' | 'knowledge-graph' | 'progress' | 'session-summary' | 'daily-summary' | 'cognitive-screening' | 'screening-results' | 'screening-history' | 'settings' | 'treatment-plan' | 'prescribing-notes'
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
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [selectedSummaryDate, setSelectedSummaryDate] = useState<string | null>(null)
  const [selectedScreeningId, setSelectedScreeningId] = useState<string | null>(null)
  const [selectedPlanId] = useState<string | null>(null)
  const [onboardingComplete, setOnboardingComplete] = useState(true)

  // Check onboarding status when user becomes authenticated
  useEffect(() => {
    if (!isAuthenticated) return
    let cancelled = false
    getOnboardingStatus()
      .then(({ status }) => {
        if (!cancelled && status !== 'completed') {
          setOnboardingComplete(false)
        }
      })
      .catch(() => {
        // On error, assume onboarding is complete so the app is still usable
      })
    return () => { cancelled = true }
  }, [isAuthenticated])

  // While token validation is in flight, show a minimal loading screen
  if (loading) {
    return (
      <div className="app__loading" role="status" aria-label="Loading">
        <div className="app__loading-spinner" />
      </div>
    )
  }

  // InstallBanner is rendered as a portal-like overlay before the main tree
  // so it appears regardless of auth state or current view.
  const installBanner = <InstallBanner />

  // Unauthenticated — show login/register/forgot-password/reset-password
  if (!isAuthenticated) {
    if (authView === 'forgot-password') {
      return (
        <>
          {installBanner}
          <ForgotPassword onBack={() => setAuthView('login')} />
        </>
      )
    }
    if (authView === 'reset-password') {
      return (
        <>
          {installBanner}
          <ResetPassword
            token={resetToken}
            onSuccess={() => {
              setResetSuccessMsg('Password updated. Please sign in with your new password.')
              window.location.hash = ''
              setAuthView('login')
            }}
            onBack={() => setAuthView('login')}
          />
        </>
      )
    }
    return (
      <>
        {installBanner}
        <Login
          onLogin={login}
          onRegister={register}
          error={resetSuccessMsg ?? error}
          onForgotPassword={() => setAuthView('forgot-password')}
        />
      </>
    )
  }

  // Onboarding gate — show wizard before main app if not completed
  if (!onboardingComplete) {
    return (
      <>
        {installBanner}
        <OnboardingFlow
          role={currentUser?.role === 'caregiver' ? 'caregiver' : 'user'}
          onComplete={() => setOnboardingComplete(true)}
        />
      </>
    )
  }

  // Caregiver role — delegate entirely to CaregiverApp which owns useCircles()
  // internally (mounted only after auth gate, so the hook always fires with a
  // valid token — see DEC-FRONTEND-020 in CaregiverApp.tsx).
  if (currentUser?.role === 'caregiver') {
    return (
      <CaregiverApp
        currentUser={currentUser}
        logout={logout}
        view={view}
        setView={setView}
        selectedSessionId={selectedSessionId}
        setSelectedSessionId={setSelectedSessionId}
        selectedSummaryDate={selectedSummaryDate}
        setSelectedSummaryDate={setSelectedSummaryDate}
        selectedScreeningId={selectedScreeningId}
        setSelectedScreeningId={setSelectedScreeningId}
        selectedPlanId={selectedPlanId}
        installBanner={installBanner}
      />
    )
  }

  // Resolve patient ID: prefer the linked patient on the user account
  const patientId = currentUser?.patient_id ?? DEMO_PATIENT_ID

  // Map View state to tab IDs for AppShell navigation
  const viewToTab: Record<string, string> = {
    home: 'home',
    chat: 'chat',
    'knowledge-graph': 'journey',
    settings: 'settings',
  }
  const activeTab = viewToTab[view] ?? 'home'

  // Map tab ID back to View
  const handleTabChange = (tabId: string) => {
    const tabToView: Record<string, View> = {
      home: 'home',
      chat: 'chat',
      journey: 'knowledge-graph',
      settings: 'settings',
    }
    setView(tabToView[tabId] ?? 'home')
  }

  const greeting = currentUser?.email
    ? `Hi, ${currentUser.email.split('@')[0]}`
    : 'Welcome back'

  return (
    <div className="app">
      {installBanner}
      <ConnectionStatus status={chatWsStatus} />

      <AppShell
        activeTab={activeTab}
        onTabChange={handleTabChange}
        greeting={greeting}
        subtitle="How are you today?"
        onLogout={logout}
      >
        {view === 'knowledge-graph' ? (
          <KnowledgeGraph patientId={patientId} clinicalOverlay={currentUser?.role !== 'user'} onBack={() => setView('home')} />
        ) : view === 'progress' ? (
          <ProgressReport patientId={patientId} onBack={() => setView('home')} />
        ) : view === 'session-summary' && selectedSessionId ? (
          <SessionSummary sessionId={selectedSessionId} onBack={() => setView('home')} />
        ) : view === 'daily-summary' && selectedSummaryDate ? (
          <DailySummaryDetail
            patientId={patientId}
            date={selectedSummaryDate}
            onBack={() => setView('home')}
            onViewSession={(id) => { setSelectedSessionId(id); setView('session-summary') }}
          />
        ) : view === 'cognitive-screening' ? (
          <CognitiveScreening
            patientId={patientId}
            onBack={() => setView('home')}
            onComplete={(id) => { setSelectedScreeningId(id); setView('screening-results') }}
          />
        ) : view === 'screening-results' ? (
          <ScreeningResults
            patientId={patientId}
            screeningId={selectedScreeningId!}
            onBack={() => setView('screening-history')}
          />
        ) : view === 'screening-history' ? (
          <ScreeningHistory
            patientId={patientId}
            onViewScreening={(id) => { setSelectedScreeningId(id); setView('screening-results') }}
          />
        ) : view === 'home' ? (
          <PatientDashboard patientId={patientId} onNavigate={(v) => setView(v as View)} />
        ) : view === 'chat' ? (
          activeSessionId ? (
            <Chat sessionId={activeSessionId} patientId={patientId} onWsStatusChange={setChatWsStatus} />
          ) : (
            <SessionList
              patientId={patientId}
              activeSessionId={activeSessionId}
              onSelectSession={setActiveSessionId}
            />
          )
        ) : view === 'settings' ? (
          <SettingsPage email={currentUser?.email} patientId={patientId} />
        ) : (
          <div className="app__mood-view">
            <h2 className="app__mood-title">Your Mood History</h2>
            <MoodChart patientId={patientId} />
          </div>
        )}
      </AppShell>
    </div>
  )
}
