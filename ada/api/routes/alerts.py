"""
Crisis alert management endpoints.

PATCH /api/alerts/{alert_id} — acknowledge or resolve a crisis alert.
Resolving sets resolved_at (UTC ISO timestamp) and resolved_by (user ID).

@decision DEC-ALERT-001
@title Minimal alert resolution endpoint — direct state access, no agent
@status accepted
@rationale Alert resolution is a caregiver UI action with no LLM involvement.
    Direct state access (matching the appointments pattern, DEC-APPT-001) keeps
    the implementation minimal and the response path fast.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ada.api.auth import get_current_user
from ada.models.user import User

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class UpdateAlertRequest(BaseModel):
    status: str  # 'acknowledged' or 'resolved'


@router.patch("/{alert_id}")
async def update_alert_status(
    alert_id: str,
    body: UpdateAlertRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Acknowledge or resolve a crisis alert.

    - ``acknowledged`` — caregiver has seen the alert; resolved_at/by not set.
    - ``resolved`` — alert is closed; resolved_at and resolved_by are recorded.
    """
    if body.status not in ("acknowledged", "resolved"):
        raise HTTPException(
            status_code=400, detail="Status must be 'acknowledged' or 'resolved'"
        )
    state = request.app.state.state_manager
    alert = await state.get_crisis_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    updates: dict = {"status": body.status}
    if body.status == "resolved":
        updates["resolved_at"] = datetime.now(tz=timezone.utc).isoformat()
        updates["resolved_by"] = current_user.id
    await state.update_crisis_alert(alert_id, updates)
    updated = await state.get_crisis_alert(alert_id)
    return dict(updated) if updated else {}
