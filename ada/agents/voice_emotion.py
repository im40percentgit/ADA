"""
VoiceEmotionAgent -- classifies emotion from audio via feature extraction + LLM.

Subscribes to AUDIO_CHUNK_RECEIVED, extracts audio features via librosa,
sends a structured feature summary to the LLM for emotion classification,
publishes VoiceAnalyzedEvent, and persists to audio_analyses table.

@decision DEC-ML-001
@title LLM classification over dedicated ML models
@status accepted
@rationale Feature extraction uses real signal processing (librosa) but
    classification is delegated to the LLM. This avoids ~2GB model downloads,
    works on any CPU, and leverages Claude's clinical emotion understanding.

@decision DEC-ML-009
@title VoiceEmotionAgent follows EmotionAnalyzerAgent pattern
@status accepted
@rationale The same handle_event -> LLM call -> parse JSON -> publish event ->
    persist to DB pattern from EmotionAnalyzerAgent is reused. This consistency
    makes the agent predictable and testable using the same MockLLMProvider
    approach.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    AudioChunkReceivedEvent,
    EventTypes,
    VoiceAnalyzedEvent,
)
from ada.ml.audio_features import extract_features, features_to_prompt_summary

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a voice emotion analysis module for a mental health support system.
Analyse the extracted audio features from a therapy session and classify the
speaker's emotional state using Plutchik's 8 primary emotions:
joy, trust, fear, surprise, sadness, disgust, anger, anticipation.

Respond ONLY with a valid JSON object -- no prose, no markdown fences:
{
  "emotion": "<one of the 8>",
  "confidence": <0.0-1.0>,
  "reasoning": "<brief explanation>"
}"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap JSON in."""
    text = re.sub(r'^\s*```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?\s*```\s*$', '', text)
    return text.strip()


def _extract_json(text: str) -> str:
    """Extract JSON object from mixed text (for models that add prose)."""
    # Try the whole text first
    stripped = _strip_fences(text)
    try:
        json.loads(stripped)
        return stripped
    except (json.JSONDecodeError, ValueError):
        pass
    # Find first { ... } block
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return stripped


class VoiceEmotionAgent(BaseAgent):
    """
    Voice emotion analysis agent.

    Subscribes to AUDIO_CHUNK_RECEIVED. For each audio chunk, extracts
    features (pitch, energy, speech rate, MFCCs) via librosa, sends the
    features to the LLM for emotion classification, publishes
    VoiceAnalyzedEvent, and persists to audio_analyses table.
    """

    @property
    def name(self) -> str:
        return "voice_emotion"

    @property
    def description(self) -> str:
        return "Voice emotion agent -- classifies emotion from audio features via LLM"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.AUDIO_CHUNK_RECEIVED]

    async def handle_event(self, event: AdaEvent) -> None:
        """Route incoming events to typed handlers."""
        try:
            if event.event_type == EventTypes.AUDIO_CHUNK_RECEIVED:
                assert isinstance(event, AudioChunkReceivedEvent)
                await self._handle_audio_chunk(event)
        except Exception:
            logger.exception("VoiceEmotionAgent: unhandled error in handle_event")

    async def _handle_audio_chunk(self, event: AudioChunkReceivedEvent) -> None:
        """Extract audio features, classify via LLM, publish and persist."""
        if not event.audio_bytes:
            return

        # Feature extraction
        features = extract_features(event.audio_bytes, sr=event.sample_rate)
        if not features.valid:
            logger.warning(
                "VoiceEmotionAgent: feature extraction failed for chunk_id=%s: %s",
                event.chunk_id, features.error,
            )
            return

        # LLM classification
        prompt = features_to_prompt_summary(features)
        try:
            response = await self.llm.complete(
                [{"role": "user", "content": prompt}],
                system=_SYSTEM_PROMPT,
                max_tokens=256,
                temperature=0.2,
            )
            raw = response.content
        except Exception:
            logger.exception(
                "VoiceEmotionAgent: LLM call failed for chunk_id=%s",
                event.chunk_id,
            )
            return

        # Parse JSON response
        try:
            cleaned = _extract_json(raw)
            data = json.loads(cleaned)
            emotion = str(data["emotion"])
            confidence = float(data["confidence"])
        except Exception:
            logger.warning(
                "VoiceEmotionAgent: failed to parse LLM response for "
                "chunk_id=%s -- raw=%r",
                event.chunk_id, raw,
            )
            return

        # Publish event
        await self.bus.publish(
            VoiceAnalyzedEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                audio_chunk_id=event.chunk_id,
                emotion=emotion,
                pitch_mean=features.pitch_mean,
                energy_mean=features.energy_mean,
                speech_rate=features.speech_rate,
                confidence=confidence,
            )
        )

        # Persist to DB
        analysis_id = str(uuid.uuid4())
        try:
            await self.state.create_audio_analysis(
                id=analysis_id,
                session_id=event.session_id,
                patient_id=event.patient_id,
                audio_chunk_id=event.chunk_id,
                emotion=emotion,
                pitch_mean=features.pitch_mean,
                energy_mean=features.energy_mean,
                speech_rate=features.speech_rate,
                confidence=confidence,
            )
        except Exception:
            logger.exception(
                "VoiceEmotionAgent: failed to persist for chunk_id=%s",
                event.chunk_id,
            )

        logger.info(
            "VoiceEmotionAgent: chunk_id=%s emotion=%s confidence=%.2f "
            "pitch=%.1fHz energy=%.4f rate=%.1f",
            event.chunk_id, emotion, confidence,
            features.pitch_mean, features.energy_mean, features.speech_rate,
        )
