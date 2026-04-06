"""
Admin retention configuration and cleanup endpoints (Phase 14c).

  GET  /api/admin/retention               -- return current retention config
  POST /api/admin/retention/cleanup       -- dry-run or confirmed cleanup

The GET endpoint is accessible to admin or org-owner roles. The cleanup POST
is restricted to admin only to prevent accidental data loss by org owners.

Cleanup safety model:
  - Without ?confirm=true: dry run — returns counts of records eligible for
    deletion without deleting anything.
  - With ?confirm=true:    live run — deletes records older than configured
    thresholds. Both modes require admin role.

@decision DEC-RETENTION-001
@title Dry-run-first cleanup enforced via query param, not separate endpoints
@status accepted
@rationale A single POST endpoint with a confirm guard is the simplest API
    that prevents accidental mass deletion. Operators can always inspect the
    dry-run counts before committing. Using a query param (rather than a
    separate /cleanup/confirm endpoint) keeps the resource URL stable.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ada.api.auth import get_current_user
from ada.core.config import AdaConfig, RetentionConfig
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(prefix="/admin/retention", tags=["retention"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state."""
    return request.app.state.state_manager


def _config(request: Request) -> AdaConfig:
    """Extract AdaConfig from app.state."""
    return request.app.state.config


async def _require_admin_or_owner(state: StateManager, user: User) -> None:
    """Raise 403 unless user is admin or an org owner.

    Mirrors the pattern used in audit_log.py (_require_audit_access).
    """
    if user.role == "admin":
        return

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


async def _require_admin(user: User) -> None:
    """Raise 403 unless user has the admin role."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requires admin role",
        )


# ---------------------------------------------------------------------------
# GET /api/admin/retention
# ---------------------------------------------------------------------------


@router.get("")
async def get_retention_config(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Return the current data retention configuration.

    Requires admin or organization owner role.
    """
    await _require_admin_or_owner(state, user)
    cfg: AdaConfig = _config(request)
    ret: RetentionConfig = cfg.retention
    return {
        "session_data_days": ret.session_data_days,
        "audit_log_days": ret.audit_log_days,
        "export_temp_days": ret.export_temp_days,
    }


# ---------------------------------------------------------------------------
# POST /api/admin/retention/cleanup
# ---------------------------------------------------------------------------


@router.post("/cleanup")
async def run_retention_cleanup(
    request: Request,
    confirm: bool = Query(False, description="Set true to actually delete records"),
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Count (dry run) or delete records older than the configured retention windows.

    Without ``?confirm=true`` (default): returns counts of records that would
    be deleted — no data is modified.

    With ``?confirm=true``: permanently deletes the eligible records from the
    database.

    Requires admin role in both modes.
    """
    await _require_admin(user)

    cfg: AdaConfig = _config(request)
    ret: RetentionConfig = cfg.retention

    counts = await state.count_records_for_retention(
        session_data_days=ret.session_data_days,
        audit_log_days=ret.audit_log_days,
    )

    if not confirm:
        return {
            "dry_run": True,
            "would_delete": counts,
        }

    # Live deletion
    deleted = await state.delete_records_for_retention(
        session_data_days=ret.session_data_days,
        audit_log_days=ret.audit_log_days,
    )
    return {
        "dry_run": False,
        "deleted": deleted,
    }
