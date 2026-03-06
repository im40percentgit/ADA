/**
 * useWebSocket — manages a single WebSocket connection lifecycle
 *
 * Handles connect, reconnect-on-close, and message dispatch. The hook does
 * NOT parse message payloads — that is the responsibility of the caller
 * (useChat). This separation keeps the transport concern isolated from the
 * application-level message protocol.
 *
 * @decision DEC-FRONTEND-003
 * @title WebSocket hook owns connection lifecycle; useChat owns message state
 * @status accepted
 * @rationale Splitting transport (useWebSocket) from state (useChat) makes
 *   each hook independently testable and avoids the god-hook anti-pattern.
 *   The reconnect strategy is intentionally simple (single retry after 2 s)
 *   for Phase 1; exponential back-off can be added in Phase 2.
 */

import { useEffect, useRef, useCallback } from 'react'
import type { WsInboundMessage } from '../types'

export type WsStatus = 'connecting' | 'open' | 'closed' | 'error'

export interface UseWebSocketOptions {
  url: string
  onMessage: (msg: WsInboundMessage) => void
  onStatusChange?: (status: WsStatus) => void
  /** Auto-reconnect after close. Default: true */
  reconnect?: boolean
  /** Delay in ms before reconnect attempt. Default: 2000 */
  reconnectDelay?: number
}

export interface UseWebSocketReturn {
  send: (payload: Record<string, string>) => void
  close: () => void
  status: WsStatus
}

export function useWebSocket({
  url,
  onMessage,
  onStatusChange,
  reconnect = true,
  reconnectDelay = 2000,
}: UseWebSocketOptions): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const statusRef = useRef<WsStatus>('closed')
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const intentionalCloseRef = useRef(false)

  const setStatus = useCallback(
    (s: WsStatus) => {
      statusRef.current = s
      onStatusChange?.(s)
    },
    [onStatusChange],
  )

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    setStatus('connecting')
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      // Send auth token as first message before marking connection open
      const token = localStorage.getItem('ADA_ACCESS_TOKEN')
      if (token) {
        ws.send(JSON.stringify({ type: 'auth', token }))
      }
      setStatus('open')
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as WsInboundMessage
        onMessage(data)
      } catch {
        // Malformed frame — ignore silently
      }
    }

    ws.onerror = () => {
      setStatus('error')
    }

    ws.onclose = () => {
      setStatus('closed')
      if (!intentionalCloseRef.current && reconnect) {
        reconnectTimerRef.current = setTimeout(connect, reconnectDelay)
      }
    }
  }, [url, onMessage, setStatus, reconnect, reconnectDelay])

  useEffect(() => {
    intentionalCloseRef.current = false
    connect()

    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((payload: Record<string, string>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload))
    }
  }, [])

  const close = useCallback(() => {
    intentionalCloseRef.current = true
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    wsRef.current?.close()
  }, [])

  return { send, close, status: statusRef.current }
}
