"""
Consent management REST endpoints (Phase 14c).

  GET  /api/consent  -- list current user's consent records (with defaults)
  PUT  /api/consent  -- grant or revoke a specific consent type

Consent types: data_collection, ai_analysis, data_sharing, research.
When no record exists for a consent type, it defaults to not-granted.

@decision DEC-CONSENT-001
@title Consent stored per-user with upsert semantics and default-deny
@status accepted
@rationale Default-deny (no record = not granted) is the safest default for
    a healthcare application. The GET endpoint fills in missing consent types
    with explicit not-granted entries so the frontend always receives a
    complete picture. PUT uses upsert so granting and revoking are idempotent.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(prefix="/consent", tags=["consent"])

CONSENT_TYPES = ("data_collection", "ai_analysis", "data_sharing", "research")


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


def _defaults_for_missing(existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fill in default not-granted entries for consent types with no record."""
    present = {r["consent_type"] for r in existing}
    result = list(existing)
    for ct in CONSENT_TYPES:
        if ct not in present:
            result.append({
                "consent_type": ct,
                "granted": False,
                "version": "1.0",
                "granted_at": None,
                "revoked_at": None,
            })
    return sorted(result, key=lambda r: r["consent_type"])


@router.get("")
async def get_consents(
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> list[dict[str, Any]]:
    """Return the authenticated user's consent records.

    For consent types with no existing record, a default not-granted entry
    is included so the caller always receives all four consent types.
    """
    records = await state.get_user_consents(user.id)
    return _defaults_for_missing(records)


@router.put("")
async def set_consent(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, str]:
    """Grant or revoke a consent type for the authenticated user.

    Request body::

        {"consent_type": "data_collection", "granted": true}

    Returns ``{"status": "ok"}`` on success.
    """
    body = await request.json()

    consent_type = body.get("consent_type")
    if consent_type not in CONSENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"consent_type must be one of {list(CONSENT_TYPES)}, got {consent_type!r}",
        )

    granted = body.get("granted")
    if not isinstance(granted, bool):
        raise HTTPException(
            status_code=422,
            detail="granted must be a boolean",
        )

    await state.set_consent(user.id, consent_type, granted)
    return {"status": "ok"}
