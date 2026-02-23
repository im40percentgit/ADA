"""
Session management REST endpoints.

@decision DEC-API-001
@title JWT auth placeholder only in Phase 1
@status accepted
@rationale Session routes are open in Phase 1. patient_id is taken from
    the request body rather than a JWT claim. Phase 2 will derive it from
    the authenticated token.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import get_current_user
from ada.models.session import Session, SessionCreate, SessionEnd
from ada.models.user import User

router = APIRouter(tags=["sessions"])


def _state(request: Request):
    return request.app.state.state_manager


@router.post("/sessions", response_model=Session, status_code=201)
async def create_session(
    body: SessionCreate,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Start a new session for a patient."""
    # Verify patient exists
    patient = await _state(request).get_patient(body.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    session = Session(
        id=str(uuid.uuid4()),
        patient_id=body.patient_id,
        started_at=datetime.utcnow(),
        mood_start=body.mood_start,
    )
    record = session.model_dump()
    record["started_at"] = record["started_at"].isoformat()
    await _state(request).create_session(record)
    return record


@router.get("/sessions/{session_id}", response_model=Session)
async def get_session(
    session_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a session by ID."""
    session = await _state(request).get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/patients/{patient_id}/sessions", response_model=list[Session])
async def list_sessions(
    patient_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """List all sessions for a patient."""
    return await _state(request).list_sessions(patient_id)


@router.post("/sessions/{session_id}/end", response_model=Session)
async def end_session(
    session_id: str,
    body: SessionEnd,
    request: Request,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """End a session, optionally recording a summary and end mood."""
    session = await _state(request).get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await _state(request).end_session(
        session_id, summary=body.summary, mood_end=body.mood_end
    )
    updated = await _state(request).get_session(session_id)
    return updated


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    request: Request,
    _user: User = Depends(get_current_user),
) -> list[dict[str, Any]]:
    """Get all messages in a session."""
    return await _state(request).get_messages(session_id)
