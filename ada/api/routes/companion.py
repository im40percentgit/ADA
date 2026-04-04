"""
Companion persona preferences REST endpoints.

  GET  /api/companion/preferences  — get current user's companion preferences
  PUT  /api/companion/preferences  — partial-update companion preferences

When no row exists in the database the GET returns config-driven defaults so
the frontend always receives a fully-populated object without extra handling.
The PUT merges the incoming payload over the current preferences before
upserting, so a caller can update just the name without touching voice or
personality.

@decision DEC-COMPANION-001
@title Companion preferences stored per-user in SQLite companion_preferences table
@status accepted
@rationale Consistent with notification_preferences pattern (DEC-NOTIF-011).
    Per-user row keyed by user_id; defaults come from CompanionConfig so
    unauthenticated or first-time users get a sensible persona immediately.
    Voice is constrained by a DB CHECK (male/female/neutral) to prevent
    invalid values reaching the TTS layer.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

router = APIRouter(prefix="/companion", tags=["companion"])

_DEFAULT_PERSONALITY: dict[str, str] = {
    "warmth": "warm",
    "verbosity": "balanced",
    "formality": "casual",
}

_VALID_VOICE_VALUES = {"male", "female", "neutral"}


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


def _defaults(request: Request) -> dict[str, Any]:
    """Build a defaults dict from the companion section of AdaConfig."""
    cfg = request.app.state.config.companion
    return {
        "name": cfg.default_name,
        "voice": cfg.default_voice,
        "personality": dict(_DEFAULT_PERSONALITY),
    }


@router.get("/preferences")
async def get_preferences(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Return the authenticated user's companion preferences.

    Returns config defaults when no preferences have been saved yet.
    """
    row = await state.get_companion_preferences(user.id)
    if row is None:
        return _defaults(request)
    return row


@router.put("/preferences", status_code=200)
async def update_preferences(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Partial-update the authenticated user's companion preferences.

    Merges the incoming payload over existing prefs so a caller can update
    just the name without losing voice or personality.

    Accepted fields (all optional):
    {
        "name": "Ada",
        "voice": "female",          // must be: male | female | neutral
        "personality": {
            "warmth": "warm",       // warm | neutral | professional
            "verbosity": "balanced",// terse | balanced | expansive
            "formality": "casual"   // casual | formal
        }
    }

    Unknown top-level keys are silently ignored.
    """
    body = await request.json()

    # Load current prefs (or defaults) as the merge base
    current = await state.get_companion_preferences(user.id)
    if current is None:
        current = _defaults(request)

    # Merge allowed top-level scalar fields
    name = body.get("name", current["name"])
    voice = body.get("voice", current["voice"])

    # Enforce voice constraint here so we return a 422 before hitting the DB
    if voice not in _VALID_VOICE_VALUES:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"voice must be one of {sorted(_VALID_VOICE_VALUES)}, got {voice!r}",
        )

    # Deep-merge personality: existing keys updated, new keys added
    personality = {**current["personality"], **body.get("personality", {})}

    merged = {"name": name, "voice": voice, "personality": personality}
    await state.set_companion_preferences(user.id, merged)
    return merged
