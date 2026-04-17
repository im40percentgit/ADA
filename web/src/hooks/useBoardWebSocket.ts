/**
 * @file useBoardWebSocket.ts
 * @description WebSocket hook for real-time board synchronisation.
 *   Opens a connection to /ws/board/{boardId}, authenticates with a Bearer
 *   token on open, and delivers parsed board messages to the onMessage
 *   callback. Uses useReconnectingWebSocket for exponential-backoff reconnect.
 *
 * @decision DEC-BOARDS-010
 * @title Board WS hook uses useReconnectingWebSocket with onOpen auth callback
 * @status accepted
 * @rationale Migrating from manual WS management to useReconnectingWebSocket
 *   gives the board connection the same exponential-backoff resilience as the
 *   chat connection. The onOpen callback sends the auth frame immediately after
 *   each (re)connect — the token is read at connect time (not hook-mount time)
 *   so a refresh that happens between reconnects is always picked up.
 *   The 'connected' ack from the server is filtered in onMessage, consistent
 *   with the prior implementation.
 */

import { useCallback } from 'react'
import { getAccessToken } from '../api/auth'
import { useReconnectingWebSocket } from './useReconnectingWebSocket'
import type { WsBoardMessage } from '../types'
import type { WsInboundMessage } from '../types'

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
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}/ws/board/${boardId}`

  // Send auth frame immediately after each (re)connect
  const handleOpen = useCallback((ws: WebSocket) => {
    const token = getAccessToken()
    ws.send(JSON.stringify({ type: 'auth', token: token ?? '' }))
  }, [])

  // Filter the server 'connected' ack; deliver all other messages
  const handleMessage = useCallback((msg: WsInboundMessage) => {
    if ((msg as { type: string }).type !== 'connected') {
      onMessage(msg as unknown as WsBoardMessage)
    }
  }, [onMessage])

  const { sendJson, status } = useReconnectingWebSocket({
    url,
    onMessage: handleMessage,
    onOpen: handleOpen,
    enabled,
  })

  const send = useCallback((msg: Record<string, unknown>) => {
    sendJson(msg)
  }, [sendJson])

  return { send, wsStatus: status }
}
