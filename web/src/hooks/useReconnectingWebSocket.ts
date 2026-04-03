/**
 * useReconnectingWebSocket — resilient WebSocket hook with exponential backoff
 *
 * Replaces useWebSocket for all production connections. Implements a state
 * machine (connecting → open → reconnecting → closed) with capped exponential
 * backoff, outbound message queuing during disconnected intervals, and
 * callbacks for message, binary message, status change, and connection open.
 *
 * @decision DEC-FRONTEND-014
 * @title Exponential backoff WebSocket replaces fixed-delay reconnect
 * @status accepted
 * @rationale The original useWebSocket used a fixed 2 s reconnect delay.
 *   Under network instability that means every client hammers the server at
 *   the same interval — a thundering-herd problem. Exponential backoff
 *   (1 s → 2 s → 4 s → … → 30 s cap) with per-client jitter spreads
 *   reconnect load across time. The message queue ensures no outbound frames
 *   are silently dropped while the socket is down — they drain on reconnect.
 *   A 'reconnecting' status (distinct from 'closed') lets the UI show
 *   "Reconnecting…" rather than "Disconnected" after the first drop, which
 *   is more accurate and less alarming.
 *
 * @decision DEC-FRONTEND-015
 * @title onOpen callback for auth-on-connect pattern
 * @status accepted
 * @rationale Board WebSocket must send an auth frame immediately after the
 *   socket opens. Making onOpen a first-class option (rather than forcing
 *   callers to intercept onMessage for 'connected' acks) keeps auth logic
 *   co-located with the caller that owns the token, not buried in transport.
 */

import { useEffect, useRef, useCallback } from 'react'
import type { WsInboundMessage } from '../types'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ReconnectingWsStatus =
  | 'connecting'
  | 'open'
  | 'reconnecting'
  | 'closed'

export interface UseReconnectingWebSocketOptions {
  url: string
  /** Called with each parsed JSON inbound message */
  onMessage: (msg: WsInboundMessage) => void
  /** Called with raw binary frames (ArrayBuffer) */
  onBinaryMessage?: (data: ArrayBuffer) => void
  /** Called on every status transition */
  onStatusChange?: (status: ReconnectingWsStatus) => void
  /** Called immediately after the socket opens (before status is set to 'open') */
  onOpen?: (ws: WebSocket) => void
  /** Base delay for first reconnect attempt, ms. Default: 1000 */
  baseDelay?: number
  /** Maximum delay cap, ms. Default: 30000 */
  maxDelay?: number
  /** When false the hook will not connect or reconnect. Default: true */
  enabled?: boolean
}

export interface UseReconnectingWebSocketReturn {
  /** Send a raw string — callers serialise their own payload */
  send: (data: string) => void
  /** Convenience helper: send(JSON.stringify(payload)) */
  sendJson: (payload: object) => void
  /** Manually close and disable reconnect */
  close: () => void
  /** Current connection status */
  status: ReconnectingWsStatus
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useReconnectingWebSocket({
  url,
  onMessage,
  onBinaryMessage,
  onStatusChange,
  onOpen,
  baseDelay = 1000,
  maxDelay = 30000,
  enabled = true,
}: UseReconnectingWebSocketOptions): UseReconnectingWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const statusRef = useRef<ReconnectingWsStatus>('closed')
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const attemptRef = useRef<number>(0)
  const intentionalCloseRef = useRef(false)

  // Outbound message queue — drained when socket opens
  const queueRef = useRef<string[]>([])

  // Keep latest callbacks in refs so the stable connect() closure always
  // calls the current version without needing them in the dependency array.
  const onMessageRef = useRef(onMessage)
  const onBinaryMessageRef = useRef(onBinaryMessage)
  const onStatusChangeRef = useRef(onStatusChange)
  const onOpenRef = useRef(onOpen)
  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])
  useEffect(() => { onBinaryMessageRef.current = onBinaryMessage }, [onBinaryMessage])
  useEffect(() => { onStatusChangeRef.current = onStatusChange }, [onStatusChange])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])

  // -------------------------------------------------------------------------
  // Status helper
  // -------------------------------------------------------------------------

  const setStatus = useCallback((s: ReconnectingWsStatus) => {
    if (statusRef.current === s) return
    statusRef.current = s
    onStatusChangeRef.current?.(s)
  }, [])

  // -------------------------------------------------------------------------
  // Backoff calculation
  // -------------------------------------------------------------------------

  const nextDelay = useCallback((): number => {
    // 2^attempt * baseDelay, capped at maxDelay, + up to 10% jitter
    const exp = Math.min(attemptRef.current, 10) // cap exponent to avoid Infinity
    const delay = Math.min(baseDelay * Math.pow(2, exp), maxDelay)
    const jitter = delay * 0.1 * Math.random()
    return Math.floor(delay + jitter)
  }, [baseDelay, maxDelay])

  // -------------------------------------------------------------------------
  // Core connect
  // -------------------------------------------------------------------------

  const connect = useCallback(() => {
    if (intentionalCloseRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    if (wsRef.current?.readyState === WebSocket.CONNECTING) return

    setStatus(attemptRef.current === 0 ? 'connecting' : 'reconnecting')

    const ws = new WebSocket(url)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      if (intentionalCloseRef.current) {
        ws.close()
        return
      }
      // Auth or any on-open action delegated to caller
      onOpenRef.current?.(ws)
      // Drain queued outbound frames
      while (queueRef.current.length > 0) {
        const frame = queueRef.current.shift()!
        ws.send(frame)
      }
      attemptRef.current = 0
      setStatus('open')
    }

    ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        onBinaryMessageRef.current?.(event.data)
        return
      }
      try {
        const data = JSON.parse(event.data as string) as WsInboundMessage
        onMessageRef.current(data)
      } catch {
        // Malformed frame — ignore silently
      }
    }

    ws.onerror = () => {
      // onerror always precedes onclose; let onclose drive reconnect logic
      setStatus('reconnecting')
    }

    ws.onclose = () => {
      wsRef.current = null
      if (intentionalCloseRef.current) {
        setStatus('closed')
        return
      }
      setStatus('reconnecting')
      attemptRef.current += 1
      const delay = nextDelay()
      reconnectTimerRef.current = setTimeout(connect, delay)
    }
  }, [url, setStatus, nextDelay])

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (!enabled) {
      setStatus('closed')
      return
    }
    intentionalCloseRef.current = false
    attemptRef.current = 0
    connect()

    return () => {
      intentionalCloseRef.current = true
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect, enabled, setStatus])

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  const send = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    } else {
      // Queue for drain on reconnect
      queueRef.current.push(data)
    }
  }, [])

  const sendJson = useCallback((payload: object) => {
    send(JSON.stringify(payload))
  }, [send])

  const close = useCallback(() => {
    intentionalCloseRef.current = true
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    wsRef.current?.close()
    wsRef.current = null
    queueRef.current = []
  }, [])

  return { send, sendJson, close, status: statusRef.current }
}
