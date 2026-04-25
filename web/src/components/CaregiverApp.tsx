/**
 * CaregiverApp — caregiver role sub-tree.
 *
 * Extracted from App.tsx so that `useCircles()` is called inside a component
 * that only mounts AFTER the auth gate. When it lived at the App root level,
 * the hook fired once on mount; if the initial fetch resolved before the JWT
 * was settled, `selectedCircle` stayed null and every caregiver navigation
 * click silently no-op'd back to CaregiverDashboard.
 *
 * By isolating the hook here, it always fires with a valid auth token in
 * context, so `selectedCircle` (and thus `cgPatientId`) is populated before
 * any sub-view can be entered.
 *
 * Settings and LabelDay access: caregivers can navigate to Settings via the
 * dashboard and from there to /admin/label-day. LabelDayPage receives both
 * the patient ID and patient name from the resolved care circle — the caregiver
 * always sees "Labeling for: {patient_name}" so they know whose data they are
 * labeling. (DEC-VERDICT-009, DEC-VERDICT-010)
 *
 * @decision DEC-FRONTEND-020
 * @title CaregiverApp isolates useCircles() to avoid auth-timing race
 * @status accepted
 * @rationale App.tsx previously hoisted useCircles() to satisfy Rules of
 *   Hooks. That caused a race: the hook fires once on mount, and if the
 *   initial /api/circles fetch resolves before the JWT cookie is available
 *   (e.g. on cold load), selectedCircle stays null. Every caregiver navigation
 *   then hits the `if (!cgPatientId) return <CaregiverDashboard/>` guard and
 *   navigation silently no-ops. Extracting the caregiver branch into this
 *   component means the hook only runs when a caregiver user is authenticated
 *   — the component itself only mounts after the auth gate in App.tsx.
 *
 * @decision DEC-VERDICT-009
 * @title /admin/label-day is caregiver-primary; Settings reachable from CaregiverApp
 * @status accepted
 * @rationale The founder's actual user is a caregiver of a dementia patient who
 *   cannot manage daily UI tasks. The 21-day calibration loop runs through the
 *   caregiver, not the patient. Settings is now a named view in CaregiverApp's
 *   View union and is reachable from CaregiverDashboard. LabelDayPage receives
 *   patientName from the resolved care circle so the caregiver always knows
 *   which patient they are labeling.
 *
 * @decision DEC-VERDICT-010
 * @title Caregiver patient resolution via care-circle membership — N=1 assumption
 * @status accepted
 * @rationale CaregiverApp already owns useCircles() (DEC-FRONTEND-020), which
 *   auto-selects the first circle. selectedCircle.patient_id + patient_name are
 *   passed directly to LabelDayPage — no additional fetch required. Multi-patient
 *   caregivers (Phase 16+) will need a patient picker; not in scope here.
 */

import { CaregiverDashboard } from './CaregiverDashboard'
import { KnowledgeGraph } from './KnowledgeGraph'
import { ProgressReport } from './ProgressReport'
import { SessionSummary } from './SessionSummary'
import { DailySummaryDetail } from './DailySummaryDetail'
import { CognitiveScreening } from './CognitiveScreening'
import { ScreeningResults } from './ScreeningResults'
import { ScreeningHistory } from './ScreeningHistory'
import { TreatmentPlan } from './TreatmentPlan'
import { PrescribingNotes } from './PrescribingNotes'
import { SettingsPage } from './SettingsPage'
import { LabelDayPage } from '../admin/LabelDayPage'
import { useCircles } from '../hooks/useCircles'
import type { UserProfile } from '../hooks/useAuth'

type View =
  | 'home'
  | 'chat'
  | 'mood'
  | 'knowledge-graph'
  | 'progress'
  | 'session-summary'
  | 'daily-summary'
  | 'cognitive-screening'
  | 'screening-results'
  | 'screening-history'
  | 'settings'
  | 'treatment-plan'
  | 'prescribing-notes'
  | 'admin-label-day'

export interface CaregiverAppProps {
  currentUser: UserProfile
  logout: () => void
  view: View
  setView: (v: View) => void
  selectedSessionId: string | null
  setSelectedSessionId: (id: string | null) => void
  selectedSummaryDate: string | null
  setSelectedSummaryDate: (d: string | null) => void
  selectedScreeningId: string | null
  setSelectedScreeningId: (id: string | null) => void
  selectedPlanId: string | null
  installBanner: React.ReactNode
}

/**
 * Renders the full caregiver experience: dashboard + all sub-views.
 * Owns its own `useCircles()` instance so navigation always has a valid
 * patient ID after auth settles.
 */
export function CaregiverApp({
  currentUser,
  logout,
  view,
  setView,
  selectedSessionId,
  setSelectedSessionId,
  selectedSummaryDate,
  setSelectedSummaryDate,
  selectedScreeningId,
  setSelectedScreeningId,
  selectedPlanId,
  installBanner,
}: CaregiverAppProps) {
  const { selectedCircle } = useCircles()
  const cgPatientId = selectedCircle?.patient_id
  const cgPatientName = selectedCircle?.patient_name

  // If no circle is selected yet (loading, or caregiver has no circles),
  // skip all sub-views and fall through to CaregiverDashboard which has
  // its own empty/loading state for this case.
  if (!cgPatientId) {
    return (
      <div className="app">
        {installBanner}
        <CaregiverDashboard
          onLogout={logout}
          onNavigate={(v) => setView(v as View)}
          onViewSession={(id) => { setSelectedSessionId(id); setView('session-summary') }}
          onViewDailySummary={(date) => { setSelectedSummaryDate(date); setView('daily-summary') }}
        />
      </div>
    )
  }

  return (
    <div className="app">
      {installBanner}
      {view === 'knowledge-graph' ? (
        <KnowledgeGraph patientId={cgPatientId} clinicalOverlay onBack={() => setView('home')} />
      ) : view === 'progress' ? (
        <ProgressReport patientId={cgPatientId} onBack={() => setView('home')} />
      ) : view === 'session-summary' && selectedSessionId ? (
        <SessionSummary sessionId={selectedSessionId} onBack={() => setView('home')} />
      ) : view === 'daily-summary' && selectedSummaryDate ? (
        <DailySummaryDetail
          patientId={cgPatientId}
          date={selectedSummaryDate}
          onBack={() => setView('home')}
          onViewSession={(id) => { setSelectedSessionId(id); setView('session-summary') }}
        />
      ) : view === 'cognitive-screening' ? (
        <CognitiveScreening
          patientId={cgPatientId}
          onBack={() => setView('home')}
          onComplete={(id) => { setSelectedScreeningId(id); setView('screening-results') }}
        />
      ) : view === 'screening-results' ? (
        <ScreeningResults
          patientId={cgPatientId}
          screeningId={selectedScreeningId!}
          onBack={() => setView('screening-history')}
        />
      ) : view === 'screening-history' ? (
        <ScreeningHistory
          patientId={cgPatientId}
          onViewScreening={(id) => { setSelectedScreeningId(id); setView('screening-results') }}
        />
      ) : view === 'treatment-plan' ? (
        <TreatmentPlan
          patientId={cgPatientId}
          planId={selectedPlanId ?? undefined}
          onBack={() => setView('home')}
        />
      ) : view === 'prescribing-notes' ? (
        <PrescribingNotes
          patientId={cgPatientId}
          onBack={() => setView('home')}
        />
      ) : view === 'settings' ? (
        <SettingsPage
          email={currentUser?.email}
          patientId={cgPatientId}
          onNavigate={(v) => setView(v as View)}
        />
      ) : view === 'admin-label-day' ? (
        <LabelDayPage
          patientId={cgPatientId}
          patientName={cgPatientName}
          onBack={() => setView('settings')}
        />
      ) : (
        <CaregiverDashboard
          onLogout={logout}
          onNavigate={(v) => setView(v as View)}
          onViewSession={(id) => { setSelectedSessionId(id); setView('session-summary') }}
          onViewDailySummary={(date) => { setSelectedSummaryDate(date); setView('daily-summary') }}
        />
      )}
    </div>
  )
}
