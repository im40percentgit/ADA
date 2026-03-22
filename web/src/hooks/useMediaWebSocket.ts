/**
 * useMediaWebSocket — manages the /ws/media/{sessionId} connection.
 *
 * Mirrors the auth protocol of useWebSocket but uses the binary framing
 * protocol expected by the media endpoint:
 *   1. JSON header: {"type": "audio_chunk"|"video_frame", ...metadata}
 *   2. Binary ArrayBuffer: raw audio/video bytes
 *
 * sendAudioChunk and sendVideoFrame handle the two-frame protocol. The
 * caller only sees sendX(blob) — the metadata frame is built internally.
 *
 * @decision DEC-FRONTEND-010
 * @title Media WebSocket uses two-frame protocol (JSON header + binary)
 * @status accepted
 * @rationale The backend media endpoint expects a JSON metadata frame
 *   immediately followed by a binary frame for audio/video data. This
 *   matches the server's pending_binary pattern and avoids multipart
 *   encoding overhead inside a WebSocket stream. Sensor data is JSON-only
 *   (no binary), so it does not use this hook.
 */

import { useEffect, useRef, useCallback } from 'react'
import { getAccessToken } from '../api/auth'

export interface UseMediaWebSocketOptions {
  sessionId: string
  onAck?: (id: string) => void
  onError?: (detail: string) => void
}

export interface UseMediaWebSocketReturn {
  connected: boolean
  sendAudioChunk: (blob: Blob, patientId?: string) => void
  sendVideoFrame: (blob: Blob, patientId?: string) => void
  sendEndOfUtterance: () => void
  close: () => void
}

export function useMediaWebSocket({
  sessionId,
  onAck,
  onError,
}: UseMediaWebSocketOptions): UseMediaWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const connectedRef = useRef(false)
  const intentionalRef = useRef(false)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/ws/media/${sessionId}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.binaryType = 'arraybuffer'

    ws.onopen = () => {
      // Auth handshake — send token as first message
      const token = getAccessToken()
      if (token) {
        ws.send(JSON.stringify({ type: 'auth', token }))
      } else {
        // No token but auth may be disabled in dev — send empty auth
        ws.send(JSON.stringify({ type: 'auth', token: '' }))
      }
      connectedRef.current = true
    }

    ws.onmessage = (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data as string) as { type: string; id?: string; detail?: string }
        if (data.type === 'ack' && data.id) {
          onAck?.(data.id)
        } else if (data.type === 'error' && data.detail) {
          onError?.(data.detail)
        }
      } catch {
        // Ignore malformed frames
      }
    }

    ws.onerror = () => {
      connectedRef.current = false
    }

    ws.onclose = () => {
      connectedRef.current = false
      if (!intentionalRef.current) {
        reconnectTimerRef.current = setTimeout(connect, 3000)
      }
    }
  }, [sessionId, onAck, onError])

  useEffect(() => {
    intentionalRef.current = false
    connect()

    return () => {
      intentionalRef.current = true
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
      connectedRef.current = false
    }
  }, [connect])

  const sendAudioChunk = useCallback(
    async (blob: Blob, patientId = '') => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN) return

      // Frame 1: JSON metadata
      ws.send(
        JSON.stringify({
          type: 'audio_chunk',
          patient_id: patientId,
          metadata: { codec: 'webm/opus', sample_rate: 48000 },
        }),
      )

      // Frame 2: binary payload
      const buffer = await blob.arrayBuffer()
      ws.send(buffer)
    },
    [],
  )

  const sendVideoFrame = useCallback(
    async (blob: Blob, patientId = '') => {
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN) return

      // Frame 1: JSON metadata
      ws.send(
        JSON.stringify({
          type: 'video_frame',
          patient_id: patientId,
          metadata: { format: 'jpeg', resolution: '320x240' },
        }),
      )

      // Frame 2: binary payload
      const buffer = await blob.arrayBuffer()
      ws.send(buffer)
    },
    [],
  )

  const sendEndOfUtterance = useCallback(() => {
    const ws = wsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return
    ws.send(JSON.stringify({ type: 'end_of_utterance' }))
  }, [])

  const close = useCallback(() => {
    intentionalRef.current = true
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    wsRef.current?.close()
    connectedRef.current = false
  }, [])

  return {
    get connected() { return connectedRef.current },
    sendAudioChunk,
    sendVideoFrame,
    sendEndOfUtterance,
    close,
  }
}
