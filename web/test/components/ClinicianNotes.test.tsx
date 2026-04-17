/**
 * ClinicianNotes.test.tsx — component tests for the clinician annotation widget.
 *
 * Tests:
 *   - Renders existing notes (content, author, timestamp)
 *   - Save button triggers upsertClinicianNote with correct payload
 *   - Hidden entirely for patient role ('user')
 *   - Shows loading state
 *   - Shows "No notes yet" when list is empty
 *   - Error state on API failure
 *
 * Data is served by the MSW handlers for GET /api/notes and PUT /api/notes
 * which use makeClinicianNote() from factories.ts.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { ClinicianNotes } from '../../src/components/ClinicianNotes'

function renderNotes(
  props: {
    entityType?: 'session_summary' | 'daily_summary'
    entityId?: string
    role?: string
  } = {},
) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return render(
    <ClinicianNotes
      entityType={props.entityType ?? 'session_summary'}
      entityId={props.entityId ?? 'session-1'}
      role={props.role ?? 'clinician'}
    />,
  )
}

describe('ClinicianNotes', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders existing notes with content', async () => {
    renderNotes()
    await waitFor(() => {
      expect(screen.getByText(/Clinician note \d+/)).toBeInTheDocument()
    })
  })

  it('renders note author and timestamp', async () => {
    renderNotes()
    await waitFor(() => {
      expect(screen.getByTestId('note-author')).toHaveTextContent('user-')
    })
    expect(screen.getByTestId('note-timestamp')).toBeInTheDocument()
  })

  it('renders "Clinician Notes" heading', async () => {
    renderNotes()
    await waitFor(() => {
      expect(screen.getByText('Clinician Notes')).toBeInTheDocument()
    })
  })

  it('save button triggers upsert with correct content', async () => {
    const user = userEvent.setup()
    let savedPayload: { entity_type: string; entity_id: string; content: string } | null = null

    server.use(
      http.put('/api/notes', async ({ request }) => {
        savedPayload = (await request.json()) as typeof savedPayload
        return HttpResponse.json({
          id: 'note-new',
          user_id: 'user-1',
          entity_type: savedPayload!.entity_type,
          entity_id: savedPayload!.entity_id,
          content: savedPayload!.content,
          created_at: '2026-01-15T12:00:00Z',
          updated_at: '2026-01-15T12:00:00Z',
        })
      }),
    )

    renderNotes({ entityType: 'session_summary', entityId: 'session-42' })

    await waitFor(() => {
      expect(screen.getByText('Clinician Notes')).toBeInTheDocument()
    })

    const textarea = screen.getByLabelText('Add a clinician note')
    await user.type(textarea, 'New note content')
    await user.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(savedPayload).not.toBeNull()
    })
    expect(savedPayload!.entity_type).toBe('session_summary')
    expect(savedPayload!.entity_id).toBe('session-42')
    expect(savedPayload!.content).toBe('New note content')
  })

  it('clears textarea after successful save', async () => {
    const user = userEvent.setup()
    renderNotes()

    await waitFor(() => {
      expect(screen.getByText('Clinician Notes')).toBeInTheDocument()
    })

    const textarea = screen.getByLabelText('Add a clinician note') as HTMLTextAreaElement
    await user.type(textarea, 'Temp note')
    await user.click(screen.getByText('Save'))

    await waitFor(() => {
      expect(textarea.value).toBe('')
    })
  })

  it('is hidden entirely for patient role', () => {
    const { container } = renderNotes({ role: 'user' })
    expect(container.innerHTML).toBe('')
  })

  it('renders for caregiver role', async () => {
    renderNotes({ role: 'caregiver' })
    await waitFor(() => {
      expect(screen.getByText('Clinician Notes')).toBeInTheDocument()
    })
  })

  it('shows empty state when no notes exist', async () => {
    server.use(
      http.get('/api/notes', () => HttpResponse.json([])),
    )

    renderNotes()
    await waitFor(() => {
      // EmptyState title: "No notes yet" (no trailing period)
      expect(screen.getByText('No notes yet')).toBeInTheDocument()
    })
  })

  it('shows error state on API failure', async () => {
    server.use(
      http.get('/api/notes', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    )

    renderNotes()
    await waitFor(() => {
      // ClinicianNotes uses an inline role="alert" paragraph for errors (not ErrorState)
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  it('save button is disabled when textarea is empty', async () => {
    renderNotes()
    await waitFor(() => {
      expect(screen.getByText('Clinician Notes')).toBeInTheDocument()
    })
    expect(screen.getByText('Save')).toBeDisabled()
  })

  it('loading container has aria-busy="true"', () => {
    renderNotes()
    // ClinicianNotes sets aria-busy on its wrapper div while fetching
    expect(document.querySelector('[aria-busy="true"]')).toBeInTheDocument()
  })

  it('renders a skeleton block while loading', () => {
    renderNotes()
    expect(document.querySelector('.ada-skeleton--block')).toBeInTheDocument()
  })
})
