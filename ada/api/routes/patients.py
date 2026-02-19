"""
Patient CRUD REST endpoints.

@decision DEC-API-001
@title JWT auth placeholder only in Phase 1
@status accepted
@rationale Patient routes accept requests without real auth in Phase 1.
    The request.app.state pattern keeps infrastructure accessible without
    global state, enabling clean testing via TestClient with overridden app.state.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ada.models.patient import Patient, PatientCreate, PatientUpdate

router = APIRouter(tags=["patients"])


def _state(request: Request):
    return request.app.state.state_manager


@router.post("/patients", response_model=Patient, status_code=201)
async def create_patient(body: PatientCreate, request: Request) -> dict[str, Any]:
    """Create a new patient record."""
    patient = Patient(
        id=str(uuid.uuid4()),
        name=body.name,
        dob=body.dob,
        preferences=body.preferences,
        emergency_contact=body.emergency_contact,
        caregiver_id=body.caregiver_id,
        created_at=datetime.utcnow(),
    )
    record = patient.model_dump()
    record["dob"] = record["dob"].isoformat() if record["dob"] else None
    record["created_at"] = record["created_at"].isoformat()
    await _state(request).create_patient(record)
    return record


@router.get("/patients", response_model=list[Patient])
async def list_patients(request: Request) -> list[dict[str, Any]]:
    """List all patients."""
    return await _state(request).list_patients()


@router.get("/patients/{patient_id}", response_model=Patient)
async def get_patient(patient_id: str, request: Request) -> dict[str, Any]:
    """Get a single patient by ID."""
    patient = await _state(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.patch("/patients/{patient_id}", response_model=Patient)
async def update_patient(
    patient_id: str, body: PatientUpdate, request: Request
) -> dict[str, Any]:
    """Update patient fields."""
    existing = await _state(request).get_patient(patient_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Patient not found")
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if "dob" in updates and updates["dob"] is not None:
        updates["dob"] = updates["dob"].isoformat()
    await _state(request).update_patient(patient_id, updates)
    updated = await _state(request).get_patient(patient_id)
    return updated
