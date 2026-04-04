"""
Push notification subscription management and preferences REST endpoints.

  POST   /api/notifications/subscribe       — register a push subscription
  DELETE /api/notifications/subscribe       — unregister a push subscription
  GET    /api/notifications/vapid-key       — return public VAPID key (unauthenticated)
  GET    /api/notifications/preferences     — get per-user notification preferences
  PUT    /api/notifications/preferences     — update per-user notification preferences

The subscribe/unsubscribe and preferences endpoints require a valid JWT.
The vapid-key endpoint is public — the browser needs it before it can authenticate.

@decision DEC-NOTIF-004
@title VAPID keys via env vars, never in config files
@status accepted
@rationale Consistent with the api_key_env pattern throughout config.py.
    Config stores the env var name; runtime reads the value. Empty key
    means push is unconfigured — the frontend handles the empty-string case
    by not registering a service worker subscription.

@decision DEC-NOTIF-011
@title Preferences GET/PUT as inline routes on existing notifications router
@status accepted
@rationale Preferences are a natural extension of the notification resource.
    Adding them to the existing router avoids a new router file and keeps
    all notification concerns co-located. The NotificationPreferenceManager
    is instantiated inline from state + config — no need to store it on
    app.state since it is stateless beyond its config.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User
from ada.notifications.preferences import NotificationPreferenceManager

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _state(request: Request) -> StateManager:
    """Extract StateManager from app.state (injected at startup)."""
    return request.app.state.state_manager


@router.post("/subscribe", status_code=201)
async def subscribe(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> dict[str, Any]:
    """Register a Web Push subscription for the authenticated user.

    Expected body (matches the PushSubscription JS object):
    {
        "endpoint": "https://fcm.googleapis.com/...",
        "keys": {
            "p256dh": "<base64url>",
            "auth": "<base64url>"
        }
    }
    """
    body = await request.json()
    sub_id = str(uuid.uuid4())
    await state.create_push_subscription({
        "id": sub_id,
        "user_id": user.id,
        "endpoint": body["endpoint"],
        "p256dh_key": body["keys"]["p256dh"],
        "auth_key": body["keys"]["auth"],
    })
    return {"id": sub_id}


@router.delete("/subscribe")
async def unsubscribe(
    request: Request,
    user: User = Depends(get_current_user),
    state: StateManager = Depends(_state),
) -> Response:
    """Unregister a push subscription by endpoint URL.

    Expected body:
    { "endpoint": "https://fcm.googleapis.com/..." }
    """
    body = await request.json()
    await state.delete_push_subscription(body["endpoint"])
    return Response(status_code=204)


@router.get("/vapid-key")
async def vapid_key(request: Request) -> dict[str, str]:
    """Return the public VAPID key for frontend push subscription setup.

    This endpoint is intentionally unauthenticated — the browser needs the
    public key to create a PushSubscription before the user may be logged in.
    Returns an empty string when VAPID is not configured (push disabled).
    """
    config = request.app.state.config
    key = os.environ.get(config.notifications.vapid_public_key_env, "")
    return {"public_key": key}


def _pref_mgr(request: Request) -> NotificationPreferenceManager:
    """Build a NotificationPreferenceManager from app config + state."""
    config = request.app.state.config
    state = request.app.state.state_manager
    return NotificationPreferenceManager(state, config.notifications.throttle)


@router.get("/preferences")
async def get_preferences(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's notification preferences.

    Returns defaults when no preferences have been explicitly set.
    Keys correspond to event type slugs (e.g. crisis_detected, board_item_added).
    """
    mgr = _pref_mgr(request)
    prefs = await mgr.get_preferences(user.id)
    return prefs


@router.put("/preferences", status_code=200)
async def update_preferences(
    request: Request,
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Update the authenticated user's notification preferences.

    Accepts a partial or full preferences object. Unknown keys are silently
    ignored — only recognised preference keys are persisted. Merges with
    existing preferences so a partial update preserves unchanged settings.

    Expected body (all fields optional):
    {
        "crisis_detected": true,
        "board_item_suggested": false,
        "board_item_added": true,
        "board_item_checked": false,
        "daily_summary_generated": true,
        "circle_member_added": true
    }
    """
    body = await request.json()
    mgr = _pref_mgr(request)

    # Merge incoming fields over current preferences
    current = await mgr.get_preferences(user.id)
    merged = {**current, **{k: v for k, v in body.items() if k in current}}
    await mgr.set_preferences(user.id, merged)
    return merged
