/**
 * ChatMessage — individual message bubble in the chat interface
 *
 * Renders user messages right-aligned and assistant messages left-aligned.
 * Streaming messages show a cursor animation while tokens arrive.
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

  return (
    <div
      className={`chat-message chat-message--${isUser ? 'user' : 'assistant'}`}
      aria-label={`${isUser ? 'You' : message.agent ?? 'Ada'}: ${message.content}`}
    >
      {!isUser && (
        <div className="chat-message__agent-label">
          {message.agent ?? 'Ada'}
        </div>
      )}
      <div className="chat-message__bubble">
        <span className="chat-message__text">
          {message.content}
          {message.streaming && (
            <span className="chat-message__cursor" aria-hidden="true" />
          )}
        </span>
      </div>
      <div className="chat-message__meta">
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
