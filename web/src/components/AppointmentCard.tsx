/**
 * AppointmentCard — full CRUD appointment management for the caregiver dashboard.
 *
 * Fetches all appointments for a patient on mount. Allows caregivers to schedule
 * new appointments, edit existing ones inline, and cancel upcoming ones.
 * Appointments are split into upcoming (sorted ascending) and past/cancelled
 * (sorted descending, hidden behind a collapsible toggle).
 *
 * @decision DEC-FRONTEND-026
 * @title AppointmentCard fetches its own data — not from dashboard overview
 * @status accepted
 * @rationale The caregiver overview endpoint returns a read-only snapshot of
 *   appointments for summary purposes. AppointmentCard needs live CRUD access via
 *   the dedicated appointments endpoints. Fetching independently keeps the
 *   component self-contained and avoids coupling its mutation state to the
 *   overview polling cycle. Same pattern as MedicationCard (DEC-FRONTEND-025).
 */

import { useState, useCallback, useEffect } from 'react'
import { listAppointments, createAppointment, updateAppointment } from '../api/client'
import type { Appointment, AppointmentCreate } from '../types'
import { SkeletonCard } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'

interface Props {
  patientId: string
}

function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function AppointmentCard({ patientId }: Props) {
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [showPast, setShowPast] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Form fields
  const [formTitle, setFormTitle] = useState('')
  const [formDate, setFormDate] = useState('')
  const [formTime, setFormTime] = useState('')
  const [formNotes, setFormNotes] = useState('')

  const fetchAppointments = useCallback(async () => {
    try {
      const data = await listAppointments(patientId)
      setAppointments(data)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load appointments')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  useEffect(() => {
    fetchAppointments()
  }, [fetchAppointments])

  const resetForm = () => {
    setFormTitle('')
    setFormDate('')
    setFormTime('')
    setFormNotes('')
    setError(null)
  }

  const startEdit = (appt: Appointment) => {
    setEditingId(appt.id)
    setShowAdd(false)
    // Parse ISO string back to date + time parts for the inputs
    const dt = new Date(appt.scheduled_at)
    const localDate = dt.toLocaleDateString('en-CA') // YYYY-MM-DD
    const localTime = dt.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) // HH:MM
    setFormTitle(appt.title)
    setFormDate(localDate)
    setFormTime(localTime)
    setFormNotes(appt.notes ?? '')
    setError(null)
  }

  const cancelForm = () => {
    setShowAdd(false)
    setEditingId(null)
    resetForm()
  }

  const buildScheduledAt = (date: string, time: string): string => {
    // Combine date + optional time into ISO string
    if (time) {
      return new Date(`${date}T${time}`).toISOString()
    }
    return new Date(`${date}T00:00`).toISOString()
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formTitle.trim() || !formDate) return
    setSaving(true)
    setError(null)
    try {
      const body: AppointmentCreate = {
        title: formTitle.trim(),
        scheduled_at: buildScheduledAt(formDate, formTime),
        notes: formNotes.trim() || undefined,
      }
      await createAppointment(patientId, body)
      await fetchAppointments()
      setShowAdd(false)
      resetForm()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to schedule appointment')
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = async (e: React.FormEvent, apptId: string) => {
    e.preventDefault()
    if (!formTitle.trim() || !formDate) return
    setSaving(true)
    setError(null)
    try {
      await updateAppointment(patientId, apptId, {
        title: formTitle.trim(),
        scheduled_at: buildScheduledAt(formDate, formTime),
        notes: formNotes.trim() || undefined,
      })
      await fetchAppointments()
      setEditingId(null)
      resetForm()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update appointment')
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = async (apptId: string) => {
    setError(null)
    try {
      await updateAppointment(patientId, apptId, { status: 'cancelled' })
      await fetchAppointments()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to cancel appointment')
    }
  }

  const renderForm = (onSubmit: (e: React.FormEvent) => void, submitLabel: string) => (
    <form className="appt-card__form" onSubmit={onSubmit}>
      <input
        className="appt-card__input"
        type="text"
        placeholder="Title *"
        value={formTitle}
        onChange={e => setFormTitle(e.target.value)}
        required
        autoFocus
      />
      <div className="appt-card__row">
        <input
          className="appt-card__input"
          type="date"
          value={formDate}
          onChange={e => setFormDate(e.target.value)}
          required
          aria-label="Date"
        />
        <input
          className="appt-card__input"
          type="time"
          value={formTime}
          onChange={e => setFormTime(e.target.value)}
          aria-label="Time"
        />
      </div>
      <textarea
        className="appt-card__input"
        placeholder="Notes (optional)"
        value={formNotes}
        onChange={e => setFormNotes(e.target.value)}
        rows={2}
      />
      {error && <p className="med-card__error">{error}</p>}
      <div className="appt-card__form-actions">
        <button
          type="button"
          className="med-card__btn med-card__btn--secondary"
          onClick={cancelForm}
          disabled={saving}
        >
          Cancel
        </button>
        <button
          type="submit"
          className="med-card__btn"
          disabled={saving || !formTitle.trim() || !formDate}
        >
          {saving ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )

  const now = new Date()
  const upcoming = appointments
    .filter(a => a.status !== 'cancelled' && new Date(a.scheduled_at) >= now)
    .sort((a, b) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime())
  const pastAndCancelled = appointments
    .filter(a => a.status === 'cancelled' || new Date(a.scheduled_at) < now)
    .sort((a, b) => new Date(b.scheduled_at).getTime() - new Date(a.scheduled_at).getTime())

  return (
    <div className="med-card">
      <div className="med-card__header">
        <h2 className="cg-card__title">Appointments</h2>
        {!showAdd && editingId === null && (
          <button
            type="button"
            className="med-card__btn"
            onClick={() => { setShowAdd(true); resetForm() }}
            aria-label="Schedule appointment"
          >
            + Schedule
          </button>
        )}
      </div>

      {showAdd && renderForm(handleAdd, 'Schedule')}

      {loading ? (
        <SkeletonCard lines={2} />
      ) : upcoming.length === 0 && !showAdd ? (
        <EmptyState icon="📅" title="No upcoming appointments" description="Your schedule is clear." tone="neutral" />
      ) : (
        <ul className="med-card__list">
          {upcoming.map(appt => (
            <li key={appt.id} className="med-card__item">
              {editingId === appt.id ? (
                renderForm(e => handleEdit(e, appt.id), 'Save Changes')
              ) : (
                <>
                  <div
                    className="med-card__item-info"
                    onClick={() => startEdit(appt)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => e.key === 'Enter' && startEdit(appt)}
                    aria-label={`Edit ${appt.title}`}
                  >
                    <span className="med-card__name">{appt.title}</span>
                    <span className="med-card__freq">{formatDate(appt.scheduled_at)}</span>
                    {appt.provider_name && (
                      <span className="med-card__prescriber">with {appt.provider_name}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="med-card__btn med-card__btn--danger"
                    onClick={() => handleCancel(appt.id)}
                    aria-label={`Cancel ${appt.title}`}
                  >
                    Cancel
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {error && editingId === null && !showAdd && (
        <p className="med-card__error">{error}</p>
      )}

      {pastAndCancelled.length > 0 && (
        <div className="med-card__past">
          <button
            type="button"
            className="med-card__toggle"
            onClick={() => setShowPast(v => !v)}
          >
            {showPast ? 'Hide' : 'Show'} past & cancelled ({pastAndCancelled.length})
          </button>
          {showPast && (
            <ul className="med-card__list">
              {pastAndCancelled.map(appt => (
                <li key={appt.id} className="med-card__item med-card__item--inactive">
                  <div className="med-card__item-info" style={{ cursor: 'default' }}>
                    <span className="med-card__name">{appt.title}</span>
                    <span className="med-card__freq">{formatDate(appt.scheduled_at)}</span>
                  </div>
                  <span className="med-card__discontinued-badge">
                    {appt.status === 'cancelled' ? 'Cancelled' : 'Past'}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
