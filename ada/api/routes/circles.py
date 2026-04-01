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
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ada.api.auth import get_current_user, hash_password, resolve_circle_access
from ada.core.state import StateManager
from ada.models.circle import AddMemberRequest
from ada.models.user import User

router = APIRouter(prefix="/circles", tags=["circles"])


class CreateWithPatientRequest(BaseModel):
    """Request body for caregiver-initiated patient + circle creation."""

    patient_name: str
    patient_email: str | None = None


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


@router.post("/create-with-patient", status_code=201)
async def create_circle_with_patient(
    body: CreateWithPatientRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a care circle with a new or existing patient in one step.

    Caregivers can invite a patient by email (links to existing account) or by
    name alone (creates a placeholder account). Returns 409 if the patient
    already has a care circle.

    @decision DEC-CIRCLE-006
    @title create_circle_with_patient creates placeholder users for email-less patients
    @status accepted
    @rationale Caregivers often register patients who don't yet have Ada accounts.
        A placeholder user (random password, is_active=1) lets the care circle
        exist immediately while the patient can claim their account later via a
        password-reset flow. Without this, caregivers would need a two-step process
        (create patient, then create circle) which is error-prone.
    """
    if current_user.role not in ("caregiver", "clinician", "admin"):
        raise HTTPException(status_code=403, detail="Caregivers only")
    state = request.app.state.state_manager
    now = datetime.now(tz=timezone.utc).isoformat()
    patient_id = None

    if body.patient_email:
        existing_user = await state.get_user_by_email(body.patient_email)
        if existing_user and existing_user.get("role") == "user":
            patient_id = existing_user.get("patient_id")

    if not patient_id:
        patient_id = str(uuid.uuid4())
        await state.create_patient({
            "id": patient_id,
            "name": body.patient_name,
            "dob": None,
            "preferences": "{}",
            "emergency_contact": None,
            "caregiver_id": None,
            "created_at": now,
        })
        if body.patient_email:
            await state.create_user({
                "id": str(uuid.uuid4()),
                "email": body.patient_email,
                "hashed_password": hash_password(str(uuid.uuid4())),
                "role": "user",
                "patient_id": patient_id,
                "created_at": now,
                "is_active": 1,
            })

    existing_circle = await state.get_care_circle_by_patient(patient_id)
    if existing_circle:
        raise HTTPException(status_code=409, detail="Patient already has a care circle")

    circle_id = str(uuid.uuid4())
    await state.create_care_circle(circle_id, patient_id)
    member_id = str(uuid.uuid4())
    await state.add_circle_member(
        member_id=member_id,
        circle_id=circle_id,
        user_id=current_user.id,
        role="primary_caregiver",
        added_by=current_user.id,
    )

    # Auto-add patient as circle member if they have a user account
    if body.patient_email:
        patient_user = await state.get_user_by_email(body.patient_email)
        if patient_user:
            patient_member_id = str(uuid.uuid4())
            await state.add_circle_member(
                member_id=patient_member_id,
                circle_id=circle_id,
                user_id=patient_user["id"],
                role="family",
                added_by=current_user.id,
            )

    return {"circle_id": circle_id, "patient_id": patient_id, "patient_name": body.patient_name}


@router.get("/lookup")
async def lookup_user_by_email(
    email: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict:
    """Look up a patient user by email for circle setup. Caregiver-only.

    Returns basic identity fields so the circle setup wizard can confirm the
    correct person before adding them. Only users with role 'user' (i.e.
    patients) are returned — caregivers cannot look up other caregivers.

    @decision DEC-CIRCLE-005
    @title lookup_user_by_email restricts results to role='user' accounts
    @status accepted
    @rationale Exposing a general email-to-user-id lookup would let caregivers
        enumerate all accounts. Restricting to role='user' limits the surface
        to patient accounts, which are the only valid targets for circle
        membership invitations.
    """
    if user.role not in ("caregiver", "clinician", "admin"):
        raise HTTPException(status_code=403, detail="Caregivers only")
    found = await state.get_user_by_email(email)
    if not found or found.get("role") != "user":
        raise HTTPException(status_code=404, detail="Patient not found")
    return {
        "user_id": found["id"],
        "email": found["email"],
        "patient_id": found.get("patient_id"),
        "role": found["role"],
    }


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
