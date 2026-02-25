"""
FacialEmotionAgent -- classifies emotion from video frames via face detection + LLM.

Subscribes to VIDEO_FRAME_RECEIVED, extracts facial features via OpenCV,
sends action unit summary to the LLM for emotion classification,
publishes FaceAnalyzedEvent, and persists to face_analyses table.

@decision DEC-ML-001
@title LLM classification over dedicated ML models
@status accepted
@rationale Same as VoiceEmotionAgent -- feature extraction is real signal
    processing, classification is delegated to the LLM.

@decision DEC-ML-011
@title FacialEmotionAgent skips frames with no face detected
@status accepted
@rationale If OpenCV cannot detect a face in the frame, there's nothing
    meaningful to classify. Skipping avoids wasting LLM calls and producing
    low-confidence noise in the face_analyses table.
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    EventTypes,
    FaceAnalyzedEvent,
    VideoFrameReceivedEvent,
)
from ada.ml.face_features import extract_features, features_to_prompt_summary

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a facial emotion analysis module for a mental health support system.
Analyse the extracted facial action units from a therapy session video frame
and classify the patient's emotional state using Plutchik's 8 primary emotions:
joy, trust, fear, surprise, sadness, disgust, anger, anticipation.

Respond ONLY with a valid JSON object -- no prose, no markdown fences:
{
  "emotion": "<one of the 8>",
  "action_units": {"AU1": 0.0, "AU2": 0.0, "AU4": 0.0, "AU5": 0.0, "AU6": 0.0, "AU12": 0.0, "AU15": 0.0},
  "confidence": <0.0-1.0>
}"""


def _strip_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes wrap JSON in."""
    text = re.sub(r'^\s*```(?:json)?\s*\n?', '', text)
    text = re.sub(r'\n?\s*```\s*$', '', text)
    return text.strip()


class FacialEmotionAgent(BaseAgent):
    """
    Facial emotion analysis agent.

    Subscribes to VIDEO_FRAME_RECEIVED. For each video frame, detects faces
    and extracts action units via OpenCV, sends features to the LLM for
    emotion classification, publishes FaceAnalyzedEvent, and persists to
    face_analyses table.
    """

    @property
    def name(self) -> str:
        return "facial_emotion"

    @property
    def description(self) -> str:
        return "Facial emotion agent -- classifies emotion from video frame action units via LLM"

    @property
    def supported_events(self) -> list[str]:
        return [EventTypes.VIDEO_FRAME_RECEIVED]

    async def handle_event(self, event: AdaEvent) -> None:
        """Route incoming events to typed handlers."""
        try:
            if event.event_type == EventTypes.VIDEO_FRAME_RECEIVED:
                assert isinstance(event, VideoFrameReceivedEvent)
                await self._handle_video_frame(event)
        except Exception:
            logger.exception("FacialEmotionAgent: unhandled error in handle_event")

    async def _handle_video_frame(self, event: VideoFrameReceivedEvent) -> None:
        """Extract face features, classify via LLM, publish and persist."""
        if not event.frame_bytes:
            return

        # Feature extraction
        features = extract_features(event.frame_bytes)
        if not features.valid:
            logger.warning(
                "FacialEmotionAgent: feature extraction failed for frame_id=%s: %s",
                event.frame_id, features.error,
            )
            return

        if not features.face_detected:
            logger.debug(
                "FacialEmotionAgent: no face detected in frame_id=%s, skipping",
                event.frame_id,
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
                "FacialEmotionAgent: LLM call failed for frame_id=%s",
                event.frame_id,
            )
            return

        # Parse JSON response
        try:
            cleaned = _strip_fences(raw)
            data = json.loads(cleaned)
            emotion = str(data["emotion"])
            action_units = dict(data.get("action_units", features.action_units))
            confidence = float(data["confidence"])
        except Exception:
            logger.warning(
                "FacialEmotionAgent: failed to parse LLM response for "
                "frame_id=%s -- raw=%r",
                event.frame_id, raw,
            )
            return

        # Publish event
        await self.bus.publish(
            FaceAnalyzedEvent(
                source=self.name,
                session_id=event.session_id,
                patient_id=event.patient_id,
                frame_id=event.frame_id,
                emotion=emotion,
                action_units=action_units,
                confidence=confidence,
            )
        )

        # Persist to DB
        analysis_id = str(uuid.uuid4())
        try:
            await self.state.create_face_analysis(
                id=analysis_id,
                session_id=event.session_id,
                patient_id=event.patient_id,
                frame_id=event.frame_id,
                emotion=emotion,
                action_units=action_units,
                confidence=confidence,
            )
        except Exception:
            logger.exception(
                "FacialEmotionAgent: failed to persist for frame_id=%s",
                event.frame_id,
            )

        logger.info(
            "FacialEmotionAgent: frame_id=%s emotion=%s confidence=%.2f",
            event.frame_id, emotion, confidence,
        )
