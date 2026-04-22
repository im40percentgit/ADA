"""
Prescribing notes REST endpoints for the clinician portal.

  POST /api/patients/{patient_id}/prescribing-notes — create a note
      (requires clinician or admin role; sets clinician_id from JWT)
  GET  /api/patients/{patient_id}/prescribing-notes — list notes newest first
      (any authenticated user)

Notes are linked to a patient and optionally to a specific medication record.
note_type must be one of: prescribe, adjust, discontinue, review.

@decision DEC-PRESC-NOTES-001
@title Prescribing notes endpoint — clinician-write, any-auth-read
@status accepted
@rationale Prescribing decisions are clinical actions that must be
    restricted to clinicians and admins. Reading notes (for audit,
    care coordination, or patient display) is appropriate for any
    authenticated party. The clinician_id is set server-side from the
    JWT so the client cannot impersonate another clinician.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ada.api.auth import get_current_user, require_patient_access
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(tags=["prescribing-notes"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


@router.post(
    "/patients/{patient_id}/prescribing-notes",
    status_code=201,
)
async def create_prescribing_note(
    patient_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    _access: None = Depends(require_patient_access),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Create a prescribing note for a patient.

    Requires clinician or admin role. clinician_id is derived from the
    authenticated user — the client cannot supply a different clinician.

    Expected body:
    {
        "note_type": "prescribe" | "adjust" | "discontinue" | "review",
        "content": "<text>",
        "medication_id": "<uuid>"  (optional)
    }
    """
    if user.role not in ("clinician", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinicians and admins can create prescribing notes",
        )

    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    body = await request.json()
    note_type = body.get("note_type")
    content = body.get("content", "").strip()
    medication_id = body.get("medication_id")

    valid_types = {"prescribe", "adjust", "discontinue", "review"}
    if note_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"note_type must be one of: {', '.join(sorted(valid_types))}",
        )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content is required and must not be empty",
        )

    note_id = str(uuid.uuid4())
    note = {
        "id": note_id,
        "patient_id": patient_id,
        "clinician_id": user.id,
        "medication_id": medication_id,
        "note_type": note_type,
        "content": content,
    }
    await state.create_prescribing_note(note)

    # Return the note as persisted (picks up server-side created_at)
    notes = await state.get_prescribing_notes(patient_id)
    created = next((n for n in notes if n["id"] == note_id), note)
    return created


@router.get("/patients/{patient_id}/prescribing-notes")
async def list_prescribing_notes(
    patient_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    _access: None = Depends(require_patient_access),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """List prescribing notes for a patient, newest first.

    Any authenticated user can read prescribing notes.
    Returns 404 if the patient does not exist.
    """
    patient = await state.get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient not found")

    return await state.get_prescribing_notes(patient_id)
