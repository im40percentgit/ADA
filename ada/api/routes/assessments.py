"""
Assessment and mood history REST endpoints.

@decision DEC-AGENT-001
@title Two-stage crisis detection (keyword then LLM)
@status accepted
@rationale Assessment results are stored independently of sessions so they
    can be queried across sessions for longitudinal tracking. Crisis alerts
    are also exposed here for caregiver review.
"""

from __future__ import annotations

from typing import Any

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import get_current_user
from ada.assessment.instruments import score_instrument
from ada.models.assessment import AssessmentCreate, AssessmentResult
from ada.models.user import User

router = APIRouter(tags=["assessments"])


def _state(request: Request):
    return request.app.state.state_manager


@router.post("/assessments", response_model=AssessmentResult, status_code=201)
async def submit_assessment(
    body: AssessmentCreate,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """
    Score and persist an assessment instrument.

    The client submits raw item scores; the server scores them and returns
    the result with severity label.
    """
    try:
        result = score_instrument(body.instrument, body.item_scores)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    record = {
        "id": str(uuid.uuid4()),
        "patient_id": body.patient_id,
        "instrument": body.instrument,
        "item_scores": result.item_scores,
        "total_score": result.total_score,
        "severity": result.severity,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await _state(request).save_assessment(record)
    return record


@router.get("/patients/{patient_id}/assessments")
async def get_assessments(
    patient_id: str,
    request: Request,
    instrument: str | None = None,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Get assessment history for a patient, optionally filtered by instrument."""
    if instrument and instrument not in ("phq9", "gad7", "who5"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid instrument {instrument!r}. Valid: phq9, gad7, who5",
        )
    return await _state(request).get_assessments(patient_id, instrument)


@router.get("/patients/{patient_id}/mood-history")
async def get_mood_history(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """
    Get mood history for a patient derived from WHO-5 assessments.

    Returns WHO-5 results with percentage scores, newest first.
    """
    results = await _state(request).get_assessments(patient_id, "who5")
    return [
        {
            "date": r["timestamp"],
            "score": r["total_score"],
            "session_id": r.get("session_id", ""),
            "percentage": r["total_score"] * 4,
            "severity": r["severity"],
        }
        for r in results
    ]


@router.get("/patients/{patient_id}/crisis-alerts")
async def get_crisis_alerts(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Get crisis alert history for a patient."""
    return await _state(request).get_crisis_alerts(patient_id)
