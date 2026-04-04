"""
Treatment plan management REST endpoints (Phase 14b).

  POST   /api/patients/{patient_id}/treatment-plans       -- create plan (clinician/admin)
  GET    /api/patients/{patient_id}/treatment-plans       -- list plans for patient
  GET    /api/treatment-plans/{plan_id}                   -- detail with goals + interventions
  PUT    /api/treatment-plans/{plan_id}                   -- update status/title
  POST   /api/treatment-plans/{plan_id}/goals             -- add goal
  PUT    /api/treatment-goals/{goal_id}                   -- update goal
  POST   /api/treatment-goals/{goal_id}/interventions     -- add intervention
  PUT    /api/treatment-interventions/{intervention_id}   -- update intervention

All endpoints require authentication via get_current_user.
Create/update operations require clinician or admin role.

@decision DEC-TX-API-001
@title Treatment plan endpoints follow organization route pattern
@status accepted
@rationale Consistent with the existing CRUD pattern used in organizations.py
    and clinician_notes.py. Role checks are done inline rather than via a
    middleware decorator, matching the established codebase style.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(tags=["treatment-plans"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


def _require_clinician_or_admin(user: User) -> None:
    """Raise 403 if user is not a clinician or admin."""
    if user.role not in ("clinician", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only clinicians and admins can manage treatment plans",
        )


# ---------------------------------------------------------------------------
# POST /api/patients/{patient_id}/treatment-plans -- create plan
# ---------------------------------------------------------------------------


@router.post("/patients/{patient_id}/treatment-plans", status_code=201)
async def create_treatment_plan(
    patient_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Create a new treatment plan for a patient."""
    _require_clinician_or_admin(user)

    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="title is required",
        )

    plan_id = str(uuid.uuid4())
    await state.create_treatment_plan({
        "id": plan_id,
        "patient_id": patient_id,
        "clinician_id": user.id,
        "organization_id": body.get("organization_id"),
        "title": title,
    })

    plan = await state.get_treatment_plan(plan_id)
    return plan  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# GET /api/patients/{patient_id}/treatment-plans -- list plans
# ---------------------------------------------------------------------------


@router.get("/patients/{patient_id}/treatment-plans")
async def list_treatment_plans(
    patient_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """List all treatment plans for a patient."""
    return await state.list_treatment_plans(patient_id)


# ---------------------------------------------------------------------------
# GET /api/treatment-plans/{plan_id} -- detail with goals + interventions
# ---------------------------------------------------------------------------


@router.get("/treatment-plans/{plan_id}")
async def get_treatment_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Return a treatment plan with nested goals and interventions."""
    plan = await state.get_treatment_plan(plan_id)
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treatment plan not found",
        )
    return plan


# ---------------------------------------------------------------------------
# PUT /api/treatment-plans/{plan_id} -- update status/title
# ---------------------------------------------------------------------------


@router.put("/treatment-plans/{plan_id}")
async def update_treatment_plan(
    plan_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Update a treatment plan's title or status."""
    _require_clinician_or_admin(user)

    existing = await state.get_treatment_plan(plan_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treatment plan not found",
        )

    body = await request.json()
    updates: dict[str, Any] = {}
    if "title" in body:
        updates["title"] = body["title"]
    if "status" in body:
        if body["status"] not in ("active", "completed", "archived"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="status must be one of: active, completed, archived",
            )
        updates["status"] = body["status"]

    if updates:
        await state.update_treatment_plan(plan_id, updates)

    plan = await state.get_treatment_plan(plan_id)
    return plan  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# POST /api/treatment-plans/{plan_id}/goals -- add goal
# ---------------------------------------------------------------------------


@router.post("/treatment-plans/{plan_id}/goals", status_code=201)
async def create_treatment_goal(
    plan_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Add a goal to a treatment plan."""
    _require_clinician_or_admin(user)

    existing = await state.get_treatment_plan(plan_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Treatment plan not found",
        )

    body = await request.json()
    description = body.get("description", "").strip()
    if not description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="description is required",
        )

    goal_id = str(uuid.uuid4())
    goal_data: dict[str, Any] = {
        "id": goal_id,
        "plan_id": plan_id,
        "description": description,
    }
    # Optional fields
    for key in ("target_metric", "target_operator", "target_value",
                "current_value", "due_date"):
        if key in body:
            goal_data[key] = body[key]

    await state.create_treatment_goal(goal_data)

    # Return the plan with all goals to show the new addition
    plan = await state.get_treatment_plan(plan_id)
    # Find and return just the new goal
    for g in plan["goals"]:  # type: ignore[index]
        if g["id"] == goal_id:
            return g
    return {"id": goal_id}  # fallback


# ---------------------------------------------------------------------------
# PUT /api/treatment-goals/{goal_id} -- update goal
# ---------------------------------------------------------------------------


@router.put("/treatment-goals/{goal_id}")
async def update_treatment_goal(
    goal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Update a treatment goal."""
    _require_clinician_or_admin(user)

    body = await request.json()
    updates: dict[str, Any] = {}
    for key in ("description", "target_metric", "target_operator",
                "target_value", "current_value", "status", "due_date"):
        if key in body:
            updates[key] = body[key]

    if "status" in updates and updates["status"] not in (
        "active", "met", "unmet", "deferred"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be one of: active, met, unmet, deferred",
        )

    if updates:
        await state.update_treatment_goal(goal_id, updates)

    return {"id": goal_id, **updates}


# ---------------------------------------------------------------------------
# POST /api/treatment-goals/{goal_id}/interventions -- add intervention
# ---------------------------------------------------------------------------


@router.post("/treatment-goals/{goal_id}/interventions", status_code=201)
async def create_treatment_intervention(
    goal_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Add an intervention to a treatment goal."""
    _require_clinician_or_admin(user)

    body = await request.json()
    description = body.get("description", "").strip()
    if not description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="description is required",
        )

    intervention_id = str(uuid.uuid4())
    intervention_data: dict[str, Any] = {
        "id": intervention_id,
        "goal_id": goal_id,
        "description": description,
    }
    if "frequency" in body:
        intervention_data["frequency"] = body["frequency"]

    await state.create_treatment_intervention(intervention_data)
    return {"id": intervention_id, "goal_id": goal_id, "description": description,
            "frequency": body.get("frequency"), "status": "active"}


# ---------------------------------------------------------------------------
# PUT /api/treatment-interventions/{intervention_id} -- update intervention
# ---------------------------------------------------------------------------


@router.put("/treatment-interventions/{intervention_id}")
async def update_treatment_intervention(
    intervention_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Update a treatment intervention."""
    _require_clinician_or_admin(user)

    body = await request.json()
    updates: dict[str, Any] = {}
    for key in ("description", "frequency", "status"):
        if key in body:
            updates[key] = body[key]

    if "status" in updates and updates["status"] not in (
        "active", "completed", "discontinued"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="status must be one of: active, completed, discontinued",
        )

    if updates:
        await state.update_treatment_intervention(intervention_id, updates)

    return {"id": intervention_id, **updates}
