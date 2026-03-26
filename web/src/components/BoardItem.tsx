/**
 * @file BoardItem.tsx
 * @description Single row in a board list. Supports inline editing via
 *   double-click, checkbox toggling, deletion, and the Ada suggestion
 *   approval flow. All mutations are forwarded to the parent via callbacks
 *   so the component is purely presentational (no direct API calls).
 *
 * @decision DEC-BOARDS-013
 * @title BoardItem is purely presentational — no direct API calls
 * @status accepted
 * @rationale All board mutations are issued via the useBoard hook (WS send
 *   + optimistic local update). BoardItem receives pre-bound callbacks so it
 *   stays decoupled from transport concerns. This makes the component trivially
 *   testable without mocking the WS layer and enables future consumers (e.g.
 *   a mobile view) to supply alternative mutation strategies.
 */

import { useState } from 'react'
import { AdaSuggestionBadge } from './AdaSuggestionBadge'
import type { BoardItem as BoardItemType } from '../types'

interface BoardItemProps {
  item: BoardItemType
  onCheck: (checked: boolean) => void
  onEdit: (text: string) => void
  onDelete: () => void
  onApprove: () => void
}

export function BoardItem({
  item,
  onCheck,
  onEdit,
  onDelete,
  onApprove,
}: BoardItemProps) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(item.text)

  const handleSubmitEdit = () => {
    if (editText.trim() && editText !== item.text) onEdit(editText.trim())
    setEditing(false)
  }

  const isSuggested = item.suggested_by_ada && !item.approved

  return (
    <li
      className={[
        'board-item',
        isSuggested ? 'board-item--suggested' : '',
        item.checked ? 'board-item--checked' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <input
        type="checkbox"
        className="board-item__checkbox"
        checked={item.checked}
        onChange={(e) => onCheck(e.target.checked)}
        aria-label={`Mark "${item.text}" as ${item.checked ? 'incomplete' : 'complete'}`}
      />

      {editing ? (
        <input
          className="board-item__edit-input"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          onBlur={handleSubmitEdit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') handleSubmitEdit()
            if (e.key === 'Escape') setEditing(false)
          }}
          autoFocus
        />
      ) : (
        <span
          className="board-item__text"
          onDoubleClick={() => { setEditText(item.text); setEditing(true) }}
        >
          {item.text}
        </span>
      )}

      {item.assigned_to && (
        <span className="board-item__assignee">{item.assigned_to}</span>
      )}
      {item.due_date && (
        <span className="board-item__due">{item.due_date}</span>
      )}

      {isSuggested && (
        <AdaSuggestionBadge onApprove={onApprove} onDismiss={onDelete} />
      )}

      <button
        className="board-item__delete"
        onClick={onDelete}
        type="button"
        aria-label="Delete item"
      >
        &times;
      </button>
    </li>
  )
}
