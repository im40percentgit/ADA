"""
Cognitive screening interaction REST endpoints.

These endpoints allow clinicians/caregivers to start a cognitive screening
session and submit patient responses to individual tasks. The actual task
presentation and scoring logic lives in CognitiveAssessorAgent — routes
only create state records and publish EventBus events.

Endpoints:
  POST /api/patients/{patient_id}/screenings/start
      Create a new in-progress cognitive screening record and fire
      AssessmentTriggeredEvent so CognitiveAssessorAgent picks it up.

  POST /api/screenings/{screening_id}/respond
      Submit a patient response for a single task. Publishes
      CognitiveTaskResponseEvent so CognitiveAssessorAgent can score and
      advance the screening state.

@decision DEC-SCREEN-INTERACT-001
@title Screening interaction routes publish events, not agent calls
@status accepted
@rationale Keeps business logic in agents. Routes are thin: persist initial
    record, publish event, return ID/200. CognitiveAssessorAgent owns the
    full task lifecycle (task selection, scoring, completion detection).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ada.api.auth import get_current_user
from ada.core.events import AssessmentTriggeredEvent, CognitiveTaskResponseEvent
from ada.models.user import User

router = APIRouter(tags=["cognitive-screening"])


def _state(request: Request):
    return request.app.state.state_manager


def _bus(request: Request):
    return request.app.state.bus


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class RespondBody(BaseModel):
    task_index: int
    response: Any  # str or dict depending on task_type


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/patients/{patient_id}/screenings/start", status_code=201)
async def start_screening(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, str]:
    """
    Create a new cognitive screening record and trigger the assessor agent.

    Returns the newly created screening_id. CognitiveAssessorAgent subscribes
    to ASSESSMENT_TRIGGERED with instrument='cognitive' and will present the
    first task via the EventBus.
    """
    patient = await _state(request).get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    screening_id = str(uuid.uuid4())
    await _state(request).create_cognitive_screening({
        "id": screening_id,
        "patient_id": patient_id,
    })

    await _bus(request).publish(
        AssessmentTriggeredEvent(
            instrument="cognitive",
            patient_id=patient_id,
            session_id=None,
            metadata={"screening_id": screening_id},
        )
    )

    return {"screening_id": screening_id}


@router.post("/screenings/{screening_id}/respond", status_code=200)
async def respond_to_task(
    screening_id: str,
    body: RespondBody,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, str]:
    """
    Submit a patient response to a cognitive task.

    Looks up the screening to derive patient_id for event routing, then
    publishes CognitiveTaskResponseEvent. CognitiveAssessorAgent scores the
    response and advances the screening to the next task or completion.
    """
    screening = await _state(request).get_cognitive_screening(screening_id)
    if not screening:
        raise HTTPException(status_code=404, detail="Cognitive screening not found")

    await _bus(request).publish(
        CognitiveTaskResponseEvent(
            screening_id=screening_id,
            task_index=body.task_index,
            response=body.response,
            session_id="",
            patient_id=screening.get("patient_id", ""),
        )
    )

    return {"status": "accepted"}
