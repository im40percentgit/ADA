/**
 * @file useBoardWebSocket.ts
 * @description WebSocket hook for real-time board synchronisation.
 *   Opens a connection to /ws/board/{boardId}, authenticates with a Bearer
 *   token on open, and delivers parsed board messages to the onMessage
 *   callback. Reconnects automatically after 3 s on close.
 *
 * @decision DEC-BOARDS-010
 * @title Board WS hook mirrors useMediaWebSocket pattern
 * @status accepted
 * @rationale Re-using the same auth-on-open + auto-reconnect pattern keeps
 *   the codebase consistent and avoids a shared-infrastructure abstraction
 *   before the pattern is proven across enough consumers. The token is read
 *   at connection time (not hook-mount time) so a refresh that happens
 *   between mounts is always picked up.
 */

import { useCallback, useEffect, useRef } from 'react'
import { getAccessToken } from '../api/auth'
import type { WsBoardMessage } from '../types'

interface UseBoardWebSocketOptions {
  boardId: string
  onMessage: (msg: WsBoardMessage) => void
  enabled?: boolean
}

export function useBoardWebSocket({
  boardId,
  onMessage,
  enabled = true,
}: UseBoardWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>()

  const connect = useCallback(() => {
    if (!enabled || wsRef.current?.readyState === WebSocket.OPEN) return
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${location.host}/ws/board/${boardId}`)
    wsRef.current = ws

    ws.onopen = () => {
      const token = getAccessToken()
      ws.send(JSON.stringify({ type: 'auth', token: token ?? '' }))
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // The server sends a 'connected' ack on auth success — ignore it
        if (data.type !== 'connected') {
          onMessage(data as WsBoardMessage)
        }
      } catch {
        // Malformed JSON — silently ignore
      }
    }

    ws.onclose = () => {
      wsRef.current = null
      if (enabled) reconnectRef.current = setTimeout(connect, 3000)
    }

    ws.onerror = () => ws.close()
  }, [boardId, onMessage, enabled])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  return { send }
}
