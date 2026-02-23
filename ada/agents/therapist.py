"""
TherapistAgent — primary therapeutic conversation agent.

Uses CBT/DBT/MI techniques via system prompts. Maintains session continuity
by loading prior session context. Detects mood from conversation and can
trigger structured assessments (PHQ-9, GAD-7, WHO-5).

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale TherapistAgent focuses on therapeutic dialogue and delegates
    crisis detection to CrisisMonitorAgent via the EventBus. This keeps
    each agent's responsibility bounded and testable in isolation.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from ada.agents.base import BaseAgent
from ada.agents.handoff import HandoffMixin
from ada.core.events import (
    AdaEvent,
    AgentHandoffResponseEvent,
    AssessmentTriggeredEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
    MoodDetectedEvent,
    SessionStartedEvent,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Ada, a compassionate and skilled mental health support assistant.
You draw on Cognitive Behavioural Therapy (CBT), Dialectical Behaviour Therapy (DBT),
and Motivational Interviewing (MI) techniques to support the person you are speaking with.

Guidelines:
- Listen actively and reflect back what you hear
- Validate emotions without judgment
- Use open-ended questions to explore thoughts and feelings
- Offer psychoeducation when helpful and appropriate
- Never diagnose — you are a support tool, not a clinician
- If someone appears to be in crisis, express care and provide crisis resources
- Keep responses warm, grounded, and appropriately concise

You are NOT a replacement for professional mental health care. Always encourage
professional support when appropriate."""

_MOOD_KEYWORDS_NEGATIVE = {
    "sad", "depressed", "hopeless", "worthless", "empty", "numb", "crying",
    "tears", "miserable", "despair", "lonely", "isolated", "anxious", "panic",
    "afraid", "scared", "overwhelmed", "exhausted", "drained",
}

_MOOD_KEYWORDS_POSITIVE = {
    "happy", "good", "great", "better", "hopeful", "calm", "peaceful",
    "grateful", "excited", "proud", "relieved", "optimistic",
}

_ASSESSMENT_TRIGGER_PHRASES = [
    "phq", "phq9", "phq-9", "depression questionnaire",
    "gad", "gad7", "gad-7", "anxiety questionnaire",
    "who5", "who-5", "wellbeing index",
    "fill out", "complete a", "take a questionnaire", "assessment",
]

_MEDICATION_KEYWORDS = {
    "medication", "medications", "medicine", "medicines", "prescription",
    "prescriptions", "drug", "drugs", "pill", "pills", "tablet", "tablets",
    "capsule", "capsules", "dose", "dosage", "refill", "pharmacy",
    "pharmacist", "side effect", "side effects", "forgot my medication",
    "forgot to take", "ran out of", "ran out",
}


class TherapistAgent(BaseAgent, HandoffMixin):
    """
    Primary therapeutic conversation agent.

    Subscribes to MESSAGE_RECEIVED events, generates LLM responses using
    a CBT/DBT/MI system prompt, detects mood from user messages, and
    publishes MESSAGE_SENT + MOOD_DETECTED events.
    """

    @property
    def name(self) -> str:
        return "therapist"

    @property
    def description(self) -> str:
        return "Primary therapeutic conversation agent using CBT/DBT/MI techniques"

    @property
    def supported_events(self) -> list[str]:
        return [
            EventTypes.MESSAGE_RECEIVED,
            EventTypes.SESSION_STARTED,
            EventTypes.AGENT_HANDOFF_RESPONSE,
        ]

    async def handle_event(self, event: AdaEvent) -> None:
        """Route events to typed handlers."""
        try:
            if event.event_type == EventTypes.MESSAGE_RECEIVED:
                assert isinstance(event, MessageReceivedEvent)
                await self._on_message(event)
            elif event.event_type == EventTypes.SESSION_STARTED:
                assert isinstance(event, SessionStartedEvent)
                await self._on_session_started(event)
            elif event.event_type == EventTypes.AGENT_HANDOFF_RESPONSE:
                assert isinstance(event, AgentHandoffResponseEvent)
                await self._on_handoff_response(event)
        except Exception:
            logger.exception("TherapistAgent: unhandled error in handle_event")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_session_started(self, event: SessionStartedEvent) -> None:
        """Load prior session context when a new session begins."""
        logger.info(
            "TherapistAgent: session %s started for patient %s",
            event.session_id,
            event.patient_id,
        )

    async def _on_message(self, event: MessageReceivedEvent) -> None:
        """Generate a therapeutic response to a user message."""
        session_id = event.session_id
        patient_id = event.patient_id
        user_content = event.content

        # Detect mood from user message (lightweight keyword scan)
        mood_score, mood_label = _detect_mood(user_content)
        if mood_label:
            await self.bus.publish(
                MoodDetectedEvent(
                    source=self.name,
                    session_id=session_id,
                    patient_id=patient_id,
                    mood_score=mood_score,
                    mood_label=mood_label,
                )
            )

        # Check for medication keywords — hand off to MedicationManagerAgent
        lower_content = user_content.lower()
        content_words = set(lower_content.split())
        # Also check multi-word phrases
        medication_hit = bool(content_words & _MEDICATION_KEYWORDS) or any(
            phrase in lower_content for phrase in _MEDICATION_KEYWORDS if " " in phrase
        )
        if medication_hit:
            await self.request_handoff(
                target_agent="medication_manager",
                session_id=session_id,
                patient_id=patient_id,
                reason="User message contains medication-related content",
                context={"trigger_content": user_content[:200]},
            )

        # Persist user message
        await self.state.save_message({
            "id": event.message_id or str(uuid.uuid4()),
            "session_id": session_id,
            "role": "user",
            "content": user_content,
            "timestamp": event.timestamp.isoformat(),
            "agent_name": None,
        })

        # Build conversation history for LLM
        prior_messages = await self.state.get_messages(session_id)
        llm_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in prior_messages
            if m["role"] in ("user", "assistant")
        ]

        # Generate response
        try:
            response = await self.llm.complete(
                llm_messages,
                system=_SYSTEM_PROMPT,
                max_tokens=self.config.llm.max_tokens,
                temperature=self.config.llm.temperature,
            )
            assistant_content = response.content
        except Exception:
            logger.exception("TherapistAgent: LLM call failed")
            assistant_content = (
                "I'm sorry, I'm having trouble responding right now. "
                "If you're in crisis, please contact a crisis line immediately."
            )

        # Persist assistant message
        assistant_msg_id = str(uuid.uuid4())
        await self.state.save_message({
            "id": assistant_msg_id,
            "session_id": session_id,
            "role": "assistant",
            "content": assistant_content,
            "timestamp": datetime.utcnow().isoformat(),
            "agent_name": self.name,
        })

        # Check if an assessment should be triggered
        await self._maybe_trigger_assessment(
            user_content, session_id, patient_id
        )

        # Publish the response event
        await self.bus.publish(
            MessageSentEvent(
                source=self.name,
                session_id=session_id,
                patient_id=patient_id,
                content=assistant_content,
                message_id=assistant_msg_id,
                agent_name=self.name,
            )
        )

    async def _on_handoff_response(self, event: AgentHandoffResponseEvent) -> None:
        """Log handoff responses directed back at the therapist."""
        logger.info(
            "TherapistAgent: handoff response from %s (request_id=%s, accepted=%s, notes=%r)",
            event.from_agent,
            event.request_id,
            event.accepted,
            event.notes,
        )

    async def _maybe_trigger_assessment(
        self,
        content: str,
        session_id: str,
        patient_id: str,
    ) -> None:
        """Trigger a structured assessment if the content suggests it."""
        lower = content.lower()
        instrument = None
        for phrase in _ASSESSMENT_TRIGGER_PHRASES:
            if phrase in lower:
                if "phq" in phrase or "depression" in phrase:
                    instrument = "phq9"
                elif "gad" in phrase or "anxiety" in phrase:
                    instrument = "gad7"
                elif "who" in phrase or "wellbeing" in phrase:
                    instrument = "who5"
                break

        if instrument:
            await self.bus.publish(
                AssessmentTriggeredEvent(
                    source=self.name,
                    session_id=session_id,
                    patient_id=patient_id,
                    instrument=instrument,
                )
            )


# ---------------------------------------------------------------------------
# Mood detection helper (keyword-based, fast path)
# ---------------------------------------------------------------------------

def _detect_mood(text: str) -> tuple[float, str]:
    """
    Lightweight mood detection from text using keyword matching.

    Returns:
        (mood_score, mood_label) where mood_score is 1-10 and
        mood_label is "negative", "positive", or "" if unclear.
    """
    lower = text.lower()
    words = set(lower.split())

    negative_hits = words & _MOOD_KEYWORDS_NEGATIVE
    positive_hits = words & _MOOD_KEYWORDS_POSITIVE

    if negative_hits and not positive_hits:
        return 3.0, "negative"
    if positive_hits and not negative_hits:
        return 7.5, "positive"
    if negative_hits and positive_hits:
        return 5.0, "mixed"
    return 5.0, ""
