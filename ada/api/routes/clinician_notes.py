"""
Clinician notes REST endpoints for annotating session and daily summaries.

  GET /api/notes?entity_type=...&entity_id=...  — read notes (clinicians see
      all, caregivers see own only)
  PUT /api/notes                                 — create/update a note
      (requires clinician or caregiver role; patients get 403)

Notes use a UNIQUE constraint on (user_id, entity_type, entity_id) so each
user has at most one note per entity. PUT is an upsert — it creates the note
on first call and updates content on subsequent calls.

@decision DEC-CLIN-NOTES-002
@title Clinicians see all notes, caregivers see only own
@status accepted
@rationale Clinicians need a holistic view of all annotations on an entity
    (including those from other clinicians and caregivers). Caregivers should
    only see their own annotations — they don't have clinical oversight.
    Patients cannot create or view notes (403).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(prefix="/notes", tags=["clinician-notes"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


@router.get("")
async def get_notes(
    request: Request,
    entity_type: str = Query(..., description="Entity type: session_summary or daily_summary"),
    entity_id: str = Query(..., description="ID of the entity being annotated"),
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """Return notes for an entity.

    Clinicians and admins see all notes on the entity.
    Caregivers see only their own notes.
    Patients are forbidden (403).
    """
    if user.role == "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patients cannot access clinician notes",
        )

    # Caregivers only see their own notes
    filter_user_id = user.id if user.role == "caregiver" else None
    rows = await state.get_clinician_notes(entity_type, entity_id, user_id=filter_user_id)
    return rows


@router.put("", status_code=200)
async def upsert_note(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Create or update a clinician note.

    Expected body:
    {
        "entity_type": "session_summary" | "daily_summary",
        "entity_id": "<id>",
        "content": "<text>"
    }

    Requires clinician, caregiver, or admin role. Patients get 403.
    """
    if user.role == "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Patients cannot create clinician notes",
        )

    body = await request.json()
    entity_type = body.get("entity_type")
    entity_id = body.get("entity_id")
    content = body.get("content", "")

    if entity_type not in ("session_summary", "daily_summary"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_type must be 'session_summary' or 'daily_summary'",
        )
    if not entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_id is required",
        )

    note_id = str(uuid.uuid4())
    await state.upsert_clinician_note({
        "id": note_id,
        "user_id": user.id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "content": content,
    })

    # Return the current state of the note (may be newly created or updated)
    rows = await state.get_clinician_notes(entity_type, entity_id, user_id=user.id)
    return rows[0] if rows else {"id": note_id, "status": "created"}
