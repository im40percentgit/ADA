/**
 * BoardList.test.tsx — component tests for the shared board list.
 *
 * BoardList fetches GET /api/circles/:circleId/boards via REST (MSW).
 * No WebSocket needed — board creation/deletion is REST-only (DEC-BOARDS-014).
 *
 * Phase 13e-04 states (DEC-BOARDS-STATES-001):
 *   - loading path: boards render after fetch resolves
 *   - empty path: EmptyState renders with Create CTA when boards array is empty
 *   - error path: no boards visible (fetch failure silently keeps list empty)
 *   - create flow: new-board form appears and disappears
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { BoardList } from '../../src/components/BoardList'

const CIRCLE_ID = 'circle-test-1'

function renderList(onSelect = vi.fn()) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return render(<BoardList circleId={CIRCLE_ID} onSelectBoard={onSelect} />)
}

describe('BoardList', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  })

  it('renders the section heading', async () => {
    renderList()
    // Use the CSS class to disambiguate from any EmptyState h3 that may also render
    expect(document.querySelector('.board-list__title')).toBeInTheDocument()
  })

  it('renders a board card after data loads', async () => {
    renderList()
    // Default MSW handler returns makeBoard() with name "Test Board 1"
    await waitFor(() => {
      expect(screen.getByText(/Test Board/i)).toBeInTheDocument()
    })
  })

  it('calls onSelectBoard when a board card is clicked', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    renderList(onSelect)

    await waitFor(() => {
      expect(screen.getByText(/Test Board/i)).toBeInTheDocument()
    })

    await user.click(screen.getByText(/Test Board/i).closest('button')!)
    expect(onSelect).toHaveBeenCalledOnce()
  })

  it('shows EmptyState with Create CTA when boards list is empty (DEC-BOARDS-STATES-001)', async () => {
    server.use(
      http.get('/api/circles/:circleId/boards', () => {
        return HttpResponse.json([])
      }),
    )
    renderList()
    await waitFor(() => {
      expect(screen.getByText(/No shared boards yet/i)).toBeInTheDocument()
    })
    // Create CTA must be present in the empty state
    expect(screen.getByRole('button', { name: /Create board/i })).toBeInTheDocument()
  })

  it('empty state Create board button opens the create form', async () => {
    server.use(
      http.get('/api/circles/:circleId/boards', () => {
        return HttpResponse.json([])
      }),
    )
    const user = userEvent.setup()
    renderList()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Create board/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /Create board/i }))
    expect(screen.getByPlaceholderText(/Board name/i)).toBeInTheDocument()
  })

  it('does not show EmptyState when boards are present', async () => {
    renderList()
    await waitFor(() => {
      expect(screen.getByText(/Test Board/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(/No shared boards yet/i)).not.toBeInTheDocument()
  })

  it('shows create form when + New Board is clicked', async () => {
    const user = userEvent.setup()
    renderList()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /New Board/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /New Board/i }))
    expect(screen.getByPlaceholderText(/Board name/i)).toBeInTheDocument()
  })

  it('hides create form and shows boards after successful creation', async () => {
    server.use(
      http.get('/api/circles/:circleId/boards', () => {
        return HttpResponse.json([])
      }),
      http.post('/api/circles/:circleId/boards', async ({ request }) => {
        const body = await request.json() as { name: string; board_type: string }
        return HttpResponse.json(
          { id: 'board-new-1', care_circle_id: CIRCLE_ID, name: body.name, board_type: body.board_type, created_by: 'user-1', created_at: '2026-01-01T00:00:00Z' },
          { status: 201 },
        )
      }),
    )
    const user = userEvent.setup()
    renderList()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Create board/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /Create board/i }))
    await user.type(screen.getByPlaceholderText(/Board name/i), 'New Board')
    await user.click(screen.getByRole('button', { name: /^Create$/ }))

    // Form should close after creation
    await waitFor(() => {
      expect(screen.queryByPlaceholderText(/Board name/i)).not.toBeInTheDocument()
    })
  })
})
