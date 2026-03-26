"""
Care circle management REST endpoints.

Provides CRUD operations for care circles and their members:
  GET  /api/circles/my                          — list circles the caller belongs to
  GET  /api/circles/{circle_id}/members         — list all members of a circle
  POST /api/circles/{circle_id}/members         — add a member (primary_caregiver/clinician only)
  DELETE /api/circles/{circle_id}/members/{uid} — remove a member (primary_caregiver only)

Authorization is enforced by resolve_circle_access, which returns 404 for
non-members (to avoid leaking circle existence) and 403 for role violations.

@decision DEC-CIRCLE-002
@title Circle routes use resolve_circle_access for all member-scoped endpoints
@status accepted
@rationale Every endpoint that touches a specific circle first calls
    resolve_circle_access, which unifies the 404/403 logic in one place.
    This prevents route authors from forgetting membership checks and keeps
    the permission model consistent: any member can read, only
    primary_caregiver/clinician can add, only primary_caregiver can remove.

@decision DEC-CIRCLE-003
@title add_circle_member looks up target user by email rather than user_id
@status accepted
@rationale Callers (UI) know the invitee's email address, not their internal
    UUID. Looking up by email keeps the API human-friendly and avoids exposing
    internal IDs in the invite flow. The route still stores the internal user_id
    in the membership record.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import get_current_user, resolve_circle_access
from ada.core.state import StateManager
from ada.models.circle import AddMemberRequest
from ada.models.user import User

router = APIRouter(prefix="/circles", tags=["circles"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


@router.get("/my")
async def list_my_circles(
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """Return all care circles the authenticated user belongs to."""
    return await state.get_circles_by_user(user.id)


@router.get("/{circle_id}/members")
async def list_circle_members(
    circle_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """Return all members of a circle. Caller must be a member."""
    await resolve_circle_access(user, circle_id, state)
    return await state.get_circle_members(circle_id)


@router.post("/{circle_id}/members", status_code=201)
async def add_circle_member(
    circle_id: str,
    body: AddMemberRequest,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Add a user to the circle by email. Requires primary_caregiver or clinician role."""
    await resolve_circle_access(
        user,
        circle_id,
        state,
        require_roles=["primary_caregiver", "clinician"],
    )

    target_user = await state._fetchone(
        "SELECT id, email FROM users WHERE email = ?", (body.email,)
    )
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    member_id = str(uuid.uuid4())
    try:
        await state.add_circle_member(
            member_id=member_id,
            circle_id=circle_id,
            user_id=target_user["id"],
            role=body.role,
            added_by=user.id,
        )
    except Exception:
        raise HTTPException(status_code=409, detail="Already a member")

    return {
        "id": member_id,
        "user_id": target_user["id"],
        "email": target_user["email"],
        "role": body.role,
        "created_at": "",
    }


@router.delete("/{circle_id}/members/{member_user_id}", status_code=204)
async def remove_circle_member(
    circle_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> None:
    """Remove a user from the circle. Requires primary_caregiver role."""
    await resolve_circle_access(
        user,
        circle_id,
        state,
        require_roles=["primary_caregiver"],
    )
    await state.remove_circle_member(circle_id, member_user_id)
