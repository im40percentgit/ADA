"""Session domain model."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


class Session(BaseModel):
    """Represents a therapy session."""

    id: str = Field(default_factory=_new_id)
    patient_id: str
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    summary: Optional[str] = None
    mood_start: Optional[float] = None  # 1-10
    mood_end: Optional[float] = None    # 1-10

    model_config = {"from_attributes": True}


class SessionCreate(BaseModel):
    """Input model for creating a session."""

    patient_id: str
    mood_start: Optional[float] = None


class SessionEnd(BaseModel):
    """Input model for ending a session."""

    summary: Optional[str] = None
    mood_end: Optional[float] = None
