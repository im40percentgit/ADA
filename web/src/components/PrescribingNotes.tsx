/**
 * PrescribingNotes — chronological timeline of prescribing activity.
 *
 * Shows prescribing notes (newest first) for a patient, with colour-coded
 * type badges and a form to add new notes. The add-note form uses type
 * picker buttons, a medication dropdown (fetched from the patient's active
 * medications), and a content textarea.
 *
 * @decision DEC-FRONTEND-071
 * @title PrescribingNotes fetches medications for the dropdown picker
 * @status accepted
 * @rationale Fetching the patient's medication list on mount lets the
 *   clinician select from existing medications when writing a prescribing
 *   note, avoiding free-text errors. The dropdown falls back to a manual
 *   entry if no medications are found.
 */

import { useState, useEffect, useCallback } from 'react'
import { Card } from './ui/Card'
import { Button } from './ui/Button'
import { Badge } from './ui/Badge'
import { listPrescribingNotes, createPrescribingNote, listMedications } from '../api/client'
import type { PrescribingNote, Medication } from '../types'

export interface PrescribingNotesProps {
  patientId: string
  onBack: () => void
}

const noteTypeVariant: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
  prescribe: 'success',
  adjust: 'warning',
  discontinue: 'danger',
  review: 'info',
}

const noteTypeLabels: Record<string, string> = {
  prescribe: 'Prescribe',
  adjust: 'Adjust',
  discontinue: 'Discontinue',
  review: 'Review',
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

function NoteCard({ note, medications }: { note: PrescribingNote; medications: Medication[] }) {
  const med = medications.find((m) => m.id === note.medication_id)
  return (
    <Card style={{ marginBottom: 'var(--space-sm)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Badge variant={noteTypeVariant[note.note_type] ?? 'neutral'}>
            {noteTypeLabels[note.note_type] ?? note.note_type}
          </Badge>
          {med && (
            <span style={{ fontWeight: 600, color: 'var(--color-text-primary)' }} data-testid="note-medication">
              {med.name}
            </span>
          )}
          {!med && note.medication_id && (
            <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--size-sm)' }}>
              (medication)
            </span>
          )}
        </div>
        <span style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)' }}>
          {formatTimestamp(note.created_at)}
        </span>
      </div>
      <p style={{ margin: '8px 0 0', lineHeight: 1.5, color: 'var(--color-text-primary)' }}>
        {note.content}
      </p>
      <div style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)', marginTop: '4px' }}>
        Clinician: {note.clinician_id}
      </div>
    </Card>
  )
}

export function PrescribingNotes({ patientId, onBack }: PrescribingNotesProps) {
  const [notes, setNotes] = useState<PrescribingNote[]>([])
  const [medications, setMedications] = useState<Medication[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Add note form state
  const [showForm, setShowForm] = useState(false)
  const [noteType, setNoteType] = useState<PrescribingNote['note_type']>('prescribe')
  const [selectedMedId, setSelectedMedId] = useState<string>('')
  const [content, setContent] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      const [notesData, medsData] = await Promise.all([
        listPrescribingNotes(patientId),
        listMedications(patientId),
      ])
      // Newest first
      setNotes(notesData.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()))
      setMedications(medsData)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load prescribing notes')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleSubmit = async () => {
    if (!content.trim()) return
    setSubmitting(true)
    try {
      const newNote = await createPrescribingNote(patientId, {
        note_type: noteType,
        medication_id: selectedMedId || null,
        content: content.trim(),
      })
      setNotes((prev) => [newNote, ...prev])
      setContent('')
      setSelectedMedId('')
      setNoteType('prescribe')
      setShowForm(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create prescribing note')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div aria-busy="true" style={{ padding: 'var(--space-md)' }}>
        Loading...
      </div>
    )
  }

  return (
    <section aria-label="Prescribing Notes" style={{ padding: 'var(--space-md)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--space-md)' }}>
        <h2 style={{ margin: 0, fontSize: 'var(--size-h2)' }}>Prescribing Notes</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="ghost" size="sm" onClick={onBack}>Back</Button>
          <Button size="sm" onClick={() => setShowForm(true)}>+ Add Note</Button>
        </div>
      </div>

      {error && (
        <p role="alert" style={{ color: 'var(--color-danger)', marginBottom: 'var(--space-sm)' }}>
          {error}
        </p>
      )}

      {showForm && (
        <Card style={{ marginBottom: 'var(--space-md)' }}>
          <h3 style={{ margin: '0 0 12px', fontSize: 'var(--size-body)' }}>New Prescribing Note</h3>

          {/* Type picker buttons */}
          <div style={{ marginBottom: '12px' }}>
            <span style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', display: 'block', marginBottom: '4px' }}>
              Note type
            </span>
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }} role="group" aria-label="Note type">
              {(['prescribe', 'adjust', 'discontinue', 'review'] as const).map((type) => (
                <Button
                  key={type}
                  size="sm"
                  variant={noteType === type ? 'primary' : 'secondary'}
                  onClick={() => setNoteType(type)}
                >
                  {noteTypeLabels[type]}
                </Button>
              ))}
            </div>
          </div>

          {/* Medication selector */}
          <div style={{ marginBottom: '12px' }}>
            <label style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginBottom: '4px' }}>
                Medication
              </span>
              <select
                value={selectedMedId}
                onChange={(e) => setSelectedMedId(e.target.value)}
                aria-label="Medication"
                style={{
                  background: 'var(--color-bg-elevated)',
                  border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-input)',
                  height: 'var(--touch-target-min)',
                  padding: '0 var(--space-sm)',
                  color: 'var(--color-text-primary)',
                  fontSize: 'var(--size-body)',
                }}
              >
                <option value="">Select medication...</option>
                {medications.map((med) => (
                  <option key={med.id} value={med.id}>
                    {med.name} {med.dosage ? `(${med.dosage})` : ''}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {/* Content textarea */}
          <div style={{ marginBottom: '12px' }}>
            <label style={{ display: 'flex', flexDirection: 'column' }}>
              <span style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', marginBottom: '4px' }}>
                Note content
              </span>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                aria-label="Note content"
                placeholder="Describe the prescribing action..."
                rows={4}
                style={{
                  width: '100%',
                  padding: '8px',
                  borderRadius: 'var(--radius-input)',
                  border: '1px solid var(--color-border)',
                  background: 'var(--color-bg-elevated)',
                  color: 'var(--color-text-primary)',
                  fontSize: 'var(--size-body)',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                  fontFamily: 'var(--font-body)',
                }}
              />
            </label>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <Button onClick={handleSubmit} disabled={submitting || !content.trim()}>
              {submitting ? 'Saving...' : 'Submit Note'}
            </Button>
            <Button variant="ghost" onClick={() => setShowForm(false)}>
              Cancel
            </Button>
          </div>
        </Card>
      )}

      {notes.length === 0 && !error && (
        <p style={{ color: 'var(--color-text-muted)' }}>No prescribing notes yet.</p>
      )}

      {notes.map((note) => (
        <NoteCard key={note.id} note={note} medications={medications} />
      ))}
    </section>
  )
}
