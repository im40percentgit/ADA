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
