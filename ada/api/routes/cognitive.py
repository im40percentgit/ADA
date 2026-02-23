"""
Cognitive screening read-only REST endpoints.

All routes are nested under /api/patients/{patient_id}/cognitive-screenings.
These endpoints expose completed screening records — the screening lifecycle
itself is driven by the CognitiveAssessorAgent via the EventBus.

@decision DEC-ASSESS-001
@title cognitive_screenings is a separate read path from assessment_results
@status accepted
@rationale Cognitive screenings are created and updated exclusively by
    CognitiveAssessorAgent. The REST layer is read-only for consumers
    (frontend, clinicians). Write access flows through the EventBus/agent
    boundary to keep business logic out of route handlers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import get_current_user
from ada.models.cognitive import CognitiveScreening
from ada.models.user import User

router = APIRouter(tags=["cognitive"])


def _state(request: Request):
    return request.app.state.state_manager


@router.get(
    "/patients/{patient_id}/cognitive-screenings",
    response_model=list[CognitiveScreening],
)
async def list_cognitive_screenings(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all cognitive screenings for a patient, newest first."""
    patient = await _state(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return await _state(request).list_cognitive_screenings(patient_id)


@router.get(
    "/patients/{patient_id}/cognitive-screenings/{screening_id}",
    response_model=CognitiveScreening,
)
async def get_cognitive_screening(
    patient_id: str,
    screening_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a single cognitive screening record."""
    screening = await _state(request).get_cognitive_screening(screening_id)
    if not screening or screening.get("patient_id") != patient_id:
        raise HTTPException(status_code=404, detail="Cognitive screening not found")
    return screening
