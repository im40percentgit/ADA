"""
Organization management REST endpoints for multi-tenancy (Phase 14a).

  POST   /api/organizations                     — create org (creator becomes owner)
  GET    /api/organizations/{id}                — get org details (requires membership)
  PUT    /api/organizations/{id}                — update org (requires owner/admin)
  GET    /api/organizations/{id}/members        — list members (requires membership)
  POST   /api/organizations/{id}/invite         — invite existing user (requires admin/owner)
  PUT    /api/organizations/{id}/members/{uid}  — update member role (requires owner)
  DELETE /api/organizations/{id}/members/{uid}  — remove member (requires admin/owner)

All endpoints require authentication via get_current_user.

@decision DEC-ORG-API-001
@title Membership/role checks via list_organization_members query
@status accepted
@rationale Rather than adding a get_organization_member(org_id, user_id)
    method to StateManager, we query list_organization_members and filter
    in the route. The member list is small (typically <100) and this avoids
    adding single-purpose state methods. If performance becomes an issue,
    a targeted query can be added later.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


async def _get_membership(
    state: StateManager, org_id: str, user_id: str
) -> dict[str, Any] | None:
    """Return the membership record for user in org, or None."""
    members = await state.list_organization_members(org_id)
    for m in members:
        if m["user_id"] == user_id:
            return m
    return None


async def _require_membership(
    state: StateManager, org_id: str, user_id: str
) -> dict[str, Any]:
    """Return membership or raise 404."""
    member = await _get_membership(state, org_id, user_id)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return member


async def _require_role(
    state: StateManager, org_id: str, user_id: str, allowed_roles: list[str]
) -> dict[str, Any]:
    """Return membership if role is sufficient, else raise 403."""
    member = await _require_membership(state, org_id, user_id)
    if member["role"] not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient organization role",
        )
    return member


# ---------------------------------------------------------------------------
# POST /api/organizations — create organization
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_organization(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Create a new organization. The creator becomes the owner."""
    body = await request.json()
    name = body.get("name", "").strip()
    slug = body.get("slug", "").strip()

    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="name is required",
        )
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="slug is required",
        )

    org_id = str(uuid.uuid4())
    try:
        await state.create_organization({
            "id": org_id,
            "name": name,
            "slug": slug,
        })
    except Exception:
        # Most likely a UNIQUE constraint violation on slug
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug already exists",
        )

    # Creator becomes owner
    await state.add_organization_member(org_id, user.id, "owner")

    # Set the user's organization_id
    assert state._conn is not None
    await state._conn.execute(
        "UPDATE users SET organization_id = ? WHERE id = ?",
        (org_id, user.id),
    )
    await state._conn.commit()

    org = await state.get_organization(org_id)
    return org  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# GET /api/organizations/{org_id} — get org details
# ---------------------------------------------------------------------------


@router.get("/{org_id}")
async def get_organization(
    org_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Get organization details. Requires membership."""
    await _require_membership(state, org_id, user.id)

    org = await state.get_organization(org_id)
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    members = await state.list_organization_members(org_id)
    org["member_count"] = len(members)
    return org


# ---------------------------------------------------------------------------
# PUT /api/organizations/{org_id} — update org
# ---------------------------------------------------------------------------


@router.put("/{org_id}")
async def update_organization(
    org_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Update organization name/settings. Requires owner or admin role."""
    await _require_role(state, org_id, user.id, ["owner", "admin"])

    body = await request.json()
    updates: dict[str, Any] = {}
    if "name" in body:
        updates["name"] = body["name"]
    if "settings" in body:
        updates["settings"] = body["settings"]

    if updates:
        await state.update_organization(org_id, updates)

    org = await state.get_organization(org_id)
    return org  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# GET /api/organizations/{org_id}/members — list members
# ---------------------------------------------------------------------------


@router.get("/{org_id}/members")
async def list_members(
    org_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """List all members of the organization. Requires membership."""
    await _require_membership(state, org_id, user.id)
    return await state.list_organization_members(org_id)


# ---------------------------------------------------------------------------
# POST /api/organizations/{org_id}/invite — invite existing user
# ---------------------------------------------------------------------------


@router.post("/{org_id}/invite", status_code=201)
async def invite_member(
    org_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Invite an existing user to the organization by email.

    Requires admin or owner role. Looks up user by email, adds them as a
    member, and sets their organization_id. Returns 404 if user not found.
    """
    await _require_role(state, org_id, user.id, ["owner", "admin"])

    body = await request.json()
    email = body.get("email", "").strip()
    role = body.get("role", "member")

    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="email is required",
        )

    if role not in ("owner", "admin", "member"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role must be one of: owner, admin, member",
        )

    # Look up user by email
    target_user = await state.get_user_by_email(email)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Check if already a member
    existing = await _get_membership(state, org_id, target_user["id"])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this organization",
        )

    await state.add_organization_member(org_id, target_user["id"], role)

    # Set the invited user's organization_id
    assert state._conn is not None
    await state._conn.execute(
        "UPDATE users SET organization_id = ? WHERE id = ?",
        (org_id, target_user["id"]),
    )
    await state._conn.commit()

    return {
        "organization_id": org_id,
        "user_id": target_user["id"],
        "email": email,
        "role": role,
    }


# ---------------------------------------------------------------------------
# PUT /api/organizations/{org_id}/members/{user_id} — update member role
# ---------------------------------------------------------------------------


@router.put("/{org_id}/members/{member_user_id}")
async def update_member_role(
    org_id: str,
    member_user_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Update a member's role. Requires owner role."""
    await _require_role(state, org_id, user.id, ["owner"])

    body = await request.json()
    new_role = body.get("role")

    if new_role not in ("owner", "admin", "member"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="role must be one of: owner, admin, member",
        )

    # Verify target is actually a member
    target_member = await _get_membership(state, org_id, member_user_id)
    if target_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    await state.update_member_role(org_id, member_user_id, new_role)

    return {
        "organization_id": org_id,
        "user_id": member_user_id,
        "role": new_role,
    }


# ---------------------------------------------------------------------------
# DELETE /api/organizations/{org_id}/members/{user_id} — remove member
# ---------------------------------------------------------------------------


@router.delete("/{org_id}/members/{member_user_id}")
async def remove_member(
    org_id: str,
    member_user_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> Response:
    """Remove a member from the organization. Requires admin or owner.

    Cannot remove the sole owner — returns 400 if attempted.
    """
    await _require_role(state, org_id, user.id, ["owner", "admin"])

    # Verify target is actually a member
    target_member = await _get_membership(state, org_id, member_user_id)
    if target_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found",
        )

    # Sole owner protection
    if target_member["role"] == "owner":
        members = await state.list_organization_members(org_id)
        owners = [m for m in members if m["role"] == "owner"]
        if len(owners) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove the sole owner",
            )

    await state.remove_organization_member(org_id, member_user_id)

    # Clear the removed user's organization_id
    assert state._conn is not None
    await state._conn.execute(
        "UPDATE users SET organization_id = NULL WHERE id = ?",
        (member_user_id,),
    )
    await state._conn.commit()

    return Response(status_code=204)
