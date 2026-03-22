/**
 * Chat — main conversation interface with multimodal media capture.
 *
 * Composes useChat, useMediaCapture, useMediaWebSocket, and useSensorSimulator
 * into the full Ada therapy chat experience. Media modalities (mic, camera,
 * sensor simulator) are optional — the text chat works independently.
 *
 * Layout:
 *   Header row: [Ada] [status dot] [EmotionChip] [VoiceIndicator] [MediaControls]
 *   Sub-header: [VitalsStrip]
 *   Body: scrolling message list
 *   Footer: status bar + input area
 *   Floating: FacePreview (bottom-right)
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
 *
 * @decision DEC-FRONTEND-018
 * @title Chat wires media capture callbacks directly to media WebSocket sends
 * @status accepted
 * @rationale The onAudioChunk and onVideoFrame callbacks from useMediaCapture
 *   are passed directly to useMediaWebSocket.sendAudioChunk/sendVideoFrame.
 *   There is no intermediate state layer for raw media bytes — storing blobs
 *   in React state would be expensive and unnecessary since they are fire-and-
 *   forget uploads. The WebSocket send is the terminal action.
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import { useAudioPlayback } from '../hooks/useAudioPlayback'
import type { WsAudioResponse } from '../types'
import { useChat } from '../hooks/useChat'
import { useMediaCapture } from '../hooks/useMediaCapture'
import { useMediaWebSocket } from '../hooks/useMediaWebSocket'
import { useSensorSimulator } from '../hooks/useSensorSimulator'
import { endSession } from '../api/client'
import { ChatMessage } from './ChatMessage'
import { CrisisAlert } from './CrisisAlert'
import { AssessmentForm } from './AssessmentForm'
import { EmotionChip } from './EmotionChip'
import { VitalsStrip } from './VitalsStrip'
import { VoiceIndicator } from './VoiceIndicator'
import { FacePreview } from './FacePreview'
import { MediaControls } from './MediaControls'
import type { Assessment } from '../types'
import type { SimulatorPreset } from '../hooks/useSensorSimulator'

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
  const { queueAudio, interrupt, isSpeaking } = useAudioPlayback()
  const [voiceEnabled, setVoiceEnabled] = useState(false)

  const handleAudioData = useCallback(
    (data: ArrayBuffer, meta: WsAudioResponse) => {
      queueAudio(data, meta.sample_rate)
    },
    [queueAudio],
  )

  const {
    messages,
    crisisAlert,
    assessmentPrompt,
    wsStatus,
    sendMessage,
    clearAssessmentPrompt,
    currentEmotion,
    currentVitals,
    sendVoiceMode,
    pendingTranscription,
  } = useChat(sessionId, patientId, { onAudioData: handleAudioData })

  // Media WebSocket — handles binary audio/video uploads
  const { sendAudioChunk, sendVideoFrame, sendEndOfUtterance } = useMediaWebSocket({ sessionId })

  // Media capture — mic + camera with callbacks into the media WS
  const {
    audioEnabled,
    videoEnabled,
    toggleAudio,
    toggleVideo,
    audioStream,
    videoRef,
    error: mediaError,
  } = useMediaCapture({
    onAudioChunk: useCallback(
      (blob: Blob) => sendAudioChunk(blob, patientId),
      [sendAudioChunk, patientId],
    ),
    onVideoFrame: useCallback(
      (blob: Blob) => sendVideoFrame(blob, patientId),
      [sendVideoFrame, patientId],
    ),
    onEndOfUtterance: useCallback(
      () => sendEndOfUtterance(),
      [sendEndOfUtterance],
    ),
  })

  // Sensor simulator
  const {
    running: simulatorRunning,
    start: startSimulator,
    stop: stopSimulator,
    error: simulatorError,
  } = useSensorSimulator(sessionId)

  const handleStartSimulator = useCallback(
    (preset: SimulatorPreset) => {
      startSimulator(preset, patientId)
    },
    [startSimulator, patientId],
  )

  const handleToggleVoice = useCallback(() => {
    const newState = !voiceEnabled
    setVoiceEnabled(newState)
    sendVoiceMode(newState)
    if (!newState) interrupt()
  }, [voiceEnabled, sendVoiceMode, interrupt])

  const [inputValue, setInputValue] = useState('')
  const [sessionEnded, setSessionEnded] = useState(false)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const prevMessageCountRef = useRef(0)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const handleEndSession = useCallback(async () => {
    try {
      await endSession(sessionId)
      setSessionEnded(true)
    } catch {
      // Silently fail — session may already be ended
    }
  }, [sessionId])

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

  // Append voice transcription to the input field (dictation mode)
  useEffect(() => {
    if (pendingTranscription) {
      setInputValue((prev) => {
        const separator = prev.trim() ? ' ' : ''
        return prev + separator + pendingTranscription
      })
      inputRef.current?.focus()
    }
  }, [pendingTranscription])

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

      {/* Chat header — emotion chip, voice indicator, media controls */}
      <div className="chat__header">
        <span className="chat__header-title">Ada</span>
        {!sessionEnded && (
          <button
            className="chat__end-btn"
            onClick={handleEndSession}
            type="button"
            title="End this session"
          >
            End Session
          </button>
        )}
        {sessionEnded && <span className="chat__ended-badge">Session Ended</span>}
        <div className="chat__header-media">
          <EmotionChip emotion={currentEmotion} />
          <VoiceIndicator stream={audioStream} />
          <MediaControls
            audioEnabled={audioEnabled}
            videoEnabled={videoEnabled}
            simulatorRunning={simulatorRunning}
            onToggleAudio={() => {
              // Interrupt TTS when user starts recording
              if (!audioEnabled) interrupt()
              toggleAudio()
            }}
            onToggleVideo={toggleVideo}
            onStartSimulator={handleStartSimulator}
            onStopSimulator={stopSimulator}
            mediaError={mediaError}
            simulatorError={simulatorError}
            voiceEnabled={voiceEnabled}
            isSpeaking={isSpeaking}
            onToggleVoice={handleToggleVoice}
          />
        </div>
      </div>

      {/* Vitals strip — hidden until first sensor reading */}
      <VitalsStrip vitals={currentVitals} />

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

      {/* Floating camera preview */}
      <FacePreview videoRef={videoRef} videoEnabled={videoEnabled} />
    </div>
  )
}
