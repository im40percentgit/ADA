/**
 * useChat — chat state management hook
 *
 * Owns the message list, streaming state, crisis alerts, assessment
 * prompts, emotion state, and vitals received over WebSocket.
 * Delegates transport to useReconnectingWebSocket.
 *
 * @decision DEC-FRONTEND-004
 * @title useChat accumulates streaming tokens into a mutable message buffer
 * @status accepted
 * @rationale Token messages arrive at high frequency during streaming. To
 *   avoid a setState per token (which would cause a React re-render per
 *   token), we accumulate tokens into a ref buffer and flush to state when
 *   the complete message arrives. This keeps rendering smooth while still
 *   showing live streaming via a single in-progress message entry.
 *
 * @decision DEC-FRONTEND-013
 * @title useChat stores latest emotion and vitals state (not history)
 * @status accepted
 * @rationale The EmotionChip and VitalsStrip components show current state
 *   only — they do not render history charts. Storing only the latest value
 *   avoids unbounded state growth during long sessions with frequent sensor
 *   updates. A future phase can add a rolling buffer for trend visualisation.
 *
 * @decision DEC-FRONTEND-017
 * @title useChat maps ReconnectingWsStatus to the legacy WsStatus type
 * @status accepted
 * @rationale Chat.tsx and its tests use WsStatus ('connecting'|'open'|'closed'|'error').
 *   useReconnectingWebSocket emits a superset: 'connecting'|'open'|'reconnecting'|'closed'.
 *   We collapse 'reconnecting' → 'connecting' so the Chat UI and tests remain unchanged.
 *   The richer status is available to App.tsx via the onWsStatusChange callback for the
 *   global ConnectionStatus banner.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { useReconnectingWebSocket, type ReconnectingWsStatus } from './useReconnectingWebSocket'
import type { WsStatus } from './useWebSocket'
import { wsUrl, getSessionMessages } from '../api/client'
import type {
  ChatMessage,
  WsInboundMessage,
  WsCrisisAlert,
  WsAssessmentPrompt,
  WsEmotionUpdate,
  WsVitalsUpdate,
  WsTranscription,

  WsAudioResponse,
} from '../types'

let messageCounter = 0
function nextId(): string {
  return `msg-${++messageCounter}-${Date.now()}`
}

export interface CurrentVitals {
  hr: number | null
  gsr: number | null
  spo2: number | null
}

export interface UseChatReturn {
  messages: ChatMessage[]
  crisisAlert: WsCrisisAlert | null
  assessmentPrompt: WsAssessmentPrompt | null
  /** Collapsed status for Chat UI: 'reconnecting' maps to 'connecting' */
  wsStatus: WsStatus
  /** Full reconnecting status — use this for the global ConnectionStatus banner */
  reconnectingStatus: ReconnectingWsStatus
  sendMessage: (content: string) => void
  clearAssessmentPrompt: () => void
  currentEmotion: WsEmotionUpdate | null
  currentVitals: CurrentVitals
  sendVoiceMode: (enabled: boolean) => void
  pendingTranscription: { text: string; interim: boolean } | null
}

export function useChat(
  sessionId: string,
  patientId: string,
  options?: { onAudioData?: (data: ArrayBuffer, meta: WsAudioResponse) => void },
): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [crisisAlert, setCrisisAlert] = useState<WsCrisisAlert | null>(null)
  const [assessmentPrompt, setAssessmentPrompt] = useState<WsAssessmentPrompt | null>(null)
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting')
  const [currentEmotion, setCurrentEmotion] = useState<WsEmotionUpdate | null>(null)
  const [currentVitals, setCurrentVitals] = useState<CurrentVitals>({
    hr: null,
    gsr: null,
    spo2: null,
  })

  const [pendingTranscription, setPendingTranscription] = useState<{ text: string; interim: boolean } | null>(null)

  const onAudioData = options?.onAudioData
  const pendingAudioRef = useRef<WsAudioResponse | null>(null)

  // Load persisted message history on mount
  useEffect(() => {
    let cancelled = false
    getSessionMessages(sessionId).then((history) => {
      if (cancelled || history.length === 0) return
      setMessages(history.map((m) => ({
        id: m.id,
        role: m.role as 'user' | 'assistant',
        content: m.content,
        agent: m.agent ?? undefined,
        streaming: false,
        timestamp: new Date(m.timestamp),
      })))
    }).catch(() => { /* session may be new with no messages */ })
    return () => { cancelled = true }
  }, [sessionId])

  // Streaming accumulation buffer — keyed by a transient message id
  const streamingIdRef = useRef<string | null>(null)
  const streamingBufferRef = useRef<string>('')

  const handleMessage = useCallback((msg: WsInboundMessage) => {
    switch (msg.type) {
      case 'token': {
        // Accumulate into the streaming message
        if (!streamingIdRef.current) {
          const id = nextId()
          streamingIdRef.current = id
          streamingBufferRef.current = msg.content
          setMessages((prev) => [
            ...prev,
            {
              id,
              role: 'assistant',
              content: msg.content,
              streaming: true,
              timestamp: new Date(),
            },
          ])
        } else {
          streamingBufferRef.current += msg.content
          const id = streamingIdRef.current
          setMessages((prev) =>
            prev.map((m) =>
              m.id === id ? { ...m, content: streamingBufferRef.current } : m,
            ),
          )
        }
        break
      }

      case 'message': {
        // Complete message — replace streaming entry or append fresh.
        // Carry source ('text' | 'voice') from the server frame if present.
        const finalContent = msg.content
        const agent = msg.agent
        const source = (msg as { source?: 'text' | 'voice' }).source ?? 'text'
        if (streamingIdRef.current) {
          const id = streamingIdRef.current
          setMessages((prev) =>
            prev.map((m) =>
              m.id === id
                ? { ...m, content: finalContent, agent, streaming: false, source }
                : m,
            ),
          )
          streamingIdRef.current = null
          streamingBufferRef.current = ''
        } else {
          setMessages((prev) => [
            ...prev,
            {
              id: nextId(),
              role: 'assistant',
              content: finalContent,
              agent,
              streaming: false,
              timestamp: new Date(),
              source,
            },
          ])
        }
        break
      }

      case 'crisis_alert': {
        setCrisisAlert(msg)
        break
      }

      case 'assessment_prompt': {
        setAssessmentPrompt(msg)
        break
      }

      case 'error': {
        // Surface backend errors as a system message
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: 'assistant',
            content: `[Error: ${msg.detail ?? msg.message ?? 'Unknown error'}]`,
            streaming: false,
            timestamp: new Date(),
          },
        ])
        break
      }

      case 'emotion_update': {
        setCurrentEmotion(msg as WsEmotionUpdate)
        break
      }

      case 'vitals_update': {
        const vitals = msg as WsVitalsUpdate
        setCurrentVitals((prev) => ({
          ...prev,
          [vitals.sensor_type]: vitals.value,
        }))
        break
      }

      case 'transcription': {
        // Phase 7: interim transcriptions replace input; final transcriptions append
        const t = msg as WsTranscription
        if (t.text) {
          setPendingTranscription({ text: t.text, interim: !!t.interim })
        }
        break
      }


      case 'audio_response': {
        // Buffer metadata — the next binary frame is the WAV data
        pendingAudioRef.current = msg as WsAudioResponse
        break
      }
    }
  }, [])

  const handleBinaryMessage = useCallback(
    (data: ArrayBuffer) => {
      const meta = pendingAudioRef.current
      if (meta && onAudioData) {
        onAudioData(data, meta)
        pendingAudioRef.current = null
      }
    },
    [onAudioData],
  )

  const [reconnectingStatus, setReconnectingStatus] = useState<ReconnectingWsStatus>('connecting')

  const handleStatusChange = useCallback((s: ReconnectingWsStatus) => {
    setReconnectingStatus(s)
    // Collapse 'reconnecting' → 'connecting' for the legacy WsStatus consumers
    const collapsed: WsStatus =
      s === 'open' ? 'open' : s === 'closed' ? 'closed' : 'connecting'
    setWsStatus(collapsed)
  }, [])

  const { sendJson } = useReconnectingWebSocket({
    url: wsUrl(sessionId),
    onMessage: handleMessage,
    onBinaryMessage: handleBinaryMessage,
    onStatusChange: handleStatusChange,
  })

  const sendMessage = useCallback(
    (content: string) => {
      const trimmed = content.trim()
      if (!trimmed) return
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: 'user',
          content: trimmed,
          streaming: false,
          timestamp: new Date(),
        },
      ])
      sendJson({ content: trimmed, patient_id: patientId })
    },
    [sendJson, patientId],
  )

  const sendVoiceMode = useCallback(
    (enabled: boolean) => {
      sendJson({ type: 'voice_mode', enabled })
    },
    [sendJson],
  )

  const clearAssessmentPrompt = useCallback(() => setAssessmentPrompt(null), [])

  return {
    messages,
    crisisAlert,
    assessmentPrompt,
    wsStatus,
    reconnectingStatus,
    sendMessage,
    clearAssessmentPrompt,
    currentEmotion,
    currentVitals,
    sendVoiceMode,
    pendingTranscription,
  }
}
