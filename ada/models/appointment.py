"""
Appointment domain model.

Appointments track scheduled therapy sessions, check-ins, and other
patient-provider meetings. The model intentionally keeps scheduling data
separate from session transcripts (which live in the sessions table).

@decision DEC-APPT-001
@title Lightweight CRUD module, not a full agent
@status accepted
@rationale Appointments are pure data in Phase 2b — no LLM involvement.
    Events (AppointmentCreatedEvent, AppointmentUpcomingEvent) are published
    for future consumer agents (reminders, caregiver notifications) without
    requiring those consumers to exist yet. This keeps the implementation
    minimal and the event contract stable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid

from pydantic import BaseModel, Field


def _new_id() -> str:
    return str(uuid.uuid4())


class Appointment(BaseModel):
    """Full appointment record returned from the API."""

    id: str = Field(default_factory=_new_id)
    patient_id: str
    title: str
    description: str | None = None
    scheduled_at: datetime
    duration_minutes: int = 60
    appointment_type: str = "therapy"
    status: str = "scheduled"
    provider_name: str | None = None
    notes: str | None = None
    change_requested: bool = False
    change_note: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"from_attributes": True}


class AppointmentCreate(BaseModel):
    """Input model for creating an appointment."""

    title: str
    scheduled_at: datetime
    description: str | None = None
    duration_minutes: int = 60
    appointment_type: str = "therapy"
    status: str = "scheduled"
    provider_name: str | None = None
    notes: str | None = None


class AppointmentUpdate(BaseModel):
    """Input model for updating an appointment. All fields optional."""

    title: str | None = None
    description: str | None = None
    scheduled_at: datetime | None = None
    duration_minutes: int | None = None
    appointment_type: str | None = None
    status: str | None = None
    provider_name: str | None = None
    notes: str | None = None
    change_requested: bool | None = None
    change_note: str | None = None
