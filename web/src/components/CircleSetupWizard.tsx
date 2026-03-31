/**
 * @file CircleSetupWizard.tsx
 * @description Stepped wizard for caregivers to set up their first care circle.
 *   Presented when a caregiver has no circles yet (empty state in CaregiverDashboard).
 *   Four steps: choose -> link (existing patient) | create (new patient) -> done.
 *
 * @decision DEC-FRONTEND-032
 * @title CircleSetupWizard replaces static empty state for new caregivers
 * @status accepted
 * @rationale The original empty state told users to wait for an invite but gave
 *   no action path. The wizard lets a primary caregiver immediately bootstrap
 *   their first circle with or without an existing Ada account for the patient,
 *   matching the two main onboarding scenarios (link existing vs create new).
 */

import { useState, type FormEvent } from 'react'
import { lookupUserByEmail, createCircleWithPatient } from '../api/client'

type Step = 'choose' | 'link' | 'create' | 'done'

interface CircleSetupWizardProps {
  onComplete: () => void
}

export function CircleSetupWizard({ onComplete }: CircleSetupWizardProps) {
  const [step, setStep] = useState<Step>('choose')

  // Link step state
  const [linkEmail, setLinkEmail] = useState('')

  // Create step state
  const [newName, setNewName] = useState('')
  const [newEmail, setNewEmail] = useState('')

  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function goTo(next: Step) {
    setError(null)
    setStep(next)
  }

  // Link step: verify patient exists, then create circle
  async function handleLink(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await lookupUserByEmail(linkEmail)
      await createCircleWithPatient({ patient_name: linkEmail, patient_email: linkEmail })
      setStep('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not link patient. Check the email and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  // Create step: create circle with a new (possibly offline) patient
  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await createCircleWithPatient({
        patient_name: newName,
        patient_email: newEmail || undefined,
      })
      setStep('done')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create circle. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  if (step === 'choose') {
    return (
      <div className="circle-wizard">
        <h2 className="circle-wizard__heading">Set up a care circle</h2>
        <p className="circle-wizard__sub">Who are you caring for?</p>
        <div className="circle-wizard__options">
          <button
            className="circle-wizard__option"
            type="button"
            onClick={() => goTo('link')}
          >
            <span className="circle-wizard__option-title">Link an existing patient</span>
            <span className="circle-wizard__option-desc">
              The person you care for already has an Ada account
            </span>
          </button>
          <button
            className="circle-wizard__option"
            type="button"
            onClick={() => goTo('create')}
          >
            <span className="circle-wizard__option-title">Set up for someone new</span>
            <span className="circle-wizard__option-desc">
              Create a profile for someone who does not have Ada yet
            </span>
          </button>
        </div>
      </div>
    )
  }

  if (step === 'link') {
    return (
      <div className="circle-wizard">
        <h2 className="circle-wizard__heading">Link an existing patient</h2>
        <p className="circle-wizard__sub">Enter their Ada account email address.</p>
        <form className="circle-wizard__form" onSubmit={handleLink}>
          <input
            className="circle-wizard__input"
            type="email"
            placeholder="patient@example.com"
            value={linkEmail}
            onChange={e => setLinkEmail(e.target.value)}
            required
            autoFocus
          />
          {error && <p className="circle-wizard__error">{error}</p>}
          <div className="circle-wizard__actions">
            <button
              className="circle-wizard__btn circle-wizard__btn--secondary"
              type="button"
              onClick={() => goTo('choose')}
              disabled={submitting}
            >
              Back
            </button>
            <button
              className="circle-wizard__btn"
              type="submit"
              disabled={submitting || !linkEmail}
            >
              {submitting ? 'Linking...' : 'Link patient'}
            </button>
          </div>
        </form>
      </div>
    )
  }

  if (step === 'create') {
    return (
      <div className="circle-wizard">
        <h2 className="circle-wizard__heading">Set up for someone new</h2>
        <p className="circle-wizard__sub">
          Enter their name and, optionally, an email so they can be invited later.
        </p>
        <form className="circle-wizard__form" onSubmit={handleCreate}>
          <input
            className="circle-wizard__input"
            type="text"
            placeholder="Full name (required)"
            value={newName}
            onChange={e => setNewName(e.target.value)}
            required
            autoFocus
          />
          <input
            className="circle-wizard__input"
            type="email"
            placeholder="Email address (optional)"
            value={newEmail}
            onChange={e => setNewEmail(e.target.value)}
          />
          {error && <p className="circle-wizard__error">{error}</p>}
          <div className="circle-wizard__actions">
            <button
              className="circle-wizard__btn circle-wizard__btn--secondary"
              type="button"
              onClick={() => goTo('choose')}
              disabled={submitting}
            >
              Back
            </button>
            <button
              className="circle-wizard__btn"
              type="submit"
              disabled={submitting || !newName.trim()}
            >
              {submitting ? 'Creating...' : 'Create circle'}
            </button>
          </div>
        </form>
      </div>
    )
  }

  // step === 'done'
  return (
    <div className="circle-wizard circle-wizard__done">
      <h2 className="circle-wizard__heading">Care circle created!</h2>
      <p className="circle-wizard__sub">
        Your care circle is ready. You can now view the patient dashboard and invite
        additional care team members.
      </p>
      <button className="circle-wizard__btn" type="button" onClick={onComplete}>
        Go to dashboard
      </button>
    </div>
  )
}
