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
 *
 * @decision DEC-MOTION-007
 * @title BoardItem motion: isNew prop for enter animation; status pulse on checked change
 * @status accepted
 * @rationale Two motion affordances for board items:
 *   1. isNew prop: BoardView passes true for WS-inserted items. The class
 *      board-item--new is applied when isNew is true, triggering the CSS enter
 *      animation (opacity 0→1 + translateY 4px→0 + warmth flash). The prop is
 *      controlled by BoardView which removes it after 640ms.
 *   2. Status pulse: useEffect watches item.checked. When it changes after mount
 *      (prevChecked ref differs from current), board-item--status-pulse is applied
 *      for one animation cycle (240ms = duration-base). A ref tracks the previous
 *      checked value so the effect only fires on actual transitions, not on mount.
 *      The pulse class is removed after 260ms (20ms grace over duration-base).
 */

import { useState, useEffect, useRef } from 'react'
import { AdaSuggestionBadge } from './AdaSuggestionBadge'
import type { BoardItem as BoardItemType } from '../types'

interface BoardItemProps {
  item: BoardItemType
  isNew?: boolean
  onCheck: (checked: boolean) => void
  onEdit: (text: string) => void
  onDelete: () => void
  onApprove: () => void
}

export function BoardItem({
  item,
  isNew = false,
  onCheck,
  onEdit,
  onDelete,
  onApprove,
}: BoardItemProps) {
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState(item.text)

  // DEC-MOTION-007: status pulse on checked transition
  const [pulsing, setPulsing] = useState(false)
  const prevChecked = useRef<boolean | null>(null)

  useEffect(() => {
    // Skip on initial mount (prevChecked starts null)
    if (prevChecked.current === null) {
      prevChecked.current = item.checked
      return
    }
    if (prevChecked.current !== item.checked) {
      prevChecked.current = item.checked
      setPulsing(true)
      const timer = setTimeout(() => setPulsing(false), 260)
      return () => clearTimeout(timer)
    }
  }, [item.checked])

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
        isNew ? 'board-item--new' : '',
        pulsing ? 'board-item--status-pulse' : '',
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
