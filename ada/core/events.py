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
