"""
Medication domain models.

Medication records track what a patient is prescribed — name, dosage,
frequency, dates, and prescribing clinician. They are owned by a patient
and can be deactivated (soft-deleted) rather than physically removed.

@decision DEC-AGENT-004
@title Medication model uses soft-delete via active flag
@status accepted
@rationale Medication history is clinically significant. Physical deletes
    would lose the record of what a patient was previously prescribed.
    The ``active`` flag allows filtering to current medications while
    preserving full history for audit and clinical review.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


class Medication(BaseModel):
    """Represents a medication record in the Ada system."""

    id: str = Field(default_factory=_new_id)
    patient_id: str
    name: str
    dosage: str | None = None
    frequency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None
    prescribed_by: str | None = None
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class MedicationCreate(BaseModel):
    """Input model for creating a medication record."""

    name: str
    dosage: str | None = None
    frequency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None
    prescribed_by: str | None = None


class MedicationUpdate(BaseModel):
    """Input model for updating a medication record."""

    name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    notes: str | None = None
    prescribed_by: str | None = None
    active: bool | None = None
