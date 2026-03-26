/**
 * @file BoardList.tsx
 * @description Lists all boards for a care circle and exposes a create-new
 *   form. On board card click, calls onSelectBoard so the parent can mount
 *   BoardView. Board creation re-fetches the list via REST — no WS needed
 *   since board creation is an infrequent, admin-level operation.
 *
 * @decision DEC-BOARDS-014
 * @title BoardList fetches via REST; no WS subscription for board-list changes
 * @status accepted
 * @rationale Board creation/deletion is a low-frequency admin operation.
 *   A WS subscription for the board list would require a circle-level channel
 *   separate from board-level channels, adding complexity without meaningful
 *   UX benefit. REST refetch after local mutations is sufficient. If multi-tab
 *   or multi-user board creation becomes a real use case, add a circle WS
 *   channel at that point.
 */

import { useCallback, useEffect, useState } from 'react'
import { createBoard, getCircleBoards } from '../api/client'
import type { Board } from '../types'

interface BoardListProps {
  circleId: string
  onSelectBoard: (boardId: string) => void
}

export function BoardList({ circleId, onSelectBoard }: BoardListProps) {
  const [boards, setBoards] = useState<Board[]>([])
  const [showCreate, setShowCreate] = useState(false)
  const [name, setName] = useState('')
  const [boardType, setBoardType] = useState('custom')
  const [creating, setCreating] = useState(false)

  const fetchBoards = useCallback(async () => {
    try {
      setBoards(await getCircleBoards(circleId))
    } catch {
      // Non-fatal: boards section stays empty
    }
  }, [circleId])

  useEffect(() => {
    fetchBoards()
  }, [fetchBoards])

  const handleCreate = async () => {
    if (!name.trim()) return
    try {
      setCreating(true)
      await createBoard(circleId, { name: name.trim(), board_type: boardType })
      setName('')
      setShowCreate(false)
      await fetchBoards()
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="board-list">
      <div className="board-list__header">
        <h3 className="board-list__title">Shared Boards</h3>
        <button
          className="board-list__new-btn"
          onClick={() => setShowCreate(!showCreate)}
          type="button"
        >
          {showCreate ? 'Cancel' : '+ New Board'}
        </button>
      </div>

      {showCreate && (
        <div className="board-list__create-form">
          <input
            placeholder="Board name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
            className="board-list__input"
            autoFocus
          />
          <select
            value={boardType}
            onChange={(e) => setBoardType(e.target.value)}
            className="board-list__type-select"
          >
            <option value="custom">Custom</option>
            <option value="shopping">Shopping</option>
            <option value="chores">Chores</option>
          </select>
          <button
            className="board-list__create-btn"
            onClick={handleCreate}
            disabled={creating || !name.trim()}
            type="button"
          >
            {creating ? 'Creating...' : 'Create'}
          </button>
        </div>
      )}

      <div className="board-list__cards">
        {boards.map((b) => (
          <button
            key={b.id}
            className="board-list__card"
            onClick={() => onSelectBoard(b.id)}
            type="button"
          >
            <span className="board-list__card-name">{b.name}</span>
            <span className="board-list__card-type">{b.board_type}</span>
          </button>
        ))}
        {boards.length === 0 && !showCreate && (
          <p className="board-list__empty">No boards yet. Create one to get started.</p>
        )}
      </div>
    </div>
  )
}
