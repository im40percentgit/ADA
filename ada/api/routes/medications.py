"""
Medication CRUD REST endpoints.

All routes are nested under /api/patients/{patient_id}/medications.
POST calls check_interactions() via the agent registry synchronously
so the response can include interaction warnings.

@decision DEC-AGENT-004
@title Synchronous interaction check via registry on POST /medications
@status accepted
@rationale The HTTP client expects a synchronous response that includes
    any interaction warnings. Routing through the EventBus would require
    request-correlation mechanics (polling or asyncio.Event). Direct
    registry.get("medication_manager").check_interactions() is simpler
    and faster. The agent still publishes MedicationInteractionDetectedEvent
    for audit/notification consumers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from ada.api.auth import get_current_user
from ada.models.medication import Medication, MedicationCreate, MedicationUpdate
from ada.models.user import User

router = APIRouter(tags=["medications"])


def _state(request: Request):
    return request.app.state.state_manager


def _registry(request: Request):
    return request.app.state.registry


@router.post(
    "/patients/{patient_id}/medications",
    response_model=dict,
    status_code=201,
)
async def create_medication(
    patient_id: str,
    body: MedicationCreate,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Add a medication to a patient's record.

    Runs an interaction check via MedicationManagerAgent before persisting.
    Returns the new medication record plus any interaction warning.
    """
    # Verify patient exists
    patient = await _state(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    now = datetime.utcnow()
    med_id = str(uuid.uuid4())
    record: dict[str, Any] = {
        "id": med_id,
        "patient_id": patient_id,
        "name": body.name,
        "dosage": body.dosage,
        "frequency": body.frequency,
        "start_date": body.start_date.isoformat() if body.start_date else None,
        "end_date": body.end_date.isoformat() if body.end_date else None,
        "notes": body.notes,
        "prescribed_by": body.prescribed_by,
        "active": 1,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }

    # Check for interactions via the agent (synchronous — see DEC-AGENT-004)
    interaction_warning: str | None = None
    registry = _registry(request)
    agent = registry.get("medication_manager") if registry else None
    if agent is not None:
        try:
            interaction_warning = await agent.check_interactions(
                patient_id, body.name
            )
        except Exception:
            # Interaction check failure must not block medication creation
            import logging
            logging.getLogger(__name__).warning(
                "Interaction check failed for patient %s med %r — proceeding without check",
                patient_id,
                body.name,
            )

    await _state(request).create_medication(record)

    # Return record with bool active + optional warning
    result = await _state(request).get_medication(med_id)
    response: dict[str, Any] = result or record
    if interaction_warning:
        response = {**response, "interaction_warning": interaction_warning}

    return response


@router.get(
    "/patients/{patient_id}/medications",
    response_model=list[Medication],
)
async def list_medications(
    patient_id: str,
    request: Request,
    active_only: bool = False,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all medications for a patient."""
    patient = await _state(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return await _state(request).list_medications(patient_id, active_only=active_only)


@router.get(
    "/patients/{patient_id}/medications/{medication_id}",
    response_model=Medication,
)
async def get_medication(
    patient_id: str,
    medication_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a single medication record."""
    med = await _state(request).get_medication(medication_id)
    if not med or med.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Medication not found")
    return med


@router.patch(
    "/patients/{patient_id}/medications/{medication_id}",
    response_model=Medication,
)
async def update_medication(
    patient_id: str,
    medication_id: str,
    body: MedicationUpdate,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update medication fields."""
    med = await _state(request).get_medication(medication_id)
    if not med or med.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Medication not found")

    updates: dict[str, Any] = {}
    for field, value in body.model_dump(exclude_none=True).items():
        if field in ("start_date", "end_date") and value is not None:
            updates[field] = value.isoformat()
        elif field == "active":
            updates[field] = 1 if value else 0
        else:
            updates[field] = value

    if updates:
        await _state(request).update_medication(medication_id, updates)

    updated = await _state(request).get_medication(medication_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Medication not found after update")
    return updated


@router.delete(
    "/patients/{patient_id}/medications/{medication_id}",
)
async def deactivate_medication(
    patient_id: str,
    medication_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> Response:
    """Deactivate (soft-delete) a medication record."""
    med = await _state(request).get_medication(medication_id)
    if not med or med.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Medication not found")
    await _state(request).deactivate_medication(medication_id)
    return Response(status_code=204)


@router.post(
    "/patients/{patient_id}/medications/{medication_id}/log",
    status_code=201,
)
async def log_medication(
    patient_id: str,
    medication_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict:
    """Log that a medication was taken."""
    state = _state(request)
    med = await state.get_medication(medication_id)
    if not med or med["patient_id"] != patient_id:
        raise HTTPException(status_code=404, detail="Medication not found")
    log_id = str(uuid.uuid4())
    now = datetime.now(tz=timezone.utc).isoformat()
    log = {
        "id": log_id,
        "medication_id": medication_id,
        "patient_id": patient_id,
        "taken_at": now,
        "status": "taken",
        "created_at": now,
    }
    await state.create_medication_log(log)
    return log


@router.get("/patients/{patient_id}/medications/{medication_id}/logs")
async def get_medication_logs_endpoint(
    patient_id: str,
    medication_id: str,
    request: Request,
    date: str | None = None,
    _user: User = Depends(get_current_user),
) -> list[dict]:
    """Get medication logs, optionally filtered by date (YYYY-MM-DD prefix)."""
    state = _state(request)
    return await state.get_medication_logs(medication_id, date)
