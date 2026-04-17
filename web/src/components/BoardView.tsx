/**
 * @file BoardView.tsx
 * @description Full-screen board detail view. Renders the board's item list
 *   via BoardItem components and provides an add-item input at the bottom.
 *   Real-time updates arrive via useBoard → useBoardWebSocket; this component
 *   only concerns itself with layout and user interaction.
 *
 * @decision DEC-BOARDS-015
 * @title BoardView renders full-screen; CaregiverDashboard swaps it in place of the grid
 * @status accepted
 * @rationale A single-level drill-down (list → board) avoids the complexity
 *   of a router at this phase. The parent (CaregiverDashboard) holds
 *   activeBoardId state and conditionally renders either the grid or BoardView.
 *   This keeps routing trivial and avoids adding react-router just for one
 *   nested view. If the navigation tree grows beyond two levels, migrate to
 *   a proper router at that point.
 *
 * @decision DEC-MOTION-007
 * @title Board new-item enter animation: track WS-inserted IDs via seenIds Set
 * @status accepted
 * @rationale The enter animation (.board-item--new) must only fire for items
 *   that arrive via WebSocket after initial load — not for items present on
 *   first render. We track a seenIds Set (ref) initialized on first non-loading
 *   render: all item IDs present at that point are "seen". Subsequent items
 *   whose IDs are not in seenIds are WS-inserted; they receive the board-item--new
 *   class for one animation cycle. The class is cleaned up after 600ms (covering
 *   both the 240ms entrance + 400ms warmth flash per DEC-MOTION-007 CSS spec).
 *   Using a ref (not state) for seenIds avoids re-renders; newItemIds is state
 *   so class removal triggers a re-render to strip the class.
 *
 * @decision DEC-BOARDS-STATES-001
 * @title AsyncBoundary pattern applied to BoardView: SkeletonList / EmptyState / ErrorState + inline ConnectionStatus
 * @status accepted
 * @rationale
 *   1. Loading — SkeletonList replaces the plain "Loading…" div so the loading
 *      state matches the visual weight of the item list and avoids layout shift.
 *   2. Empty — EmptyState (tone="info") replaces the bare <li> text while
 *      preserving the add-item form below it, satisfying the "add one below"
 *      affordance without losing context.
 *   3. Error — ErrorState (role="status", aria-label="Error state") replaces
 *      the plain role="alert" div; consistent with DEC-ERROR-001.
 *   4. WS disconnect — ConnectionStatus is rendered inline at the top of the
 *      board view (not at App root) because the board WS is a separate
 *      connection from the chat WS. CaregiverDashboard has no WS status
 *      callback mechanism; threading wsStatus up through CaregiverDashboard →
 *      App would require changes to three files for a contained, view-scoped
 *      concern. Inline placement is intentional and scoped.
 *   5. DEC-MOTION-007 is fully preserved: seenIds initialization is still
 *      gated on `!loading` and only runs once. SkeletonList renders while
 *      loading=true, EmptyState/items render while loading=false — the exact
 *      same condition that gates seenIds initialization. No interference.
 */

import { useState, useRef, useEffect } from 'react'
import { useBoard } from '../hooks/useBoard'
import { BoardItem } from './BoardItem'
import { SkeletonList } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'
import { ErrorState } from './ui/ErrorState'
import { ConnectionStatus } from './ConnectionStatus'

interface BoardViewProps {
  boardId: string
  onBack: () => void
}

export function BoardView({ boardId, onBack }: BoardViewProps) {
  const {
    board,
    items,
    loading,
    error,
    wsStatus,
    addItem,
    checkItem,
    editItem,
    deleteItem,
    approveItem,
  } = useBoard(boardId)
  const [newText, setNewText] = useState('')

  // DEC-MOTION-007: track IDs seen at initial load to distinguish WS-inserted items
  const seenIds = useRef<Set<string>>(new Set())
  const initializedRef = useRef(false)
  const [newItemIds, setNewItemIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (loading) return
    if (!initializedRef.current) {
      // First render after load: seed seenIds with all current item IDs
      initializedRef.current = true
      seenIds.current = new Set(items.map((i) => i.id))
      return
    }
    // On subsequent renders: find any items whose ID is not yet seen
    const fresh: string[] = []
    for (const item of items) {
      if (!seenIds.current.has(item.id)) {
        fresh.push(item.id)
        seenIds.current.add(item.id)
      }
    }
    if (fresh.length === 0) return
    setNewItemIds((prev) => {
      const next = new Set(prev)
      for (const id of fresh) next.add(id)
      return next
    })
    // Remove the enter class after animation completes (240ms enter + 400ms warmth = 640ms)
    const timer = setTimeout(() => {
      setNewItemIds((prev) => {
        const next = new Set(prev)
        for (const id of fresh) next.delete(id)
        return next
      })
    }, 640)
    return () => clearTimeout(timer)
  }, [items, loading])

  const handleAdd = () => {
    if (!newText.trim()) return
    addItem(newText.trim())
    setNewText('')
  }

  if (loading) {
    return (
      <div className="board-view board-view--loading">
        <SkeletonList count={4} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="board-view board-view--error">
        <ErrorState
          title="Could not load board"
          message={error}
        />
      </div>
    )
  }

  return (
    <div className="board-view">
      {/* DEC-BOARDS-STATES-001: inline WS disconnect banner for board-scoped WS */}
      <ConnectionStatus status={wsStatus} />

      <div className="board-view__header">
        <button className="board-view__back" onClick={onBack} type="button">
          &larr; Back
        </button>
        <h2 className="board-view__title">{board?.name}</h2>
        <span className="board-view__type">{board?.board_type}</span>
      </div>

      <ul className="board-view__items">
        {items.map((item) => (
          <BoardItem
            key={item.id}
            item={item}
            isNew={newItemIds.has(item.id)}
            onCheck={(c) => checkItem(item.id, c)}
            onEdit={(t) => editItem(item.id, t)}
            onDelete={() => deleteItem(item.id)}
            onApprove={() => approveItem(item.id)}
          />
        ))}
        {items.length === 0 && (
          <li className="board-view__empty" aria-label="empty board">
            <EmptyState
              icon="📋"
              title="No items on this board yet"
              description="Add the first item using the form below."
              tone="info"
            />
          </li>
        )}
      </ul>

      <div className="board-view__add">
        <input
          className="board-view__add-input"
          placeholder="Add an item..."
          value={newText}
          onChange={(e) => setNewText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
        />
        <button
          className="board-view__add-btn"
          onClick={handleAdd}
          disabled={!newText.trim()}
          type="button"
        >
          Add
        </button>
      </div>
    </div>
  )
}
