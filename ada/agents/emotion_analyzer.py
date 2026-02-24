"""
EmotionAnalyzerAgent — analyses patient messages for emotional content.

Subscribes to MESSAGE_RECEIVED, calls the LLM for structured emotion analysis
using Plutchik's 8 primary emotions plus valence/arousal dimensions, publishes
EmotionAnalyzedEvent, and persists the result to the emotion_analyses table.

@decision DEC-EMOTION-002
@title JSON parsing with regex markdown fence stripping (DEC-KNOWLEDGE-004 pattern)
@status accepted
@rationale LLM providers often wrap JSON in markdown code fences (```json ... ```).
    The same stripping pattern used in the KnowledgeExtractorAgent (DEC-KNOWLEDGE-004)
    is applied here: strip leading/trailing code fences via regex before json.loads().
    On parse failure the agent logs a warning and skips persistence rather than
    crashing — a single malformed response should not interrupt the session.

@decision DEC-EMOTION-003
@title EmotionAnalyzerAgent subscribes to MESSAGE_RECEIVED only
@status accepted
@rationale Emotion analysis is purely reactive — every incoming patient message
    is a candidate for analysis. No session lifecycle events are needed because
    the agent is stateless between messages (each analysis is self-contained).
    Publishing EmotionAnalyzedEvent allows downstream consumers (e.g., trend
    dashboards, therapist summaries) to react without coupling to this agent.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    EmotionAnalyzedEvent,
    EventTypes,
    MessageReceivedEvent,
)
from ada.models.emotion import EmotionResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an emotion analysis module for a mental health support system.
Analyse the patient's message and identify the primary emotion using Plutchik's 8 primary emotions:
joy, trust, fear, surprise, sadness, disgust, anger, anticipation.

Respond ONLY with a valid JSON object — no prose, no markdown fences — in this exact format:
{
  "primary_emotion": "<one of the 8>",
  "secondary_emotion": "<one of the 8 or null>",
  "intensity": <0.0-1.0>,
  "valence": <-1.0 to 1.0>,
  "arousal": <0.0-1.0>,
  "confidence": <0.0-1.0>
}

Definitions:
- primary_emotion: the dominant emotion expressed
- secondary_emotion: a second notable emotion, or null if absent
- intensity: how strongly the emotion is expressed (0=very mild, 1=very strong)
- valence: emotional positivity (-1=very negative, 0=neutral, 1=very positive)
- arousal: activation level (0=calm/low energy, 1=excited/high energy)
- confidence: your confidence in this analysis (0=uncertain, 1=certain)"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap JSON in."""
    text = re.sub(r'^\s*```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?\s*```\s*$', '', text)
    return text.strip()


class EmotionAnalyzerAgent(BaseAgent):
    """
    Emotion analysis agent.

    Subscribes to MESSAGE_RECEIVED. For each incoming patient message, sends
    the content to the LLM requesting a structured Plutchik emotion analysis,
    parses the JSON response, publishes EmotionAnalyzedEvent, and persists
    the result to the emotion_analyses table.

    Parsing failures are logged as warnings and silently skipped — a bad
    LLM response must not interrupt the therapeutic session.
    """

    @property
    def name(self) -> str:
        return "emotion_analyzer"

    @property
    def description(self) -> str:
        return "Emotion analysis agent — identifies Plutchik emotions in patient messages"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.MESSAGE_RECEIVED]

    async def handle_event(self, event: AdaEvent) -> None:
        """Route incoming events to typed handlers."""
        try:
            if event.event_type == EventTypes.MESSAGE_RECEIVED:
                assert isinstance(event, MessageReceivedEvent)
                await self._handle_message_received(event)
        except Exception:
            logger.exception("EmotionAnalyzerAgent: unhandled error in handle_event")

    async def _handle_message_received(self, event: MessageReceivedEvent) -> None:
        """Analyse emotion in a patient message and publish/persist the result."""
        content = event.content
        if not content or not content.strip():
            return

        # Call LLM for structured emotion analysis
        try:
            response = await self.llm.complete(
                [{"role": "user", "content": content}],
                system=_SYSTEM_PROMPT,
                max_tokens=256,
                temperature=0.2,
            )
            raw = response.content
        except Exception:
            logger.exception(
                "EmotionAnalyzerAgent: LLM call failed for message_id=%s",
                event.message_id,
            )
            return

        # Parse JSON response — strip markdown fences first
        try:
            cleaned = _strip_fences(raw)
            data = json.loads(cleaned)
            result = EmotionResult(
                primary_emotion=data["primary_emotion"],
                secondary_emotion=data.get("secondary_emotion"),
                intensity=float(data["intensity"]),
                dimensions={
                    "valence": float(data["valence"]),
                    "arousal": float(data["arousal"]),
                },
                confidence=float(data["confidence"]),
            )
        except Exception:
            logger.warning(
                "EmotionAnalyzerAgent: failed to parse LLM response for "
                "message_id=%s — raw=%r",
                event.message_id,
                raw,
            )
            return

        # Publish event
        analysis_id = str(uuid.uuid4())
        await self.bus.publish(
            EmotionAnalyzedEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                message_id=event.message_id,
                primary_emotion=result.primary_emotion,
                secondary_emotion=result.secondary_emotion,
                intensity=result.intensity,
                valence=result.dimensions.valence,
                arousal=result.dimensions.arousal,
                confidence=result.confidence,
            )
        )

        # Persist to DB
        try:
            await self.state.create_emotion_analysis({
                "id": analysis_id,
                "session_id": event.session_id,
                "patient_id": event.patient_id,
                "message_id": event.message_id,
                "primary_emotion": result.primary_emotion,
                "secondary_emotion": result.secondary_emotion,
                "intensity": result.intensity,
                "valence": result.dimensions.valence,
                "arousal": result.dimensions.arousal,
                "confidence": result.confidence,
            })
        except Exception:
            logger.exception(
                "EmotionAnalyzerAgent: failed to persist analysis for "
                "message_id=%s",
                event.message_id,
            )

        logger.info(
            "EmotionAnalyzerAgent: analysed message_id=%s — "
            "primary=%s intensity=%.2f valence=%.2f arousal=%.2f confidence=%.2f",
            event.message_id,
            result.primary_emotion,
            result.intensity,
            result.dimensions.valence,
            result.dimensions.arousal,
            result.confidence,
        )
