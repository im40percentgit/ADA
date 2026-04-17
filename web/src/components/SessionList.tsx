/**
 * SessionList — session management sidebar
 *
 * Lists past sessions for a patient, allows starting a new session, and
 * selecting an existing session to resume. Fetches from /api/sessions.
 *
 * @decision DEC-FRONTEND-008
 * @title SessionList fetches on mount and on patientId change only
 * @status accepted
 * @rationale Sessions are created infrequently (one per conversation).
 *   Polling would waste requests; a full pub/sub setup is over-engineering
 *   for Phase 1. The parent App triggers a re-fetch by changing the key prop
 *   or calling the exposed refresh callback after session creation.
 */

import { useEffect, useState } from 'react'
import { listSessions, createSession } from '../api/client'
import type { Session } from '../types'
import { EmptyState } from './ui/EmptyState'

interface SessionListProps {
  patientId: string
  activeSessionId: string | null
  onSelectSession: (sessionId: string) => void
}

function formatSessionDate(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleDateString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function SessionList({
  patientId,
  activeSessionId,
  onSelectSession,
}: SessionListProps) {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listSessions(patientId)
      .then((s) => {
        if (!cancelled) setSessions(s)
      })
      .catch((err: unknown) => {
        if (!cancelled)
          setError(err instanceof Error ? err.message : 'Failed to load sessions')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [patientId])

  async function handleNewSession() {
    setCreating(true)
    setError(null)
    try {
      const session = await createSession({ patient_id: patientId })
      setSessions((prev) => [session, ...prev])
      onSelectSession(session.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create session')
    } finally {
      setCreating(false)
    }
  }

  return (
    <aside className="session-list" aria-label="Sessions">
      <div className="session-list__header">
        <h2 className="session-list__title">Sessions</h2>
        <button
          className="session-list__new-btn"
          onClick={handleNewSession}
          disabled={creating}
          aria-label="Start new session"
          type="button"
        >
          {creating ? '…' : '+ New'}
        </button>
      </div>

      {error && (
        <p className="session-list__error" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <p className="session-list__loading" aria-busy="true">
          Loading…
        </p>
      ) : sessions.length === 0 ? (
        <EmptyState
          tone="warm"
          icon="💬"
          title="No sessions yet"
          description="Start your first conversation with Ada."
          action={
            <button
              className="session-list__new-btn"
              onClick={handleNewSession}
              disabled={creating}
              aria-label="Start new session"
              type="button"
            >
              {creating ? '…' : '+ New Session'}
            </button>
          }
        />
      ) : (
        <ul className="session-list__items" role="list">
          {sessions.map((s) => (
            <li key={s.id}>
              <button
                className={`session-list__item${s.id === activeSessionId ? ' session-list__item--active' : ''}`}
                onClick={() => onSelectSession(s.id)}
                aria-current={s.id === activeSessionId ? 'true' : undefined}
                type="button"
              >
                <span className="session-list__item-date">
                  {formatSessionDate(s.started_at)}
                </span>
                {s.summary && (
                  <span className="session-list__item-summary">{s.summary}</span>
                )}
                {s.ended_at == null && s.id === activeSessionId && (
                  <span className="session-list__item-active-badge" aria-label="Active">
                    Active
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
