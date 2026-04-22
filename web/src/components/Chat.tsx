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
 * @decision DEC-CHAT-STATES-001
 * @title AsyncBoundary pattern applied to Chat: Skeleton / EmptyState / ErrorState
 * @status accepted
 * @rationale Phase 13e applies the primitives shipped in #43 (DEC-LOADING-001,
 *   DEC-EMPTY-001, DEC-ERROR-001) to the Chat component's three async surface areas:
 *
 *   1. Initial load — SkeletonList is shown while useChat.isLoading is true and
 *      the message list is empty. isLoading is set false in the .finally() of the
 *      getSessionMessages fetch so it covers both the success and error paths.
 *
 *   2. Empty state — EmptyState (tone="warm") replaces the previous plain-text
 *      placeholder. The warm tone signals an encouraging first-run state. Copy is
 *      exactly: "Say hello to Ada — she's listening." (em-dash per spec).
 *
 *   3. Send failure — ErrorState is rendered inline above the input area when
 *      sendMessage is called while the WS is not open. retrySend retries the
 *      buffered content when the connection has recovered. This is separate from
 *      the WS disconnect banner (ConnectionStatus, DEC-FRONTEND-016) which is
 *      already mounted at the App root and covers the global disconnect state.
 *
 *   WS disconnect is surfaced via the existing ConnectionStatus banner (Phase 11a,
 *   DEC-FRONTEND-016) — this component does not duplicate that logic.
 *
 *   13c a11y contract preserved: role="log" + aria-live="polite" on the message
 *   list container is untouched. The typing indicator aria-live="polite" wrapper
 *   from DEC-MOTION-006 is also untouched.
 *
 * @decision DEC-MOTION-006
 * @title Chat affordance motion: typing indicator aria-live, message entrance, STT pulse tokens
 * @status accepted
 * @rationale The "Ada is thinking…" typing indicator is shown when the last message
 *   in the list has role='user' (Ada has not replied yet) — derived directly from
 *   the messages array rather than adding a separate state flag to useChat. This
 *   keeps the hook surface unchanged and avoids race conditions between a flag reset
 *   and the first streaming token arriving.
 *
 *   The indicator wrapper carries aria-live="polite" on a static DOM node so the
 *   announcement fires exactly once when the text is first inserted into the live
 *   region. The animated dots are aria-hidden so screen readers do not re-announce
 *   on every animation tick. The existing role="log" aria-live="polite" on the
 *   message list (Phase 13c) is unchanged — both live regions coexist without
 *   conflict because one announces the indicator (polite, once) and the other
 *   announces completed messages (polite, on addition).
 *
 *   Reduced-motion: DEC-MOTION-002 blanket override zeroes animation-duration to
 *   0.01ms, so dots stop animating. Text "Ada is thinking…" remains visible.
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
import { useCompanionPreferences } from '../hooks/useCompanionPreferences'
import { endSession } from '../api/client'
import { ChatMessage } from './ChatMessage'
import { CrisisAlert } from './CrisisAlert'
import { AssessmentForm } from './AssessmentForm'
import { ScreeningTask } from './ScreeningTask'
import { EmotionChip } from './EmotionChip'
import { VitalsStrip } from './VitalsStrip'
import { VoiceIndicator } from './VoiceIndicator'
import { FacePreview } from './FacePreview'
import { MediaControls } from './MediaControls'
import { Card } from './ui/Card'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import { SkeletonList } from './ui/Skeleton'
import { EmptyState } from './ui/EmptyState'
import { ErrorState } from './ui/ErrorState'
import type { Assessment } from '../types'
import type { SimulatorPreset } from '../hooks/useSensorSimulator'
import type { ReconnectingWsStatus } from '../hooks/useReconnectingWebSocket'

interface ChatProps {
  sessionId: string
  patientId: string
  /** Optional callback to lift the full reconnecting WS status to a parent */
  onWsStatusChange?: (status: ReconnectingWsStatus) => void
}

const WS_STATUS_LABELS: Record<string, string> = {
  connecting: 'Connecting…',
  open: 'Connected',
  closed: 'Disconnected',
  error: 'Connection error',
}

export function Chat({ sessionId, patientId, onWsStatusChange }: ChatProps) {
  const { queueAudio, interrupt, isSpeaking } = useAudioPlayback()
  const { preferences: companionPrefs } = useCompanionPreferences()
  const companionName = companionPrefs?.name ?? 'Ada'
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
    reconnectingStatus,
    sendMessage,
    clearAssessmentPrompt,
    currentEmotion,
    currentVitals,
    sendVoiceMode,
    pendingTranscription,
    sendCognitiveResponse,
    markCognitiveTaskAnswered,
    isLoading,
    sendError,
    retrySend,
  } = useChat(sessionId, patientId, { onAudioData: handleAudioData })

  // Bubble full reconnecting status up to App for the global ConnectionStatus banner
  useEffect(() => {
    onWsStatusChange?.(reconnectingStatus)
  }, [reconnectingStatus, onWsStatusChange])

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

  // Track finalized text from completed transcriptions (separate from interim)
  const finalTextRef = useRef('')

  // Voice transcription → input field (dictation mode)
  // Interim: replace input with finalized text + latest partial result
  // Final: append to finalized text accumulator
  useEffect(() => {
    if (!pendingTranscription) return

    if (pendingTranscription.interim) {
      // Interim: show finalized text so far + current partial
      const separator = finalTextRef.current ? ' ' : ''
      setInputValue(finalTextRef.current + separator + pendingTranscription.text)
    } else {
      // Final: append to the finalized accumulator
      const separator = finalTextRef.current ? ' ' : ''
      finalTextRef.current = finalTextRef.current + separator + pendingTranscription.text
      setInputValue(finalTextRef.current)
    }
    inputRef.current?.focus()
  }, [pendingTranscription])

  const handleSend = useCallback(() => {
    const trimmed = inputValue.trim()
    if (!trimmed || wsStatus !== 'open') return
    sendMessage(trimmed)
    setInputValue('')
    finalTextRef.current = ''
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
    <div className="chat" style={{ fontFamily: 'var(--font-body)' }}>
      {/* Crisis alert — always rendered at top, non-dismissible */}
      {crisisAlert && <CrisisAlert alert={crisisAlert} />}

      {/* Assessment overlay — ada-dialog + ada-dialog--open provides entrance/exit motion
          (DEC-MOTION-004). This overlay uses React's conditional render (mount/unmount)
          so the entrance transition fires naturally on mount. Exit is instantaneous on
          unmount — a future enhancement could wrap this in a deferred-unmount hook like
          GraphDetailPanel for a smooth exit transition, but the current mount-only approach
          is consistent with the existing clearAssessmentPrompt pattern. */}
      {assessmentPrompt && (
        <div className="chat__assessment-overlay ada-dialog ada-dialog--open" role="dialog" aria-modal="true" aria-label="Assessment questionnaire">
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

      {/* Chat header — companion name, online status, emotion chip, media controls */}
      <div className="chat__header" style={{ background: 'var(--color-bg-card)', borderBottom: '1px solid var(--color-border)', padding: 'var(--space-sm) var(--space-md)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-sm)' }}>
          <span className="chat__header-title" style={{ fontFamily: 'var(--font-heading)', fontSize: 'var(--size-h2)', fontWeight: 700, color: 'var(--color-text-primary)' }}>{companionName}</span>
          <span
            aria-label={wsStatus === 'open' ? 'Online' : 'Offline'}
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              background: wsStatus === 'open' ? 'var(--color-success)' : 'var(--color-text-muted)',
              display: 'inline-block',
              flexShrink: 0,
            }}
          />
        </div>
        {!sessionEnded && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleEndSession}
            className="chat__end-btn"
          >
            End Session
          </Button>
        )}
        {sessionEnded && <Badge variant="neutral">Session Ended</Badge>}
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
        role="log"
        aria-label="Chat messages"
        aria-live="polite"
        aria-relevant="additions"
        style={{ background: 'var(--color-bg-base)' }}
      >
        {isLoading && messages.length === 0 && (
          <div className="chat__skeleton" style={{ padding: 'var(--space-md)' }}>
            <SkeletonList count={4} />
          </div>
        )}
        {!isLoading && messages.length === 0 && (
          <EmptyState
            className="chat__empty-state"
            tone="warm"
            icon="💬"
            title="Start a conversation"
            description="Say hello to Ada — she's listening."
          />
        )}
        {messages.map((msg) =>
          msg.cognitiveTask ? (
            <div key={msg.id} className="chat-message chat-message--assistant chat-message--cognitive-task">
              <div className="chat-message__agent-label">Cognitive Screening</div>
              <Card style={{ marginTop: 'var(--space-sm)' }}>
                <p className="chat-message__text" style={{ marginBottom: 'var(--space-sm)' }}>
                  <strong>{msg.cognitiveTask.domain}</strong> — Task {msg.cognitiveTask.task_index + 1} of {msg.cognitiveTask.total_tasks}
                </p>
                <p className="chat-message__text" style={{ marginBottom: 'var(--space-md)' }}>{msg.content}</p>
                {msg.cognitiveTaskAnswered ? (
                  <div className="screening-task__answered" aria-label="Task answered" style={{ padding: 'var(--space-sm) var(--space-md)', backgroundColor: '#052e16', borderRadius: 'var(--radius-button)', color: 'var(--color-success)', fontWeight: 600 }}>
                    {msg.cognitiveTask.domain} — Answered
                  </div>
                ) : (
                  <ScreeningTask
                    task={msg.cognitiveTask}
                    onSubmit={(response) => {
                      sendCognitiveResponse(msg.cognitiveTask!.screening_id, msg.cognitiveTask!.task_index, response)
                      markCognitiveTaskAnswered(msg.id)
                    }}
                  />
                )}
              </Card>
            </div>
          ) : (
            <ChatMessage key={msg.id} message={msg} />
          ),
        )}
        {/* Typing indicator — shown when Ada has not yet replied to the last user message.
            Derived from messages: last message role === 'user' means no assistant response yet.
            aria-live="polite" on the static wrapper announces once when text is inserted. */}
        {messages.length > 0 && messages[messages.length - 1].role === 'user' && (
          <div
            className="chat-typing-indicator"
            aria-live="polite"
            aria-atomic="true"
          >
            <span className="chat-typing-indicator__text">{companionName} is thinking</span>
            <span className="chat-typing-indicator__dots" aria-hidden="true">
              <span className="chat-typing-indicator__dot" />
              <span className="chat-typing-indicator__dot" />
              <span className="chat-typing-indicator__dot" />
            </span>
          </div>
        )}
        <div ref={sentinelRef} aria-hidden="true" />
      </main>

      {/* Status bar */}
      <div
        className={`chat__status chat__status--${wsStatus}`}
        role="status"
        aria-live="polite"
        aria-atomic="true"
        style={{ fontSize: 'var(--size-caption)', color: 'var(--color-text-muted)', padding: 'var(--space-xs) var(--space-md)' }}
      >
        <span className="chat__status-dot" aria-hidden="true" />
        {WS_STATUS_LABELS[wsStatus] ?? wsStatus}
      </div>

      {/* Inline send-failure error — shown when sendMessage fails due to WS being closed */}
      {sendError && (
        <ErrorState
          className="chat__send-error"
          title="Message not sent"
          message={sendError}
          onRetry={retrySend}
        />
      )}

      {/* Input area */}
      <div className="chat__input-area" style={{ background: 'var(--color-bg-elevated)', borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-sm)', paddingLeft: 'var(--space-md)', paddingRight: 'var(--space-md)', paddingBottom: 'calc(var(--space-sm) + env(safe-area-inset-bottom, 0px))', display: 'flex', gap: 'var(--space-sm)', alignItems: 'flex-end' }}>
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
          style={{
            flex: 1,
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-input)',
            color: 'var(--color-text-primary)',
            fontFamily: 'var(--font-body)',
            fontSize: 'var(--size-body)',
            padding: 'var(--space-sm)',
            resize: 'none',
          }}
        />
        <button
          className="chat__send-btn"
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send message"
          type="button"
          style={{
            background: 'var(--color-primary)',
            color: '#ffffff',
            border: 'none',
            borderRadius: 'var(--radius-button)',
            minHeight: 'var(--touch-target-min)',
            padding: '0 var(--space-md)',
            fontFamily: 'var(--font-body)',
            fontWeight: 600,
            fontSize: 'var(--size-body)',
            cursor: canSend ? 'pointer' : 'default',
            opacity: canSend ? 1 : 0.5,
          }}
        >
          Send
        </button>
      </div>

      {/* Floating camera preview */}
      <FacePreview videoRef={videoRef} videoEnabled={videoEnabled} />
    </div>
  )
}
