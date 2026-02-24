"""
Pydantic models for emotion analysis results.

EmotionResult captures a single emotion analysis over a patient message,
using Plutchik's wheel of 8 primary emotions plus valence/arousal dimensions.

@decision DEC-EMOTION-001
@title Plutchik 8-emotion model with valence/arousal dimensions
@status accepted
@rationale Plutchik's wheel provides a well-established, clinically-relevant
    set of discrete emotion categories (joy, trust, fear, surprise, sadness,
    disgust, anger, anticipation) that map cleanly to therapeutic language.
    Valence (-1 to +1) and arousal (0 to 1) provide continuous dimensions
    that complement the discrete labels for trend analysis. The combination
    enables both categorical reasoning (e.g., "patient frequently feels sadness")
    and dimensional analysis (e.g., tracking valence over sessions).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

PLUTCHIK_EMOTIONS = frozenset({
    "joy", "trust", "fear", "surprise",
    "sadness", "disgust", "anger", "anticipation",
})


class EmotionDimensions(BaseModel):
    """Continuous valence/arousal dimensions for a detected emotion."""

    valence: float = Field(ge=-1.0, le=1.0, description="Negative (-1) to positive (+1)")
    arousal: float = Field(ge=0.0, le=1.0, description="Calm (0) to excited (1)")


class EmotionResult(BaseModel):
    """
    Result of a single emotion analysis over a message.

    primary_emotion must be one of Plutchik's 8 primary emotions.
    secondary_emotion is optional (also from Plutchik's wheel when present).
    intensity reflects how strongly the emotion is expressed (0.0–1.0).
    dimensions provides continuous valence/arousal placement.
    confidence reflects the model's certainty about the analysis (0.0–1.0).
    """

    primary_emotion: str = Field(description="One of Plutchik's 8 primary emotions")
    secondary_emotion: str | None = Field(default=None, description="Optional secondary emotion")
    intensity: float = Field(ge=0.0, le=1.0, description="Strength of the emotion")
    dimensions: EmotionDimensions
    confidence: float = Field(ge=0.0, le=1.0, description="Analysis confidence")
