"""
Assessment result and crisis alert domain models.

@decision DEC-AGENT-002
@title Safety-first — always err toward higher severity
@status accepted
@rationale Crisis alerts are always persisted regardless of severity level.
    The CrisisMonitorAgent escalates when uncertain rather than downgrading.
    Missing a real crisis is far worse than a false positive.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
import uuid

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


Instrument = Literal["phq9", "gad7", "who5"]
CrisisSeverity = Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


class AssessmentResult(BaseModel):
    """Scored result for a structured assessment instrument."""

    id: str = Field(default_factory=_new_id)
    patient_id: str
    instrument: Instrument
    item_scores: list[int]
    total_score: int
    severity: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class AssessmentCreate(BaseModel):
    """Input model for submitting assessment responses."""

    patient_id: str
    instrument: Instrument
    item_scores: list[int]


class CrisisAlert(BaseModel):
    """Persisted record of a detected crisis event."""

    id: str = Field(default_factory=_new_id)
    patient_id: str
    session_id: Optional[str] = None
    severity: CrisisSeverity
    trigger_text: str
    detection_method: str               # "keyword" | "llm"
    escalation_action: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}
