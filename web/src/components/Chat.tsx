/**
 * Chat — main conversation interface
 *
 * Composes useChat hook, ChatMessage list, CrisisAlert banner, and
 * AssessmentForm overlay. Handles auto-scroll to the latest message
 * and keyboard submission (Enter to send).
 *
 * @decision DEC-FRONTEND-009
 * @title Chat uses useEffect scroll-to-bottom on message list changes
 * @status accepted
 * @rationale scrollIntoView on the sentinel div at the bottom of the message
 *   list fires after every render where messages change. Using a ref on the
 *   sentinel (not the container) avoids reading scrollHeight/clientHeight and
 *   works correctly when the container height is set via CSS flexbox.
 *   behavior: 'smooth' is used for incremental streaming tokens so the scroll
 *   feels natural; 'auto' (instant) is used for the first message of a new
 *   exchange to jump immediately to context.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useChat } from '../hooks/useChat'
import { ChatMessage } from './ChatMessage'
import { CrisisAlert } from './CrisisAlert'
import { AssessmentForm } from './AssessmentForm'
import type { Assessment } from '../types'

interface ChatProps {
  sessionId: string
  patientId: string
}

const WS_STATUS_LABELS: Record<string, string> = {
  connecting: 'Connecting…',
  open: 'Connected',
  closed: 'Disconnected',
  error: 'Connection error',
}

export function Chat({ sessionId, patientId }: ChatProps) {
  const { messages, crisisAlert, assessmentPrompt, wsStatus, sendMessage, clearAssessmentPrompt } =
    useChat(sessionId)

  const [inputValue, setInputValue] = useState('')
  const sentinelRef = useRef<HTMLDivElement>(null)
  const prevMessageCountRef = useRef(0)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Auto-scroll: smooth for streaming updates, instant for new messages
  useEffect(() => {
    if (!sentinelRef.current) return
    const isNewMessage = messages.length > prevMessageCountRef.current
    sentinelRef.current.scrollIntoView({
      behavior: isNewMessage ? 'auto' : 'smooth',
      block: 'end',
    })
    prevMessageCountRef.current = messages.length
  }, [messages])

  const handleSend = useCallback(() => {
    const trimmed = inputValue.trim()
    if (!trimmed || wsStatus !== 'open') return
    sendMessage(trimmed)
    setInputValue('')
    inputRef.current?.focus()
  }, [inputValue, wsStatus, sendMessage])

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function handleAssessmentComplete(_result: Assessment) {
    // Assessment submitted — dismiss the overlay after a short delay
    setTimeout(clearAssessmentPrompt, 2000)
  }

  const canSend = inputValue.trim().length > 0 && wsStatus === 'open'

  return (
    <div className="chat">
      {/* Crisis alert — always rendered at top, non-dismissible */}
      {crisisAlert && <CrisisAlert alert={crisisAlert} />}

      {/* Assessment overlay */}
      {assessmentPrompt && (
        <div className="chat__assessment-overlay" role="dialog" aria-modal="true" aria-label="Assessment questionnaire">
          <div className="chat__assessment-panel">
            <AssessmentForm
              instrument={assessmentPrompt.instrument === 'who5' ? 'phq9' : assessmentPrompt.instrument}
              patientId={patientId}
              sessionId={sessionId}
              onComplete={handleAssessmentComplete}
              onDismiss={clearAssessmentPrompt}
            />
          </div>
        </div>
      )}

      {/* Message list */}
      <main
        className="chat__messages"
        aria-label="Conversation"
        aria-live="polite"
        aria-relevant="additions"
      >
        {messages.length === 0 && (
          <div className="chat__empty-state">
            <p>Welcome. How are you feeling today?</p>
          </div>
        )}
        {messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
        <div ref={sentinelRef} aria-hidden="true" />
      </main>

      {/* Status bar */}
      <div
        className={`chat__status chat__status--${wsStatus}`}
        role="status"
        aria-live="polite"
        aria-atomic="true"
      >
        <span className="chat__status-dot" aria-hidden="true" />
        {WS_STATUS_LABELS[wsStatus] ?? wsStatus}
      </div>

      {/* Input area */}
      <div className="chat__input-area">
        <label htmlFor="chat-input" className="visually-hidden">
          Type your message
        </label>
        <textarea
          id="chat-input"
          ref={inputRef}
          className="chat__input"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type a message… (Enter to send, Shift+Enter for new line)"
          rows={3}
          disabled={wsStatus !== 'open'}
          aria-disabled={wsStatus !== 'open'}
        />
        <button
          className="chat__send-btn"
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send message"
          type="button"
        >
          Send
        </button>
      </div>
    </div>
  )
}
