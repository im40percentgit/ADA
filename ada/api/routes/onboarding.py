"""
Onboarding status REST endpoints.

  GET  /api/onboarding/status  — return the authenticated user's onboarding status
  PUT  /api/onboarding/status  — update the authenticated user's onboarding status

Onboarding status tracks where a user is in the first-run setup flow.
Valid values: 'not_started' | 'in_progress' | 'completed'.

The GET always returns a status string (defaults to 'not_started' for
unknown users, matching the DB column DEFAULT).  The PUT accepts only
'in_progress' or 'completed' — callers cannot revert to 'not_started'
via this endpoint.

@decision DEC-ONBOARDING-001
@title Onboarding status stored as a TEXT column on the users table
@status accepted
@rationale Onboarding is a per-user, single-value lifecycle flag. A dedicated
    column on users avoids an extra table join, keeps the default ('not_started')
    co-located with the user record, and is consistent with the is_active flag
    pattern already on the same table. Only 'in_progress' and 'completed' are
    accepted on PUT — 'not_started' is the implicit starting state and cannot
    be restored once a user has progressed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

_VALID_PUT_STATUSES = {"in_progress", "completed"}
_ALL_VALID_STATUSES = {"not_started", "in_progress", "completed"}


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


@router.get("/status")
async def get_status(
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, str]:
    """Return the authenticated user's onboarding status.

    Always returns a valid status string — 'not_started' when no row exists.
    """
    status = await state.get_onboarding_status(user.id)
    return {"status": status}


@router.put("/status", status_code=200)
async def update_status(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, str]:
    """Update the authenticated user's onboarding status.

    Accepted values: 'in_progress' | 'completed'.
    'not_started' is rejected — it is the implicit starting state.

    Body: {"status": "in_progress" | "completed"}
    """
    body = await request.json()
    new_status = body.get("status")

    if new_status not in _VALID_PUT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"status must be one of {sorted(_VALID_PUT_STATUSES)}, got {new_status!r}"
            ),
        )

    await state.set_onboarding_status(user.id, new_status)
    return {"status": new_status}
