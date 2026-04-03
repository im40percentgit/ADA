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
})
