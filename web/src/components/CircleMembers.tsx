/**
 * @file CircleMembers.tsx
 * @description Care Team management card. Shows the members of a Care Circle
 *   and — for primary_caregiver and clinician roles — provides an inline form
 *   to invite new members by email. Only primary_caregivers may remove members.
 * @rationale Keeping member management inline (rather than a modal or separate
 *   page) reduces navigation friction. Role-gated UI (canManage / canRemove)
 *   mirrors the backend permission model so the UI never offers actions that
 *   the API will reject.
 *
 * @decision DEC-FRONTEND-031
 * @title CircleMembers uses local component state, not a shared hook
 * @status accepted
 * @rationale Member list is only ever displayed in this one card. Extracting
 *   a useCircleMembers hook would add indirection without enabling reuse.
 *   The fetch + mutate pattern is self-contained: fetchMembers() is called on
 *   mount and after every add/remove to keep the list current without a global
 *   cache layer.
 */

import { useCallback, useEffect, useState } from 'react'

import { addCircleMember, getCircleMembers, removeCircleMember } from '../api/client'
import type { CareCircleMember } from '../types'
import { EmptyState } from './ui/EmptyState'
import { ErrorState } from './ui/ErrorState'

interface CircleMembersProps {
  circleId: string
  currentUserRole: string
}

const ROLE_LABELS: Record<string, string> = {
  primary_caregiver: 'Primary Caregiver',
  family: 'Family',
  clinician: 'Clinician',
}

export function CircleMembers({ circleId, currentUserRole }: CircleMembersProps) {
  const [members, setMembers] = useState<CareCircleMember[]>([])
  const [showAdd, setShowAdd] = useState(false)
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<string>('family')
  const [error, setError] = useState<string | null>(null)

  const canManage = currentUserRole === 'primary_caregiver' || currentUserRole === 'clinician'
  const canRemove = currentUserRole === 'primary_caregiver'

  const fetchMembers = useCallback(async () => {
    try {
      const data = await getCircleMembers(circleId)
      setMembers(data)
    } catch {
      setError('Failed to load members')
    }
  }, [circleId])

  useEffect(() => {
    fetchMembers()
  }, [fetchMembers])

  const handleAdd = async () => {
    if (!email.trim()) return
    try {
      setError(null)
      await addCircleMember(circleId, { email: email.trim(), role })
      setEmail('')
      setShowAdd(false)
      await fetchMembers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add member')
    }
  }

  const handleRemove = async (userId: string) => {
    try {
      setError(null)
      await removeCircleMember(circleId, userId)
      await fetchMembers()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove member')
    }
  }

  return (
    <div className="circle-members">
      <div className="circle-members__header">
        <h3 className="circle-members__title">Care Team</h3>
        {canManage && (
          <button
            className="circle-members__add-btn"
            onClick={() => setShowAdd(!showAdd)}
          >
            {showAdd ? 'Cancel' : '+ Add Member'}
          </button>
        )}
      </div>

      {error && (
        <ErrorState
          title="Could not load members"
          message={error}
          onRetry={fetchMembers}
        />
      )}

      {showAdd && (
        <div className="circle-members__add-form">
          <input
            type="email"
            placeholder="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="circle-members__input"
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="circle-members__role-select"
          >
            <option value="family">Family</option>
            <option value="primary_caregiver">Primary Caregiver</option>
            <option value="clinician">Clinician</option>
          </select>
          <button className="circle-members__submit-btn" onClick={handleAdd}>
            Add
          </button>
        </div>
      )}

      {members.length === 0 && !error && (
        <EmptyState
          icon="👥"
          title="No members invited yet"
          description="Invite family members or caregivers from the care circle settings."
          tone="neutral"
        />
      )}

      <ul className="circle-members__list">
        {members.map((m) => (
          <li key={m.id} className="circle-members__item">
            <span className="circle-members__email">{m.email}</span>
            <span className={`circle-members__role circle-members__role--${m.role}`}>
              {ROLE_LABELS[m.role] ?? m.role}
            </span>
            {canRemove && m.role !== 'primary_caregiver' && (
              <button
                className="circle-members__remove-btn"
                onClick={() => handleRemove(m.user_id)}
                aria-label={`Remove ${m.email}`}
              >
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
