"""
Ada event type definitions and event dataclasses.

Events flow through the EventBus connecting agents, the API layer,
and the state manager. String-based event types allow dynamic agent
registration without a central enum.

@decision DEC-CORE-001
@title String-based event types over enum
@status accepted
@rationale Agents should be able to define their own event types without
    modifying a central enum. This enables loose coupling and future
    extensibility (e.g., plugin agents). The trade-off is losing static
    exhaustiveness checks, which we accept in favour of flexibility.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

class EventTypes:
    """String constants for all Ada event types."""

    # Session lifecycle
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"

    # Messaging
    MESSAGE_RECEIVED = "message.received"      # user -> system
    MESSAGE_SENT = "message.sent"              # agent -> user
    MESSAGE_STREAM_CHUNK = "message.stream_chunk"

    # Crisis detection
    CRISIS_DETECTED = "crisis.detected"
    CRISIS_ESCALATED = "crisis.escalated"
    CRISIS_RESOLVED = "crisis.resolved"

    # Assessment
    ASSESSMENT_TRIGGERED = "assessment.triggered"
    ASSESSMENT_COMPLETED = "assessment.completed"

    # Agent lifecycle
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    AGENT_ERROR = "agent.error"

    # Mood
    MOOD_DETECTED = "mood.detected"

    # Inter-agent handoff
    AGENT_HANDOFF_REQUEST = "agent.handoff.request"
    AGENT_HANDOFF_RESPONSE = "agent.handoff.response"

    # Knowledge graph
    KNOWLEDGE_INSIGHT_EXTRACTED = "knowledge.insight_extracted"

    # Agent consultation (lightweight, non-handoff)
    AGENT_CONSULTATION_REQUEST = "agent.consultation.request"
    AGENT_CONSULTATION_RESPONSE = "agent.consultation.response"

    # Medication management
    MEDICATION_ADDED = "medication.added"
    MEDICATION_UPDATED = "medication.updated"
    MEDICATION_INTERACTION_DETECTED = "medication.interaction_detected"

    # Cognitive assessment
    COGNITIVE_SCREENING_STARTED = "cognitive.screening_started"
    COGNITIVE_SCREENING_COMPLETED = "cognitive.screening_completed"
    COGNITIVE_TASK_PRESENTED = "cognitive.task_presented"
    COGNITIVE_TASK_RESPONSE = "cognitive.task_response"

    # Appointments
    APPOINTMENT_CREATED = "appointment.created"
    APPOINTMENT_UPCOMING = "appointment.upcoming"

    # Emotion analysis
    EMOTION_ANALYZED = "emotion.analyzed"

    # Session summarization
    SESSION_SUMMARIZED = "session.summarized"

    # Multimodal (Phase 4)
    VOICE_ANALYZED = "voice.analyzed"
    FACE_ANALYZED = "face.analyzed"
    SENSOR_READING = "sensor.reading"
    SENSOR_ALERT = "sensor.alert"
    EMOTION_FUSED = "emotion.fused"

    # Multimodal input (Phase 4b)
    AUDIO_CHUNK_RECEIVED = "audio.chunk_received"
    VIDEO_FRAME_RECEIVED = "video.frame_received"

    # Speech-to-text (Phase 4c STT)
    TRANSCRIPTION_COMPLETED = "transcription.completed"

    # Voice I/O (Phase 7)
    AUDIO_RESPONSE = "audio.response"

    # Daily summary (Phase 8)
    DAILY_SUMMARY_GENERATED = "daily_summary.generated"

    # Care circles (Phase 9a)
    CIRCLE_MEMBER_ADDED = "circle.member_added"
    CIRCLE_MEMBER_REMOVED = "circle.member_removed"

    # Shared boards (Phase 9b)
    BOARD_CREATED = "board.created"
    BOARD_ITEM_ADDED = "board.item_added"
    BOARD_ITEM_CHECKED = "board.item_checked"
    BOARD_ITEM_REORDERED = "board.item_reordered"
    BOARD_ITEM_DELETED = "board.item_deleted"
    BOARD_ITEM_SUGGESTED = "board.item_suggested"
    BOARD_ITEM_APPROVED = "board.item_approved"


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

@dataclass
class AdaEvent:
    """Base class for all Ada events."""

    event_type: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    source: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Domain events
# ---------------------------------------------------------------------------

@dataclass
class SessionStartedEvent(AdaEvent):
    event_type: str = EventTypes.SESSION_STARTED
    session_id: str = ""
    patient_id: str = ""


@dataclass
class SessionEndedEvent(AdaEvent):
    event_type: str = EventTypes.SESSION_ENDED
    session_id: str = ""
    patient_id: str = ""
    summary: str = ""


@dataclass
class MessageReceivedEvent(AdaEvent):
    event_type: str = EventTypes.MESSAGE_RECEIVED
    session_id: str = ""
    patient_id: str = ""
    content: str = ""
    message_id: str = ""


@dataclass
class MessageSentEvent(AdaEvent):
    event_type: str = EventTypes.MESSAGE_SENT
    session_id: str = ""
    patient_id: str = ""
    content: str = ""
    message_id: str = ""
    agent_name: str = ""


@dataclass
class MessageStreamChunkEvent(AdaEvent):
    event_type: str = EventTypes.MESSAGE_STREAM_CHUNK
    session_id: str = ""
    chunk: str = ""
    done: bool = False


@dataclass
class CrisisDetectedEvent(AdaEvent):
    event_type: str = EventTypes.CRISIS_DETECTED
    session_id: str = ""
    patient_id: str = ""
    severity: str = "LOW"          # LOW / MODERATE / HIGH / CRITICAL
    trigger_text: str = ""
    detection_method: str = ""     # "keyword" | "llm"
    escalation_action: str = ""


@dataclass
class AssessmentTriggeredEvent(AdaEvent):
    event_type: str = EventTypes.ASSESSMENT_TRIGGERED
    session_id: str = ""
    patient_id: str = ""
    instrument: str = ""           # phq9 | gad7 | who5


@dataclass
class AssessmentCompletedEvent(AdaEvent):
    event_type: str = EventTypes.ASSESSMENT_COMPLETED
    session_id: str = ""
    patient_id: str = ""
    instrument: str = ""
    total_score: int = 0
    severity: str = ""


@dataclass
class MoodDetectedEvent(AdaEvent):
    event_type: str = EventTypes.MOOD_DETECTED
    session_id: str = ""
    patient_id: str = ""
    mood_score: float = 5.0        # 1-10 scale
    mood_label: str = ""


@dataclass
class AgentHandoffRequestEvent(AdaEvent):
    """
    Published by an agent that wants to hand off context to another agent.

    @decision DEC-AGENT-003
    @title AgentHandoff via EventBus AgentHandoffRequestEvent
    @status accepted
    @rationale Keeps agents fully decoupled. The requesting agent publishes
        a handoff request with target_agent and a context payload. Any agent
        subscribed to AGENT_HANDOFF_REQUEST that matches target_agent will
        respond. This is consistent with the existing event-driven design
        and requires no direct agent-to-agent references.
    """

    event_type: str = EventTypes.AGENT_HANDOFF_REQUEST
    session_id: str = ""
    patient_id: str = ""
    from_agent: str = ""           # name of requesting agent
    target_agent: str = ""         # name of intended recipient
    handoff_reason: str = ""       # human-readable reason
    context: dict = field(default_factory=dict)   # arbitrary context payload
    request_id: str = ""           # correlation ID for matching response


@dataclass
class AgentHandoffResponseEvent(AdaEvent):
    """Published by the receiving agent to acknowledge a handoff request."""

    event_type: str = EventTypes.AGENT_HANDOFF_RESPONSE
    session_id: str = ""
    patient_id: str = ""
    from_agent: str = ""           # agent that handled the handoff
    request_id: str = ""           # matches AgentHandoffRequestEvent.request_id
    accepted: bool = True
    notes: str = ""                # optional response notes


@dataclass
class AgentConsultationRequestEvent(AdaEvent):
    """Published when an agent wants advice from another without full handoff."""

    event_type: str = EventTypes.AGENT_CONSULTATION_REQUEST
    session_id: str = ""
    patient_id: str = ""
    from_agent: str = ""
    target_agent: str = ""
    question: str = ""
    context: dict = field(default_factory=dict)
    request_id: str = ""


@dataclass
class AgentConsultationResponseEvent(AdaEvent):
    """Published in response to a consultation request."""

    event_type: str = EventTypes.AGENT_CONSULTATION_RESPONSE
    session_id: str = ""
    patient_id: str = ""
    from_agent: str = ""
    request_id: str = ""
    answer: str = ""


@dataclass
class MedicationAddedEvent(AdaEvent):
    """Published when a medication record is created for a patient."""

    event_type: str = EventTypes.MEDICATION_ADDED
    patient_id: str = ""
    medication_id: str = ""
    medication_name: str = ""


@dataclass
class MedicationUpdatedEvent(AdaEvent):
    """Published when a medication record is updated."""

    event_type: str = EventTypes.MEDICATION_UPDATED
    patient_id: str = ""
    medication_id: str = ""
    medication_name: str = ""


@dataclass
class MedicationInteractionDetectedEvent(AdaEvent):
    """Published when the MedicationManagerAgent detects a potential drug interaction."""

    event_type: str = EventTypes.MEDICATION_INTERACTION_DETECTED
    patient_id: str = ""
    new_medication: str = ""
    existing_medications: list = field(default_factory=list)
    interaction_notes: str = ""


@dataclass
class AppointmentCreatedEvent(AdaEvent):
    """Published when a new appointment is created for a patient."""

    event_type: str = EventTypes.APPOINTMENT_CREATED
    patient_id: str = ""
    appointment_id: str = ""
    title: str = ""
    scheduled_at: str = ""
    appointment_type: str = ""


@dataclass
class AppointmentUpcomingEvent(AdaEvent):
    """Published by a scheduler when an appointment is approaching."""

    event_type: str = EventTypes.APPOINTMENT_UPCOMING
    patient_id: str = ""
    appointment_id: str = ""
    title: str = ""
    scheduled_at: str = ""
    minutes_until: int = 0


@dataclass
class CognitiveScreeningStartedEvent(AdaEvent):
    """Published when an adaptive cognitive screening session begins."""

    event_type: str = EventTypes.COGNITIVE_SCREENING_STARTED
    session_id: str = ""
    patient_id: str = ""
    screening_id: str = ""


@dataclass
class CognitiveScreeningCompletedEvent(AdaEvent):
    """Published when an adaptive cognitive screening session is scored and saved."""

    event_type: str = EventTypes.COGNITIVE_SCREENING_COMPLETED
    session_id: str = ""
    patient_id: str = ""
    screening_id: str = ""
    overall_score: float = 0.0
    concerns: list = field(default_factory=list)


@dataclass
class CognitiveTaskPresentedEvent(AdaEvent):
    """Published when an individual cognitive task is presented during screening."""

    event_type: str = EventTypes.COGNITIVE_TASK_PRESENTED
    screening_id: str = ""
    task_index: int = 0
    total_tasks: int = 0
    domain: str = ""
    task_type: str = ""            # "text" | "pattern_grid" | "sequence_order" | "clock_reading"
    prompt: str = ""
    task_data: dict = field(default_factory=dict)
    session_id: str = ""
    patient_id: str = ""


@dataclass
class CognitiveTaskResponseEvent(AdaEvent):
    """Published when a patient submits a response to a cognitive task."""

    event_type: str = EventTypes.COGNITIVE_TASK_RESPONSE
    screening_id: str = ""
    task_index: int = 0
    response: Any = ""             # str or dict depending on task_type
    session_id: str = ""
    patient_id: str = ""


@dataclass
class EmotionAnalyzedEvent(AdaEvent):
    """Published by EmotionAnalyzerAgent after analysing a patient message."""

    event_type: str = EventTypes.EMOTION_ANALYZED
    session_id: str = ""
    patient_id: str = ""
    message_id: str = ""
    primary_emotion: str = ""
    secondary_emotion: str | None = None
    intensity: float = 0.0
    valence: float = 0.0
    arousal: float = 0.0
    confidence: float = 0.0


@dataclass
class SessionSummarizedEvent(AdaEvent):
    """Published by SessionSummarizer after generating and persisting a SOAP note."""

    event_type: str = EventTypes.SESSION_SUMMARIZED
    session_id: str = ""
    patient_id: str = ""
    summary_id: str = ""


@dataclass
class VoiceAnalyzedEvent(AdaEvent):
    """Published by VoiceEmotionAgent after analysing an audio chunk."""

    event_type: str = EventTypes.VOICE_ANALYZED
    session_id: str = ""
    patient_id: str = ""
    audio_chunk_id: str = ""
    emotion: str = ""
    pitch_mean: float = 0.0
    energy_mean: float = 0.0
    speech_rate: float = 0.0
    confidence: float = 0.0


@dataclass
class FaceAnalyzedEvent(AdaEvent):
    """Published by FacialEmotionAgent after analysing a video frame."""

    event_type: str = EventTypes.FACE_ANALYZED
    session_id: str = ""
    patient_id: str = ""
    frame_id: str = ""
    emotion: str = ""
    action_units: dict = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class SensorReadingEvent(AdaEvent):
    """Published by SensorSimulator or IoT gateway for each sensor reading."""

    event_type: str = EventTypes.SENSOR_READING
    session_id: str = ""
    patient_id: str = ""
    sensor_type: str = ""    # hr, gsr, spo2
    value: float = 0.0
    unit: str = ""           # bpm, μS, %


@dataclass
class SensorAlertEvent(AdaEvent):
    """Published by PhysiologicalAgent when a sensor reading is anomalous."""

    event_type: str = EventTypes.SENSOR_ALERT
    session_id: str = ""
    patient_id: str = ""
    sensor_type: str = ""
    alert_type: str = ""     # spike, drop, threshold
    value: float = 0.0
    threshold: float = 0.0
    description: str = ""


@dataclass
class FusedEmotionEvent(AdaEvent):
    """Published by MultimodalFusionAgent after combining all modality signals."""

    event_type: str = EventTypes.EMOTION_FUSED
    session_id: str = ""
    patient_id: str = ""
    text_emotion: str = ""
    voice_emotion: str = ""
    face_emotion: str = ""
    physiological_state: str = ""
    fused_emotion: str = ""
    fused_valence: float = 0.0
    fused_arousal: float = 0.0
    confidence: float = 0.0
    modalities_available: list = field(default_factory=list)


@dataclass
class AudioChunkReceivedEvent(AdaEvent):
    """Published by media WS when an audio chunk arrives for processing."""

    event_type: str = EventTypes.AUDIO_CHUNK_RECEIVED
    session_id: str = ""
    patient_id: str = ""
    audio_bytes: bytes = b""
    codec: str = "webm/opus"
    sample_rate: int = 48000
    chunk_id: str = ""
    interim: bool = False


@dataclass
class VideoFrameReceivedEvent(AdaEvent):
    """Published by media WS when a video frame arrives for processing."""

    event_type: str = EventTypes.VIDEO_FRAME_RECEIVED
    session_id: str = ""
    patient_id: str = ""
    frame_bytes: bytes = b""
    format: str = "jpeg"
    resolution: str = ""
    frame_id: str = ""


@dataclass
class TranscriptionCompletedEvent(AdaEvent):
    """Published by TranscriptionAgent when a speech chunk is transcribed.

    Downstream the chat WebSocket bridge subscribes to this event,
    sends a ``{"type": "transcription"}`` frame to the frontend for display,
    and publishes a ``MessageReceivedEvent`` so WellnessCompanionAgent responds.
    """

    event_type: str = EventTypes.TRANSCRIPTION_COMPLETED
    session_id: str = ""
    patient_id: str = ""
    audio_chunk_id: str = ""
    text: str = ""
    language: str = ""
    confidence: float = 0.0
    duration_s: float = 0.0
    interim: bool = False

@dataclass
class AudioResponseEvent(AdaEvent):
    """Published by TTSAgent for each synthesized sentence audio chunk."""

    event_type: str = EventTypes.AUDIO_RESPONSE
    session_id: str = ""
    patient_id: str = ""
    message_id: str = ""
    audio_bytes: bytes = b""
    sample_rate: int = 22050
    format: str = "wav"
    sentence_index: int = 0
    total_sentences: int = 1
    is_final: bool = True


@dataclass
class DailySummaryGeneratedEvent(AdaEvent):
    """Published by DailySummaryGenerator after generating and persisting a daily summary."""

    event_type: str = EventTypes.DAILY_SUMMARY_GENERATED
    patient_id: str = ""
    summary_id: str = ""
    summary_date: str = ""


@dataclass
class CircleMemberAddedEvent(AdaEvent):
    """Published when a user is added to a care circle."""

    event_type: str = EventTypes.CIRCLE_MEMBER_ADDED
    circle_id: str = ""
    patient_id: str = ""
    user_id: str = ""
    role: str = ""


@dataclass
class CircleMemberRemovedEvent(AdaEvent):
    """Published when a user is removed from a care circle."""

    event_type: str = EventTypes.CIRCLE_MEMBER_REMOVED
    circle_id: str = ""
    patient_id: str = ""
    user_id: str = ""


@dataclass
class BoardItemEvent(AdaEvent):
    """Base for board item events — carries board_id and item_id."""

    board_id: str = ""
    item_id: str = ""


@dataclass
class BoardItemAddedEvent(BoardItemEvent):
    """Published when a new item is added to a shared board."""

    event_type: str = EventTypes.BOARD_ITEM_ADDED
    text: str = ""
    created_by: str = ""
    patient_id: str = ""  # Phase 10: needed for notification routing


@dataclass
class BoardItemCheckedEvent(BoardItemEvent):
    """Published when a board item is checked or unchecked."""

    event_type: str = EventTypes.BOARD_ITEM_CHECKED
    checked: bool = False
    updated_by: str = ""
    patient_id: str = ""  # Phase 10: needed for notification routing


@dataclass
class BoardItemReorderedEvent(BoardItemEvent):
    """Published when a board item's position changes."""

    event_type: str = EventTypes.BOARD_ITEM_REORDERED
    new_position: float = 0.0
    updated_by: str = ""


@dataclass
class BoardItemDeletedEvent(BoardItemEvent):
    """Published when a board item is deleted."""

    event_type: str = EventTypes.BOARD_ITEM_DELETED
    deleted_by: str = ""


@dataclass
class BoardItemSuggestedEvent(BoardItemEvent):
    """Published when Ada suggests an item for a board (requires caregiver approval)."""

    event_type: str = EventTypes.BOARD_ITEM_SUGGESTED
    text: str = ""
    patient_id: str = ""


@dataclass
class BoardItemApprovedEvent(BoardItemEvent):
    """Published when a caregiver approves an Ada-suggested board item."""

    event_type: str = EventTypes.BOARD_ITEM_APPROVED
    approved_by: str = ""


@dataclass
class AgentErrorEvent(AdaEvent):
    """
    Published when an agent's LLM call fails, times out, or the circuit opens.

    Subscribed by the chat WebSocket handler, which relays this event to
    user-facing frontends for WellnessCompanion, CognitiveAssessor, and
    CrisisMonitor agents. Background agents (EmotionAnalyzer, FacialEmotion,
    VoiceEmotion, Physiological, MultimodalFusion) do not relay to the frontend.

    Fields:
        agent_name: Name of the agent that failed (e.g. "wellness_companion").
        error_type: One of "timeout", "llm_error", "circuit_open".
        session_id: Session in which the failure occurred (may be empty for
            background agents not tied to a single session).
        user_message: Optional human-readable message suitable for display
            in the chat UI. Empty string means no user-visible message.
    """

    event_type: str = EventTypes.AGENT_ERROR
    agent_name: str = ""
    error_type: str = ""       # "timeout" | "llm_error" | "circuit_open"
    session_id: str = ""
    user_message: str = ""
