/**
 * PrescribingNotes.test.tsx — component tests for the prescribing notes timeline.
 *
 * Tests:
 *   - Renders notes timeline with correct type badges
 *   - Add note form submits correctly
 *   - Type badges render with correct variants
 *   - Shows empty state
 *   - Shows error state on API failure
 *
 * Data is served by MSW handlers using makePrescribingNote/makeMedication factories.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { PrescribingNotes } from '../../src/components/PrescribingNotes'
import { makePrescribingNote, makeMedication } from '../factories'

function renderNotes(props: Partial<Parameters<typeof PrescribingNotes>[0]> = {}) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  const defaultProps = {
    patientId: 'patient-1',
    onBack: () => {},
    ...props,
  }
  return render(<PrescribingNotes {...defaultProps} />)
}

describe('PrescribingNotes', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders notes timeline', async () => {
    server.use(
      http.get('/api/patients/:patientId/prescribing-notes', () => {
        return HttpResponse.json([
          makePrescribingNote({
            note_type: 'prescribe',
            content: 'Started sertraline 50mg',
            medication_id: 'med-1',
          }),
          makePrescribingNote({
            note_type: 'adjust',
            content: 'Increased dosage to 100mg',
            medication_id: 'med-1',
          }),
        ])
      }),
      http.get('/api/patients/:patientId/medications', () => {
        return HttpResponse.json([
          makeMedication({ id: 'med-1', name: 'Sertraline' }),
        ])
      }),
    )

    renderNotes()

    await waitFor(() => {
      expect(screen.getByText('Started sertraline 50mg')).toBeInTheDocument()
    })
    expect(screen.getByText('Increased dosage to 100mg')).toBeInTheDocument()
    expect(screen.getByText('Prescribing Notes')).toBeInTheDocument()
  })

  it('renders type badges with correct variants', async () => {
    server.use(
      http.get('/api/patients/:patientId/prescribing-notes', () => {
        return HttpResponse.json([
          makePrescribingNote({ note_type: 'prescribe', content: 'New prescription' }),
          makePrescribingNote({ note_type: 'adjust', content: 'Dose change' }),
          makePrescribingNote({ note_type: 'discontinue', content: 'Stopped med' }),
          makePrescribingNote({ note_type: 'review', content: 'Quarterly review' }),
        ])
      }),
    )

    renderNotes()

    await waitFor(() => {
      expect(screen.getByText('New prescription')).toBeInTheDocument()
    })

    // Check that badge text appears for each type
    expect(screen.getByText('Prescribe')).toBeInTheDocument()
    expect(screen.getByText('Adjust')).toBeInTheDocument()
    expect(screen.getByText('Discontinue')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()

    // Check badge CSS classes/variants
    expect(screen.getByText('Prescribe').closest('.ada-badge--success')).toBeInTheDocument()
    expect(screen.getByText('Adjust').closest('.ada-badge--warning')).toBeInTheDocument()
    expect(screen.getByText('Discontinue').closest('.ada-badge--danger')).toBeInTheDocument()
    expect(screen.getByText('Review').closest('.ada-badge--info')).toBeInTheDocument()
  })

  it('add note form works', async () => {
    const user = userEvent.setup()
    let savedPayload: Record<string, unknown> | null = null

    server.use(
      http.get('/api/patients/:patientId/prescribing-notes', () => {
        return HttpResponse.json([])
      }),
      http.get('/api/patients/:patientId/medications', () => {
        return HttpResponse.json([
          makeMedication({ id: 'med-1', name: 'Sertraline' }),
        ])
      }),
      http.post('/api/patients/:patientId/prescribing-notes', async ({ request }) => {
        savedPayload = await request.json() as Record<string, unknown>
        return HttpResponse.json(
          makePrescribingNote({
            note_type: savedPayload.note_type as 'prescribe',
            medication_id: savedPayload.medication_id as string,
            content: savedPayload.content as string,
          }),
          { status: 201 },
        )
      }),
    )

    renderNotes()

    await waitFor(() => {
      expect(screen.getByText('No prescribing notes yet.')).toBeInTheDocument()
    })

    // Open form
    await user.click(screen.getByText('+ Add Note'))

    // Select the Adjust type
    await user.click(screen.getByText('Adjust'))

    // Select medication from dropdown
    const medSelect = screen.getByLabelText('Medication')
    await user.selectOptions(medSelect, 'med-1')

    // Enter content
    const textarea = screen.getByLabelText('Note content')
    await user.type(textarea, 'Increased to 100mg daily')

    // Submit
    await user.click(screen.getByText('Submit Note'))

    await waitFor(() => {
      expect(savedPayload).not.toBeNull()
    })
    expect(savedPayload!.note_type).toBe('adjust')
    expect(savedPayload!.medication_id).toBe('med-1')
    expect(savedPayload!.content).toBe('Increased to 100mg daily')
  })

  it('shows empty state when no notes exist', async () => {
    server.use(
      http.get('/api/patients/:patientId/prescribing-notes', () => {
        return HttpResponse.json([])
      }),
    )

    renderNotes()

    await waitFor(() => {
      expect(screen.getByText('No prescribing notes yet.')).toBeInTheDocument()
    })
  })

  it('shows error state on API failure', async () => {
    server.use(
      http.get('/api/patients/:patientId/prescribing-notes', () => {
        return HttpResponse.json({ detail: 'Server error' }, { status: 500 })
      }),
    )

    renderNotes()

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('renders medication name from the linked medication', async () => {
    server.use(
      http.get('/api/patients/:patientId/prescribing-notes', () => {
        return HttpResponse.json([
          makePrescribingNote({ medication_id: 'med-1', content: 'Review note' }),
        ])
      }),
      http.get('/api/patients/:patientId/medications', () => {
        return HttpResponse.json([
          makeMedication({ id: 'med-1', name: 'Fluoxetine' }),
        ])
      }),
    )

    renderNotes()

    await waitFor(() => {
      expect(screen.getByTestId('note-medication')).toHaveTextContent('Fluoxetine')
    })
  })
})
