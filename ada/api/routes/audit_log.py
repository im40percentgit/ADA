"""
Audit log query endpoint for compliance (Phase 14c).

  GET /api/audit-log  -- query audit log entries (admin or org owner only)

The audit log is append-only. Entries are created by other endpoints via the
``log_audit`` helper; this module exposes only the read/query side.

@decision DEC-AUDIT-001
@title Audit log query restricted to admin and org-owner roles
@status accepted
@rationale Audit logs contain user actions across the system. Only admins
    (global role) and organization owners (org-level role) should be able to
    query them. Regular users and clinicians access their own data through
    other endpoints. The org-owner check uses the same membership query
    pattern as organizations.py (DEC-ORG-API-001).
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(prefix="/audit-log", tags=["audit-log"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


async def _require_audit_access(state: StateManager, user: User) -> None:
    """Raise 403 unless user is admin or an org owner.

    Admin role (global) always has access. For non-admins, we check whether
    the user is an owner of any organization via organization_members.
    """
    if user.role == "admin":
        return

    # Check if user is an org owner
    org = await state.get_user_organization(user.id)
    if org is not None:
        members = await state.list_organization_members(org["id"])
        for m in members:
            if m["user_id"] == user.id and m["role"] == "owner":
                return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Requires admin or organization owner role",
    )


# ---------------------------------------------------------------------------
# Convenience helper — used by other routes to record audit entries
# ---------------------------------------------------------------------------


async def log_audit(
    state: StateManager,
    user_id: str,
    action: str,
    resource: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
) -> None:
    """Create an audit log entry with an auto-generated UUID.

    This is the primary interface for other route modules to record auditable
    actions. It wraps ``state.create_audit_entry`` with UUID generation.

    Args:
        state: StateManager instance.
        user_id: ID of the acting user.
        action: Action name (e.g. 'export', 'login', 'update').
        resource: Resource type (e.g. 'patient', 'session', 'assessment').
        resource_id: Optional ID of the specific resource acted upon.
        details: Optional dict of additional context.
        ip: Optional IP address of the request origin.
    """
    await state.create_audit_entry({
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "resource_id": resource_id,
        "details": details or {},
        "ip_address": ip,
    })


# ---------------------------------------------------------------------------
# GET /api/audit-log — query audit log
# ---------------------------------------------------------------------------


@router.get("")
async def query_audit_log(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
    user_id: str | None = Query(None, description="Filter by acting user ID"),
    action: str | None = Query(None, description="Filter by action name"),
    resource: str | None = Query(None, description="Filter by resource type"),
    from_date: str | None = Query(None, alias="from", description="ISO datetime lower bound"),
    to_date: str | None = Query(None, alias="to", description="ISO datetime upper bound"),
    limit: int = Query(100, ge=1, le=1000, description="Max entries to return"),
) -> list[dict[str, Any]]:
    """Query audit log entries with optional filters.

    Requires admin role or organization owner membership.
    """
    await _require_audit_access(state, user)

    return await state.query_audit_log(
        user_id=user_id,
        action=action,
        resource=resource,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
    )
