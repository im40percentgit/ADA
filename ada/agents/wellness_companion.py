"""
WellnessCompanionAgent — primary daily wellness check-in agent.

Asks about sleep, mood, energy, medication adherence, activities, and social
connection. Reflects and summarises what it hears; does NOT diagnose, prescribe,
or use therapeutic clinical language. Warm, friendly, non-clinical tone.

When a user message contains clinical keywords (coping techniques, specific
terms, breathing exercises, etc.), the agent fires a consultation request to
KnowledgeAgent before generating its response. The resulting evidence is
appended to the system prompt so Ada's answer is grounded in relevant context.

@decision DEC-AGENT-002
@title WellnessCompanionAgent: product repositioning from therapy to wellness
@status accepted
@rationale Ada is repositioned from "AI therapist" to a caregiver-visibility
    platform. Calling the primary agent "therapist" and using CBT/DBT/MI
    therapeutic language creates regulatory and safety risk — the product is
    not a licensed therapist and cannot diagnose or treat. Renaming to
    WellnessCompanionAgent and rewriting the system prompt to daily wellness
    check-ins (sleep, mood, energy, medication, activities, social connection)
    accurately represents the product's role and keeps the scope safe. Crisis
    detection routing through CrisisMonitorAgent via EventBus is unchanged.

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale WellnessCompanionAgent focuses on wellness dialogue and delegates
    crisis detection to CrisisMonitorAgent via the EventBus. This keeps
    each agent's responsibility bounded and testable in isolation.

@decision DEC-KNOWLEDGE-008
@title WellnessCompanionAgent keyword-triggered consultation
@status accepted
@rationale Only messages containing clinical keywords trigger consultation,
    keeping latency low for casual conversation. Fire-and-forget with 2s
    timeout ensures the agent never hangs waiting for evidence.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime

from ada.agents.base import BaseAgent
from ada.agents.handoff import HandoffMixin
from ada.core.events import (
    AdaEvent,
    AgentConsultationRequestEvent,
    AgentConsultationResponseEvent,
    AgentHandoffResponseEvent,
    AssessmentTriggeredEvent,
    EventTypes,
    MessageReceivedEvent,
    MessageSentEvent,
    MoodDetectedEvent,
    SessionStartedEvent,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are Ada, a daily wellness companion supporting people and their caregivers.
Your role is to check in warmly on how someone is doing each day — not to provide therapy or clinical advice.

During each check-in, you may gently ask about:
- Sleep: how they slept, any difficulties
- Mood: how they're feeling emotionally today
- Energy: their energy levels and fatigue
- Medication adherence: whether they took their medications as prescribed
- Activities: what they did today, engagement with hobbies or routines
- Social connection: interactions with family, friends, or carers

Guidelines:
- Listen actively and reflect back what you hear in plain, friendly language
- Validate how they're feeling without judgment
- Use open-ended, conversational questions — one at a time
- Summarise and reflect; do NOT diagnose, prescribe, or make treatment recommendations
- Keep language warm, simple, and non-clinical — avoid therapy jargon
- If someone appears to be in distress or crisis, express genuine care and provide crisis resources
- You are a wellness companion, not a replacement for professional medical or mental health care

You are NOT a clinician. If someone needs medical advice, always encourage them to speak with their doctor."""

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
    "cognitive", "memory test", "brain check",
]

_MEDICATION_KEYWORDS = {
    "medication", "medications", "medicine", "medicines", "prescription",
    "prescriptions", "drug", "drugs", "pill", "pills", "tablet", "tablets",
    "capsule", "capsules", "dose", "dosage", "refill", "pharmacy",
    "pharmacist", "side effect", "side effects", "forgot my medication",
    "forgot to take", "ran out of", "ran out",
}

_CONSULTATION_KEYWORDS = {
    "technique", "strategy", "exercise", "coping", "skill",
    "cbt", "dbt", "mindfulness", "breathing", "grounding",
}

_CONSULTATION_PHRASES = {
    "how do i", "what can i do", "help me with",
    "any tips", "what techniques",
}


class WellnessCompanionAgent(BaseAgent, HandoffMixin):
    """
    Primary daily wellness check-in agent.

    Subscribes to MESSAGE_RECEIVED events, generates LLM responses using
    a wellness-focused system prompt, detects mood from user messages, and
    publishes MESSAGE_SENT + MOOD_DETECTED events.
    """

    @property
    def name(self) -> str:
        return "wellness_companion"

    @property
    def description(self) -> str:
        return "Daily wellness check-in companion — mood, sleep, energy, medication, activities"

    @property
    def supported_events(self) -> list[str]:
        return [
            EventTypes.MESSAGE_RECEIVED,
            EventTypes.SESSION_STARTED,
            EventTypes.AGENT_HANDOFF_RESPONSE,
            EventTypes.AGENT_CONSULTATION_RESPONSE,
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
            elif event.event_type == EventTypes.AGENT_CONSULTATION_RESPONSE:
                pass  # Handled via Future in _consult_knowledge_agent
        except Exception:
            logger.exception("WellnessCompanionAgent: unhandled error in handle_event")

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_session_started(self, event: SessionStartedEvent) -> None:
        """Load prior session context when a new session begins."""
        logger.info(
            "WellnessCompanionAgent: session %s started for patient %s",
            event.session_id,
            event.patient_id,
        )

    async def _on_message(self, event: MessageReceivedEvent) -> None:
        """Generate a wellness companion response to a user message."""
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

        # Check for consultation keywords — ask KnowledgeAgent for evidence
        consultation_evidence = ""
        consultation_hit = bool(content_words & _CONSULTATION_KEYWORDS) or any(
            phrase in lower_content for phrase in _CONSULTATION_PHRASES
        )
        if consultation_hit:
            consultation_evidence = await self._consult_knowledge_agent(
                session_id, patient_id, user_content
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

        # Build system prompt, personalized with companion preferences if available
        system = await self._build_personalized_prompt(patient_id)
        if consultation_evidence:
            system += (
                "\n\nRelevant context for this conversation:\n"
                + consultation_evidence
                + "\n\nIncorporate this context naturally into your response when relevant."
            )

        # Generate response via llm_call() which applies timeout + circuit breaker.
        # On failure, llm_call() calls on_agent_failure() and returns the fallback.
        _fallback_text = "I'm having a moment — could you try saying that again?"
        response = await self.llm_call(
            self.llm.complete(
                llm_messages,
                system=system,
                max_tokens=self.config.llm.max_tokens,
                temperature=self.config.llm.temperature,
            ),
            session_id=session_id,
            fallback=None,
        )
        if response is not None:
            assistant_content = response.content
        else:
            assistant_content = _fallback_text

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
        """Log handoff responses directed back at the wellness companion."""
        logger.info(
            "WellnessCompanionAgent: handoff response from %s (request_id=%s, accepted=%s, notes=%r)",
            event.from_agent,
            event.request_id,
            event.accepted,
            event.notes,
        )

    async def on_agent_failure(
        self,
        error_type: str,
        session_id: str = "",
        exc: Exception | None = None,
    ) -> None:
        """
        Publish AGENT_ERROR event with a user-visible fallback message.

        WellnessCompanionAgent is user-facing — the chat WebSocket relays
        AGENT_ERROR events with a non-empty user_message to the frontend.
        """
        from ada.core.events import AgentErrorEvent

        logger.warning(
            "WellnessCompanionAgent: LLM failure [%s] session=%s",
            error_type, session_id or "<none>",
        )
        if self._bus is not None:
            try:
                await self._bus.publish(
                    AgentErrorEvent(
                        source=self.name,
                        agent_name=self.name,
                        error_type=error_type,
                        session_id=session_id,
                        user_message="Ada is having trouble responding. Try sending another message.",
                    )
                )
            except Exception:
                logger.exception("WellnessCompanionAgent: failed to publish AGENT_ERROR")

    async def _build_personalized_prompt(self, patient_id: str) -> str:
        """Build the system prompt, prepending personality traits if available.

        Looks up companion preferences for the patient's linked user account.
        When preferences exist, the companion's name and communication style
        are injected before the standard wellness prompt.  When no preferences
        are found (new user, no linked account), the default _SYSTEM_PROMPT
        is returned unchanged — "Ada" with standard style.
        """
        try:
            prefs = await self.state.get_companion_preferences_for_patient(patient_id)
        except Exception:
            logger.debug(
                "WellnessCompanionAgent: failed to load companion preferences for %s",
                patient_id,
            )
            prefs = None

        if prefs is None:
            return _SYSTEM_PROMPT

        name = prefs.get("name", "Ada")
        personality = prefs.get("personality", {})
        warmth = personality.get("warmth", "warm")
        verbosity = personality.get("verbosity", "balanced")
        formality = personality.get("formality", "casual")

        persona_prefix = (
            f"Your name is {name}. You are a wellness companion. "
            f"Communication style: {warmth}, {verbosity}, {formality}.\n\n"
        )

        # Replace the default "You are Ada" opening with the personalized version
        return persona_prefix + _SYSTEM_PROMPT

    async def _consult_knowledge_agent(
        self, session_id: str, patient_id: str, question: str
    ) -> str:
        """
        Fire a consultation request to KnowledgeAgent and wait up to 2s for a response.

        Subscribes a one-shot Future-backed handler to AGENT_CONSULTATION_RESPONSE,
        publishes the request, then awaits the future with a 2-second timeout.
        If KnowledgeAgent is absent or slow, returns "" so the agent proceeds
        normally with no evidence enrichment.

        Args:
            session_id: Current session identifier.
            patient_id: Current patient identifier.
            question: The user's message (used as the question).

        Returns:
            Evidence string from KnowledgeAgent, or "" on timeout/error.
        """
        req_id = str(uuid.uuid4())
        response_future: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        async def _capture_response(event: AdaEvent) -> None:
            if (
                isinstance(event, AgentConsultationResponseEvent)
                and event.request_id == req_id
            ):
                if not response_future.done():
                    response_future.set_result(event.answer)

        self.bus.subscribe(
            EventTypes.AGENT_CONSULTATION_RESPONSE,
            _capture_response,
            f"wellness_companion:consultation:{req_id}",
        )

        await self.bus.publish(
            AgentConsultationRequestEvent(
                source=self.name,
                session_id=session_id,
                patient_id=patient_id,
                from_agent=self.name,
                target_agent="knowledge_agent",
                question=question,
                request_id=req_id,
            )
        )

        try:
            evidence = await asyncio.wait_for(response_future, timeout=2.0)
        except asyncio.TimeoutError:
            logger.debug("WellnessCompanionAgent: consultation timed out for %s", req_id)
            evidence = ""
        finally:
            self.bus.unsubscribe(
                EventTypes.AGENT_CONSULTATION_RESPONSE,
                f"wellness_companion:consultation:{req_id}",
            )

        return evidence

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

        # Handle cognitive triggers separately from the standard instrument loop
        if instrument is None:
            for phrase in ("cognitive", "memory test", "brain check"):
                if phrase in lower:
                    instrument = "cognitive"
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
