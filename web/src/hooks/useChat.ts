/**
 * useChat — chat state management hook
 *
 * Owns the message list, streaming state, crisis alerts, and assessment
 * prompts received over WebSocket. Delegates transport to useWebSocket.
 *
 * @decision DEC-FRONTEND-004
 * @title useChat accumulates streaming tokens into a mutable message buffer
 * @status accepted
 * @rationale Token messages arrive at high frequency during streaming. To
 *   avoid a setState per token (which would cause a React re-render per
 *   token), we accumulate tokens into a ref buffer and flush to state when
 *   the complete message arrives. This keeps rendering smooth while still
 *   showing live streaming via a single in-progress message entry.
 */

import { useState, useCallback, useRef } from 'react'
import { useWebSocket, type WsStatus } from './useWebSocket'
import { wsUrl } from '../api/client'
import type {
  ChatMessage,
  WsInboundMessage,
  WsCrisisAlert,
  WsAssessmentPrompt,
} from '../types'

let messageCounter = 0
function nextId(): string {
  return `msg-${++messageCounter}-${Date.now()}`
}

export interface UseChatReturn {
  messages: ChatMessage[]
  crisisAlert: WsCrisisAlert | null
  assessmentPrompt: WsAssessmentPrompt | null
  wsStatus: WsStatus
  sendMessage: (content: string) => void
  clearAssessmentPrompt: () => void
}

export function useChat(sessionId: string): UseChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [crisisAlert, setCrisisAlert] = useState<WsCrisisAlert | null>(null)
  const [assessmentPrompt, setAssessmentPrompt] = useState<WsAssessmentPrompt | null>(null)
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting')

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
        // Complete message — replace streaming entry or append fresh
        const finalContent = msg.content
        const agent = msg.agent
        if (streamingIdRef.current) {
          const id = streamingIdRef.current
          setMessages((prev) =>
            prev.map((m) =>
              m.id === id
                ? { ...m, content: finalContent, agent, streaming: false }
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
            content: `[Error: ${msg.message}]`,
            streaming: false,
            timestamp: new Date(),
          },
        ])
        break
      }
    }
  }, [])

  const { send } = useWebSocket({
    url: wsUrl(sessionId),
    onMessage: handleMessage,
    onStatusChange: setWsStatus,
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
      send({ content: trimmed })
    },
    [send],
  )

  const clearAssessmentPrompt = useCallback(() => setAssessmentPrompt(null), [])

  return {
    messages,
    crisisAlert,
    assessmentPrompt,
    wsStatus,
    sendMessage,
    clearAssessmentPrompt,
  }
}
