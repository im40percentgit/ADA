/**
 * BoardView.test.tsx — component tests for the shared board detail view.
 *
 * BoardView uses useBoard which:
 *   1. Fetches GET /api/boards/:boardId via REST (intercepted by MSW)
 *   2. Opens a WebSocket to /ws/board/:boardId (intercepted by MockWebSocket)
 *
 * No hook mocking needed — real useBoard + real useWebSocket global stub.
 * The board WebSocket sends an auth message on open; MockWebSocket captures it.
 * Board mutations (add, approve) are sent as WS messages captured in sentMessages.
 */

import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { server } from '../msw/handlers'
import { http, HttpResponse } from 'msw'
import { BoardView } from '../../src/components/BoardView'
import { makeBoardItem } from '../factories'
import { MockWebSocket } from '../setup'

const BOARD_ID = 'board-test-1'

function renderBoard(onBack = vi.fn()) {
  localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
  return render(<BoardView boardId={BOARD_ID} onBack={onBack} />)
}

describe('BoardView', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
    MockWebSocket.lastInstance = null
  })

  it('shows loading state initially', () => {
    renderBoard()
    expect(screen.getByRole('status')).toBeInTheDocument()
  })

  it('renders board name after loading', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/Test Board/i)).toBeInTheDocument()
    })
  })

  it('renders back button', async () => {
    const onBack = vi.fn()
    renderBoard(onBack)
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument()
    })
  })

  it('calls onBack when back button is clicked', async () => {
    const onBack = vi.fn()
    const user = userEvent.setup()
    renderBoard(onBack)

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Back/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /Back/i }))
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders existing board item', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/Test item/i)).toBeInTheDocument()
    })
  })

  it('shows empty state when no items', async () => {
    server.use(
      http.get('/api/boards/:boardId', ({ params }) => {
        return HttpResponse.json({
          board: { id: params.boardId, care_circle_id: 'circle-1', name: 'Empty Board', board_type: 'custom', created_by: 'user-1', created_at: '2026-01-01T00:00:00Z' },
          items: [],
        })
      }),
    )
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/No items yet/i)).toBeInTheDocument()
    })
  })

  it('renders add item input and button', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Add an item/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /^Add$/i })).toBeInTheDocument()
    })
  })

  it('Add button is disabled when input is empty', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Add$/i })).toBeDisabled()
    })
  })

  it('sends add item WS message when Add is clicked', async () => {
    const user = userEvent.setup()
    renderBoard()

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Add an item/i)).toBeInTheDocument()
    })

    // Wait for MockWebSocket to fire its setTimeout open callback before interacting.
    // The send() guard in useBoardWebSocket checks readyState === OPEN, so messages
    // sent before open completes are silently dropped.
    await waitFor(() => {
      expect(MockWebSocket.lastInstance?.readyState).toBe(MockWebSocket.OPEN)
    })

    await user.type(screen.getByPlaceholderText(/Add an item/i), 'Buy milk')
    await user.click(screen.getByRole('button', { name: /^Add$/i }))

    await waitFor(() => {
      const ws = MockWebSocket.lastInstance
      expect(ws).not.toBeNull()
      const addMsg = ws!.sentMessages.find(
        (m) => (m as Record<string, unknown>).type === 'item_add',
      )
      expect(addMsg).toBeDefined()
      expect((addMsg as Record<string, unknown>).text).toBe('Buy milk')
    })
  })

  it('clears add input after submitting', async () => {
    const user = userEvent.setup()
    renderBoard()

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Add an item/i)).toBeInTheDocument()
    })

    const input = screen.getByPlaceholderText(/Add an item/i)
    await user.type(input, 'Buy milk')
    await user.click(screen.getByRole('button', { name: /^Add$/i }))

    await waitFor(() => {
      expect(input).toHaveValue('')
    })
  })

  it('renders Ada suggestion badge for suggested items', async () => {
    server.use(
      http.get('/api/boards/:boardId', ({ params }) => {
        return HttpResponse.json({
          board: { id: params.boardId, care_circle_id: 'circle-1', name: 'Test Board', board_type: 'custom', created_by: 'user-1', created_at: '2026-01-01T00:00:00Z' },
          items: [makeBoardItem({ suggested_by_ada: true, approved: false })],
        })
      }),
    )
    renderBoard()
    await waitFor(() => {
      // AdaSuggestionBadge or approve button visible for unapproved Ada suggestions
      expect(screen.getByRole('button', { name: /approve/i })).toBeInTheDocument()
    })
  })

  it('shows error state when board fetch fails', async () => {
    server.use(
      http.get('/api/boards/:boardId', () =>
        HttpResponse.json({ detail: 'Not found' }, { status: 404 }),
      ),
    )
    renderBoard()
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })
})

// ---------------------------------------------------------------------------
// DEC-MOTION-007: BoardView new-item enter animation + status pulse
// ---------------------------------------------------------------------------

describe('BoardView — DEC-MOTION-007 motion classes', () => {
  beforeEach(() => {
    localStorage.setItem('ADA_ACCESS_TOKEN', 'test-access-token')
    MockWebSocket.lastInstance = null
  })

  it('items present on initial load do NOT receive board-item--new class', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/Test item/i)).toBeInTheDocument()
    })
    // The item from the MSW handler was present on first render — no enter class
    const li = screen.getByText(/Test item/i).closest('li')
    expect(li).not.toHaveClass('board-item--new')
  })

  it('WS-injected item receives board-item--new class', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/Test item/i)).toBeInTheDocument()
    })
    // Wait for WS to open so message dispatch works
    await waitFor(() => {
      expect(MockWebSocket.lastInstance?.readyState).toBe(MockWebSocket.OPEN)
    })

    const ws = MockWebSocket.lastInstance!
    ws.simulateMessage({
      type: 'item_added',
      item: makeBoardItem({ id: 'ws-item-999', text: 'WS injected item', position: 99 }),
    })

    await waitFor(() => {
      expect(screen.getByText('WS injected item')).toBeInTheDocument()
    })
    const li = screen.getByText('WS injected item').closest('li')
    expect(li).toHaveClass('board-item--new')
  })

  it('board-item--new class is removed after the animation timeout', async () => {
    // Use real timers — inject the item, confirm class present, then wait > 640ms
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/Test item/i)).toBeInTheDocument()
    })
    await waitFor(() => {
      expect(MockWebSocket.lastInstance?.readyState).toBe(MockWebSocket.OPEN)
    })

    const ws = MockWebSocket.lastInstance!
    ws.simulateMessage({
      type: 'item_added',
      item: makeBoardItem({ id: 'ws-item-888', text: 'Fading item', position: 88 }),
    })

    await waitFor(() => {
      expect(screen.getByText('Fading item')).toBeInTheDocument()
    })
    const li = screen.getByText('Fading item').closest('li')!
    expect(li).toHaveClass('board-item--new')

    // Wait for the 640ms cleanup timer to fire (real timers)
    await waitFor(() => {
      expect(li).not.toHaveClass('board-item--new')
    }, { timeout: 1500 })
  }, 10000)

  it('checking an item applies board-item--status-pulse class', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/Test item/i)).toBeInTheDocument()
    })

    // Use fireEvent (synchronous) to avoid userEvent delay issues
    const checkbox = screen.getByRole('checkbox')
    act(() => {
      fireEvent.click(checkbox)
    })

    // Pulse class should appear on the list item after the checked state changes
    const li = screen.getByText(/Test item/i).closest('li')
    await waitFor(() => {
      expect(li).toHaveClass('board-item--status-pulse')
    }, { timeout: 3000 })
  }, 10000)

  it('board-item--status-pulse class is removed after 260ms', async () => {
    renderBoard()
    await waitFor(() => {
      expect(screen.getByText(/Test item/i)).toBeInTheDocument()
    })

    const checkbox = screen.getByRole('checkbox')
    act(() => {
      fireEvent.click(checkbox)
    })

    const li = screen.getByText(/Test item/i).closest('li')!
    await waitFor(() => {
      expect(li).toHaveClass('board-item--status-pulse')
    }, { timeout: 3000 })

    // Wait for the 260ms pulse cleanup timer (real timers)
    await waitFor(() => {
      expect(li).not.toHaveClass('board-item--status-pulse')
    }, { timeout: 2000 })
  }, 10000)
})
