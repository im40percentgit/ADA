"""
MultimodalFusionAgent -- deterministic weighted-average fusion of multimodal emotion signals.

Subscribes to EMOTION_ANALYZED (text), VOICE_ANALYZED, FACE_ANALYZED, and SENSOR_ALERT.
Maintains a per-session signal buffer (one slot per modality). On every incoming signal,
fuses all buffered signals using exponential staleness decay and publishes EMOTION_FUSED.

Architecture:
    EMOTION_ANALYZED (text) ──┐
    VOICE_ANALYZED ───────────┤
    FACE_ANALYZED ────────────┼──→ FusionAgent → weighted average → EMOTION_FUSED → DB
    SENSOR_ALERT ─────────────┘

@decision DEC-FUSION-001
@title Deterministic weighted average over LLM fusion
@status accepted
@rationale Each upstream agent already used Claude for classification.
    Fusion combines their outputs — a math problem, not reasoning.
    Deterministic fusion is fast (~0ms), predictable, and testable
    without LLM mocks. DEC-FUSION-004 also rules out extra LLM spend here.

@decision DEC-FUSION-002
@title Trigger-on-any with staleness decay (no blocking on missing modalities)
@status accepted
@rationale Fusion fires on every incoming signal. Missing modalities get
    zero effective weight rather than blocking the whole pipeline. This
    handles therapy sessions where modalities come and go (muted mic,
    covered camera). The cost is one DB write per incoming event — acceptable.

@decision DEC-FUSION-003
@title Exponential staleness decay with half-life=10s
@status accepted
@rationale weight = 2^(-age/half_life). Default half_life=10s means a signal
    10 seconds old has half the weight of a fresh one. Avoids hard cutoffs —
    signals gradually lose influence rather than suddenly disappearing.
    Configurable via MultimodalConfig.fusion_staleness_half_life.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass

from ada.agents.base import BaseAgent
from ada.core.events import (
    AdaEvent,
    EmotionAnalyzedEvent,
    EventTypes,
    FaceAnalyzedEvent,
    FusedEmotionEvent,
    SensorAlertEvent,
    VoiceAnalyzedEvent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Plutchik valence-arousal map
# ---------------------------------------------------------------------------

PLUTCHIK_MAP: list[tuple[str, float, float]] = [
    ("joy",          0.8,  0.6),
    ("trust",        0.5,  0.3),
    ("fear",        -0.6,  0.8),
    ("surprise",     0.1,  0.9),
    ("sadness",     -0.7,  0.2),
    ("disgust",     -0.5,  0.5),
    ("anger",       -0.6,  0.7),
    ("anticipation", 0.4,  0.7),
]

# Physiological stress level to arousal mapping
STRESS_TO_AROUSAL: dict[str, float] = {
    "low": 0.2, "moderate": 0.5, "high": 0.7, "critical": 0.9,
}


# ---------------------------------------------------------------------------
# ModalitySignal dataclass
# ---------------------------------------------------------------------------

@dataclass
class ModalitySignal:
    """A single emotion signal from one modality."""

    emotion: str        # Plutchik emotion name
    valence: float      # -1.0 to 1.0
    arousal: float      # 0.0 to 1.0
    confidence: float   # 0.0 to 1.0
    timestamp: float    # time.monotonic()
    modality: str       # "text" | "voice" | "face" | "physiological"


# ---------------------------------------------------------------------------
# Pure fusion math functions
# ---------------------------------------------------------------------------

def recency_weight(signal_age_seconds: float, half_life: float = 10.0) -> float:
    """
    Compute exponential recency weight for a signal of given age.

    Formula: 2^(-age / half_life). A signal at age=0 has weight=1.0;
    at age=half_life it has weight=0.5; at age=2*half_life weight=0.25.

    Args:
        signal_age_seconds: Age of the signal in seconds. Negative ages
            (clock skew) are clamped to 0.
        half_life: Half-life in seconds (default 10.0).

    Returns:
        Weight in [0.0, 1.0].
    """
    age = max(0.0, signal_age_seconds)
    return 2.0 ** (-age / half_life)


def emotion_to_va(emotion: str) -> tuple[float, float]:
    """
    Map a Plutchik emotion name to (valence, arousal).

    Case-insensitive lookup. Unknown emotions return (0.0, 0.5) -- neutral.

    Args:
        emotion: Emotion name string (e.g. "joy", "fear").

    Returns:
        (valence, arousal) tuple with values in [-1.0, 1.0] x [0.0, 1.0].
    """
    target = emotion.lower()
    for name, valence, arousal in PLUTCHIK_MAP:
        if name == target:
            return (valence, arousal)
    return (0.0, 0.5)


def va_to_emotion(valence: float, arousal: float) -> str:
    """
    Map a (valence, arousal) point to the nearest Plutchik emotion.

    Nearest by Euclidean distance in V-A space.

    Args:
        valence: Valence in [-1.0, 1.0].
        arousal: Arousal in [0.0, 1.0].

    Returns:
        Emotion name string from PLUTCHIK_MAP.
    """
    best_name = PLUTCHIK_MAP[0][0]
    best_dist = math.inf
    for name, v, a in PLUTCHIK_MAP:
        dist = math.sqrt((valence - v) ** 2 + (arousal - a) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_name = name
    return best_name


def fuse_signals(
    signals: list[ModalitySignal],
    now: float,
    half_life: float = 10.0,
    min_weight: float = 0.01,
) -> dict | None:
    """
    Fuse a list of modality signals into a unified emotion estimate.

    For each signal, effective_weight = confidence * recency_weight(age, half_life).
    Signals with effective_weight < min_weight are discarded as too stale.
    Returns None if no signals survive filtering.

    Args:
        signals: List of ModalitySignal to fuse.
        now: Current monotonic timestamp (time.monotonic()).
        half_life: Staleness half-life in seconds.
        min_weight: Minimum effective weight to include a signal.

    Returns:
        Dict with keys: fused_emotion, fused_valence, fused_arousal,
        confidence, modalities. Or None if no valid signals remain.
    """
    valid: list[tuple[ModalitySignal, float]] = []

    for sig in signals:
        age = now - sig.timestamp
        w = sig.confidence * recency_weight(age, half_life)
        if w >= min_weight:
            valid.append((sig, w))

    if not valid:
        return None

    total_weight = sum(w for _, w in valid)
    fused_v = sum(sig.valence * w for sig, w in valid) / total_weight
    fused_a = sum(sig.arousal * w for sig, w in valid) / total_weight
    mean_confidence = total_weight / len(valid)
    fused_emotion = va_to_emotion(fused_v, fused_a)
    modalities = [sig.modality for sig, _ in valid]

    return {
        "fused_emotion": fused_emotion,
        "fused_valence": fused_v,
        "fused_arousal": fused_a,
        "confidence": mean_confidence,
        "modalities": modalities,
    }


# ---------------------------------------------------------------------------
# MultimodalFusionAgent
# ---------------------------------------------------------------------------

class MultimodalFusionAgent(BaseAgent):
    """
    Fuses text, voice, face, and physiological emotion signals into a unified
    emotion assessment using deterministic weighted averaging with exponential
    staleness decay.

    Subscribes to EMOTION_ANALYZED, VOICE_ANALYZED, FACE_ANALYZED, SENSOR_ALERT.
    On every incoming signal: updates the per-session buffer, fuses all available
    signals, publishes FusedEmotionEvent, and persists to fused_emotions DB table.

    @decision DEC-FUSION-001
    @title Deterministic weighted average over LLM fusion
    @status accepted
    @rationale See module docstring.

    @decision DEC-FUSION-002
    @title Trigger-on-any with staleness decay
    @status accepted
    @rationale See module docstring.

    @decision DEC-FUSION-003
    @title Exponential staleness decay (half-life model)
    @status accepted
    @rationale See module docstring.
    """

    def __init__(self) -> None:
        super().__init__()
        # session_id -> modality -> ModalitySignal
        self._buffers: dict[str, dict[str, ModalitySignal]] = {}

    @property
    def name(self) -> str:
        return "fusion"

    @property
    def description(self) -> str:
        return "Multimodal fusion -- weighted-average emotion signal combiner"

    @property
    def supported_events(self) -> list[str]:
        return [
            EventTypes.EMOTION_ANALYZED,
            EventTypes.VOICE_ANALYZED,
            EventTypes.FACE_ANALYZED,
            EventTypes.SENSOR_ALERT,
        ]

    # ------------------------------------------------------------------
    # Config accessors
    # ------------------------------------------------------------------

    @property
    def _half_life(self) -> float:
        if self._config and hasattr(self._config, "multimodal"):
            return getattr(self._config.multimodal, "fusion_staleness_half_life", 10.0)
        return 10.0

    @property
    def _min_weight(self) -> float:
        if self._config and hasattr(self._config, "multimodal"):
            return getattr(self._config.multimodal, "fusion_min_weight", 0.01)
        return 0.01

    @property
    def _fusion_enabled(self) -> bool:
        if self._config and hasattr(self._config, "multimodal"):
            return getattr(self._config.multimodal, "fusion_enabled", True)
        return True

    # ------------------------------------------------------------------
    # Event routing
    # ------------------------------------------------------------------

    async def handle_event(self, event: AdaEvent) -> None:
        """Route incoming events to typed handlers."""
        try:
            if event.event_type == EventTypes.EMOTION_ANALYZED:
                assert isinstance(event, EmotionAnalyzedEvent)
                await self._handle_text(event)
            elif event.event_type == EventTypes.VOICE_ANALYZED:
                assert isinstance(event, VoiceAnalyzedEvent)
                await self._handle_voice(event)
            elif event.event_type == EventTypes.FACE_ANALYZED:
                assert isinstance(event, FaceAnalyzedEvent)
                await self._handle_face(event)
            elif event.event_type == EventTypes.SENSOR_ALERT:
                assert isinstance(event, SensorAlertEvent)
                await self._handle_sensor(event)
        except Exception:
            logger.exception("FusionAgent: error handling %s", event.event_type)

    # ------------------------------------------------------------------
    # Per-modality signal extraction
    # ------------------------------------------------------------------

    async def _handle_text(self, event: EmotionAnalyzedEvent) -> None:
        """Extract signal from text emotion analysis event."""
        signal = ModalitySignal(
            emotion=event.primary_emotion,
            valence=event.valence,
            arousal=event.arousal,
            confidence=event.confidence,
            timestamp=time.monotonic(),
            modality="text",
        )
        await self._update_and_fuse(event.session_id, event.patient_id, signal)

    async def _handle_voice(self, event: VoiceAnalyzedEvent) -> None:
        """Extract signal from voice emotion analysis event."""
        valence, arousal = emotion_to_va(event.emotion)
        signal = ModalitySignal(
            emotion=event.emotion,
            valence=valence,
            arousal=arousal,
            confidence=event.confidence,
            timestamp=time.monotonic(),
            modality="voice",
        )
        await self._update_and_fuse(event.session_id, event.patient_id, signal)

    async def _handle_face(self, event: FaceAnalyzedEvent) -> None:
        """Extract signal from facial emotion analysis event."""
        valence, arousal = emotion_to_va(event.emotion)
        signal = ModalitySignal(
            emotion=event.emotion,
            valence=valence,
            arousal=arousal,
            confidence=event.confidence,
            timestamp=time.monotonic(),
            modality="face",
        )
        await self._update_and_fuse(event.session_id, event.patient_id, signal)

    async def _handle_sensor(self, event: SensorAlertEvent) -> None:
        """Extract signal from physiological sensor alert event.

        Parses stress level from description format: "stress=high, ...".
        Maps stress level to arousal via STRESS_TO_AROUSAL lookup.
        Uses valence=0.0 (neutral) and emotion="anticipation" (arousal
        without clear valence maps best to anticipation in Plutchik space).
        Confidence fixed at 0.7 -- sensor signals are reliable but indirect.
        """
        try:
            first_part = event.description.split(",")[0].strip()
            stress_level = first_part.split("=")[1].strip().lower()
        except (IndexError, ValueError):
            stress_level = "moderate"

        arousal = STRESS_TO_AROUSAL.get(stress_level, 0.5)
        signal = ModalitySignal(
            emotion="anticipation",
            valence=0.0,
            arousal=arousal,
            confidence=0.7,
            timestamp=time.monotonic(),
            modality="physiological",
        )
        await self._update_and_fuse(event.session_id, event.patient_id, signal)

    # ------------------------------------------------------------------
    # Core fusion
    # ------------------------------------------------------------------

    async def _update_and_fuse(
        self,
        session_id: str,
        patient_id: str,
        signal: ModalitySignal,
    ) -> None:
        """Update the session buffer and publish a fused emotion event."""
        if not session_id:
            return

        if not self._fusion_enabled:
            return

        # Update buffer -- one slot per modality
        if session_id not in self._buffers:
            self._buffers[session_id] = {}
        self._buffers[session_id][signal.modality] = signal

        # Fuse all buffered signals
        signals = list(self._buffers[session_id].values())
        now = time.monotonic()
        result = fuse_signals(signals, now, self._half_life, self._min_weight)
        if result is None:
            return

        # Extract per-modality labels for the event
        buf = self._buffers[session_id]
        text_emotion = buf["text"].emotion if "text" in buf else ""
        voice_emotion = buf["voice"].emotion if "voice" in buf else ""
        face_emotion = buf["face"].emotion if "face" in buf else ""
        physio_state = buf["physiological"].emotion if "physiological" in buf else ""

        # Publish fused event
        await self.bus.publish(FusedEmotionEvent(
            source=self.name,
            session_id=session_id,
            patient_id=patient_id,
            text_emotion=text_emotion,
            voice_emotion=voice_emotion,
            face_emotion=face_emotion,
            physiological_state=physio_state,
            fused_emotion=result["fused_emotion"],
            fused_valence=result["fused_valence"],
            fused_arousal=result["fused_arousal"],
            confidence=result["confidence"],
            modalities_available=result["modalities"],
        ))

        # Persist to DB
        await self.state.create_fused_emotion(
            id=str(uuid.uuid4()),
            session_id=session_id,
            patient_id=patient_id,
            fused_emotion=result["fused_emotion"],
            fused_valence=result["fused_valence"],
            fused_arousal=result["fused_arousal"],
            confidence=result["confidence"],
            modalities_available=result["modalities"],
            text_emotion=text_emotion or None,
            voice_emotion=voice_emotion or None,
            face_emotion=face_emotion or None,
            physiological_state=physio_state or None,
        )

        logger.info(
            "FusionAgent: session=%s fused=%s v=%.2f a=%.2f conf=%.2f modalities=%s",
            session_id,
            result["fused_emotion"],
            result["fused_valence"],
            result["fused_arousal"],
            result["confidence"],
            result["modalities"],
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def stop(self) -> None:
        """Clear session buffers on stop."""
        self._buffers.clear()
        await super().stop()
