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
 */

import { useState } from 'react'
import { useBoard } from '../hooks/useBoard'
import { BoardItem } from './BoardItem'

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
    addItem,
    checkItem,
    editItem,
    deleteItem,
    approveItem,
  } = useBoard(boardId)
  const [newText, setNewText] = useState('')

  const handleAdd = () => {
    if (!newText.trim()) return
    addItem(newText.trim())
    setNewText('')
  }

  if (loading) {
    return <div className="board-view__loading" role="status">Loading...</div>
  }

  if (error) {
    return <div className="board-view__error" role="alert">{error}</div>
  }

  return (
    <div className="board-view">
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
            onCheck={(c) => checkItem(item.id, c)}
            onEdit={(t) => editItem(item.id, t)}
            onDelete={() => deleteItem(item.id)}
            onApprove={() => approveItem(item.id)}
          />
        ))}
        {items.length === 0 && (
          <li className="board-view__empty">No items yet — add one below.</li>
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
