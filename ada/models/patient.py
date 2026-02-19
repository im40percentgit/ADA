"""Patient domain model."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field
import uuid


def _new_id() -> str:
    return str(uuid.uuid4())


class Patient(BaseModel):
    """Represents a patient in the Ada system."""

    id: str = Field(default_factory=_new_id)
    name: str
    dob: date | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    emergency_contact: str | None = None
    caregiver_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class PatientCreate(BaseModel):
    """Input model for creating a patient."""

    name: str
    dob: date | None = None
    preferences: dict[str, Any] = Field(default_factory=dict)
    emergency_contact: str | None = None
    caregiver_id: str | None = None


class PatientUpdate(BaseModel):
    """Input model for updating a patient."""

    name: str | None = None
    dob: date | None = None
    preferences: dict[str, Any] | None = None
    emergency_contact: str | None = None
    caregiver_id: str | None = None
