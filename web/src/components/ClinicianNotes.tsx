/**
 * ClinicianNotes — reusable annotation component for clinical entities.
 *
 * Fetches existing notes for a given entity (session_summary or daily_summary)
 * on mount, displays them with author and timestamp, and provides an editable
 * textarea + Save button for the current user's note.
 *
 * Hidden entirely when the current user's role is 'user' (patient).
 *
 * @decision DEC-FRONTEND-060
 * @title ClinicianNotes reads role from prop, hides for patient role
 * @status accepted
 * @rationale The useAuth hook already provides currentUser with a role field.
 *   Accepting role as a prop avoids re-fetching auth state and makes the
 *   component easily testable by passing role directly. The isPatient flag
 *   is derived before hooks to satisfy the rules-of-hooks constraint (no
 *   hooks after conditional returns), then the entire render is gated.
 */

import { useState, useEffect, useCallback } from 'react'
import { getClinicianNotes, upsertClinicianNote } from '../api/client'
import type { ClinicianNote } from '../types'

interface ClinicianNotesProps {
  entityType: 'session_summary' | 'daily_summary' | 'cognitive_screening'
  entityId: string
  /** Current user role — hide component entirely for 'user' (patient) */
  role?: string
}

function formatTimestamp(ts: string): string {
  return new Date(ts).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function ClinicianNotes({ entityType, entityId, role }: ClinicianNotesProps) {
  const isPatient = role === 'user'

  const [notes, setNotes] = useState<ClinicianNote[]>([])
  const [loading, setLoading] = useState(!isPatient)
  const [error, setError] = useState<string | null>(null)
  const [draft, setDraft] = useState('')
  const [saving, setSaving] = useState(false)

  const fetchNotes = useCallback(async () => {
    if (isPatient) return
    try {
      setLoading(true)
      const data = await getClinicianNotes(entityType, entityId)
      setNotes(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load notes')
    } finally {
      setLoading(false)
    }
  }, [entityType, entityId, isPatient])

  useEffect(() => {
    fetchNotes()
  }, [fetchNotes])

  const handleSave = async () => {
    if (!draft.trim()) return
    setSaving(true)
    try {
      const saved = await upsertClinicianNote(entityType, entityId, draft.trim())
      setNotes((prev) => {
        const idx = prev.findIndex((n) => n.user_id === saved.user_id)
        if (idx >= 0) {
          const updated = [...prev]
          updated[idx] = saved
          return updated
        }
        return [...prev, saved]
      })
      setDraft('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save note')
    } finally {
      setSaving(false)
    }
  }

  // Hide entirely for patient role
  if (isPatient) {
    return null
  }

  if (loading) {
    return (
      <div className="patient-dash__card" aria-busy="true">
        Loading notes...
      </div>
    )
  }

  return (
    <section className="patient-dash__card" aria-label="Clinician Notes">
      <h3>Clinician Notes</h3>

      {error && (
        <p className="patient-dash__error" role="alert">
          {error}
        </p>
      )}

      {notes.length === 0 && !error && (
        <p style={{ color: '#6b7280', fontSize: '14px' }}>No notes yet.</p>
      )}

      {notes.map((note) => (
        <div
          key={note.id}
          style={{
            borderLeft: '3px solid #6366f1',
            paddingLeft: '12px',
            marginBottom: '12px',
          }}
        >
          <div style={{ fontSize: '12px', color: '#6b7280', marginBottom: '4px' }}>
            <span data-testid="note-author">{note.user_id}</span>
            {' — '}
            <span data-testid="note-timestamp">{formatTimestamp(note.updated_at)}</span>
          </div>
          <p style={{ margin: 0, lineHeight: 1.5 }}>{note.content}</p>
        </div>
      ))}

      {/* New note editor */}
      <div style={{ marginTop: '12px' }}>
        <textarea
          aria-label="Add a clinician note"
          placeholder="Add a note..."
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          style={{
            width: '100%',
            padding: '8px',
            borderRadius: '6px',
            border: '1px solid #d1d5db',
            fontSize: '14px',
            resize: 'vertical',
            boxSizing: 'border-box',
          }}
        />
        <button
          type="button"
          className="med-card__btn"
          onClick={handleSave}
          disabled={saving || !draft.trim()}
          style={{ marginTop: '8px' }}
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </section>
  )
}
