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

    # Voice I/O (Phase 7)
    AUDIO_RESPONSE = "audio.response"


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
