/**
 * @file useBoard.ts
 * @description React hook for board state management.
 *   Loads the board + items via REST on mount, then subscribes to real-time
 *   updates via useBoardWebSocket. Mutation operations send WS commands and
 *   apply optimistic local updates for snappy UX.
 *
 * @decision DEC-BOARDS-011
 * @title Optimistic local state + WS echo for board mutations
 * @status accepted
 * @rationale Board operations (check, edit, delete) are low-risk and fast.
 *   Applying the change locally before the server echo lands gives sub-50 ms
 *   perceived latency. The WS broadcast from the server is the source of
 *   truth and will correct any divergence (e.g. rejected auth). REST-only
 *   fallback is intentionally not implemented — if WS is unavailable the
 *   user sees a stale board, which is acceptable for a prototype.
 *
 * @decision DEC-BOARDS-012
 * @title item_added and item_suggested handled identically in state
 * @status accepted
 * @rationale Both message types carry a full BoardItem object. The
 *   distinction (human vs Ada suggestion) is conveyed by the item's
 *   suggested_by_ada flag, not the message type. Merging the two cases
 *   in the switch keeps the reducer lean.
 */

import { useCallback, useEffect, useState } from 'react'
import { getBoard, clearBoardItems } from '../api/client'
import { useBoardWebSocket } from './useBoardWebSocket'
import type { Board, BoardItem, WsBoardMessage } from '../types'
import type { ReconnectingWsStatus } from './useReconnectingWebSocket'

interface UseBoardResult {
  board: Board | null
  items: BoardItem[]
  loading: boolean
  error: string | null
  wsStatus: ReconnectingWsStatus
  addItem: (text: string) => void
  checkItem: (itemId: string, checked: boolean) => void
  editItem: (itemId: string, text: string) => void
  deleteItem: (itemId: string) => void
  reorderItem: (itemId: string, afterItemId: string | null) => void
  approveItem: (itemId: string) => void
  clearBoard: () => Promise<void>
}

export function useBoard(boardId: string): UseBoardResult {
  const [board, setBoard] = useState<Board | null>(null)
  const [items, setItems] = useState<BoardItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        setLoading(true)
        const data = await getBoard(boardId)
        if (!cancelled) {
          setBoard(data.board)
          setItems(data.items)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load board')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [boardId])

  const handleMessage = useCallback((msg: WsBoardMessage) => {
    switch (msg.type) {
      case 'item_added':
      case 'item_suggested':
        setItems(prev => [...prev, msg.item])
        break
      case 'item_checked':
        setItems(prev =>
          prev.map(i => i.id === msg.item_id ? { ...i, checked: msg.checked } : i),
        )
        break
      case 'item_edited':
        setItems(prev =>
          prev.map(i => i.id === msg.item_id ? { ...i, text: msg.text } : i),
        )
        break
      case 'item_deleted':
        setItems(prev => prev.filter(i => i.id !== msg.item_id))
        break
      case 'item_reordered':
        setItems(prev =>
          prev
            .map(i => i.id === msg.item_id ? { ...i, position: msg.position } : i)
            .sort((a, b) => a.position - b.position),
        )
        break
      case 'item_approved':
        setItems(prev =>
          prev.map(i => i.id === msg.item_id ? { ...i, approved: true } : i),
        )
        break
      case 'board_cleared':
        setItems([])
        break
    }
  }, [])

  const { send, wsStatus } = useBoardWebSocket({ boardId, onMessage: handleMessage })

  const addItem = useCallback(
    (text: string) => send({ type: 'item_add', text }),
    [send],
  )

  const checkItem = useCallback(
    (itemId: string, checked: boolean) => {
      send({ type: 'item_check', item_id: itemId, checked })
      setItems(prev => prev.map(i => i.id === itemId ? { ...i, checked } : i))
    },
    [send],
  )

  const editItem = useCallback(
    (itemId: string, text: string) => {
      send({ type: 'item_edit', item_id: itemId, text })
      setItems(prev => prev.map(i => i.id === itemId ? { ...i, text } : i))
    },
    [send],
  )

  const deleteItem = useCallback(
    (itemId: string) => {
      send({ type: 'item_delete', item_id: itemId })
      setItems(prev => prev.filter(i => i.id !== itemId))
    },
    [send],
  )

  const reorderItem = useCallback(
    (itemId: string, afterItemId: string | null) => {
      send({ type: 'item_reorder', item_id: itemId, after_item_id: afterItemId })
    },
    [send],
  )

  const approveItem = useCallback(
    (itemId: string) => {
      send({ type: 'item_approve', item_id: itemId })
      setItems(prev => prev.map(i => i.id === itemId ? { ...i, approved: true } : i))
    },
    [send],
  )

  const clearBoard = useCallback(async () => {
    // Optimistic: clear locally immediately; WS board_cleared echo will confirm
    setItems([])
    await clearBoardItems(boardId)
  }, [boardId])

  return {
    board,
    items,
    loading,
    error,
    wsStatus,
    addItem,
    checkItem,
    editItem,
    deleteItem,
    reorderItem,
    approveItem,
    clearBoard,
  }
}
