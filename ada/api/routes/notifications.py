"""
Push notification subscription management REST endpoints.

  POST   /api/notifications/subscribe    — register a push subscription
  DELETE /api/notifications/subscribe    — unregister a push subscription
  GET    /api/notifications/vapid-key    — return public VAPID key (unauthenticated)

The subscribe/unsubscribe endpoints require a valid JWT. The vapid-key
endpoint is public — the browser needs it before it can authenticate.

@decision DEC-NOTIF-004
@title VAPID keys via env vars, never in config files
@status accepted
@rationale Consistent with the api_key_env pattern throughout config.py.
    Config stores the env var name; runtime reads the value. Empty key
    means push is unconfigured — the frontend handles the empty-string case
    by not registering a service worker subscription.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from ada.api.auth import get_current_user
from ada.core.state import StateManager
from ada.models.user import User

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


@router.delete("/subscribe", status_code=204)
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
