/**
 * MedicationCard — full CRUD medication management for the caregiver dashboard.
 *
 * Fetches all medications for a patient on mount. Allows caregivers to add new
 * medications (with interaction warning display), edit existing ones inline, and
 * discontinue (soft-delete) medications. Active and past medications are split,
 * with past medications hidden behind a collapsible toggle.
 *
 * @decision DEC-FRONTEND-025
 * @title MedicationCard fetches its own data — not from dashboard overview
 * @status accepted
 * @rationale The caregiver overview endpoint returns a read-only snapshot of
 *   medications for the summary view. MedicationCard needs live CRUD access via
 *   the dedicated medications endpoints. Fetching independently keeps the
 *   component self-contained and avoids coupling its mutation state to the
 *   overview polling cycle.
 */

import { useState, useCallback, useEffect } from 'react'
import {
  listMedications,
  createMedication,
  updateMedication,
  deactivateMedication,
} from '../api/client'
import type { Medication, MedicationCreate } from '../types'
import { SkeletonCard } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'

const FREQUENCY_OPTIONS = ['daily', 'twice daily', 'weekly', 'as needed'] as const

interface Props {
  patientId: string
}

export function MedicationCard({ patientId }: Props) {
  const [meds, setMeds] = useState<Medication[]>([])
  const [loading, setLoading] = useState(true)
  const [showPast, setShowPast] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [warning, setWarning] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Form fields shared by add and edit
  const [formName, setFormName] = useState('')
  const [formDosage, setFormDosage] = useState('')
  const [formFrequency, setFormFrequency] = useState<string>('daily')
  const [formPrescriber, setFormPrescriber] = useState('')

  const fetchMeds = useCallback(async () => {
    try {
      const data = await listMedications(patientId)
      setMeds(data)
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load medications')
    } finally {
      setLoading(false)
    }
  }, [patientId])

  useEffect(() => {
    fetchMeds()
  }, [fetchMeds])

  const resetForm = () => {
    setFormName('')
    setFormDosage('')
    setFormFrequency('daily')
    setFormPrescriber('')
    setWarning(null)
    setError(null)
  }

  const startEdit = (med: Medication) => {
    setEditingId(med.id)
    setShowAdd(false)
    setFormName(med.name)
    setFormDosage(med.dosage ?? '')
    setFormFrequency(med.frequency ?? 'daily')
    setFormPrescriber(med.prescribed_by ?? '')
    setWarning(null)
    setError(null)
  }

  const cancelForm = () => {
    setShowAdd(false)
    setEditingId(null)
    resetForm()
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formName.trim()) return
    setSaving(true)
    setError(null)
    setWarning(null)
    try {
      const body: MedicationCreate = {
        name: formName.trim(),
        dosage: formDosage.trim() || undefined,
        frequency: formFrequency || undefined,
        prescribed_by: formPrescriber.trim() || undefined,
      }
      const result = await createMedication(patientId, body)
      if (result.interaction_warning) {
        setWarning(result.interaction_warning)
      }
      await fetchMeds()
      setShowAdd(false)
      resetForm()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add medication')
    } finally {
      setSaving(false)
    }
  }

  const handleEdit = async (e: React.FormEvent, medId: string) => {
    e.preventDefault()
    if (!formName.trim()) return
    setSaving(true)
    setError(null)
    try {
      await updateMedication(patientId, medId, {
        name: formName.trim(),
        dosage: formDosage.trim() || undefined,
        frequency: formFrequency || undefined,
        prescribed_by: formPrescriber.trim() || undefined,
      })
      await fetchMeds()
      setEditingId(null)
      resetForm()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to update medication')
    } finally {
      setSaving(false)
    }
  }

  const handleDiscontinue = async (medId: string) => {
    setError(null)
    try {
      await deactivateMedication(patientId, medId)
      await fetchMeds()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to discontinue medication')
    }
  }

  const renderForm = (onSubmit: (e: React.FormEvent) => void, submitLabel: string) => (
    <form className="med-card__form" onSubmit={onSubmit}>
      <input
        className="med-card__input"
        type="text"
        placeholder="Medication name *"
        value={formName}
        onChange={e => setFormName(e.target.value)}
        required
        autoFocus
      />
      <input
        className="med-card__input"
        type="text"
        placeholder="Dosage (e.g. 10mg)"
        value={formDosage}
        onChange={e => setFormDosage(e.target.value)}
      />
      <select
        className="med-card__input"
        value={formFrequency}
        onChange={e => setFormFrequency(e.target.value)}
      >
        {FREQUENCY_OPTIONS.map(f => (
          <option key={f} value={f}>{f}</option>
        ))}
      </select>
      <input
        className="med-card__input"
        type="text"
        placeholder="Prescriber"
        value={formPrescriber}
        onChange={e => setFormPrescriber(e.target.value)}
      />
      {error && <p className="med-card__error">{error}</p>}
      <div className="med-card__form-actions">
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
          disabled={saving || !formName.trim()}
        >
          {saving ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )

  const activeMeds = meds.filter(m => m.active)
  const pastMeds = meds.filter(m => !m.active)

  return (
    <div className="med-card">
      <div className="med-card__header">
        <h2 className="cg-card__title">Medications</h2>
        {!showAdd && editingId === null && (
          <button
            type="button"
            className="med-card__btn"
            onClick={() => { setShowAdd(true); resetForm() }}
            aria-label="Add medication"
          >
            + Add
          </button>
        )}
      </div>

      {warning && <p className="med-card__warning">{warning}</p>}

      {showAdd && renderForm(handleAdd, 'Add Medication')}

      {loading ? (
        <SkeletonCard lines={2} />
      ) : activeMeds.length === 0 && !showAdd ? (
        <EmptyState icon="💊" title="No medications added yet" description="Add a medication to start tracking adherence." tone="neutral" />
      ) : (
        <ul className="med-card__list">
          {activeMeds.map(med => (
            <li key={med.id} className="med-card__item">
              {editingId === med.id ? (
                renderForm(e => handleEdit(e, med.id), 'Save Changes')
              ) : (
                <>
                  <div
                    className="med-card__item-info"
                    onClick={() => startEdit(med)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => e.key === 'Enter' && startEdit(med)}
                    aria-label={`Edit ${med.name}`}
                  >
                    <span className="med-card__name">{med.name}</span>
                    {med.dosage && <span className="med-card__dosage">{med.dosage}</span>}
                    {med.frequency && <span className="med-card__freq">{med.frequency}</span>}
                    {med.prescribed_by && (
                      <span className="med-card__prescriber">Rx: {med.prescribed_by}</span>
                    )}
                  </div>
                  <button
                    type="button"
                    className="med-card__btn med-card__btn--danger"
                    onClick={() => handleDiscontinue(med.id)}
                    aria-label={`Discontinue ${med.name}`}
                  >
                    Discontinue
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

      {pastMeds.length > 0 && (
        <div className="med-card__past">
          <button
            type="button"
            className="med-card__toggle"
            onClick={() => setShowPast(v => !v)}
          >
            {showPast ? 'Hide' : `Show`} past medications ({pastMeds.length})
          </button>
          {showPast && (
            <ul className="med-card__list">
              {pastMeds.map(med => (
                <li key={med.id} className="med-card__item med-card__item--inactive">
                  <div className="med-card__item-info" style={{ cursor: 'default' }}>
                    <span className="med-card__name">{med.name}</span>
                    {med.dosage && <span className="med-card__dosage">{med.dosage}</span>}
                    {med.frequency && <span className="med-card__freq">{med.frequency}</span>}
                  </div>
                  <span className="med-card__discontinued-badge">Discontinued</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
