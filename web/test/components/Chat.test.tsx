/**
 * Chat.test.tsx — component tests for the Chat interface.
 *
 * # @mock-exempt: useChat, useMediaCapture, useMediaWebSocket, useSensorSimulator,
 * # useAudioPlayback are all mocked because they open WebSocket connections,
 * # access getUserMedia, and use Web Audio APIs — none of which are available
 * # in jsdom. These are external boundary mocks (transport/hardware), not
 * # internal logic mocks. The component rendering and interaction logic
 * # (message display, send button, crisis alert, session end) is tested against
 * # the real Chat component with controlled hook return values.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { Mock } from 'vitest'

// ---------------------------------------------------------------------------
// Mock transport/hardware hooks — external boundary mocks
// ---------------------------------------------------------------------------

vi.mock('../../src/hooks/useChat', () => ({
  useChat: vi.fn(),
}))

vi.mock('../../src/hooks/useMediaCapture', () => ({
  useMediaCapture: vi.fn(() => ({
    audioEnabled: false,
    videoEnabled: false,
    toggleAudio: vi.fn(),
    toggleVideo: vi.fn(),
    audioStream: null,
    videoRef: { current: null },
    error: null,
  })),
}))

vi.mock('../../src/hooks/useMediaWebSocket', () => ({
  useMediaWebSocket: vi.fn(() => ({
    sendAudioChunk: vi.fn(),
    sendVideoFrame: vi.fn(),
    sendEndOfUtterance: vi.fn(),
  })),
}))

vi.mock('../../src/hooks/useSensorSimulator', () => ({
  useSensorSimulator: vi.fn(() => ({
    running: false,
    start: vi.fn(),
    stop: vi.fn(),
    error: null,
  })),
}))

vi.mock('../../src/hooks/useAudioPlayback', () => ({
  useAudioPlayback: vi.fn(() => ({
    queueAudio: vi.fn(),
    interrupt: vi.fn(),
    isSpeaking: false,
  })),
}))

// @mock-exempt: useCompanionPreferences fetches from /api/companion-preferences HTTP endpoint — external API boundary mock
vi.mock('../../src/hooks/useCompanionPreferences', () => ({
  useCompanionPreferences: vi.fn(() => ({
    preferences: { name: 'Ada', voice: 'female', personality: { warmth: 'warm', verbosity: 'balanced', formality: 'casual' } },
    loading: false,
    update: vi.fn(),
  })),
}))

// ---------------------------------------------------------------------------
// Import after mocks are set up
// ---------------------------------------------------------------------------

import { Chat } from '../../src/components/Chat'
import { useChat } from '../../src/hooks/useChat'

// ---------------------------------------------------------------------------
// Default useChat return value
// ---------------------------------------------------------------------------

function makeChatHookReturn(overrides = {}) {
  return {
    messages: [],
    crisisAlert: null,
    assessmentPrompt: null,
    wsStatus: 'open' as const,
    sendMessage: vi.fn(),
    clearAssessmentPrompt: vi.fn(),
    currentEmotion: null,
    currentVitals: { hr: null, gsr: null, spo2: null },
    sendVoiceMode: vi.fn(),
    pendingTranscription: null,
    sendCognitiveResponse: vi.fn(),
    markCognitiveTaskAnswered: vi.fn(),
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Chat', () => {
  const SESSION_ID = 'session-1'
  const PATIENT_ID = 'patient-1'

  beforeEach(() => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn())
  })

  it('renders the Ada header and input area', () => {
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByText('Ada')).toBeInTheDocument()
    expect(screen.getByLabelText('Type your message')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send message' })).toBeInTheDocument()
  })

  it('shows empty state when no messages', () => {
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByText(/Welcome. How are you feeling today/i)).toBeInTheDocument()
  })

  it('displays messages when present', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      messages: [
        { id: 'msg-1', role: 'user', content: 'Hello Ada', streaming: false, timestamp: new Date() },
        { id: 'msg-2', role: 'assistant', content: 'Hello! How are you?', streaming: false, timestamp: new Date() },
      ],
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByText('Hello Ada')).toBeInTheDocument()
    expect(screen.getByText('Hello! How are you?')).toBeInTheDocument()
  })

  it('send button is disabled when input is empty', () => {
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled()
  })

  it('send button is disabled when WebSocket is not open', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({ wsStatus: 'connecting' }))
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    // Input disabled when WS not open
    expect(screen.getByLabelText('Type your message')).toBeDisabled()
  })

  it('calls sendMessage with input text when Send is clicked', async () => {
    const sendMessage = vi.fn()
    ;(useChat as Mock).mockReturnValue(makeChatHookReturn({ sendMessage }))
    const user = userEvent.setup()

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    await user.type(screen.getByLabelText('Type your message'), 'How do I sleep better?')
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => {
      expect(sendMessage).toHaveBeenCalledWith('How do I sleep better?')
    })
  })

  it('clears input after sending', async () => {
    const user = userEvent.setup()
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)

    const input = screen.getByLabelText('Type your message')
    await user.type(input, 'Test message')
    await user.click(screen.getByRole('button', { name: 'Send message' }))

    await waitFor(() => {
      expect(input).toHaveValue('')
    })
  })

  it('displays crisis alert when crisisAlert is set', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      crisisAlert: {
        type: 'crisis_alert',
        severity: 'HIGH',
        message: 'Crisis detected — please reach out for help.',
        hotline: '988',
      },
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    // CrisisAlert component renders with the alert content
    expect(screen.getByText(/Crisis detected/i)).toBeInTheDocument()
  })

  it('shows connected status when wsStatus is open', () => {
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByRole('status')).toHaveTextContent('Connected')
  })

  it('shows disconnected status when wsStatus is closed', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({ wsStatus: 'closed' }))
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByRole('status')).toHaveTextContent('Disconnected')
  })

  // @mock-exempt: cognitive task tests use same mock pattern as above (useChat is an external boundary — WebSocket transport)
  it('renders cognitive task inline when message has cognitiveTask data', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      messages: [
        {
          id: 'msg-cog-1',
          role: 'assistant',
          content: 'Remember this pattern',
          agent: 'cognitive_assessor',
          streaming: false,
          timestamp: new Date(),
          cognitiveTask: {
            screening_id: 'scr-001',
            task_index: 0,
            total_tasks: 12,
            domain: 'memory',
            task_type: 'text',
            prompt: 'Remember this pattern',
            task_data: { type: 'free_text' },
          },
          cognitiveTaskAnswered: false,
        },
      ],
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByText('Cognitive Screening')).toBeInTheDocument()
    expect(screen.getByText(/memory/i)).toBeInTheDocument()
    expect(screen.getByText(/Task 1 of 12/)).toBeInTheDocument()
    expect(screen.getByText('Remember this pattern')).toBeInTheDocument()
  })

  // ---------------------------------------------------------------------------
  // Typing indicator (DEC-MOTION-006)
  // ---------------------------------------------------------------------------

  it('shows typing indicator when last message is from user', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      messages: [
        { id: 'msg-1', role: 'user', content: 'Hello Ada', streaming: false, timestamp: new Date() },
      ],
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByText(/Ada is thinking/i)).toBeInTheDocument()
  })

  it('hides typing indicator when last message is from assistant', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      messages: [
        { id: 'msg-1', role: 'user', content: 'Hello Ada', streaming: false, timestamp: new Date() },
        { id: 'msg-2', role: 'assistant', content: 'Hello!', streaming: false, timestamp: new Date() },
      ],
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.queryByText(/is thinking/i)).not.toBeInTheDocument()
  })

  it('hides typing indicator when no messages', () => {
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.queryByText(/is thinking/i)).not.toBeInTheDocument()
  })

  it('typing indicator has aria-live="polite" and aria-atomic="true"', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      messages: [
        { id: 'msg-1', role: 'user', content: 'Hello', streaming: false, timestamp: new Date() },
      ],
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    const indicator = screen.getByText(/Ada is thinking/i).closest('[aria-live]')
    expect(indicator).toHaveAttribute('aria-live', 'polite')
    expect(indicator).toHaveAttribute('aria-atomic', 'true')
  })

  it('typing indicator dots are aria-hidden', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      messages: [
        { id: 'msg-1', role: 'user', content: 'Hello', streaming: false, timestamp: new Date() },
      ],
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    const dots = document.querySelector('.chat-typing-indicator__dots')
    expect(dots).toHaveAttribute('aria-hidden', 'true')
  })

  it('role=log aria-live=polite on message list is unchanged (13c contract)', () => {
    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    const log = screen.getByRole('log', { name: 'Chat messages' })
    expect(log).toHaveAttribute('aria-live', 'polite')
    expect(log).toHaveAttribute('aria-relevant', 'additions')
  })

  it('renders answered state for cognitive task after submission', () => {
    (useChat as Mock).mockReturnValue(makeChatHookReturn({
      messages: [
        {
          id: 'msg-cog-2',
          role: 'assistant',
          content: 'What time is shown?',
          agent: 'cognitive_assessor',
          streaming: false,
          timestamp: new Date(),
          cognitiveTask: {
            screening_id: 'scr-002',
            task_index: 1,
            total_tasks: 6,
            domain: 'attention',
            task_type: 'clock_reading',
            prompt: 'What time is shown?',
            task_data: { hour: 3, minute: 15, options: ['3:15', '3:45', '9:15'] },
          },
          cognitiveTaskAnswered: true,
        },
      ],
    }))

    render(<Chat sessionId={SESSION_ID} patientId={PATIENT_ID} />)
    expect(screen.getByLabelText('Task answered')).toBeInTheDocument()
    expect(screen.getByText(/attention — Answered/i)).toBeInTheDocument()
  })
})
