/**
 * App — root component
 *
 * Manages patient/session selection and composes the sidebar (SessionList),
 * main chat area (Chat), and mood chart. Uses a hardcoded patient_id for
 * Phase 1 (no auth).
 *
 * @decision DEC-FRONTEND-010
 * @title Hardcoded DEMO_PATIENT_ID for Phase 1 — no auth
 * @status accepted
 * @rationale Phase 1 explicitly excludes authentication (per MASTER_PLAN.md
 *   Non-Goals). A single hardcoded patient_id lets the UI exercise all
 *   API paths without a login flow. Replace with real auth in Phase 2.
 */

import { useState } from 'react'
import { SessionList } from './components/SessionList'
import { Chat } from './components/Chat'
import { MoodChart } from './components/MoodChart'
import './App.css'

// Phase 1: no auth — hardcoded patient for demo
const DEMO_PATIENT_ID = 'demo-patient-001'

type View = 'chat' | 'mood'

export default function App() {
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [view, setView] = useState<View>('chat')

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
          patientId={DEMO_PATIENT_ID}
          activeSessionId={activeSessionId}
          onSelectSession={setActiveSessionId}
        />
      </div>

      {/* Main content */}
      <div className="app__main">
        {view === 'chat' ? (
          activeSessionId ? (
            <Chat sessionId={activeSessionId} patientId={DEMO_PATIENT_ID} />
          ) : (
            <div className="app__no-session">
              <p>Select a session or start a new one to begin.</p>
            </div>
          )
        ) : (
          <div className="app__mood-view">
            <h2 className="app__mood-title">Your Mood History</h2>
            <MoodChart patientId={DEMO_PATIENT_ID} />
          </div>
        )}
      </div>
    </div>
  )
}
