"""
TranscriptionAgent -- transcribes audio chunks to text via faster-whisper.

Subscribes to AUDIO_CHUNK_RECEIVED, calls transcribe_audio() in a thread
(to avoid blocking the asyncio event loop), publishes
TranscriptionCompletedEvent, and persists the result to the transcriptions
table.

Downstream, the Chat WS handler subscribes to TRANSCRIPTION_COMPLETED
per-session and:
  1. Sends a {"type": "transcription", "text": ...} frame to the frontend
     for live display.
  2. Publishes a MessageReceivedEvent so TherapistAgent responds as if the
     user had typed the text.

This agent deliberately has no LLM dependency -- Whisper does the
recognition. The pattern (handle_event -> process -> publish -> persist)
mirrors VoiceEmotionAgent for consistency.

@decision DEC-STT-003
@title TranscriptionAgent follows VoiceEmotionAgent pattern exactly
@status accepted
@rationale Same handle_event -> process -> publish event -> persist to DB
    pipeline. No LLM needed (Whisper handles recognition directly).
    asyncio.to_thread() keeps the blocking Whisper call off the event loop.
    Consistency makes the agent predictable and testable.

@decision DEC-ML-016
@title faster-whisper for server-side STT with amplitude-based silence guard
@status accepted
@rationale See ada/ml/stt.py for full rationale. Agent layer only calls
    transcribe_audio() and handles the event routing and DB persistence.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    AudioChunkReceivedEvent,
    EventTypes,
    TranscriptionCompletedEvent,
)
from ada.ml.stt import transcribe_audio

logger = logging.getLogger(__name__)


class TranscriptionAgent(BaseAgent):
    """
    Speech-to-text agent.

    Subscribes to AUDIO_CHUNK_RECEIVED. For each chunk:
    1. Calls transcribe_audio() via asyncio.to_thread() (blocking Whisper).
    2. Skips if the result is empty (silence or decode failure).
    3. Publishes TranscriptionCompletedEvent.
    4. Persists to the transcriptions table.

    Uses config.stt.model_size / language / compute_type for Whisper settings.
    """

    @property
    def name(self) -> str:
        return "transcription"

    @property
    def description(self) -> str:
        return "Speech-to-text agent -- transcribes audio chunks via faster-whisper"

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
            logger.exception("TranscriptionAgent: unhandled error in handle_event")

    async def _handle_audio_chunk(self, event: AudioChunkReceivedEvent) -> None:
        """Transcribe audio chunk, publish event, persist to DB."""
        if not event.audio_bytes:
            return

        # Pull STT config if available (graceful degradation to defaults).
        stt_cfg = getattr(self.config, "stt", None)
        model_size = getattr(stt_cfg, "model_size", "base") if stt_cfg else "base"
        language = getattr(stt_cfg, "language", None) if stt_cfg else None
        compute_type = getattr(stt_cfg, "compute_type", "int8") if stt_cfg else "int8"

        # Run blocking Whisper inference in a thread pool.
        try:
            result = await asyncio.to_thread(
                transcribe_audio,
                event.audio_bytes,
                model_size=model_size,
                language=language,
                compute_type=compute_type,
            )
        except Exception:
            logger.exception(
                "TranscriptionAgent: transcribe_audio failed for chunk_id=%s",
                event.chunk_id,
            )
            return

        # Skip silence / decode failures.
        if not result.text:
            logger.debug(
                "TranscriptionAgent: empty transcript for chunk_id=%s -- skipping",
                event.chunk_id,
            )
            return

        # Publish event.
        await self.bus.publish(
            TranscriptionCompletedEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                audio_chunk_id=event.chunk_id,
                text=result.text,
                language=result.language,
                confidence=result.confidence,
                duration_s=result.duration_s,
            )
        )

        # Persist to DB.
        transcription_id = str(uuid.uuid4())
        try:
            await self.state.create_transcription(
                id=transcription_id,
                session_id=event.session_id,
                patient_id=event.patient_id,
                audio_chunk_id=event.chunk_id,
                text=result.text,
                language=result.language,
                confidence=result.confidence,
                duration_s=result.duration_s,
            )
        except Exception:
            logger.exception(
                "TranscriptionAgent: failed to persist transcription for chunk_id=%s",
                event.chunk_id,
            )

        logger.info(
            "TranscriptionAgent: chunk_id=%s lang=%s confidence=%.2f "
            "duration=%.1fs text=%r",
            event.chunk_id, result.language, result.confidence,
            result.duration_s, result.text[:60],
        )
