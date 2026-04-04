"""
Appointment CRUD REST endpoints.

All routes are nested under /api/patients/{patient_id}/appointments.
POST publishes AppointmentCreatedEvent to the EventBus for future
consumer agents (reminders, caregiver notifications).

@decision DEC-APPT-001
@title Lightweight module (routes + state), not a full agent
@status accepted
@rationale Appointments are pure CRUD in Phase 2b. Events are defined for
    downstream extensibility without requiring any consumer to exist today.
    Direct state access (no agent intermediary) keeps the code minimal and
    the response path fast.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ada.api.auth import get_current_user
from ada.core.events import AppointmentCreatedEvent
from ada.models.appointment import Appointment, AppointmentCreate, AppointmentUpdate
from ada.models.user import User

router = APIRouter(tags=["appointments"])


def _state(request: Request):
    return request.app.state.state_manager


def _bus(request: Request):
    return request.app.state.bus


@router.post(
    "/patients/{patient_id}/appointments",
    response_model=Appointment,
    status_code=201,
)
async def create_appointment(
    patient_id: str,
    body: AppointmentCreate,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Create a new appointment for a patient.

    Publishes AppointmentCreatedEvent on success for future
    reminder/notification consumers.
    """
    patient = await _state(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    now = datetime.utcnow()
    appt_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "id": appt_id,
        "patient_id": patient_id,
        "title": body.title,
        "description": body.description,
        "scheduled_at": body.scheduled_at.isoformat(),
        "duration_minutes": body.duration_minutes,
        "appointment_type": body.appointment_type,
        "status": body.status,
        "provider_name": body.provider_name,
        "notes": body.notes,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    await _state(request).create_appointment(record)

    # Publish event for future consumers (reminders, caregiver notifications)
    bus = _bus(request)
    if bus is not None:
        try:
            await bus.publish(
                AppointmentCreatedEvent(
                    patient_id=patient_id,
                    appointment_id=appt_id,
                    title=body.title,
                    scheduled_at=body.scheduled_at.isoformat(),
                    appointment_type=body.appointment_type,
                )
            )
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to publish AppointmentCreatedEvent for appointment %s — proceeding",
                appt_id,
            )

    result = await _state(request).get_appointment(appt_id)
    return result or record


@router.get(
    "/patients/{patient_id}/appointments",
    response_model=list[Appointment],
)
async def list_appointments(
    patient_id: str,
    request: Request,
    status: str | None = None,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all appointments for a patient, optionally filtered by status."""
    patient = await _state(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return await _state(request).list_appointments(patient_id, status=status)


@router.get(
    "/patients/{patient_id}/appointments/{appointment_id}",
    response_model=Appointment,
)
async def get_appointment(
    patient_id: str,
    appointment_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a single appointment record."""
    appt = await _state(request).get_appointment(appointment_id)
    if not appt or appt.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


@router.patch(
    "/patients/{patient_id}/appointments/{appointment_id}",
    response_model=Appointment,
)
async def update_appointment(
    patient_id: str,
    appointment_id: str,
    body: AppointmentUpdate,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update appointment fields."""
    appt = await _state(request).get_appointment(appointment_id)
    if not appt or appt.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Appointment not found")

    updates: dict[str, Any] = {}
    for field, value in body.model_dump(exclude_none=True).items():
        if field == "scheduled_at" and value is not None:
            updates[field] = value.isoformat()
        else:
            updates[field] = value

    if "change_requested" in updates:
        updates["change_requested"] = int(updates["change_requested"])

    if updates:
        await _state(request).update_appointment(appointment_id, updates)

    updated = await _state(request).get_appointment(appointment_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Appointment not found after update")
    return updated


@router.delete(
    "/patients/{patient_id}/appointments/{appointment_id}",
)
async def delete_appointment(
    patient_id: str,
    appointment_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> Response:
    """Hard-delete an appointment record."""
    appt = await _state(request).get_appointment(appointment_id)
    if not appt or appt.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    await _state(request).delete_appointment(appointment_id)
    return Response(status_code=204)
