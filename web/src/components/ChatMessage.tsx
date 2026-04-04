/**
 * ChatMessage — individual message bubble in the chat interface
 *
 * Renders user messages right-aligned and assistant messages left-aligned.
 * Streaming messages show a cursor animation while tokens arrive.
 *
 * Phase 7: voice-sourced messages (source === 'voice') display a mic icon
 * next to the timestamp so users can distinguish spoken from typed input.
 */

import type { ChatMessage as ChatMessageType } from '../types'

interface ChatMessageProps {
  message: ChatMessageType
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const isVoice = message.source === 'voice'

  const bubbleStyle: React.CSSProperties = {
    background: isUser ? 'var(--color-primary-subtle)' : 'var(--color-bg-card)',
    borderRadius: 'var(--radius-card)',
    padding: 'var(--space-sm) var(--space-md)',
    maxWidth: '80%',
  }

  return (
    <div
      className={`chat-message chat-message--${isUser ? 'user' : 'assistant'}${isVoice ? ' chat-message--voice' : ''}`}
      aria-label={`${isUser ? 'You' : message.agent ?? 'Ada'}${isVoice ? ' (voice)' : ''}: ${message.content}`}
      style={{ display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start' }}
    >
      {!isUser && (
        <div className="chat-message__agent-label" style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)', marginBottom: 'var(--space-xs)' }}>
          {message.agent ?? 'Ada'}
        </div>
      )}
      <div className="chat-message__bubble" style={bubbleStyle}>
        <span className="chat-message__text" style={{ color: 'var(--color-text-primary)', fontFamily: 'var(--font-body)', fontSize: 'var(--size-body)' }}>
          {message.content}
          {message.streaming && (
            <span className="chat-message__cursor" aria-hidden="true" />
          )}
        </span>
      </div>
      <div className="chat-message__meta" style={{ fontSize: 'var(--size-xs)', color: 'var(--color-text-muted)', marginTop: 'var(--space-xs)' }}>
        {isVoice && (
          <span
            className="chat-message__voice-icon"
            aria-label="voice message"
            title="Sent by voice"
          >
            {/* Unicode microphone — no external icon dependency */}
            &#127908;
          </span>
        )}
        <time
          className="chat-message__time"
          dateTime={message.timestamp.toISOString()}
        >
          {formatTime(message.timestamp)}
        </time>
      </div>
    </div>
  )
}
