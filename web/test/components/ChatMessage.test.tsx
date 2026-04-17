/**
 * ChatMessage.test.tsx — component tests for the ChatMessage bubble.
 *
 * Verifies rendering logic and the DEC-MOTION-006 entrance animation class.
 * No mocks needed — ChatMessage is a pure rendering component with no
 * external dependencies (hooks, APIs, or WebSocket transport).
 */

import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { ChatMessage } from '../../src/components/ChatMessage'
import type { ChatMessage as ChatMessageType } from '../../src/types'

function makeMessage(overrides: Partial<ChatMessageType> = {}): ChatMessageType {
  return {
    id: 'msg-test-1',
    role: 'assistant',
    content: 'Hello there',
    streaming: false,
    timestamp: new Date('2024-01-01T12:00:00Z'),
    ...overrides,
  }
}

describe('ChatMessage', () => {
  it('renders assistant message content', () => {
    render(<ChatMessage message={makeMessage()} />)
    expect(screen.getByText('Hello there')).toBeInTheDocument()
  })

  it('renders user message content', () => {
    render(<ChatMessage message={makeMessage({ role: 'user', content: 'Hi Ada!' })} />)
    expect(screen.getByText('Hi Ada!')).toBeInTheDocument()
  })

  it('renders agent label for assistant messages', () => {
    render(<ChatMessage message={makeMessage({ agent: 'wellness' })} />)
    expect(screen.getByText('wellness')).toBeInTheDocument()
  })

  it('does not render agent label for user messages', () => {
    render(<ChatMessage message={makeMessage({ role: 'user' })} />)
    // User messages have no agent label div
    expect(screen.queryByText('Ada')).not.toBeInTheDocument()
  })

  it('shows streaming cursor when streaming is true', () => {
    render(<ChatMessage message={makeMessage({ streaming: true })} />)
    // Cursor span is aria-hidden, query by class
    const cursor = document.querySelector('.chat-message__cursor')
    expect(cursor).toBeInTheDocument()
  })

  it('does not show streaming cursor when streaming is false', () => {
    render(<ChatMessage message={makeMessage({ streaming: false })} />)
    expect(document.querySelector('.chat-message__cursor')).not.toBeInTheDocument()
  })

  it('shows voice icon for voice-sourced messages', () => {
    render(<ChatMessage message={makeMessage({ source: 'voice' })} />)
    expect(screen.getByLabelText('voice message')).toBeInTheDocument()
  })

  it('does not show voice icon for text-sourced messages', () => {
    render(<ChatMessage message={makeMessage({ source: 'text' })} />)
    expect(screen.queryByLabelText('voice message')).not.toBeInTheDocument()
  })

  it('renders formatted timestamp', () => {
    const ts = new Date('2024-01-01T14:30:00')
    render(<ChatMessage message={makeMessage({ timestamp: ts })} />)
    const timeEl = document.querySelector('.chat-message__time')
    expect(timeEl).toBeInTheDocument()
    // The time element has a dateTime attribute matching the ISO string
    expect(timeEl).toHaveAttribute('dateTime', ts.toISOString())
  })

  // DEC-MOTION-006: message entrance animation
  it('has chat-message--new class for entrance animation (DEC-MOTION-006)', () => {
    render(<ChatMessage message={makeMessage()} />)
    const messageEl = document.querySelector('.chat-message')
    expect(messageEl).toHaveClass('chat-message--new')
  })

  it('assistant message has chat-message--assistant and chat-message--new classes', () => {
    render(<ChatMessage message={makeMessage({ role: 'assistant' })} />)
    const messageEl = document.querySelector('.chat-message')
    expect(messageEl).toHaveClass('chat-message--assistant')
    expect(messageEl).toHaveClass('chat-message--new')
  })

  it('user message has chat-message--user and chat-message--new classes', () => {
    render(<ChatMessage message={makeMessage({ role: 'user' })} />)
    const messageEl = document.querySelector('.chat-message')
    expect(messageEl).toHaveClass('chat-message--user')
    expect(messageEl).toHaveClass('chat-message--new')
  })
})
